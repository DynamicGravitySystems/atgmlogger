#!/usr/bin/python3.5

import serial
import serial.tools.list_ports
import sys
import time
import logging
import threading
import os

class SerialRecorder(threading.Thread):
    def __init__(self, port, signal):
        threading.Thread.__init__(self)
        self.port = os.path.join('/dev', port)
        self.exiting = signal
        self.exception = None
        self.config = {'port' : self.port, 'timeout' : 1} 
        self.data = [] 

    def readline(self, handle, encoding='utf-8'):
        return handle.readline().decode(encoding).rstrip('\n')

    def run(self):
        ser = serial.Serial(**self.config)
        while not self.exiting.is_set():
            try:
                line = self.readline(ser)
                if line not '':
                    self.data.append(line)
            except serial.SerialException:
                self.exception = sys.exc_info() 
                self.exiting.set()



class DgsRecorder:
    def __init__(self):
       self.threads = [] 
       self.exiting = threading.Event()

    def _configure(self):
        pass

    def _get_ports(self):
        return [p.name for p in serial.tools.list_ports.comports()]

    def _make_thread(self, port):
        thread = SerialRecorder(port, self.exiting)
        return thread

    def spawn_threads(self):
        for port in self._get_ports():
            thread = self._make_thread(port)
            thread.start()
            self.threads.append(thread)
