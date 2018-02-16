# -*- coding: utf-8 -*-

import os
import sys
import copy
import threading
import datetime
import logging
import time
import queue
import multiprocessing as mp
from pathlib import Path
from pprint import pprint

from atgmlogger import atgmlogger, common, _ConfigParams

_log = logging.getLogger(__name__)
_log.setLevel(logging.DEBUG)
_log.addHandler(logging.StreamHandler(stream=sys.stderr))

SLEEPTIME = float(os.getenv('SLEEPTIME', .5))


def join_threads(threads, timeout=0.1):
    for thread in threads:
        try:
            thread.join(timeout=timeout)
        except:
            continue


def test_at1logger(handle, logger, sigExit):
    data_queue = queue.Queue()
    atgm = atgmlogger.SerialListener(handle,
                                     data_queue=data_queue,
                                     exit_sig=sigExit)
    listen_th = threading.Thread(target=atgm.listen, name='listener')

    cmd_listener = atgmlogger.CommandListener(atgm.commands,
                                              exit_sig=sigExit)
    writer = atgmlogger.DataLogger(data_queue,
                                   logger=logger,
                                   exit_sig=sigExit)

    threads = [listen_th, cmd_listener, writer]
    for thread in threads:
        thread.start()

    in_list = list()
    for i in range(0, 1001):
        decoded = "Line: {}".format(i)
        data = "Line: {}\n".format(i).encode('latin-1')
        in_list.append(decoded)
        handle.write(data)

    _log.debug("Sleeping for %.2f seconds.", SLEEPTIME)
    time.sleep(SLEEPTIME)
    sigExit.set()
    join_threads(threads)

    assert in_list == writer._internal_copy
    assert in_list == logger.accumulator


def test_mproc_queue(handle, logger, sigExit):
    # Test use of multiprocessing.Queue with listener and DataLogger
    data_queue = mp.Queue()
    atgm = atgmlogger.SerialListener(handle,
                                     data_queue=data_queue,
                                     exit_sig=sigExit)
    listener = threading.Thread(target=atgm.listen, name='listener')
    writer = atgmlogger.DataLogger(data_queue,
                                   logger=logger,
                                   exit_sig=sigExit)

    threads = [listener, writer]
    for thread in threads:
        thread.start()

    in_list = list()
    for i in range(0, 1001):
        decoded = "Line: {}".format(i)
        raw = "Line: {}\n".format(i).encode('latin-1')
        in_list.append(decoded)
        handle.write(raw)

    _log.debug("Sleeping for %.2f seconds.", SLEEPTIME)
    time.sleep(SLEEPTIME)
    sigExit.set()
    join_threads(threads)

    assert in_list == writer._internal_copy
    assert in_list == logger.accumulator


def test_gpio_failure(sigExit):
    # Test that GPIO fails gracefully
    gpio_th = atgmlogger.GPIOListener({},
                                      gpio_queue=queue.PriorityQueue(),
                                      exit_sig=sigExit)

    gpio_th.start()


def test_decode():
    bad_byte_str = b'\xff\x01\x02Hello World\xff'
    res = common.decode(bad_byte_str)
    assert "Hello World" == res

    decoded_str = "Hello World"
    res = common.decode(decoded_str)
    assert decoded_str == res


def test_convert_gps_time():
    gpsweek = 1984
    gpssec = 596080
    expected = 1516484080.0

    res = common.convert_gps_time(gpsweek, gpssec)
    assert expected == res

    # Test casting of string values
    res = common.convert_gps_time(str(gpsweek), str(gpssec))
    assert expected == res

    # Test for invalid values, should return 0
    res = common.convert_gps_time(None, None)
    assert 0 == res


def test_timestamp_from_data():
    data_unsync = '$UW,81251,2489,4779,4807953,307,874,201,-8919,7232,' \
                  '211,977,266,4897355,0.000000,0.000000,0.0000,0.0000,' \
                  '00000000005558'

    res = common.timestamp_from_data(data_unsync)
    assert res is None

    data_sync = '$UW,81251,2489,4779,4807953,307,874,201,-8919,7232,211,' \
                '977,266,4897355,0.000000,0.000000,0.0000,0.0000,' \
                '20180115203005'
    expected = datetime.datetime(2018, 1, 15, 20, 30, 5).timestamp()

    res = common.timestamp_from_data(data_sync)
    assert expected == res

    data_malformed = '$UW,81251,2489,4779,4807953,307,874,201,-8919,7232'
    res = common.timestamp_from_data(data_malformed)
    assert res is None


def test_parse_args():
    from atgmlogger import rcParams
    cfg_path = Path('test/.atgmlogger')
    with cfg_path.open('r') as fd:
        rcParams.load_config(fd)
    argv = ['atgmlogger.py', '-vvv', '-c', 'test/.atgmlogger', '--logdir',
            '/var/log/atgmlogger']
    args = common.parse_args(argv)

    assert args.verbose == 3
    assert args.config == 'test/.atgmlogger'
    assert args.logdir == '/var/log/atgmlogger'
    assert rcParams['logging.logdir'] == '/var/log/atgmlogger'


def test_config(cfg_dict):
    # Test rcParams/ConfigParams wrapper
    orig_cfg = copy.deepcopy(cfg_dict)
    cfg = _ConfigParams(config=cfg_dict)

    # Test config getter with arbitrary depths
    assert cfg['logging.version'] == 1
    assert cfg['usb.copy_level'] == "debug"
    assert cfg['logging.filters.data_filter.level'] == 75
    assert cfg['logging.handlers.applog_hdlr.filters'] == ["data_filter"]
    assert isinstance(cfg['serial'], dict)

    # Test setting arbitrary values in config
    orig = cfg._default['serial']['port']
    cfg['serial.port'] = 'COM0'
    # Ensure that original copy remains unchanged
    assert cfg._default['serial']['port'] == orig
    assert cfg['serial.port'] == 'COM0'
    assert cfg._default == orig_cfg


def test_fallback_config(cfg_dict):
    # Test ConfigParams loading when no configuration file is available
    for path in _ConfigParams.cfg_paths:
        # Make sure none of the search paths exist or this will skew the test
        assert not path.exists()
    cfg = _ConfigParams()
    # Selectively exclude logging node due to filepath expansion
    # Don't feel like fixing that yet.
    for node in ['version', 'serial', 'usb', 'gpio']:
        assert cfg[node] == cfg_dict[node]


def test_config_default(cfg_dict):
    # Test retrieval of default values when an override has been set
    orig_cfg = copy.deepcopy(cfg_dict)
    cfg = _ConfigParams(config=cfg_dict)

    assert cfg['logging.version'] == 1
    cfg['logging.version'] = 2
    assert cfg['logging.version'] == 2
    # Verify that all keys still exist
    for key in orig_cfg['logging'].keys():
        assert key in cfg.config['logging']
    assert cfg.get_default('logging.version') == 1


def test_configparams_search(cfg_dict):
    cfg = _ConfigParams(path='test/.atgmlogger')

    assert cfg.config == cfg_dict


def test_config_notexist(cfg_dict):
    cfg = _ConfigParams(config=cfg_dict)

    assert cfg['badkey.badbranch'] is None


def test_expand_path(cfg_dict):
    orig = copy.deepcopy(cfg_dict)
    cfg = _ConfigParams(config=cfg_dict)
    cfg._expand_paths(cfg.config['logging'], 'filename', '/var/log')

    assert (cfg['logging.handlers.data_hdlr.filename'] ==
            os.path.normpath('/var/log/gravdata.dat'))

