# -*- coding: utf-8 -*-

import threading
from pathlib import Path

import pytest
import serial

from atgmlogger.dispatcher import Dispatcher
from atgmlogger.runconfig import _ConfigParams


@pytest.fixture(scope="module")
def cfg_dict():
    return {
        "version": 0.4,
        "serial": {
            "port": "/dev/serial0",
            "baudrate": 57600,
            "bytesize": 8,
            "parity": "N",
            "stopbits": 1
        },
        "logging": {
            "logdir": "/var/log/atgmlogger"
        },
        "usb": {
            "mount": "/media/removable",
            "copy_level": "debug"
        },
        "plugins": {
            "gpio": {
                "mode": "board",
                "data_pin": 11,
                "usb_pin": 13,
                "freq": 0.04
            },
            "usb": {
                "mountpath": "/media/removable",
                "logdir": "/var/log/atgmlogger",
                "patterns": ["*.dat", "*.log", "*.gz", "*.dat.*"]
            },
            "timesync": {
                "interval": 1000
            }
        }
    }


@pytest.fixture
def rcParams():
    return _ConfigParams(path='atgmlogger/atgmlogger.json')


@pytest.fixture()
def handle():
    hdl = serial.serial_for_url('loop://', baudrate=57600, timeout=None)
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
    if disp.is_alive():
        disp.exit(join=True)
    disp.detach_all()


@pytest.fixture(params=["/var/log/", Path("/var/log")])
def logpath(request):
    return request.param


@pytest.fixture
def mountpoint(tmpdir):
    path = tmpdir.mkdir('mount')
    return Path(str(path))
