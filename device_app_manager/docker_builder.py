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
import shutil
from .exceptions import ApplicationError, InternalError

from jinja2 import Template, Environment, PackageLoader, select_autoescape

from ._logging import create_logger
from .redis_controller import RedisController
from .app_model import AppModel

DOCKERFILE_TPL_MAP = {
    'py3': 'Dockerfile.py3.tpl',
    'r4a_commlib': 'Dockerfile.r4a_commlib.tpl',
    'nodered': 'Dockerfile.nodered.tpl'
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
    VOICE_COMMANDS_FILE_NAME = 'voice-commands.txt'
    APP_UIS_DIR = "/home/pi/.config/device_app_manager/"

    def __init__(self, image_prefix='app', build_dir='/tmp/app-manager/apps/'):
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

        # Check if folder ui in app_dir
        # ------------------------------------------------------------->
        target_dir = None
        self.logger.info('Setup UI component...')
        if os.path.isdir(os.path.join(app_dir, "app", "ui")):
            self.logger.info(f'App <{app_name}> has ui dir!')
            source_dir = os.path.join(app_dir, "app", "ui")
            target_dir = os.path.join(self.APP_UIS_DIR, app_name)
            # Delete old folder if exists
            try:
                shutil.rmtree(target_dir)
            except:
                self.logger.info("No previous ui dir existed")
            shutil.copytree(source_dir, target_dir)
        else:
            self.logger.info(f'App <{app_name}> has no ui dir')
        self.logger.info('Setup UI finished')
        # <------------------------------------------------------------

        if app_type == 'r4a_commlib':
            self.logger.info('R4A APP using commlib!')
            if not os.path.isfile(os.path.join(app_dir, 'app',
                                               self.APP_INFO_FILE_NAME)):
                raise ApplicationError('Missing app.info file')
            try:
                init_params = self._read_init_params(
                    os.path.join(app_dir, 'app', self.APP_INIT_FILE_NAME))
            except Exception:
                self.logger.warn('Missing init.conf file!')
                init_params = {}
            try:
                app_info = self._read_app_info(
                    os.path.join(app_dir, 'app', self.APP_INFO_FILE_NAME))
            except Exception as exc:
                self.logger.error('Could not properly read app.info file!',
                                  exc_info=True)
                raise ApplicationError('File app.info seems malformed!')
            try:
                scheduler_params = self._read_scheduler_params(
                    os.path.join(app_dir, 'app', self.SCHEDULER_FILE_NAME))
            except Exception:
                self.logger.warn('Missing <exec.conf> file!')
                scheduler_params = {}
            try:
                voice_params = self._read_voice_activation_params(
                    os.path.join(app_dir, 'app', self.VOICE_COMMANDS_FILE_NAME))
            except Exception:
                self.logger.warn('Missing <voice-commands.txt> file!')
                voice_params = {}

            _app = AppModel(app_name, app_type, docker_image_name=image_name,
                            init_params=init_params, app_info=app_info,
                            scheduler_params=scheduler_params, ui=target_dir,
                            voice_command_params=voice_params)
        elif app_type == 'py3':
            _app = AppModel(app_name, app_type, docker_image_name=image_name)
        elif app_type == 'nodered':
            _app = AppModel(app_name, app_type, docker_image_name=image_name)
        else:
            raise ValueError('Not supported app_type')

        self._build_image(app_dir, image_name)

        try:
            shutil.rmtree(app_dir)
        except Exception as exc:
            self.logger.error('Failed to remove decompressed application dir',
                              exc_info=True)
        return _app

    def __init_logger(self):
        """Initialize logger."""
        self.logger = create_logger(self.__class__.__name__)

    def _build_image(self, app_dir, image_name):
        self.logger.debug('[*] - Building image {} ...'.format(image_name))
        try:
            image, logs = self.docker_client.images.build(
                path=app_dir,
                tag=image_name,
                rm=True,
                forcerm=True
            )
            for l in logs:
                self.logger.debug(l)
        except docker.errors.BuildError as e:
            self.logger.error('Build for application <{}> failed!'.format(
                image_name))
            for line in e.build_log:
                if 'stream' in line:
                    self.logger.error(line['stream'].strip())
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

    def _read_voice_activation_params(self, fpath):
        with open(fpath, 'r') as fstream:
            sentences = [line.rstrip() for line in fstream]
            return sentences

    def _create_dockerfile(self, app_type, app_src_dir, dest_path):
        self.logger.debug(f'Constructing Dockerfile from template for app_type <{app_type}>...')
        _tpl = self._dockerfile_templates[app_type]
        dockerfile = _tpl.render(
            app_src_dir=app_src_dir,
            app_dest_dir=self.APP_DEST_DIR
            )
        self.logger.debug('Dockerfile rendered')
        with open(dest_path, 'w') as fp:
            fp.write(dockerfile)

    def _untar_app(self, tarball_path, dest_path):
        self.logger.debug(
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
        self.logger.info('Searching for Application Dockerfile templates to load...')
        _current_dir = os.path.dirname(os.path.abspath(__file__))
        _templates_dir = os.path.join(_current_dir, 'templates')
        for key in DOCKERFILE_TPL_MAP:
            _tplpath = os.path.join(_templates_dir,DOCKERFILE_TPL_MAP[key])
            if os.path.isfile(_tplpath):
                self.logger.info(f'Loading Application Template for type {key}')
                # self.dockerfile_templates['key'] = Template(_tplpath)
                _tpl = self._jinja_env.get_template(DOCKERFILE_TPL_MAP[key])
                self._dockerfile_templates[key] = _tpl
            else:
                self.logger.error(f'Dockerfile Template for [{key}] not found ({_tplpath})')
