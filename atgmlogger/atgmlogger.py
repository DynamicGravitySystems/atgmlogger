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
from pathlib import Path

import serial

from .common import parse_args, decode
from .dispatcher import Dispatcher
from .plugins import load_plugin
from . import VERBOSITY_MAP, APPLOG, rcParams

DATA_LVL = 75


# TODO: Determine how/if data string should be encapsulated
class DataRecord:
    __slots__ = ['data', 'timestamp']

    def __init__(self, data, timestamp):
        self.data = data
        self.timestamp = timestamp


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
    collector : queue.Queue, Optional
    sigExit : threading.Event, Optional

    """

    def __init__(self, handle, collector=None, sigExit=None):
        self._handle = handle
        self._queue = collector or queue.Queue()
        self.sigExit = sigExit or threading.Event()

        if not self._handle.is_open:
            self._handle.open()

    def exit(self):
        self.sigExit.set()

    @property
    def collector(self) -> queue.Queue:
        return self._queue

    @property
    def exiting(self) -> bool:
        return self.sigExit.is_set()

    def listen(self):
        """
        Listen endlessly for serial data on the specified port and add it
        to the output queue.

        This loop should not do any heavy processing, as we want to ensure
        all data is read from the serial buffer as soon as it is available.
        To this end any IO operations are pushed to a Queue for offloading to a
        separate thread to be processed.

        """
        while not self.exiting:
            data = decode(self._handle.readline())
            if data is None or data == '':
                continue
            self._queue.put_nowait(data)

        APPLOG.debug("Exiting listener.listen() method, and closing serial "
                     "handle.")
        self._handle.close()


def firstrun():
    # Attempt to run first-run installation script
    if not os.path.exists("/etc/%s/.atgmlogger" % __name__):
        APPLOG.info("Configuring ATGMLogger for first run.")
        try:
            from . import install
            install.install(verbose=True)

        except (ImportError, RuntimeError):
            APPLOG.exception("Failed to import/execute first run "
                             "initialization script")


def _configure_logger():
    log_dir = Path(rcParams['logging.logdir']) or Path('~').joinpath('atgmlogger')
    APPLOG.debug("Logging path set to: %s", str(log_dir))
    try:
        log_dir.mkdir(parents=False, exist_ok=True)
    except FileNotFoundError:
        log_dir = Path('.')
    try:
        logging.config.dictConfig(rcParams['logging'])
        _log = logging.getLogger()
    except (ValueError, TypeError, AttributeError, ImportError):
        APPLOG.exception("Exception applying logging configuration, fallback "
                         "configuration will be used.")
        from logging.handlers import TimedRotatingFileHandler
        _log = logging.getLogger()
        fpath = str(log_dir.joinpath('gravity.dat').resolve())
        data_hdlr = TimedRotatingFileHandler(fpath, when='D', interval=7,
                                             encoding='utf-8', delay=True,
                                             backupCount=8)
        _log.addHandler(data_hdlr)
        _log.setLevel(DATA_LVL)
    else:
        APPLOG.info("Logging facility configured from rcParams")
    return _log


def run(*argv):
    if argv is None:
        argv = sys.argv

    # Init Performance Counter
    t_start = time.perf_counter()

    args = parse_args(argv)
    APPLOG.setLevel(VERBOSITY_MAP.get(args.verbose, logging.DEBUG))

    # Do first run install stuff
    firstrun()
    # Configure Logging
    _configure_logger()

    dispatcher = Dispatcher()

    # Explicitly register the DataLogger 'plugin'
    from .logger import DataLogger
    dispatcher.register(DataLogger)

    plugins = rcParams['plugins']
    for plugin in plugins:
        try:
            load_plugin(plugin, register=True, **plugins[plugin])
        except (ImportError, ModuleNotFoundError):
            APPLOG.warning("Plugin %s could not be loaded.", plugin)

    hdl = serial.Serial(**rcParams['serial'])
    listener = SerialListener(hdl, collector=dispatcher.message_queue)

    # End Init Performance Counter
    t_end = time.perf_counter()
    APPLOG.debug("Initialization time: %.4f", t_end - t_start)

    try:
        dispatcher.start()
        listener.listen()
    except KeyboardInterrupt:
        APPLOG.info("Keyboard Interrupt intercepted, initiating clean exit.")
        listener.exit()
        dispatcher.exit(join=True)

    return 0
