# -*- coding: utf-8 -*-

from pathlib import Path

from atgmlogger.logger import DataLogger

LINE = "$UW,81242,-1948,557,4807924,307,872,204,6978,7541,-70,305,266," \
       "4903912,0.000000,0.000000,0.0000,0.0000,{idx}"


class MockAppContext:
    def blink(self, *args, **kwargs):
        pass


def test_simple_logger(tmpdir):
    test_dir = Path(str(tmpdir.mkdir('logs')))
    log_file = test_dir.joinpath('gravdata.dat')

    logger = DataLogger()
    logger.set_context(MockAppContext())
    _params = dict(logfile=log_file)
    logger.configure(**_params)

    for key, value in _params.items():
        assert hasattr(logger, key)
        assert value == getattr(logger, key)

    accumulator = []

    logger.start()
    for i in range(1000):
        item = LINE.format(idx=i)
        accumulator.append(item)
        logger.put(item)

    logger.exit(join=True)
    assert not logger.is_alive()

    with log_file.open('r') as fd:
        for i, line in enumerate(fd):
            assert accumulator[i] == line.strip()
