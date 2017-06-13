import unittest
import SerialLogger
import logging
import yaml
import shutil
import sys


class TestSerialLogger(unittest.TestCase):

    def setUp(self):
        # Link to but don't initialize SerialLogger class for convenience
        self.s = SerialLogger.SerialLogger
        self.log_stream = logging.StreamHandler(stream=sys.stdout)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree('./logs')

    def test_level_filter(self):
        lvl_filter = SerialLogger.level_filter(60)
        data_record = logging.makeLogRecord({'name': 'test_level_filter',
                                        'levelno': 60,
                                        'msg': 'line of data at level 60'})
        info_record = logging.makeLogRecord({'name': 'test_level_filter',
                                             'levelno': int(logging.INFO),
                                             'msg': 'informational message'})
        self.assertFalse(lvl_filter(data_record))
        self.assertTrue(lvl_filter(info_record))

    def test_set_verbosity(self):
        result = self.s.set_verbosity(4, lvlmax=3)
        self.assertEqual(result, 3)
        result = self.s.set_verbosity(-1)
        self.assertEqual(result, 0)
        result = self.s.set_verbosity(None)
        self.assertEqual(result, 0)

    def test_load_config(self):
        config = 'logging.yaml'
        with open(config, 'r') as source:
            src_yaml = yaml.load(source)
        test = self.s.load_config(config)
        self.assertDictEqual(src_yaml, test)

        test_empty = self.s.load_config('nonexistant.yaml')
        self.assertIsNone(test_empty)

        test_defaults = self.s.load_config('nonexistant.yaml', default_opts={
            'version': 0.2,
            'usb': {'mount': '/media/removable', 'poll_int': 3, 'copy_level': 'all'}
        })
        self.assertEqual(test_defaults['version'], 0.2)
        self.assertEqual(test_defaults['usb']['poll_int'], 3)

    def test_decode(self):
        raw_data = bytes('abcd!%*\t\r\n', encoding='latin_1')
        raw_data += bytes(chr(255), encoding='latin_1')
        raw_data += bytes(chr(0), encoding='latin_1')
        self.assertIsInstance(raw_data, bytes)
        result = self.s.decode(raw_data)
        self.assertEqual(result, 'abcd!%*')
        self.assertIsInstance(result, str)

    def test_SerialLogger_init(self):
        init = self.s(['test.py', '-vvv', '--logdir=./logs'])

        # Replace log handlers with Stream to sys.stdout for testing
        init.log.handlers = self.log_stream

        self.assertEqual(init.verbosity, 3)
        logging.shutdown()
