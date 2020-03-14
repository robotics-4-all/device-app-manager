#!/usr/bin/python
# -*- coding: utf-8 -*-
import sys
import os
import time

from utilities import TekException
from utilities import Languages
from utilities import InputMessage
from utilities import Colors

from robot_api import RobotAPI

try:
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

    out = rapi.showOptions(InputMessage({
        'options': ['Kalimera Ellada', 'Kalimera Athina'],
        'duration': 5
    }))
    out.print()

    rapi.speak(InputMessage({
        'texts': ['Στάσου, πράσινο'],
        'volume': 100,
        'language': Languages.EL
    }))

    out = rapi.showColor(InputMessage({
        'color': Colors.GREEN.value,
        'duration': 5
    }))
    out.print()

    rapi.speak(InputMessage({
        'texts': ['Θα ηχογραφήσω κάτι. Πώς σε λενε;'],
        'volume': 100,
        'language': Languages.EL
    }))

    out = rapi.recordSound(InputMessage({
        'name': 'test_sound_1',
        'duration': 3,
        'save_file_url': '/tmp/tmp.wav'
    }))
    sound_str = out.data['record']

    rapi.speak(InputMessage({
        'texts': ['Η απάντηση της ηχογράφησης είναι'],
        'volume': 100,
        'language': Languages.EL
    }))

    out = rapi.replaySound(InputMessage({
        'is_file': False,
        'string': sound_str,
        'volume': 100
    }))
    out.print()

    rapi.speak(InputMessage({
        'texts': ['Το αρχείο που αποθηκεύτηκε είναι'],
        'volume': 100,
        'language': Languages.EL
    }))

    out = rapi.replaySound(InputMessage({
        'is_file': True,
        'string': '/tmp/tmp.wav',
        'volume': 100
    }))
    out.print()

except TekException:
    pass
