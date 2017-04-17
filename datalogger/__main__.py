# coding=utf-8

import sys
import argparse

from datalogger.runner import run

def get_version():
    return 0.1


def main(argv=None):
    """Main entry point for DGSlogger. Called from __main__"""
    if argv is None:
        argv = sys.argv[1:]
    print('Running main with args: {}'.format(argv))

    parser = argparse.ArgumentParser(prog="DGSLogger", description="Run DGSLogger")
    parser.add_argument('-V', '--version', action='version',
                        version='DGS Logger version {}'.format(get_version()))
    parser.add_argument('-v', '--verbose', action='count')
    parser.add_argument('--install', action='store_true',
                        help='Install systemd unit script')
    parser.add_argument('-s', '--start', action='store_true')
    options = parser.parse_args(argv)

    if options.install:
        return True

    if options.start:
        return run()


sys.exit(main(['--start', '-vv']))
