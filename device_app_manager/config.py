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
    ## -------------------------------------------------------------
    ## ----------------------- CORE Parameters ---------------------
    ## -------------------------------------------------------------
    try:
        debug = config.getboolean('core', 'debug')
    except configparser.NoOptionError:
        debug = False
    try:
        app_build_dir = config.get('core', 'app_build_dir')
    except configparser.NoOptionError:
        app_build_dir = '/tmp/app-manager/apps/'
    try:
        app_storage_dir = config.get('core', 'app_storage_dir')
    except configparser.NoOptionError:
        app_storage_dir = '~/.apps/'
    try:
        stop_apps_on_exit = config.getboolean('core', 'stop_apps_on_exit')
    except configparser.NoOptionError:
        stop_apps_on_exit = False
    try:
        keep_app_tarballls  = config.getboolean('core', 'keep_app_tarballls')
    except configparser.NoOptionError:
        keep_app_tarballls = False
    try:
        app_image_prefix = config.get('core', 'app_image_prefix')
    except configparser.NoOptionError:
        app_image_prefix = 'app-'
    ## -------------------------------------------------------------
    ## ----------------------- Broker Parameters -------------------
    ## -------------------------------------------------------------
    try:
        username = config.get('broker', 'username')
    except configparser.NoOptionError:
        username = 'bot'
    try:
        password = config.get('broker', 'password')
    except configparser.NoOptionError:
        password = 'b0t'
    try:
        host = config.get('broker', 'host')
    except configparser.NoOptionError:
        host = '127.0.0.1'
    try:
        port = config.get('broker', 'port')
    except configparser.NoOptionError:
        port = '5762'
    try:
        vhost = config.get('broker', 'vhost')
    except configparser.NoOptionError:
        vhost = '/'
    ## -------------------------------------------------------------
    ## ------------------ Control Interfaces -----------------------
    ## -------------------------------------------------------------
    try:
        app_list_rpc_name = config.get('control_interfaces',
                                       'app_list_rpc_name')
    except configparser.NoOptionError:
        app_list_rpc_name = 'thing.x.appmanager.apps'
    try:
        get_running_apps_rpc_name = config.get('control_interfaces',
                                               'get_running_apps_rpc_name')
    except configparser.NoOptionError:
        get_running_apps_rpc_name = 'thing.x.appmanager.apps.running'
    try:
        app_delete_rpc_name = config.get('control_interfaces',
                                         'app_delete_rpc_name')
    except configparser.NoOptionError:
        app_delete_rpc_name = 'thing.x.appmanager.delete_app'
    try:
        app_install_rpc_name = config.get('control_interfaces',
                                          'app_install_rpc_name')
    except configparser.NoOptionError:
        app_install_rpc_name = 'thing.x.appmanager.download_app'
    try:
        app_start_rpc_name = config.get('control_interfaces',
                                        'app_start_rpc_name')
    except configparser.NoOptionError:
        app_start_rpc_name = 'thing.x.appmanager.start_app'
    try:
        app_stop_rpc_name = config.get('control_interfaces',
                                       'app_stop_rpc_name')
    except configparser.NoOptionError:
        app_stop_rpc_name = 'thing.x.appmanager.stop_app'
    try:
        alive_rpc_name = config.get('control_interfaces',
                                    'alive_rpc_name')
    except configparser.NoOptionError:
        alive_rpc_name = 'thing.x.appmanager.is_alive'
    ## ------------------------------------------------------------
    ## -------------- Monitoring Interfaces -----------------------
    ## ------------------------------------------------------------
    try:
        heartbeat_topic = config.get('monitoring_interfaces',
                                     'heartbeat_topic')
    except configparser.NoOptionError:
        heartbeat_topic = 'thing.x.appmanager.hearbeat'
    try:
        heartbeat_interval = config.getint('monitoring_interfaces',
                                        'heartbeat_interval')
    except configparser.NoOptionError:
        heartbeat_interval = 10  # seconds
    try:
        connected_event = config.get('monitoring_interfaces',
                                     'connected_event')
    except configparser.NoOptionError:
        connected_event = 'thing.x.appmanager.connected'
    try:
        disconnected_event = config.get('monitoring_interfaces',
                                        'disconnected_event')
    except configparser.NoOptionError:
        disconnected_event = 'thing.x.appmanager.disconnected'
    ## ------------------------------------------------------------
    ## -------------- Application Interfaces ----------------------
    ## ------------------------------------------------------------
    try:
        app_started_event = config.get('app_interfaces', 'app_started_event')
    except configparser.NoOptionError:
        app_started_event = 'thing.x.app.y.started'
    try:
        app_stopped_event = config.get('app_interfaces', 'app_stopped_event')
    except configparser.NoOptionError:
        app_stopped_event = 'thing.x.app.y.stopped'
    try:
        app_logs_topic = config.get('app_interfaces', 'app_logs_topic')
    except configparser.NoOptionError:
        app_logs_topic = 'thing.x.app.y.logs'
    try:
        app_stats_topic = config.get('app_interfaces', 'app_stats_topic')
    except configparser.NoOptionError:
        app_stats_topic = 'thing.x.app.y.stats'
    try:
        publish_app_logs = config.getboolean('app_interfaces',
                                             'publish_app_logs')
    except configparser.NoOptionError:
        publish_app_logs = False
    try:
        publish_app_stats = config.getboolean('app_interfaces',
                                              'publish_app_stats')
    except configparser.NoOptionError:
        publish_app_stats = False
    ## ------------------------------------------------------------
    ## ------------------ Redis Parameters  -----------------------
    ## ------------------------------------------------------------
    try:
        redis_host = config.get('redis', 'host')
    except configparser.NoOptionError:
        redis_host = 'localhost'
    try:
        redis_port = config.getint('redis', 'port')
    except configparser.NoOptionError:
        redis_port = 6379
    try:
        redis_db = config.getint('redis', 'database')
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
        'app_build_dir': app_build_dir,
        'stop_apps_on_exit': stop_apps_on_exit,
        'keep_app_tarballls': keep_app_tarballls,
        'app_storage_dir': app_storage_dir,
        'app_image_prefix': app_image_prefix,
        'username': username,
        'password': password,
        'host': host,
        'port': port,
        'vhost': vhost,
        'heartbeat_interval': heartbeat_interval,
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
        'redis_app_list_name': redis_app_list_name,
        'app_started_event': app_started_event,
        'app_stopped_event': app_stopped_event,
        'app_logs_topic': app_logs_topic,
        'app_stats_topic': app_stats_topic,
        'publish_app_logs': publish_app_logs,
        'publish_app_stats': publish_app_stats
    }
