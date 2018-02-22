# -*- coding: utf-8 -*-

__plugin__ = 'TestPlugin'


class TestPlugin:
    consumerType = str

    # Important Note, if plugins utilize a __init__ they must make a call to
    # super().__init__()
    def __init__(self):
        super().__init__()
        self._smtp = None

    def run(self):
        pass

    def configure(self, **options):
        if 'smtp' in options:
            self._smtp = options['smtp']

    @property
    def smtp(self):
        return self._smtp
