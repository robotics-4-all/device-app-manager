#!/usr/bin/env python

import sys
import os
import json
import argparse

from device_app_manager import AppManager, load_cfg


def main():
    parser = argparse.ArgumentParser(description='Application Manager CLI')
    parser.add_argument('--config', dest='config',
                        help='Config file path',
                        default='~/.config/device_app_manager/config')
    # parser.add_argument('--debug', dest='debug',
    #                     help='Enable debugging',
    #                     type=bool,
    #                     const=True,
    #                     nargs='?')

    args = parser.parse_args()
    config_file = args.config
    # debug = args.debug

    config = load_cfg(config_file)

    ## Parameters passed from CLI are getting priority and override
    ## those defined in the configuration file

    print('==================== AppManager Configuration ====================')
    print(json.dumps(config, indent=4, sort_keys=True))
    print('==================================================================')

    manager = AppManager(
        config['platform_broker'],
        config['local_broker'],
        config['db'],
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
