#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import os

os.system(f"./install_app.py --device-id {sys.argv[1]} --host 155.207.33.189 --port 5782 --vhost / --debug --fpath {sys.argv[2]} --app-type r4a_commlib --app-id {sys.argv[3]}")
