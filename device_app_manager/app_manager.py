#!/usr/bin/env python3

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
from .deployments import *


class Protocol(object):

    @staticmethod
    def response_success(app_id=-1):
        return {
            'status': 200,
            'app_id': app_id,
            'error': ''
        }

    @staticmethod
    def response_error(error_msg=''):
        return {
            'status': 404,
            'app_id': -1,
            'error': error_msg
        }


class RemoteLogger(object):
    def __init__(self, platform_connection_params=None, topic=None):
        self.pub = PublisherSync(
                topic=topic, connection_params=platform_connection_params,
                debug=False)

    def log(self, msg):
        pass


class AppManagerProtocol(object):
    def __init__(self):
        pass

    def rpc_deployapp(self):
        pass

    def rpc_isalive(self):
        pass

    def rpc_killapp(self):
        pass


class AppManager(object):
    APP_STORAGE_DIR = '~/.apps'
    APP_DOWNLOAD_RPC_NAME = 'thing.x.appmanager.download_app'
    APP_DELETE_RPC_NAME = 'thing.x.appmanager.delete_app'
    APP_START_RPC_NAME = 'thing.x.appmanager.start_app'
    APP_STOP_RPC_NAME = 'thing.x.appmanager.stop_app'
    APP_LIST_RPC_NAME = 'thing.x.appmanager.apps'
    ISALIVE_RPC_NAME = 'thing.x.appmanager.is_alive'
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
                 app_delete_rpc_name=None,
                 app_download_rpc_name=None,
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
        if app_download_rpc_name is not None:
            self.APP_DOWNLOAD_RPC_NAME = app_download_rpc_name
        if app_start_rpc_name is not None:
            self.APP_START_RPC_NAME = app_start_rpc_name
        if app_start_rpc_name is not None:
            self.APP_START_RPC_NAME = app_start_rpc_name
        if app_stop_rpc_name is not None:
            self.APP_STOP_RPC_NAME = app_stop_rpc_name
        if alive_rpc_name is not None:
            self.ISALIVE_RPC_NAME
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

        self._redis = redis.Redis(
            host=self.REDIS_HOST,
            port=self.REDIS_PORT,
            db=self.REDIS_DB,
            password=self.REDIS_PASSWORD,
            decode_responses=True,
            charset="utf-8"
        )

    @property
    def debug(self):
        return self._debug

    @debug.setter
    def debug(self, val):
        if val:
            enable_debug(self.log)
            self._debug = True
        else:
            disable_debug(self.log)
            self._debug = False

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
        if self._stop_app_rpc:
            self._stop_app_rpc.stop()

        apps = self._redis_get_app_list()
        apps = [json.loads(app) for app in apps]
        app_idx = 0
        for app in apps:
            app['state'] = 0
            app['container']['name'] = ''
            app['container']['id'] = ''
            self._redis.lset(self.REDIS_APP_LIST_NAME, app_idx, json.dumps(app))

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
        self._init_app_download_rpc()
        self._init_app_start_rpc()
        self._init_app_stop_rpc()
        self._init_app_list_rpc()
        self._init_app_delete_rpc()

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
            on_request=self._app_list_rpc_callback,
            connection_params=self.broker_conn_params,
            debug=self.debug)

        self._app_list_rpc.run_threaded()

    def _init_app_download_rpc(self):
        rpc_name = self.APP_DOWNLOAD_RPC_NAME.replace(
                'x', self.platform_creds[0])

        self._download_rpc = RpcServer(
            rpc_name,
            on_request=self._download_app_rpc_callback,
            connection_params=self.broker_conn_params,
            debug=self.debug)

        self._download_rpc.run_threaded()

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

    def _download_app_rpc_callback(self, msg, meta):
        try:
            app_type = msg['app_type']
            app_file = msg['app_tarball']
            # Optional. Empty app_name means unnamed app
            app_name = msg['app_id'] if 'app_id' in msg else ''
            tarball_b64 = app_file['data']

            apps = self._redis_get_app_list()

            tarball_path = self._store_app_tar(
                tarball_b64, self.APP_STORAGE_DIR)

            app_deploy = self._get_app_object(
                app_name, app_type, tarball_path)
            self._build_app(app_deploy)
            app_image = app_deploy.image_id

            app, app_index = self._check_app_exists(app_name, apps)
            if app_index != -1:
                # Update
                app['type'] = app_type
                app['path'] = tarball_path
                app['image'] = app_image
                self.log.info('Updating app <{}>'.format(app_name))
                self._redis.lset(
                    self.REDIS_APP_LIST_NAME, app_index, json.dumps(app))
            else:
                # Create
                app = {
                    'name': app_name,
                    'type': app_type,
                    'path': tarball_path,
                    'image': app_image,
                    'container': {
                        'name': '',
                        'id': ''
                    },
                    'state': 0,
                }

                self._redis.lpush(
                    self.REDIS_APP_LIST_NAME, json.dumps(app))
            ## Save db in hdd
            self._redis.bgsave()

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

    def _delete_app_rpc_callback(self, msg, meta):
        try:
            # Optional. Empty app_name means unnamed app
            if not 'app_name' in msg:
                raise ValueError('Message schema error. app_name is not defined')
            app_name = msg['app_id']

            apps = self._redis_get_app_list()

            app, app_index = self._check_app_exists(app_name, apps)
            if app_index == -1:
                raise ValueError('Application does not exist')

            self.log.info('Deleting Application <{}>'.format(app_name))
            self._redis.lrem(self.REDIS_APP_LIST_NAME, 1, app_index)

            ## TODO: Remove from docker!!

            ## Save db in hdd
            self._redis.bgsave()

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
        try:
            # Optional. Empty app_name means unnamed app
            app_name = msg['app_id'] if 'app_id' in msg else ''

            if not isinstance(app_name, str):
                raise TypeError('Parameter app_name should be of type string')
            elif app_name == '':
                raise ValueError('Parameter app_name value is empty')

            apps = self._redis_get_app_list()
            if len(apps) == 0:
                raise ValueError(
                    'Application with name <{}> not found in local storage'.format(
                        app_name))
            elif len(apps) > 1:
                raise NotImplementedError(
                    'Found more than 1 app with the same name in local storage')
            app, app_index = self._check_app_exists(app_name, apps)
            if app_index == -1:
                raise ValueError('Application does not exist')
            ## Deploy application
            app_deploy = self._get_app_object(
                app['name'], app['type'], app['path'])

            container_name, container_id = self._deploy_app(app_deploy)

            app['container'] = {
                'name': container_name,
                'id': container_id
            }
            app['state'] = 1
            self._redis.lset(self.REDIS_APP_LIST_NAME, app_index, json.dumps(app))

            ## Save db in hdd
            self._redis.bgsave()

            resp =  {
                'status': 200,
                'app_id': app_name,
                'error': ''
            }
        except Exception as e:
            self.log.error(e, exc_info=True)
            resp =  {
                'status': 404,
                'app_id': "",
                'error': str(e)
            }
        finally:
            print(resp)
            return resp

    def _stop_app_rpc_callback(self, msg, meta):
        app_name = msg['app_id']
        try:
            apps = self._redis_get_app_list()
            if len(apps) == 0:
                raise ValueError(
                    'Application with name <{}> not found in local storage'.format(
                        app_name))
            elif len(apps) > 1:
                raise NotImplementedError(
                    'Found more than 1 app with the same name in local storage')
            app, app_index = self._check_app_exists(app_name, apps)
            if app_index == -1:
                raise ValueError('Application does not exist')

            if app['state'] == 0:
                raise ValueError('Application is not running')

            app_deploy = self._get_app_object(
                app['name'], app['type'], app['path'])
            app_deploy.container_name = app['container']['id']
            app_deploy.stop()

            # Update Redis
            app['container'] = ''
            app['state'] = 0
            self._redis.lset(self.REDIS_APP_LIST_NAME, app_index, json.dumps(app))

            ## Save db in hdd
            self._redis.bgsave()

            self.log.info('App {} stopped!'.format(app_name))
            return {
                'status': 200,
                'skata': 1
            }
        except Exception as e:
            self.log.error(e, exc_info=True)
            return {
                'status': 404,
                'error': str(e)
            }

    def _app_list_rpc_callback(self, msg, meta):
        resp = {
            'status': 200,
            'apps': []
            'error': ''
        }
        try:
            apps = self._redis.lrange(self.REDIS_APP_LIST_NAME, 0, -1)
            resp['apps'] = [json.loads(app) for app in apps],
            return resp
        except Exception as e:
            self.log.error(e, exc_info=True)
            resp['error'] = str(e)
            return resp

    def _build_app(self, app_deployment):
        image_id = app_deployment.build()
        return image_id

    def _deploy_app(self, app_deployment):
        app_id, container_id = app_deployment.deploy()
        self.apps[app_id] = app_deployment
        return app_id, container_id

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

    def _get_app_object(self, app_name, app_type, app_tar_path):
        # Add here more deployment options.
        # TODO: The way deployment definition works much change to module-based.
        # Generalize the way so that it is easier to maintain extentions.
        if app_type == 'py3':
            app_deployment = AppDeploymentPython3(
                self.broker_conn_params,
                app_name,
                app_type,
                app_tar_path)
        elif app_type == 'r4a_ros2_py':
            app_deployment = AppDeploymentR4AROS2Py(
                self.broker_conn_params,
                app_name,
                app_type,
                app_tar_path)
        else:
            raise TypeError(
                'Application type <{}> not supported'.format(app_type))
        return app_deployment

    def _check_app_exists(self, app_name, apps):
        app_index = -1
        index = 0
        app = {}
        for _app in apps:
            _app = json.loads(_app)
            if _app['name'] == app_name:
                app = _app
                app_index = index

            index += 1
        resp = (app, app_index)
        return resp

    def _redis_set_app_state(self, app_name, state):
        app = self._redis_get_app(app_name)
        app['state'] = state
        self._redis.lset(self.REDIS_APP_LIST_NAME, app_index, json.dumps(app))

    def _redis_get_app(self, app_name):
            apps = self._redis_get_app_list()
            app, app_index = self._check_app_exists(app_name, apps)

            if app_index == -1:
                return None
            return app

    def _redis_get_app_list(self):
        apps = self._redis.lrange(self.REDIS_APP_LIST_NAME, 0, -1)
        return apps

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

