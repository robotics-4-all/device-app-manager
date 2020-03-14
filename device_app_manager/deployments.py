from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals
)


class AppDeployment(object):
    PLATFORM_APP_LOGS_TOPIC_TPL = 'thing.x.app.y.logs'
    PLATFORM_APP_STATS_TOPIC_TPL = 'thing.x.app.y.stats'
    APP_STARTED_EVENT = 'thing.x.app.y.started'
    APP_STOPED_EVENT = 'thing.x.app.y.stoped'
    TEMP_DIR = '/tmp/app-deployments'
    IMAGE = 'python:3.7-alpine'
    APP_DEST_DIR = '/app'
    APP_SRC_DIR = './app'
    DEPLOYMENT_BASEDIR = '/tmp/app-deployments'
    # If set to tcp can deploy remotely
    DOCKER_DAEMONN_URL = 'unix://var/run/docker.sock'

    def __init__(
        self,
        platform_params,
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
        self.platform_params = platform_params
        self.platform_creds = platform_params.credentials
        self.app_tarball_path = app_tarball_path
        self.remote_logging = remote_logging
        self.send_app_stats = send_app_stats

        self.container = None
        self.image = None
        self.script_dir = os.path.dirname(os.path.realpath(__file__))

        self.deployment_id = self._gen_uid()
        self.container_id = self.deployment_id
        self.app_id = self.deployment_id
        self.image_id = 'app-{}'.format(self.deployment_id)

        # Instantiate a docker client
        # self.docker_client = docker.APIClient(base_url=self.DOCKER_DAEMONN_URL)
        self.docker_client = docker.from_env()
        self.__init_logger()
        atexit.register(self._cleanup)

    def __init_logger(self):
        """Initialize Logger."""
        self.log = create_logger(
            self.__class__.__name__ + '-' + self.deployment_id)

    def start(self):
        deployment_id = self.deploy(self.app_tarball_path)
        if deployment_id:
            self._send_appstarted_event(self.app_id)
        return deployment_id

    def stop(self):
        self._send_appstoped_event(self.app_id)
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

    def _send_appstarted_event(self, app_id):
        event_uri = self.APP_STARTED_EVENT.replace(
            'x', self.platform_creds.username).replace('y', app_id)

        p = PublisherSync(
            event_uri,
            connection_params=self.platform_params,
            debug=False
        )
        p.publish({})
        p.close()
        del p

    def _send_appstoped_event(self, app_id):
        event_uri = self.APP_STOPED_EVENT.replace(
            'x', self.platform_creds.username).replace('y', app_id)

        p = PublisherSync(
            event_uri,
            connection_params=self.platform_params,
            debug=False
        )
        p.publish({})
        p.close()
        del p

    def _app_log_publish_loop(self, app_id, stop_event):
        topic_logs = self.PLATFORM_APP_LOGS_TOPIC_TPL.replace(
                'x', self.platform_creds.username).replace(
                        'y', app_id)
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

    def _app_stats_publish_loop(self, app_id, stop_event):
        topic_stats = self.PLATFORM_APP_STATS_TOPIC_TPL.replace(
                'x', self.platform_creds.username).replace(
                        'y', app_id)

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

    def run_container(self, image_id, deployment_id, detach=True):
        container = self.docker_client.containers.run(
            image_id,
            name=image_id,
            detach=detach,
            # auto_remove=True,
            # network='host',
            network_mode='host',
            ipc_mode='host',
            pid_mode='host'
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

    def detach_app_logging(self, app_id):
        t_stop_event = threading.Event()
        t = threading.Thread(target=self._app_log_publish_loop,
                             args=(app_id, t_stop_event))
        t.daemon = True
        t.start()
        self.app_log_thread = {
            'thread': t,
            'stop_event': t_stop_event
        }

    def detach_app_stats(self, app_id):
        t_stop_event = threading.Event()
        t = threading.Thread(target=self._app_stats_publish_loop,
                             args=(app_id, t_stop_event))
        t.daemon = True
        t.start()
        self.app_stats_thread = {
            'thread': t,
            'stop_event': t_stop_event
        }

    def deploy(self, app_tarball_path, deployment_id=None):
        deployment_dir = os.path.join(self.DEPLOYMENT_BASEDIR,
                                      self.deployment_id)

        if not os.path.exists(deployment_dir):
            os.mkdir(deployment_dir)

        app_src_dir = os.path.join(deployment_dir, 'app')
        dockerfile_path = os.path.join(deployment_dir, 'Dockerfile')
        image_id = 'app-{}'.format(self.deployment_id)
        self.image_id = image_id

        self._untar(app_tarball_path, app_src_dir)
        self._create_dockerfile_from_tpl(self.APP_SRC_DIR,
                                         self.dockerfile_tpl,
                                         dockerfile_path)

        self._build_image(deployment_dir, image_id)
        _ = self.run_container(image_id, self.deployment_id)
        return self.deployment_id

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
            self.log.debug('Killing container: {}'.format(self.container.id))
            self.container.kill()
        except docker.errors.NotFound as e:
            self.log.debug(
                'Could not kill container <{}>'.format(self.container.id))
        try:
            self.log.debug('Removing container: {}'.format(self.container.id))
            self.container.remove(force=True)
        except docker.errors.NotFound as e:
            self.log.debug(
                'Could not remove container <{}>'.format(self.container.id))
        try:
            self.log.debug('Removing image: {}'.format(self.image.id.split(':')[1]))
            self.docker_client.images.remove(self.image.id.split(':')[1])
        except docker.errors.NotFound as e:
            self.log.debug('Could not remove image <{}>'.format(self.image.id))
        try:
            self.app_stats_thread['stop_event'].set()
        except Exception as e:
            pass
        try:
            self.app_log_thread['stop_event'].set()
        except Exception as e:
            pass


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


