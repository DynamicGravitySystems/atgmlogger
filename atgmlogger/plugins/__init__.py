# -*- coding: utf-8 -*-

import abc
import queue
import threading
from importlib import import_module

__all__ = ['command', 'gpio', 'usb', 'PluginInterface']


class PluginInterface(threading.Thread, metaclass=abc.ABCMeta):
    consumerType = None
    options = []
    oneshot = False  # or use a method i.e. is_oneshot() -> bool?

    @abc.abstractmethod
    def __init__(self):
        super().__init__()
        self._exitSig = threading.Event()
        self._queue = queue.Queue()
        self._configured = False

    @abc.abstractmethod
    def run(self):
        pass

    @abc.abstractmethod
    def configure(self, **options):
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
            self._queue.join()
        self._exitSig.set()

    def put(self, item):
        if isinstance(item, self.consumerType):
            self._queue.put_nowait(item)

    def get(self, block=True, timeout=0.1):
        # Raises queue.Empty if queue empty after timeout
        return self._queue.get(block=block, timeout=timeout)

    @property
    def configured(self) -> bool:
        return self._configured

    @property
    def exiting(self):
        return self._exitSig.is_set()

    @property
    def queue(self) -> queue.Queue:
        return self._queue

    @queue.setter
    def queue(self, value):
        self._queue = value


def load_plugin(name, path=None, register=True, **plugin_params):
    """

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
    except (ImportError, ModuleNotFoundError):
        raise
    klass = getattr(plugin, '__plugin__')
    if klass is None:
        print("Invalid plugin loaded.")
        return
    if not issubclass(klass, PluginInterface):
        wrapper = type(name, (klass, PluginInterface), {})
        if register:
            from ..dispatcher import Dispatcher
            Dispatcher.register(wrapper, **plugin_params)
        return wrapper
    else:
        if register:
            from ..dispatcher import Dispatcher
            Dispatcher.register(klass, **plugin_params)
        return klass
