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

from ._logging import create_logger
from .redis_controller import RedisController

from commlib.transports.amqp import Publisher

from commlib.transports.redis import ActionClient, RPCClient
from commlib.transports.redis import ConnectionParameters as RedisParams


DOCKER_COMMAND_MAP = {
    'py3': ['python3', '-u', 'app.py'],
    'r4a_ros2_py': ['python3', '-u', 'app.py'],
    'r4a_commlib': ['python', '-u', 'app.py']
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

    def __init__(self, platform_params, redis_params,
                 redis_app_list_name='appmanager.apps',
                 app_started_event='thing.x.app.y.started',
                 app_stopped_event='thing.x.app.y.stopped',
                 app_logs_topic='thing.x.app.y.logs',
                 app_stats_topic='thing.x.app.y.stats',
                 publish_logs=True, publish_stats=False,
                 sound_events=True):
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
        atexit.register(self._cleanup)

        self.platform_params = platform_params
        self.PLATFORM_APP_LOGS_TOPIC_TPL = app_logs_topic
        self.PLATFORM_APP_STATS_TOPIC_TPL = app_stats_topic
        self.APP_STARTED_EVENT = app_started_event
        self.APP_STOPED_EVENT = app_stopped_event

        self.sound_events = sound_events

        self.docker_client = docker.from_env()
        self.docker_cli = docker.APIClient(base_url=self.DOCKER_DAEMON_URL)
        self.__init_logger()
        self.redis = RedisController(redis_params, redis_app_list_name)
        self.running_apps = []  # Array of tuples (app_name, container_name)
        self.publish_logs = publish_logs
        self.publish_stats = publish_stats
        ## TODO: Might change!
        self._device_id = self.platform_params.credentials.username
        self.container_config = DockerContainerConfig()
        self._rparams = RedisParams(host='localhost')

        self.custom_ui_rpc_client_start = RPCClient(
            conn_params=self._rparams,rpc_name="device.ui.custom.start")
        self.custom_ui_rpc_client_stop = RPCClient(
            conn_params=self._rparams, rpc_name="device.ui.custom.stop")

        if self.sound_events:
            self._speak_action_name = \
                '/robot/robot_1/actuator/audio/speaker/usb_speaker/d0/id_0/speak'
            self._speak_action = ActionClient(
                conn_params=self._rparams, action_name=self._speak_action_name)

    def __init_logger(self):
        """Initialize Logger."""
        self.log = create_logger(self.__class__.__name__)

    def run_app(self, app_name, app_args=[]):
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
        if app_args is not None:
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

        self._send_app_started_event(app_name)

        # Start custom ui if exists
        ui = self.redis.get_app(app_name)['ui']
        if ui is not None:
            self.log.info("Raising UI from the dead")
            res = self.custom_ui_rpc_client_start.call({"dir": ui + "/"})
            self.log.info(f"Response from Custom UI: {res}")
        else:
            self.log.info("No UI for this app")

        log_thread = None
        if self.publish_logs:
            log_thread = self._detach_app_logging(_container_name, _container)

        stats_thread = None
        if self.publish_stats:
            stats_thread = self._detach_app_stats(_container_name, _container)

        exit_capture_thread = self._detach_app_exit_listener(_container_name,
                                                             _container)

        self.running_apps.append((app_name, _container_name, _container,
                                  log_thread, stats_thread,
                                  exit_capture_thread))

        self._on_app_started(app_name)

    def stop_app(self, app_name):
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
        except docker.errors.APIError as exc:  # Not running case
            self.log.warning(exc)

        ## Call Exit handler for this application ------>
        _aidx = -1
        for i in range(len(self.running_apps)):
            if self.running_apps[i][0] == app_name:
                _aidx = i
        if _aidx != -1:
            del self.running_apps[_aidx]
            c.wait()
        ## <---------------------------------------------

    def _cleanup(self):
        ## TODO
        pass

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

    def _wait_app_exit(self, app_name, container):
        container.wait()
        self._app_exit_handler(app_name, container)

    def _app_exit_handler(self, app_name, container):
        try:
            if not self.redis.app_exists(app_name):
                raise RuntimeError(
                    '[AppExitHandler] - App <{}> does not exist'.format(
                        app_name))
            self._on_app_stopped(app_name)
            container.remove(force=True)
            self.redis.set_app_state(app_name, 0)
            self._send_app_stopped_event(app_name)
            self.redis.save_db()
        except docker.errors.APIError as exc:
            self.log.error(exc, exc_info=True)
        except Exception as exc:
            self.log.error(exc, exc_info=True)

    def _send_app_stopped_event(self, app_name):
        event_uri = self.APP_STOPED_EVENT.replace(
            'x', self._device_id).replace('y', app_name)

        p = Publisher(
            topic=event_uri,
            conn_params=self.platform_params,
            debug=False
        )
        p.publish({})
        self.log.debug(
            'Send <app_stopped> event for application {}'.format(app_name))
        del p

    def _send_app_started_event(self, app_name):
        event_uri = self.APP_STARTED_EVENT.replace(
            'x', self._device_id).replace('y', app_name)

        p = Publisher(
            topic=event_uri,
            conn_params=self.platform_params,
            debug=False
        )
        p.publish({})
        self.log.debug(
            'Sent <app_started> event for application {}'.format(app_name))
        del p

    def _detach_app_logging(self, app_name, container):
        t_stop_event = threading.Event()
        t = threading.Thread(target=self._app_log_publish_loop,
                             args=(app_name, t_stop_event, container))
        t.daemon = True
        t.start()
        app_log_thread = {
            'thread': t,
            'stop_event': t_stop_event
        }
        return app_log_thread

    def _app_log_publish_loop(self, app_name, stop_event, container):
        topic_logs = self.PLATFORM_APP_LOGS_TOPIC_TPL.replace(
                'x', self._device_id).replace(
                        'y', app_name)
        app_logs_pub = Publisher(topic=topic_logs,
                                 conn_params=self.platform_params,
                                 debug=False)

        self.log.info('Initiated remote platform log publisher: {}'.format(
            topic_logs))

        try:
            for line in container.logs(stream=True):
                _log_msg = line.strip().decode('utf-8')
                self.log.debug(_log_msg)
                msg = {
                    'timestamp': 0,
                    'log_msg': _log_msg
                }
                app_logs_pub.publish(msg)
                if stop_event.is_set():
                    break
        except Exception:
            pass

    def _app_stats_publish_loop(self, app_name, stop_event, container):
        topic_stats = self.PLATFORM_APP_STATS_TOPIC_TPL.replace(
                'x', self._device_id).replace(
                        'y', app_name)

        app_stats_pub = Publisher(topic=topic_stats,
                                  conn_params=self.platform_params,
                                  debug=False)

        self.log.info(
            'Initiated remote platform stats publisher: {}'.format(topic_stats))

        for line in container.stats(
                decode=True,
                stream=True):
            _stats_msg = line
            app_stats_pub.publish(_stats_msg)
            if stop_event.is_set():
                break
        self.log.info(
            'Stats Publisher stopped for Application <{}>'.format(app_name))

    def _detach_app_stats(self, app_name, container):
        t_stop_event = threading.Event()
        t = threading.Thread(target=self._app_stats_publish_loop,
                             args=(app_name, t_stop_event, container))
        t.daemon = True
        t.start()
        app_stats_thread = {
            'thread': t,
            'stop_event': t_stop_event
        }
        return app_stats_thread

    def _detach_app_exit_listener(self, app_name, container):
        t_stop_event = threading.Event()
        t = threading.Thread(target=self._wait_app_exit,
                             args=(app_name, container))
        t.daemon = True
        t.start()
        app_exit_thread = {
            'thread': t,
            'stop_event': t_stop_event
        }
        return app_exit_thread

    def _on_app_started(self, app_name):
        return
        # MANUAL KILL OF SPEAK HERE
        _text = 'Η εφαρμογή {} ξεκίνησε'.format(app_name)
        speak_goal_data = {
            'text': _text,
            'volume': 50,
            'language': 'el'
        }
        if self.sound_events:
            try:
                self._speak_action.send_goal(speak_goal_data)
            except Exception as exc:
                self.log.error(exc)

    def _on_app_stopped(self, app_name):

        # Stop custom ui if exists
        self.log.info("Banishing UI to the dead")
        res = self.custom_ui_rpc_client_stop.call({}, timeout=1)
        self.log.info(f"Response from Custom UI: {res}")

        _text = 'Η εφαρμογή {} τερμάτισε'.format(app_name)
        speak_goal_data = {
            'text': _text,
            'volume': 50,
            'language': 'el'
        }
        if self.sound_events:
            try:
                self._speak_action.send_goal(speak_goal_data, timeout=1)
            except Exception as exc:
                self.log.error(exc)
