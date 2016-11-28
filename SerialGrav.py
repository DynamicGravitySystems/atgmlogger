#!/usr/bin/python3.5

<<<<<<< HEAD
import serial
import serial.tools.list_ports
=======
"""
SerialGrav.py:

"""

import os
>>>>>>> dgsrecorder
import sys
import time
import logging
import logging.handlers
import threading
<<<<<<< HEAD
import os
=======

import serial
import serial.tools.list_ports

__author__ = 'Zachery Brady'
__copyright__ ='Copyright 2016, Dynamic Gravity Systems Inc.'
__status__ = 'Development'
__version__ = "0.1.0"
>>>>>>> dgsrecorder

class Recorder:
    max_threads = 4
    def __init__(self, loglevel=logging.DEBUG):
       self.threads = [] 
       self.data_loggers = {}
       self.exiting = threading.Event()
       self.log = None
       self.loglevel = loglevel
       self.data_log_path = '/var/log/dgslogger'
       self._configure()

    def _configure(self):
        self.log = self._get_logger() 
        if not os.path.exists(self.data_log_path):
            try:
                os.makedirs(self.data_log_path)
            except OSError:
                self.log.exception('Error creating log directory {}'.format(
                    self.data_log_path))
        
    def _get_logger(self, debug=True):
        applogger = logging.getLogger(__name__)
<<<<<<< HEAD
        applogger.setLevel(self.loglevel)
        formatter = logging.Formatter(
                fmt="%(asctime)s - %(levelname)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S")

        debug_handler = logging.StreamHandler(sys.stdout)
        #debug_handler.setLevel(logging.DEBUG)
        debug_handler.setFormatter(formatter)
=======
        applogger.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            fmt="%(asctime)s - %(levelname)s - %(module)s.%(funcName)s :: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S")

        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setLevel(self.loglevel)
        stream_handler.setFormatter(formatter)
>>>>>>> dgsrecorder

        #TODO: Replace this with instance var or from config file
        logpath = 'logs/SerialGrav.log'
        #TODO: Evaluate using system /var/log/... path instead of module dir
        fullpath = os.path.join(os.path.abspath(os.path.dirname(__file__)),
                os.path.dirname(logpath))

        if not os.path.exists(fullpath):
            try:
                os.makedirs(fullpath)
<<<<<<< HEAD
            except IOError as e:
=======
            except OSError as e:
>>>>>>> dgsrecorder
                print("Error creating log directory: {}".format(e))

        trfh_handler = logging.handlers.TimedRotatingFileHandler(
                './logs/SerialGrav.log', when='midnight', backupCount=15,
                encoding='utf-8', delay=False, utc=False)
<<<<<<< HEAD
        # trfh_handler.setLevel(logging.DEBUG)
        trfh_handler.setFormatter(formatter)

        if debug:
            applogger.addHandler(debug_handler)
=======
        trfh_handler.setLevel(logging.DEBUG)
        trfh_handler.setFormatter(formatter)

        if debug:
            applogger.addHandler(stream_handler)
>>>>>>> dgsrecorder
        applogger.addHandler(trfh_handler)

        applogger.info("Application log initialized")
        return applogger

<<<<<<< HEAD

=======
>>>>>>> dgsrecorder
    def _get_data_logger(self, port):
        # Check first to see if logger already init
        if port in self.data_loggers.keys(): 
            return self.data_loggers[port]
        if logging.getLogger(port).hasHandlers():
            self.data_loggers[port] = logging.getLogger(port)
            return self.data_loggers[port]
        # If not create a new logger for the tty port 
        log_name = '.'.join([port, 'log'])
        data_file = os.path.join(self.data_log_path, log_name)

        data_logger = logging.getLogger(port)
        data_logger.setLevel(logging.DEBUG)
<<<<<<< HEAD
        # TODO: Determine what levels to use to diff data vs program debug - or to use parent logger for program debug info
=======
>>>>>>> dgsrecorder
        # Create a stream handler and a timed rotating file handler
        sh = logging.StreamHandler(sys.stdout) 
        sh.setLevel(logging.WARNING)
        trfh = logging.handlers.TimedRotatingFileHandler(
                data_file, when='midnight', backupCount=32, encoding='utf-8',
                delay=False, utc=False)
        trfh.setLevel(logging.INFO)
        stream_formatter = logging.Formatter(
                "%(asctime)s - %(levelname)s - %(thread)d - %(message)s",
                datefmt = "%Y-%m-%d %H:%M:%S")
        file_formatter = logging.Formatter("%(message)s") 
        
        sh.setFormatter(stream_formatter)
        trfh.setFormatter(file_formatter)
        
        data_logger.addHandler(sh)
        data_logger.addHandler(trfh)

        self.data_loggers[port] = data_logger
        return data_logger

    def _get_ports(self):
        return [p.name for p in serial.tools.list_ports.comports()]

    def _make_thread(self, port):
