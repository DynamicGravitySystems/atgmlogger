# -*- coding: utf-8 -*-

# PyTest utility module containing Dispatch tests modules for atgmlogger
import logging
import threading

from atgmlogger.plugins import PluginInterface
from atgmlogger.dispatcher import Dispatcher

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
    def consumer_type():
        return {SimplePacket}

    def run(self):
        while not self.exiting:
            item = self.queue.get(block=True, timeout=None)
            if item is None:
                self.task_done()
                continue
            assert self.consumes(item)
            self.accumulator.append(item.value)
            self.task_done()

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
    def consumer_type():
        return {SimplePacket}

    def run(self):
        while not self.exiting:
            item = self.queue.get(block=True, timeout=None)
            if item is None:
                self.task_done()
                continue
            self.count += 1
            self.accumulator.append(item.value * 10)
            self.task_done()

    def configure(self, **options):
        pass


class TestLogger:
    def __init__(self):
        self.data = []

    def log(self, level, data):
        self.data.append((level, data))

