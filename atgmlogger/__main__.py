#! /usr/bin/python3
# -*- encoding: utf-8 -*-

import sys
import logging
import argparse
from pathlib import Path

from . import *


def parse_args(argv=None):
    """Parse arguments from commandline and load configuration file.
    TODO: Consider, should this function change global state, or simply parse
    arguments and pass them on to atgmlogger (main caller) to operate on?
    """

    parser = argparse.ArgumentParser(description=__description__)
    parser.add_argument('-V', '--version', action='version',
                        version=__version__)
    parser.add_argument('-v', '--verbose', action='count', default=0,
                        help="Enable verbose logging.")
    parser.add_argument('--debug', action='store_true',
                        help="Enable DEBUG level logging.")
    parser.add_argument('-d', '--device', action='store',
                        help="Serial device path")
    parser.add_argument('-l', '--logdir', action='store')
    parser.add_argument('-m', '--mountdir', action='store',
                        help="Specify custom USB Storage mount path. "
                             "Overrides path configured in configuration.")
    parser.add_argument('-c', '--config', action='store',
                        help="Specify path to custom JSON configuration.")
    parser.add_argument('--nogpio', action='store_true',
                        help="Disable GPIO output (LED notifications).")
    parser.add_argument('--install', action='store_true',
                        help="Install/verify system components and systemd "
                             "configuration.")
    parser.add_argument('--uninstall', action='store_true',
                        help="Uninstall module configurations and systemd "
                             "unit scripts.")

    if argv is not None:
        args = parser.parse_args(argv[1:])
    else:
        args = parser.parse_args()

    if args.debug:
        log_level = logging.DEBUG
    else:
        log_level = LOG_LVLMAP.get(args.verbose, logging.INFO)
    APPLOG.setLevel(log_level)

    if args.install:
        try:
            from . import install
            sys.exit(install.install(args.verbose > 0 or args.debug))
        except (ImportError, OSError):
            APPLOG.exception("Exception occurred trying to install system "
                             "files.")
            sys.exit(1)
    elif args.uninstall:
        try:
            from . import install
            sys.exit(install.uninstall(args.verbose > 0 or args.debug))
        except (ImportError, OSError):
            APPLOG.exception("Exception occurred uninstalling system files.")

    # Set overrides from arguments
    from .runconfig import rcParams
    if args.config:
        # This must come first as it will re-initialize the configuration class
        APPLOG.info("Reloading rcParams with config file: %s", args.config)
        with Path(args.config).open('r') as fd:
            rcParams.load_config(fd)
    if args.device:
        rcParams['serial.port'] = args.device
    if args.logdir:
        rcParams['logging.logdir'] = args.logdir
        APPLOG.info("Updated logging directories, new datafile path: %s",
                    rcParams['logging.handlers.data_hdlr.filename'])
    if args.mountdir:
        rcParams['usb.mount'] = args.mountdir

    return args


def entry_point():
    args = parse_args()

    from .atgmlogger import atgmlogger
    sys.exit(atgmlogger(args))


entry_point()
