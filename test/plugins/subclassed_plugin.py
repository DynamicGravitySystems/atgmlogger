# -*- coding: utf-8 -*-

from atgmlogger.plugins import PluginInterface


class SubclassPlugin(PluginInterface):
    options = ['friendly_name', 'sleeptime']

    def __init__(self):
        super().__init__()

    def run(self):
        print("Running %s" % __class__.__name__)

    def configure(self, **options):
        super().configure(**options)


__plugin__ = SubclassPlugin
