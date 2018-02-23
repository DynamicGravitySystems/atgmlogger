# -*- coding: utf-8 -*-

# PyTest utility module containing Dispatch test modules
import logging
import threading
import queue

from atgmlogger.plugins import PluginInterface
from atgmlogger.dispatcher import Dispatcher
from atgmlogger.logger import DataLogger

_log = logging.getLogger(__name__)


class SimplePacket:
    def __init__(self, value):
        self.value = value

    def __repr__(self):
        return "<SimplePacket({})>".format(self.value)


@Dispatcher.register
class BasicModule(PluginInterface):
    def __init__(self):
        super().__init__()
        self._exitSig = threading.Event()
        self.accumulator = []

    @staticmethod
    def consumes(item):
        return isinstance(item, SimplePacket)

    def run(self):
        while not self.exiting:
            try:
                item = self.queue.get(block=True, timeout=0.1)
            except queue.Empty:
                continue
            assert self.consumes(item)
            self.accumulator.append(item.value)
            self.queue.task_done()

    def configure(self, **options):
        pass


@Dispatcher.register
class ComplexModule(PluginInterface):
    def __init__(self):
        super().__init__()
        self._exitSig = threading.Event()
        self.accumulator = []
        self.count = 0

    @staticmethod
    def consumes(item):
        return isinstance(item, SimplePacket)

    def run(self):
        while not self.exiting:
            try:
                item = self.queue.get(block=True, timeout=0.1)
            except queue.Empty:
                continue
            self.count += 1
            self.accumulator.append(item.value * 10)
            self.queue.task_done()

    def configure(self, **options):
        pass


class TestLogger:
    def __init__(self):
        self.data = []

    def log(self, level, data):
        self.data.append((level, data))


class LoggerAdapter(DataLogger):
    def __init__(self):
        super().__init__()
        self._logger = TestLogger()

    def data(self):
        return self._logger.data


