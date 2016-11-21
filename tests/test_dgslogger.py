#!/usr/bin/python3.5

import unittest
import dgslogger
import serial
import os

class test_dgslogger(unittest.TestCase):
    def setUp(self):
       self.logger = dgslogger.SerialRecorder()

    def test_read_configuration(self):
        self.assertEqual(self.logger.baudrate, 57600)
        self.assertEqual(self.logger.port, 'tty0')
        self.assertEqual(self.logger.parity, serial.PARITY_NONE)
        self.assertEqual(self.logger.stopbits, serial.STOPBITS_ONE)
    
    def test_config_exception(self):
        """Test exception handling when config file doesn't exist"""
        pass
        with self.assertRaises(FileNotFoundError):
            self.logger.read_config('nonexistant.file')

    def tearDown(self):
        pass

if __name__ == '__main__':
    unittest.main()
