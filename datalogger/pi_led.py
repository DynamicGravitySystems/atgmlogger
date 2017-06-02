import threading
import time
import logging

try:
    import RPi.GPIO as gpio
except ImportError:
    print("Raspberry Pi GPIO module not available")
    raise ImportError

DATA_PIN = 32
USB_PIN = 36
LOG_NAME = 'datalog'


def usb_write(pin):
    for i in range(10):
        gpio.output(pin, True)
        time.sleep(.1)
        gpio.output(pin, False)
        time.sleep(.1)


def data_write(pin):
    gpio.output(pin, True)
    time.sleep(.1)
    gpio.output(pin, False)


def led_thread(e_signal: threading.Event, d_signal: threading.Event, u_signal: threading.Event):
    """
    
    :param e_signal: Thread exit signal
    :param d_signal: Thread data writing signal
    :param u_signal: Thread USB signal
    :return: int
    """
    gpio.setmode(gpio.BOARD)
    gpio.setup(DATA_PIN, gpio.OUT)
    gpio.setup(USB_PIN, gpio.OUT)

    applog = logging.getLogger(LOG_NAME) 
    
    while not e_signal.is_set():
        if u_signal.is_set():
            gpio.output(DATA_PIN, False)
            usb_write(USB_PIN)
            u_signal.clear()
        elif d_signal.is_set():
            gpio.output(USB_PIN, False)
            data_write(DATA_PIN)
            d_signal.clear()
        elif e_signal.is_set():
            return
    if e_signal.is_set():
        applog.debug("Cleaning up and exiting led_thread")
        gpio.cleanup()
    return 0
	
