#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import os

os.system(f"./get_apps.py --device-id {sys.argv[1]} --host r4a-platform.ddns.net --port 5782 --vhost / --debug")
