# -*- coding: utf-8 -*-

import os
import logging
import threading
import queue
from weakref import WeakSet

_log = logging.getLogger()
TIMEOUT = float(os.getenv("ATGM_TIMEOUT", '0.5'))

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


class Dispatcher(threading.Thread):
    _listeners = WeakSet()
    _oneshots = WeakSet()
    _params = {}

    @classmethod
    def register(cls, klass, **params):
        if klass.consumerType is None:
            raise ValueError("Plugin/Listener {} consumerType is not defined."
                             .format(klass))
        if klass not in cls._listeners and not klass.oneshot:
            _log.debug("Registering class in dispatcher: {}".format(klass))
            cls._listeners.add(klass)
            cls._params[klass] = params
        elif klass not in cls._oneshots and klass.oneshot:
            _log.debug("Registering class as oneshot")
            cls._oneshots.add(klass)
            try:
                klass.configure(**params)
            except (AttributeError, TypeError):
                pass
            cls._params[klass] = params
        return klass

    @classmethod
    def detach(cls, klass):
        _log.debug("Attempting to detach %s", str(klass))
        if klass in cls._listeners:
            cls._listeners.remove(klass)
            del cls._params[klass]
        elif klass in cls._oneshots:
            cls._oneshots.remove(klass)

    @classmethod
    def detach_all(cls):
        cls._listeners.clear()
        cls._oneshots.clear()
        cls._params = {}

    @classmethod
    def registered_listeners(cls):
        return cls._listeners

    def __init__(self, sigExit=None):
        super().__init__(name=self.__class__.__name__)
        self.sigExit = sigExit or threading.Event()
        self._queue = queue.Queue()
        self._threads = []

    @property
    def message_queue(self):
        return self._queue

    def put(self, item):
        self._queue.put_nowait(item)

    def run(self):
        for listener in self._listeners:
            try:
                instance = listener()
                instance.configure(**self._params[listener])
            except TypeError:
                _log.exception("Error instantiating listener.")
                continue
            else:
                instance.start()
                self._threads.append(instance)

        while not self.sigExit.is_set():
            try:
                item = self._queue.get(block=True, timeout=TIMEOUT)
            except queue.Empty:
                continue
            for thread in self._threads:
                if not thread.is_alive():
                    continue
                if isinstance(item, thread.consumerType):
                    thread.put(item)

            for daemon in self._oneshots:
                if hasattr(daemon, 'condition') and daemon.condition():
                    print("Initializing daemon: {} condition is True"
                          .format(daemon))
                    oneshot = daemon()
                    oneshot.configure(**self._params.get(daemon, {}))
                    oneshot.start()
                    oneshot.put(item)

            self._queue.task_done()

        for thread in self._threads:
            thread.exit(join=True)

    def exit(self, join=False):
        if join:
            _log.debug("Waiting for queue to empty.")
            self._queue.join()
            _log.debug("Queue joined, setting sigExit")
        self.sigExit.set()

    def get_instance(self, klass):
        for obj in self._threads:
            if isinstance(obj, klass):
                return obj
