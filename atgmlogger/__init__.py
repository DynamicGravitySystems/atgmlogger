# -*- coding: utf-8 -*-

import os
import sys
import copy
import json
import logging
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
        self._path = path

        if path is not None:
            self.load_config(path)

        if not self._default:
            for cfg in self.cfg_paths:
                if os.path.exists(cfg):
                    self.load_config(cfg)
                    self._path = cfg
                    break
            else:
                APPLOG.warning("No configuration file could be located, "
                               "proceeding with defaults.")

    def load_config(self, path):
        if not isinstance(path, Path):
            path = Path(path)
        with path.open('r') as fd:
            try:
                cfg = json.load(fd)
            except json.JSONDecodeError:
                APPLOG.exception("JSON Exception decoding: %s", str(path))
                cfg = dict()
        self._default = cfg
        self._working = copy.deepcopy(cfg)

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
