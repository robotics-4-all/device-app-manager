import os
import uuid
import docker
import atexit
import tarfile
import threading
import json
import enum
from collections import namedtuple
import yaml
import time

from jinja2 import Template, Environment, PackageLoader, select_autoescape

from device_app_manager._logging import create_logger
from device_app_manager.redis_controller import RedisController

from commlib.transports.redis import ConnectionParameters as RedisParams
from commlib.logger import Logger


DOCKER_COMMAND_MAP = {
    'py3': ['python3', '-u', 'app.py'],
    'r4a_commlib': ['python', '-u', 'app.py'],
    'nodered': [],
    'r4a_nodered': []
}


class DockerContainerConfig(object):
    auto_remove = True
    network_mode = 'host'
    ipc_mode = 'host'
    pid_mode = 'host'
    publish_all_ports = False
    privileged = False


class AppExecutorDocker(object):
    DOCKER_DAEMON_URL = 'unix://var/run/docker.sock'
    PLATFORM_APP_LOGS_TOPIC_TPL = 'thing.x.app.y.logs'
    PLATFORM_APP_STATS_TOPIC_TPL = 'thing.x.app.y.stats'
    APP_STARTED_EVENT = 'thing.x.app.y.started'
    APP_STOPED_EVENT = 'thing.x.app.y.stopped'

    def __init__(self,
                 redis_params: dict,
                 redis_app_list_name: str,
                 on_app_started: callable = True,
                 on_app_stopped: callable = True,
                 logger = None):
        """Constructor.

        Args:
            platform_params (ConnectionParameters):
            redis_params (dict):
            redis_app_list_name (str):
            app_started_event (str):
            app_stopped_event (str):
            app_logs_topic (str):
            app_stats_topic (str):
            publish_logs (str):
            publish_stats (str):
        """
        self.docker_client = docker.from_env()
        if logger is None:
            logger = Logger('AppManager-DockerExecutor')
        self.log = logger
        self.redis = RedisController(redis_params, redis_app_list_name)
        self.running_apps = []  # Array of tuples (app_name, container_name)

        self.container_config = DockerContainerConfig()
        self._rparams = RedisParams(host='localhost')

        self._on_app_started = on_app_started
        self._on_app_stopped = on_app_stopped

    def run_app(self, app_name: str,
                app_args: list = [],
                auto_remove: bool = False,
                logs_publisher = None,
                stats_publisher = None):
        """Run an Application.

        Args:
            app_name (str): Application name.
            app_args (list): Application Arguments passed via stdin.
        """
        image_id = self.redis.get_app_image(app_name)
        _container_name = app_name

        app_type = self.redis.get_app_type(app_name)
        ## DIRTY SOLUTION!!
        docker_cmd = DOCKER_COMMAND_MAP[app_type]
        if app_args is not None and docker_cmd is not []:
            docker_cmd = docker_cmd + app_args

        try:
            _container = self._run_container(image_id, _container_name,
                                             cmd=docker_cmd)
        except Exception as exc:
            self.log.error(exc, exc_info=True)
            raise exc

        self.redis.set_app_state(app_name, 1)
        self.redis.set_app_container(app_name, _container_name, _container.id)
        self.redis.save_db()

        log_thread = None
        if logs_publisher is not None:
            log_thread = self._detach_app_logging(_container_name, _container,
                                                  logs_publisher)

        stats_thread = None
        if stats_publisher is not None:
            stats_thread = self._detach_app_stats(_container_name, _container,
                                                  stats_publisher)

        exit_capture_thread = self._detach_app_exit_listener(_container_name,
                                                             _container,
                                                             auto_remove)

        self.running_apps.append((app_name, _container_name, _container,
                                  log_thread, stats_thread,
                                  exit_capture_thread))

        # Fire the on_app_started callback
        if self._on_app_started is not None:
            self._on_app_started(app_name)

    def stop_app(self, app_name: str) -> None:
        """Stops application given its name

        Args:
            app_name (str): Application Name (==app-id).
        """
        if not self.redis.app_is_running(app_name):
            raise ValueError('Application <{}> is not running'.format(app_name))
        _container_id = self.redis.get_app_container(app_name)
        self.log.debug('Killing container: {}'.format(_container_id))
        c = self.docker_client.containers.get(_container_id)
        try:
            c.stop(timeout=10)
            c.wait()
        except docker.errors.APIError as exc:  # Not running case
            self.log.warning(exc)
        ## <---------------------------------------------

    def _run_container(self, image_id, container_name, cmd=None):
        """Run the application container.

        Args:
            image_id (str):
            container_name (str):
            cmd (list):
        """
        self.log.debug(
            'Starting application {} with cmd {}'.format(image_id, cmd))
        self.log.debug('-------- Executing within Container... --------->')
        container = self.docker_client.containers.run(
            image_id,
            name=container_name,
            detach=True,
            network_mode=self.container_config.network_mode,
            ipc_mode=self.container_config.ipc_mode,
            pid_mode=self.container_config.pid_mode,
            command=cmd
        )
        self.log.debug('<------------------------------------------------')
        self.log.debug('Application Container created - [{}:{}]'.format(
            container_name, container.id))
        return container

    def _wait_app_exit(self, app_name, container, auto_remove=False):
        container.wait()
        self._app_exit_handler(app_name, container, auto_remove)

    def _app_exit_handler(self, app_name, container, auto_remove=False):
        try:
            if not self.redis.app_exists(app_name):
                raise RuntimeError(
                    f'[AppExitHandler] - App <{app_name}> does not exist')
            self._on_app_stopped(app_name)
            container.remove(force=True)
            self.redis.set_app_state(app_name, 0)
            if auto_remove:
                self.redis.delete_app(app_name)
                self.docker_client.images.remove(container.image.id,
                                                 force=True)
            self.redis.save_db()

            _aidx = -1
            for i in range(len(self.running_apps)):
                if self.running_apps[i][0] == app_name:
                    _aidx = i
            if _aidx != -1:
                del self.running_apps[_aidx]
        except docker.errors.APIError as exc:
            self.log.error(exc, exc_info=True)
        except Exception as exc:
            self.log.error(exc, exc_info=True)

    def _detach_app_logging(self, app_name, container, publisher):
        t_stop_event = threading.Event()
        t = threading.Thread(target=self._app_logs_publish_loop,
                             args=(app_name, t_stop_event, container,
                                   publisher))
        t.daemon = True
        t.start()
        app_log_thread = {
            'thread': t,
            'stop_event': t_stop_event
        }
        return app_log_thread

    def _app_logs_publish_loop(self, app_name, stop_event, container,
                              publisher):
        self.log.info(
            f'Initiated remote platform logs publisher for app <{app_name}>')
        try:
            for line in container.logs(stream=True):
                _log_msg = line.strip().decode('utf-8')
                msg = {
                    'timestamp': 0,
                    'log_msg': _log_msg
                }
                publisher.publish(msg)
                if stop_event.is_set():
                    break
        except Exception:
            pass

    def _detach_app_stats(self, app_name, container, publisher):
        t_stop_event = threading.Event()
        t = threading.Thread(target=self._app_stats_publish_loop,
                             args=(app_name, t_stop_event, container,
                                   publisher))
        t.daemon = True
        t.start()
        app_stats_thread = {
            'thread': t,
            'stop_event': t_stop_event
        }
        return app_stats_thread

    def _app_stats_publish_loop(self, app_name, stop_event, container,
                                publisher):
        self.log.info(
            f'Initiated remote platform stats publisher for app <{app_name}>')

        for line in container.stats(
                decode=True,
                stream=True):
            _stats_msg = line
            publisher.publish(_stats_msg)
            if stop_event.is_set():
                break
        self.log.info(
            f'Stats Publisher stopped for Application <{app_name}>')

    def _detach_app_exit_listener(self, app_name, container, auto_remove=False):
        t_stop_event = threading.Event()
        t = threading.Thread(target=self._wait_app_exit,
                             args=(app_name, container, auto_remove))
        t.daemon = True
        t.start()
        app_exit_thread = {
            'thread': t,
            'stop_event': t_stop_event
        }
        return app_exit_thread
