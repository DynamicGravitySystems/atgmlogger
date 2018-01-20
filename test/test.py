import unittest
import threading
import datetime
import time
import queue

import serial

from atgmlogger import atgmlogger, helpers


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
        self.atgm = atgmlogger.AT1Listener(self.handle, exit_sig=self._exit)
        self.logger = CustomLogger()

    def test_at1logger(self):
        listen_th = threading.Thread(target=self.atgm.listen, name='listener')

        cmd_listener = atgmlogger.CommandListener(self.atgm.commands,
                                                  exit_sig=self._exit)
        writer = atgmlogger.DataWriter(self.atgm.output,
                                       self.logger,
                                       exit_sig=self._exit)

        print("Starting consumer thread")
        writer.start()
        print("Starting command listener thread")
        cmd_listener.start()
        print("Starting listen thread")
        listen_th.start()
        in_list = list()
        for i in range(0, 1001):
            decoded = "Line: {}".format(i)
            data = "Line: {}\n".format(i).encode('latin-1')
            in_list.append(decoded)
            self.handle.write(data)

        time.sleep(.15)
        self._exit.set()
        listen_th.join()
        writer.join()
        cmd_listener.join()

        self.assertListEqual(in_list, writer._internal_copy)
        self.assertListEqual(in_list, self.logger.accumulator)

    def test_loginit(self):
        pass


class TestHelperModule(unittest.TestCase):
    def setUp(self):
        pass

    def test_decode(self):
        bad_byte_str = b'\xff\x01\x02Hello World\xff'
        res = helpers.decode(bad_byte_str)
        self.assertEqual('Hello World', res)

        decoded_str = "Hello World"
        res = helpers.decode(decoded_str)
        self.assertEqual(decoded_str, res)

    def test_convert_gps_time(self):
        gpsweek = 1984
        gpssec = 596080
        expected = 1516484080.0

        res = helpers.convert_gps_time(gpsweek, gpssec)
        self.assertEqual(expected, res)

        # Test casting of string values
        res = helpers.convert_gps_time(str(gpsweek), str(gpssec))
        self.assertEqual(expected, res)

        # Test for invalid values, should return 0
        res = helpers.convert_gps_time(None, None)
        self.assertEqual(0, res)

    def test_timestamp_from_data(self):
        data_unsync = '$UW,81251,2489,4779,4807953,307,874,201,-8919,7232,' \
                      '211,977,266,4897355,0.000000,0.000000,0.0000,0.0000,' \
                      '00000000005558'

        res = helpers.timestamp_from_data(data_unsync)
        self.assertEqual(None, res)

        data_sync = '$UW,81251,2489,4779,4807953,307,874,201,-8919,7232,211,' \
                    '977,266,4897355,0.000000,0.000000,0.0000,0.0000,' \
                    '20180115203005'
        expected = datetime.datetime(2018, 1, 15, 20, 30, 5).timestamp()

        res = helpers.timestamp_from_data(data_sync)
        self.assertEqual(expected, res)

        data_malformed = '$UW,81251,2489,4779,4807953,307,874,201,-8919,7232'
        res = helpers.timestamp_from_data(data_malformed)
        self.assertEqual(None, res)

