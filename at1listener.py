#!/usr/bin/python3

import sys
import json
import time
import queue
import shlex
import logging
import itertools
import threading
import subprocess
from typing import Union
from datetime import datetime
from pathlib import Path

import serial

try:
    import RPi.GPIO as gpio
except ImportError:
    gpio = None

ILLEGAL_CHARS = list(itertools.chain(range(0, 32), [255]))
JSON_CONFIG = Path('config.json')


def get_config(path=None):
    path = path or JSON_CONFIG
    if not path.exists():
        return {}
    try:
        with path.open('r') as fd:
            config = json.load(fd)
    except json.JSONDecodeError:
        print("Error decoding JSON config")
        return {}
    else:
        return config


def decode(bytearr, encoding='utf-8'):
    if isinstance(bytearr, str):
        return bytearr
    try:
        raw = bytes([c for c in bytearr if c not in ILLEGAL_CHARS])
        decoded = raw.decode(encoding, errors='ignore').strip('\r\n')
    except AttributeError:
        decoded = None
    return decoded


def convert_gps_time(gpsweek: int, gpsweekseconds: float):
    """
    convert_gps_time :: (int -> float) -> float
    Simplified method from DynamicGravityProcessor application:
    https://github.com/DynamicGravitySystems/DGP

    Converts a GPS time format (weeks + seconds since 6 Jan 1980) to a UNIX
    timestamp (seconds since 1 Jan 1970) without correcting for UTC leap
    seconds.

    Static values gps_delta and gpsweek_cf are defined by the below functions
    (optimization)
    gps_delta is the time difference (in seconds) between UNIX time and GPS time
    gps_delta = (dt.datetime(1980,1,6) - dt.datetime(1970,1,1)).total_seconds()

    gpsweek_cf is the coefficient to convert weeks to seconds
    gpsweek_cf = 7 * 24 * 60 * 60  # 604800

    :param gpsweek: Number of weeks since beginning of GPS time
        (1980-01-06 00:00:00)
    :param gpsweekseconds: Number of seconds since the GPS week parameter
    :return: (float) unix timestamp
        number of seconds since 1970-01-01 00:00:00
    """
    # GPS time begins 1980 Jan 6 00:00, UNIX time begins 1970 Jan 1 00:00
    gps_delta = 315964800.0
    gpsweek_cf = 604800

    gps_ticks = (float(gpsweek) * gpsweek_cf) + float(gpsweekseconds)

    timestamp = gps_delta + gps_ticks
    return timestamp


def timestamp_from_data(line) -> Union[float, None]:
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
        fmt = "%Y%m%d%H%H%S"
        try:
            timestamp = datetime.strptime(date, fmt).timestamp()
        except ValueError:
            return None
        else:
            return timestamp
    else:
        return None


def set_system_time(timestamp):
    platform = sys.platform
    if platform == 'linux' or platform == 'linux2':
        cmd = 'date +%s -s @{ts}'.format(ts=timestamp)
        output = subprocess.check_output(shlex.split(cmd)).decode('utf-8')
        return output
    else:
        print("set_system_time not supported on this platform.")
        return None


def blink_led(led=1):
    print("Blinking led: {}".format(led))


class Blink:
    def __init__(self, led, priority=5, frequency=0.1):
        self.led = led
        self.priority = priority
        self.frequency = frequency

    def __lt__(self, other):
        return self.priority < other.priority


class GPIOListener(threading.Thread):
    def __init__(self, config, blink_queue: queue.PriorityQueue, exiting):
        super().__init__(name=self.__class__.__name__)
        self._queue = blink_queue
        self._exiting = exiting
        self._mode = gpio.BOARD

        self._mode = {'board': gpio.BOARD, 'bcm': gpio.BCM}['board']
        self.data_pin = config.get('data_led', 11)
        self.usb_pin = config.get('usb_led', 13)

        # TODO: Fix hardcoding
        self.outputs = [self.data_pin, self.usb_pin]

        try:
            gpio.setmode(self._mode)
            for pin in self.outputs:
                gpio.setup(pin, gpio.OUT)
        except AttributeError:
            pass

    def blink(self, blink: Blink):
        if blink.led not in self.outputs:
            return
        gpio.output(blink.led, True)
        time.sleep(blink.frequency)
        gpio.output(blink.led, False)
        time.sleep(blink.frequency)

    def run(self):
        if gpio is None:
            return
        while not self._exiting.is_set():
            try:
                blink = self._queue.get(timeout=.1)  # type: Blink
            except queue.Empty:
                continue

            self.blink(blink)

        for pin in self.outputs:
            gpio.output(pin, False)
        gpio.cleanup()


