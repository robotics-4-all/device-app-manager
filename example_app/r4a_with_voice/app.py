# !/usr/bin/env python
# -*- coding: utf-8 -*-
import logging, os, sys, pathlib, requests
import base64
from os.path import expanduser
import socket

from r4a_apis.robot_api import RobotAPI
from r4a_apis.utilities import *
from commlib.logger import Logger

from google.cloud import texttospeech as tts
from google.cloud import speech



class ConversationApp:
    """ A conversational elsa app using a local rasa server """
    def __init__(self):

        self.log = Logger("testing")
        self.log.set_debug(True)
        self.rapi = RobotAPI(logger = self.log)
        InputMessage.logger = self.log
        OutputMessage.logger = self.log
        # TekException.logger = self.log

        # Rasa configuration for local mode
        # ip = '192.168.1.4'
        ip = "localhost"
        self.url = f"http://{ip}:5005/webhooks/rest/webhook"
        # ip = 'http://c115e00953e1.ngrok.io'
        # self.url = f"{ip}/webhooks/rest/webhook"
        self.username = 'me'

        # Google text to speech configuration
        path = os.path.abspath(os.path.dirname(__file__))
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = \
            path + "/elsa-277912-3dfe30a8f65b.json"

        self.tts_client = tts.TextToSpeechClient()

        self.audio_config = tts.AudioConfig(
            audio_encoding = tts.AudioEncoding.LINEAR16,
            sample_rate_hertz = 44100)

        self.voice = tts.VoiceSelectionParams(\
            language_code = 'el-GR',\
            ssml_gender = tts.SsmlVoiceGender.NEUTRAL)

        # Google speech to text configuration
        self.stt_client = speech.SpeechClient()

        self.speech_config = speech.RecognitionConfig(\
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,\
            sample_rate_hertz=44100,\
            language_code='el-GR')

        # Greet user
        # out = self.rapi.speak(InputMessage({
        #     'texts': ["Γεια σου, είμαι η Έλσα. Πώς θα μπορούσα να σε βοηθήσω;"],
        #     'volume': 80, # volume may be suppressed by the ELSA's global volume
        #     'language': Languages.EL # or Languages.EN for English
        # }))
        self.speak(text = "Γειά σου, είμαι η Έλσα! Πώς θα μπορούσα να σε βοηθήσω;")
        print("App started!")



    def speak(self, text = "default", filepath = "speak_file.wav"):
        """ Text to Speech function using Google API """
        file = os.path.join(os.path.expanduser("~"), filepath)
        print("Speaking...")

        # Call text to speech google api
        synthesis_input = tts.SynthesisInput(text = text)
        response = self.tts_client.synthesize_speech(input = synthesis_input, \
            voice = self.voice, audio_config = self.audio_config)
        # Save speech wav
        # record = base64.b64encode(response.audio_content).decode("ascii")
        with open(file, 'wb') as out:
            out.write(response.audio_content)
            print('Audio output from Google written')
        # Play wav
        self.rapi.replaySound(InputMessage({
            'is_file': True,
            'volume': 80,
            'string': file
        }))
        return


    def listen(self):
        """ Speech to Text function """
        file = os.path.join(expanduser("~"), "listen_command.wav")
        self.speak(text = "Σε ακούω")
        print("Listening...")
        # Record a sound and write it to file
        out = self.rapi.recordSound(InputMessage({
            'duration': 3,
            'name': 'testing',
            'save_file_url': file
        }))

        sound_str = out.data['record']
        audio = {'content': base64.b64decode(sound_str)}
        # Call google speech to text api
        text = self.stt_client.recognize(config = self.speech_config, audio = audio)
        if len(text.results):
            text = text.results[0].alternatives[0].transcript
        else:
            text = ''
        print(f"Text recorded: { text }")
        return text

    def nlu(self, text = '', metadata = ''):
        """ Connector with Rasa server """
        print("Connecting with rasa...")

        response = requests.post(self.url, json = {'sender': self.username, 'message': text})
        data = response.json()[0]['text']
        print(f"Rasa server's response: { data }")
        return data


print("Starting app...")
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = os.path.join(os.path.dirname(sys.argv[0]), 'elsa-277912-3dfe30a8f65b.json')
app = ConversationApp()

try:
    while True:
        text = app.listen()
        print(f"The user said: {text}")
        if text == '':
            app.speak(text = "Δεν κατάλαβα, μπορείς να επαναλάβεις;")
            continue
        response = app.nlu(text)
        filepath = "response_command.wav"
        app.speak(text = response, filepath = filepath)
        if response == 'Αντίο':
            app.speak(text = "Καλή συνέχεια! Αντίο!")
            break

except Exception as e:
    print(e)
