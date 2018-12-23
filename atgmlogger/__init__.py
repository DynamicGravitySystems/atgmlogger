# -*- coding: utf-8 -*-

import sys
import logging

__all__ = ['LOG_LVLMAP', 'LOG_FMT', 'SIMPLE_LOG_FMT', 'TRACE_LOG_FMT', 'DATE_FMT', 'POSIX',
           '__version__', '__description__']

__version__ = "0.5.0-alpha.1"
__description__ = "Advanced Technology Gravity Meter - Serial Data Logger"


LOG_LVLMAP = {0: logging.CRITICAL,
              1: logging.ERROR,
              2: logging.WARNING,
              3: logging.INFO,
              5: logging.DEBUG}
# Application level root logger - all other loggers should branch from this
# Note, only stderr handler is configured here. Output to file is configured
# in atgmlogger.py
APPLOG = logging.getLogger('atgmlogger')
LOG_FMT = "%(levelname)8s::%(asctime)s - (%(name)s/%(funcName)s) %(message)s"
SIMPLE_LOG_FMT = "%(levelname)8s::%(asctime)s - %(message)s"
TRACE_LOG_FMT = "%(levelname)8s::%(asctime)s - (%(name)s/%(funcName)s:%(lineno)d " \
                "- thread: %(threadName)s) %(message)s"
DATE_FMT = "%Y-%m-%d::%H:%M:%S"
_stderr_hdlr = logging.StreamHandler(sys.stderr)
_stderr_hdlr.setFormatter(logging.Formatter(LOG_FMT, datefmt=DATE_FMT))
APPLOG.addHandler(_stderr_hdlr)

if sys.platform.lower().startswith("linux"):
    POSIX = True
else:
    POSIX = False


_changes = {
    '0.5.0-alpha.1': 'Experimental build with support for streaming data to collector',
}
