# -*- coding: utf-8 -*-

import sys
import logging

__all__ = ['APPLOG', 'VERBOSITY_MAP', 'POSIX', '__version__', '__description__']

__version__ = '0.3.4'
__description__ = "Advanced Technology Gravity Meter - Serial Data Logger"


VERBOSITY_MAP = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
APPLOG = logging.getLogger()
APPLOG.addHandler(logging.StreamHandler(sys.stderr))
APPLOG.setLevel(VERBOSITY_MAP[0])

if sys.platform.lower().startswith('linux'):
    POSIX = True
else:
    POSIX = False


