# -*- coding: utf-8 -*-

import abc
import logging
import threading
import queue
from importlib import import_module
from weakref import WeakSet

_log = logging.getLogger()

"""Premise: centralize and abstract the launching of threads and feeding of
data to one location to allow for a modular/pluggable architecture.

This could be a way to allow 'modules' to be loaded on demand, 
a threadable class could be registered with the dispatcher, informing the 
dispatcher of the types of objects it acts on, the dispatcher could then 
push any objects matching the criteria into the appropriate registerd 
classes internal queue.
An interface of some sort would need to be defined to say what 
characteristics/standards must be followed by any pluggable module.

Registered modules could then be enabled/disabled on startup via 
configuration file directives. Parameters could then be defined within 
the module directive for the tweaking of the modules.

=====
Considering the nature of how we want to deal with plugins:

Configuration file will have a 'plugin' block where the keys are the names of 
the plugin module, the value (dict) can contain optional parameters, 
like when the plugin is executed, or other params specific to the plugin, 
e.g. for an email sending plugin the smtp server/credentials would need to be 
specified.

All plugins must be python modules (probably self contained?) and must be 
located in a specific directory (consider a search path like for the config 
file).
Use module level variable pointing to the 'exported' class?
e.g. PLUGIN = MyPluginClass

So the general concept:

Main loads config -> for plugin in config try to load plugin module -> 
register the plugin class with dispatcher -> start dispatcher.

Another though: attempt to register plugin class with ModuleInterface ABC to 
verify that it conforms to the spec, without requiring the plugins to 
directly subclass ModuleInterface
^ This doesn't work as ABC.register doesn't check to verify interface 
implementation.
What I might be able to do is dynamically create a Wrapper which subclasses 
the plugin AND ModuleInterface - this will then raise a TypeError on 
instantiation if the plugin class does not implement the abstract methods.
This will also allow the plugin to indirectly override concrete methods in 
the ABC.
e.g.

class PluginWrapper(Plugin, ModuleInterface):
    pass
    
p1 = PluginWrapper()
# raises TypeError if Plugin does not implement ModuleInterface abstractmethods


"""


class ModuleInterface(threading.Thread, metaclass=abc.ABCMeta):
    consumerType = None

    def __init__(self):
        super().__init__()
        self._exitSig = threading.Event()
        self._queue = queue.Queue()

    @abc.abstractmethod
    def run(self):
        pass

    @abc.abstractmethod
    def configure(self, **options):
        pass

    def exit(self, join=False):
        if join:
            self._queue.join()
        self._exitSig.set()

    def put(self, item):
        if isinstance(item, self.consumerType):
            self._queue.put_nowait(item)

    @property
    def exiting(self):
        return self._exitSig.is_set()

    @property
    def queue(self) -> queue.Queue:
        return self._queue


def load_plugin(name, path=None):
    try:
        pkg_name = path or f"{__package__}.plugins"
        plugin = import_module(".%s" % name, package=pkg_name)
    except (ImportError, ModuleNotFoundError):
        raise
    base = getattr(plugin, 'PLUGIN', None)
    if base is not None:
        wrapper = type(name, (base, ModuleInterface), {})
        return wrapper
    else:
        return None


class Dispatcher(threading.Thread):
    _dispatch_registry = WeakSet()  # rename to _listeners?

    @classmethod
    def register(cls, klass, **params):
        if klass not in cls._dispatch_registry:
            _log.debug("Registering class in dispatcher: {}".format(klass))
            cls._dispatch_registry.add(klass)
        return klass

    @classmethod
    def registered_modules(cls):
        return cls._dispatch_registry

    def __init__(self, sigExit=None):
        super().__init__(name=self.__class__.__name__)
        self.sigExit = sigExit or threading.Event()
        self._queue = queue.Queue()
        self._enabled = WeakSet({klass for klass in self._dispatch_registry})
        self._threads = []

    def put(self, item):
        self._queue.put_nowait(item)

    def run(self):
        self._threads = [klass() for klass in self._dispatch_registry if
                         klass in self._enabled]
        for thread in self._threads:
            thread.start()

        while not self.sigExit.is_set():
            try:
                item = self._queue.get(block=True, timeout=.1)
            except queue.Empty:
                continue
            for thread in self._threads:
                if isinstance(item, thread.consumerType):
                    thread.put(item)
            self._queue.task_done()
        for thread in self._threads:
            thread.exit(join=True)

    def exit(self):
        _log.debug("Waiting for queue to empty.")
        self._queue.join()
        _log.debug("Queue joined, setting sigExit")
        self.sigExit.set()

    def detach(self, klass):
        if klass in self._enabled:
            self._enabled.remove(klass)

    def get_instance(self, klass):
        for obj in self._threads:
            if isinstance(obj, klass):
                return obj
        return None
