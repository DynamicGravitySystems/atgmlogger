# -*- coding: utf-8 -*-

import os
import sys
import copy
import json
import logging
from io import TextIOWrapper
from typing import Dict
from pathlib import Path

__all__ = ['atgmlogger', 'common', 'APPLOG', 'VERBOSITY_MAP', '__version__',
           '__description__', 'rcParams']

__version__ = '0.3.1'
__description__ = "Advanced Technology Gravity Meter - Serial Data Logger"


VERBOSITY_MAP = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
APPLOG = logging.getLogger()
APPLOG.addHandler(logging.StreamHandler(sys.stderr))
APPLOG.setLevel(VERBOSITY_MAP[0])


class _ConfigParams:
    """Centralize the loading and dissemination of configuration parameters"""
    cfg_name = '.atgmlogger'
    cfg_paths = [Path('~').expanduser().joinpath(cfg_name),
                 Path('/opt/atgmlogger').joinpath(cfg_name),
                 Path('/etc/atgmlogger').joinpath(cfg_name)]

    def __init__(self, config: Dict=None, path=None):
        self._default = config or dict()
        self._working = copy.deepcopy(config) or dict()
        self._path = None

        if path is not None:
            with Path(path).open('r') as fd:
                self.load_config(fd)

        if not self._default:
            for cfg in self.cfg_paths:  # type: Path
                if cfg.exists():
                    with cfg.open('r') as fd:
                        self.load_config(fd)
                    break
            else:
                APPLOG.warning("No configuration file could be located, "
                               "attempting to load default.")
                try:
                    import pkg_resources as pkg
                    rawfd = pkg.resource_stream(__name__ + '.install',
                                                '.atgmlogger')
                    text_wrapper = TextIOWrapper(rawfd, encoding='utf-8')

                    self.load_config(text_wrapper)
                except IOError:
                    APPLOG.exception("Error loading default configuration.")
                else:
                    APPLOG.info("Successfully loaded fallback configuration.")

    def load_config(self, descriptor):
        if not hasattr(descriptor, 'read'):
            APPLOG.warning("Invalid file descriptor passed to load_config.")
            return
        try:
            cfg = json.load(descriptor)
        except json.JSONDecodeError:
            APPLOG.exception("JSON Exception decoding: %s", descriptor.name)
            cfg = dict()
        self._path = Path(descriptor.name)
        self._default = cfg
        self._working = copy.deepcopy(cfg)

    def update(self):
        # TODO: This is too rigid for my liking
        self._expand_paths(self['logging'], 'filename', self['logging.logdir'])

    def get_default(self, key):
        base = self._default
        for part in key.split('.'):
            base = base.get(part, None)
        return base or None

    def _expand_paths(self, leaf, key, base_path):
        """Expand filenames within logging configuration section"""
        if not self._default:
            return

        for k, v in leaf.items():
            if k == key:
                expanded = os.path.normpath(os.path.join(base_path, v))
                leaf[k] = expanded
                continue
            elif isinstance(v, dict):
                self._expand_paths(v, key, base_path)

    @property
    def config(self):
        if not self._working:
            self._working = copy.deepcopy(self._default)
        return self._working

    @property
    def path(self):
        return self._path

    def __getattr__(self, item):
        pass

    def __getitem__(self, key: str):
        base = self.config
        for part in key.split('.'):
            base = base.get(part, {})
        return base or None

    def __setitem__(self, key, value):
        base = self.config
        path = key.split('.')
        last = path.pop()

        # TODO: Allow creation of new paths or not?
        for part in path:
            base = base.setdefault(part, {})
        base[last] = value

    def __str__(self):
        return ''


rcParams = _ConfigParams()
