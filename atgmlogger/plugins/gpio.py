# -*- coding: utf-8 -*-

import logging
import time

from . import PluginInterface
from ..dispatcher import Blink

_APPLOG = logging.getLogger(__name__)

try:
    import RPi.GPIO as gpio
    HAVE_GPIO = True
    __plugin__ = 'GPIOListener'
except (ImportError, RuntimeError):
    HAVE_GPIO = False
    __plugin__ = None


class GPIOListener(PluginInterface):
    options = ['mode', 'data_pin', 'usb_pin']

    def __init__(self):
        super().__init__()
        if not HAVE_GPIO:
            raise RuntimeError("GPIO Module is unavailable. GPIO plugin "
                               "cannot run.")
        self.outputs = []
        self.modes = {'board': gpio.BOARD, 'bcm': gpio.BCM}
        self.data_pin = 11
        self.usb_pin = 13

    @staticmethod
    def consumer_type():
        return {Blink}

    def configure(self, **options):
        _APPLOG.debug("Configuring GPIO with options: {}".format(options))
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
            time.sleep(blink.frequency)
            gpio.output(led_id, False)
            time.sleep(blink.frequency)

    def run(self):
        # TODO: How to trigger constant blink until stopped, while allowing
        # queue events to still be processed.
        # Maybe a separate thread for each output LED, which can be
        # controlled via external signals/calls
        if not HAVE_GPIO:
            _APPLOG.warning("GPIO Module is unavailable. Exiting %s thread.",
                            self.__class__.__name__)
            return

        while not self.exiting:
            blink = self.get()
            if blink is None:
                self.task_done()
                continue
            else:
                self._blink(blink)
                self.task_done()

        for pin in self.outputs:
            gpio.output(pin, False)
        gpio.cleanup()


