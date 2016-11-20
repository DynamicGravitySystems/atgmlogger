#!/usr/bin/python3.5

import unittest
import dgslogger
import serial


class test_dgslogger(unittest.TestCase):
    def setUp(self):
       self.logger = dgslogger.SerialRecorder()

    def test_read_configuration(self):
        self.assertEqual(self.logger.baudrate, 57600)
        self.assertEqual(self.logger.port, 'tty0')
        self.assertEqual(self.logger.parity, serial.PARITY_NONE)
        self.assertEqual(self.logger.stopbits, serial.STOPBITS_ONE)
        

if __name__ == '__main__':
    unittest.main()

