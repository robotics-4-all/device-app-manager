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
    try:
        single_app_mode = config.getboolean('core', 'single_app_mode')
    except configparser.NoOptionError:
        single_app_mode = True
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
        app_list_rpc_name = config.get('control',
                                       'app_list_rpc_name')
    except configparser.NoOptionError:
        app_list_rpc_name = 'apps'
    try:
        get_running_apps_rpc_name = config.get('control',
                                               'get_running_apps_rpc_name')
    except configparser.NoOptionError:
        get_running_apps_rpc_name = 'apps.running'
    try:
        app_delete_rpc_name = config.get('control', 'app_delete_rpc_name')
    except configparser.NoOptionError:
        app_delete_rpc_name = 'delete_app'
    try:
        app_install_rpc_name = config.get('control', 'app_install_rpc_name')
    except configparser.NoOptionError:
        app_install_rpc_name = 'install_app'
    try:
        app_start_rpc_name = config.get('control', 'app_start_rpc_name')
    except configparser.NoOptionError:
        app_start_rpc_name = 'start_app'
    try:
        app_stop_rpc_name = config.get('control', 'app_stop_rpc_name')
    except configparser.NoOptionError:
        app_stop_rpc_name = 'stop_app'
    try:
        alive_rpc_name = config.get('control', 'alive_rpc_name')
    except configparser.NoOptionError:
        alive_rpc_name = 'is_alive'
    try:
        fast_deploy_rpc_name = config.get('control', 'fast_deploy_rpc_name')
    except configparser.NoOptionError:
        fast_deploy_rpc_name = 'fast_deploy'
    ## ------------------------------------------------------------
    ## -------------- Monitoring Interfaces -----------------------
    ## ------------------------------------------------------------
    try:
        heartbeat_topic = config.get('monitoring', 'heartbeat_topic')
    except configparser.NoOptionError:
        heartbeat_topic = 'hearbeat'
    try:
        heartbeat_interval = config.getint('monitoring', 'heartbeat_interval')
    except configparser.NoOptionError:
        heartbeat_interval = 10  # seconds
    try:
        connected_event = config.get('monitoring', 'connected_event_name')
    except configparser.NoOptionError:
        connected_event = 'connected'
    try:
        disconnected_event = config.get('monitoring', 'disconnected_event_name')
    except configparser.NoOptionError:
        disconnected_event = 'disconnected'
    ## ------------------------------------------------------------
    ## -------------- Application Interfaces ----------------------
    ## ------------------------------------------------------------
    try:
        app_started_event_uri = config.get('applications', 'app_started_event')
    except configparser.NoOptionError:
        app_started_event_uri = 'app.{APP_ID}.started'
    try:
        app_stopped_event_uri = config.get('applications', 'app_stopped_event')
    except configparser.NoOptionError:
        app_stopped_event_uri = 'app.{APP_ID}.stopped'
    try:
        app_logs_topic = config.get('applications', 'app_logs_topic')
    except configparser.NoOptionError:
        app_logs_topic = 'app.y.logs'
    try:
        app_stats_topic = config.get('applications', 'app_stats_topic')
    except configparser.NoOptionError:
        app_stats_topic = 'app.y.stats'
    try:
        publish_app_logs = config.getboolean('applications',
                                             'publish_app_logs')
    except configparser.NoOptionError:
        publish_app_logs = False
    try:
        publish_app_stats = config.getboolean('applications',
                                              'publish_app_stats')
    except configparser.NoOptionError:
        publish_app_stats = False
    try:
        app_ui_storage_dir = config.get('applications', 'app_ui_storage_dir')
    except configparser.NoOptionError:
        app_ui_storage_dir = '~/.config/device_app_manager'
    finally:
        app_ui_storage_dir = os.path.expanduser(app_ui_storage_dir)
    ## ------------------------------------------------------------
    ## --------------- UI-Manager Parameters ----------------------
    ## ------------------------------------------------------------
    try:
        ui_start_rpc = config.get('custom_ui_handler', 'start_rpc')
    except configparser.NoOptionError:
        ui_start_rpc = 'ui.custom.start'
    try:
        ui_stop_rpc = config.get('custom_ui_handler', 'stop_rpc')
    except configparser.NoOptionError:
        ui_stop_rpc = 'ui.custom.stop'
    ## ------------------------------------------------------------
    ## ------------------ Rhasspy Parameters ----------------------
    ## ------------------------------------------------------------
    try:
        rhasspy_add_sentences_rpc = config.get('rhasspy',
                                               'add_sentences_rpc')
    except configparser.NoOptionError:
        rhasspy_add_sentences_rpc = 'rhasspy_manager.add_sentences'
    try:
        rhasspy_delete_intent_rpc = config.get('rhasspy',
                                               'delete_intent_rpc')
    except configparser.NoOptionError:
        rhasspy_delete_intent_rpc = 'rhasspy_manager.delete_intent'
    ## -----------------------------------------------------------------
    ## ------------------ Audio-Events Parameters ----------------------
    ## ----------------------------------------------------------------
    try:
        app_installed_event = config.getboolean('audio_events',
                                                'app_installed_event')
    except configparser.NoOptionError:
        app_installed_event = 1
    try:
        app_deleted_event = config.getboolean('audio_events',
                                              'app_deleted_event')
    except configparser.NoOptionError:
        app_deleted_event = 1
    try:
        speak_action_uri = config.get('audio_events', 'speak_action_uri')
    except configparser.NoOptionError:
        speak_action_uri = \
            '/robot/robot_1/actuator/audio/speaker/usb_speaker/d0/id_0/speak'
    try:
        sound_effects_dir = config.get('audio_events', 'sound_effects_dir')
    except configparser.NoOptionError:
        sound_effects_dir = \
            '~/.sound_effects'
    try:
        app_started_event = config.getboolean('audio_events',
                                              'app_started_event')
    except configparser.NoOptionError:
        app_started_event = 1
    try:
        app_termination_event = config.getboolean('audio_events',
                                                  'app_termination_event')
    except configparser.NoOptionError:
        app_termination_event = 1
    ## ------------------------------------------------------------
    ## ------------------ DB Parameters  -----------------------
    ## ------------------------------------------------------------
    try:
        db_type = config.get('db', 'type')
    except configparser.NoOptionError:
        db_type = 'redis'
    try:
        db_password = config.get('db', 'password')
    except configparser.NoOptionError:
        db_password = ''
    try:
        db_app_list_name = config.get('db', 'app_list_name')
    except configparser.NoOptionError:
        db_app_list_name = 'appmanager.apps'

    print(local_uri_namespace)

    return {
        'core': {
            'debug': debug,
            'app_build_dir': app_build_dir,
            'device_id': device_id,
            'stop_apps_on_exit': stop_apps_on_exit,
            'keep_app_tarballls': keep_app_tarballls,
            'app_storage_dir': app_storage_dir,
            'app_image_prefix': app_image_prefix,
            'uri_namespace': uri_namespace,
            'single_app_mode': single_app_mode
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
        'db': {
            'type': db_type,
            'password': db_password,
            'app_list_name': db_app_list_name,
        },
        'monitoring': {
            'heartbeat_interval': heartbeat_interval,
            'heartbeat_topic': heartbeat_topic,
            'connected_event': connected_event,
            'disconnected_event': disconnected_event,
        },
        'applications': {
            'app_started_event': app_started_event_uri,
            'app_stopped_event': app_stopped_event_uri,
            'app_logs_topic': app_logs_topic,
            'app_stats_topic': app_stats_topic,
            'publish_app_logs': publish_app_logs,
            'publish_app_stats': publish_app_stats,
            'app_ui_storage_dir': app_ui_storage_dir
        },
        'control': {
            'app_delete_rpc_name': app_delete_rpc_name,
            'app_list_rpc_name': app_list_rpc_name,
            'get_running_apps_rpc_name': get_running_apps_rpc_name,
            'app_install_rpc_name': app_install_rpc_name,
            'app_start_rpc_name': app_start_rpc_name,
            'app_stop_rpc_name': app_stop_rpc_name,
            'alive_rpc_name': alive_rpc_name,
            'fast_deploy_rpc_name': fast_deploy_rpc_name
        },
        'rhasspy': {
            'add_sentences_rpc': rhasspy_add_sentences_rpc,
            'delete_intent_rpc': rhasspy_delete_intent_rpc
        },
        'custom_ui_handler': {
            'start_rpc': ui_start_rpc,
            'stop_rpc': ui_stop_rpc
        },
        'audio_events': {
            'app_installed_event': app_installed_event,
            'app_deleted_event': app_deleted_event,
            'speak_action_uri': speak_action_uri,
            'sound_effects_dir': sound_effects_dir,
            'app_started_event': app_started_event,
            'app_termination_event': app_termination_event
        }
    }
