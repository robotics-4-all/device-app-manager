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
import pprint

import amqp_common


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='AMQP RPC Client CLI.')
    parser.add_argument(
        '--device-id', dest='device_id', help='UID of the device',
        type=str, default='')
    parser.add_argument(
        '--rpc-name', dest='rpc_name', help='The URI of the RPC endpoint',
        type=str, default='thing.{}.appmanager.apps')
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
    rpc_name = args.rpc_name
    debug = True if args.debug else False

    conn_params = amqp_common.ConnectionParameters(
        host=host, port=port, vhost=vhost)
    conn_params.credentials = amqp_common.Credentials(username, password)

    rpc_name = rpc_name.format(device_id)
    rpc_client = amqp_common.RpcClient(rpc_name, connection_params=conn_params)

    rpc_client.debug = True
    resp = rpc_client.call({}, timeout=30)
    pprint.pprint(resp)
