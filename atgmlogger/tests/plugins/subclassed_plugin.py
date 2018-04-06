# -*- coding: utf-8 -*-

from atgmlogger.plugins import PluginInterface

__plugin__ = 'SubclassPlugin'


class SubclassPlugin(PluginInterface):
    options = ['friendly_name', 'sleeptime']

    def __init__(self):
        super().__init__()

    @staticmethod
    def consumer_type():
        return {str}

    def run(self):
        print("Running %s" % __class__.__name__)

    def configure(self, **options):
        super().configure(**options)
