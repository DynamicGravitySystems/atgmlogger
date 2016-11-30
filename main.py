#!/usr/bin/python3.5

"""
main.py
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

from SerialGrav import SerialRecorder

# End Imports

MAX_THREADS = 4
EXIT_E = threading.Event()
LOGLEVEL = logging.DEBUG
LOG_PATH = '/var/log/dgslogger'
LOG_NAME = __name__

def configure(path=LOG_PATH, retry=0, debug=False):
    """Configure base program functions, logging and directories needed"""
    # Ensure or create logging directory
    if not os.path.isdir(path):
        print("Error initiating logging: {} is not a directory".format(LOG_PATH))
        configure(path=os.path.abspath('./logs'), retry=1)
    if not os.path.exists(path):
        try:
            os.makedirs(path)
        except OSError as err:
            if err.errno == errno.EPERM:
                print("Error - insufficient privileges to create logging directory {}"\
                        .format(path))
            if retry > 0:
                # Prevent loop if unable to create dir in 1st or 2nd attempt
                sys.exit(1)
            configure(path=os.path.abspath('./logs'), retry=1)

    # Initialize application log
    log = logging.getLogger(LOG_NAME)
    log.setLevel(LOGLEVEL)
    formatter = logging.Formatter(
        fmt="%(asctime)s - %(levelname)s - %(module)s.%(funcName)s :: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S")
    st_handler = logging.StreamHandler(sys.stderr)
    st_handler.setLevel(LOGLEVEL)
    st_handler.setFormatter(formatter)

    logfile = os.path.join(path, '.'.join([LOG_NAME, 'log']))
    rf_handler = logging.handlers.TimedRotatingFileHandler(
        logfile, when='midnight', backupCount=15, encoding='utf-8')
    rf_handler.setLevel(LOGLEVEL)
    rf_handler.setFormatter(formatter)

    if debug:
        # Output to stream if debug enabled
        log.addHandler(st_handler)
    log.addHandler(rf_handler)
    return log

def configure_datalog(port, header=False):
    """Configure log named for the specified port"""
    # TODO: Configure serial port loggers
    pass


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

    if len(thread_list) > MAX_THREADS:
        # Reached concurrent thread limit
        logging.getLogger(LOG_NAME).warning("Reached thread limit trying to create\
                thread for port %s", ','.join(spawn_list))
        return 0

    for port in spawn_list:
        thread = SerialRecorder(port, EXIT_E)
        thread.start()
        thread_list.append(thread)
        logging.getLogger(LOG_NAME).info("Started new thread for port %s", thread.name)

def cull_threads(thread_list):
    """Check for dead threads and remove from thread_list"""
    for thread in thread_list:
        if not thread.is_alive():
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
            sys.exit(0)

if __name__ == "__main__":
    run()
