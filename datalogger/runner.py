# coding=utf-8

import threading
import time
import os
import logging
import logging.config
import sys
import pkg_resources

import yaml
import serial
from serial.tools.list_ports import comports

try:
    from datalogger.pi_led import led_thread
except ImportError:
    def led_thread(**_):
        print("Dummy LED thread")
        return False


LOG_NAME = 'datalog'
LOG_CONFIG = 'logging.yaml'
SER_BAUDRATE = 57600
POLL_INTERVAL = 1

# decode_str :: [Byte] -> String
def decode_str(byte_str) -> str:
    """
    Safely decode an ASCII string received from a serial port. Stripping characters that
    will cause a unicode decode error and returning a unicode 'utf-8' string.
    :param byte_str: ASCII encoded byte 'string'
    :return: utf-8 str
    """
    if isinstance(byte_str, str):
        return byte_str
    try:
        decoded = byte_str.decode('utf-8')
    except UnicodeDecodeError:
        illegal = [0, 255]
        decoded = bytes([x for x in byte_str if x not in illegal]).decode('utf-8')
    except AttributeError:
        decoded = None
    return decoded


def log_data(data):
    log = logging.getLogger(LOG_NAME)
    log.log(60, data)


def logger_thread(dev_path, e_signal: threading.Event, d_signal: threading.Event=None,
                  l_signal: threading.Event=None):
    """
    
    :param dev_path: FileSystem path to Serial Device to read from
    :param e_signal: Thread signal to signal program exit
    :param l_signal: Thread signal to signal LED should be activated
    :return: 
    """
    try:
        serial_hdl = serial.Serial(dev_path, baudrate=SER_BAUDRATE)
    except serial.SerialException:
        logging.getLogger(LOG_NAME).debug('exception trying to open port %s', dev_path)
        return 1

    while not e_signal.is_set():
        try:
            logging.getLogger(LOG_NAME).debug('trying to read data')
            log_data("Waiting for Input")
            data = decode_str(serial_hdl.readline())
            if data is not None:
                # TODO: Add logging output from data
                if d_signal:
                    d_signal.set()
                log_data(data)
        except serial.SerialException:
            logging.getLogger(LOG_NAME).debug('encountered serial exception while attempting to read from port')
            serial_hdl.close()
            return 1

    logging.getLogger(LOG_NAME).debug('Closing serial handle')
    serial_hdl.close()
    return 0


def is_alive(thread: threading.Thread):
    return thread.is_alive()


def check_config_paths(config_dict, fallback_path=None):
    """Take a logging configuration dictionary and check handlers for filename
    properties. If they have a filename then check that the path to file exists.
    If the path doesn't exist, update the value to the fallback_path and return
    the new dictionary."""
    if fallback_path is None:
        fallback_path = './logs'
    # TODO: Investigate way to deep-copy dictionary as to not mutate the original
    n_config_dict = config_dict.copy()
    for handler, properties in config_dict.get('handlers').items():
        prop_filename = properties.get('filename', None)
        if prop_filename is None:
            continue
        base_path, filename = os.path.split(prop_filename)
        if not os.path.exists(base_path):
            n_config_dict['handlers'][handler]['filename'] = os.path.normpath(
                os.path.join(fallback_path, filename)
            )
    return n_config_dict


def configure_logging(conf_file=None):
    """
    Configure the logging for the application from a yaml file.
    """
    if conf_file is None:
        conf_file = 'logging.yaml'

    # Consider adding exception handling here, but to what end?
    resource = pkg_resources.resource_stream(__package__, conf_file)
    dict_conf = yaml.load(resource)

    # Do some path checking on any 'filename' keys in dict_conf['handlers']
    #default_path = '/var/log/dgslogger'
    default_path = './logs'
    make_default = True
    # Iterate through dict_conf 'handlers' looking for
    dict_conf = check_config_paths(dict_conf, default_path)

    # Make the default sub-directory if required.
    if make_default and not os.path.exists(default_path):
        os.mkdir(default_path, mode=0o770)

    # Execute logging configuration
    logging.config.dictConfig(dict_conf)
    # Return list of available loggers from the configuration dict.
    return list(dict_conf.get('loggers').keys())


def run():
    """
    Main program loop - executes threads for serial port listener, GPIO control, and USB file operations
    :return: 0
    """

    # Note: Ports should always be referenced by the full device path, e.g. /dev/ttyUSB0

    configure_logging(LOG_CONFIG)
    log = logging.getLogger(LOG_NAME)
    log.info('DGS Logger initialized')

    threads = []
    exit_signal = threading.Event()
    data_signal = threading.Event()
    usb_signal = threading.Event()

    led_th = threading.Thread(target=led_thread, name='raspi-led',
                              kwargs={'e_signal': exit_signal, 'd_signal': data_signal, 'u_signal': usb_signal})
    led_th.start()
    threads.append(led_th)

    while not exit_signal.is_set():
        ports = comports()
        if ports:
            port = ports[0].device
        else:
            log.warning('No Ports available')
            time.sleep(POLL_INTERVAL)
            continue

        threads = list(filter(is_alive, threads[:]))
        if port not in [th.name for th in threads]:
            log.debug('Spawning new thread for %s', port)
            n_thread = threading.Thread(target=logger_thread, name=port,
                                        kwargs={'dev_path': port, 'e_signal': exit_signal, 'd_signal': data_signal})
            n_thread.start()
            threads.append(n_thread)

        time.sleep(POLL_INTERVAL)
    log.debug('Program Exiting')
    return 0
