#!/usr/bin/python3.5

import unittest
import dgslogger
import os
from unittest import mock

class test_outline(unittest.TestCase):
    """Pseudo class used to outline what the actual tests should be"""

    def setUp(self):
        """Set up an instance of any classes we need i.e. dgslogger"""
        pass

    def test_read_configuration(self):
        """Test to see that the configuration file is read/applied correctly"""
        pass

    def test_app_logger(self):
        """Test to ensure the application log is working"""
        pass

    def test_data_logger(self):
        """Test that data log is recording correctly"""
        pass

    def test_open_serial(self):
        """Test opening of a serial port based on config"""
        pass

    def test_read_serial(self):
        """Test that serial data can be read properly"""
        pass

    def test_write_data(self):
        """Test that serial data is recorded to log"""
        pass

    def test_serial_fail(self):
        """Test to ensure recovery from failed serial e.g. disconnect"""
        pass
    
    def test_serial_thread(self):
        """Test threaded serial operation (multiple ports)"""
        pass

    def test_thread_spawn(self):
        """Test proper spawning of serial readers given multiple ports"""
        pass


