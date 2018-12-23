#! /usr/bin/python3
# -*- encoding: utf-8 -*-

import sys
import logging
import argparse
from pathlib import Path

from . import __description__, __version__, LOG_LVLMAP, LOG_FMT, DATE_FMT, TRACE_LOG_FMT

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

    install_parser = sub_parsers.add_parser('install', help='Install system files for ATGMLogger', allow_abbrev=True)
    install_parser.add_argument('--service', action='store_true', default=True, help='Install ATGMLogger as a Systemd '
                                                                                     'Service')
    install_parser.add_argument('--dependencies', action='store_true', help='Install system dependencies using apt.')
    install_parser.add_argument('--configure', action='store_true', help='Run RaspberryPi configuration scripts.')
    install_parser.add_argument('--check-install', action='store_true', help='Verify installed components.')
    install_parser.add_argument('--logrotate', action='store_true', default=True, help='Install logrotate '
                                                                                       'configuration')
    install_parser.add_argument('--with-mqtt', action='store_true', help='Install MQTT plugin configuration and AWS '
                                                                         'IoT dependencies')

    uninst_parser = sub_parsers.add_parser('uninstall', help='Uninstall ATGMLogger system files and configurations')
    uninst_parser.add_argument('--keep-config', action='store_true', help='Retain configuration after uninstalling '
                                                                          'ATGMLogger')

    chkinst_parser = sub_parsers.add_parser('chkinstall', help="Check ATGMLogger installation and depdendencies")

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

    # This fails if we specify global positional args before the command
    # if args[0].lower() not in ['install', 'uninstall', 'run']:
    #     args.insert(0, 'run')
    return parser.parse_args(args)


def _configure_applog(log_format, logdir):
    logdir = Path(logdir)
    if not logdir.exists():
        try:
            logdir.mkdir(parents=True, mode=0o750)
        except (FileNotFoundError, OSError):
            LOG.warning("Log directory could not be created, log "
                        "files will be output to current directory (%s).",
                        str(Path().resolve()))
            logdir = Path()

    from logging.handlers import WatchedFileHandler

    applog_hdlr = WatchedFileHandler(str(logdir.joinpath('application.log')),
                                     encoding='utf-8')
    applog_hdlr.setFormatter(logging.Formatter(log_format, datefmt=DATE_FMT))
    LOG.addHandler(applog_hdlr)
    LOG.debug("Application log configured, log path: %s", str(logdir))


def initialize(args):
    """Initialize global application params and/or execute install/uninstall methods"""
    if args.debug:
        log_level = logging.DEBUG
        args.verbose = 5
    else:
        log_level = LOG_LVLMAP.get(args.verbose, logging.INFO)
    LOG.setLevel(log_level)

    if args.command in {'install', 'uninstall', 'chkinstall'}:
        from . import install
        method = getattr(install, args.command, None)
        if method is None:
            LOG.error("Command %s is not implemented", args.command)
            sys.exit(1)
        sys.exit(method(args))

    # if args.command == 'install':
    #     try:
    #         from .install import install
    #         sys.exit(install(args))
    #     except (ImportError, OSError):
    #         LOG.exception("Exception occurred trying to install system "
    #                       "files.")
    #         sys.exit(1)
    # elif args.command == 'uninstall':
    #     try:
    #         from .install import uninstall
    #         sys.exit(uninstall(args))
    #     except (ImportError, OSError):
    #         LOG.exception("Exception occurred uninstalling system files.")
    # elif args.command == 'chkinstall':
    #     try:
    #         from .install import chkinstall
    #         sys.exit(chkinstall(args))
    #
    #     except (ImportError, OSError):
    #         pass

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
                 rcParams['logging.logdir'])
    if args.mountdir:
        rcParams['usb.mount'] = args.mountdir

    # Configure Root Application Logger
    if args.trace:
        _configure_applog(TRACE_LOG_FMT, rcParams['logging.logdir'])
    else:
        _configure_applog(LOG_FMT, rcParams['logging.logdir'])

    return args


def entry_point():
    args = initialize(parse_args())

    from .atgmlogger import atgmlogger

    sys.exit(atgmlogger(args))


if __name__ == '__main__':
    entry_point()
