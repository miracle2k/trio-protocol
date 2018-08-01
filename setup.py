#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import re
import sys
from setuptools import setup


def get_long_description():
    """
    Return the README.
    """
    return open('README.md', 'r').read()


def get_packages(package):
    """
    Return root package and all sub-packages.
    """
    return [dirpath
            for dirpath, dirnames, filenames in os.walk(package)
            if os.path.exists(os.path.join(dirpath, '__init__.py'))]


setup(
    name='trio-protocol',
    version='0.2',
    url='https://github.com/miracle2k/trio-protocol',
    license='BSD',
    description='Trio implementation of asyncio.Protocol',
    long_description=get_long_description(),
    long_description_content_type='text/markdown',
    author='Michael Elsdorfer',
    author_email='michael@elsdorfer.com',
    packages=get_packages('trio_protocol'),
    install_requires=[        
    ],
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Topic :: Internet :: WWW/HTTP',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
    ]    
)
