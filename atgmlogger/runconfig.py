# -*- coding: utf-8 -*-
# This file is part of ATGMLogger https://github.com/bradyzp/atgmlogger

import copy
import json
import logging
from io import TextIOWrapper
from pathlib import Path
from typing import Dict


__all__ = ['rcParams']
_base = __name__.split('.')[0]
LOG = logging.getLogger(__name__)


class _ConfigParams:
    """Centralize the loading and dissemination of configuration parameters"""
    cfg_name = '.atgmlogger'
    cfg_paths = [Path('~').expanduser().joinpath(cfg_name),
                 Path('/etc/atgmlogger').joinpath(cfg_name),
                 Path('/opt/atgmlogger').joinpath(cfg_name)]

    def __init__(self, config: Dict=None, path=None):
        self._default = config or dict()
        self._working = copy.deepcopy(config) or dict()
        self._path = None
        search_paths = copy.copy(self.cfg_paths)
        if path is not None:
            search_paths.insert(0, Path(path))

        if not self._default:
            for cfg in search_paths:  # type: Path
                if cfg.exists():
                    with cfg.open('r') as fd:
                        self.load_config(fd)
                    if self._default:
                        LOG.info("Loaded configuration from: %s",
                                 str(self._path))
                        break
            else:
                LOG.warning("No configuration file could be located, "
                            "attempting to load default.")
                LOG.warning("Execute with --install option to install "
                            "default configuration files.")
                try:
                    import pkg_resources as pkg
                    rawfd = pkg.resource_stream(_base + '.install',
                                                '.atgmlogger')
                    text_wrapper = TextIOWrapper(rawfd, encoding='utf-8')

                    self.load_config(text_wrapper)
                except IOError:
                    LOG.exception("Error loading default configuration.")
                else:
                    LOG.info("Successfully loaded default configuration.")

    def load_config(self, descriptor):
        try:
            cfg = json.load(descriptor)
        except json.JSONDecodeError:
            LOG.exception("JSON Exception decoding: %s", descriptor.name)
            cfg = self._default
        self._path = Path(descriptor.name)
        self._default = cfg
        self._working = copy.deepcopy(cfg)
        if cfg:
            LOG.info("Loaded Configuration from %s", str(self._path))

    def get_default(self, key):
        base = self._default
        for part in key.split('.'):
            base = base.get(part, None)
        return base or None

    def dump(self, path: Path=None, overrides=False, exist_ok=False):
        path = path or self.path
        if not exist_ok and path.exists():
            raise FileExistsError("Destination configuration already exists. "
                                  "Set exist_ok=True to override.")
        if overrides:
            cfg = self._working
        else:
            cfg = self._default
        try:
            LOG.info("Writing current configuration to %s", str(path))
            with path.open('w+') as fd:
                json.dump(cfg, fd, indent=2)
        except (IOError, OSError):
            LOG.exception("Exception attempting to save configuration to disk.")

    @property
    def config(self):
        if not self._working:
            self._working = copy.deepcopy(self._default)
        return self._working

    @property
    def path(self) -> Path:
        return self._path

    def __getitem__(self, key: str):
        base = self.config
        for part in key.split('.'):
            base = base.get(part, {})
        if isinstance(base, dict):
            return copy.deepcopy(base) or None
        return base or None

    def __setitem__(self, key, value):
        base = self.config
        path = key.split('.')
        last = path.pop()

        for part in path:
            base = base.setdefault(part, {})
        base[last] = value


rcParams = _ConfigParams()
