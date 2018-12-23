# -*- coding: utf-8 -*-
# This file is part of ATGMLogger https://github.com/bradyzp/atgmlogger

import copy
import json
import logging
from collections import UserDict
from pathlib import Path

__all__ = ['rcParams']
LOG = logging.getLogger(__name__)


class RunConfig(UserDict):
    def __init__(self, path: Path):
        assert isinstance(path, Path)
        self.path = path

        try:
            with self.path.open('r') as fd:
                config = json.load(fd)
        except json.JSONDecodeError:
            LOG.exception("Error decoding configuration file")
            super().__init__(RunConfig._load_default())
        except FileNotFoundError:
            super().__init__(RunConfig._load_default())
        else:
            super().__init__(config)

    @staticmethod
    def _load_default():
        LOG.warning("Loading default configuration values")
        return dict(sensor={"name": "undefined"},
                    serial={"port": "/dev/serial0",
                            "baudrate": 57600,
                            "bytesize": 8,
                            "parity": "N",
                            "stopbits": 1},
                    logging={"logdir": "./atgmlogger"},
                    plugins={})

    def __getitem__(self, key: str):
        branch = self.data
        for node in key.split('.'):
            branch = branch[node]
        if isinstance(branch, dict):
            return copy.deepcopy(branch)
        return branch

    def __setitem__(self, key, value):
        branch = self.data
        path = key.split('.')
        last = path.pop()

        for segment in path:
            branch = branch.setdefault(segment, {})
        branch[last] = value

    def load_config(self, path: Path) -> None:
        """Reload and replace existing configuration from file path"""
        try:
            with path.open('r') as fd:
                config = json.load(fd)
        except json.JSONDecodeError:
            LOG.exception('Error loading config from JSON. Retaining existing '
                          'configuration.')
        else:
            self.data = config
            self.path = path

    @staticmethod
    def from_file(config_name='atgmlogger.json'):
        """Search for configuration from default filesystem locations"""
        _default_paths = [
            Path('~/'),
            Path('/etc/atgmlogger'),
            Path('/opt/atgmlogger')
        ]
        for loc in _default_paths:
            cfg_path = loc.joinpath(config_name)
            if cfg_path.exists():
                return RunConfig(cfg_path)
        return RunConfig(_default_paths[0].joinpath(config_name))


rcParams = RunConfig.from_file()
