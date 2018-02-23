# -*- coding: utf-8 -*-

from . import PluginInterface
from .. import APPLOG
from ..common import timestamp_from_data, set_system_time

__plugin__ = 'TimeSync'


class TimeSync(PluginInterface):
    options = ['interval']
    oneshot = True
    _tick = 0
    interval = 1000

    @classmethod
    def condition(cls, line):
        cls._tick += 1
        return cls._tick % cls.interval == 0

    def __init__(self):
        super().__init__()

    def run(self):
        data = self.get(block=True, timeout=None)
        try:
            APPLOG.info("Trying to set system time.")
            ts = timestamp_from_data(data)
            if ts is not None:
                set_system_time(ts)
            else:
                APPLOG.debug("Timestamp could not be extracted from data.")
        except:  # TODO: Be more specific
            raise
        self.queue.task_done()

    @staticmethod
    def consumes(item) -> bool:
        return isinstance(item, str)

    @classmethod
    def configure(cls, **options):
        for key, value in options.items():
            lkey = str(key).lower()
            if lkey in cls.options:
                if isinstance(cls.options, dict):
                    dtype = cls.options[lkey]
                    if not isinstance(value, dtype):
                        print("Invalid option value provided for key: ", key)
                        continue
                setattr(cls, lkey, value)
