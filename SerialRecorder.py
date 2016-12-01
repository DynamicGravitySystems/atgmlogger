#!/usr/bin/python3.5

"""
SerialGrav.py:

"""

import os
import sys
import time
import logging
import logging.handlers
import threading

import serial
import serial.tools.list_ports

__author__ = 'Zachery Brady'
__copyright__ = 'Copyright 2016, Dynamic Gravity Systems Inc.'
__status__ = 'Development'
__version__ = "0.1.0"

class SerialRecorder(threading.Thread):
    """
    Threaded serial recorder - binds to a serial port and records all text data
    port paramater expects the name of the device without directory info i.e.
    'ttyS0' not '/dev/ttyS0'
    """
    def __init__(self, port, signal):
        threading.Thread.__init__(self)
        # Retain port as name, self.device becomes device path e.g. /dev/ttyS0
        self.name = port
        self.device = os.path.join('/dev', port)
        # exiting is global thread signal - setting will kill all threads
        self.exiting = signal
        self.kill = False
        self.exc = None
        self.config = {'port' : self.device, 'timeout' : 1}
        self.data = []

        self.data_log = logging.getLogger(port)
        self.log = logging.getLogger(self.name)
        self.log.info("Thread %s initialized", self.name)
        # self.exiting.clear()

    # TODO: Fix this method (make port instance level?)
    def read_data(self, ser, encoding='utf-8'):
        """Perform blocking readline() on serial stream 'ser'
        then decode to a string and strip newline chars '\\n'
        Returns: string
        """
        return ser.readline().decode(encoding).rstrip('\n')

    def exit(self):
        """Cleanly exit the thread, and log the event"""
        self.log.warning("Exiting thread %s", self.name)
        self.kill = True
        return

    def run(self):
        # TODO: Move this to Class DOCSTRING
        """Creates a serial port from self.config dict then
        attempts to read from the port until the self.exiting
        event is triggered (set). If a timeout is not specified
        when opening the serial port the self.readline() method
        can block forever and thread signals will not be received.
        ---
        Data read via readline is appended to the self.data list,
        each item = a line of data.
        Logging will be added to log each line to a file concurrently.
        """
        ser = serial.Serial(**self.config)
        self.log.debug("Started thread %s", self.name)
        while not self.exiting.is_set():
            if self.kill:
                break
            try:
                line = self.read_data(ser)
                if line is not '':
                    self.data.append(line)
                    self.data_log.critical(line)
            except serial.SerialException:
                self.exc = sys.exc_info()
                break
        self.exit()

if __name__ == "__main__":
    MAIN = Recorder()
    MAIN.run()
