#! /usr/bin/python3
# -*- encoding: utf-8 -*-

import sys
import logging
import argparse
from pathlib import Path

from . import __description__, __version__, LOG_LVLMAP

LOG = logging.getLogger('atgmlogger')


def parse_args(argv=None):
    """Parse arguments from commandline and load configuration file."""
    args = argv or sys.argv[1:]

    parser = argparse.ArgumentParser(prog="ATGMLogger", description=__description__,
                                     allow_abbrev=True)
    # Global Parser Arguments
    parser.add_argument('-V', '--version', action='version',
                        version=__version__)

    parser.add_argument('-v', '--verbose', action='count', default=0,
                        help="Enable verbose logging.")
    parser.add_argument('--debug', action='store_true',
                        help="Enable DEBUG level logging.")
    parser.add_argument('--trace', action='store_true',
                        help="Enable detailed trace info in log messages.")

    # Sub-Parser Groups
    sub_parsers = parser.add_subparsers(dest='command', help="Subcommands to run/install/uninstall ATGMLogger")

    run_parser = sub_parsers.add_parser('run', help='Run atgmlogger')
    run_parser.add_argument('-d', '--device', action='store',
                            help="Serial device path")
    run_parser.add_argument('-l', '--logdir', action='store')
    run_parser.add_argument('-m', '--mountdir', action='store',
                            help="Specify custom USB Storage mount path. "
                                 "Overrides path configured in configuration.")
    run_parser.add_argument('-c', '--config', action='store',
                            help="Specify path to custom JSON configuration.")
    run_parser.add_argument('--nogpio', action='store_true',
                            help="Disable GPIO output (LED notifications).")

    return parser.parse_args(args)


def initialize(args):
    """Initialize global application params and/or execute install/uninstall methods"""
    if args.debug:
        log_level = logging.DEBUG
        args.verbose = 5
    else:
        log_level = LOG_LVLMAP.get(args.verbose, logging.INFO)
    LOG.setLevel(log_level)

    # Set overrides from arguments
    from .runconfig import rcParams

    if args.config:
        # This must come first as it will re-initialize the configuration class
        LOG.info("Reloading rcParams with config file: %s", args.config)
        with Path(args.config).open('r') as fd:
            rcParams.load_config(fd)
    if args.device:
        rcParams['serial.port'] = args.device
    if args.logdir:
        rcParams['logging.logdir'] = args.logdir
        LOG.info("Updated logging directories, new datafile path: %s",
                 rcParams['logging.handlers.data_hdlr.filename'])
    if args.mountdir:
        rcParams['usb.mount'] = args.mountdir

    return args


def entry_point():
    args = initialize(parse_args())

    from .atgmlogger import atgmlogger

    sys.exit(atgmlogger(args))
