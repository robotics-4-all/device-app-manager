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

from jinja2 import Template

from ._logging import create_logger
from .redis_controller import RedisController

from amqp_common import (
    ConnectionParameters,
    Credentials,
    PublisherSync,
    RpcServer
)


class Application(object):
    APP_TYPE = 'py3'
    PLATFORM_APP_LOGS_TOPIC_TPL = 'thing.x.app.y.logs'
    PLATFORM_APP_STATS_TOPIC_TPL = 'thing.x.app.y.stats'
    APP_STARTED_EVENT = 'thing.x.app.y.started'
    APP_STOPED_EVENT = 'thing.x.app.y.stoped'
    TMP_DIR = '/tmp/app-deployments'
    IMAGE = 'python:3.7-alpine'
    APP_DEST_DIR = '/app'
    APP_SRC_DIR = './app'
    TMP_DIR = '/tmp/app-deployments'
    # If set to tcp can deploy remotely
    DOCKER_DAEMONN_URL = 'unix://var/run/docker.sock'
    REDIS_APP_LIST_NAME = 'appmanager.apps'

    def __init__(
        self,
        platform_params,
        app_name,
        group=None,
        target=None,
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

        self.app_type = self.APP_TYPE
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

        self.docker_client = docker.from_env()
        self.docker_cli = docker.APIClient(base_url='unix://var/run/docker.sock')

    def _load_app_info_from_db(self):
        _app = self.redis.get_app(self.app_name)
        # self.app_type = _app['type']
        self.app_state = _app['state']
        self.app_tar_path = _app['tarball_path']
        self.image_id = _app['docker_image']
        self.container_name = _app['docker_container']

    def build(self, app_tarball_path=None):
        tmp_dir = os.path.join(self.TMP_DIR,
                               self.app_name)

        # Create temp dir if it does not exist
        if not os.path.exists(tmp_dir):
            os.mkdir(tmp_dir)

        app_src_dir = os.path.join(tmp_dir, 'app')
        dockerfile_path = os.path.join(tmp_dir, 'Dockerfile')

        self._untar(app_tarball_path, app_src_dir)
        self._create_dockerfile_from_tpl(self.APP_SRC_DIR,
                                         self.dockerfile_tpl,
                                         dockerfile_path)
        self._build_image(tmp_dir, self.image_id)
        if app_tarball_path is not None:
            self.app_tar_path = app_tarball_path
        return self.image_id

    def deploy(self):
        _ = self.run_container(self.image_id, self.container_name)
        return self.container_name, self.container_id

    def run_container(
            self,
            image_id,
            deployment_id,
            detach=True,
            privileged=False
    ):
        container = self.docker_client.containers.run(
            image_id,
            name=deployment_id,
            detach=detach,
            # auto_remove=True,
            # network='host',
            network_mode='host',
            ipc_mode='host',
            pid_mode='host',
            # publish_all_ports=True,
            # remove=True
        )
        self.log.debug('[*] - Container created!')
        self.container = container
        self.container_id = container.id

        if self.remote_logging:
            self._detach_app_logging(deployment_id)
        if self.send_app_stats:
            self._detach_app_stats(deployment_id)

    def stop(self):
        self._send_appstoped_event(self.app_name)
        self._cleanup()

    def __init_logger(self):
        """Initialize Logger."""
        self.log = create_logger(
            self.__class__.__name__ + '-' + self.app_name)

    def _create_dockerfile_from_tpl(self, app_src_dir, tpl_path, dest_path):
        tpl = Template(tpl_path)
        dockerfile = tpl.render(
            image=self.IMAGE,
            app_src_dir=app_src_dir,
            app_dest_dir=self.APP_DEST_DIR
            )
        with open(dest_path, 'w') as fp:
            fp.write(dockerfile)

    def _untar(self, tarball_path, dest_path):
        self.log.debug('[*] - Untar {} ...'.format(tarball_path))
        if tarball_path.endswith('tar.gz'):
            tar = tarfile.open(tarball_path)
            tar.extractall(dest_path)
            tar.close()
        else:
            raise ValueError('Not a tarball')

    def _build_image(self, dockerfile_path, image_id):
        self.log.debug('[*] - Building image {} ...'.format(
            image_id))
        # image, logs = self.docker_client.build(
        #     path=dockerfile_path,
        #     tag=image_id,
        #     rm=True,
        #     forcerm=True
        # )
        # for l in logs:
        #     self.log.debug(l)
        for log_l in self.docker_cli.build(
                path=dockerfile_path,
                tag=image_id,
                rm=True,
                forcerm=True,
                decode=True):
            if 'stream' not in log_l:
                continue
            if log_l['stream'] == '\n':
                continue
            _l = log_l['stream'].replace('\n', '')

            self.log.debug('[Docker Build - {}]: {}'.format(image_id, _l))
        self.log.info('Created docker image <{}>'.format(image_id))

    def _send_appstarted_event(self, app_name):
        event_uri = self.APP_STARTED_EVENT.replace(
            'x', self.platform_creds.username).replace('y', app_name)

        p = PublisherSync(
            event_uri,
            connection_params=self.platform_params,
            debug=False
        )
        p.publish({})
        p.close()
        del p

    def _send_appstoped_event(self, app_name):
        event_uri = self.APP_STOPED_EVENT.replace(
            'x', self.platform_creds.username).replace('y', app_name)

        p = PublisherSync(
            event_uri,
            connection_params=self.platform_params,
            debug=False
        )
        p.publish({})
        p.close()
        del p

    def _app_log_publish_loop(self, app_name, stop_event):
        topic_logs = self.PLATFORM_APP_LOGS_TOPIC_TPL.replace(
                'x', self.platform_creds.username).replace(
                        'y', app_name)
        app_logs_pub = PublisherSync(
                topic_logs, connection_params=self.platform_params,
                debug=False)

        self.log.info('Initiated remote platform log publisher: {}'.format(
            topic_logs))
        container_id = self.container_id
        if container_id is None:
            self.log.error('App with id={} does not exist!')
            return

        for line in self.container.logs(stream=True):
            _log_msg = line.strip().decode('utf-8')
            self.log.debug(_log_msg)
            msg = {
                'timestamp': 0,
                'log_msg': _log_msg
            }
            app_logs_pub.publish(msg)
            if stop_event.is_set():
                break

    def _app_stats_publish_loop(self, app_name, stop_event):
        topic_stats = self.PLATFORM_APP_STATS_TOPIC_TPL.replace(
                'x', self.platform_creds.username).replace(
                        'y', app_name)

        app_stats_pub = PublisherSync(
                topic_stats, connection_params=self.platform_params,
                debug=False)

        self.log.info('Initiated remote platform stats publisher: {}'.format(
            topic_stats))
        container_id = self.container_id
        if container_id is None:
            self.log.error('App with id={} does not exist!')
            return

        for line in self.docker_client.stats(
                container=container_id,
                decode=False,
                stream=True):
            _stats_msg = line.strip().decode('utf-8')
            app_stats_pub.publish(_stats_msg)
            if stop_event.is_set():
                break

    def _detach_app_logging(self, app_name):
        t_stop_event = threading.Event()
        t = threading.Thread(target=self._app_log_publish_loop,
                             args=(app_name, t_stop_event))
        t.daemon = True
        t.start()
        self.app_log_thread = {
            'thread': t,
            'stop_event': t_stop_event
        }

    def _detach_app_stats(self, app_name):
        t_stop_event = threading.Event()
        t = threading.Thread(target=self._app_stats_publish_loop,
                             args=(app_name, t_stop_event))
        t.daemon = True
        t.start()
        self.app_stats_thread = {
            'thread': t,
            'stop_event': t_stop_event
        }

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


class AppPython3(Application):
    IMAGE = 'python:3.7-alpine'
    APP_TYPE = 'py3'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dockerfile_tpl = self._read_dockerfile_template(
            'Dockerfile.py3.tpl')


class AppR4AROS2Py(Application):
    IMAGE = 'r4a/app-ros2'
    APP_TYPE = 'r4a_ros2_py'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dockerfile_tpl = self._read_dockerfile_template(
            'Dockerfile.r4a_ros2_py.tpl')


