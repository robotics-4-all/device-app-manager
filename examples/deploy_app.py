#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals
)

import sys
import argparse

import amqp_common


class AppDeployMessage(amqp_common.Message):
    __slots__ = ['header', 'app_tarball', 'app_type']

    def __init__(self, app_tarball_fmsg, app_type):
        self.header = amqp_common.HeaderMessage()
        self.app_tarball = app_tarball_fmsg
        self.app_type = app_type


class AppKillMessage(amqp_common.Message):
    __slots__ = ['header', 'app_id']

    def __init__(self, app_id):
        self.header = amqp_common.HeaderMessage()
        self.app_id = app_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='AMQP RPC Client CLI.')
    parser.add_argument(
        '--device-id', dest='device_id', help='UID of the device',
        type=str, default='')
    parser.add_argument(
        '--app-name', dest='app_name', help='Application Name',
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
        default='/klpanagi')
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
    fpath = args.fpath
    app_type = args.app_type
    rpc_name = args.rpc_name
    debug = True if args.debug else False

    conn_params = amqp_common.ConnectionParameters(
        host=host, port=port, vhost=vhost)
    conn_params.credentials = amqp_common.Credentials(username, password)

    rpc_name = rpc_name.format(device_id)
    rpc_client = amqp_common.RpcClient(rpc_name, connection=conn)
    fmsg = amqp_common.FileMessage()
    fmsg.load_from_file(fpath)
    msg = AppDeployMessage(fmsg, app_type)

    rpc_client.debug = True
    resp = rpc_client.call(msg.serialize_json(), timeout=30)
    print('[*] - Response:\n{}'.format(resp))
