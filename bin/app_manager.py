#!/usr/bin/env python

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
        debug = config.get('core', 'debug')
        debug = True if debug == 1 else False
    except configparser.NoOptionError:
        debug = False
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
        heartbeat_topic = config.get('services', 'heartbeat_topic')
    except configparser.NoOptionError:
        heartbeat_topic = 'thing.x.appmanager.hearbeat'
    try:
        heartbeat_interval = config.get('core', 'heartbeat_interval')
    except configparser.NoOptionError:
        heartbeat_interval = 10  # seconds
    try:
        app_list_rpc_name = config.get('services', 'app_list_rpc_name')
    except configparser.NoOptionError:
        app_list_rpc_name = 'thing.x.appmanager.apps'
    try:
        get_running_apps_rpc_name = config.get('services', 'get_running_apps_rpc_name')
    except configparser.NoOptionError:
        get_running_apps_rpc_name = 'thing.x.appmanager.apps.running'
    try:
        app_delete_rpc_name = config.get('services', 'app_delete_rpc_name')
    except configparser.NoOptionError:
        app_delete_rpc_name = 'thing.x.appmanager.delete_app'
    try:
        app_download_rpc_name = config.get('services', 'app_download_rpc_name')
    except configparser.NoOptionError:
        app_download_rpc_name = 'thing.x.appmanager.download_app'
    try:
        app_start_rpc_name = config.get('services', 'app_start_rpc_name')
    except configparser.NoOptionError:
        app_start_rpc_name = 'thing.x.appmanager.start_app'
    try:
        app_stop_rpc_name = config.get('services', 'app_stop_rpc_name')
    except configparser.NoOptionError:
        app_stop_rpc_name = 'thing.x.appmanager.stop_app'
    try:
        alive_rpc_name = config.get('services', 'alive_rpc_name')
    except configparser.NoOptionError:
        alive_rpc_name = 'thing.x.appmanager.is_alive'
    try:
        connected_event = config.get('services', 'connected_event')
    except configparser.NoOptionError:
        connected_event = 'thing.x.appmanager.connected'
    try:
        disconnected_event = config.get('services', 'disconnected_event')
    except configparser.NoOptionError:
        disconnected_event = 'thing.x.appmanager.disconnected'
    try:
        redis_host = config.get('redis', 'host')
    except configparser.NoOptionError:
        redis_host = 'localhost'
    try:
        redis_port = config.get('redis', 'port')
    except configparser.NoOptionError:
        redis_port = 6379
    try:
        redis_db = config.get('redis', 'database')
    except configparser.NoOptionError:
        redis_db = 0
    try:
        redis_password = config.get('redis', 'password')
    except configparser.NoOptionError:
        redis_password = ''
    try:
        redis_app_list_name = config.get('redis', 'app_list_name')
    except configparser.NoOptionError:
        redis_app_list_name = 'appmanager.apps'

    return {
        'debug': debug,
        'username': username,
        'password': password,
        'host': host,
        'port': int(port),
        'vhost': vhost,
        'heartbeat_interval': int(heartbeat_interval),
        'heartbeat_topic': heartbeat_topic,
        'app_delete_rpc_name': app_delete_rpc_name,
        'app_list_rpc_name': app_list_rpc_name,
        'get_running_apps_rpc_name': get_running_apps_rpc_name,
        'app_download_rpc_name': app_download_rpc_name,
        'app_start_rpc_name': app_start_rpc_name,
        'app_stop_rpc_name': app_stop_rpc_name,
        'alive_rpc_name': alive_rpc_name,
        'connected_event': connected_event,
        'disconnected_event': disconnected_event,
        'redis_host': redis_host,
        'redis_port': redis_port,
        'redis_db': redis_db,
        'redis_password': redis_password,
        'redis_app_list_name': redis_app_list_name
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

    manager = AppManager(
        platform_creds=(config['username'], config['password']),
        platform_host=config['host'],
        platform_port=config['port'],
        platform_vhost=config['vhost'],
        heartbeat_interval=config['heartbeat_interval'],
        heartbeat_topic=config['heartbeat_topic'],
        app_list_rpc_name=config['app_list_rpc_name'],
        app_delete_rpc_name=config['app_delete_rpc_name'],
        app_download_rpc_name=config['app_download_rpc_name'],
        app_start_rpc_name=config['app_start_rpc_name'],
        app_stop_rpc_name=config['app_stop_rpc_name'],
        alive_rpc_name=config['alive_rpc_name'],
        get_running_apps_rpc_name=config['get_running_apps_rpc_name'],
        connected_event=config['connected_event'],
        disconnected_event=config['disconnected_event'],
        redis_host=config['redis_host'],
        redis_port=config['redis_port'],
        redis_db=config['redis_db'],
        redis_password=config['redis_password'],
        redis_app_list_name=config['redis_app_list_name'],
        debug=config['debug']

    )
    manager.run()


if __name__ == "__main__":
    main()
