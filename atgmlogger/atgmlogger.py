#!/usr/bin/python3
# -*- encoding: utf-8 -*-

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
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

import serial
try:
    import RPi.GPIO as gpio
    HAVE_GPIO = True
except (ImportError, RuntimeError):
    HAVE_GPIO = False

from .common import *
from .removable import RemovableStorageHandler
from .logger import DataLogger
from atgmlogger import __version__, __description__, VERBOSITY_MAP, applog

JOIN_TIMEOUT = 0.1
POLL_RATE = 1
CONFIG_PATH = 'config.json'
DATA_LVL = 75


class GPIOListener(threading.Thread):
    def __init__(self, config, gpio_queue: queue.PriorityQueue, exit_sig):
        super().__init__(name=self.__class__.__name__, daemon=True)
        if not HAVE_GPIO:
            applog.warning("GPIO Module Unavailable on this System.")
            return
        self._queue = gpio_queue
        self._exiting = exit_sig

        modes = {'board': gpio.BOARD, 'bcm': gpio.BCM}
        self._mode = modes[config.get('mode', 'board')]
        self.data_pin = config.get('data_led', 11)
        self.usb_pin = config.get('usb_led', 13)

        self.outputs = [self.data_pin, self.usb_pin]

        gpio.setmode(self._mode)
        for pin in self.outputs:
            gpio.setup(pin, gpio.OUT)

    def _blink(self, blink: Blink):
        if blink.led not in self.outputs:
            return
        if HAVE_GPIO:
            gpio.output(blink.led, True)
            time.sleep(blink.frequency)
            gpio.output(blink.led, False)
            time.sleep(blink.frequency)

    def run(self):
        if not HAVE_GPIO:
            applog.warning("GPIO Module is unavailable. Exiting %s thread.",
                           self.__class__.__name__)
            return

        while not self._exiting.is_set():
            try:
                blink = self._queue.get(timeout=.1)  # type: Blink
            except queue.Empty:
                continue
            self._blink(blink)
            self._queue.task_done()

        for pin in self.outputs:
            gpio.output(pin, False)
        applog.debug("Exiting GPIOListener thread.")
        gpio.cleanup()


class Command:
    # TODO: Add on_complete hook? allow firing of lambda on success
    """
    Command class which encapsulates a function and its arguments, to be
    executed by the CommandListener subscriber.

    Commands may be assigned an int priority where 0 is the highest priority.
    This class implements the necessary interface to be compatible with the
    PriorityQueue. e.g.:
        Command[0] returns the priority
        Command < OtherCommand returns True if Command.priority <
        OtherCommand.priority

    The result of the executed function is returned via the execute or call
    methods to be captured if necessary.

    """
    def __init__(self, command, *cmd_args, priority=None, name=None,
                 **cmd_kwargs):
        self.priority = priority or 9
        self.functor = command
        self.name = name or command.__name__
        self._args = cmd_args
        self._kwargs = cmd_kwargs

    def execute(self):
        return self.functor(*self._args, **self._kwargs)

    def __call__(self, *args, **kwargs):
        """Alternate syntax to execute()
        TODO: Allow updating of kwargs via call syntax?
        """
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
            result = cmd.execute()
            self._results.append(result)
            applog.debug("Command executed without exception.")
            self._cmd_queue.task_done()

        applog.debug("Exiting %s thread.", self.__class__.__name__)


class MountListener(threading.Thread):
    """Simple thread that watches a mount_path then forks a subprocess to
    perform actions when a device is mounted."""
    def __init__(self, mount_path, log_dir, exit_sig):
        super().__init__(name=self.__class__.__name__)

        self._exiting = exit_sig
        self._mount = mount_path
        self._logs = log_dir

    def run(self):
        if sys.platform == 'win32':
            applog.warning("%s not supported on Windows Platform",
                           self.__class__.__name__)
            return
        while not self._exiting.is_set():
            # Check for device mount at mount path, sleep for POLL_RATE if none
            if os.path.ismount(self._mount):
                applog.debug("Mount detected on %s", self._mount)
                dispatcher = RemovableStorageHandler(self._mount, self._logs)
                applog.info("Starting USB dispatcher.")
                dispatcher.start()
                dispatcher.join()
            else:
                time.sleep(POLL_RATE)


