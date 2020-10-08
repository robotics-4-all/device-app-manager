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


class AppDownloadMessage(amqp_common.Message):
    __slots__ = ['app_id', 'app_tarball', 'app_type']

    def __init__(self, app_name, app_type, app_tarball_fmsg):
        self.app_id = app_id
        self.app_tarball = app_tarball_fmsg
        self.app_type = app_type


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='AMQP RPC Client CLI.')
    parser.add_argument(
        '--fpath', dest='fpath', help='Path of the application tarball',
        type=str, default='')
    parser.add_argument(
        '--device-id', dest='device_id', help='UID of the device',
        type=str, default='')
    parser.add_argument(
        '--app-id', dest='app_id', help='Application ID/Name',
        type=str, default='')
    parser.add_argument(
        '--app-type', dest='app_type', help='Application Type',
        type=str, default='')
    parser.add_argument(
        '--rpc-name', dest='rpc_name', help='The URI of the RPC endpoint',
        type=str, default='thing.{}.appmanager.install_app')
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
    fpath = args.fpath
    app_type = args.app_type
    app_id = args.app_id
    rpc_name = args.rpc_name
    debug = True if args.debug else False

    conn_params = amqp_common.ConnectionParameters(
        host=host, port=port, vhost=vhost)
    conn_params.credentials = amqp_common.Credentials(username, password)

    rpc_name = rpc_name.format(device_id)
    rpc_client = amqp_common.RpcClient(rpc_name, connection_params=conn_params)
    fmsg = amqp_common.FileMessage()
    fmsg.load_from_file(fpath)
    msg = AppDownloadMessage(app_id, app_type, fmsg)

    rpc_client.debug = True
    resp = rpc_client.call(msg.to_dict(), timeout=30)
    print('[*] - Response:\n{}'.format(resp))
