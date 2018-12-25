# -*- coding: utf-8 -*-
# This file is part of ATGMLogger https://github.com/bradyzp/atgmlogger

import io
import logging
from pathlib import Path

from .plugins import PluginInterface
from .types import Command, CommandSignals, DataLine

__all__ = ['DataLogger']
LOG = logging.getLogger(__name__)


class DataLogger(PluginInterface):
    options = ['logfile']

    def __init__(self):
        super().__init__()
        self.logfile = Path('gravdata.dat')
        self._hdl = None  # type: io.TextIOBase
        self._params = dict(mode='w+', buffering=1, encoding='utf-8',
                            newline='\n')

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
        LOG.info("LogRotate signal received, re-opening log handle.")
        if self._hdl is None:
            return

        try:
            self._hdl.flush()
            self._hdl.close()
            self._hdl = None
        except IOError:
            LOG.exception("IOError encountered rotating log file.")
            return

        self._get_fhandle()
        LOG.debug("LogRotate completed without exception, handle opened "
                  "on path %s", self._hdl.name)

    def run(self):
        try:
            self._get_fhandle()
        except IOError:
            LOG.exception("Error opening file for writing.")
            return

        while not self.exiting:
            try:
                item = self.get(block=True, timeout=None)
                if item is None:
                    self.queue.task_done()
                    continue
                elif isinstance(item, Command):
                    if item.cmd is CommandSignals.SIGHUP:
                        self.log_rotate()
                else:
                    self._hdl.write(item + '\n')
                    self.context.blink()
                    self.queue.task_done()
            except IOError:
                LOG.exception("IOError attempting to read/write data line")
                continue
        self._hdl.close()

    def configure(self, **options):
        super().configure(**options)
