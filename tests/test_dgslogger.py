#!/usr/bin/python3.5

import unittest
from unittest.mock import patch
import dgslogger
import serial
import os
from unittest import mock

def mock_config():
    config_dict = {
            'SERIAL' : {
                'port' : 'tty0',
                'baudrate' : 57600,
                'parity' : 'none',
                'stopbits' : 1,
                'timeout' : 0
                },
            'DATA' : {
                'logdir' : '/var/log/dgslogger',
                'meterid' : 'AT1X-TEST',
                'loginterval' : '1d'
                }
            }
    return config_dict


class test_dgslogger(unittest.TestCase):
    def setUp(self):
       self.logger = dgslogger.SerialRecorder()

    def test_read_configuration(self):
        #TODO: mock the config data and pass to the function
        self.assertEqual(self.logger.baudrate, 57600)
        self.assertEqual(self.logger.port, 'tty0')
        self.assertEqual(self.logger.parity, serial.PARITY_NONE)
        self.assertEqual(self.logger.stopbits, serial.STOPBITS_ONE)

    def test_config_set(self): 
        """Test configuration using mocked config values"""
        pass


    def test_config_exception(self):
        """Test exception handling when config file doesn't exist"""
        pass
        with self.assertRaises(FileNotFoundError):
            self.logger.read_config('nonexistant.file')
    
    @patch(logging.getLogger)
    def test_app_logging(self, mock_log):
        """Test that the application is creating logs properly"""
        pass


    def tearDown(self):
        pass

if __name__ == '__main__':
    unittest.main()
