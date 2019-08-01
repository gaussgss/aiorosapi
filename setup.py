#!/usr/bin/env python3
# -+- coding: utf-8 -+-

from setuptools import setup, find_packages
from os.path import join, dirname
import aiorosapi

setup(
    name='aiorosapi',
    version=aiorosapi.__version__,

    author="Andrey Gusev",
    author_email="gaussgss@gmail.com",
    url="https://github.com/gaussgss/aiorosapi",

    long_description=open(join(dirname(__file__), 'README.md')).read(),
    long_description_content_type="text/markdown",

    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],

    packages=find_packages(exclude=["tests"]),
    test_suite='tests'
)
