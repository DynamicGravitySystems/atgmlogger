import threading
import time

try:
    import RPi.GPIO as gpio
except ImportError:
    print("Raspberry Pi GPIO module not available")
    raise ImportError


def usb_write(pin):
    for i in range(10):
        gpio.output(pin, True)
        time.sleep(.1)
        gpio.output(pin, False)
        time.sleep(.1)


def data_write(pin):
    gpio.output(pin, True)
    time.sleep(.2)
    gpio.output(pin, False)


def led_thread(e_signal: threading.Event, d_signal: threading.Event, u_signal: threading.Event):
    """
    
    :param e_signal: Thread exit signal
    :param d_signal: Thread data writing signal
    :param u_signal: Thread USB signal
    :return: int
    """
    data_pin = 6
    usb_pin = 7
    gpio.setmode(gpio.BOARD)
    gpio.setup(data_pin, gpio.OUT)
    gpio.setup(usb_pin, gpio.OUT)

    while not e_signal.is_set():
        if u_signal.is_set():
            gpio.output(data_pin, False)
            usb_write(usb_pin)
            u_signal.clear()
        elif d_signal.is_set():
            gpio.output(usb_pin, False)
            data_write(data_pin)
            d_signal.clear()
