from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals
)

import os
import uuid
import docker
import atexit
import tarfile
import threading
import json
import enum
from collections import namedtuple

from jinja2 import Template, Environment, PackageLoader, select_autoescape

from ._logging import create_logger
from .redis_controller import RedisController

from amqp_common import (
    ConnectionParameters,
    Credentials,
    PublisherSync,
    RpcServer
)


DOCKERFILE_TPL_MAP = {
    'py3': 'Dockerfile.py3.tpl',
    'r4a_ros2_py': 'Dockerfile.r4a_ros2_py.tpl',
    # 'ros2_package': 'Dockerfile.ros2_package.tpl'  ## Not yet supported
}



class AppType(enum.Enum):
    py3 = 1
    r4a_ros2_py = 2


class AppModel(object):

    def __init__(self, name=None, app_type=None, state=0,
                 docker_image_name=None, docker_container_id=None,
                 docker_container_name=None):
        self.name = name
        self.app_type = app_type
        self.state = state
        self.docker_image_name = docker_image_name
        self.docker_container_id = docker_container_id
        self.docker_container_name = docker_container_name
        self.created_at = -1
        self.updated_at = -1

    @property
    def docker(self):
        return {
            'image': {
                'name': self.docker_image_name
            },
            'container': {
                'name': self.docker_container_name,
                'id': self.docker_container_id
            }
        }

    def serialize(self):
        _d = {
            'name': self.name,
            'type': self.app_type,
            'state': self.state,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'docker': {
                'image': {
                    'name': self.docker_image_name
                },
                'container': {
                    'name': self.docker_container_name,
                    'id': self.docker_container_id
                }
            }
        }
        return _d


class AppBuilderDocker(object):
    BUILD_TMP_DIR = '/tmp/app-manager/apps/'
    APP_DEST_DIR = '/app'
    APP_SRC_DIR = './app'
    DOCKER_DAEMON_URL = 'unix://var/run/docker.sock'
    IMAGE_NAME_PREFIX = 'app'

    def __init__(self, image_prefix='app'):
        self.IMAGE_NAME_PREFIX = image_prefix
        self.docker_client = docker.from_env()
        self.docker_cli = docker.APIClient(base_url=self.DOCKER_DAEMON_URL)
        self.__init_logger()
        self._dockerfile_templates = {}
        self._jinja_env = Environment(
            loader=PackageLoader('device_app_manager', 'templates'),
            autoescape=select_autoescape(['tpl', 'Dockerfile'])
        )
        self._load_app_templates()

    def build_app(self, app_name, app_type, app_tarball_path):
        ## Adds a prefix to create docker image tag.
        image_name = '{}-{}'.format(self.IMAGE_NAME_PREFIX, app_name)
        app_dir = self._prepare_build(app_name, app_type, app_tarball_path)
        self._build_image(app_dir, image_name)
        _app = AppModel(app_name, app_type, docker_image_name=image_name)
        return _app

    def __init_logger(self):
        """Initialize Logger."""
        self.log = create_logger(self.__class__.__name__)

    def _build_image(self, app_dir, image_name):
        self.log.debug('[*] - Building image {} ...'.format(image_name))
        try:
            image, logs = self.docker_client.images.build(
                path=app_dir,
                tag=image_name,
                rm=True,
                forcerm=True
            )
            for l in logs:
                self.log.debug(l)
        except docker.errors.BuildError as e:
            self.log.error('Build for application <{}> failed!'.format(
                image_name))
            for line in e.build_log:
                if 'stream' in line:
                    self.log.error(line['stream'].strip())
            raise e

    def _prepare_build(self, app_name, app_type, app_tarball_path=None):
        # Validate Application type
        if app_type not in DOCKERFILE_TPL_MAP:
            raise ValueError('Application type not supported!')

        app_tmp_dir = os.path.join(self.BUILD_TMP_DIR,
                               app_name)

        # Create temp dir if it does not exist
        if not os.path.exists(app_tmp_dir):
            os.makedirs(app_tmp_dir, exist_ok=True)

        app_src_dir = os.path.join(app_tmp_dir, 'app')
        ## Create Application Dockerfile.
        ##  - app/
        ##  - Dockerfile
        dockerfile_path = os.path.join(app_tmp_dir, 'Dockerfile')

        self._untar_app(app_tarball_path, app_src_dir)
        self._create_dockerfile(app_type, self.APP_SRC_DIR, dockerfile_path)
        return app_tmp_dir

    def _create_dockerfile(self, app_type, app_src_dir, dest_path):
        _tpl = self._dockerfile_templates[app_type]
        dockerfile = _tpl.render(
            app_src_dir=app_src_dir,
            app_dest_dir=self.APP_DEST_DIR
            )
        with open(dest_path, 'w') as fp:
            fp.write(dockerfile)

    def _untar_app(self, tarball_path, dest_path):
        self.log.debug(
            '[*] - Decompressing application tarball <{}> ...'.format(
                tarball_path)
        )
        if tarball_path.endswith('tar.gz'):
            tar = tarfile.open(tarball_path)
            tar.extractall(dest_path)
            tar.close()
        else:
            raise ValueError('Not a tarball')

    def _load_app_templates(self):
        _current_dir = os.path.dirname(os.path.abspath(__file__))
        _templates_dir = os.path.join(_current_dir, 'templates')
        for key in DOCKERFILE_TPL_MAP:
            _tplpath = os.path.join(_templates_dir,DOCKERFILE_TPL_MAP[key])
            if os.path.isfile(_tplpath):
                self.log.info(
                    'Loading Application Template for type {}'.format(key))
                # self.dockerfile_templates['key'] = Template(_tplpath)
                _tpl = self._jinja_env.get_template(DOCKERFILE_TPL_MAP[key])
                self._dockerfile_templates[key] = _tpl


