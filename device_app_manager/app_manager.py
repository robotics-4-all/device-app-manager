from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals
)

import sys
import os
import uuid
import time
import signal
import json
import subprocess
import shutil
import shlex
# from collections import namedtuple

import base64

import redis
import json

from amqp_common import (
    ConnectionParameters,
    Credentials,
    PublisherSync,
    RpcServer
)

from ._logging import create_logger, enable_debug, disable_debug
from .docker_builder import *
from .docker_executor import *
from .redis_controller import RedisController, RedisConnectionParams


class RemoteLogger(object):
    def __init__(self, platform_connection_params=None, topic=None):
        if topic is None:
            u_id = uuid.uuid4().hex[0:8]
            topic = 'logs.{}'.format(u_id)
        self.topic = topic
        self.pub = PublisherSync(
            topic=self.topic,
            connection_params=platform_connection_params,
            debug=False)

    def log(self, msg):
        self.pub.publish(msg)


class AppManagerExecutor(object):
    """Application Manager Executor class.
    Not Implemented!!
    """
    def __init__(self):
        pass


class AppManager(object):
    """AppManager class.
    Implementation of the Device Application Manager as described here (TODO)

    Args:
        platform_creds (tuple): Broker (Username, Password) Tuple.
        heartbeat_interval (int): Interval time to send heartbeat messages.
            Not the same as AMQP heartbeats. Device Manager sends
            heartbeat messages at a specific topic.
        debug (bool) Enable/Disable debug mode.
        app_build_dir (str):
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
    ISALIVE_RPC_NAME = 'thing.x.appmanager.is_alive'
    GET_RUNNING_APPS_RPC_NAME = 'thing.x.appmanager.apps.running'
    HEARTBEAT_TOPIC = 'thing.x.appmanager.heartbeat'
    THING_CONNECTED_EVENT = 'thing.x.appmanager.connected'
    THING_DISCONNECTED_EVENT = 'thing.x.appmanager.disconnected'
    PLATFORM_PORT = '5672'
    PLATFORM_HOST = '155.207.33.189'
    PLATFORM_VHOST = '/'
    HEARTBEAT_INTERVAL = 10  # seconds

    def __init__(self,
                 platform_creds=('guest', 'guest'),
                 heartbeat_interval=10,
                 debug=True,
                 app_build_dir=None,
                 stop_apps_on_exit=None,
                 keep_app_tarballls=None,
                 app_storage_dir=None,
                 app_image_prefix=None,
                 app_list_rpc_name=None,
                 get_running_apps_rpc_name=None,
                 app_delete_rpc_name=None,
                 app_install_rpc_name=None,
                 app_start_rpc_name=None,
                 app_stop_rpc_name=None,
                 alive_rpc_name=None,
                 heartbeat_topic=None,
                 connected_event=None,
                 disconnected_event=None,
                 platform_host=None,
                 platform_port=None,
                 platform_vhost=None,
                 redis_host=None,
                 redis_port=None,
                 redis_db=None,
                 redis_password=None,
                 redis_app_list_name=None,
                 app_started_event=None,
                 app_stoped_event=None,
                 app_logs_topic=None,
                 app_stats_topic=None,
                 publish_app_logs=None,
                 publish_app_stats=None,
                 ):
        atexit.register(self._cleanup)

        self.platform_creds = platform_creds
        self.heartbeat_interval = heartbeat_interval
        if app_list_rpc_name is not None:
            self.APP_LIST_RPC_NAME = app_list_rpc_name
        if app_delete_rpc_name is not None:
            self.APP_DELETE_RPC_NAME = app_delete_rpc_name
        if app_install_rpc_name is not None:
            self.APP_INSTALL_RPC_NAME = app_install_rpc_name
        if app_start_rpc_name is not None:
            self.APP_START_RPC_NAME = app_start_rpc_name
        if app_start_rpc_name is not None:
            self.APP_START_RPC_NAME = app_start_rpc_name
        if app_stop_rpc_name is not None:
            self.APP_STOP_RPC_NAME = app_stop_rpc_name
        if alive_rpc_name is not None:
            self.ISALIVE_RPC_NAME = alive_rpc_name
        if get_running_apps_rpc_name is not None:
            self.GET_RUNNING_APPS_RPC_NAME = get_running_apps_rpc_name
        if heartbeat_topic is not None:
            self.HEARTBEAT_TOPIC = heartbeat_topic
        if connected_event is not None:
            self.THING_CONNECTED_EVENT = connected_event
        if disconnected_event is not None:
            self.THING_DISCONNECTED_EVENT = disconnected_event
        if platform_host is not None:
            self.PLATFORM_HOST = platform_host
        if platform_port is not None:
            self.PLATFORM_PORT = platform_port
        if platform_vhost is not None:
            self.PLATFORM_VHOST = platform_vhost

        self.APP_STORAGE_DIR = os.path.expanduser(self.APP_STORAGE_DIR)

        self._heartbeat_data = {}
        self._heartbeat_thread = None
        self.apps = {}

        self.__init_logger()
        self.debug = debug
        self._deploy_rpc = None
        self._delete_rpc = None
        self._start_rpc = None
        self._install_rpc = None
        self._stop_rpc = None

        self._init_platform_params()

        redis_params = RedisConnectionParams(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            password=redis_password,
            redis_app_list_name=redis_app_list_name
        )

        self.docker_client = docker.from_env()

        self._create_app_storage_dir()

        self.redis = RedisController(redis_params, redis_app_list_name)
        if not self.redis.ping():
            raise Exception('Could not connect to redis server.')

        self.app_builder = AppBuilderDocker(
            build_dir=app_build_dir,
            image_prefix=app_image_prefix
        )
        self.app_executor = AppExecutorDocker(
            self.broker_conn_params,
            redis_params,
            redis_app_list_name=redis_app_list_name,
            app_started_event=app_started_event,
            app_stoped_event=app_stoped_event,
            app_logs_topic=app_logs_topic,
            app_stats_topic=app_stats_topic,
            publish_logs=publish_app_logs,
            publish_stats=publish_app_stats
        )
        self._clean_startup()

    def _clean_startup(self):
        self.log.info('Prune stopped containers...')
        _c = self.docker_client.containers.prune()
        self.log.info('Cleaning up possible zombie containers...')
        _apps = self.redis.get_apps()
        for app in _apps:
            # print(app)
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
                print(_cid)
                try:
                    _c = self.docker_client.containers.get(_cid)
                    _c.remove(force=True)
                except docker.errors.NotFound as exc:
                    self.log.error(exc, exc_info=True)
                except docker.errors.APIError as exc:
                    self.log.error(exc, exc_info=True)


        # _apps = self.redis.get_apps()
        # for app in _apps:
        #     print(app)

    def install_app(self, app_name, app_type, app_tarball_path):
        _app = self.app_builder.build_app(app_name, app_type, app_tarball_path)

        if self.redis.app_exists(app_name):
            ## Updating app
            self.log.info('Updating App in DB: <{}>'.format(app_name))
            self.redis.update_app(_app.serialize())
        else:
            ## Creating new app instance in db
            self.log.info('Storing new App in DB: <{}>'.format(app_name))
            self.redis.add_app(_app.serialize())

        self.redis.save_db()
        return app_name

    def delete_app(self, app_name, force_stop=False):
        if not self.redis.app_exists(app_name):
            raise ValueError('App <{}> does not exist locally'.format(app_name))

        if self.redis.app_is_running(app_name) and force_stop:
            self.log.info('Stoping App before deleting')
            self.stop_app(app_name)

        self.log.info('Deleting Application <{}>'.format(app_name))
        docker_app_image = self.redis.get_app_image(app_name)
        self.docker_client.images.remove(image=docker_app_image, force=True)
        self.redis.delete_app(app_name)
        ## Save db in hdd
        self.redis.save_db()

    def start_app(self, app_name, app_args=[]):
        if not self.redis.app_exists(app_name):
            raise ValueError('App <{}> does not exist locally'.format(app_name))

        app = self.redis.get_app(app_name)

        if app['state'] == 1:
            raise ValueError('Application is allready running.')

        self.app_executor.run_app(app_name, app_args)
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

    def _init_platform_params(self):
        self.broker_conn_params = ConnectionParameters(
                host=self.PLATFORM_HOST, port=self.PLATFORM_PORT,
                vhost=self.PLATFORM_VHOST)
        self.broker_conn_params.credentials = Credentials(
                self.platform_creds[0], self.platform_creds[1])

    def __init_logger(self):
        """Initialize Logger."""
        self.log = create_logger('Thing-AppManager')

    def _cleanup(self):
        self._send_disconnected_event()
        _rapps = self.redis.get_running_apps()
        for _app in _rapps:
            self.stop_app(_app['name'])

        # apps = self.redis.get_apps()
        # app_idx = 0
        # for app in apps:
        #     self.redis.set_app_state(app['name'], 0)

    def _create_app_storage_dir(self):
        if not os.path.exists(self.APP_STORAGE_DIR):
            os.mkdir(self.APP_STORAGE_DIR)

    def _init_heartbeat_pub(self):
        self._heartbeat_pub = PublisherSync(
            topic=self.HEARTBEAT_TOPIC.replace(
                'x', self.platform_creds[0]),
            connection_params=self.broker_conn_params,
            debug=False
        )
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_pub.pub_loop,
            args=(self._heartbeat_data, 1.0 / self.heartbeat_interval)
        )
        self._heartbeat_thread.daemon = True
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

    def _init_isalive_rpc(self):
        rpc_name = self.ISALIVE_RPC_NAME.replace('x', self.platform_creds[0])

        self._isalive_rpc = RpcServer(
            rpc_name,
            on_request=self._isalive_rpc_callback,
            connection_params=self.broker_conn_params,
            debug=self.debug)

        self._isalive_rpc.run_threaded()

    def _init_app_list_rpc(self):
        rpc_name = self.APP_LIST_RPC_NAME.replace('x', self.platform_creds[0])

        self._app_list_rpc = RpcServer(
            rpc_name,
            on_request=self._get_apps_rpc_callback,
            connection_params=self.broker_conn_params,
            debug=self.debug)

        self._app_list_rpc.run_threaded()

    def _init_get_running_apps_rpc(self):
        rpc_name = self.GET_RUNNING_APPS_RPC_NAME.replace('x', self.platform_creds[0])

        self._running_apps_rpc = RpcServer(
            rpc_name,
            on_request=self._get_running_apps_rpc_callback,
            connection_params=self.broker_conn_params,
            debug=self.debug)

        self._running_apps_rpc.run_threaded()

    def _init_app_install_rpc(self):
        rpc_name = self.APP_INSTALL_RPC_NAME.replace(
                'x', self.platform_creds[0])

        self._install_rpc = RpcServer(
            rpc_name,
            on_request=self._install_app_rpc_callback,
            connection_params=self.broker_conn_params,
            debug=self.debug)

        self._install_rpc.run_threaded()

    def _init_app_start_rpc(self):
        rpc_name = self.APP_START_RPC_NAME.replace(
                'x', self.platform_creds[0])

        self._start_rpc = RpcServer(
            rpc_name,
            on_request=self._start_app_rpc_callback,
            connection_params=self.broker_conn_params,
            debug=self.debug)

        self._start_rpc.run_threaded()

    def _init_app_stop_rpc(self):
        rpc_name = self.APP_STOP_RPC_NAME.replace('x', self.platform_creds[0])
        self._stop_rpc = RpcServer(
            rpc_name,
            on_request=self._stop_app_rpc_callback,
            connection_params=self.broker_conn_params,
            debug=self.debug)

        self._stop_rpc.run_threaded()

    def _init_app_delete_rpc(self):
        rpc_name = self.APP_DELETE_RPC_NAME.replace('x', self.platform_creds[0])
        self._delete_rpc = RpcServer(
            rpc_name,
            on_request=self._delete_app_rpc_callback,
            connection_params=self.broker_conn_params,
            debug=self.debug)

        self._delete_rpc.run_threaded()

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
                raise ValueError('App <{}> does not exist locally'.format(app_name))

            self.stop_app(app_name)
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
        p = PublisherSync(
            self.THING_CONNECTED_EVENT.replace(
                'x', self.platform_creds[0]),
            connection_params=self.broker_conn_params,
            debug=False
        )
        p.publish({})
        p.close()
        del p

    def _send_disconnected_event(self):
        p = PublisherSync(
            self.THING_DISCONNECTED_EVENT.replace(
                'x', self.platform_creds[0]),
            connection_params=self.broker_conn_params,
            debug=False
        )
        p.publish({})
        p.close()
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
