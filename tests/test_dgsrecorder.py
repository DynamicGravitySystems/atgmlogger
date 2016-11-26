#!/usr/bin/python3.5

import unittest
from unittest.mock import patch
from unittest import mock
import dgsrecorder
import threading
import serial
import time

"""
Skip a testcase with @unittest.skip('reason')
Assert exceptions using 'with' context:
    with self.assertRaises(Exception):
        do something that raises
"""

class test_dgsrecorder(unittest.TestCase):
    def setUp(self):
        self.recorder = dgsrecorder.DgsRecorder() 

    def test_instance(self):
        self.assertIsInstance(self.recorder, dgsrecorder.DgsRecorder)

    @patch('serial.tools.list_ports.comports')
    def test_get_ports(self, mock_comports):
        #Mock up a ListPortInfo object to provide 'ttyS0' when comports() is called
        mock_port = mock.Mock()
        mock_port.name = 'ttyS0'
        mock_port.description = 'ttyS0'
        mock_port.device = '/dev/ttyS0'
        mock_comports.return_value = [mock_port]
        
        ports = self.recorder._get_ports()
        self.assertEqual(ports, ['ttyS0'])
        mock_comports.assert_called_once_with()

    def test_make_thread(self):
       thread = self.recorder._make_thread('ttyS0')
       self.assertIsInstance(thread, dgsrecorder.SerialRecorder)
       self.assertEqual(thread.port, 'ttyS0')
       self.assertEqual(thread.name, 'Thread-1')
       self.assertFalse(thread.is_alive())
    
    @patch('dgsrecorder.DgsRecorder._get_ports', return_value=['ttyS0', 'ttyS1'])
    def test_spawn_threads(self, mock_ports):
       self.assertEqual(self.recorder._get_ports(), ['ttyS0', 'ttyS1'])
       self.assertEqual(self.recorder.threads, [])

       self.recorder.spawn_threads()
       self.assertEqual(len(self.recorder.threads), 2)
       self.assertEqual(self.recorder.threads[0].port, 'ttyS0')
       self.assertEqual(self.recorder.threads[1].port, 'ttyS1')

       mock_ports.return_value = ['ttyS3']
       self.recorder.spawn_threads()
       self.assertEqual(len(self.recorder.threads), 3)
       self.recorder.exiting.set()

    @patch('dgsrecorder.SerialRecorder.readline', side_effect=serial.SerialException('error'))
    def test_serial_read_exception(self, mock_read):
        thread = self.recorder._make_thread('ttyS0')
        self.assertTrue(thread.exception is None)
        thread.start()
        self.assertFalse(thread.is_alive())
        self.assertTrue(thread.exception is not None)

    @patch('serial.Serial', return_value = serial.serial_for_url('loop://', timeout=0))
    def test_serial_read(self, mock_serial):
        s = mock_serial.return_value
        thread = self.recorder._make_thread('ttyS0')
        thread.start()
        s.write(b'test')
        #Sleep to ensure loop port has time to setup/send (may vary on diff system)
        time.sleep(2)
        self.assertEqual(thread.data, 'test')

    def tearDown(self):
        self.recorder.exiting.set()
        self.recorder.threads = []

if __name__ == "__main__":
    unittest.main()
