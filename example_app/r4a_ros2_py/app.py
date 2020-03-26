#!/usr/bin/python
# -*- coding: utf-8 -*-
import sys
import os
import time

import yaml

from utilities import TekException
from utilities import Languages
from utilities import InputMessage
from utilities import Colors

from robot_api import RobotAPI


def read_init_params():
    params_file = 'init.conf'
    if not os.path.isfile(params_file):
        print('App params file <{}> does not exist'.format(params_file))
        sys.exit(1)
    with open(params_file, 'r') as stream:
        try:
            params = yaml.safe_load(stream)
            return params
        except yaml.YAMLError as exc:
            print(exc)
            sys.exit(1)
        except Exception as exc:
            print(exc)
            sys.exit(1)


def app_main(params=()):
    ## Here you write the application login, using the RobotAPI class
    ## to communicate with the robot/device
    """
    rapi = RobotAPI()

    rapi.speak(InputMessage({
        'texts': ['Καλημέρα Ελλάδα, καλημέρα Αθήνα'],
        'volume': 100,
        'language': Languages.EL
    }))

    rapi.speak(InputMessage({
        'texts': ['Τραβάω εικόνα'],
        'volume': 100,
        'language': Languages.EL
    }))

    out = rapi.captureImage(InputMessage({
        'width': 800,
        'height': 480,
        'save_file_url': None
    }))
    out.print()

    rapi.speak(InputMessage({
        'texts': ['Τώρα θα δείξω την εικόνα'],
        'volume': 100,
        'language': Languages.EL
    }))

    out = rapi.showImage(InputMessage({
        'image': out.data['image'],
        'width': out.data['width'],
        'height': out.data['height'],
        'duration': 10,
        'touch': True
    }))
    out.print()

    rapi.speak(InputMessage({
        'texts': ['Επίλεξε κάτι'],
        'volume': 100,
        'language': Languages.EL
    }))

    """


if __name__ == "__main__":
    app_params = read_init_params()
    try:
        app_main(app_params)
    except Exception as exc:
        print(exc)
        sys.exit(1)
