# -*- coding: utf-8 -*-

from enum import Enum


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
