# -*- coding: utf-8 -*-

import sys
import logging

__all__ = ['APPLOG', 'LOG_LVLMAP', 'POSIX', '__version__', '__description__']

__version__ = '0.3.42'
__description__ = "Advanced Technology Gravity Meter - Serial Data Logger"


LOG_LVLMAP = {0: logging.CRITICAL,
              1: logging.ERROR,
              2: logging.WARNING,
              3: logging.INFO,
              5: logging.DEBUG}
APPLOG = logging.getLogger()
_stderr_hdlr = logging.StreamHandler(sys.stderr)
_stderr_hdlr.setFormatter(logging.Formatter("%(levelname)s::%(asctime)s - %("
                                            "message)s",
                                            datefmt="%Y-%m-%d::%H:%M:%S"))
APPLOG.addHandler(_stderr_hdlr)

if sys.platform.lower().startswith('linux'):
    POSIX = True
else:
    POSIX = False
