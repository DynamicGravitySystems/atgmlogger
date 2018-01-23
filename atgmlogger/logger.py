# coding: utf-8

import queue
import threading
from .common import Blink
from atgmlogger import applog
__all__ = ['DataLogger']

DATA_LVL = 75


class DataLogger(threading.Thread):
    """
    Parameters
    ----------
    data_queue : Union[queue.Queue, mp.Queue]
    logger : logging.Logger
    exit_sig : threading.Event
    gpio_queue : queue.PriorityQueue
    """
    # TODO: Pass logger config dict here for init?
    def __init__(self, data_queue, logger, exit_sig, gpio_queue=None):
        super().__init__(name=self.__class__.__name__)
        self._data_queue = data_queue
        self._exiting = exit_sig
        self._logger = logger
        self._internal_copy = []
        self._gpio_queue = gpio_queue or queue.PriorityQueue()

        # TODO: Infer data rate to better control blinking
        self._blink_data = Blink(11, frequency=0.05)

    def run(self):
        while not self._exiting.is_set() or not self._data_queue.empty():
            try:
                data = self._data_queue.get(block=True, timeout=0.1)
                self._internal_copy.append(data)
                self._logger.log(DATA_LVL, data)
                self._gpio_queue.put_nowait(self._blink_data)
            except queue.Empty:
                # Using timeout and empty exception allows for thread to
                # check exit signal
                continue
            except queue.Full:
                continue
            except FileNotFoundError:
                applog.error("Log handler file path not found, data will not "
                              "be saved.")
            try:
                self._data_queue.task_done()
            except AttributeError:
                # In case of multiprocessing.Queue
                pass

        applog.debug("Exiting DataLogger thread.")
