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
    APP_DEPLOY_RPC_NAME = 'thing.x.appmanager.deploy_app'
    APP_DOWNLOAD_RPC_NAME = 'thing.x.appmanager.download_app'
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
                 app_deploy_rpc_name=None,
                 app_download_rpc_name=None,
                 app_start_rpc_name=None,
                 app_stop_rpc_name=None,
                 alive_rpc_name=None,
                 heartbeat_topic=None,
                 connected_event=None,
                 disconnected_event=None,
                 platform_host=None,
                 platform_port=None,
                 platform_vhost=None
                 ):
        atexit.register(self._cleanup)

        self.platform_creds = platform_creds
        self.heartbeat_interval = heartbeat_interval
        if app_deploy_rpc_name is not None:
            self.APP_DEPLOY_RPC_NAME = app_deploy_rpc_name
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
        for key in self.apps:
            self.apps[key].stop()

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
        self._init_app_deploy_rpc()
        self._init_app_stop_rpc()
        self._init_isalive_rpc()
        self._init_app_start_rpc()
        self._init_app_download_rpc()
        self._init_app_list_rpc()

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

    def _init_app_deploy_rpc(self):
        rpc_name = self.APP_DEPLOY_RPC_NAME.replace(
                'x', self.platform_creds[0])

        self._deploy_rpc = RpcServer(
            rpc_name,
            on_request=self._deploy_app_rpc_callback,
            connection_params=self.broker_conn_params,
            debug=self.debug)

        self._deploy_rpc.run_threaded()

    def _init_app_stop_rpc(self):
        rpc_name = self.APP_STOP_RPC_NAME.replace('x', self.platform_creds[0])
        self._stop_rpc = RpcServer(
            rpc_name,
            on_request=self._stop_app_rpc_callback,
            connection_params=self.broker_conn_params,
            debug=self.debug)

        self._stop_rpc.run_threaded()

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

    def _stop_app_rpc_callback(self, msg, meta):
        app_id = msg['app_id']
        try:
            r = self.stop_app(app_id)
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

    def _isalive_rpc_callback(self, msg, meta):
        return {
            'status': 200
        }

    def _deploy_app_rpc_callback(self, msg, meta):
        try:
            app_type = msg['app_type']
            app_file = msg['app_tarball']
            # Optional. Empty app_name means unnamed app
            app_name = msg['app_name'] if 'app_name' in msg else ''
            tarball_b64 = app_file['data']

            tarball_path = self._store_app_tar(
                tarball_b64, self.APP_STORAGE_DIR)

            app_deployment = self._build_app(app_name, app_type, tarball_path)
            app_id = self._deploy_app(app_deployment)
            return {
                'status': 200,
                'app_id': app_id,
                'error': ''
            }
        except Exception as e:
            self.log.error(e, exc_info=True)
            return {
                'status': 404,
                'app_id': -1,
                'error': str(e)
            }

    def _download_app_rpc_callback(self, msg, meta):
        try:
            app_type = msg['app_type']
            app_file = msg['app_tarball']
            # Optional. Empty app_name means unnamed app
            app_name = msg['app_name'] if 'app_name' in msg else ''
            tarball_b64 = app_file['data']

            apps = self._redis.lrange(self.REDIS_APP_LIST_NAME, 0, -1)
            exists = False
            for app in apps:
                app = json.loads(app)
                if app['name'] == app_name:
                    exists = True
                    break

            tarball_path = self._store_app_tar(
                tarball_b64, self.APP_STORAGE_DIR)

            app_deploy = self._get_app_object(
                app_name, app_type, tarball_path)
            self._build_app(app_deploy)
            app_image = app_deploy.image_id

            schema = {
                'name': app_name,
                'type': app_type,
                'path': tarball_path,
                'image': app_image
            }

            if exists:
                llen = self._redis.llen(self.REDIS_APP_LIST_NAME)
                for i in range(llen):
                    app = self._redis.lindex(self.REDIS_APP_LIST_NAME, i)
                    app = json.loads(app)
                    if app['name'] == app_name:
                        self.log.info('Updating app <{}>'.format(app_name))
                        self._redis.lset(
                            self.REDIS_APP_LIST_NAME, i, json.dumps(schema))
                        break
            else:
                self._redis.lpush(
                    self.REDIS_APP_LIST_NAME, json.dumps(schema))
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
            app_name = msg['app_name'] if 'app_name' in msg else ''

            if not isinstance(app_name, str):
                raise TypeError('Parameter app_name should be of type string')
            elif app_name == '':
                raise ValueError('Parameter app_name value is empty')

            apps = self._redis.lrange(self.REDIS_APP_LIST_NAME, 0, -1)
            if len(apps) == 0:
                raise ValueError(
                    'Application with name <{}> not found in local storage'.format(
                        app_name))
            elif len(apps) > 1:
                raise NotImplementedError(
                    'Found more than 1 app with the same name in local storage')
            for app in apps:
                if app['name'] == app_name:
                    app_deploy = self._get_app_object(
                        app['name'], app['type'], app['path'])
                    self._deploy_app(app_deploy)

            resp =  {
                'status': 200,
                'error': ''
            }
        except Exception as e:
            self.log.error(e, exc_info=True)
            resp =  {
                'status': 404,
                'error': str(e)
            }
        finally:
            print(resp)
            return resp

    def _app_list_rpc_callback(self, msg, meta):
        try:
            apps = self._redis.lrange(self.REDIS_APP_LIST_NAME, 0, -1)
            print(apps)
            resp = {
                'status': 200,
                'stats': 200,
                'apps': [json.loads(app)['name'] for app in apps],
                'error': ''
            }
            self.log.info(resp)
            return resp
        except Exception as e:
            self.log.error(e, exc_info=True)
            return {
                'status': 404,
                'error': str(e)
            }

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

    def _build_app(self, app_deployment):
        image_id = app_deployment.build()
        return image_id

    def _deploy_app(self, app_deployment):
        app_id = app_deployment.deploy()
        self.apps[app_id] = app_deployment
        return app_id

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

    def stop_app(self, app_id):
        if app_id not in self.apps:
            self.log.error('App does not exist: {}'.format(app_id))
            raise TypeError('Application with id={} does not exist'.format(
                app_id))
        app = self.apps[app_id]
        app.stop()
        del self.apps[app_id]
        self.log.info('App {} killed!'.format(app_id))
        return {
            'status': 200
        }

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
