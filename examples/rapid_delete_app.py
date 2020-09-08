#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import os

os.system(f"./delete_app.py --device-id {sys.argv[1]} --host 155.207.33.189 --port 5782 --vhost / --debug --app-id {sys.argv[2]}")