<<<<<<< HEAD
        data_logger = self._get_data_logger(port)
        return SerialRecorder(port, data_logger, self.exiting)

    def spawn_threads(self):
        if len(self.threads) > self.max_threads:
            return 0
        to_spawn = [port for port in self._get_ports() if port not in [p.name for p in self.threads]]
=======
        self._get_data_logger(port)
        return SerialRecorder(port, self.exiting)

    def spawn_threads(self):

        if len(self.threads) > self.max_threads:
            return 0
        to_spawn = [port for port in self._get_ports() if port not in 
                [p.name for p in self.threads]]
>>>>>>> dgsrecorder
        for port in to_spawn:
            thread = self._make_thread(port)
            thread.start()
            self.threads.append(thread)
    
    def scrub_threads(self):
<<<<<<< HEAD
=======

>>>>>>> dgsrecorder
        for t in self.threads[:]:
            if not t.is_alive():
                self.threads.remove(t)

    def run(self):
        """Main program loop - spawn threads and respawn them when dead
        if the port is still available
        """
<<<<<<< HEAD
        print("Initializing run loop {}".format(__name__))
=======
        self.log.warning("Initializing Run Loop")
>>>>>>> dgsrecorder
        while not self.exiting.is_set():
            try:
                self.scrub_threads()
                self.spawn_threads() 
                time.sleep(.5)
            except KeyboardInterrupt:
<<<<<<< HEAD
=======
                self.log.warning("Ctrl-C captured - initiating exit")
>>>>>>> dgsrecorder
                print(" Ctrl-C Captured - Exiting threads...\n")
                self.exit()

    def exit(self):
        """Controlled exit, join threads and flush logs"""
        self.exiting.set()
        for t in (_ for _ in self.threads if _.is_alive()):
            t.join()
<<<<<<< HEAD
        self.log.shutdown()
        sys.exit(0)


class SerialRecorder(threading.Thread):
    def __init__(self, port, logger, signal):
        threading.Thread.__init__(self)
        #Retain port as name, self.device becomes device path e.g. /dev/ttyS0
        self.name = port
        self.device = os.path.join('/dev', port)
        #exiting is global thread signal - setting will kill all threads
=======
        self.log.warning("Shutting down logging and application")
        self.log.shutdown()
        sys.exit(0)

class SerialRecorder(threading.Thread):
    def __init__(self, port, signal):
        threading.Thread.__init__(self)
        # Retain port as name, self.device becomes device path e.g. /dev/ttyS0
        self.name = port
        self.device = os.path.join('/dev', port)
        # exiting is global thread signal - setting will kill all threads
>>>>>>> dgsrecorder
        self.exiting = signal
        self.kill = False
        self.exc = None
        self.config = {'port' : self.device, 'timeout' : 1} 
        self.data = [] 
<<<<<<< HEAD
        self.log = logger
        self.log.warning("Thread {} initialized".format(self.name))
        self.exiting.clear()
=======

        self.data_log = logging.getLogger(port)
        self.log = logging.getLogger(__name__)
        self.log.info("Thread {} initialized".format(self.name))
        # self.exiting.clear()
>>>>>>> dgsrecorder
    
    def read_data(self, ser, encoding='utf-8'):
        """Perform blocking readline() on serial stream 'ser'
        then decode to a string and strip newline chars '\\n'
        Returns: string
        """
        return ser.readline().decode(encoding).rstrip('\n')

    def exit(self):
<<<<<<< HEAD
        self.log.info("Exiting thread %s", self.name)
=======
        self.log.warning("Exiting thread %s", self.name)
>>>>>>> dgsrecorder
        self.kill = True
        return

    def run(self):
<<<<<<< HEAD
        #TODO: Move this to Class DOCSTRING
=======
        # TODO: Move this to Class DOCSTRING
>>>>>>> dgsrecorder
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
        self.log.debug("Started thread {}".format(self.name))
        while not self.exiting.is_set():
            if self.kill:
                break
            try:
                line = self.read_data(ser)
                if line is not '':
                    self.data.append(line)
<<<<<<< HEAD
                    self.log.critical(line)
=======
                    self.data_log.critical(line)
>>>>>>> dgsrecorder
            except serial.SerialException:
                self.exc = sys.exc_info() 
                break 
        self.exit()
            
if __name__ == "__main__":
    recorder = Recorder()
    recorder.run()
    
<<<<<<< HEAD


=======
>>>>>>> dgsrecorder
