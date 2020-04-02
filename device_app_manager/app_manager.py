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
from .app import *
from .redis_controller import RedisController


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


class AppManager(object):
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
    REDIS_HOST = 'localhost'
    REDIS_PORT = 6379
    REDIS_DB = 0
    REDIS_PASSWORD = ''
    REDIS_APP_LIST_NAME = 'appmanager.apps'

    def __init__(self,
                 platform_creds=('guest', 'guest'),
                 heartbeat_interval=10,
                 debug=True,
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
                 redis_app_list_name=None
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
        if redis_host is not None:
            self.REDIS_HOST = redis_host
        if redis_port is not None:
            self.REDIS_PORT = redis_port
        if redis_db is not None:
            self.REDIS_DB = redis_db
        if redis_password is not None:
            self.REDIS_PASSWORD = redis_password
        if redis_app_list_name is not None:
            self.REDIS_APP_LIST_NAME = redis_app_list_name

        self.APP_STORAGE_DIR = os.path.expanduser(self.APP_STORAGE_DIR)

        self._heartbeat_data = {}
        self._heartbeat_thread = None
        self.apps = {}

        self.__init_logger()
        self.debug = debug

        self._create_app_storage_dir()
        self.redis = RedisController(redis_host, redis_port, redis_db,
                                     redis_password,
                                     app_list_name=redis_app_list_name)

    def install_app(self, app_name, app_type, app_tarball_path):
        app_d = self._get_app_object(app_name, app_type)
        app_d.build(app_tarball_path)
        if self.redis.app_exists(app_name):
            ## Updating app
            self.log.info('Updating App in DB: <{}>'.format(app_name))
            self.redis.update_app(app_d._serialize())
        else:
            ## Creating new app instance in db
            self.log.info('Storing new App in DB: <{}>'.format(app_name))
            self.redis.add_app(app_d._serialize())

        self.redis.save_db()
        return app_name

    def delete_app(self, app_name):
        if not self.redis.app_exists(app_name):
            raise ValueError('App does not exist locally')
        app = self.redis.get_app(app_name)

        app_d = self._get_app_object(app_name, app['type'])
        app_d.stop()

        self.log.info('Deleting Application <{}>'.format(app_name))
        self.redis.delete_app(app_name)

        ## TODO: Remove from docker!!

        ## Save db in hdd
        self.redis.save_db()

    def start_app(self, app_name):
        if not self.redis.app_exists(app_name):
            raise ValueError('App does not exist locally')

        app = self.redis.get_app(app_name)

        if app['state'] == 1:
            raise ValueError('Application is allready running.')

        app_d = self._get_app_object(app_name, app['type'])

        app_d.deploy()

        self.redis.set_app_state(app_name, 1)
        self.redis.set_app_property(app_name, 'docker_container',
                                    {'name': app_d.container_name,
                                     'id': app_d.container_id})

        ## Save db in hdd
        self.redis.save_db()
        return app_name

    def stop_app(self, app_name):
        app = self.redis.get_app(app_name)

        app_d = self._get_app_object(app_name, app['type'])
        app_d.stop()

        self.redis.set_app_state(app_name, 0)
        self.redis.save_db()

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
        if self._deploy_rpc:
            self._deploy_rpc.stop()

        apps = self.redis.get_apps()
        app_idx = 0
        for app in apps:
            self.redis.set_app_state(app['name'], 0)

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
        return {
            'status': 200
        }

    def _install_app_rpc_callback(self, msg, meta):
        try:
            if 'app_type' not in msg:
                raise ValueError('Message does not include app_type property')
            if 'app_tarball' not in msg:
                raise ValueError('Message does not include app_tarball property')
            app_type = msg['app_type']
            app_file = msg['app_tarball']
            # Optional. Empty app_name means unnamed app
            app_name = msg['app_id'] if 'app_id' in msg else ''
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
            if not 'app_id' in msg:
                raise ValueError('Message schema error. app_id is not defined')
            app_name = msg['app_id']

            self.delete_app(app_name)

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
            # Optional. Empty app_name means unnamed app
            app_name = msg['app_id'] if 'app_id' in msg else ''

            if not isinstance(app_name, str):
                raise TypeError('Parameter app_name should be of type string')
            elif app_name == '':
                raise ValueError('Parameter app_name value is empty')

            app_id = self.start_app(app_name)
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
            if not 'app_id' in msg:
                raise ValueError('Message schema error. app_id is not defined')
            app_name = msg['app_id']

            if not self.redis.app_exists(app_name):
                raise ValueError('App does not exist locally')

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

    def _get_app_object(self, app_name, app_type):
        # Add here more deployment options.
        # TODO: The way deployment definition works much change to module-based.
        # Generalize the way so that it is easier to maintain extentions.
        if app_type == 'py3':
            app_deployment = AppPython3(
                self.broker_conn_params,
                app_name,
                redis_host=self.REDIS_HOST,
                redis_port=self.REDIS_PORT,
                redis_db=self.REDIS_DB,
                redis_password=self.REDIS_PASSWORD,
                redis_app_list_name=self.REDIS_APP_LIST_NAME)
        elif app_type == 'r4a_ros2_py':
            app_deployment = AppR4AROS2Py(
                self.broker_conn_params,
                app_name,
                redis_host=self.REDIS_HOST,
                redis_port=self.REDIS_PORT,
                redis_db=self.REDIS_DB,
                redis_password=self.REDIS_PASSWORD,
                redis_app_list_name=self.REDIS_APP_LIST_NAME)
        else:
            raise TypeError(
                'Application type <{}> not supported'.format(app_type))
        return app_deployment

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
            self._init_platform_params()
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

