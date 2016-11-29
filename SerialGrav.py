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

class Recorder:
    """DGS Logger base class - scans for ports, and sets up threads to record
    data from the serial ports.
    """

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
        applogger.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            fmt="%(asctime)s - %(levelname)s - %(module)s.%(funcName)s :: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S")

        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setLevel(self.loglevel)
        stream_handler.setFormatter(formatter)

        # TODO: Replace this with instance var or from config file
        logpath = 'logs/SerialGrav.log'
        # TODO: Evaluate using system /var/log/... path instead of module dir
        fullpath = os.path.join(os.path.abspath(os.path.dirname(__file__)),
                                os.path.dirname(logpath))

        if not os.path.exists(fullpath):
            try:
                os.makedirs(fullpath)
            except OSError as err:
                print("Error creating log directory: {}".format(err))

        trfh_handler = logging.handlers.TimedRotatingFileHandler(
            './logs/SerialGrav.log', when='midnight', backupCount=15,
            encoding='utf-8', delay=False, utc=False)
        trfh_handler.setLevel(logging.DEBUG)
        trfh_handler.setFormatter(formatter)

        if debug:
            applogger.addHandler(stream_handler)
        applogger.addHandler(trfh_handler)

        applogger.info("Application log initialized")
        return applogger

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
        # Create a stream handler and a timed rotating file handler
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setLevel(logging.WARNING)
        trf_handler = logging.handlers.TimedRotatingFileHandler(
            data_file, when='midnight', backupCount=32, encoding='utf-8',
            delay=False, utc=False)
        trf_handler.setLevel(logging.INFO)
        stream_formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(thread)d - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S")
        file_formatter = logging.Formatter("%(message)s")
        stream_handler.setFormatter(stream_formatter)
        trf_handler.setFormatter(file_formatter)
        data_logger.addHandler(stream_handler)
        data_logger.addHandler(trf_handler)
        self.data_loggers[port] = data_logger
        return data_logger

    @staticmethod
    def _get_ports():
        return [p.name for p in serial.tools.list_ports.comports()]

    def _make_thread(self, port):
        """Create a SerialRecorder thread for a 'port' and injects exit
        event signal.
        Returns SerialRecorder
        """
        self._get_data_logger(port)
        return SerialRecorder(port, self.exiting)

    def spawn_threads(self):
        """Create and start a new SerialRecorder thread for each available
        port found via _get_ports if the current thread count is less than
        self.max_threads
        """
        if len(self.threads) > self.max_threads:
            return 0
        to_spawn = [port for port in self._get_ports() if port not in
                    [_.name for _ in self.threads]]
        for port in to_spawn:
            thread = self._make_thread(port)
            thread.start()
            self.threads.append(thread)

    def scrub_threads(self):
        """Delete threads from thread list if they are dead"""
        for thread in self.threads[:]:
            if not thread.is_alive():
                self.threads.remove(thread)

    def run(self):
        """Main program loop - spawn threads and respawn them when dead
        if the port is still available
        """
        self.log.warning("Initializing Run Loop")
        while not self.exiting.is_set():
            try:
                self.scrub_threads()
                self.spawn_threads()
                time.sleep(.5)
            except KeyboardInterrupt:
                self.log.warning("Ctrl-C captured - initiating exit")
                print(" Ctrl-C Captured - Exiting threads...\n")
                self.exit()

    def exit(self):
        """Controlled exit, join threads and flush logs"""
        self.exiting.set()
        for thread in (_ for _ in self.threads if _.is_alive()):
            thread.join()
        self.log.warning("Shutting down logging and application")
        self.log.shutdown()
        sys.exit(0)


class SerialRecorder(threading.Thread):
    """
    Threaded serial recorder - binds to a serial port and records all text data
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
        self.log = logging.getLogger(__name__)
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
