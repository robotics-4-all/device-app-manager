#!/usr/bin/env python

import os
try:
    from setuptools import setup, find_packages
except ImportError:
    from distutils.core import setup, find_packages


# Utility function to read the README file.
# Used for the long_description.  It's nice, because now
#   1) we have a top level README file
#   2) it's easier to type in the README file than to put a raw string in below
def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()


setup(
    package_data={'': ['*.tpl']}
)
