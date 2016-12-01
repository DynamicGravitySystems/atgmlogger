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

from serial.tools.list_ports import comports

from SerialRecorder import SerialRecorder

# End Imports

MAX_THREADS = 4
EXIT_E = threading.Event()
LOGLEVEL = logging.DEBUG
LOG_DIR = '/var/log/dgslogger'
LOG_NAME = __name__
LOG_EXT = 'log'
DATA_EXT = 'dat'
DEBUG = True

def debug_handler(stream=sys.stderr, level=logging.DEBUG):
    debug_handler = logging.StreamHandler(stream)
    debug_handler.setLevel(level)
    debug_fmtr = logging.Formatter(
        fmt="%(asctime)s - %(levelname)s - %(module)s.%(funcName)s :: %(message)s",
        datefmt="%y-%m-%d %H:%M:%S")
    debug_handler.setFormatter(debug_fmtr)
    return debug_handler

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
        return False
    else:
        return True


def get_applog(debug=False):
    """Configure and return the application logger (for info/error logging)."""

    app_log = logging.getLogger(LOG_NAME)
    if log.hasHandlers():
        return log

    app_log.setLevel(LOGLEVEL)
    formatter = logging.Formatter(
        fmt="%(asctime)s - %(levelname)s - %(module)s %(funcName)s :: %(message)s",
        datefmt="%y-%m-%d %H:%M:%S")

    logfile = os.path.join(LOG_DIR, '.'.join([LOG_NAME, LOG_EXT]))
    rf_handler = logging.handlers.TimedRotatingFileHandler(
        logfile, when='midnight', backupCount=15, encoding='utf-8')
    rf_handler.setLevel(LOGLEVEL)
    rf_handler.setFormatter(formatter)

    log.addHandler(rf_handler)
    if DEBUG:
        # Output to stream if debug enabled
        log.addHandler(debug_handler())
    return log

def get_portlog(port, header=False):
    """Configure log named for the specified port"""
    port_log = logging.getLogger(port)
    if port_log.hasHandlers():
        return port_log

    logfile = os.path.join(LOG_DIR, '.'.join([port, DATA_EXT]))
    log_format = logging.Formatter(fmt="%(message)s")
    trf_hdlr = logging.handlers.TimedRotatingFileHandler(logfile,
            when='midnight', backupCount=32, encoding='utf-8')
    trf_hdlr.setLevel(logging.CRITICAL)
    trf_hdlr.setFormatter(log_format)

    port_log.addHandler(trf_hdlr)
    if DEBUG:
        port_log.addHandler(debug_handler())
    if header:
        port_log.info("Initialized Serial Port Log on port: %s", port)
    return port_log

def get_ports(path=False):
    """Return a list of serial port names or full device path if path is True"""
    if path:
        return [_.device for _ in comports()]
    return [_.name for _ in comports()]

def spawn_threads(thread_list):
    """Spawn a thread for each serial port available"""
    # get a list of ports and check that they don't exist in THREADS
    spawn_list = [port for port in get_ports()
                  if port not in [_.name for _ in thread_list]]

    # TODO add logic to limit threads to reasonable number

    for port in spawn_list:
        port_log = get_portlog(port)
        thread = SerialRecorder(port, EXIT_E)
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
    log = configure(debug=True)
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
