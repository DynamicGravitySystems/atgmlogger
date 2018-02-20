# coding: utf-8

import queue
import logging
from atgmlogger import APPLOG
from .plugins import PluginInterface
from .dispatcher import Dispatcher
__all__ = ['DataLogger']

DATA_LVL = 75


def level_filter(level):
    """Return a filter function to be used by a logging handler.
    This function is referenced in the default logging config file."""
    def _filter(record):
        """Filter a record based on level, allowing only records less than
        the specified level."""
        if record.levelno < level:
            return True
        return False
    return _filter


class DataLogger(PluginInterface):
    """
    DataLogger conforms to the PluginInterface spec but is not really
    intended to be pluggable or optional.
    It should be explicitly
    imported/loaded in the main program logic/init.
    DataLogger is designed to simply process data from a queue and log it to
    a python logging logger - typically to a file as defined in the program
    configuration (see rcParams).
    """
    options = ['timeout', 'loggername', 'datalvl']
    consumerType = str

    def __init__(self, data_queue=None, logger=None, exit_sig=None):
        super().__init__()

        # For compatibility - TODO: Determine if these should be kept
        if data_queue is not None:
            self.queue = data_queue
        if exit_sig is not None:
            self._exitSig = exit_sig

        self._logger = logger or logging.getLogger(__name__)
        self.timeout = 0.1

    def run(self):
        while not self.exiting:
            try:
                data = self.get(block=True, timeout=self.timeout)
                self._logger.log(DATA_LVL, data)
            except queue.Empty:
                continue
            except FileNotFoundError:
                APPLOG.error("Log handler file path not found, data will not "
                             "be saved.")
            try:
                self.queue.task_done()
            except AttributeError:
                # In case of multiprocessing.Queue
                pass

        APPLOG.debug("Exiting DataLogger thread.")

    def configure(self, **options):
        super().configure(**options)
        if 'loggername' in options:
            self._logger = logging.getLogger(options['loggername'])


class SimpleLogger(PluginInterface):
    options = ['timeout', 'logfile']

    def __init__(self):
        super().__init__()
        self.logfile = 'gravdata.dat'
        self.timeout = 0.2

    def run(self):
        try:
            hdl = open(self.logfile, 'w+', encoding='utf-8', newline='\n')
        except IOError:
            APPLOG.exception("Erroor opening file for writing.")
            return

        while not self.exiting:
            try:
                line = self.get(block=True, timeout=self.timeout)
            except queue.Empty:
                continue
            hdl.write(line + '\n')
        hdl.close()

    def configure(self, **options):
        super().configure(**options)




