#!/usr/bin/python3
# -*- coding: utf-8 -*-

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
import logging.config
import threading
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from pprint import pprint

import serial
try:
    import RPi.GPIO as gpio
    HAVE_GPIO = True
except (ImportError, RuntimeError):
    HAVE_GPIO = False

from .common import *
from .removable import RemovableStorageHandler
from .logger import DataLogger
from atgmlogger import VERBOSITY_MAP, APPLOG, rcParams

JOIN_TIMEOUT = 0.1
POLL_RATE = 1
CONFIG_PATH = '.atgmlogger'
DATA_LVL = 75


class GPIOListener(threading.Thread):
    def __init__(self, config, gpio_queue: queue.PriorityQueue, exit_sig):
        super().__init__(name=self.__class__.__name__, daemon=True)
        if not HAVE_GPIO:
            APPLOG.warning("GPIO Module Unavailable on this System.")
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
            APPLOG.warning("GPIO Module is unavailable. Exiting %s thread.",
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
        APPLOG.debug("Exiting GPIOListener thread.")
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
    def __init__(self, command, *cmd_args, priority=None, name=None, log=True,
                 **cmd_kwargs):
        self.priority = priority or 9
        self.functor = command
        self.name = name or command.__name__
        self._log = True
        self._args = cmd_args
        self._kwargs = cmd_kwargs

    def execute(self):
        res = self.functor(*self._args, **self._kwargs)
        if self._log:
            APPLOG.info("Command {name} executed with result: {"
                        "result}".format(name=self.name, result=res))
        return res

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
            APPLOG.debug("Command executed without exception.")
            self._cmd_queue.task_done()

        APPLOG.debug("Exiting %s thread.", self.__class__.__name__)


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
            APPLOG.warning("%s not supported on Windows Platform",
                           self.__class__.__name__)
            return
        while not self._exiting.is_set():
            # Check for device mount at mount path, sleep for POLL_RATE if none
            if os.path.ismount(self._mount):
                APPLOG.debug("Mount detected on %s", self._mount)
                dispatcher = RemovableStorageHandler(self._mount, self._logs)
                APPLOG.info("Starting USB dispatcher.")
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
        APPLOG.info("Attempting to synchronize to GPS time.")
        ts = timestamp_from_data(data)
        if ts is None:
            APPLOG.info("Unable to synchronize time, no valid GPS time data.")
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
                APPLOG.debug("Attempting to resynchronize time after 10000 "
                             "ticks.")
                self._sync_time(data)

        APPLOG.debug("Exiting listener.listen() method, and closing serial "
                     "handle.")
        self._handle.close()


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
    args = parse_args(argv)
    APPLOG.setLevel(VERBOSITY_MAP.get(args.verbose, logging.DEBUG))

    # Attempt to run first-run installation script
    if not os.path.exists("/etc/%s/.atgmlogger" % __name__):
        APPLOG.info("Configuring ATGMLogger for first run.")
        try:
            from . import install
            install.install(verbose=True)

        except (ImportError, RuntimeError):
            APPLOG.exception("Failed to import/execute first run "
                             "initialization script")

    log_dir = Path(rcParams['logging.logdir']) or Path('~').joinpath('atgmlogger')
    APPLOG.debug("Logging path set to: %s", str(log_dir))
    try:
        log_dir.mkdir(parents=False, exist_ok=True)
    except FileNotFoundError:
        log_dir = Path('.')
    try:
        logging.config.dictConfig(rcParams['logging'])
        data_log = logging.getLogger()
        APPLOG.setLevel(VERBOSITY_MAP.get(args.verbose, logging.DEBUG))
    except (ValueError, TypeError, AttributeError, ImportError):
        APPLOG.exception("Exception applying logging configuration, fallback "
                         "configuration will be used.")
        data_log = logging.getLogger()
        fpath = str(log_dir.joinpath('gravity.dat').resolve())
        data_hdlr = TimedRotatingFileHandler(fpath, when='D', interval=7,
                                             encoding='utf-8', delay=True,
                                             backupCount=8)
        data_log.addHandler(data_hdlr)
        data_log.setLevel(DATA_LVL)
    else:
        APPLOG.info("Logging facility configured from rcParams")

    # Initialize and Run #
    exit_event = threading.Event()
    data_queue = queue.Queue()
    cmd_queue = queue.PriorityQueue()
    gpio_queue = queue.PriorityQueue(maxsize=10)

    hdl = serial.Serial(**rcParams['serial'])
    listener = SerialListener(hdl,
                              exit_sig=exit_event,
                              data_queue=data_queue,
                              cmd_queue=cmd_queue)

    threads = []
    if not args.nogpio and HAVE_GPIO:
        threads.append(GPIOListener(rcParams['gpio'],
                                    gpio_queue=gpio_queue,
                                    exit_sig=exit_event))

    threads.append(DataLogger(data_queue,
                              logger=data_log,
                              exit_sig=exit_event,
                              gpio_queue=gpio_queue))

    threads.append(CommandListener(cmd_queue,
                                   exit_sig=exit_event))

    threads.append(MountListener(rcParams['usb.mount'],
                                 log_dir=log_dir,
                                 exit_sig=exit_event))

    for thread in threads:
        thread.start()

    APPLOG.debug("Initialization time: %.5f", time.perf_counter() - t_start)
    try:
        # Infinite Main Thread - Listen for Serial Data
        APPLOG.debug("Starting serial listener.")
        listener.listen()
    except KeyboardInterrupt:
        APPLOG.debug("KeyboardInterrupt intercepted. Setting exit signal.")
        exit_event.set()
        for thread in threads:
            APPLOG.debug("Joining thread {}, timeout {}"
                         .format(thread.name, JOIN_TIMEOUT))
            thread.join(timeout=JOIN_TIMEOUT)
        return 1
    return 0
