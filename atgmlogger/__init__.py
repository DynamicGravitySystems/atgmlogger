import sys
import logging

__all__ = ['atgmlogger', 'common', 'APPLOG', 'VERBOSITY_MAP', '__version__',
           '__description__']

__version__ = '0.3.1'
__description__ = "Advanced Technology Gravity Meter - Serial Data Logger"


VERBOSITY_MAP = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
APPLOG = logging.getLogger(__name__)
APPLOG.addHandler(logging.StreamHandler(sys.stderr))
APPLOG.setLevel(VERBOSITY_MAP[0])
