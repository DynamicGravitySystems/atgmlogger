#!/usr/bin/python3

"""
Advanced Technology Gravity Meter - Logger (AGTMlogger)

Linux/Raspberry PI utility designed to record serial data from Dynamic
Gravity Systems' (DGS) AT1A and AT1M advanced technology gravity meters.

"""

import os
import sys
import time
import queue
import logging
import argparse
import threading
import multiprocessing as mp
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

import serial
try:
    import RPi.GPIO as gpio
except (ImportError, RuntimeError):
    gpio = None

from .helpers import *
# TODO: Better name for usbdispatcher
from .usbdispatcher import USBDispatcher
from atgmlogger import __version__, __description__

JOIN_TIMEOUT = 0.1
POLL_RATE = 1
# Data Logging Level
DATA_LVL = 75
VERBOSITY_MAP = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
_applog = logging.getLogger(__name__)
_applog.addHandler(logging.StreamHandler(sys.stderr))
_applog.setLevel(VERBOSITY_MAP[0])


class Blink:
    def __init__(self, led, priority=5, frequency=0.1):
        self.led = led
        self.priority = priority
        self.frequency = frequency

    def __lt__(self, other):
        return self.priority < other.priority


class GPIOListener(threading.Thread):
    def __init__(self, config, gpio_queue: queue.PriorityQueue, exit_sig):
        super().__init__(name=self.__class__.__name__)
        self._queue = gpio_queue
        self._exiting = exit_sig

        try:
            modes = {'board': gpio.BOARD, 'bcm': gpio.BCM}
            self._mode = modes[config.get('mode', 'board')]
        except AttributeError:
            pass
        self.data_pin = config.get('data_led', 11)
        self.usb_pin = config.get('usb_led', 13)

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
            try:
                self.blink(blink)
            except AttributeError:
                pass
            finally:
                self._queue.task_done()

        for pin in self.outputs:
            gpio.output(pin, False)
        _applog.debug("Exiting GPIOListener thread.")
        gpio.cleanup()


class Command:
    # TODO: Add on_complete hook? allow firing of lambda on success
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
    """
    Attributes
    ----------
    command_queue : queue.PriorityQueue
    exit_sig : threading.Event

    """
    def __init__(self, command_queue, exit_sig):
        super().__init__(name=self.__class__.__name__)
        self._cmd_queue = command_queue
        self._exiting = exit_sig
        self._results = list()

    def run(self):
        while not self._exiting.is_set():
            try:
                cmd = self._cmd_queue.get(block=True, timeout=1)
            except queue.Empty:
                continue
            try:
                result = cmd.execute()
                self._results.append(result)
            except AttributeError:
                _applog.exception("Invalid command in Queue, command must "
                                  "support execute() attribute.")
            except Exception as e:
                _applog.exception("Error Executing Command in CommandListener.")
                continue
            else:
                _applog.debug("Command executed without exception.")
                # Run on_complete hook?
                pass
            finally:
                self._cmd_queue.task_done()
        _applog.debug("Exiting CommandListener thread.")


class DataWriter(threading.Thread):
    """
    Parameters
    ----------
    data_queue : queue.Queue
    logger : logging.Logger
    exit_sig : threading.Event
    gpio_queue : queue.PriorityQueue
    """
    # TODO: Pass logger config dict here for init?
    def __init__(self, data_queue, logger, exit_sig, gpio_queue=None):
        super().__init__(name=self.__class__.__name__)
        self._data_queue = data_queue
        self._exiting = exit_sig
        self._logger = logger
        self._internal_copy = []
        self._gpio_queue = gpio_queue or queue.PriorityQueue()
        # TODO: Find data rate to better control blinking
        self._blink_data = Blink(11)

    def run(self):
        while not self._exiting.is_set() or not self._data_queue.empty():
            try:
                data = self._data_queue.get(block=True, timeout=0.1)
                self._internal_copy.append(data)
                self._logger.log(DATA_LVL, data)
                self._gpio_queue.put_nowait(self._blink_data)
            except queue.Empty:
                # Using timeout and empty exception allows for thread to
                # check exit signal
                continue
            except queue.Full:
                continue
            except FileNotFoundError:
                _applog.error("Log handler file path not found, data will not "
                              "be saved.")
            else:
                try:
                    self._data_queue.task_done()
                except AttributeError:
                    # In case of multiprocessing.Queue
                    pass

        _applog.debug("Exiting DataWriter thread.")


class MountListener(threading.Thread):
    """Simple thread that watches a mount_path then forks a subprocess to
    perform actions when a device is mounted."""
    def __init__(self, mount_path, log_dir, exit_sig):
        super().__init__(name=self.__class__.__name__)
        self._exiting = exit_sig
        self._mount = mount_path
        self._logs = log_dir

    def run(self):
        while not self._exiting.is_set():
            # Check for device mount at mount path, sleep for POLL_RATE if none
            if not os.path.ismount(self._mount):
                time.sleep(POLL_RATE)
                continue

            try:
                dispatcher = USBDispatcher(self._mount, self._logs)
            except:
                _applog.exception("Exception encountered instantiating "
                                  "USBDispatcher")
                continue
            else:
                _applog.info("Starting USB dispatcher.")
                dispatcher.start()
                dispatcher.join()


