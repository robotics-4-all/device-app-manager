#!/usr/bin/python
# -*- coding: utf-8 -*-
import sys
import os
import logging

from r4a_apis.utilities import *
from r4a_apis.tek_nodes import *

from r4a_apis.robot_api import RobotAPI
from r4a_apis.cloud_api import CloudAPI
from r4a_apis.generic_api import GenericAPI

try:
	log = Logger(allow_cutelog = True, level = logging.INFO)
	TekNode.logger = log
	TekNode.robot_api = RobotAPI(logger = log)
	TekNode.cloud_api = CloudAPI(memory = TekNode.robot_api.memory, logger = log)
	TekNode.generic_api = GenericAPI(memory = TekNode.robot_api.memory, logger = log)
	Condition.memory = TekNode.robot_api.memory
	Condition.logger = log
	InputMessage.logger = log
	OutputMessage.logger = log
	TekException.logger = log
	NodeExecutor.logger = log
	log.debug('main', "Hey, app is starting")

	nodes = {}
	nodes[0] = StartTekNode(0)
	nodes[1] = RobotMotionTekNode(1)
	nodes[1].setParameters(distance = None, duration = 5.0, direction = Directions.FORWARDS, speed = 0.2, type = MotionType.BASIC)
	nodes[2] = RobotTurnTekNode(2)
	nodes[2].setParameters(type = MotionType.BASIC, direction = Directions.RIGHT)
	nodes[3] = CameraMotionTekNode(3)
	nodes[3].setParameters(direction =  Directions.NEUTRAL, yaw = None, pitch = None)
	nodes[4] = TalkTekNode(4)
	nodes[4].setParameters(language = Languages.EL, texts = ["Γεια σου"], volume = 100)
	nodes[5] = RecordSoundTekNode(5)
	nodes[5].setParameters(name = "Sound", duration = 5.0)
	nodes[6] = ReplaySoundTekNode(6)
	nodes[6].setParameters(name = "Sound", volume = 100)
	nodes[7] = TurnLedsOnTekNode(7)
	nodes[7].setParameters(brightness = 100, color = Colors.WHITE)
	nodes[8] = TurnLedsOffTekNode(8)
	nodes[9] = StopTekNode(9)

	# Conditions


	# Transitions
	nodes[0].setNextNode(id = 1)
	nodes[1].setNextNode(id = 2)
	nodes[2].setNextNode(id = 3)
	nodes[3].setNextNode(id = 4)
	nodes[4].setNextNode(id = 5)
	nodes[5].setNextNode(id = 6)
	nodes[6].setNextNode(id = 7)
	nodes[7].setNextNode(id = 8)
	nodes[8].setNextNode(id = 9)

	# Main execution
	main_executor = NodeExecutor(exe_id = 0)
	for i in nodes:
		main_executor.addNode(id = i, node = nodes[i])
	main_executor.setStartingNode(id = 0)

	# Go for it
	main_executor.execute()
	log.debug('main', "App is done")

except TekException:
	pass
