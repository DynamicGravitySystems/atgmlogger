# -*- coding: utf-8 -*-
# This file is part of ATGMLogger https://github.com/bradyzp/atgmlogger

import logging
import threading
from pathlib import Path
from queue import Queue

from ._types import Command, CommandSignals, DataLine

__all__ = ['DataLogger']
LOG = logging.getLogger(__name__)


class DataLogger(threading.Thread):
    """DataLogger is the primary logging facility which ingests raw sensor data
    and writes it to a file on disk.

    """
    def __init__(self, logpath: Path, context, filename='gravdata.dat'):
        super().__init__(name='DataLogger')
        self.logfile = Path(logpath).joinpath(filename)
        self.queue = Queue()
        self.sig_exit = threading.Event()
        self.context = context
        self._hdl_params = dict(mode='w+',
                                buffering=1,
                                encoding='utf-8',
                                newline='\n')
        try:
            self._hdl = self._get_fhandle()
        except IOError:
            LOG.exception("Error opening file handle.")
            raise
        else:
            LOG.debug('Logging thread initialized')

    @property
    def exiting(self) -> bool:
        return self.sig_exit.is_set()

    def exit(self, join=False):
        if join:
            self.queue.join()
        self.sig_exit.set()
        if self.is_alive():
            self.queue.put(None)
            self.join()

    def _get_fhandle(self):
        return self.logfile.open(**self._hdl_params)

    def log_rotate(self):
        """Call this to notify the logger that logs may have been rotated by the
        system.

        Flushes, closes, then reopens the current log/file handle.

        Returns
        -------
        None

        """
        LOG.info("LogRotate signal received, re-opening log handle.")
        if self._hdl is None:
            LOG.warning("No handle exists, will attempt to open.")
            self._hdl = self._get_fhandle()
            return self._hdl
        try:
            self._hdl.flush()
            self._hdl.close()
            self._hdl = None
        except IOError:
            LOG.exception("IOError encountered rotating log file.")
            return

        self._hdl = self._get_fhandle()
        LOG.debug("LogRotate completed without exception, handle opened "
                  "on path %s", self._hdl.name)

    def log(self, item):
        self.queue.put_nowait(item)

    def run(self):
        if self._hdl is None:
            raise IOError("No file handle available. Critical Error.")

        while not self.exiting:
            try:
                item = self.queue.get(block=True, timeout=None)
                if item is None:
                    self.queue.task_done()
                    continue
                if isinstance(item, DataLine):
                    self._hdl.write(item.data + '\n')
                    self.context.blink()
                    self.queue.task_done()
                elif isinstance(item, Command):
                    if item.cmd is CommandSignals.SIGHUP:
                        self.log_rotate()
                    self.queue.task_done()
            except IOError:
                LOG.exception("IOError attempting to read/write data line")
                continue
            except Exception:
                LOG.exception("Unexpected exception in logging thread. "
                              "Continuing.")
                continue
        LOG.info("Logging thread exiting")
        self._hdl.close()
