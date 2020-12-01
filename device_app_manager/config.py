import os
import configparser


def load_cfg(cfg_file):
    cfg_file = os.path.expanduser(cfg_file)
    if not os.path.isfile(cfg_file):
        print(f'Config file <{cfg_file}> does not exist')
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
    finally:
        app_storage_dir = os.path.expanduser(app_storage_dir)
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
    try:
        uri_namespace = config.get('core', 'uri_namespace')
    except configparser.NoOptionError:
        uri_namespace = 'app_manager'
    try:
        device_id = config.get('core', 'device_id')
    except configparser.NoOptionError:
        device_id = 'device0'
    ## -------------------------------------------------------------
    ## ----------------------- Platform Broker Parameters -------------------
    ## -------------------------------------------------------------
    try:
        platform_broker_type = config.get('platform_broker', 'type')
    except configparser.NoOptionError:
        platform_broker_type = 'AMQP'
    try:
        platform_broker_host = config.get('platform_broker', 'host')
    except configparser.NoOptionError:
        platform_broker_host = '127.0.0.1'
    try:
        platform_broker_port = config.get('platform_broker', 'port')
    except configparser.NoOptionError:
        platform_broker_port = '5762'
    try:
        platform_broker_vhost = config.get('platform_broker', 'vhost')
    except configparser.NoOptionError:
        platform_broker_vhost = '/'
    try:
        platform_broker_db = config.get('platform_broker', 'db')
    except configparser.NoOptionError:
        platform_broker_db = 0
    try:
        platform_broker_username = config.get('platform_broker', 'username')
    except configparser.NoOptionError:
        platform_broker_username = 'bot'
    try:
        platform_broker_password = config.get('platform_broker', 'password')
    except configparser.NoOptionError:
        platform_broker_password = 'b0t'
    try:
        platform_uri_namespace = config.get('platform_broker', 'uri_namespace')
    except configparser.NoOptionError:
        platform_uri_namespace = 'thing.{DEVICE_ID}'
    try:
        platform_logging = config.get('platform_broker', 'logging')
    except configparser.NoOptionError:
        platform_logging = 0
    ## ------------------------------------------------------------------------
    ## ----------------------- Local Broker Parameters -------------
    ## ------------------------------------------------------------------------
    try:
        local_broker_username = config.get('local_broker', 'username')
    except configparser.NoOptionError:
        local_broker_username = ''
    try:
        local_broker_password = config.get('local_broker', 'password')
    except configparser.NoOptionError:
        local_broker_password = ''
    try:
        local_broker_host = config.get('local_broker', 'host')
    except configparser.NoOptionError:
        local_broker_host = 'localhost'
    try:
        local_broker_port = config.get('local_broker', 'port')
    except configparser.NoOptionError:
        local_broker_port = '6379'
    try:
        local_broker_type = config.get('local_broker', 'type')
    except configparser.NoOptionError:
        local_broker_type = 'REDIS'
    try:
        local_broker_vhost = config.get('local_broker', 'vhost')
    except configparser.NoOptionError:
        local_broker_vhost = '/'
    try:
        local_broker_db = config.get('local_broker', 'db')
    except configparser.NoOptionError:
        local_broker_db = 0
    try:
        local_uri_namespace = config.get('local_broker', 'uri_namespace')
    except configparser.NoOptionError:
        local_uri_namespace = ''
    try:
        local_logging = config.get('local_broker', 'logging')
    except configparser.NoOptionError:
        local_logging = 0
    ## ------------------------------------------------------------------------
    ## ------------------ Control Interfaces -----------------------
    ## ------------------------------------------------------------------------
    try:
        app_list_rpc_name = config.get('control_interfaces',
                                       'app_list_rpc_name')
    except configparser.NoOptionError:
        app_list_rpc_name = 'thing.{DEVICE_ID}.appmanager.apps'
    try:
        get_running_apps_rpc_name = config.get('control_interfaces',
                                               'get_running_apps_rpc_name')
    except configparser.NoOptionError:
        get_running_apps_rpc_name = 'thing.{DEVICE_ID}.appmanager.apps.running'
    try:
        app_delete_rpc_name = config.get('control_interfaces',
                                         'app_delete_rpc_name')
    except configparser.NoOptionError:
        app_delete_rpc_name = 'thing.{DEVICE_ID}.appmanager.delete_app'
    try:
        app_install_rpc_name = config.get('control_interfaces',
                                          'app_install_rpc_name')
    except configparser.NoOptionError:
        app_install_rpc_name = 'thing.{DEVICE_ID}.appmanager.download_app'
    try:
        app_start_rpc_name = config.get('control_interfaces',
                                        'app_start_rpc_name')
    except configparser.NoOptionError:
        app_start_rpc_name = 'thing.{DEVICE_ID}.appmanager.start_app'
    try:
        app_stop_rpc_name = config.get('control_interfaces',
                                       'app_stop_rpc_name')
    except configparser.NoOptionError:
        app_stop_rpc_name = 'thing.{DEVICE_ID}.appmanager.stop_app'
    try:
        alive_rpc_name = config.get('control_interfaces',
                                    'alive_rpc_name')
    except configparser.NoOptionError:
        alive_rpc_name = 'thing.{DEVICE_ID}.appmanager.is_alive'
    ## ------------------------------------------------------------
    ## -------------- Monitoring Interfaces -----------------------
    ## ------------------------------------------------------------
    try:
        heartbeat_topic = config.get('monitoring_interfaces',
                                     'heartbeat_topic')
    except configparser.NoOptionError:
        heartbeat_topic = 'thing.{DEVICE_ID}.appmanager.hearbeat'
    try:
        heartbeat_interval = config.getint('monitoring_interfaces',
                                        'heartbeat_interval')
    except configparser.NoOptionError:
        heartbeat_interval = 10  # seconds
    try:
        connected_event = config.get('monitoring_interfaces',
                                     'connected_event')
    except configparser.NoOptionError:
        connected_event = 'thing.{DEVICE_ID}.appmanager.connected'
    try:
        disconnected_event = config.get('monitoring_interfaces',
                                        'disconnected_event')
    except configparser.NoOptionError:
        disconnected_event = 'thing.{DEVICE_ID}.appmanager.disconnected'
    ## ------------------------------------------------------------
    ## -------------- Application Interfaces ----------------------
    ## ------------------------------------------------------------
    try:
        app_started_event = config.get('app_interfaces', 'app_started_event')
    except configparser.NoOptionError:
        app_started_event = 'thing.{DEVICE_ID}.app.y.started'
    try:
        app_stopped_event = config.get('app_interfaces', 'app_stopped_event')
    except configparser.NoOptionError:
        app_stopped_event = 'thing.{DEVICE_ID}.app.y.stopped'
    try:
        app_logs_topic = config.get('app_interfaces', 'app_logs_topic')
    except configparser.NoOptionError:
        app_logs_topic = 'thing.{DEVICE_ID}.app.y.logs'
    try:
        app_stats_topic = config.get('app_interfaces', 'app_stats_topic')
    except configparser.NoOptionError:
        app_stats_topic = 'thing.{DEVICE_ID}.app.y.stats'
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
        'core': {
            'debug': debug,
            'app_build_dir': app_build_dir,
            'device_id': device_id,
            'stop_apps_on_exit': stop_apps_on_exit,
            'keep_app_tarballls': keep_app_tarballls,
            'app_storage_dir': app_storage_dir,
            'app_image_prefix': app_image_prefix,
            'uri_namespace': uri_namespace
        },
        'platform_broker': {
            'type': platform_broker_type,
            'uri_namespace': platform_uri_namespace,
            'logging': platform_logging,
            'username': platform_broker_username,
            'password': platform_broker_password,
            'host': platform_broker_host,
            'port': platform_broker_port,
            'vhost': platform_broker_vhost,
            'db': platform_broker_db
        },
        'local_broker': {
            'type': local_broker_type,
            'uri_namespace': local_uri_namespace,
            'logging': local_logging,
            'username': local_broker_username,
            'password': local_broker_password,
            'host': local_broker_host,
            'port': local_broker_port,
            'vhost': local_broker_vhost,
            'db': local_broker_db
        },
        'redis': {
            'host': redis_host,
            'port': redis_port,
            'db': redis_db,
            'password': redis_password,
            'app_list_name': redis_app_list_name,
        },
        'monitoring_interfaces': {
            'heartbeat_interval': heartbeat_interval,
            'heartbeat_topic': heartbeat_topic,
            'connected_event': connected_event,
            'disconnected_event': disconnected_event,
        },
        'app_interfaces': {
            'app_started_event': app_started_event,
            'app_stopped_event': app_stopped_event,
            'app_logs_topic': app_logs_topic,
            'app_stats_topic': app_stats_topic,
            'publish_app_logs': publish_app_logs,
            'publish_app_stats': publish_app_stats
        },
        'control_interfaces': {
            'app_delete_rpc_name': app_delete_rpc_name,
            'app_list_rpc_name': app_list_rpc_name,
            'get_running_apps_rpc_name': get_running_apps_rpc_name,
            'app_install_rpc_name': app_install_rpc_name,
            'app_start_rpc_name': app_start_rpc_name,
            'app_stop_rpc_name': app_stop_rpc_name,
            'alive_rpc_name': alive_rpc_name
        }
    }
