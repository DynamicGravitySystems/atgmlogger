# -*- coding: utf-8 -*-

import pytest
import datetime
from pathlib import Path
from atgmlogger.logger import SimpleLogger


LINE = "$UW,81242,-1948,557,4807924,307,872,204,6978,7541,-70,305,266," \
       "4903912,0.000000,0.000000,0.0000,0.0000,{idx}"


def test_simple_logger(tmpdir):

    test_dir = Path(tmpdir.mkdir('logs'))
    log_file = test_dir.joinpath('gravdata.dat')
    # print("Logging test_dir: ", test_dir)
    # print("Initial grav file: ", log_file)

    logger = SimpleLogger()
    _params = dict(timeout=0.1, logfile=log_file)
    logger.configure(**_params)

    for key, value in _params.items():
        assert hasattr(logger, key)
        assert value == getattr(logger, key)

    accumulator = []

    print("Starting logger")
    logger.start()
    for i in range(1000):
        item = LINE.format(idx=i)
        accumulator.append(item)
        logger.put(item)
    logger.exit()

    with log_file.open('r') as fd:
        for i, line in enumerate(fd):
            assert accumulator[i] == line.strip()


def test_logger_rotate(tmpdir):
    test_dir = Path(tmpdir.mkdir('logs'))
    log_file = test_dir.joinpath('gravdata.dat')

    logger = SimpleLogger()
    _params = dict(timeout=0.1, logfile=log_file)
    logger.configure(**_params)

    accumulator = []
    print("Starting logger")
    logger.start()
    rot_time = None
    rot_idx = 500

    for i in range(1000):
        if i == rot_idx:
            logger.queue.join()
            logger.logrotate()
            rot_time = datetime.datetime.now().strftime('%Y%m%d-%H%M')
        item = LINE.format(idx=i)
        accumulator.append(item)
        logger.put(item)

    logger.exit(join=True)

    orig_file = test_dir.joinpath('gravdata.dat.'+rot_time)
    assert orig_file.exists()
    print(orig_file)
    assert log_file.exists()
    print(log_file)
    with orig_file.open('r') as fd:
        for i, line in enumerate(fd):
            assert accumulator[i] == line.strip()

    with log_file.open('r') as fd:
        for i, line in enumerate(fd):
            assert accumulator[rot_idx+i] == line.strip()





