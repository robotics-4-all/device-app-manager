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
import configparser

from amqp_common import (
    ConnectionParameters,
    Credentials,
    PublisherSync,
    RpcServer
)

from ._logging import create_logger
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
    DEPLOYMENT_BASEDIR = '/tmp/app-deployments'
    APP_DEPLOY_RPC_NAME = 'thing.x.appmanager.deploy'
    APP_KILL_RPC_NAME = 'thing.x.appmanager.kill'
    ISALIVE_RPC_NAME = 'thing.x.appmanager.is_alive'
    HEARTBEAT_TOPIC = 'thing.x.appmanager.heartbeat'
    THING_CONNECTED_EVENT = 'thing.x.appmanager.connected'
    THING_DISCONNECTED_EVENT = 'thing.x.appmanager.disconnected'
    PLATFORM_PORT = '5672'
    PLATFORM_HOST = '155.207.33.189'
    PLATFORM_VHOST = '/'

    def __init__(self,
                 platform_creds=('guest', 'guest'),
                 heartbeat_interval=10,
                 debug=True,
                 app_deploy_rpc_name=None,
                 app_kill_rpc_name=None,
                 alive_rpc_name=None,
                 heartbeat_topic=None,
                 connected_event=None,
                 disconnected_event=None,
                 platform_host=None,
                 platform_port=None,
                 platform_vhost=None
                 ):
        self.platform_creds = platform_creds
        self.heartbeat_interval = heartbeat_interval
        self.debug = debug

        if app_deploy_rpc_name is not None:
            self.APP_DEPLOY_RPC_NAME = app_deploy_rpc_name
        if app_kill_rpc_name is not None:
            self.APP_KILL_RPC_NAME = app_kill_rpc_name
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

        self._heartbeat_data = {}
        self._heartbeat_thread = None
        self.apps = {}

        self.__init_logger()

        self._create_deployment_dir()
        atexit.register(self._cleanup)

    def load_cfg(self, cfg_file):
        config = configparser.ConfigParser()
        config.read(cfg_file)

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
        if self._kill_app_rpc:
            self._kill_app_rpc.stop()
        for key in self.apps:
            self.apps[key].stop()

    def _create_deployment_dir(self):
        if not os.path.exists(self.DEPLOYMENT_BASEDIR):
            os.mkdir(self.DEPLOYMENT_BASEDIR)

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
        self._kill_app_rpc = None
        self._isalive_rpc = None
        self._init_app_deploy_rpc()
        self._init_app_kill_rpc()
        self._init_isalive_rpc()

    def _init_isalive_rpc(self):
        rpc_name = self.ISALIVE_RPC_NAME.replace(
                'x', self.platform_creds[0])

        self._isalive_rpc = RpcServer(
            rpc_name, on_request=self._isalive_rpc_callback,
            connection_params=self.broker_conn_params, debug=self.debug)

        self._isalive_rpc.run_threaded()
        self.log.debug(
                '[*] - Initialized Is-Alive <{}>'.format(rpc_name))

    def _init_app_deploy_rpc(self):
        rpc_name = self.APP_DEPLOY_RPC_NAME.replace(
                'x', self.platform_creds[0])

        self._deploy_rpc = RpcServer(
            rpc_name, on_request=self._deploy_app_rpc_callback,
            connection_params=self.broker_conn_params, debug=True)

        self._deploy_rpc.run_threaded()
        self.log.debug(
                '[*] - Initialized Deployment RPC <{}>'.format(rpc_name))

    def _init_app_kill_rpc(self):
        rpc_name = self.APP_KILL_RPC_NAME.replace(
                'x', self.platform_creds[0])
        self._kill_app_rpc = RpcServer(
            rpc_name, on_request=self._kill_app_rpc_callback,
            connection_params=self.broker_conn_params, debug=True)

        self._kill_app_rpc.run_threaded()
        self.log.debug(
                '[*] - Initialized Deployment RPC <{}>'.format(rpc_name))

    def _kill_app_rpc_callback(self, msg, meta):
        app_id = msg['app_id']
        try:
            r = self.kill_app(app_id)
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
            # self.log.debug(meta)
            self.log.info(msg)
            app_type = msg['app_type']
            app_file = msg['app_tarball']
            tarball_b64 = app_file['data']

            tarball_decoded = base64.b64decode(tarball_b64)
            u_id = uuid.uuid4().hex[0:8]
            tarball_path = os.path.join(
                self.DEPLOYMENT_BASEDIR,
                'app-{}.tar.gz'.format(u_id)
            )
            with open(tarball_path, 'wb') as f:
                f.write(tarball_decoded)

            app_id = self.deploy_app(app_type, tarball_path)
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

    def deploy_app(self, app_type, app_tarball):
        # Add here more deployment options.
        # TODO: The way deployment definition works much change to module-based.
        # Generalize the way so that it is easier to maintain extentions.
        if app_type == 'py3':
            app_deployment = AppDeploymentPython3(self.broker_conn_params,
                                                  app_tarball)
        elif app_type == 'r4a_ros2_py':
            app_deployment = AppDeploymentR4AROS2Py(
                self.broker_conn_params, app_tarball)
        else:
            raise TypeError('Application type <{}> not supported'.format(app_type))
        app_id = app_deployment.start()
        self.apps[app_id] = app_deployment
        return app_id

    def kill_app(self, app_id):
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
