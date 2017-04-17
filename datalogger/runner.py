# coding=utf-8

import threading
import time
import logging
import sys

import serial
from serial.tools.list_ports import comports

try:
    from datalogger.pi_led import led_thread
except ImportError:
    def led_thread(**_):
        print("Dummy LED thread")
        return False


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


def logger_thread(dev_path, e_signal: threading.Event, d_signal: threading.Event=None):
    """
    
    :param dev_path: FileSystem path to Serial Device to read from
    :param e_signal: Thread signal to signal program exit
    :param l_signal: Thread signal to signal LED should be activated
    :return: 
    """
    try:
        serial_hdl = serial.Serial(dev_path, baudrate=57600)
    except serial.SerialException:
        logging.getLogger('debug').debug('exception trying to open port %s', dev_path)
        return 1

    while not e_signal.is_set():
        try:
            logging.getLogger('debug').debug('trying to read data')
            data = decode_str(serial_hdl.readline())
            if data is not None:
                # TODO: Add logging output from data
                if d_signal:
                    d_signal.set()
                print(data)
        except serial.SerialException:
            logging.getLogger('debug').debug('encountered serial exception while attempting to read from port')
            serial_hdl.close()
            return 1

    serial_hdl.close()
    return 0


def is_alive(thread: threading.Thread):
    return thread.is_alive()


def run():
    """
    Main program loop - executes threads for serial port listener, GPIO control, and USB file operations
    :return: 0
    """

    # Note: Ports should always be referenced by the full device path, e.g. /dev/ttyUSB0
    debug_logger = logging.getLogger('debug')
    debug_logger.setLevel(logging.DEBUG)
    debug_logger.addHandler(logging.StreamHandler(stream=sys.stdout))

    threads = []
    exit_signal = threading.Event()
    data_signal = threading.Event()
    usb_signal = threading.Event()

    led_th = threading.Thread(target=led_thread, name='raspi-led', kwargs={'e_signal': exit_signal,
                                                                           'd_signal': data_signal,
                                                                           'u_signal': usb_signal})
    led_th.start()
    threads.append(led_th)

    while not exit_signal.is_set():
        ports = comports()
        if ports:
            port = ports[0].device
        else:
            debug_logger.debug('No ports available, sleeping for .5sec')
            time.sleep(.5)

        threads = list(filter(is_alive, threads[:]))
        if port not in [th.name for th in threads]:
            debug_logger.debug('Spawning new thread for %s', port)
            n_thread = threading.Thread(target=logger_thread, name=port,
                                        kwargs={'dev_path': port, 'e_signal': exit_signal, 'd_signal': data_signal})
            n_thread.start()
            threads.append(n_thread)

        time.sleep(1)

    debug_logger.debug('Process exiting')
    return 0
