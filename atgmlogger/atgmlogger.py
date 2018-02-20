# -*- coding: utf-8 -*-

"""
Advanced Technology Gravity Meter - Logger (AGTMlogger)

Linux/Raspberry PI utility designed to record serial data from Dynamic
Gravity Systems' (DGS) AT1A and AT1M advanced technology gravity meters.

"""

import sys
import time
import queue
import logging
import logging.config
import threading
from pathlib import Path
# from pprint import pprint

import serial

from .common import parse_args, decode
from .dispatcher import Dispatcher
from .plugins import load_plugin
from . import VERBOSITY_MAP, APPLOG, rcParams

DATA_LVL = 75


class SerialListener:
    """"
    Redesign of SerialLogger to achieve greater separation of responsibilities,
    and simplify the overall logic of the serial logging application.

    SerialListener comprises the core functionality of ATGMLogger - which is
    capturing raw serial data from a serial device.
    Ingested serial data is pushed onto a Queue for consumption by another
    thread or subprocess. This is to ensure that ideally no serial data is
    lost due to the listener waiting for a write event to complete
    (especially at higher data rates).

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


def _expand_log_paths(base, prefix, key='filename'):
    """Traverse a given 'base' dictionary searching for key (
    default='filename'), and update the key's value by prepending the
    specified prefix to it.
    The base dictionary is recursively traversed (searching all
    sub-dictionaries) to find any of the specified key.

    Parameters
    ----------
    base : dict
        The base dictionary to begin the recursive search and update.
    prefix : str or Path

    """
    if not isinstance(prefix, Path):
        prefix = Path(prefix)
    for k, v in base.items():
        if k == 'filename':
            expanded = prefix.joinpath(v)
            base[k] = str(expanded)
        elif isinstance(v, dict):
            _expand_log_paths(v, prefix, key=key)


def _configure_logger():
    log_dir = Path(rcParams['logging.logdir']) or \
              Path('~').expanduser().joinpath('atgmlogger')

    APPLOG.debug("Logging path set to: %s", str(log_dir))
    try:
        log_dir.mkdir(parents=False, exist_ok=True)
    except FileNotFoundError:
        log_dir = Path('.')
    try:
        log_conf = rcParams['logging']
        _expand_log_paths(log_conf, log_dir, key='filename')

        logging.config.dictConfig(log_conf)
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
    APPLOG.debug("Run received arguments: {}".format(argv))

    # Init Performance Counter
    t_start = time.perf_counter()

    args = parse_args(argv)
    APPLOG.setLevel(VERBOSITY_MAP.get(args.verbose, logging.DEBUG))
    _configure_logger()

    dispatcher = Dispatcher()

    # Explicitly register the DataLogger 'plugin'
    from .logger import DataLogger
    dispatcher.register(DataLogger)

    plugins = rcParams['plugins']
    if plugins is not None:
        for plugin in plugins:
            try:
                load_plugin(plugin, register=True, **plugins[plugin])
                APPLOG.info("Loaded plugin: %s", plugin)
            except (ImportError, ModuleNotFoundError):
                if args.verbose is not None and args.verbose > 2:
                    APPLOG.exception("Plugin <%s> could not be loaded.", plugin)
                else:
                    APPLOG.warning("Plugin <%s> could not be loaded.", plugin)

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
