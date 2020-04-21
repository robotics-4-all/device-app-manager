from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals
)

import os
import configparser


def load_cfg(cfg_file):
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
        heartbeat_topic = config.get('platform_monitoring_interfaces',
                                     'heartbeat_topic')
    except configparser.NoOptionError:
        heartbeat_topic = 'thing.x.appmanager.hearbeat'
    try:
        heartbeat_interval = config.get('platform_monitoring_interfaces',
                                        'heartbeat_interval')
    except configparser.NoOptionError:
        heartbeat_interval = 10  # seconds
    try:
        app_list_rpc_name = config.get('platform_control_interfaces',
                                       'app_list_rpc_name')
    except configparser.NoOptionError:
        app_list_rpc_name = 'thing.x.appmanager.apps'
    try:
        get_running_apps_rpc_name = config.get('platform_control_interfaces',
                                               'get_running_apps_rpc_name')
    except configparser.NoOptionError:
        get_running_apps_rpc_name = 'thing.x.appmanager.apps.running'
    try:
        app_delete_rpc_name = config.get('platform_control_interfaces',
                                         'app_delete_rpc_name')
    except configparser.NoOptionError:
        app_delete_rpc_name = 'thing.x.appmanager.delete_app'
    try:
        app_install_rpc_name = config.get('platform_control_interfaces',
                                          'app_install_rpc_name')
    except configparser.NoOptionError:
        app_install_rpc_name = 'thing.x.appmanager.download_app'
    try:
        app_start_rpc_name = config.get('platform_control_interfaces',
                                        'app_start_rpc_name')
    except configparser.NoOptionError:
        app_start_rpc_name = 'thing.x.appmanager.start_app'
    try:
        app_stop_rpc_name = config.get('platform_control_interfaces',
                                       'app_stop_rpc_name')
    except configparser.NoOptionError:
        app_stop_rpc_name = 'thing.x.appmanager.stop_app'
    try:
        alive_rpc_name = config.get('platform_control_interfaces',
                                    'alive_rpc_name')
    except configparser.NoOptionError:
        alive_rpc_name = 'thing.x.appmanager.is_alive'
    try:
        connected_event = config.get('platform_monitoring_interfaces',
                                     'connected_event')
    except configparser.NoOptionError:
        connected_event = 'thing.x.appmanager.connected'
    try:
        disconnected_event = config.get('platform_monitoring_interfaces',
                                        'disconnected_event')
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
        'app_install_rpc_name': app_install_rpc_name,
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
