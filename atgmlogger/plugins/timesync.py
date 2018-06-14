# -*- coding: utf-8 -*-
# This file is part of ATGMLogger https://github.com/bradyzp/atgmlogger

import shlex
import time
import datetime
import logging
import subprocess
from typing import Union

from . import PluginDaemon
from atgmlogger import POSIX

__plugin__ = 'TimeSyncDaemon'
LOG = logging.getLogger(__name__)


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
        LOG.info("set_system_time not supported on this platform.")
        return None


class TimeSyncDaemon(PluginDaemon):
    options = ['interval', 'timetravel']
    interval = 1000
    _tick = -1
    timetravel = False

    @classmethod
    def condition(cls, item=None):
        if not isinstance(item, str):
            return False
        cls._tick += 1
        return cls._tick % cls.interval == 0

    @classmethod
    def reset_tick(cls):
        cls._tick = 0

    def _valid_time(self, timestamp):
        if not self.timetravel and timestamp > time.time():
            LOG.debug("Timestamp is valid, {ts} > {now}".format(
                ts=timestamp, now=time.time()))
            return True
        else:
            return False

    def run(self):
        if not self.data:
            raise ValueError("TimeSyncDaemon has no data set.")
        try:
            self.reset_tick()
            ts = timestamp_from_data(self.data)
            if ts is not None and self._valid_time(ts):
                set_system_time(ts)
            else:
                pass
        except ValueError:
            pass

