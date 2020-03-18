#!/usr/bin/env python3

from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals
)

import sys
import os
import argparse
import configparser

from device_app_manager import AppManager


def load_cfg(cfg_file=None):
    if cfg_file is None:
        cfg_file = '~/.config/device_app_manager/config'
    cfg_file = os.path.expanduser(cfg_file)
    if not os.path.isfile(cfg_file):
        self.log.warn('Config file does not exist')
        return False
    config = configparser.ConfigParser()
    config.read(cfg_file)
    try:
        username = config.get('platform', 'username')
    except configparser.NoOptionError:
        username = 'bot'
    try:
        password = config.get('platform', 'password')
    except configparser.NoOptionError:
        password = 'b0t'
    try:
        host = config.get('platform', 'host')
    except configparser.NoOptionError:
        host = '127.0.0.1'
    try:
        port = config.get('platform', 'port')
    except configparser.NoOptionError:
        port = '5762'
    try:
        vhost = config.get('platform', 'vhost')
    except configparser.NoOptionError:
        vhost = '/'
    try:
        heartbeat_topic = config.get('core', 'heartbeat_topic')
    except configparser.NoOptionError:
        heartbeat_topic = 'thing.x.appmanager.hearbeat'
    try:
        heartbeat_interval = config.get('core', 'heartbeat_interval')
    except configparser.NoOptionError:
        heartbeat_interval = 10  # seconds

    return {
        'username': username,
        'password': password,
        'host': host,
        'port': int(port),
        'vhost': vhost,
        'heartbeat_interval': int(heartbeat_interval),
        'heartbeat_topic': heartbeat_topic
    }


def main():
    parser = argparse.ArgumentParser(description='Application Manager CLI')
    parser.add_argument('--host', dest='host',
                        help='AMQP broker host (IP/Hostname)',
                        default=None)
    parser.add_argument('--port', dest='port',
                        help='AMQP broker listening port',
                        default=None)
    parser.add_argument('--vhost', dest='vhost',
                        help='Virtual host to connect to',
                        default=None)
    parser.add_argument('--username', dest='username',
                        help='Authentication username',
                        default=None)
    parser.add_argument('--password', dest='password',
                        help='Authentication password',
                        default=None)
    parser.add_argument('--queue-size', dest='queue_size',
                        help='Maximum queue size.',
                        type=int,
                        default=None)
    parser.add_argument('--heartbeat', dest='heartbeat',
                        help='Heartbeat interval in seconds',
                        type=int,
                        default=None)
    parser.add_argument('--config', dest='config',
                        help='Config file path',
                        default='~/.config/device_app_manager/config')
    parser.add_argument('--debug', dest='debug',
                        help='Enable debugging',
                        type=bool,
                        const=True,
                        nargs='?')

    args = parser.parse_args()
    config_file = args.config
    username = args.username
    password = args.password
    host = args.host
    port = args.port
    vhost = args.vhost
    debug = args.debug
    heartbeat = args.heartbeat

    config = load_cfg(config_file)

    if username is not None:
        config['username'] = username
    if password is not None:
        config['password'] = password
    if host is not None:
        config['host'] = host
    if port is not None:
        config['port'] = port
    if vhost is not None:
        config['vhost'] = vhost
    if heartbeat is not None:
        config['heartbeat_interval'] = heartbeat_interval

    print(config)

    manager = AppManager(
        platform_creds=(config['username'], config['password']),
        platform_host=config['host'],
        platform_port=config['port'],
        platform_vhost=config['vhost'],
        heartbeat_interval=config['heartbeat_interval']
    )
    manager.run()


if __name__ == "__main__":
    main()
