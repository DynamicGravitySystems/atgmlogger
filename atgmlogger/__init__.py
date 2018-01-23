import sys
import logging

__all__ = ['atgmlogger', 'common', 'applog', 'VERBOSITY_MAP', '__version__',
           '__description__']

__version__ = '0.3.0'
__description__ = "Advanced Technology Gravity Meter - Serial Data Logger"


VERBOSITY_MAP = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
applog = logging.getLogger(__name__)
applog.addHandler(logging.StreamHandler(sys.stderr))
applog.setLevel(VERBOSITY_MAP[0])