class AppExecutorDocker(object):
    DOCKER_DAEMON_URL = 'unix://var/run/docker.sock'
    PLATFORM_APP_LOGS_TOPIC_TPL = 'thing.x.app.y.logs'
    PLATFORM_APP_STATS_TOPIC_TPL = 'thing.x.app.y.stats'
    APP_STARTED_EVENT = 'thing.x.app.y.started'
    APP_STOPED_EVENT = 'thing.x.app.y.stoped'

    def __init__(self, platform_params, redis_params,
                 redis_app_list_name='appmanager.apps',
                 remote_logging=True, send_stats=False):
        self.platform_params = platform_params
        self.docker_client = docker.from_env()
        self.docker_cli = docker.APIClient(base_url=self.DOCKER_DAEMON_URL)
        self.__init_logger()
        self.redis = RedisController(redis_params)
        self.running_apps = []  # Array of tuples (app_name, container_name)
        self.remote_logging = remote_logging
        self.send_stats = send_stats
        ## TODO: Might change!
        self._device_id = self.platform_params.credentials.username

    def __init_logger(self):
        """Initialize Logger."""
        self.log = create_logger(self.__class__.__name__)

    def run_app(self, app_name):
        image_id = self.redis.get_app_image(app_name)
        _container_name = app_name
        _container = self._run_container(image_id, _container_name)

        self.redis.set_app_state(app_name, 1)
        self.redis.set_app_container(app_name, _container_name, _container.id)
        self.redis.save_db()

        self._send_app_started_event(app_name)

        log_thread = None
        if self.remote_logging:
            log_thread = self._detach_app_logging(_container_name, _container)

        stats_thread = None
        if self.send_stats:
            stats_thread = self._detach_app_stats(_container_name, _container)

        exit_capture_thread = self._detach_app_exit_listener(_container_name,
                                                             _container)

        self.running_apps.append((app_name, _container_name, _container,
                                  log_thread, stats_thread,
                                  exit_capture_thread))

    def stop_app(self, app_name):
        if not self.redis.app_is_running(app_name):
            raise ValueError('Application is not running')
        _container_name = self.redis.get_app_container(app_name)
        self.log.debug('Killing container: {}'.format(_container_name))
        c = self.docker_client.containers.get(_container_name)
        c.stop()
        _aidx = -1
        for i in range(len(self.running_apps)):
            if self.running_apps[i][0] == app_name:
                _aidx = i
        if _aidx == -1:
            self._app_exit_handler(app_name, c)
        else:
            del self.running_apps[_aidx]

    def _run_container(self, image_id, container_name,
                       detach=True, privileged=False):
        container = self.docker_client.containers.run(
            image_id,
            name=container_name,
            detach=detach,
            # auto_remove=True,
            # network='host',
            network_mode='host',
            ipc_mode='host',
            pid_mode='host',
            # publish_all_ports=True,
            # remove=True
        )
        self.log.debug('Application Container created!')
        return container

    def _wait_app_exit(self, app_name, stop_event, container):
        container.wait()
        self._app_exit_handler(app_name, container)

    def _app_exit_handler(self, app_name, container):
        self.redis.set_app_state(app_name, 0)
        self.redis.save_db()
        try:
            container.remove(force=True)
        except docker.errors.APIError:
            pass
        self._send_app_stoped_event(app_name)

    def _send_app_stoped_event(self, app_name):
        event_uri = self.APP_STOPED_EVENT.replace(
            'x', self._device_id).replace('y', app_name)

        p = PublisherSync(
            event_uri,
            connection_params=self.platform_params,
            debug=False
        )
        p.publish({})
        self.log.debug(
            'Send <app_stopped> event for application {}'.format(app_name))
        p.close()
        del p

    def _send_app_started_event(self, app_name):
        event_uri = self.APP_STARTED_EVENT.replace(
            'x', self._device_id).replace('y', app_name)

        p = PublisherSync(
            event_uri,
            connection_params=self.platform_params,
            debug=False
        )
        p.publish({})
        self.log.debug(
            'Sent <app_started> event for application {}'.format(app_name))
        p.close()
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
        app_logs_pub = PublisherSync(
                topic_logs, connection_params=self.platform_params,
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

        app_stats_pub = PublisherSync(
                topic_stats, connection_params=self.platform_params,
                debug=False)

        self.log.info('Initiated remote platform stats publisher: {}'.format(
            topic_stats))

        for line in container.stats(
                container=container_id,
                decode=True,
                stream=True):
            _stats_msg = line.strip().decode('utf-8')
            app_stats_pub.publish(_stats_msg)
            if stop_event.is_set():
                break

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
                             args=(app_name, t_stop_event, container))
        t.daemon = True
        t.start()
        app_exit_thread = {
            'thread': t,
            'stop_event': t_stop_event
        }
        return app_exit_thread


