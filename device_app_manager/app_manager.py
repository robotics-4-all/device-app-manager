import sys
import os
import uuid
import time
import signal
import json
import subprocess
import shutil
import shlex
import threading
# from collections import namedtuple
import base64
import atexit
import json

import redis
import docker

from commlib.node import TransportType, Node
from commlib.logger import Logger
from commlib.events import Event

from .docker_builder import AppBuilderDocker
from .docker_executor import AppExecutorDocker
from .redis_controller import RedisController, RedisConnectionParams


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
                 redis_params,
                 core_params,
                 monitoring_params,
                 app_params,
                 control_params,
                 rhasspy_params,
                 ui_manager_params,
                 audio_events_params):
        atexit.register(self._cleanup)

        self._platform_broker_params = platform_broker_params
        self._local_broker_params = local_broker_params
        self._redis_params = redis_params
        self._core_params = core_params
        self._monitoring_params = monitoring_params
        self._app_params = app_params
        self._control_params = control_params
        self._rhasspy_params = rhasspy_params
        self._ui_manager_params = ui_manager_params
        self._audio_events_params = audio_events_params

        self.debug = core_params['debug']

        self._init_platform_node()
        self._init_local_node()

        self.log = Logger('AppManager', debug=True)

        redis_params = RedisConnectionParams(
            host=redis_params['host'],
            port=redis_params['port'],
            db=redis_params['db'],
            password=redis_params['password'],
            redis_app_list_name=redis_params['app_list_name']
        )

        self.docker_client = docker.from_env()

        self._create_app_storage_dir()

        self.redis = RedisController(redis_params,
                                     self._redis_params['app_list_name'])
        if not self.redis.ping():
            raise Exception('Could not connect to redis server.')

        self.app_builder = AppBuilderDocker(
            build_dir=self._core_params['app_build_dir'],
            image_prefix=self._core_params['app_image_prefix']
        )

        self.app_executor = AppExecutorDocker(
            redis_params,
            redis_app_list_name=self._redis_params['app_list_name'],
            on_app_started=self._on_app_started,
            on_app_stopped=self._on_app_stopped
        )
        self._clean_startup()
        self._init_rhassy_endpoints()
        self._init_ui_manager_endpoints()

    def _clean_startup(self):
        self.log.info('Prune stopped containers...')
        _c = self.docker_client.containers.prune()
        self.log.info('Cleaning up possible zombie containers...')
        _apps = self.redis.get_apps()
        for app in _apps:
            app_name = app['name']
            app_state = app['state']
            _cid = self.redis.get_app_container(app_name)
            if app_state == 1:
                try:
                    self.log.info('Found zombie container! Removing...')
                    _c = self.docker_client.containers.get(_cid)
                    _c.stop()
                    _c.remove(force=True)
                    self.log.info('Zombie container removed!')
                except docker.errors.NotFound as exc:
                    self.log.error(exc, exc_info=True)
                except Exception as exc:
                    self.log.error(exc, exc_info=True)
                finally:
                    self.redis.set_app_state(app_name, 0)
                    self.redis.save_db()
            elif _cid not in [None, '']:
                try:
                    _c = self.docker_client.containers.get(_cid)
                    _c.remove(force=True)
                except docker.errors.NotFound as exc:
                    self.log.error(exc, exc_info=True)
                except docker.errors.APIError as exc:
                    self.log.error(exc, exc_info=True)

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

        if self.redis.app_exists(app_name):
            ## Updating app
            self.log.info('Updating App in DB: <{}>'.format(app_name))
            self.redis.update_app(_app.serialize())
        else:
            ## Creating new app instance in db
            self.log.info('Storing new App in DB: <{}>'.format(app_name))
            self.redis.add_app(_app.serialize())

        # Set rhassphy sentences for activating the application.
        ## Look here: https://github.com/robotics-4-all/sythes-voice-events-system
        if _app.voice_commands is not None:
            resp = self._set_rhasspy_sentences(app_name, _app.voice_commands)
            self.log.info(resp)

        self.redis.save_db()
        return app_name

    def delete_app(self, app_name: str, force_stop: bool = False):
        """delete_app.
        Delete an application from the local repository

        Args:
            app_name (str): The name/id of application
            force_stop (bool): Force stop application container
        """
        if not self.redis.app_exists(app_name):
            raise ValueError('App <{}> does not exist locally'.format(app_name))

        if self.redis.app_is_running(app_name) and force_stop:
            self.log.info('Stoping App before deleting')
            self.stop_app(app_name)

        self.log.info('Deleting Application <{}>'.format(app_name))
        docker_app_image = self.redis.get_app_image(app_name)
        self.docker_client.images.remove(image=docker_app_image, force=True)

        # Check if app has ui and remove it
        _app = self.redis.get_app(app_name)
        if _app['ui'] is not None:
            try:
                import shutil
                target_dir = os.path.join(self.APP_UIS_DIR, app_name)
                shutil.rmtree(target_dir)
            except Exception as e:
                raise ValueError("App UI removal has gone wrong:" + str(e))
        self.redis.delete_app(app_name)
        ## Save db in hdd
        self.redis.save_db()

    def start_app(self, app_name, app_args=[], auto_remove=False):
        """start_app.

        Args:
            app_name: The name/id of application
            app_args: Arguments to pass to the application executable
            auto_remove: Autoremove application from local repo upon termination
                of the current execution. Used for testing applications.
        """
        if not self.redis.app_exists(app_name):
            raise ValueError('App <{}> does not exist locally'.format(app_name))

        app = self.redis.get_app(app_name)

        if app['state'] == 1:
            raise ValueError('Application is allready running.')

        _logs_topic = self._app_params['app_logs_topic']
        _logs_topic = self.__add_platform_ns(_logs_topic)
        _logs_topic = _logs_topic.replace('{APP_ID}', app_name)
        logs_publisher = self._local_node.create_publisher(
            topic=_logs_topic)

        self.app_executor.run_app(app_name, app_args, auto_remove=auto_remove,
                                  logs_publisher=logs_publisher)
        return app_name

    def _on_app_started(self, app_id: str):
        self._send_app_started_event(app_id)
        self._start_app_ui_component(app_id)

    def _on_app_stopped(self, app_id: str):
        self._send_app_stopped_event(app_id)
        self._stop_app_ui_component(app_id)
        if self._audio_events_params['enable']:
            _text = f'Η εφαρμογή {app_id} τερμάτισε'
            speak_goal_data = {
                'text': _text,
                'volume': 50,
                'language': 'el'
            }
            try:
                self._speak_action.send_goal(speak_goal_data, timeout=1)
            except Exception as exc:
                self.log.error(exc)

    def stop_app(self, app_name):
        if not self.redis.app_exists(app_name):
            raise ValueError('App <{}> does not exist locally'.format(app_name))
        self.app_executor.stop_app(app_name)
        self.log.info('App {} stopped!'.format(app_name))

    def get_apps(self):
        return self.redis.get_apps()

    def get_running_apps(self):
        apps = self.redis.get_apps()
        _r_apps = []
        for app in apps:
            if app['state'] == 1:
                _r_apps.append(app)
        return _r_apps

    def fast_deploy(self, app_name, app_type, app_tarball_path, app_args=[]):
        self.install_app(app_name, app_type, app_tarball_path)
        self.start_app(app_name, app_args=app_args, auto_remove=True)
        return app_name

    def _init_platform_node(self):
        if self._platform_broker_params['type'] == 'REDIS':
            from commlib.transports.redis import ConnectionParameters
            conn_params = ConnectionParameters(
                host=self._platform_broker_params['host'],
                port=self._platform_broker_params['port'],
                db=self._platform_broker_params['db'])
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
                vhost=self._platform_broker_params['vhost'])
            conn_params.credentials.username = \
                self._platform_broker_params['username']
            conn_params.credentials.password = \
                self._platform_broker_params['password']
            _btype = TransportType.AMQP

        self._platform_node = Node('app_manager',
                                   transport_type=_btype,
                                   transport_connection_params=conn_params,
                                   debug=self.debug)

        _hb_topic = self._monitoring_params['heartbeat_topic']
        _hb_topic = self.__add_platform_ns(_hb_topic)
        self._platform_node.init_heartbeat_thread(_hb_topic)

        self._platform_event_emitter = \
            self._platform_node.create_event_emitter()

        # ---------------------- Alive RPC Service ----------------------
        rpc_name = self._control_params['alive_rpc_name']
        rpc_name = self.__add_platform_ns(rpc_name)
        self._platform_node.create_rpc(
            rpc_name=rpc_name,
            on_request=self._isalive_rpc_callback,
            debug=self.debug).run()
        # --------------------- Get-Apps RPC Service --------------------
        rpc_name = self._control_params['app_list_rpc_name']
        rpc_name = self.__add_platform_ns(rpc_name)
        self._platform_node.create_rpc(
            rpc_name=rpc_name,
            on_request=self._get_apps_rpc_callback,
            debug=self.debug).run()
        # ----------------- Get-Running-Apps RPC Service ----------------
        rpc_name = self._control_params['get_running_apps_rpc_name']
        rpc_name = self.__add_platform_ns(rpc_name)
        self._platform_node.create_rpc(
            rpc_name=rpc_name,
            on_request=self._get_running_apps_rpc_callback,
            debug=self.debug).run()
        # -------------------- Install-App RPC Service ------------------
        rpc_name = self._control_params['app_install_rpc_name']
        rpc_name = self.__add_platform_ns(rpc_name)
        self._platform_node.create_rpc(
            rpc_name=rpc_name,
            on_request=self._install_app_rpc_callback,
            debug=self.debug).run()
        # --------------------- Start-App RPC Service -------------------
        rpc_name = self._control_params['app_start_rpc_name']
        rpc_name = self.__add_platform_ns(rpc_name)
        self._platform_node.create_rpc(
            rpc_name=rpc_name,
            on_request=self._start_app_rpc_callback,
            debug=self.debug).run()
        # --------------------- Stop-App RPC Service --------------------
        rpc_name = self._control_params['app_stop_rpc_name']
        rpc_name = self.__add_platform_ns(rpc_name)
        self._platform_node.create_rpc(
            rpc_name=rpc_name,
            on_request=self._stop_app_rpc_callback,
            debug=self.debug).run()
        # --------------------- Delete-App RPC Service --------------------
        rpc_name = self._control_params['app_delete_rpc_name']
        rpc_name = self.__add_platform_ns(rpc_name)
        self._platform_node.create_rpc(
            rpc_name=rpc_name,
            on_request=self._delete_app_rpc_callback,
            debug=self.debug).run()
        # --------------------- Fast-Deploy-App RPC Service --------------------
        rpc_name = self._control_params['fast_deploy_rpc_name']
        rpc_name = self.__add_platform_ns(rpc_name)
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

        self._local_node = Node('app_manager',
                                transport_type=_btype,
                                transport_connection_params=conn_params,
                                debug=self.debug)
        _hb_topic = self._monitoring_params['heartbeat_topic']
        _hb_topic = self.__add_local_ns(_hb_topic)
        self._local_node.init_heartbeat_thread(_hb_topic)

        self._local_event_emitter = self._local_node.create_event_emitter()

        # ---------------------- Alive RPC Service ----------------------
        rpc_name = self._control_params['alive_rpc_name']
        rpc_name = self.__add_local_ns(rpc_name)
        self._local_node.create_rpc(
            rpc_name=rpc_name,
            on_request=self._isalive_rpc_callback,
            debug=self.debug).run()
        # --------------------- Get-Apps RPC Service --------------------
        rpc_name = self._control_params['app_list_rpc_name']
        rpc_name = self.__add_local_ns(rpc_name)
        self._local_node.create_rpc(
            rpc_name=rpc_name,
            on_request=self._get_apps_rpc_callback,
            debug=self.debug).run()
        # ----------------- Get-Running-Apps RPC Service ----------------
        rpc_name = self._control_params['get_running_apps_rpc_name']
        rpc_name = self.__add_local_ns(rpc_name)
        self._local_node.create_rpc(
            rpc_name=rpc_name,
            on_request=self._get_running_apps_rpc_callback,
            debug=self.debug).run()
        # -------------------- Install-App RPC Service ------------------
        rpc_name = self._control_params['app_install_rpc_name']
        rpc_name = self.__add_local_ns(rpc_name)
        self._local_node.create_rpc(
            rpc_name=rpc_name,
            on_request=self._install_app_rpc_callback,
            debug=self.debug).run()
        # --------------------- Start-App RPC Service -------------------
        rpc_name = self._control_params['app_start_rpc_name']
        rpc_name = self.__add_local_ns(rpc_name)
        self._local_node.create_rpc(
            rpc_name=rpc_name,
            on_request=self._start_app_rpc_callback,
            debug=self.debug).run()
        # --------------------- Stop-App RPC Service --------------------
        rpc_name = self._control_params['app_stop_rpc_name']
        rpc_name = self.__add_local_ns(rpc_name)
        self._local_node.create_rpc(
            rpc_name=rpc_name,
            on_request=self._stop_app_rpc_callback,
            debug=self.debug).run()
        # --------------------- Delete-App RPC Service --------------------
        rpc_name = self._control_params['app_delete_rpc_name']
        rpc_name = self.__add_local_ns(rpc_name)
        self._local_node.create_rpc(
            rpc_name=rpc_name,
            on_request=self._delete_app_rpc_callback,
            debug=self.debug).run()
        # --------------------- Fast-Deploy-App RPC Service --------------------
        rpc_name = self._control_params['fast_deploy_rpc_name']
        rpc_name = self.__add_local_ns(rpc_name)
        self._local_node.create_rpc(
            rpc_name=rpc_name,
            on_request=self._fast_deploy_rpc_callback,
            debug=self.debug).run()

    def _cleanup(self):
        self._send_disconnected_event()
        _rapps = self.redis.get_running_apps()
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

    def _isalive_rpc_callback(self, msg, meta=None):
        self.log.debug('Call <is_alive> RPC')
        return {
            'status': 200
        }

    def _install_app_rpc_callback(self, msg, meta=None):
        try:
            self.log.debug('Call <install-app> RPC')
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
            self.log.error(e, exc_info=True)
            return {
                'status': 404,
                'app_id': '',
                'error': str(e)
            }

    def _delete_app_rpc_callback(self, msg, meta=None):
        try:
            self.log.debug('Call <delete-app> RPC')
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
            self.log.error(e, exc_info=True)
            return {
                'status': 404,
                'error': str(e)
            }

    def _start_app_rpc_callback(self, msg, meta=None):
        resp =  {
            'status': 200,
            'error': ''
        }
        try:
            self.log.debug('Call <start-app> RPC')
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
            self.log.error(e, exc_info=True)
            resp['status'] = 404
            resp['error'] = str(e)
        finally:
            return resp

    def _stop_app_rpc_callback(self, msg, meta=None):
        resp = {
            'status': 200,
            'error': ''
        }
        try:
            self.log.debug('Call <stop-app> RPC')
            if not 'app_id' in msg:
                raise ValueError('Message schema error. app_id is not defined')
            if msg['app_id'] == '':
                raise ValueError('App Id is empty')
            app_name = msg['app_id']
            if not isinstance(app_name, str):
                raise TypeError('Parameter app_name should be of type string')

            if not self.redis.app_exists(app_name):
                raise ValueError(f'App <{app_name}> does not exist locally')

            self.stop_app(app_name)
        except Exception as e:
            self.log.error(e, exc_info=True)
            resp['status'] = 404
            resp['error'] = str(e)
        finally:
            return resp

    def _fast_deploy_rpc_callback(self, msg, meta=None):
        resp = {
            'status': 200,
            'error': '',
            'app_id': ''
        }
        try:
            self.log.debug('Call <fast-deploy> RPC')
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
        _uri = self.__add_local_ns(_uri)
        event = Event('AppManager-Connected', _uri)
        self._local_event_emitter.send_event(event)
        self._platform_event_emitter.send_event(event)

    def _send_disconnected_event(self):
        _uri = f'{self._monitoring_params["disconnected_event"]}'
        _uri = self.__add_local_ns(_uri)
        event = Event('AppManager-Disconnected', _uri)
        self._local_event_emitter.send_event(event)
        self._platform_event_emitter.send_event(event)

    def _send_app_started_event(self, app_id):
        _uri = f'{self._app_params["app_started_event"]}'
        _uri = self.__add_local_ns(_uri)
        _uri = _uri.replace('{APP_ID}', app_id)
        event = Event('Application-Started', _uri)
        self._local_event_emitter.send_event(event)
        self._platform_event_emitter.send_event(event)

    def _send_app_stopped_event(self, app_id):
        _uri = f'{self._app_params["app_stopped_event"]}'
        _uri = self.__add_local_ns(_uri)
        _uri = _uri.replace('{APP_ID}', app_id)
        event = Event('Application-Stopped', _uri)
        self._local_event_emitter.send_event(event)
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
        resp = self._rhasspy_add_sentences.call(msg)
        return resp

    def _start_app_ui_component(self, app_name: str) -> None:
        ui = self.redis.get_app(app_name)['ui']
        if ui is not None:
            self.log.info("Raising UI from the dead!")
            res = self._ui_start.call({"dir": ui + "/"})
            self.log.info(f"Response from Custom UI: {res}")
        else:
            self.log.info("No UI for this app")

    def _stop_app_ui_component(self, app_name: str) -> None:
        ui = self.redis.get_app(app_name)['ui']
        if ui is not None:
            self.log.info("Banishing UI to the dead")
            res = self._ui_stop.call({}, timeout=1)
            self.log.info(f"Response from Custom UI: {res}")

    def _init_ui_manager_endpoints(self):
        rpc_name = self._ui_manager_params['start_rpc'].replace(
            '{DEVICE_ID}', self._core_params['device_id'])
        self._ui_start = self._local_node.create_rpc_client(
            rpc_name=rpc_name,
            debug=self.debug)
        rpc_name = self._ui_manager_params['stop_rpc'].replace(
            '{DEVICE_ID}', self._core_params['device_id'])
        self._ui_stop = self._local_node.create_rpc_client(
            rpc_name=rpc_name,
            debug=self.debug)

    def _init_speak_client(self):
        self._speak_action = self._local_node.create_action_client(
            action_name=self._audio_events_params['speak_action_uri']
        )

    def __add_local_ns(self, uri: str):
        _ns = self._core_params['uri_namespace']
        _local_ns = self._local_broker_params['uri_namespace']
        if _ns != '':
            uri = f'{_ns}.{uri}'
        if _local_ns != '':
            uri = f'{_local_ns}.{uri}'
        uri = uri.replace('{DEVICE_ID}', self._core_params['device_id'])
        return uri

    def __add_platform_ns(self, uri: str):
        _ns = self._core_params['uri_namespace']
        _platform_ns = self._platform_broker_params['uri_namespace']
        if _ns != '':
            uri = f'{_ns}.{uri}'
        if _platform_ns != '':
            uri = f'{_platform_ns}.{uri}'
        uri = uri.replace('{DEVICE_ID}', self._core_params['device_id'])
        return uri

    def run(self):
        self._send_connected_event()
        while True:
            time.sleep(0.1)
