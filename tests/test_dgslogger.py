#!/usr/bin/python3.5
"""
Unittest module for dgslogger.py execution
"""

import unittest
from unittest.mock import patch, call, Mock
import os
import logging
import itertools

import serial

import dgslogger as main 
from SerialRecorder import SerialRecorder

def null_logger():
    nlog = logging.getLogger('null')
    handler = logging.NullHandler()
    nlog.addHandler(handler)
    return nlog

N_LOG = null_logger()

class test_dgslogger(unittest.TestCase):
    """Test case for dgslogger.py"""
    def setUp(self):
        pass

    @patch('os.makedirs')
    @patch('os.path.exists')
    def test_check_dirs(self, mock_exists, mock_mkdirs):
        """Verify check_dirs function checks/creates log directory"""
        # Test True case
        mock_exists.return_value=True
        self.assertTrue(main.check_dirs())
        mock_exists.assert_called_once_with(main.LOG_DIR)
        # Test False case
        mock_exists.reset_mock()
        mock_exists.return_value=False
        self.assertTrue(main.check_dirs())
        mock_exists.assert_called_once_with(main.LOG_DIR)
        mock_mkdirs.assert_called_once_with(main.LOG_DIR)

        # Test permission error 1=errno.EPERM, 2=errno.ENOENT
        mock_mkdirs.reset_mock()
        mock_mkdirs.side_effect = OSError(1, 'Operation not permitted',
                main.LOG_DIR)
        main.DEBUG = False  # Suppress log output in test
        with self.assertRaises(OSError) as exc:
            self.assertFalse(main.check_dirs())
            self.assertEqual(exc.filename, main.LOG_DIR)
            mock_mkdirs.assert_called_once_with(main.LOG_DIR)

        mock_mkdirs.reset_mock()
        mock_mkdirs.side_effect = OSError(2, 'No such file or directory')
        with self.assertRaises(OSError) as exc:
            self.assertFalse(main.check_dirs())

    def test_get_ports(self):
        """Verify serial.tools.list_ports.comports() returns as expected."""
        ports = main.get_ports()
        # comports imported into dgslogger with 'from' context
        with patch.object(main, 'comports') as mock_ports:
            ttyS1 = serial.tools.list_ports_linux.SysFS('ttyS1')
            ttyS1.device = '/dev/ttyS1'
            ttyS2 = serial.tools.list_ports_linux.SysFS('ttyS2')
            ttyS2.device = '/dev/ttyS2'
            mock_ports.return_value = [ttyS1, ttyS2]
            mocked = main.get_ports()
            mock_ports.assert_called_once_with()
            self.assertEqual(mocked[0], 'ttyS1')
            self.assertEqual(mocked[1], 'ttyS2')

            mock_dev = main.get_ports(path=True)
            self.assertEqual(mock_dev[0], '/dev/ttyS1')
            self.assertEqual(mock_dev[1], '/dev/ttyS2')

    @patch.object(main, 'get_ports')
    @patch('dgslogger.SerialRecorder')
    def test_spawn_threads(self, mock_ser, mock_ports):
        """Verify correct threads spawned for ports"""
        
        mock_threads = lambda c: [SerialRecorder('ttyS{}'.format(x),
            main.EXIT_E) for x in range(c)]

        # Test with no active ports
        mock_ports.return_value = ['ttyS0', 'ttyS1']
        spawned = main.spawn_threads([])
        self.assertEqual(spawned, mock_ports.return_value)
        def mock_calls(port=''):
            yield call(port, main.EXIT_E)
            yield call().start()
        calls = list(itertools.chain.from_iterable(mock_calls(p)
            for p in mock_ports.return_value))
        mock_ser.assert_has_calls(calls)

        # Test with a port already active
        mock_ports.return_value = ['ttyS0', 'ttyS1', 'ttyS2']
        active_ports = [Mock(spec=SerialRecorder, name='ttyS0')]




    def test_cull_threads(self):
        """Verify that threads are removed correctly from list if dead"""
        pass
