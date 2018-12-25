# -*- coding: utf-8 -*-

import pytest
import json
import serial
import threading
from pathlib import Path

from atgmlogger.runconfig import RunConfig
from atgmlogger.dispatcher import Dispatcher


@pytest.fixture(scope="module", params=["atgmlogger/install/atgmlogger.json"])
def cfg_dict(request):
    with open(request.param, 'r') as fd:
        config = json.load(fd)
    return config


@pytest.fixture
def rcParams():
    return RunConfig(path=Path('atgmlogger/install/atgmlogger.json'))


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


@pytest.fixture(params=["/var/log/", Path("/var/log")])
def logpath(request):
    return request.param


@pytest.fixture
def mountpoint(tmpdir):
    path = tmpdir.mkdir('mount')
    return Path(str(path))


