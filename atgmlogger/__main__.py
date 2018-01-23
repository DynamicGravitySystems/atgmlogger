#! /usr/bin/python3
# -*- encoding: utf-8 -*-

import sys
from .atgmlogger import run


def main(*args):
    if args is None:
        args = sys.argv

    return run(*args)
