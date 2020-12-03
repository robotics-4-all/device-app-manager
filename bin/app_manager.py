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
        config['platform_broker']['username'] = username
    if password is not None:
        config['platform_broker']['password'] = password
    if host is not None:
        config['platform_broker']['host'] = host
    if port is not None:
        config['platform_broker']['port'] = port
    if vhost is not None:
        config['platform_broker']['vhost'] = vhost
    if heartbeat is not None:
        config['heartbeat_interval'] = heartbeat

    print('==================== AppManager Configuration ====================')
    print(json.dumps(config, indent=4, sort_keys=True))
    print('==================================================================')

    manager = AppManager(
        config['platform_broker'],
        config['local_broker'],
        config['redis'],
        config['core'],
        config['monitoring'],
        config['applications'],
        config['control'],
        config['rhasspy'],
        config['custom_ui_handler'],
        config['audio_events']
    )
    try:
        manager.run()
    except Exception as exc:
        print(exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
