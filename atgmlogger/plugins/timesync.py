# -*- coding: utf-8 -*-

import shlex
import time
import datetime
import subprocess
from typing import Union

from . import PluginInterface
from .. import APPLOG, POSIX

__plugin__ = 'TimeSyncSleeper'


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


class TimeSync(PluginInterface):
    options = ['interval', 'timetravel']
    oneshot = True
    _tick = -1
    interval = 10000
    timetravel = False  # Allow system time to be set to a date in the past

    @classmethod
    def condition(cls, line):
        cls._tick += 1
        return cls._tick % cls.interval == 0

    @staticmethod
    def consumer_type():
        return {str}

    def __init__(self):
        super().__init__()

    def run(self):
        data = self.get(block=True, timeout=None)
        try:
            APPLOG.debug("Trying to set system time from data.")
            ts = timestamp_from_data(data)
            if ts is not None:
                if not self.timetravel and (ts > datetime.datetime.now()
                                            .timestamp()):
                    set_system_time(ts)
                else:
                    APPLOG.warning("Timestamp from meter is in the past: "
                                   "%.2f", ts)
            else:
                APPLOG.debug("Timestamp could not be extracted from data.")
                raise ValueError("Invalid System Time Specified")
        except ValueError:  # TODO: Be more specific
            pass
        else:
            APPLOG.debug("System time set to: %.2f", ts)
        finally:
            APPLOG.debug("TimeSync plugin exited.")
            self.queue.task_done()

    @classmethod
    def configure(cls, **options):
        for key, value in options.items():
            lkey = str(key).lower()
            if lkey in cls.options:
                if isinstance(cls.options, dict):
                    dtype = cls.options[lkey]
                    if not isinstance(value, dtype):
                        print("Invalid option value provided for key: ", key)
                        continue
                setattr(cls, lkey, value)


class TimeSyncSleeper(PluginInterface):
    """This isn't a huge improvement over the daemon, in terms of perceived
    cpu usage on the Raspberry Pi Nano, though it does reduce memory
    consumption from approx 3.4% to 2.8% (probably because we aren't
    maintaining another queue in this plugin). """

    options = ['interval', 'timetravel']

    def __init__(self):
        super().__init__(daemon=True)
        self.interval = 1000
        self.timetravel = False
        self._lastvalue = None

    @staticmethod
    def consumer_type():
        return {str}

    def put(self, item):
        self._lastvalue = item

    def run(self):
        while not self.exiting:
            if self._lastvalue is None:
                continue
            try:
                ts = timestamp_from_data(self._lastvalue)
                if ts is not None:
                    if not self.timetravel and (ts > datetime.datetime.now()
                                                .timestamp()):
                        set_system_time(ts)
                    else:
                        APPLOG.warning("Timestamp is from the past, skipping "
                                       "set_system_time.")
            except ValueError:
                pass
            APPLOG.debug("Sleeping for %d seconds", self.interval)
            time.sleep(self.interval)


