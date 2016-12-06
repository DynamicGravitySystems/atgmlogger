#!/usr/bin/python3.5

"""
SerialRecorder.py:

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


# TODO: We can assume only one gravity meter will be recording at any one time
# so make the data logs merge together so that in case of disconnect it will
# not be spread across multiple files
class SerialRecorder(threading.Thread):
    """
    Threaded serial recorder - binds to a serial port and records all text data
    port paramater expects the name of the device without directory info i.e.
    'ttyS0' not '/dev/ttyS0'
    """
    def __init__(self, port, signal, logname):
        threading.Thread.__init__(self)
        # Retain port as name, self.device becomes device path e.g. /dev/ttyS0
        self.name = port
        self.device = os.path.join('/dev', port)
        # exiting is global thread signal - setting will kill all threads
        self.exiting = signal
        self.kill = False
        self.exc = None
        self.config = {'port' : self.device, 'timeout' : 1, 'baudrate' : 57600,
                'stopbits' : serial.STOPBITS_ONE, 'parity' : serial.PARITY_NONE}
        self.data = []

        self.data_log = logging.getLogger(logname)
        self.log = logging.getLogger(self.name)
        self.log.info("Thread %s initialized", self.name)
        # self.exiting.clear()

    def readline(self, encoding='utf-8'):
        """Perform blocking readline() on serial stream 'ser'
        then decode to a string and strip newline chars '\\n'
        Returns: string
        """
        raw = self.socket.readline()
        try:
            line = raw.decode(encoding).rstrip('\n')
        except UnicodeDecodeError:
            line = raw[1:].decode(encoding).rstrip('\n')
        return line

    def open_port(self):
        """Open a serial connection assigned to self.socket, with the specified config"""
        try:
            self.socket = serial.Serial(**self.config)
        except SerialException:
            self.log.exception("Error opening serial port for reading")
            self.exc = sys.exc_info()
            # Re-raise the serial exception?
            return False
        else:
            return True

    def close_port(self):
        """Close this instances serial port if it is open"""
        if self.socket.is_open:
            self.socket.close()

    def exit(self):
        """Cleanly exit the thread, and log the event"""
        self.log.warning("Exiting thread %s", self.name)
        self.close_port()
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
        self.log.debug("Started thread %s", self.name)
        if not self.open_port():
            self.log.warning("Error opening serial port for reading "\
                    "- aborting thread")
            self.exit()
        while not self.exiting.is_set():
            if self.kill:
                break
            try:
                line = self.readline()
                if line is not '':
                    # TODO: self.data should contain 'timestamp' : 'line' for future use
                    self.data.append(line)
                    self.data_log.critical(line)
            except serial.SerialException:
                self.exc = sys.exc_info()
                break
        self.exit()

