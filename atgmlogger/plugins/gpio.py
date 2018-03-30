# -*- coding: utf-8 -*-

import threading
import time
import queue

from . import PluginInterface
from .. import APPLOG
from ..dispatcher import Blink


try:
    import RPi.GPIO as gpio
    HAVE_GPIO = True
    __plugin__ = 'GPIOListener'
except (ImportError, RuntimeError):
    HAVE_GPIO = False
    __plugin__ = None


class _BlinkUntil(threading.Thread):
    def __init__(self, delegate, blink, duration=None):
        super().__init__(name=self.__class__.__name__)
        self._exit_sig = threading.Event()
        self._delegate = delegate
        self._blink = blink
        self.led = blink.led
        self._duration = duration or 0

    @property
    def exiting(self):
        return self._exit_sig.is_set()

    def exit(self):
        self._exit_sig.set()

    def run(self):
        while not self.exiting:
            self._duration -= 1
            if self._duration == 0:
                break
            else:
                self._delegate(self._blink)


# TODO: Consider limiting queue size, or inferring elsewhere the data rate
# Limiting the queue might cause continuous blinks to be ignored if put with
# nowait - this does cause random behavior where the continuous start signal
# might be received but not the stop
class GPIOListener(PluginInterface):
    options = ['mode', 'data_pin', 'usb_pin', 'freq']

    def __init__(self):
        super().__init__()
        if not HAVE_GPIO:
            raise RuntimeError("GPIO Module is unavailable. GPIO plugin "
                               "cannot run.")
        self.outputs = []
        self.modes = {'board': gpio.BOARD, 'bcm': gpio.BCM}
        self.data_pin = 11
        self.usb_pin = 13
        self.freq = 0.04

        self._blink_until_sig = threading.Event()
        # self.queue = queue.Queue(maxsize=20)

    @staticmethod
    def consumer_type():
        return {Blink}

    def configure(self, **options):
        super().configure(**options)
        _mode = self.modes[getattr(self, 'mode', 'board')]
        gpio.setwarnings(False)
        gpio.setmode(_mode)

        self.outputs = [getattr(self, pin) for pin in ['data_pin', 'usb_pin']
                        if hasattr(self, pin)]
        for pin in self.outputs:
            gpio.setup(pin, gpio.OUT)

    def _get_pin(self, name: str) -> int:
        if name.lower().startswith('data'):
            return self.data_pin
        elif name.lower().startswith('usb'):
            return self.usb_pin

    def _blink(self, blink):
        if isinstance(blink.led, str):
            led_id = self._get_pin(blink.led)
        else:
            led_id = blink.led
        if led_id not in self.outputs:
            return
        if HAVE_GPIO:
            gpio.output(led_id, True)
            time.sleep(self.freq)
            gpio.output(led_id, False)
            time.sleep(self.freq)

    def _blink_until_stopped(self, blink):
        while not self._blink_until_sig.is_set():
            self._blink(blink)

    def run(self):
        # TODO: How to trigger constant blink until stopped, while allowing
        # queue events to still be processed.
        # Maybe a separate thread for each output LED, which can be
        # controlled via external signals/calls
        if not HAVE_GPIO:
            APPLOG.warning("GPIO Module is unavailable. Exiting %s thread.",
                            self.__class__.__name__)
            return

        subthreads = dict()

        while not self.exiting:
            blink = self.get()
            if blink is None:
                self.task_done()
                continue
            elif blink.until_stopped:
                if blink.led in subthreads:
                    # then stop the continuous blink
                    self._blink_until_sig.set()
                    thread = subthreads[blink.led]
                    thread.join()
                    del subthreads[blink.led]
                    self._blink_until_sig.clear()
                else:
                    # start a new continuous blink
                    worker = threading.Thread(target=self._blink_until_stopped,
                                              args=[blink])
                    worker.start()
                    subthreads[blink.led] = worker
                    del worker
            else:
                self._blink(blink)
                self.task_done()

        for pin in self.outputs:
            gpio.output(pin, False)
        gpio.cleanup()
