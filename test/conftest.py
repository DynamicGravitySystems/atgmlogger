# -*- coding: utf-8 -*-

import pytest
import json
import serial
import threading

from atgmlogger import _ConfigParams
from atgmlogger.dispatcher import Dispatcher


@pytest.fixture(scope="module", params=["test/.atgmlogger"])
def cfg_dict(request):
    with open(request.param, 'r') as fd:
        config = json.load(fd)
    return config


@pytest.fixture
def rcParams():
    return _ConfigParams(path='test/.atgmlogger')


@pytest.fixture()
def handle():
    hdl = serial.serial_for_url('loop://', baudrate=57600, timeout=0.1)
    yield hdl
    hdl.close()


@pytest.fixture
def logger():
    class CustomLogger:
        def __init__(self):
            self.accumulator = list()

        def log(self, level, data):
            self.accumulator.append(data)
    return CustomLogger()


@pytest.fixture
def sigExit():
    sig = threading.Event()
    yield sig
    sig.set()


@pytest.fixture
def dispatcher():
    disp = Dispatcher()
    yield disp
    disp.exit()
