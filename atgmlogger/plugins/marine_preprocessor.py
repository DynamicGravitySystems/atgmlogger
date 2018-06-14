# -*- coding: utf-8 -*-

import configparser
import logging
from collections import OrderedDict
from datetime import datetime

from . import PluginInterface
from atgmlogger.runconfig import rcParams

LOG = logging.getLogger(__name__)


def map_fields(raw: str, field_map):
    """Map raw field values to column name and perform type cast on value"""
    fields = raw.split(',')
    return {key: field_map[key](fields[i]) for i, key in enumerate(field_map.keys())}


def parse_time(ymdtime):
    fmt = "%Y%m%d%H%M%S"
    try:
        return datetime.strptime(ymdtime, fmt)
    except ValueError:
        return int(ymdtime)


correction = 8388607


class MarinePreprocessor(PluginInterface):
    options = ['meterini', 'fields']

    def __init__(self):
        super().__init__()
        self.meterini = None
        self.config = None
        self.fields = {'GravCal', 'g0', 'LongCal', 'LongOffset', 'CrossCal', 'CrossOffset'}

    @staticmethod
    def consumer_type() -> set:
        return {str}

    def run(self):
        if self.meterini is not None:
            self.config = configparser.ConfigParser(strict=False)
            try:
                self.config.read(self.meterini)
            except (IOError, FileNotFoundError) as e:
                LOG.exception("Exception loading meter.ini file")
                self.config = None
                raise e
        else:
            raise FileNotFoundError("Invalid or no Meter INI configuration available.")

        cfg_values = {field: self.config['Sensor'].getfloat(field) for field in self.fields}
        field_map = OrderedDict({
            "header": str, "gravity": float, "long": float, "cross": float, "beam": float, "temp": float,
            "pressure": float, "etemp": float, "vcc": float, "ve": float, "al": float, "ax": float, "status": int,
            "chksum": int, "latitude": float, "longitude": float, "speed": float, "course": float, "time": parse_time
        })

        while not self.exiting:
            item = self.get()
            if item is None or item == "":
                self.task_done()
                continue

            corrected = dict()
            data = map_fields(item, field_map)
            corrected['gravity'] = data['gravity'] * cfg_values['GravCal'] / correction + cfg_values['g0']
            corrected['long'] = data['long'], * cfg_values['LongCal'] / correction + cfg_values['LongOffset']
            corrected['cross'] = data['cross'] * cfg_values['CrossCal'] / correction + cfg_values['CrossOffset']