class SerialListener:
    """"
    Redesign of SerialLogger to achieve greater separation of responsibilities,
    and simplify the overall logic of the serial logging application.

    SerialListener comprises the core functionality of ATGMLogger - which is
    capturing raw serial data from a serial device.
    Ingested serial data is pushed onto a Queue for consumption by another
    thread or subprocess. This is to ensure that ideally no serial data is
    lost due to the listener waiting for a write event to complete (
    especially at higher data rates).

    Parameters
    ----------
    handle : serial.Serial
    exit_sig : threading.Event
    data_queue : queue.Queue

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
    def data(self) -> queue.Queue:
        return self._data_queue

    @property
    def commands(self) -> queue.PriorityQueue:
        return self._cmd_queue

    @property
    def exiting(self) -> threading.Event:
        return self._exiting

    def _sync_time(self, data):
        applog.info("Attempting to synchronize to GPS time.")
        ts = timestamp_from_data(data)
        if ts is None:
            applog.info("Unable to synchronize time, no valid GPS time data.")
            return False
        else:
            cmd = Command(set_system_time, ts, priority=1)
            self._cmd_queue.put_nowait(cmd)
            return True

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
                self._timesynced = self._sync_time(data)
            elif tick % 10000 == 0:
                applog.debug("Attempting to resynchronize time after 10000 "
                             "ticks.")
                self._sync_time(data)

        applog.debug("Exiting listener.listen() method, and closing serial "
                     "handle.")
        self._handle.close()


def parse_argv(argv):
    parser = argparse.ArgumentParser(prog=__name__, description=__description__)
    parser.add_argument('-V', '--version', action='version',
                        version=__version__)
    parser.add_argument('-v', '--verbose', action='count')
    parser.add_argument('-d', '--device', action='store')
    parser.add_argument('-l', '--logdir', action='store',
                        default='/var/log/dgs')
    parser.add_argument('-m', '--mountdir', action='store',
                        help="Specify custom USB Storage mount path. "
                             "Overrides path configured in configuration.")
    parser.add_argument('-c', '--config', action='store', default='config.json',
                        help="Specify path to custom JSON configuration.")
    parser.add_argument('--nogpio', action='store_true',
                        help="Disable GPIO output (LED notifications).")
    return parser.parse_args(argv[1:])


def get_config(argv):
    """Parse arguments from commandline and load configuration file."""
    parser = argparse.ArgumentParser(prog=argv[0], description=__description__)
    parser.add_argument('-V', '--version', action='version',
                        version=__version__)
    parser.add_argument('-v', '--verbose', action='count')
    parser.add_argument('-d', '--device', action='store')
    parser.add_argument('-l', '--logdir', action='store',
                        default='/var/log/dgs')
    parser.add_argument('-m', '--mountdir', action='store',
                        help="Specify custom USB Storage mount path. "
                             "Overrides path configured in configuration.")
    parser.add_argument('-c', '--config', action='store',
                        help="Specify path to custom JSON configuration.")
    parser.add_argument('--nogpio', action='store_true',
                        help="Disable GPIO output (LED notifications).")

    args = parser.parse_args(argv[1:])
    config = get_json_config(args.config or CONFIG_PATH)

    if args.device:
        config['serial']['port'] = args.device

    if args.logdir:
        config['logging']['logdir'] = args.logdir

    if args.mountdir:
        config['usb']['mount'] = args.mountdir

    if args.nogpio:
        pass

    return config


def run(*argv):
    """
    Initialize and start main application loop.


    Parameters
    ----------
    argv

    Returns
    -------

    """
    if argv is None:
        argv = sys.argv
    t_start = time.perf_counter()
    args = parse_argv(argv)
    applog.setLevel(VERBOSITY_MAP.get(args.verbose, logging.DEBUG))

    # TODO: Arguments passed via cmdline should take precedent over defaults
    # AND over JSON config values.

    # Note: Behavior of get_json_config is to return empty dict if no json cfg
    config = get_json_config(args.config)

    c_serial = config.get('serial', dict(port='/dev/serial0', baudrate=57600,
                                         timeout=1))
    if args.device is not None:
        c_serial.update(dict(port=args.device))

    c_usb = config.get('usb', dict(mount="/media/removable", copy_level="data"))
    c_gpio = config.get('gpio', dict(mode="board", data_led=11, usb_led=13))
    c_logging = config.get('logging',
                           dict(logdir="/var/log/{}".format(__name__)))
    if args.logdir is not None:
        c_logging.update({"logdir": args.logdir})

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

    hdl = serial.Serial(**c_serial)
    listener = SerialListener(hdl,
                              exit_sig=exit_event,
                              data_queue=data_queue,
                              cmd_queue=cmd_queue)

    threads = []
    if not args.nogpio and HAVE_GPIO:
        threads.append(GPIOListener(c_gpio,
                                    gpio_queue=gpio_queue,
                                    exit_sig=exit_event))

    threads.append(DataLogger(data_queue,
                              logger=data_log,
                              exit_sig=exit_event,
                              gpio_queue=gpio_queue))

    threads.append(CommandListener(cmd_queue,
                                   exit_sig=exit_event))

    threads.append(MountListener(c_usb.get('mount', args.mountdir),
                                 log_dir=log_dir,
                                 exit_sig=exit_event))

    for thread in threads:
        thread.start()

    applog.debug("Initialization time: %.5f", time.perf_counter() - t_start)
    try:
        # Infinite Main Thread - Listen for Serial Data
        applog.debug("Starting listener.")
        listener.listen()
    except KeyboardInterrupt:
        applog.debug("KeyboardInterrupt intercepted. Setting exit signal.")
        exit_event.set()
        for thread in threads:
            applog.debug("Joining thread {}, timeout {}"
                         .format(thread.name, JOIN_TIMEOUT))
            thread.join(timeout=JOIN_TIMEOUT)
        return 1
    return 0
