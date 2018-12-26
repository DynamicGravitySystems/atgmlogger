# -*- coding: utf-8 -*-

import sys
import copy
import datetime
import logging

from atgmlogger import atgmlogger
from atgmlogger.runconfig import _ConfigParams
from atgmlogger.atgmlogger import load_plugin

_log = logging.getLogger(__name__)
_log.setLevel(logging.DEBUG)
_log.addHandler(logging.StreamHandler(stream=sys.stderr))


def test_atgmlogger_plugins(rcParams):
    # This is causing errors in the test_dispatcher suite, maybe the
    # registration happening twice?
    plugins = rcParams['plugins']
    for key in ['usb', 'timesync']:
        assert key in plugins

    for plugin in plugins:
        try:
            load_plugin(plugin, register=False)
        except ImportError:
            pass


def test_decode():
    bad_byte_str = b'\xff\x01\x02Hello World\xff'
    res = atgmlogger.SerialListener.decode(bad_byte_str)
    assert "Hello World" == res

    decoded_str = "Hello World"
    res = atgmlogger.SerialListener.decode(decoded_str)
    assert decoded_str == res


def test_convert_gps_time():
    gpsweek = 1984
    gpssec = 596080
    expected = 1516484080.0

    from atgmlogger.plugins import timesync
    res = timesync.convert_gps_time(gpsweek, gpssec)
    assert expected == res

    # Test casting of string values
    res = timesync.convert_gps_time(str(gpsweek), str(gpssec))
    assert expected == res

    # Test for invalid values, should return 0
    res = timesync.convert_gps_time(None, None)
    assert 0 == res


def test_timestamp_from_data():
    data_unsync = '$UW,81251,2489,4779,4807953,307,874,201,-8919,7232,' \
                  '211,977,266,4897355,0.000000,0.000000,0.0000,0.0000,' \
                  '00000000005558'

    from atgmlogger.plugins import timesync
    res = timesync.timestamp_from_data(data_unsync)
    assert res is None

    data_sync = '$UW,81251,2489,4779,4807953,307,874,201,-8919,7232,211,' \
                '977,266,4897355,0.000000,0.000000,0.0000,0.0000,' \
                '20180115203005'
    expected = datetime.datetime(2018, 1, 15, 20, 30, 5).timestamp()

    res = timesync.timestamp_from_data(data_sync)
    assert expected == res

    data_malformed = '$UW,81251,2489,4779,4807953,307,874,201,-8919,7232'
    res = timesync.timestamp_from_data(data_malformed)
    assert res is None


def test_config(cfg_dict):
    # Test rcParams/ConfigParams wrapper
    orig_cfg = copy.deepcopy(cfg_dict)
    cfg = _ConfigParams(config=cfg_dict)

    # Test config getter with arbitrary depths
    assert cfg['plugins.usb.logdir'] == "/var/log/atgmlogger"
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
        # Make sure none of the search paths exist or this will skew the tests
        assert not path.exists()
    cfg = _ConfigParams()
    # Selectively exclude logging node due to filepath expansion
    # Don't feel like fixing that yet.
    for node in ['version', 'serial', 'plugins']:
        assert cfg[node] == cfg_dict[node]


def test_config_default(cfg_dict):
    # Test retrieval of default values when an override has been set
    orig_cfg = copy.deepcopy(cfg_dict)
    cfg = _ConfigParams(config=cfg_dict)

    assert cfg['serial.baudrate'] == 57600
    cfg['serial.baudrate'] = 9600
    assert cfg['serial.baudrate'] == 9600
    # Verify that all keys still exist
    for key in orig_cfg['serial'].keys():
        assert key in cfg.config['serial']
    assert cfg.get_default('serial.baudrate') == 57600


def test_configparams_search(cfg_dict):
    cfg = _ConfigParams(path='atgmlogger/install/atgmlogger.json')

    assert cfg.config == cfg_dict


def test_config_notexist(cfg_dict):
    cfg = _ConfigParams(config=cfg_dict)

    assert cfg['badkey.badbranch'] is None
