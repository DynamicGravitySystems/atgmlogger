#!/usr/bin/python3.5

import serial
import serial.tools.list_ports
import sys
import time
import logging
import threading
import os

class Recorder:
    max_threads = 4
    def __init__(self):
       self.threads = [] 
       self.exiting = threading.Event()

    def _configure(self):
        pass

    def _get_ports(self):
        return [p.name for p in serial.tools.list_ports.comports()]

    def _make_thread(self, port):
        return SerialRecorder(port, self.exiting)

    def spawn_threads(self):
        if len(self.threads) > self.max_threads:
            return 0
        to_spawn = [port for port in self._get_ports() if port not in [p.name for p in self.threads]]
        for port in to_spawn:
            thread = self._make_thread(port)
            thread.start()
            self.threads.append(thread)
    
    def scrub_threads(self):
        for t in self.threads[:]:
            if not t.is_alive():
                self.threads.remove(t)

    def run(self):
        """Main program loop - spawn threads and respawn them when dead
        if the port is still available
        """
        print("Initializing run loop {}".format(__name__))
        while not self.exiting.is_set():
            try:
                self.scrub_threads()
                self.spawn_threads() 
                time.sleep(.5)
            except KeyboardInterrupt:
                print(" Ctrl-C Captured - Exiting threads...\n")
                self.exit()

    def exit(self):
        """Controlled exit, join threads and flush logs"""
        self.exiting.set()
        for t in (_ for _ in self.threads if _.is_alive()):
            t.join()
        #self.log.flush()
        sys.exit(0)



class SerialRecorder(threading.Thread):
    def __init__(self, port, signal):
        threading.Thread.__init__(self)
        #Retain port as name, self.device becomes device path e.g. /dev/ttyS0
        self.name = port
        self.device = os.path.join('/dev', port)
        self.exiting = signal
        self.exc = None
        self.config = {'port' : self.device, 'timeout' : 1} 
        self.data = [] 
        self.log = logging.getLogger(self.name)
        self.exiting.clear()
    
    def read_data(self, ser, encoding='utf-8'):
        line = ser.readline().decode(encoding).rstrip('\n')
        return line

    def run(self):
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
        while not self.exiting.is_set():
            try:
                #line = ser.readline().decode('utf-8').rstrip('\n')
                line = self.read_data(ser)
                if line is not '':
                    self.data.append(line)
                #    self.log.info(line)
            except serial.SerialException:
                self.exc = sys.exc_info() 
                #self.log.flush()
                #self.exiting.set()
                return
            
if __name__ == "__main__":
    recorder = Recorder()
    recorder.run()
    


