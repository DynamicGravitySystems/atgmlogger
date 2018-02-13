# coding: utf-8

import sys
import json
import unittest
import threading
import datetime
import logging
import time
import queue
import multiprocessing as mp
from pathlib import Path
from pprint import pprint

import serial

from atgmlogger import atgmlogger, common

_log = logging.getLogger(__name__)
_log.setLevel(logging.DEBUG)
_log.addHandler(logging.StreamHandler(stream=sys.stderr))


class CustomLogger:
    def __init__(self):
        self.accumulator = list()

    def log(self, level, data):
        self.accumulator.append(data)


class TestSerialIO(unittest.TestCase):
    def setUp(self):
        self.handle = serial.serial_for_url('loop://',
                                            baudrate=57600,
                                            timeout=.1)
        self._exit = threading.Event()
        self.logger = CustomLogger()
        self.threads = []

    def start_threads(self):
        for thread in self.threads:
            try:
                _log.debug("Starting thread: %s", thread.name)
                thread.start()
            except:
                continue

    def join_threads(self, timeout=0.1):
        for thread in self.threads:
            try:
                _log.debug("Joining thread: %s", thread.name)
                thread.join(timeout=timeout)
            except:
                continue

    def test_at1logger(self):
        data_queue = queue.Queue()
        atgm = atgmlogger.SerialListener(self.handle,
                                         data_queue=data_queue,
                                         exit_sig=self._exit)
        listen_th = threading.Thread(target=atgm.listen, name='listener')

        cmd_listener = atgmlogger.CommandListener(atgm.commands,
                                                  exit_sig=self._exit)
        writer = atgmlogger.DataLogger(data_queue,
                                       logger=self.logger,
                                       exit_sig=self._exit)

        self.threads.extend([listen_th, cmd_listener, writer])
        self.start_threads()

        in_list = list()
        for i in range(0, 1001):
            decoded = "Line: {}".format(i)
            data = "Line: {}\n".format(i).encode('latin-1')
            in_list.append(decoded)
            self.handle.write(data)

        time.sleep(.15)
        self._exit.set()
        self.join_threads()

        assert in_list == writer._internal_copy
        # self.assertListEqual(in_list, writer._internal_copy)
        assert in_list == self.logger.accumulator
        # self.assertListEqual(in_list, self.logger.accumulator)

    def test_mproc_queue(self):
        # Test use of multiprocessing.Queue with listener and DataLogger
        data_queue = mp.Queue()
        atgm = atgmlogger.SerialListener(self.handle,
                                         data_queue=data_queue,
                                         exit_sig=self._exit)
        listener = threading.Thread(target=atgm.listen, name='listener')
        writer = atgmlogger.DataLogger(data_queue,
                                       logger=self.logger,
                                       exit_sig=self._exit)

        self.threads.extend([listener, writer])
        self.start_threads()

        in_list = list()
        for i in range(0, 1001):
            decoded = "Line: {}".format(i)
            raw = "Line: {}\n".format(i).encode('latin-1')
            in_list.append(decoded)
            self.handle.write(raw)

        time.sleep(.15)
        self._exit.set()
        self.join_threads()

        assert in_list == writer._internal_copy
        # self.assertListEqual(in_list, writer._internal_copy)
        assert in_list == self.logger.accumulator
        # self.assertListEqual(in_list, self.logger.accumulator)

    def test_gpio_failure(self):
        # Test that GPIO fails gracefully
        gpio_th = atgmlogger.GPIOListener({},
                                          gpio_queue=queue.PriorityQueue(),
                                          exit_sig=self._exit)

        gpio_th.start()
        self._exit.set()

    def tearDown(self):
        self._exit.set()
        self.join_threads()


class TestHelperModule:

    def test_decode(self):
        bad_byte_str = b'\xff\x01\x02Hello World\xff'
        res = common.decode(bad_byte_str)
        assert "Hello World" == res
        # self.assertEqual("Hello World", res)

        decoded_str = "Hello World"
        res = common.decode(decoded_str)
        assert decoded_str == res
        # self.assertEqual(decoded_str, res)

    def test_convert_gps_time(self):
        gpsweek = 1984
        gpssec = 596080
        expected = 1516484080.0

        res = common.convert_gps_time(gpsweek, gpssec)
        assert expected == res
        # self.assertEqual(expected, res)

        # Test casting of string values
        res = common.convert_gps_time(str(gpsweek), str(gpssec))
        assert expected == res
        # self.assertEqual(expected, res)

        # Test for invalid values, should return 0
        res = common.convert_gps_time(None, None)
        assert 0 == res
        # self.assertEqual(0, res)

    def test_timestamp_from_data(self):
        data_unsync = '$UW,81251,2489,4779,4807953,307,874,201,-8919,7232,' \
                      '211,977,266,4897355,0.000000,0.000000,0.0000,0.0000,' \
                      '00000000005558'

        res = common.timestamp_from_data(data_unsync)
        assert res is None
        # self.assertEqual(None, res)

        data_sync = '$UW,81251,2489,4779,4807953,307,874,201,-8919,7232,211,' \
                    '977,266,4897355,0.000000,0.000000,0.0000,0.0000,' \
                    '20180115203005'
        expected = datetime.datetime(2018, 1, 15, 20, 30, 5).timestamp()

        res = common.timestamp_from_data(data_sync)
        assert expected == res
        # self.assertEqual(expected, res)

        data_malformed = '$UW,81251,2489,4779,4807953,307,874,201,-8919,7232'
        res = common.timestamp_from_data(data_malformed)
        assert res is None
        # self.assertEqual(None, res)

    def test_logger_preprocess(self):
        with open('test/.atgmlogger', 'r') as fd:
            config = json.load(fd)

        log_conf = config['logging']
        handlers = log_conf['handlers']
        data_name = handlers['data_hdlr']['filename']
        appl_name = handlers['applog_hdlr']['filename']
        common.preprocess_log_config(log_conf, logdir='test/logs')

        expected = str(Path('test/logs').resolve().joinpath(data_name))
        assert log_conf['handlers']['data_hdlr']['filename'] == expected
        expected = str(Path('test/logs').resolve().joinpath(appl_name))
        assert log_conf['handlers']['applog_hdlr']['filename'] == expected

    def test_parse_args(self):
        argv = ['atgmlogger.py', '-vvv', '-c', 'test/.atgmlogger']
        cfg = common.parse_args(argv)

        expected = Path('/var/log/atgmlogger/gravdata.dat').resolve()
        assert cfg['logging']['handlers']['data_hdlr']['filename'] == str(
            expected)
