import atexit
# from collections import namedtuple
import base64
import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
import pathlib

import docker
from commlib.events import Event
from commlib.logger import Logger
from commlib.node import Node, TransportType

from .docker_builder import AppBuilderDocker
from .docker_executor import AppExecutorDocker
from .db_controller import RedisConnectionParams, RedisController


class AppManager(object):
    """AppManager class.
    Implementation of the Device Application Manager as described here (TODO)

    Args:
        heartbeat_interval (int): Interval time to send heartbeat messages.
            Not the same as AMQP heartbeats. Device Manager sends
            heartbeat messages at a specific topic.
        debug (bool) Enable/Disable debug mode.
        keep_app_tarballls (bool):
        app_storage_dir (str):
        app_image_prefix (str):
        app_list_rpc_name (str):
        get_running_apps_rpc_name (str):

    """
    def __init__(self,
                 platform_broker_params,
                 local_broker_params,
                 db_params,
                 core_params,
                 monitoring_params,
                 app_params,
                 control_params,
                 rhasspy_params,
                 custom_ui_handler_params,
                 audio_events_params):
        atexit.register(self._cleanup)

        self._platform_broker_params = platform_broker_params
        self._local_broker_params = local_broker_params
        self._db_params = db_params
        self._core_params = core_params
        self._monitoring_params = monitoring_params
        self._app_params = app_params
        self._control_params = control_params
        self._rhasspy_params = rhasspy_params
        self._custom_ui_handler_params = custom_ui_handler_params
        self._audio_events_params = audio_events_params

        self._single_app_mode = core_params['single_app_mode']
        self._app_running = False
        self.debug = core_params['debug']

        self.log = Logger('AppManager', debug=self.debug)

        if db_params['type'] == 'redis':
            conn_params = RedisConnectionParams(
                password=db_params['password'],
            )
            self.db = RedisController(conn_params, db_params['app_list_name'])
        else:
            raise ValueError('Database type not recognized')

        self.docker_client = docker.from_env()

        self._create_app_storage_dir()

        if not self.db.ping():
            raise Exception('Could not connect to database.')

        self.app_builder = AppBuilderDocker(
            build_dir=self._core_params['app_build_dir'],
            image_prefix=self._core_params['app_image_prefix']
        )

        self.app_executor = AppExecutorDocker(
            db_params,
            on_app_started=self._on_app_started,
            on_app_stopped=self._on_app_stopped
        )
        self._clean_startup()

        self._init_local_node()
        self._init_platform_node()

        self._init_rhassy_endpoints()
        self._init_custom_ui_handler_endpoints()
        self._init_speak_client()

        self._start_boot_apps()

    def _clean_startup(self):
        self.log.info('Prune stopped containers...')
        _c = self.docker_client.containers.prune()
        self.log.info('Cleaning up possible zombie containers...')
        _apps = self.db.get_apps()
        for app in _apps:
            app_name = app['name']
            app_state = app['state']
            _cid = self.db.get_app_container(app_name)
            if app_state == 1:
                try:
                    self.log.info(f'Found zombie app! Removing {app_name}...')
                    _c = self.docker_client.containers.get(_cid)
                    _c.stop()
                    _c.remove(force=True)
                except docker.errors.NotFound as exc:
                    self.log.error(exc, exc_info=True)
                except Exception as exc:
                    self.log.error(exc, exc_info=True)
                finally:
                    self.db.set_app_state(app_name, 0)
                    self.db.save_db()
            elif _cid not in [None, '']:
                try:
                    _c = self.docker_client.containers.get(_cid)
                    _c.remove(force=True)
                except docker.errors.NotFound as exc:
                    self.log.error(exc, exc_info=True)
                except docker.errors.APIError as exc:
                    self.log.error(exc, exc_info=True)

    def _start_boot_apps(self):
        self.log.info('Starting Apps with boot flag enabled')
        _apps = self.db.get_apps()
        for app in _apps:
            try:
                if app['scheduler_params']['start_on_boot']:
                    self.start_app(app['name'], force=True)
            except:
                pass

    def install_app(self, app_name: str, app_type: str, app_tarball_path: str):
        """install_app.
        Install an application locally on the device. Builds the docker image
            and stores information on the local repository.

        Args:
            app_name (str): The name/id of application
            app_type (str): The type of the application (r4a_commlib/py3/..)
            app_tarball_path (str): The path to the application tarball
        """
        _app = self.app_builder.build_app(app_name, app_type, app_tarball_path)
        self.log.info(f'Application {app_name}<{app_type}> was build succesfully')

        if self.db.app_exists(app_name):
            ## Updating app
            self.log.info(f'Updating App in DB: <{app_name}>')
            self.db.update_app(_app.serialize())
        else:
            ## Creating new app instance in db
            self.log.info(f'Storing new App in DB: <{app_name}>')
            self.db.add_app(_app.serialize())

        # Set rhassphy sentences for activating the application.
        ## Look here: https://github.com/robotics-4-all/sythes-voice-events-system
        if _app.voice_commands is not None:
            try:
                resp = self._set_rhasspy_sentences(app_name, _app.voice_commands)
            except Exception as e:
                self.log.error(f'Error on calling set_rhasspy_sentences')
                self.log.error(e, exc_info=True)

        self.db.save_db()
        try:
            self._vocal_app_installed(app_name)
        except Exception as e:
            self.log.error(f'Error on calling vocal_app_installed')
            self.log.error(e, exc_info=True)
        return app_name

    def delete_app(self, app_name: str, force_stop: bool = False):
        """delete_app.
        Delete an application from the local repository

        Args:
            app_name (str): The name/id of application
            force_stop (bool): Force stop application container
        """
        if not self.db.app_exists(app_name):
            raise ValueError(f'App <{app_name}> does not exist locally')

        if self.db.app_is_running(app_name) and force_stop:
            self.log.info(f'Stopping App <{app_name}> before deleting...')
            self.stop_app(app_name)

        self.log.info(f'Deleting docker image for app <{app_name}>...')
        try:
            docker_app_image = self.db.get_app_image(app_name)
            self.docker_client.images.remove(image=docker_app_image, force=True)
        except Exception as e:
            self.log.error(e, exc_info=True)

        _app = self.db.get_app(app_name)

        # Check if app has ui and remove it
        try:
            if _app['ui'] is not None:
                target_dir = os.path.join(
                    self._app_params['app_ui_storage_dir'], app_name)
                shutil.rmtree(target_dir)
        except Exception as e:
            self.log.warn(
                f'Error while trying to remove UI component for app {app_name}',
                exc_info=False
            )
            self.log.error(e)
        try:
            if _app['voice_commands'] is not None:
                self.log.info(f'Deleting Rhasspy intent for app <{app_name}>')
                resp = self._delete_rhasspy_intent(app_name)
        except Exception:
            self.log.warn(
                f'Failed to delete voice_commands for app {app_name}',
                exc_info=False
            )
        try:
            self.db.delete_app(app_name)
        except Exception:
            self.log.warn(
                f'Failed to remove app entry ({app_name}) from local DB.',
                exc_info=False
            )
        self.db.save_db()
        try:
            self._vocal_app_deleted(app_name)
        except Exception as e:
            self.log.error(f'Error on calling vocal_app_installed')
            self.log.error(e, exc_info=True)

    def start_app(self, app_name: str, app_args: list = [],
                  auto_remove: bool = False, force: bool = False):
        """start_app.

        Args:
            app_name: The name/id of application
            app_args: Arguments to pass to the application executable
            auto_remove: Autoremove application from local repo upon termination
                of the current execution. Used for testing applications.
        """
        if self._single_app_mode and self._app_running and not force:
            raise ValueError(f'AppManager is running in single app mode, which means that only one application can be active!')

        if not self.db.app_exists(app_name):
            raise ValueError(f'App <{app_name}> does not exist locally')

        app = self.db.get_app(app_name)

        if app['state'] == 1:
            raise ValueError(f'Application {app_name} is allready running.')

        _logs_topic = self._app_params['app_logs_topic']
        _logs_topic = self._add_platform_ns(_logs_topic)
        _logs_topic = _logs_topic.replace('{APP_ID}', app_name)
        logs_publisher = self._local_node.create_publisher(
            topic=_logs_topic)

        self.app_executor.run_app(app_name,
                                  app_args,
                                  auto_remove=auto_remove,
                                  logs_publisher=logs_publisher)
        return app_name

    def _on_app_started(self, app_id: str):
        self._send_app_started_event(app_id)
        self._start_app_ui_component(app_id)
        if self._audio_events_params['app_started_event']:
            self._play_sound_effect('app_started')
        self._app_running = True

    def _on_app_stopped(self, app_id: str):
        self._send_app_stopped_event(app_id)
        self._stop_app_ui_component(app_id)
        if self._audio_events_params['app_termination_event']:
            self._play_sound_effect('app_termination')
        self._app_running = False

    def stop_app(self, app_name):
        if not self.db.app_exists(app_name):
            raise ValueError(f'App <{app_name}> does not exist locally')
        self.app_executor.stop_app(app_name)
        self.log.info(f'App <{app_name}> stopped!')

    def get_apps(self):
        return self.db.get_apps()

    def get_running_apps(self):
        apps = self.db.get_apps()
        _r_apps = []
        for app in apps:
            if app['state'] == 1:
                _r_apps.append(app)
        return _r_apps

    def fast_deploy(self,
                    app_name: str,
                    app_type: str,
                    app_tarball_path: str,
                    app_args: list = []):
        """
        Executes a sequence of INSTALL-START-DELETE operations for an app
        """
        self.install_app(app_name, app_type, app_tarball_path)
        time.sleep(1)
        self.start_app(app_name, app_args=app_args, auto_remove=True)
        return app_name

    def _init_platform_node(self):
        if self._platform_broker_params['type'] == 'REDIS':
            from commlib.transports.redis import ConnectionParameters
            conn_params = ConnectionParameters(
                host=self._platform_broker_params['host'],
                port=self._platform_broker_params['port'],
                db=self._platform_broker_params['db']
            )
            conn_params.credentials.username = \
                self._platform_broker_params['username']
            conn_params.credentials.password = \
                self._platform_broker_params['password']
            _btype = TransportType.REDIS
        elif self._platform_broker_params['type'] == 'AMQP':
            from commlib.transports.amqp import ConnectionParameters
            conn_params = ConnectionParameters(
                host=self._platform_broker_params['host'],
                port=self._platform_broker_params['port'],
                vhost=self._platform_broker_params['vhost']
            )
            conn_params.credentials.username = \
                self._platform_broker_params['username']
            conn_params.credentials.password = \
                self._platform_broker_params['password']
            _btype = TransportType.AMQP
        elif self._platform_broker_params['type'] == 'MQTT':
            from commlib.transports.mqtt import ConnectionParameters
            conn_params = ConnectionParameters(
                host=self._platform_broker_params['host'],
                port=self._platform_broker_params['port']
            )
            conn_params.credentials.username = \
                self._platform_broker_params['username']
            conn_params.credentials.password = \
                self._platform_broker_params['password']
            _btype = TransportType.MQTT

        self._platform_node = Node(self.__class__.__name__,
                                   transport_type=_btype,
                                   transport_connection_params=conn_params,
                                   debug=self.debug)

        _hb_topic = self._monitoring_params['heartbeat_topic']
        _hb_topic = self._add_platform_ns(_hb_topic)
        self._platform_node.init_heartbeat_thread(_hb_topic)

        self._platform_event_emitter = \
            self._platform_node.create_event_emitter()

        # ---------------------- Alive RPC Service ----------------------
        rpc_name = self._control_params['alive_rpc_name']
        rpc_name = self._add_platform_ns(rpc_name)
        self._platform_node.create_rpc(
            rpc_name=rpc_name,
            on_request=self._isalive_rpc_callback,
            debug=self.debug).run()
        # --------------------- Get-Apps RPC Service --------------------
        rpc_name = self._control_params['app_list_rpc_name']
        rpc_name = self._add_platform_ns(rpc_name)
        self._platform_node.create_rpc(
            rpc_name=rpc_name,
            on_request=self._get_apps_rpc_callback,
            debug=self.debug).run()
        # ----------------- Get-Running-Apps RPC Service ----------------
        rpc_name = self._control_params['get_running_apps_rpc_name']
        rpc_name = self._add_platform_ns(rpc_name)
        self._platform_node.create_rpc(
            rpc_name=rpc_name,
            on_request=self._get_running_apps_rpc_callback,
            debug=self.debug).run()
        # -------------------- Install-App RPC Service ------------------
        rpc_name = self._control_params['app_install_rpc_name']
        rpc_name = self._add_platform_ns(rpc_name)
        self._platform_node.create_rpc(
            rpc_name=rpc_name,
            on_request=self._install_app_rpc_callback,
            debug=self.debug).run()
        # --------------------- Start-App RPC Service -------------------
        rpc_name = self._control_params['app_start_rpc_name']
        rpc_name = self._add_platform_ns(rpc_name)
        self._platform_node.create_rpc(
            rpc_name=rpc_name,
            on_request=self._start_app_rpc_callback,
            debug=self.debug).run()
        # --------------------- Stop-App RPC Service --------------------
        rpc_name = self._control_params['app_stop_rpc_name']
        rpc_name = self._add_platform_ns(rpc_name)
        self._platform_node.create_rpc(
            rpc_name=rpc_name,
            on_request=self._stop_app_rpc_callback,
            debug=self.debug).run()
        # --------------------- Delete-App RPC Service --------------------
        rpc_name = self._control_params['app_delete_rpc_name']
        rpc_name = self._add_platform_ns(rpc_name)
        self._platform_node.create_rpc(
            rpc_name=rpc_name,
            on_request=self._delete_app_rpc_callback,
            debug=self.debug).run()
        # --------------------- Fast-Deploy-App RPC Service --------------------
        rpc_name = self._control_params['fast_deploy_rpc_name']
        rpc_name = self._add_platform_ns(rpc_name)
        self._platform_node.create_rpc(
            rpc_name=rpc_name,
            on_request=self._fast_deploy_rpc_callback,
            debug=self.debug).run()

    def _init_local_node(self):
        if self._local_broker_params['type'] == 'REDIS':
            from commlib.transports.redis import ConnectionParameters
            conn_params = ConnectionParameters(
                host=self._local_broker_params['host'],
                port=self._local_broker_params['port'],
                db=self._local_broker_params['db'])
            conn_params.credentials.username = \
                self._local_broker_params['username']
            conn_params.credentials.password = \
                self._local_broker_params['password']
            _btype = TransportType.REDIS
        elif self._local_broker_params['type'] == 'AMQP':
            from commlib.transports.amqp import ConnectionParameters
            conn_params = ConnectionParameters(
                host=self._local_broker_params['host'],
                port=self._local_broker_params['port'],
                vhost=self._local_broker_params['vhost'])
            conn_params.credentials.username = \
                self._local_broker_params['username']
            conn_params.credentials.password = \
                self._local_broker_params['password']
            _btype = TransportType.AMQP
        elif self._local_broker_params['type'] == 'MQTT':
            from commlib.transports.mqtt import ConnectionParameters
            conn_params = ConnectionParameters(
                host=self._local_broker_params['host'],
                port=self._local_broker_params['port']
            )
            conn_params.credentials.username = \
                self._local_broker_params['username']
            conn_params.credentials.password = \
                self._local_broker_params['password']
            _btype = TransportType.MQTT

        self._local_node = Node('AppManager',
                                transport_type=_btype,
                                transport_connection_params=conn_params,
                                debug=self.debug)
        _hb_topic = self._monitoring_params['heartbeat_topic']
        _hb_topic = self._add_local_ns(_hb_topic)
        self._local_node.init_heartbeat_thread(_hb_topic)

        self._local_event_emitter = self._local_node.create_event_emitter()

        # ---------------------- Alive RPC Service ----------------------
        rpc_name = self._control_params['alive_rpc_name']
        rpc_name = self._add_local_ns(rpc_name)
        self._local_node.create_rpc(
            rpc_name=rpc_name,
            on_request=self._isalive_rpc_callback,
            debug=self.debug).run()
        # --------------------- Get-Apps RPC Service --------------------
        rpc_name = self._control_params['app_list_rpc_name']
        rpc_name = self._add_local_ns(rpc_name)
        self._local_node.create_rpc(
            rpc_name=rpc_name,
            on_request=self._get_apps_rpc_callback,
            debug=self.debug).run()
        # ----------------- Get-Running-Apps RPC Service ----------------
        rpc_name = self._control_params['get_running_apps_rpc_name']
        rpc_name = self._add_local_ns(rpc_name)
        self._local_node.create_rpc(
            rpc_name=rpc_name,
            on_request=self._get_running_apps_rpc_callback,
            debug=self.debug).run()
        # -------------------- Install-App RPC Service ------------------
        rpc_name = self._control_params['app_install_rpc_name']
        rpc_name = self._add_local_ns(rpc_name)
        self._local_node.create_rpc(
            rpc_name=rpc_name,
            on_request=self._install_app_rpc_callback,
            debug=self.debug).run()
        # --------------------- Start-App RPC Service -------------------
        rpc_name = self._control_params['app_start_rpc_name']
        rpc_name = self._add_local_ns(rpc_name)
        self._local_node.create_rpc(
            rpc_name=rpc_name,
            on_request=self._start_app_rpc_callback,
            debug=self.debug).run()
        # --------------------- Stop-App RPC Service --------------------
        rpc_name = self._control_params['app_stop_rpc_name']
        rpc_name = self._add_local_ns(rpc_name)
        self._local_node.create_rpc(
            rpc_name=rpc_name,
            on_request=self._stop_app_rpc_callback,
            debug=self.debug).run()
        # --------------------- Delete-App RPC Service --------------------
        rpc_name = self._control_params['app_delete_rpc_name']
        rpc_name = self._add_local_ns(rpc_name)
        self._local_node.create_rpc(
            rpc_name=rpc_name,
            on_request=self._delete_app_rpc_callback,
            debug=self.debug).run()
        # --------------------- Fast-Deploy-App RPC Service --------------------
        rpc_name = self._control_params['fast_deploy_rpc_name']
        rpc_name = self._add_local_ns(rpc_name)
        self._local_node.create_rpc(
            rpc_name=rpc_name,
            on_request=self._fast_deploy_rpc_callback,
            debug=self.debug).run()

    def _cleanup(self):
        self._send_disconnected_event()
        _rapps = self.db.get_running_apps()
        for _app in _rapps:
            self.stop_app(_app['name'])

    def _create_app_storage_dir(self):
        if not os.path.exists(self._core_params['app_storage_dir']):
            os.mkdir(self._core_params['app_storage_dir'])

    def _init_rhassy_endpoints(self):
        rpc_name = self._rhasspy_params['add_sentences_rpc'].replace(
            '{DEVICE_ID}', self._core_params['device_id'])
        self._rhasspy_add_sentences = self._local_node.create_rpc_client(
            rpc_name=rpc_name,
            debug=self.debug)
        rpc_name = self._rhasspy_params['delete_intent_rpc'].replace(
            '{DEVICE_ID}', self._core_params['device_id'])
        self._rhasspy_delete_intent = self._local_node.create_rpc_client(
            rpc_name=rpc_name,
            debug=self.debug)

    def _delete_rhasspy_intent(self, app_id):
        req = {
            'intent': app_id
        }
        resp = self._rhasspy_delete_intent.call(req)
        return resp

    def _isalive_rpc_callback(self, msg, meta=None):
        self.log.debug('RPC Request: is_alive')
        return {
            'status': 200
        }

    def _install_app_rpc_callback(self, msg, meta=None):
        """
        Install application RPC callback

        """
        try:
            self.log.debug('RPC Request: install_app')
            if 'app_id' not in msg:
                raise ValueError('Message does not include app_id property')
            if msg['app_id'] == '':
                raise ValueError('App Id is empty')
            if 'app_type' not in msg:
                raise ValueError('Message does not include app_type property')
            if 'app_tarball' not in msg:
                raise ValueError('Message does not include app_tarball property')
            app_name = msg['app_id']
            app_type = msg['app_type']
            app_file = msg['app_tarball']
            # Optional. Empty app_name means unnamed app
            tarball_b64 = app_file['data']

            tarball_path = self._store_app_tar(
                tarball_b64, self._core_params['app_storage_dir'])

            app_id = self.install_app(app_name, app_type, tarball_path)

            return {
                'status': 200,
                'app_id': app_id,
                'error': ''
            }
        except Exception as e:
            self.log.error(f'Error while installing application {app_name}',
                           exc_info=True)
            self.log.error(e)
            return {
                'status': 404,
                'app_id': '',
                'error': str(e)
            }

    def _delete_app_rpc_callback(self, msg, meta=None):
        """
        Delete application RPC callback

        """
        try:
            self.log.debug('RPC Request: delete_app')
            if 'app_id' not in msg:
                raise ValueError('Message schema error. app_id is not defined')
            if msg['app_id'] == '':
                raise ValueError('App Id is empty')
            app_name = msg['app_id']

            fstop = True
            if 'force_stop' in msg:
                fstop = msg['force_stop']

            self.delete_app(app_name, fstop)

            return {
                'status': 200,
                'error': ''
            }
        except Exception as e:
            self.log.error(f'Error while deleting app {app_name}',
                           exc_info=True)
            self.log.error(e)
            return {
                'status': 404,
                'error': str(e)
            }

    def _start_app_rpc_callback(self, msg, meta=None):
        """
        Start application RPC callback

        """
        resp =  {
            'status': 200,
            'error': ''
        }
        try:
            self.log.debug('RPC Request: start_app')
            if 'app_id' not in msg:
                raise ValueError('Message does not include app_id property')
            if msg['app_id'] == '':
                raise ValueError('App Id is empty')
            app_name = msg['app_id']
            if not isinstance(app_name, str):
                raise TypeError('Parameter app_name should be of type string')
            app_args = []
            if 'app_args' in msg:
                app_args = msg['app_args']

            app_id = self.start_app(app_name, app_args)
        except Exception as e:
            self.log.error(f'Error while deploying application {app_name}' +
                           ' container', exc_info=False)
            self.log.error(e)
            resp['status'] = 404
            resp['error'] = str(e)
        finally:
            return resp

    def _stop_app_rpc_callback(self, msg, meta=None):
        """
        Stop application RPC callback

        """
        resp = {
            'status': 200,
            'error': ''
        }
        try:
            self.log.debug('RPC Request: stop_app')
            if not 'app_id' in msg:
                raise ValueError('Message schema error. app_id is not defined')
            if msg['app_id'] == '':
                raise ValueError('App Id is empty')
            app_name = msg['app_id']
            if not isinstance(app_name, str):
                raise TypeError('Parameter app_name should be of type string')

            if not self.db.app_exists(app_name):
                raise ValueError(f'App <{app_name}> does not exist locally')

            self.stop_app(app_name)
        except Exception as e:
            self.log.error(f'Error while trying to stop app {app_name}',
                           exc_info=True)
            self.log.error(e)
            resp['status'] = 404
            resp['error'] = str(e)
        finally:
            return resp

    def _fast_deploy_rpc_callback(self, msg, meta=None):
        """
        Fast-Deploy application RPC callback

        """
        resp = {
            'status': 200,
            'error': '',
            'app_id': ''
        }
        try:
            self.log.debug('RPC Request: fast_deploy')
            if not 'app_id' in msg:
                raise ValueError('Message schema error. app_id is not defined')
            if msg['app_id'] == '':
                raise ValueError('App Id is empty')
            app_name = msg['app_id']
            if not isinstance(app_name, str):
                raise TypeError('Parameter app_name should be of type string')
            if not 'app_type' in msg:
                raise ValueError(
                    'Message schema error. app_type is not defined')
            if msg['app_type'] == '':
                raise ValueError('App Type is empty')
            app_type = msg['app_type']
            if not isinstance(app_type, str):
                raise TypeError('Parameter app_type should be of type string')
            if not 'app_tarball' in msg:
                raise ValueError(
                    'Message schema error. app_tarball is not defined')
            if msg['app_tarball'] == '':
                raise ValueError('App Tarball is empty')
            if 'app_args' in msg:
                app_args = msg['app_args']
            else:
                app_args = []
            app_tar = msg['app_tarball']
            tarball_b64 =  app_tar['data']
            tarball_path = self._store_app_tar(
                tarball_b64, self._core_params['app_storage_dir'])
            app_id = self.fast_deploy(app_name, app_type,
                                      tarball_path, app_args)
            resp['app_id'] = app_id

        except Exception as e:
            self.log.error(e, exc_info=True)
            resp['status'] = 404
            resp['error'] = str(e)
        finally:
            return resp

    def _get_apps_rpc_callback(self, msg, meta=None):
        """
        Get installed application RPC callback

        """
        resp = {
            'status': 200,
            'apps': [],
            'error': ''
        }
        try:
            self.log.debug('Call <get-apps> RPC')
            apps = self.get_apps()
            resp['apps'] = apps
            return resp
        except Exception as e:
            self.log.error(e, exc_info=True)
            resp['error'] = str(e)
            return resp

    def _get_running_apps_rpc_callback(self, msg, meta=None):
        """
        Get currently running application RPC callback

        """
        resp = {
            'status': 200,
            'apps': [],
            'error': ''
        }
        try:
            self.log.debug('Call <get-running-apps> RPC')
            apps = self.get_running_apps()
            resp['apps'] = apps
            return resp
        except Exception as e:
            self.log.error(e, exc_info=True)
            resp['error'] = str(e)
            return resp

    def _send_connected_event(self):
        _uri = f'{self._monitoring_params["connected_event"]}'
        _luri = self._add_local_ns(_uri)
        event = Event('AppManager-Connected', _luri)
        self._local_event_emitter.send_event(event)
        _puri = self._add_platform_ns(_uri)
        event = Event('AppManager-Connected', _puri)
        self._platform_event_emitter.send_event(event)

    def _send_disconnected_event(self):
        _uri = f'{self._monitoring_params["disconnected_event"]}'
        _luri = self._add_local_ns(_uri)
        _puri = self._add_platform_ns(_uri)
        event = Event('AppManager-Disconnected', _luri)
        self._local_event_emitter.send_event(event)
        event = Event('AppManager-Disconnected', _puri)
        self._platform_event_emitter.send_event(event)

    def _send_app_started_event(self, app_id):
        _uri = f'{self._app_params["app_started_event"]}'
        _luri = self._add_local_ns(_uri).replace('{APP_ID}', app_id)
        _puri = self._add_platform_ns(_uri).replace('{APP_ID}', app_id)
        event = Event('Application-Started', _luri)
        self._local_event_emitter.send_event(event)
        event = Event('Application-Started', _puri)
        self._platform_event_emitter.send_event(event)

    def _send_app_stopped_event(self, app_id):
        _uri = f'{self._app_params["app_stopped_event"]}'
        _luri = self._add_local_ns(_uri).replace('{APP_ID}', app_id)
        _puri = self._add_platform_ns(_uri).replace('{APP_ID}', app_id)
        event = Event('Application-Stopped', _luri)
        self._local_event_emitter.send_event(event)
        event = Event('Application-Stopped', _puri)
        self._platform_event_emitter.send_event(event)

    def _store_app_tar(self, tar_b64, dest_dir):
        tarball_decoded = base64.b64decode(tar_b64)
        u_id = uuid.uuid4().hex[0:8]
        tarball_path = os.path.join(
            self._core_params['app_storage_dir'],
            'app-{}.tar.gz'.format(u_id)
        )
        with open(tarball_path, 'wb') as f:
            f.write(tarball_decoded)
            return tarball_path

    def _set_rhasspy_sentences(self, intent, sentences):
        msg = {
            'intent': intent,
            'sentences': sentences
        }
        self.log.info('Calling Rhasspy Add-Sentences RPC...')
        resp = self._rhasspy_add_sentences.call(msg, timeout=10)
        return resp

    def _start_app_ui_component(self, app_name: str) -> None:
        ui = self.db.get_app(app_name)['ui']
        if ui is not None:
            self.log.info("Raising UI from the dead!")
            res = self._ui_start.call({"dir": ui + "/"})
            self.log.info(f"Response from Custom UI: {res}")
        else:
            self.log.info("No UI for this app")

    def _stop_app_ui_component(self, app_name: str) -> None:
        ui = self.db.get_app(app_name)['ui']
        if ui is not None:
            self.log.info("Banishing UI to the dead")
            res = self._ui_stop.call({}, timeout=1)
            self.log.info(f"Response from Custom UI: {res}")

    def _init_custom_ui_handler_endpoints(self):
        rpc_name = self._custom_ui_handler_params['start_rpc'].replace(
            '{DEVICE_ID}', self._core_params['device_id'])
        self._ui_start = self._local_node.create_rpc_client(
            rpc_name=rpc_name,
            debug=self.debug)
        rpc_name = self._custom_ui_handler_params['stop_rpc'].replace(
            '{DEVICE_ID}', self._core_params['device_id'])
        self._ui_stop = self._local_node.create_rpc_client(
            rpc_name=rpc_name,
            debug=self.debug)

    def _init_speak_client(self):
        self._speak_action = self._local_node.create_action_client(
            action_name=self._audio_events_params['speak_action_uri']
        )

    def _add_local_ns(self, uri: str):
        _ns = self._core_params['uri_namespace']
        _local_ns = self._local_broker_params['uri_namespace']
        if _ns != '':
            uri = f'{_ns}.{uri}'
        if _local_ns != '':
            uri = f'{_local_ns}.{uri}'
        uri = uri.replace('{DEVICE_ID}', self._core_params['device_id'])
        return uri

    def _add_platform_ns(self, uri: str):
        _ns = self._core_params['uri_namespace']
        _platform_ns = self._platform_broker_params['uri_namespace']
        if _ns != '':
            uri = f'{_ns}.{uri}'
        if _platform_ns != '':
            uri = f'{_platform_ns}.{uri}'
        uri = uri.replace('{DEVICE_ID}', self._core_params['device_id'])
        return uri

    def _speak(self, text: str, volume: int = 75, lang: str = 'el'):
        if self._audio_events_params['speak_action_uri'] in ('', None):
            self.log.warn(
                'Cannot send speak command - speak_action_uri is not defined'
            )
            return
        speak_goal_data = {
            'text': text,
            'volume': volume,
            'language': lang
        }
        self._speak_action.send_goal(speak_goal_data, timeout=1)

    def _vocal_app_installed(self, app_name: str):
        if not self._audio_events_params['app_installed_event']:
            self.log.warn('App Installed Event is disabled!')
            return
        text = f'Η εγκατάσταση της εφαρμογής {app_name} ολοκληρώθηκε με επιτυχία'
        self._speak(text=text)

    def _vocal_app_deleted(self, app_name: str):
        if not self._audio_events_params['app_deleted_event']:
            self.log.warn('App Installed Event is disabled!')
            return
        text = f'Η απεγκατάσταση της εφαρμογής {app_name} ολοκληρώθηκε με επιτυχία'
        self._speak(text=text)

    def _play_sound_effect(self, sound_effect_id: str):
        _file = f'{sound_effect_id}.wav'
        _se_dir = self._audio_events_params['sound_effects_dir']
        _fpath = pathlib.Path(_se_dir).expanduser().joinpath(_file)
        self.log.warn(f'Playing sound effect: {_fpath}')
        proc = subprocess.Popen(['aplay', _fpath])

    def run(self):
        self._send_connected_event()
        while True:
            time.sleep(0.1)
