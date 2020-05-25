#!/usr/bin/env python

from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals
)

import sys
import os
import json
import argparse

from device_app_manager import AppManager, load_cfg


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

    ## Parameters passed from CLI are getting priority and override
    ## those defined in the configuration file
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

    print('==================== AppManager Configuration ====================')
    print(json.dumps(config, indent=4, sort_keys=True))
    print('==================================================================')

    manager = AppManager(
        platform_creds=(config['username'], config['password']),
        platform_host=config['host'],
        platform_port=config['port'],
        platform_vhost=config['vhost'],
        heartbeat_interval=config['heartbeat_interval'],
        heartbeat_topic=config['heartbeat_topic'],
        app_list_rpc_name=config['app_list_rpc_name'],
        app_delete_rpc_name=config['app_delete_rpc_name'],
        app_install_rpc_name=config['app_install_rpc_name'],
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
        debug=config['debug'],
        app_build_dir=config['app_build_dir'],
        app_image_prefix=config['app_image_prefix'],
        keep_app_tarballls=config['keep_app_tarballls'],
        app_storage_dir=config['app_storage_dir'],
        app_started_event=config['app_started_event'],
        app_stoped_event=config['app_stoped_event'],
        app_logs_topic=config['app_logs_topic'],
        app_stats_topic=config['app_logs_topic'],
        publish_app_logs=config['publish_app_logs'],
        publish_app_stats=config['publish_app_logs']
    )
    manager.run()


if __name__ == "__main__":
    main()
