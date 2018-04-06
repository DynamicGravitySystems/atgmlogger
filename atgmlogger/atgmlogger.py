# -*- coding: utf-8 -*-

"""
Advanced Technology Gravity Meter - Logger (AGTMLogger)

Linux/Raspberry PI utility designed to record serial data from Dynamic
Gravity Systems' (DGS) AT1A and AT1M advanced technology gravity meters.

"""

import time
import queue
import itertools
import logging
import logging.config
import signal
import threading
from pathlib import Path

import serial

from .runconfig import rcParams
from .dispatcher import Dispatcher
from .plugins import load_plugin
from . import APPLOG, POSIX, LOG_FMT, DATE_FMT

ILLEGAL_CHARS = list(itertools.chain(range(0, 32), [255, 256]))


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
        self.buffer = bytearray()

        if not self._handle.is_open:
            self._handle.open()

    def exit(self):
        self.sigExit.set()
        self._queue.put(None)

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
            data = self.decode(self.readline())
            if data is None or data == '':
                continue
            self._queue.put_nowait(data)

        APPLOG.debug("Exiting listener.listen() method, and closing serial "
                     "handle.")
        self._handle.close()

    def readline(self):
        """
        This method drastically reduces CPU usage of the utility (from ~50%
        when reading 10hz gravity data to ~27% on a raspberry pi zero)

        Credit for this function to skoehler (https://github.com/skoehler) from
        https://github.com/pyserial/pyserial/issues/216

        """
        i = self.buffer.find(b"\n")
        if i >= 0:
            line = self.buffer[:i + 1]
            self.buffer = self.buffer[i + 1:]
            return line
        while True:
            i = max(1, min(2048, self._handle.in_waiting))
            data = self._handle.read(i)
            i = data.find(b"\n")
            if i >= 0:
                line = self.buffer + data[:i + 1]
                self.buffer[0:] = data[i + 1:]
                return line
            else:
                self.buffer.extend(data)

    @staticmethod
    def decode(bytearr, encoding='utf-8'):
        if isinstance(bytearr, str):
            return bytearr
        try:
            raw = bytes([c for c in bytearr if c not in ILLEGAL_CHARS])
            decoded = raw.decode(encoding, errors='ignore').strip('\r\n')
        except AttributeError:
            decoded = None
        return decoded


def _configure_applog():
    logdir = Path(rcParams['logging.logdir'])
    if not logdir.exists():
        try:
            logdir.mkdir(parents=True, mode=0o750)
        except (FileNotFoundError, OSError):
            APPLOG.warning("Log directory could not be created, log "
                           "files will be output to current directory (%s).",
                           str(Path().resolve()))
            logdir = Path()

    from logging.handlers import WatchedFileHandler

    applog_hdlr = WatchedFileHandler(str(logdir.joinpath('application.log')),
                                     encoding='utf-8')
    applog_hdlr.setFormatter(logging.Formatter(LOG_FMT, datefmt=DATE_FMT))
    APPLOG.addHandler(applog_hdlr)
    APPLOG.debug("Application log configured, log path: %s", str(logdir))


def _get_dispatcher(collector=None, plugins=None, verbosity=0, exclude=None):
    """Loads plugin and returns instance of Dispatcher"""
    dispatcher = Dispatcher(collector=collector)

    # Explicitly register the DataLogger 'plugin'
    from .logger import DataLogger

    logfile = Path(rcParams['logging.logdir']).joinpath('gravdata.dat')
    dispatcher.register(DataLogger, logfile=logfile)

    plugins = plugins or rcParams['plugins']
    if plugins is not None:
        for plugin in plugins:
            try:
                load_plugin(plugin, register=True, **plugins[plugin])
                APPLOG.info("Loaded plugin: %s", plugin)
            except ImportError:  # ModuleNotFoundError implemented in 3.6
                if verbosity is not None and verbosity >= 2:
                    APPLOG.exception("Plugin <%s> could not be loaded.", plugin)
                else:
                    APPLOG.warning("Plugin <%s> could not be loaded.", plugin)
    return dispatcher


def _get_handle():
    if '://' in str(rcParams['serial.port']).lower():
        params = rcParams['serial']
        url = params.pop('port')
        hdl = serial.serial_for_url(url=url, **params)
    else:
        hdl = serial.Serial(**rcParams['serial'])
    return hdl


def atgmlogger(args, listener=None, handle=None, dispatcher=None):
    """

    Parameters
    ----------
    args : Namespace
        Namespace containing parsed commandline arguments.
    listener
    handle
    dispatcher

    Returns
    -------

    """
    # Init Performance Counter
    t_start = time.perf_counter()

    _configure_applog()

    if listener is None:
        listener = SerialListener(handle or _get_handle())
    dispatcher = dispatcher or _get_dispatcher(collector=listener.collector,
                                               verbosity=args.verbose)

    # End Init Performance Counter
    t_end = time.perf_counter()
    if args.verbose:
        APPLOG.info("ATGMLogger started. Initialization time: %.4f", t_end -
                    t_start)

    try:
        if POSIX:
            # Listen for SIGHUP to tell logger that files have been rotated.
            # Note: Signal handler must be defined in main thread
            signal.signal(signal.SIGHUP,
                          lambda sig, frame: dispatcher.log_rotate())
        dispatcher.start()
        listener.listen()
    except KeyboardInterrupt:
        APPLOG.info("Keyboard Interrupt intercepted, initiating clean exit.")
        listener.exit()
        dispatcher.exit(join=False)
        APPLOG.debug("Dispatcher exited.")

    return 0
