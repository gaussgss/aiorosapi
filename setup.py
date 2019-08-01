#!/usr/bin/env python3
# -+- coding: utf-8 -+-

from setuptools import setup, find_packages
from os.path import join, dirname
import aiorosapi

setup(
    name='aiorosapi',
    version=aiorosapi.__version__,
    packages=find_packages(),
    long_description=open(join(dirname(__file__), 'README.md')).read(),

    test_suite='tests'
)
