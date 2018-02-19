# -*- coding: utf-8 -*-

import pytest
import json
import serial
import threading


@pytest.fixture(scope="module", params=["test/.atgmlogger"])
def cfg_dict(request):
    with open(request.param, 'r') as fd:
        config = json.load(fd)
    return config


@pytest.fixture(scope="module")
def handle():
    return serial.serial_for_url('loop://', baudrate=57600, timeout=0.1)


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
    if not sig.is_set():
        sig.set()
