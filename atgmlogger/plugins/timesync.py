# -*- coding: utf-8 -*-

import queue
from . import PluginInterface
from ..common import timestamp_from_data, set_system_time


class TimeSync(PluginInterface):
    options = ['interval']
    consumerType = str

    def __init__(self):
        super().__init__()
        self._tick = 0
        self.interval = 1000

    def run(self):
        while not self.exiting:
            self._tick += 1
            try:
                data = self.get(block=True, timeout=0.1)
            except queue.Empty:
                continue
            if self._tick % self.interval == 0:
                try:
                    set_system_time(timestamp_from_data(data))
                except:  # TODO: Be more specific
                    raise
            self.queue.task_done()

    def configure(self, **options):
        super().configure(**options)


__plugin__ = TimeSync
