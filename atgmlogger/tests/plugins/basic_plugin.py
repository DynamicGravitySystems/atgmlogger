# -*- coding: utf-8 -*-

__plugin__ = 'TestPlugin'


class TestPlugin:
    # Important Note, if plugins utilize a __init__ they must make a call to
    # super().__init__()
    def __init__(self):
        super().__init__()
        self._smtp = None

    @staticmethod
    def consumer_type():
        return {str}

    def consumes(self, item):
        return isinstance(item, str)

    def run(self):
        pass

    def configure(self, **options):
        if 'smtp' in options:
            self._smtp = options['smtp']

    @property
    def smtp(self):
        return self._smtp
