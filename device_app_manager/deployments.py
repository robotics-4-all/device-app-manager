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

from jinja2 import Template

from ._logging import create_logger

from amqp_common import (
    ConnectionParameters,
    Credentials,
    PublisherSync,
    RpcServer
)


class AppDeployment(object):
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

    def __init__(
        self,
        platform_params,
        app_name,
        app_type,
        app_tarball_path,
        group=None,
        target=None,
        name=None,
        args=(),
        kwargs=None,
        verbose=None,
        remote_logging=True,
        send_app_stats=False
    ):
        self.args = args
        self.kwargs = kwargs

        self.app_name = app_name
        self.app_type = app_type
        self.app_tarball_path = app_tarball_path

        self.platform_params = platform_params
        self.platform_creds = platform_params.credentials

        self.remote_logging = remote_logging
        self.send_app_stats = send_app_stats

        self.container = None
        self.image = None
        self.script_dir = os.path.dirname(os.path.realpath(__file__))

        # Register callback for garbage collector exit. Cleanup.
        atexit.register(self._cleanup)

        self.app_name = self._gen_uid() if not self.app_name else self.app_name
        self.image_id = 'app-{}'.format(self.app_name)
        self.container_id = None

        self.app_stats_thread = None
        self.app_log_thread = None

        # Instantiate a docker client
        # self.docker_client = docker.APIClient(base_url=self.DOCKER_DAEMONN_URL)
        self.docker_client = docker.from_env()
        self.__init_logger()

    def __init_logger(self):
        """Initialize Logger."""
        self.log = create_logger(
            self.__class__.__name__ + '-' + self.app_name)


    def stop(self):
        self._send_appstoped_event(self.app_name)
        self._cleanup()

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
            self.log.debug('Not a tarball')

    def _build_image(self, dockerfile_path, image_id):
        self.log.debug('[*] - Building image {} ...'.format(
            image_id))
        self.image, logs = self.docker_client.images.build(
            path=dockerfile_path,
            tag=image_id,
            rm=True,
            forcerm=True
        )
        for l in logs:
            self.log.debug(l)
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
            self.detach_app_logging(deployment_id)
        if self.send_app_stats:
            self.detach_app_stats(deployment_id)

    def detach_app_logging(self, app_name):
        t_stop_event = threading.Event()
        t = threading.Thread(target=self._app_log_publish_loop,
                             args=(app_name, t_stop_event))
        t.daemon = True
        t.start()
        self.app_log_thread = {
            'thread': t,
            'stop_event': t_stop_event
        }

    def detach_app_stats(self, app_name):
        t_stop_event = threading.Event()
        t = threading.Thread(target=self._app_stats_publish_loop,
                             args=(app_name, t_stop_event))
        t.daemon = True
        t.start()
        self.app_stats_thread = {
            'thread': t,
            'stop_event': t_stop_event
        }

    def build(self):
        tmp_dir = os.path.join(self.TMP_DIR,
                               self.app_name)

        # Create temp dir if it does not exist
        if not os.path.exists(tmp_dir):
            os.mkdir(tmp_dir)

        app_src_dir = os.path.join(tmp_dir, 'app')
        dockerfile_path = os.path.join(tmp_dir, 'Dockerfile')

        self._untar(self.app_tarball_path, app_src_dir)
        self._create_dockerfile_from_tpl(self.APP_SRC_DIR,
                                         self.dockerfile_tpl,
                                         dockerfile_path)
        self._build_image(tmp_dir, self.image_id)
        return self.image_id

    def deploy(self):
        self.container_name = self.image_id
        _ = self.run_container(self.image_id, self.container_name)
        return self.container_name, self.container_id

    def _read_dockerfile_template(self, fname):
        tpl_path = os.path.join(self.script_dir, 'templates', fname)
        with open(tpl_path, "r+") as fp:
            dockerfile_tpl = fp.read()
            return dockerfile_tpl

    def _gen_uid(self):
        return uuid.uuid4().hex[0:8]

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
        # try:
        #     self.log.debug('Removing container: {}'.format(self.container.id))
        #     self.container.remove(force=True)
        # except docker.errors.NotFound as e:
        #     self.log.debug(
        #         'Could not remove container <{}>'.format(self.container.id))
        # try:
        #     self.log.debug('Removing image: {}'.format(self.image.id.split(':')[1]))
        #     self.docker_client.images.remove(self.image.id.split(':')[1])
        # except docker.errors.NotFound as e:
        #     self.log.debug('Could not remove image <{}>'.format(self.image.id))


class AppDeploymentPython3(AppDeployment):
    IMAGE = 'python:3.7-alpine'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dockerfile_tpl = self._read_dockerfile_template(
            'Dockerfile.py3.tpl')


class AppDeploymentR4AROS2Py(AppDeployment):
    IMAGE = 'r4a/app-ros2'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dockerfile_tpl = self._read_dockerfile_template(
            'Dockerfile.r4a_ros2_py.tpl')


