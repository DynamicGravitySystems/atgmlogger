# -*- coding: utf-8 -*-

import sys
import shlex
import logging
import argparse
import datetime
import itertools
import subprocess
from typing import Union
from pathlib import Path

from . import *

__all__ = ['parse_args', 'decode', 'convert_gps_time', 'timestamp_from_data',
           'set_system_time', 'Blink', 'Command']

ILLEGAL_CHARS = list(itertools.chain(range(0, 32), [255]))


def parse_args(argv=None):
    """Parse arguments from commandline and load configuration file."""

    parser = argparse.ArgumentParser(description=__description__)
    parser.add_argument('-V', '--version', action='version',
                        version=__version__)
    parser.add_argument('-v', '--verbose', action='count', default=0,
                        help="Enable verbose logging.")
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

    if args.install:
        try:
            from . import install
            install.install()
        except (ImportError, OSError):
            APPLOG.exception("Exception occurred trying to install system "
                             "files.")
    elif args.uninstall:
        try:
            from . import install
            install.uninstall()
        except (ImportError, OSError):
            APPLOG.exception("Exception occurred uninstalling system files.")

    log_level = VERBOSITY_MAP.get(args.verbose, logging.DEBUG)
    APPLOG.setLevel(log_level)

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


def decode(bytearr, encoding='utf-8'):
    if isinstance(bytearr, str):
        return bytearr
    try:
        raw = bytes([c for c in bytearr if c not in ILLEGAL_CHARS])
        decoded = raw.decode(encoding, errors='ignore').strip('\r\n')
    except AttributeError:
        decoded = None
    return decoded


def convert_gps_time(gpsweek: int, gpsweekseconds: float) -> float:
    """
    Converts a GPS time format (weeks + seconds since 6 Jan 1980) to a UNIX
    timestamp (seconds since 1 Jan 1970) without correcting for UTC leap
    seconds.

    Simplified method from DynamicGravityProcessor application:
    https://github.com/DynamicGravitySystems/DGP

    Notes
    -----
    GPS time begins 1980 Jan 6 00:00, UNIX time begins 1970 Jan 1 00:00

    Static values gps_delta and gpsweek_cf are defined by the below functions
    (optimization)
    gps_delta is the time difference (in seconds) between UNIX time and GPS time
    gps_delta = (dt.datetime(1980,1,6) - dt.datetime(1970,1,1)).total_seconds()

    gpsweek_cf is the coefficient to convert weeks to seconds
    gpsweek_cf = 7 * 24 * 60 * 60  # 604800

    Attributes
    ----------
    gpsweek: Number of weeks since beginning of GPS time
        (1980-01-06 00:00:00)
    gpsweekseconds: Number of seconds since the GPS week parameter

    Returns
    -------
    float : unix timestamp
        number of seconds since 1970-01-01 00:00:00

    """
    # TODO: Consider UTC/GPS leap seconds?
    gps_delta = 315964800.0
    gpsweek_cf = 604800

    try:
        gps_ticks = float(int(gpsweek) * gpsweek_cf) + float(gpsweekseconds)
    except TypeError:
        return 0

    timestamp = gps_delta + gps_ticks
    return timestamp


def timestamp_from_data(line) -> Union[float, None]:
    """Extract and convert to a UNIX style timestamp from a raw line of data.
    Supports extraction and conversion from DGS AT1A and AT1M (Airborne/Marine)
    raw serial outputs.

    Returns
    -------
    float : timestamp
        UNIX timestamp from data line, or None if conversion/formatting failed

    """
    # TODO: Consider using regex for more accurate testing?
    fields = line.split(',')
    if len(fields) == 13:
        # Airborne RAW Data w/ GPS Week/GPS Second
        week = int(fields[11])
        seconds = float(fields[12])
        if week == 0:
            return None
        return convert_gps_time(week, seconds)

    elif len(fields) == 19:
        # Marine RAW Data w/ date in last column
        # Format e.g. 20171117202136
        #             YYYYMMDDHHmmss
        date = str(fields[18])
        fmt = "%Y%m%d%H%M%S"
        try:
            timestamp = datetime.datetime.strptime(date, fmt).timestamp()
        except ValueError:
            return None
        else:
            return timestamp
    else:
        return None


def set_system_time(timestamp):
    if POSIX:
        cmd = 'date +%s -s @{ts}'.format(ts=timestamp)
        output = subprocess.check_output(shlex.split(cmd)).decode('utf-8')
        return output
    else:
        APPLOG.info("set_system_time not supported on this platform.")
        return None


class Blink:
    def __init__(self, led, priority=5, frequency=0.1):
        self.led = led
        self.priority = priority
        self.frequency = frequency

    def __lt__(self, other):
        return self.priority < other.priority


class Command:
    def __init__(self, cmd, **params):
        self.cmd = cmd
        self.params = params
