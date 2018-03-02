# -*- coding: utf-8 -*-

import queue
import threading
from weakref import WeakSet

from . import APPLOG


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

"""


class Dispatcher(threading.Thread):
    _listeners = WeakSet()
    _oneshots = set()
    _locks = {}
    _params = {}
    _runlock = threading.Lock()

    @classmethod
    def register(cls, klass, **params):
        cls.acquire_lock()
        assert klass is not None
        if klass not in cls._listeners and not klass.oneshot:
            APPLOG.debug("Registering class {} in dispatcher.".format(klass))
            cls._listeners.add(klass)
            cls._params[klass] = params
        elif klass not in cls._oneshots and klass.oneshot:
            APPLOG.debug("Registering class as oneshot")
            cls._oneshots.add(klass)
            try:
                klass.configure(**params)
            except (AttributeError, TypeError):
                pass
            cls._params[klass] = params
        cls.release_lock()
        return klass

    @classmethod
    def detach(cls, klass):
        APPLOG.debug("Attempting to detach %s", str(klass))
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
    def acquire_lock(cls, blocking=True):
        APPLOG.debug("%s acquired runlock", cls)
        return cls._runlock.acquire(blocking=blocking)

    @classmethod
    def release_lock(cls):
        APPLOG.debug("%s releasing runlock", cls)
        cls._runlock.release()

    def __init__(self, collector=None, sigExit=None):
        super().__init__(name=self.__class__.__name__)
        self.sigExit = sigExit or threading.Event()
        self._queue = collector or queue.Queue()
        self._threads = set()
        self._daemons = WeakSet()

    @classmethod
    def __contains__(cls, item):
        return item in cls._listeners or item in cls._oneshots

    @property
    def message_queue(self):
        return self._queue

    def put(self, item):
        self._queue.put_nowait(item)

    def run(self):
        self.acquire_lock(blocking=True)
        APPLOG.debug("Dispatcher run acquired runlock")
        context = AppContext(self._queue)
        consumers = {}  # Todo: Better name for this?
        for listener in self._listeners:
            try:
                instance = listener()
                instance.set_context(context)
                instance.configure(**self._params[listener])
            except TypeError:
                APPLOG.exception("Error instantiating listener.")
                continue
            else:
                ctypes = instance.consumer_type()
                for ctype in ctypes:
                    consumer_set = consumers.setdefault(ctype, WeakSet())
                    consumer_set.add(instance)

                instance.start()
                self._threads.add(instance)

        while not self.sigExit.is_set():
            item = self._queue.get(block=True, timeout=None)
            if item is None:
                self._queue.task_done()
                continue
            subscribers = consumers.get(type(item), None)
            if subscribers is None:
                # Maybe warn once when this happens.
                pass

            else:
                for subscriber in subscribers:
                    subscriber.put(item)
            self._queue.task_done()

            # TODO: Consider adding an optional tick counter to run oneshots
            # only every 5 ticks for example?
            # Need to be careful about oneshots that depend on a tick count
            # e.g. TimeSync - the interval might be multiplied if we do this.
            for oneshot in self._oneshots:
                # Optimization to only create the set if first condition passes
                if oneshot.condition(item) and oneshot not in {type(daemon) for daemon in self._daemons}:
                    daemon = oneshot()
                    daemon.set_context(context)
                    daemon.start()
                    daemon.put(item)
                    self._daemons.add(daemon)
                    del daemon

        self.release_lock()

    def _exit_threads(self, join=False):
        for thread in self._threads:
            thread.exit(join=join)
        for daemon in self._daemons:
            daemon.exit(join=join)

    def exit(self, join=False):
        self.sigExit.set()
        if self.is_alive():
            # We must check if we're still alive to see if it's necessary to
            # put a None object on the queue, else if we join the queue it
            # may block indefinitely
            self._queue.put(None)
        self._exit_threads(join=join)
        if join:
            self.join()

    def get_instance_of(self, klass):
        for obj in self._threads:
            if isinstance(obj, klass):
                return obj

    def log_rotate(self):
        """Call this method to notify any subscriber threads that logs have
        been rotated, and handles may need to be recreated."""
        self.put(Command('rotate'))


class Blink:
    def __init__(self, led, priority=5, frequency=0.1):
        self.led = led
        self.priority = priority
        self.frequency = frequency

    def __lt__(self, other):
        return self.priority < other.priority


class Command:
    def __init__(self, cmd, **params):
        self.cmd = cmd
        self.params = params


class AppContext:
    def __init__(self, listener_queue):
        self._queue = listener_queue

    # def blink(self, led='data', freq=0.1):
    def blink(self, led='data', freq=0.04):
        cmd = Blink(led=led, frequency=freq)
        self._queue.put_nowait(cmd)

    def blink_until(self, until: threading.Event=None, led='usb', freq=0.1):
        raise NotImplementedError("blink_until not implemented yet.")
        until = until or threading.Event()
        pass

    def log_rotate(self):
        cmd = Command('logrotate')
        self._queue.put_nowait(cmd)
