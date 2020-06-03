# -*- coding: utf-8 -*-
# This file is part of ATGMLogger https://github.com/bradyzp/atgmlogger

import abc
import queue
import logging
import threading
from importlib import import_module

__all__ = ['PluginInterface', 'PluginDaemon', 'load_plugin']
LOG = logging.getLogger(__name__)


class PluginInterface(threading.Thread, metaclass=abc.ABCMeta):
    options = []

    def __init__(self, daemon=False):
        super().__init__(name=self.__class__.__name__, daemon=daemon)
        self._exitSig = threading.Event()
        self._queue = queue.Queue()
        self._configured = False
        self._context = None

    def consumes(self, item) -> bool:
        return type(item) in self.consumer_type()

    @staticmethod
    @abc.abstractmethod
    def consumer_type() -> set:
        """Return an iterable (set, list, tuple, dict) with item types that this
        plugin consumes e.g. str, list, Command etc."""
        return {None}

    @classmethod
    def condition(cls, *args):
        return False

    @abc.abstractmethod
    def run(self):
        pass

    def set_context(self, context):
        self._context = context

    @property
    def context(self):
        return self._context

    def configure(self, **options):
        LOG.debug("Configuring Plugin: {} with options: {}".format(
            self.__class__.__name__, options))
        for key, value in options.items():
            lkey = str(key).lower()
            if lkey in self.options:
                if isinstance(self.options, dict):
                    dtype = self.options[lkey]
                    if not isinstance(value, dtype):
                        print("Invalid option value provided for key: ", key)
                        continue
                setattr(self, lkey, value)
        self._configured = True

    def exit(self, join=False):
        if join:
            self.queue.join()
        self._exitSig.set()
        if self.is_alive():
            self.queue.put(None)
            self.join()

    def put(self, item):
        try:
            self.queue.put_nowait(item)
        except queue.Full:
            pass

    def get(self, block=True, timeout=None):
        """
        Wrapper around internal Queue object.

        Returns
        -------
        item : Any
            Item from queue if available,
            else raise queue.Empty

        """
        return self.queue.get(block=block, timeout=timeout)

    def task_done(self):
        try:
            self.queue.task_done()
        except AttributeError:
            pass

    @property
    def configured(self) -> bool:
        return self._configured

    @property
    def exiting(self) -> bool:
        return self._exitSig.is_set()

    @property
    def queue(self) -> queue.Queue:
        return self._queue

    @queue.setter
    def queue(self, value):
        self._queue = value


class PluginDaemon(threading.Thread, metaclass=abc.ABCMeta):
    options = {}

    def __init__(self, **kwargs):
        super().__init__(daemon=True)
        self._context = kwargs.get('context', None)
        self._data = kwargs.get('data', None)

    @property
    def data(self):
        return self._data

    # For compatibility with PluginInterface
    def put(self, item):
        self._data = item

    @property
    def context(self):
        return self._context

    @context.setter
    def context(self, value):
        self._context = value

    # For compatibility with PluginInterface
    def set_context(self, value):
        self._context = value

    @classmethod
    @abc.abstractmethod
    def condition(cls, item=None):
        return False

    @classmethod
    def configure(cls, **options):
        for key, value in {str(k).lower(): v for k, v in options.items()
                           if k in cls.options}.items():
            if isinstance(cls.options, dict):
                dtype = cls.options[key]
                if not isinstance(value, dtype):
                    try:
                        value = dtype(value)
                    except TypeError:
                        print("TypeError: invalid type provided for key: {}, "
                              "should be {}".format(key, dtype))
            setattr(cls, key, value)

    @abc.abstractmethod
    def run(self):
        pass


def load_plugin(name, path=None, register=True, **plugin_params):
    """
    Load a runtime plugin from either the default module path
    (atgmlogger.plugins), or from the specified path.
    Optionally register the newly imported plugin with the dispatcher class,
    passing specified keyword arguments 'plugin_params'

    Parameters
    ----------
    name : str
        Plugin module name (e.g. gpio for module file named gpio.py)
    path : str
        Alternate path to load module from, otherwise the default is to load
        from __package__.plugins
    register : bool

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
        pkg_name = path or "%s.plugins" % __package__.split('.')[0]
        plugin = import_module(".%s" % name, package=pkg_name)
    except ImportError:
        raise

    try:
        klass = getattr(plugin, '__plugin__')
    except AttributeError:
        raise ImportError("__plugin__ is not defined in plugin module %s." % name)
    if isinstance(klass, str):
        klass = getattr(plugin, klass)
    if klass is None:
        raise ImportError("__plugin__ is None in plugin module %s." % name)
    if not issubclass(klass, PluginInterface) and not issubclass(klass, PluginDaemon):
        klass = type(name, (klass, PluginInterface), {})
    if register:
        from ..dispatcher import Dispatcher
        Dispatcher.register(klass, **plugin_params)

    return klass
