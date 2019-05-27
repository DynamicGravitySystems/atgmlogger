# -*- coding: utf-8 -*-

from enum import Enum


class Blink:
    def __init__(self, led, priority=5, frequency=0.1, continuous=False):
        self.led = led
        self.priority = priority
        self.frequency = frequency
        self.duration = 0
        self.until_stopped = continuous

    def __lt__(self, other):
        return self.priority < other.priority


class CommandSignals(Enum):
    SIGHUP = 1


class Command:
    def __init__(self, cmd, **params):
        self.cmd = cmd
        self.params = params


class DataLine:
    def __init__(self, data):
        self.data = data

    def __str__(self):
        return self.data
