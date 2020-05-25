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
import yaml

from jinja2 import Template, Environment, PackageLoader, select_autoescape

from ._logging import create_logger
from .redis_controller import RedisController
from .app_model import AppModel
from .docker_executor import *
from .docker_builder import *

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


class AppBuilderDocker(object):
    BUILD_DIR = '/tmp/app-manager/apps/'
    APP_DEST_DIR = '/app'
    APP_SRC_DIR = './app'
    DOCKER_DAEMON_URL = 'unix://var/run/docker.sock'
    IMAGE_NAME_PREFIX = 'app'
    APP_INIT_FILE_NAME = 'init.conf'
    APP_INFO_FILE_NAME = 'app.info'
    SCHEDULER_FILE_NAME = 'exec.conf'

    def __init__(self, image_prefix='app',
                 build_dir='/tmp/app-manager/apps/',
                 ):
        self.IMAGE_NAME_PREFIX = image_prefix
        self.BUILD_DIR = build_dir

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
        image_name = '{}{}'.format(self.IMAGE_NAME_PREFIX, app_name)

        app_dir = self._prepare_build(
            app_name, app_type, app_tarball_path)

        self._build_image(app_dir, image_name)

        if app_type == 'r4a_ros2_py':
            init_params = self._read_init_params(
                os.path.join(app_dir, 'app', self.APP_INIT_FILE_NAME))
            app_info = self._read_app_info(
                os.path.join(app_dir, 'app', self.APP_INFO_FILE_NAME))
            scheduler_params = self._read_scheduler_params(
                os.path.join(app_dir, 'app', self.SCHEDULER_FILE_NAME))

            _app = AppModel(app_name, app_type, docker_image_name=image_name,
                            init_params=init_params, app_info=app_info,
                            scheduler_params=scheduler_params)
        else:
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

        app_tmp_dir = os.path.join(self.BUILD_DIR,
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

        ## Dirty Solution!!
        # if app_type == 'r4a_ros2_py':

        return app_tmp_dir

    def _read_yaml_file(self, fpath):
        with open(fpath, 'r') as fstream:
            data = yaml.safe_load(fstream)
            return data

    def _read_init_params(self, fpath):
        return self._read_yaml_file(fpath)['params']

    def _read_app_info(self, fpath):
        return self._read_yaml_file(fpath)

    def _read_scheduler_params(self, fpath):
        return self._read_yaml_file(fpath)

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



