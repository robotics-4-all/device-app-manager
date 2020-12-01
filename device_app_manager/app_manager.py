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
from commlib.logger import RemoteLogger

from .docker_builder import AppBuilderDocker
from .docker_executor import AppExecutorDocker
from .redis_controller import RedisController, RedisConnectionParams


class HeartbeatThread(threading.Thread):
    def __init__(self, topic, conn_params, interval=10,  *args, **kwargs):
        super(HeartbeatThread, self).__init__(*args, **kwargs)
        self._stop_event = threading.Event()
        self._rate_secs = interval
        self._heartbeat_pub = Publisher(
            topic=topic,
            conn_params=conn_params,
            debug=False
        )
        self.daemon = True

    def run(self):
        try:
            while not self._stop_event.isSet():
                self._heartbeat_pub.publish({})
                self._stop_event.wait(self._rate_secs)
        except Exception as exc:
            # print('Heartbeat Thread Ended')
            pass
        finally:
            # print('Heartbeat Thread Ended')
            pass

    def force_join(self, timeout=None):
        """ Stop the thread. """
        self._stop_event.set()
        threading.Thread.join(self, timeout)

    def stop(self):
        self._stop_event.set()

    def stopped(self):
        return self._stop_event.is_set()


class AppManager(object):
    """AppManager class.
    Implementation of the Device Application Manager as described here (TODO)

    Args:
        heartbeat_interval (int): Interval time to send heartbeat messages.
            Not the same as AMQP heartbeats. Device Manager sends
            heartbeat messages at a specific topic.
        debug (bool) Enable/Disable debug mode.
        stop_apps_on_exit (bool): Currently not supported feature!
        keep_app_tarballls (bool):
        app_storage_dir (str):
        app_image_prefix (str):
        app_list_rpc_name (str):
        get_running_apps_rpc_name (str):

    """
    APP_STORAGE_DIR = '~/.apps'
    APP_INSTALL_RPC_NAME = 'thing.x.appmanager.install_app'
    APP_DELETE_RPC_NAME = 'thing.x.appmanager.delete_app'
    APP_START_RPC_NAME = 'thing.x.appmanager.start_app'
    APP_STOP_RPC_NAME = 'thing.x.appmanager.stop_app'
    APP_LIST_RPC_NAME = 'thing.x.appmanager.apps'
    APP_FAST_DEPLOY_RPC_NAME = 'thing.x.appmanager.fast_deploy'
    ISALIVE_RPC_NAME = 'thing.x.appmanager.is_alive'
    GET_RUNNING_APPS_RPC_NAME = 'thing.x.appmanager.apps.running'
    RHASSPY_ADD_SENTENCES_RPC = 'rhasspy_ctrl.add_sentences'
    HEARTBEAT_TOPIC = 'thing.x.appmanager.heartbeat'
    THING_CONNECTED_EVENT = 'thing.x.appmanager.connected'
    THING_DISCONNECTED_EVENT = 'thing.x.appmanager.disconnected'
    HEARTBEAT_INTERVAL = 10  # seconds
    APP_UIS_DIR = "/home/pi/.config/device_app_manager/"

    def __init__(self,
                 platform_broker_params,
                 local_broker_params,
                 redis_params,
                 core_params,
                 monitoring_params,
                 app_params,
                 control_params):
        atexit.register(self._cleanup)

        self._platform_broker_params = platform_broker_params
        self._local_broker_params = local_broker_params
        self._redis_params = redis_params
        self._core_params = core_params
        self._monitoring_params = monitoring_params
        self._app_params = app_params
        self._control_params = control_params

        self.apps = {}
        self._deploy_rpc = None
        self._delete_rpc = None
        self._start_rpc = None
        self._install_rpc = None
        self._stop_rpc = None


        self._init_platform_node()
        self._init_local_node()

        self.__init_logger()

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
            self.broker_conn_params,
            redis_params,
            redis_app_list_name=self._redis_params['app_list_name'],
            app_started_event=self._app_params['app_started_event'],
            app_stopped_event=self._app_params['app_stopped_event'],
            app_logs_topic=self._app_params['app_logs_topic'],
            app_stats_topic=self._app_params['app_stats_topic'],
            publish_logs=self._app_params['publish_app_logs'],
            publish_stats=self._app_params['publish_app_stats']
        )
        self._clean_startup()
        self._init_rhassy_sentences_client()

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

        self.app_executor.run_app(app_name, app_args, auto_remove=auto_remove)
        return app_name

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

        _hb_topic = self.HEARTBEAT_TOPIC.replace(
            '{DEVICE_ID}', self._local_broker_params['username']),
        self._local_node.init_heartbeat_thread(_hb_topic)

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
        _hb_topic = self.HEARTBEAT_TOPIC.replace(
            '{DEVICE_ID}', self._local_broker_params['username']),
        self._local_node.init_heartbeat_thread('app_manager.heartbeat')

    def __init_logger(self):
        """Initialize Logger."""
        log_uri = \
            f'thing.{self.broker_conn_params.credentials.username}.appmanager.logs'
        self.log = RemoteLogger(self.__class__.__name__, TransportType.AMQP,
                                self.broker_conn_params, remote_topic=log_uri)

    def _cleanup(self):
        self._send_disconnected_event()
        _rapps = self.redis.get_running_apps()
        for _app in _rapps:
            self.stop_app(_app['name'])

    def _create_app_storage_dir(self):
        if not os.path.exists(self.APP_STORAGE_DIR):
            os.mkdir(self.APP_STORAGE_DIR)

    def _init_heartbeat_pub(self):
        self._heartbeat_thread = HeartbeatThread(
            self.HEARTBEAT_TOPIC.replace(
                'x', self._platform_broker_params['username']),
            self.broker_conn_params,
            interval=self.HEARTBEAT_INTERVAL
        )
        self._heartbeat_thread.start()

    def _init_rpc_endpoints(self):
        self._deploy_rpc = None
        self._stop_app_rpc = None
        self._isalive_rpc = None
        self._init_isalive_rpc()
        self._init_app_install_rpc()
        self._init_app_start_rpc()
        self._init_app_stop_rpc()
        self._init_app_list_rpc()
        self._init_app_delete_rpc()
        self._init_get_running_apps_rpc()
        self._init_app_fast_deploy_rpc()

    def _init_isalive_rpc(self):
        rpc_name = self.ISALIVE_RPC_NAME.replace(
            'x', self._platform_broker_params['username'])
        self._isalive_rpc = RPCService(
            rpc_name=rpc_name,
            on_request=self._isalive_rpc_callback,
            conn_params=self.broker_conn_params,
            debug=self.debug)
        self._isalive_rpc.run()

    def _init_app_list_rpc(self):
        rpc_name = self.APP_LIST_RPC_NAME.replace(
            'x', self._platform_broker_params['username'])
        self._app_list_rpc = RPCService(
            rpc_name=rpc_name,
            on_request=self._get_apps_rpc_callback,
            conn_params=self.broker_conn_params,
            debug=self.debug)
        self._app_list_rpc.run()

    def _init_get_running_apps_rpc(self):
        rpc_name = self.GET_RUNNING_APPS_RPC_NAME.replace(
            'x', self._platform_broker_params['username'])
        self._running_apps_rpc = RPCService(
            rpc_name=rpc_name,
            on_request=self._get_running_apps_rpc_callback,
            conn_params=self.broker_conn_params,
            debug=self.debug)
        self._running_apps_rpc.run()

    def _init_app_install_rpc(self):
        rpc_name = self.APP_INSTALL_RPC_NAME.replace(
                'x', self._platform_broker_params['username'])
        self._install_rpc = RPCService(
            rpc_name=rpc_name,
            on_request=self._install_app_rpc_callback,
            conn_params=self.broker_conn_params,
            debug=self.debug)
        self._install_rpc.run()

    def _init_app_start_rpc(self):
        rpc_name = self.APP_START_RPC_NAME.replace(
                'x', self._platform_broker_params['username'])
        self._start_rpc = RPCService(
            rpc_name=rpc_name,
            on_request=self._start_app_rpc_callback,
            conn_params=self.broker_conn_params,
            debug=self.debug)
        self._start_rpc.run()

    def _init_app_stop_rpc(self):
        rpc_name = self.APP_STOP_RPC_NAME.replace(
            'x', self._platform_broker_params['username'])
        self._stop_rpc = RPCService(
            rpc_name=rpc_name,
            on_request=self._stop_app_rpc_callback,
            conn_params=self.broker_conn_params,
            debug=self.debug)
        self._stop_rpc.run()

    def _init_app_delete_rpc(self):
        rpc_name = self.APP_DELETE_RPC_NAME.replace(
            'x', self._platform_broker_params['username'])
        self._delete_rpc = RPCService(
            rpc_name=rpc_name,
            on_request=self._delete_app_rpc_callback,
            conn_params=self.broker_conn_params,
            debug=self.debug)
        self._delete_rpc.run()

    def _init_app_fast_deploy_rpc(self):
        rpc_name = self.APP_FAST_DEPLOY_RPC_NAME.replace(
            'x', self._platform_broker_params['username'])
        self._fast_deploy_rpc = RPCService(
            rpc_name=rpc_name,
            on_request=self._fast_deploy_rpc_callback,
            conn_params=self.broker_conn_params,
            debug=self.debug)
        self._fast_deploy_rpc.run()

    def _init_rhassy_sentences_client(self):
        rpc_name = self.RHASSPY_ADD_SENTENCES_RPC.replace(
            'x', self._platform_broker_params['username'])
        if self._local_broker_params['type'] == 'REDIS':
            from commlib.transports.redis import (
                ConnectionParameters, RPCClient
            )
        elif self._local_broker_params['type'] == 'AMQP':
            from commlib.transports.amqp import (
                ConnectionParameters, RPCClient
            )
        elif self._local_broker_params['type'] == 'MQTT':
            from commlib.transports.mqtt import (
                ConnectionParameters, RPCClient
            )

        broker_params = ConnectionParameters(
            host=self._local_broker_params['host'],
            port=self._local_broker_params['port'])
        self._rhasspy_add_sentences = RPCClient(
            rpc_name=rpc_name,
            conn_params=broker_params,
            debug=self.debug)

    def _isalive_rpc_callback(self, msg, meta):
        self.log.debug('Call <is_alive> RPC')
        return {
            'status': 200
        }

    def _install_app_rpc_callback(self, msg, meta):
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
                tarball_b64, self.APP_STORAGE_DIR)

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

    def _delete_app_rpc_callback(self, msg, meta):
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

    def _start_app_rpc_callback(self, msg, meta):
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

    def _stop_app_rpc_callback(self, msg, meta):
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

    def _fast_deploy_rpc_callback(self, msg, meta):
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
                tarball_b64, self.APP_STORAGE_DIR)
            app_id = self.fast_deploy(app_name, app_type,
                                      tarball_path, app_args)
            resp['app_id'] = app_id

        except Exception as e:
            self.log.error(e, exc_info=True)
            resp['status'] = 404
            resp['error'] = str(e)
        finally:
            return resp

    def _get_apps_rpc_callback(self, msg, meta):
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

    def _get_running_apps_rpc_callback(self, msg, meta):
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
        p = Publisher(
            topic=self.THING_CONNECTED_EVENT.replace(
                'x', self._platform_broker_params['username']),
            conn_params=self.broker_conn_params,
            debug=False
        )
        p.publish({})
        del p

    def _send_disconnected_event(self):
        p = Publisher(
            topic=self.THING_DISCONNECTED_EVENT.replace(
                'x', self._platform_broker_params['username']),
            conn_params=self.broker_conn_params,
            debug=False
        )
        p.publish({})
        del p

    def _store_app_tar(self, tar_b64, dest_dir):
        tarball_decoded = base64.b64decode(tar_b64)
        u_id = uuid.uuid4().hex[0:8]
        tarball_path = os.path.join(
            self.APP_STORAGE_DIR,
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

    def run(self):
        try:
            self._init_rpc_endpoints()
            self._init_heartbeat_pub()
            self._send_connected_event()
            while True:
                time.sleep(0.1)
        except KeyboardInterrupt as exc:
            self.log.error(exc, exc_info=True)
            self._cleanup()
        except Exception as exc:
            self.log.error(exc, exc_info=True)
            self._cleanup()
