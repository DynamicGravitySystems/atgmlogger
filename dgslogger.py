#!/usr/bin/python3.5

"""
dgslogger.py
Functional main method to execute DGSLogger program
"""

# Imports
import threading
import logging
import os
import sys
import errno
import time
import configparser

from serial.tools.list_ports import comports

try:
    from SerialRecorder import SerialRecorder
except ImportError:
    from dgslogger.SerialRecorder import SerialRecorder

__author__ = 'Zachery Brady'
__copyright__ = 'Copyright 2016, Dynamic Gravity Systems Inc.'
__status__ = 'Development'
__version__ = "0.1.0"


MAX_THREADS = 4
EXIT_E = threading.Event()
LOGLEVEL = logging.DEBUG
LOG_DIR = '/var/log/dgslogger'
LOG_NAME = __name__
DATA_LOG_NAME = 'gravity_log'
LOG_EXT = 'log'
DATA_EXT = 'dat'
DEBUG = True
CONFIG_DEFAULTS = {'SERIAL' : {'port' : 'tty0',
                               'buadrate': 57600,
                               'parity' : 'none',
                               'stopbits' : 1,
                               'timeout' : 1},
                   'DATA' : {'logdir' : '/var/log/dgslogger',
                             'meterid' : 'AT1M-Test',
                             'loginterval' : '1d'}
                  }

def debug_handler(stream=sys.stderr, level=logging.DEBUG):
    """Return a log handler for debugging out to 'stream' e.g. sys.stderr"""
    handler = logging.StreamHandler(stream)
    handler.setLevel(level)
    debug_fmtr = logging.Formatter(
        fmt="%(asctime)s - %(levelname)s - %(module)s.%(funcName)s :: %(message)s",
        datefmt="%y-%m-%d %H:%M:%S")
    handler.setFormatter(debug_fmtr)
    return handler

def check_dirs(path=LOG_DIR):
    """Check for existance and create log dirs if not present"""
    if os.path.exists(path):
        return True
    try:
        os.makedirs(path)
    except OSError as exc:
        logger = logging.getLogger(LOG_NAME)
        if exc.errno == errno.EPERM:
            if DEBUG:
                logger.error('Permission error attempting to create directory %s'\
                        ' are you executing as root?', exc.filename)
        raise exc
    else:
        return True

def read_config(path='./dgslogger'):
    """Read program configuration from a file - or use sensible defaults if
    file cannot be loaded
    """
    config = configparser.ConfigParser()
    if not os.path.exists(path):
        config.read_dict(CONFIG_DEFAULTS)
        return config

    config.read(path)
    return config

def get_applog():
    """Configure and return the application logger (for info/error logging)."""

    app_log = logging.getLogger(LOG_NAME)
    if app_log.hasHandlers():
        return app_log

    app_log.setLevel(LOGLEVEL)
    formatter = logging.Formatter(
        fmt="%(asctime)s - %(levelname)s - %(module)s.%(funcName)s :: %(message)s",
        datefmt="%y-%m-%d %H:%M:%S")

    logfile = os.path.join(LOG_DIR, '.'.join([LOG_NAME, LOG_EXT]))
    rf_handler = logging.handlers.TimedRotatingFileHandler(
        logfile, when='midnight', backupCount=15, encoding='utf-8')
    rf_handler.setLevel(LOGLEVEL)
    rf_handler.setFormatter(formatter)

    # Handle exception here? for permission err
    app_log.addHandler(rf_handler)
    if DEBUG:
        # Output to stream if debug enabled
        app_log.addHandler(debug_handler())
    return app_log

def get_portlog(header=False):
    """Configure log named for the specified port"""
    port_log = logging.getLogger(DATA_LOG_NAME)
    if port_log.hasHandlers():
        return port_log

    logfile = os.path.join(LOG_DIR, '.'.join([DATA_LOG_NAME, DATA_EXT]))
    log_format = logging.Formatter(fmt="%(message)s")
    trf_hdlr = logging.handlers.TimedRotatingFileHandler(
        logfile, when='midnight', backupCount=32, encoding='utf-8')
    trf_hdlr.setLevel(logging.CRITICAL)
    trf_hdlr.setFormatter(log_format)

    port_log.addHandler(trf_hdlr)
    if DEBUG:
        port_log.addHandler(debug_handler())
        port_log.info("Initialized data log in file: %s, debug ON", logfile)
    if header:
        port_log.info("Initialized data log @ time")
    return port_log

def get_ports(path=False):
    """Return a list of serial port names or full device path if path is True"""
    if path:
        return [_.device for _ in comports()]
    return [_.name for _ in comports()]

def spawn_threads(thread_list):
    """Spawn a thread for each serial port available
    Returns: List of port names that were spawned
    """
    # get a list of ports and check that they don't exist in THREADS
    spawn_list = [port for port in get_ports()
                  if port not in [_.name for _ in thread_list]]
    for port in spawn_list:
        thread = SerialRecorder(port, EXIT_E, DATA_LOG_NAME)
        thread.start()
        thread_list.append(thread)
        logging.getLogger(LOG_NAME).info('Started new thread for port %s', thread.name)
    # return list of ports spawned
    return spawn_list

def cull_threads(thread_list):
    """Check for dead threads and remove from thread_list"""
    for thread in thread_list:
        if not thread.is_alive():
            logging.getLogger(LOG_NAME).warning("Thread %s is dead", thread.name)
            thread_list.remove(thread)

def join_threads(thread_list):
    """End and join all threads"""
    for thread in thread_list:
        if not thread.is_alive():
            continue
        thread.exit()
        thread.join()
    cull_threads(thread_list)

def run():
    """Main program run loop - creates and manages threads"""
    config = read_config()
    if not check_dirs():
        logging.getLogger(LOG_NAME).critical("Logging directories cannot"\
                " be created, are you running as root?")
        sys.exit(1)
    log = get_applog()
    threads = []
    log.info("Starting DGSLogger main thread")
    while not EXIT_E.is_set():
        try:
            spawn_threads(threads)
            cull_threads(threads)
            time.sleep(1)
        except KeyboardInterrupt:
            EXIT_E.set()
            join_threads(threads)
            log.warning("KeyboardInterrupt captured - exiting dgslogger")
            sys.exit(0)

if __name__ == "__main__":
    run()