class Application(object):
    IMAGE = 'python:3.7-alpine'
    REDIS_APP_LIST_NAME = 'appmanager.apps'

    def __init__(
        self,
        app_name,
        app_type,
        platform_params,
        name=None,
        verbose=None,
        remote_logging=True,
        send_app_stats=False,
        redis_host='localhost',
        redis_port=6379,
        redis_db=0,
        redis_password=None,
        redis_app_list_name='appmanager.apps'
    ):

        self.app_type = app_type
        self.app_name = app_name
        self.app_state = None
        self.app_tar_path = None
        self.image_id = None
        self.docker_container = None
        self.platform_params = platform_params
        self.platform_creds = platform_params.credentials
        self.remote_logging = remote_logging
        self.send_app_stats = send_app_stats

        self.REDIS_APP_LIST_NAME = redis_app_list_name

        # Register callback for garbage collector exit. Cleanup.
        atexit.register(self._cleanup)

        self.__init_logger()

        self.redis = RedisController(redis_host, redis_port, redis_db,
                                     redis_password,
                                     app_list_name=self.REDIS_APP_LIST_NAME)

        try:
            self._load_app_info_from_db()
        except ValueError as exc:
            # Does not exist locally
            self.log.warn('Application does not exist locally.')
            self.image_id = self.app_name

        self.container = None
        self.script_dir = os.path.dirname(os.path.realpath(__file__))

        # self.container_name = self.docker_container['name'] if self.docker_container \
        #     is not None else 'app-r4a-{}'.format(self.app_name)
        self.container_name = self.docker_container['name'] if self.docker_container \
            is not None else self.app_name
        self.container_id = self.docker_container['id'] if self.docker_container \
            is not None else None

        self.app_stats_thread = None
        self.app_log_thread = None


    def stop(self):
        self._send_appstoped_event(self.app_name)
        self._cleanup()



    def _read_dockerfile_template(self, fname):
        tpl_path = os.path.join(self.script_dir, 'templates', fname)
        with open(tpl_path, "r+") as fp:
            dockerfile_tpl = fp.read()
            return dockerfile_tpl

    def _gen_uid(self):
        return uuid.uuid4().hex[0:8]

    def _serialize(self):
        return {
            'name': self.app_name,
            'state': self.app_state,
            'type': self.app_type,
            'tarball_path': self.app_tar_path,
            'docker_image': self.image_id,
            'docker_container': {
                'name': self.container_name,
                'id': self.container_id
            }
        }

    def _cleanup(self):
        if not self.docker_client:
            return
        try:
            self.log.debug('Killing container: {}'.format(self.container_name))
            c = self.docker_client.containers.get(self.container_name)
            c.remove(force=True)
            if self.app_stats_thread:
                self.app_stats_thread['stop_event'].set()
            if self.app_log_thread:
                self.app_log_thread['stop_event'].set()
        except docker.errors.NotFound as e:
            self.log.debug(
                'Could not kill container <{}>'.format(self.container_name))