#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import argparse
from pprint import pprint

import amqp_common


class AppStartMessage(amqp_common.Message):
    __slots__ = ['app_id', 'app_args']

    def __init__(self, app_id, app_args=[]):
        self.app_id = app_id
        self.app_args=app_args


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='AMQP RPC Client CLI.')
    parser.add_argument(
        '--device-id', dest='device_id', help='UID of the device',
        type=str, default='')
    parser.add_argument(
        '--app-id', dest='app_id', help='Application ID/Name',
        type=str, default='')
    parser.add_argument(
        '--rpc-name', dest='rpc_name', help='The URI of the RPC endpoint',
        type=str, default='thing.{}.appmanager.start_app')
    parser.add_argument(
        '--host',
        dest='host',
        help='AMQP broker host (IP/Hostname)',
        default='localhost')
    parser.add_argument(
        '--port',
        dest='port',
        help='AMQP broker listening port',
        default='5672')
    parser.add_argument(
        '--vhost',
        dest='vhost',
        help='Virtual host to connect to.',
        default='/')
    parser.add_argument(
        '--username',
        dest='username',
        help='Authentication username',
        default='bot')
    parser.add_argument(
        '--password',
        dest='password',
        help='Authentication password',
        default='b0t')
    parser.add_argument(
        '--debug',
        dest='debug',
        help='Enable debugging',
        type=bool,
        const=True,
        nargs='?')

    args = parser.parse_args()
    host = args.host
    port = args.port
    vhost = args.vhost
    username = args.username
    password = args.password
    device_id = args.device_id
    app_id = args.app_id
    rpc_name = args.rpc_name
    debug = True if args.debug else False

    conn_params = amqp_common.ConnectionParameters(
        host=host, port=port, vhost=vhost)
    conn_params.credentials = amqp_common.Credentials(username, password)

    rpc_name = rpc_name.format(device_id)
    rpc_client = amqp_common.RpcClient(rpc_name, connection_params=conn_params)
    msg = AppStartMessage(app_id, ['--arg1', '1'])

    rpc_client.debug = True
    resp = rpc_client.call(msg.to_dict(), timeout=30)
    pprint(resp)