class Command:
    def __init__(self, command, *cmd_args, priority=None, **cmd_kwargs):
        self.priority = priority or 9
        self.functor = command
        self._args = cmd_args
        self._kwargs = cmd_kwargs

    def execute(self):
        return self.functor(*self._args, **self._kwargs)

    def __getitem__(self, item):
        if item == 0:
            return self.priority
        raise IndexError

    def __lt__(self, other):
        return self.priority < other.priority


class CommandListener(threading.Thread):
    def __init__(self, command_queue, exiting):
        super().__init__(name=self.__class__.__name__)
        self._commands = command_queue
        self._exiting = exiting
        self._results = list()

    def run(self):
        while not self._exiting.is_set():
            try:
                cmd = self._commands.get(block=True, timeout=1)
            except queue.Empty:
                continue

            try:
                result = cmd.execute()
                self._results.append(result)
            except AttributeError:
                print("Invalid command pulled from queue. Must support "
                      "execute() method.")
            except:
                print("Error executing command")
                continue


class DataWriter(threading.Thread):
    def __init__(self, data_queue, logger, exiting: threading.Event=None):
        super().__init__(name=self.__class__.__name__)
        self._input = data_queue
        self._exiting = exiting
        self._logger = logger
        self._internal_copy = []

    def run(self):
        while not self._exiting.is_set():
            try:
                data = self._input.get(block=True, timeout=0.05)
                self._internal_copy.append(data)
                self._logger.log(data)
            except queue.Empty:
                continue


class AT1Listener:
    """"
    Redesign of SerialLogger to achieve greater separation of duties,
    and simplify the overall logic of the serial logging application.

    Parameters
    ----------
    handle : serial.Serial

    Attributes
    ----------

    """

    def __init__(self, handle, exiting, gpio_queue=None):
        self._handle = handle
        self._timesynced = False
        self._output = queue.Queue()
        self._cmd_queue = queue.PriorityQueue()
        self._exiting = exiting
        self._gpio_queue = gpio_queue or queue.PriorityQueue()

        self._blink_data_led = Blink(11)

        if not self._handle.is_open:
            self._handle.open()

    @property
    def output(self) -> queue.Queue:
        return self._output

    @property
    def commands(self) -> queue.PriorityQueue:
        return self._cmd_queue

    @property
    def gpio(self) -> queue.PriorityQueue:
        return  self._gpio_queue

    @property
    def exiting(self) -> threading.Event:
        return self._exiting

    def listen(self):
        """
        Listen endlessly for serial data on the specified port and add it
        to the output queue.

        This loop should not do any heavy processing, as we want to ensure
        all data is read from the serial buffer as soon as it is available.
        To this end any IO operations are pushed to a Queue for offloading to a
        separate thread to be processed.
        """
        tick = 0
        while not self.exiting.is_set():
            data = decode(self._handle.readline())
            if data == '':
                continue
            tick += 1
            self._output.put_nowait(data)
            self._gpio_queue.put_nowait(self._blink_data_led)

            # TODO: Consider periodically re-synchronizing (every 12hrs?)
            if not self._timesynced and (tick % 100 == 0):
                ts = timestamp_from_data(data)
                if ts is None:
                    continue
                cmd = Command(set_system_time, ts, priority=1)
                self._cmd_queue.put_nowait(cmd)
                self._timesynced = True


def main():
    config = get_config(JSON_CONFIG)
    c_serial = config.get('serial', dict(device='/dev/serial0', baudrate=57600,
                                         timeout=0.1))
    main_exit = threading.Event()
    threads = []

    hdlr = serial.Serial(**c_serial)
    gpio_queue = queue.PriorityQueue(maxsize=10)
    listener = AT1Listener(hdlr, main_exit, gpio_queue)

    threads.append(GPIOListener(config.get('gpio', {}), gpio_queue, main_exit))

    data_log = logging.getLogger('data')
    threads.append(DataWriter(listener.output, data_log, main_exit))
    threads.append(CommandListener(listener.commands, main_exit))

    for thread in threads:
        thread.start()

    try:
        listener.listen()
    except KeyboardInterrupt:
        main_exit.set()
        for thread in threads:
            thread.join(timeout=.1)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
