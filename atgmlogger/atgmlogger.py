# -*- coding: utf-8 -*-

"""
Advanced Technology Gravity Meter - Logger (AGTMLogger)

Linux/Raspberry PI utility designed to record serial data from Dynamic
Gravity Systems' (DGS) AT1A and AT1M advanced technology gravity meters.

"""

import time
import queue
import itertools
import logging.config
import signal
import threading
from pathlib import Path

import serial

from . import POSIX
from .runconfig import rcParams
from .dispatcher import Dispatcher
from .plugins import load_plugin
from .types import DataLine

LOG = logging.getLogger('atgmlogger.main')
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

    def __call__(self, *args, **kwargs):
        return self.listen()

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
            self._queue.put_nowait(DataLine(data))

        LOG.debug("Exiting listener.listen() method, and closing serial "
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


def _init_dispatcher(collector=None, plugins=None, verbosity=0):
    """Loads plugin(s) and returns initialized Dispatcher"""
    dispatcher = Dispatcher(collector=collector)

    # Explicitly import and register the DataLogger 'plugin'
    from .logger import DataLogger

    logfile = Path(rcParams['logging.logdir']).joinpath('gravdata.dat')
    dispatcher.register(DataLogger, logfile=logfile)

    for plugin in plugins or []:
        try:
            klass = load_plugin(plugin)
            dispatcher.register(klass, **plugins[plugin])
            # load_plugin(plugin, register=True, **plugins[plugin])
            LOG.info("Loaded plugin: %s", plugin)
        except ImportError:
            # Note: ModuleNotFoundError is not implemented until py3.6
            if verbosity is not None and verbosity >= 2:
                LOG.exception("Plugin <%s> could not be loaded. Continuing.",
                              plugin)
            else:
                LOG.warning("Plugin <%s> could not be loaded. Continuing.",
                            plugin)
    return dispatcher


def _get_handle(**params):
    """Return a serial handle from a url string or device name"""
    url_or_dev = params.pop('port')
    if '://' in str(url_or_dev).lower():
        hdl = serial.serial_for_url(url=url_or_dev, **params)
    else:
        hdl = serial.Serial(port=url_or_dev, **params)
    return hdl


def atgmlogger(verbosity=0, listener=None, handle=None, dispatcher=None):
    """
    Main execution method, expects args passed from a Namespace created
    by an argparse class.
    listener, handle, and dispatcher can optionally be injected as dependencies,
    otherwise standard instances will be created via rcParams options and args.

    Parameters
    ----------
    verbosity : int
        Verbosity level for logging output
    listener : SerialListener
        Callable function/class with exit method
    handle : serial.Serial
        PySerial Serial object for Serial IO
    dispatcher : Dispatcher

    """
    # Initialization Performance Counter
    t_start = time.perf_counter()

    # Initialize dependencies if not supplied
    if handle is None:
        handle = _get_handle(**rcParams['serial'])

    if listener is None:
        listener = SerialListener(handle)

    if dispatcher is None:
        dispatcher = _init_dispatcher(collector=listener.collector,
                                      plugins=rcParams.get('plugins', None),
                                      verbosity=verbosity)

    # End Initialization Performance Counter
    t_end = time.perf_counter()
    if verbosity:
        LOG.info("ATGMLogger started. Initialization time: %.4f",
                 t_end - t_start)
    try:
        if POSIX:
            # Listen for SIGHUP to notify logger that files have been rotated.
            # Note: Signal handlers must be defined in main thread (here)
            signal.signal(signal.SIGHUP,
                          lambda sig, frame: dispatcher.signal())
        dispatcher.start()
        listener.listen()
    except KeyboardInterrupt:
        LOG.info("Keyboard Interrupt intercepted, cleaning up and exiting.")
        listener.exit()
        dispatcher.exit(join=False)
        LOG.debug("Dispatcher exited.")

    return 0
