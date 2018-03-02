# -*- coding: utf-8 -*-

import io
import logging
from pathlib import Path
from io import TextIOBase

from atgmlogger import APPLOG
from .plugins import PluginInterface
from .dispatcher import Command

__all__ = ['DataLogger', 'SimpleLogger']
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


# Pending deprecation/removal
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
    options = ['loggername', 'datalvl']

    def __init__(self, logger=None):
        super().__init__()
        self._logger = logger or logging.getLogger(__name__)

    def consumes(self, item):
        return isinstance(item, str) or isinstance(item, Command)

    def logrotate(self):
        APPLOG.debug("Doing logrotate")
        raise NotImplementedError("Logrotate not yet implemented")

    def run(self):
        while not self.exiting:
            try:
                item = self.get(block=True, timeout=None)
                if item is None:
                    self.task_done()
                    continue
                if isinstance(item, Command) and item.cmd == 'rotate':
                    self.logrotate()
                else:
                    self._logger.log(DATA_LVL, item)
                    self.context.blink()
            except FileNotFoundError:
                APPLOG.error("Log handler file path not found, data will not "
                             "be saved.")
            self.task_done()

        APPLOG.debug("Exited DataLogger thread.")

    def configure(self, **options):
        super().configure(**options)
        if 'loggername' in options:
            self._logger = logging.getLogger(options['loggername'])


# TODO: this will be renamed
class SimpleLogger(PluginInterface):
    options = ['logfile']

    def __init__(self):
        super().__init__()
        self.logfile = Path('gravdata.dat')
        self._hdl = None  # type: io.TextIOBase
        self._params = dict(mode='w+', buffering=1, encoding='utf-8',
                            newline='\n')

    @staticmethod
    def consumes(item):
        return isinstance(item, str) or isinstance(item, Command)

    @staticmethod
    def consumer_type():
        return {str, Command}

    def _get_fhandle(self):
        self._hdl = self.logfile.open(**self._params)

    def log_rotate(self):
        """
        Call this to notify the logger that logs may have been rotated by the
        system.
        Flush, close then reopen the handle.

        Returns
        -------

        """
        APPLOG.info("LogRotate signal received, re-opening log handle.")
        if self._hdl is None:
            return

        try:
            self._hdl.flush()
            self._hdl.close()
            self._hdl = None
        except IOError:
            APPLOG.exception()
            return

        self._get_fhandle()
        APPLOG.debug("LogRotate completed without exception, handle opened "
                     "on path %s", self._hdl.name)

    def run(self):
        try:
            # self._hdl = self.logfile.open(**self._params)
            self._get_fhandle()
        except IOError:
            APPLOG.exception("Error opening file for writing.")
            return

        while not self.exiting:
            try:
                item = self.get(block=True, timeout=None)
                if item is None:
                    self.queue.task_done()
                    continue
                if isinstance(item, Command):
                    if item.cmd == 'rotate':
                        self.log_rotate()
                else:
                    self._hdl.write(item + '\n')
                    self.context.blink()
                    self.queue.task_done()
            except IOError:
                APPLOG.exception()
                continue
        self._hdl.close()

    def configure(self, **options):
        super().configure(**options)
