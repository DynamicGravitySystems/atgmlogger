# -*- coding: utf-8 -*-

# PyTest utility module containing Dispatch test modules
import threading
import queue
from atgmlogger.dispatcher import Dispatcher, ModuleInterface


class SimplePacket:
    def __init__(self, value):
        self.value = value

    def __repr__(self):
        return "<SimplePacket({})>".format(self.value)


@Dispatcher.register
class BasicModule(ModuleInterface):
    consumerType = SimplePacket
    # accumulator = []  # For testing assertion purposes

    def __init__(self):
        super().__init__()
        self._exitSig = threading.Event()
        self._queue = queue.Queue()
        self.accumulator = []

    def run(self):
        while not self.exiting:
            try:
                item = self.queue.get(block=True, timeout=0.1)
            except queue.Empty:
                continue
            assert isinstance(item, self.consumerType)
            self.accumulator.append(item.value)
            self.queue.task_done()

    def configure(self, **options):
        pass


@Dispatcher.register
class ComplexModule(ModuleInterface):
    consumerType = SimplePacket

    def __init__(self):
        super().__init__()
        self._exitSig = threading.Event()
        self._queue = queue.Queue()
        self.accumulator = []

    def run(self):
        while not self.exiting:
            try:
                item = self.queue.get(block=True, timeout=0.1)
            except queue.Empty:
                continue
            self.accumulator.append(item.value * 10)
            self.queue.task_done()

    def configure(self, **options):
        pass

