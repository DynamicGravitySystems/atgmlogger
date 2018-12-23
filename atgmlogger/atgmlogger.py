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
from importlib import import_module

import serial

from .runconfig import rcParams
from .dispatcher import Dispatcher
from .plugins import PluginInterface, PluginDaemon
from . import POSIX, LOG_FMT, TRACE_LOG_FMT, DATE_FMT


LOG = logging.getLogger('atgmlogger.main')
ILLEGAL_CHARS = list(itertools.chain(range(0, 32), [255, 256]))


def load_plugin(name, register=True, **plugin_params):
    """
    Load a runtime plugin from either the default module path
    (atgmlogger.plugins), or from the specified path.
    Optionally register the newly imported plugin with the dispatcher class,
    passing specified keyword arguments 'plugin_params'

    Parameters
    ----------
    name : str
        Plugin module name (e.g. gpio for module file named gpio.py)
    register : bool
        If true, loaded plugin will be registered in the Dispatcher Singleton

    Raises
    ------
    AttributeError
        If plugin module does not have __plugin__ atribute defined
    ImportError, ModuleNotFoundError
        If plugin cannot be found or error importing plugin

    Returns
    -------
    Plugin class as defined by the module attribue __plugin__ if the plugin
    directly subclasses ModuleInterface.
    else, an empty adapter class is constructed with the plugin class and
    ModuleInterface as its base classes.

    """

    try:
        pkg_name = "%s.plugins" % __package__.split('.')[0]
        plugin = import_module(".%s" % name, package=pkg_name)
    except ImportError:
        raise
    else:
        klass = getattr(plugin, '__plugin__', None)

    if klass is None:
        raise ImportError('Plugin has no __plugin__ attribute.')

    if isinstance(klass, str):
        klass = getattr(plugin, klass)
    if klass is None:
        raise ImportError("__plugin__ is None in plugin module %s." % name)
    if not issubclass(klass, PluginInterface) and not issubclass(klass, PluginDaemon):
        # Attempt to create subclass of PluginInterface with imported plugin
        klass = type(name, (klass, PluginInterface), {})
    if register:
        Dispatcher.register(klass, **plugin_params)

    return klass


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
            self._queue.put_nowait(data)

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


def _get_dispatcher(collector=None, plugins=None, verbosity=0, exclude=None):
    """Loads plugin and returns instance of Dispatcher"""
    dispatcher = Dispatcher(collector=collector)

    # Explicitly import and register the DataLogger 'plugin'
    from .logger import DataLogger

    logfile = Path(rcParams['logging.logdir']).joinpath('gravdata.dat')
    dispatcher.register(DataLogger, logfile=logfile)

    plugins = plugins or rcParams['plugins']
    if plugins is not None:
        for plugin in plugins:
            try:
                load_plugin(plugin, register=True, **plugins[plugin])
                LOG.info("Loaded plugin: %s", plugin)
            except ImportError:  # ModuleNotFoundError not implemented until py3.6
                if verbosity is not None and verbosity >= 2:
                    LOG.exception("Plugin <%s> could not be loaded. Continuing.", plugin)
                else:
                    LOG.warning("Plugin <%s> could not be loaded. Continuing.", plugin)
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
    Main execution method, expects args passed from a Namespace created
    by an argparse class.
    listener, handle, and dispatcher can optionally be injected as dependencies,
    otherwise standard instances will be created via rcParams options and args.

    Parameters
    ----------
    args : Namespace
        Namespace containing parsed commandline arguments.
    listener : SerialListener
        Callable function/class with exit method
    handle : serial.Serial
        PySerial Serial object for Serial IO
    dispatcher : Dispatcher

    """
    # Init Performance Counter
    t_start = time.perf_counter()

    if listener is None:
        listener = SerialListener(handle or _get_handle())
    dispatcher = dispatcher or _get_dispatcher(collector=listener.collector,
                                               verbosity=args.verbose)

    # End Init Performance Counter
    t_end = time.perf_counter()
    if args.verbose:
        LOG.info("ATGMLogger started. Initialization time: %.4f", t_end - t_start)
    try:
        if POSIX:
            # Listen for SIGHUP to tell logger that files have been rotated.
            # Note: Signal handler must be defined in main thread
            signal.signal(signal.SIGHUP, lambda sig, frame: dispatcher.log_rotate())
        dispatcher.start()
        # print(logging.Logger.manager.loggerDict.keys())
        listener()
    except KeyboardInterrupt:
        LOG.info("Keyboard Interrupt intercepted, cleaning up and exiting.")
        listener.exit()
        dispatcher.exit(join=False)
        LOG.debug("Dispatcher exited.")

    return 0
