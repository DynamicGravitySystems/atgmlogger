# -*- coding: utf-8 -*-

import queue
import threading
from weakref import WeakSet

from . import APPLOG
from .plugins import PluginInterface, PluginDaemon

POLL_INTV = 1


class Dispatcher(threading.Thread):
    _listeners = set()  # Registered Regular Plugins
    _daemons = set()  # Registered Daemon Plugins
    _params = {}
    _runlock = threading.Lock()

    @classmethod
    def register(cls, klass, **params):
        cls.acquire_lock()
        assert klass is not None
        if issubclass(klass, PluginInterface) and klass not in cls._listeners:
            APPLOG.debug("Registering class {} in dispatcher.".format(klass))
            cls._listeners.add(klass)
            cls._params[klass] = params
        elif issubclass(klass, PluginDaemon) and klass not in cls._daemons:
            APPLOG.debug("Registering class as Daemon")
            cls._daemons.add(klass)
            try:
                klass.configure(**params)
            except (AttributeError, TypeError):
                APPLOG.warning("Unable to configure daemon class: ", klass)
            cls._params[klass] = params
        else:
            APPLOG.info("Class %s is already registered in dispatcher.",
                        str(klass))
        cls.release_lock()
        return klass

    @classmethod
    def detach(cls, klass):
        APPLOG.debug("Attempting to detach %s", str(klass))
        if klass in cls._listeners:
            cls._listeners.remove(klass)
            del cls._params[klass]
        elif klass in cls._daemons:
            cls._daemons.remove(klass)

    @classmethod
    def detach_all(cls):
        cls._listeners.clear()
        cls._daemons.clear()
        cls._params = {}

    @classmethod
    def acquire_lock(cls, blocking=True):
        APPLOG.debug("%s acquired lock.", cls)
        return cls._runlock.acquire(blocking=blocking)

    @classmethod
    def release_lock(cls):
        APPLOG.debug("%s releasing lock.", cls)
        cls._runlock.release()

    def __init__(self, collector=None, sigExit=None):
        super().__init__(name=self.__class__.__name__)
        self.sigExit = sigExit or threading.Event()
        self._queue = collector or queue.Queue()
        self._threads = set()
        self._active_daemons = WeakSet()
        self._context = AppContext(self.message_queue)
        self._tick = 0

    @classmethod
    def __contains__(cls, item):
        return item in cls._listeners or item in cls._daemons

    @property
    def message_queue(self):
        return self._queue

    def put(self, item):
        self._queue.put_nowait(item)

    def run(self):
        self.acquire_lock(blocking=True)
        APPLOG.debug("Dispatcher run acquired runlock")

        # Create perpetual listener threads
        listener_map = {}  # Todo: Better name for this?
        for listener in self._listeners:
            try:
                instance = listener()
                instance.set_context(self._context)
                instance.configure(**self._params[listener])
            except TypeError:
                APPLOG.exception("Error instantiating listener.")
                continue
            else:
                ctypes = instance.consumer_type()
                for ctype in ctypes:
                    consumer_set = listener_map.setdefault(ctype, WeakSet())
                    consumer_set.add(instance)

                instance.start()
                self._threads.add(instance)

        while not self.sigExit.is_set():
            self._tick += 1
            # TODO: Enable polling of plugins even if no data is incoming
            # e.g. USB copy should still run even when no input stream
            try:
                item = self._queue.get(block=True, timeout=POLL_INTV)
            except queue.Empty:
                item = None
            else:
                for subscriber in listener_map.get(type(item), set()):
                    subscriber.put(item)
                self._queue.task_done()

            # Check if a daemon needs to be spawned
            for daemon in self._daemons:
                if daemon.condition(item):
                    try:
                        inst = daemon(context=self._context, data=item)
                        inst.start()
                    except TypeError:
                        APPLOG.exception()
                else:
                    continue

        self.release_lock()

    def _exit_threads(self, join=False):
        for thread in self._threads:
            thread.exit(join=join)
        for daemon in self._active_daemons:
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
    def __init__(self, led, priority=5, frequency=0.1, continuous=False):
        self.led = led
        self.priority = priority
        self.frequency = frequency
        self.duration = 0
        self.until_stopped = continuous

    def __lt__(self, other):
        return self.priority < other.priority


class Command:
    def __init__(self, cmd, **params):
        self.cmd = cmd
        self.params = params


class AppContext:
    def __init__(self, listener_queue):
        self._queue = listener_queue

    def blink(self, led='data', freq=0.04):
        cmd = Blink(led=led, frequency=freq)
        self._queue.put_nowait(cmd)

    def blink_until(self, until: threading.Event=None, led='usb', freq=0.03):
        # TODO: Possibly allow caller to pass event that the caller can set
        # to end the blink
        cmd = Blink(led=led, frequency=freq, continuous=True)
        self._queue.put_nowait(cmd)

    def log_rotate(self):
        cmd = Command('logrotate')
        self._queue.put_nowait(cmd)