class AT1Listener:
    """"
    Redesign of SerialLogger to achieve greater separation of duties,
    and simplify the overall logic of the serial logging application.

    AT1Listener comprises the core functionality of ATGMLogger - which is
    capturing raw serial data from a serial device.
    Ingested serial data is pushed onto a Queue for consumption by another
    thread or subprocess. This is to ensure that ideally no serial data is
    lost due to the listener waiting for a write event to complete (
    especially at higher data rates).

    Parameters
    ----------
    handle : serial.Serial
    exit_sig : threading.Event
    data_queue : queue.Queue or multiprocessing.Queue

    """

    def __init__(self, handle, exit_sig, data_queue=None, cmd_queue=None):
        self._handle = handle
        self._timesynced = False
        # Set defaults if no queue's are supplied.
        self._data_queue = data_queue or queue.Queue()
        self._cmd_queue = cmd_queue or queue.PriorityQueue()
        self._exiting = exit_sig

        if not self._handle.is_open:
            self._handle.open()

    @property
    def output(self) -> queue.Queue:
        return self._data_queue

    @property
    def commands(self) -> queue.PriorityQueue:
        return self._cmd_queue

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
        tick = 99
        while not self.exiting.is_set():
            data = decode(self._handle.readline())
            if data == '':
                continue
            self._data_queue.put_nowait(data)
            tick += 1
            # TODO: Consider periodically re-synchronizing (every 12hrs?)
            if not self._timesynced and (tick % 100 == 0):
                _applog.info("Attempting to synchronize to GPS time.")
                ts = timestamp_from_data(data)
                if ts is None:
                    _applog.info("Unable to synchronize time, no valid GPS "
                                 "time data.")
                    continue
                else:
                    cmd = Command(set_system_time, ts, priority=1)
                    self._cmd_queue.put_nowait(cmd)
                    self._timesynced = True

        # exiting set
        _applog.debug("Exiting listener.listen() method, and closing serial "
                      "handle.")
        self._handle.close()


def parse_argv(argv):
    parser = argparse.ArgumentParser(prog=argv[0], description=__description__)
    parser.add_argument('-V', '--version', action='version',
                        version=__version__)
    parser.add_argument('-v', '--verbose', action='count')
    parser.add_argument('-l', '--logdir', action='store',
                        default='/var/log/dgs')
    parser.add_argument('-d', '--device', action='store')
    parser.add_argument('-c', '--config', action='store',
                        default='config.json')
    parser.add_argument('--nogpio', action='store_true', help="Disable GPIO "
                                                              "thread.")
    return parser.parse_args(argv[1:])


def main(argv):
    tstart = time.perf_counter()
    args = parse_argv(argv)
    _applog.setLevel(VERBOSITY_MAP.get(args.verbose, logging.DEBUG))

    # TODO: Arguments passed via cmdline should take precedent over defaults
    # AND over JSON config values.

    config = get_json_config(args.config)

    c_serial = config.get('serial', dict(port='/dev/serial0', baudrate=57600,
                                         timeout=1))
    if args.device is not None:
        c_serial.update(port=args.device)

    c_usb = config.get('usb', dict(mount="/media/removable", copy_level="data"))
    c_gpio = config.get('gpio', dict(mode="board", data_led=11, usb_led=13))
    c_logging = config.get('logging',
                           dict(logdir="/var/log/{}".format(__name__)))
    if args.logdir is not None:
        c_logging.update(logdir=args.logdir)

    # Initialize and Run #
    exit_event = threading.Event()
    data_queue = queue.Queue()
    cmd_queue = queue.PriorityQueue()
    gpio_queue = queue.PriorityQueue(maxsize=10)

    data_log = logging.getLogger('gravity')
    log_dir = Path(c_logging['logdir'])
    try:
        log_dir.mkdir(parents=False, exist_ok=True)
    except FileNotFoundError:
        log_dir = Path('.')
    fpath = str(log_dir.joinpath('gravity.dat').resolve())
    data_hdlr = TimedRotatingFileHandler(fpath, when='D', interval=7,
                                         encoding='utf-8', delay=True,
                                         backupCount=8)
    data_log.addHandler(data_hdlr)
    data_log.setLevel(DATA_LVL)

    hdlr = serial.Serial(**c_serial)
    listener = AT1Listener(hdlr,
                           exit_sig=exit_event,
                           data_queue=data_queue,
                           cmd_queue=cmd_queue)

    threads = []
    if not args.nogpio:
        threads.append(GPIOListener(c_gpio,
                                    gpio_queue=gpio_queue,
                                    exit_sig=exit_event))

    threads.append(DataWriter(data_queue,
                              logger=data_log,
                              exit_sig=exit_event,
                              gpio_queue=gpio_queue))

    threads.append(CommandListener(cmd_queue,
                                   exit_sig=exit_event))

    threads.append(MountListener(c_usb['mount'],
                                 log_dir=log_dir,
                                 exit_sig=exit_event))

    for thread in threads:
        thread.start()

    tend = time.perf_counter()
    _applog.debug("Initialization time: " + str(tend - tstart))
    try:
        # Infinite Main Thread - Listen for Serial Data
        _applog.debug("Starting listener.")
        listener.listen()
    except KeyboardInterrupt:
        _applog.debug("KeyboardInterrupt intercepted. Setting exit signal.")
        exit_event.set()
        for thread in threads:
            _applog.debug("Joining thread {}, timeout {}"
                          .format(thread.name, JOIN_TIMEOUT))
            thread.join(timeout=JOIN_TIMEOUT)
        return 1
    return 0
