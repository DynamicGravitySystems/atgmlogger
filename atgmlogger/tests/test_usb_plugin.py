# -*- coding: utf-8 -*-

import pytest
from pathlib import Path

from atgmlogger.plugins import load_plugin, PluginDaemon


@pytest.fixture
def usb_plugin():
    klass = load_plugin('usb', path='atgmlogger.plugins', register=False)
    return klass


def test_usb_configure(usb_plugin, mountpoint):
    params = dict(mountpath=mountpoint,
                  logdir=Path('tests/logs'),
                  patterns=['*.dat', '*.data', '*.grav', '*.log'])
    usb_plugin.configure(**params)

    assert issubclass(usb_plugin, PluginDaemon)

    for key, value in params.items():
        assert hasattr(usb_plugin, key)
        if key == 'mountpath' or key == 'logdir':
            value = Path(value)
        assert value == getattr(usb_plugin, key)


def test_usb_watchfiles(usb_plugin, mountpoint: Path):
    # import atgmlogger.plugins.usb as _usb
    # _usb.CHECK_PLATFORM = False

    params = dict(mountpath=mountpoint,
                  logdir='tests/logs',
                  patterns=['*.dat', '*.data', '*.grav', '*.log'])
    usb_plugin.configure(**params)

    triggers = ['diag.txt', 'diagnostics.txt', 'clear.txt', 'get_config.txt']
    for trigger in triggers:
        with mountpoint.joinpath(trigger).open('w') as fd:
            fd.write('null')

    inst = usb_plugin()
    matches = inst.watch_files(run=False)  # Change run to True for testing
    # results
    assert sorted(['clear.txt', 'diag.txt', 'get_config.txt']) == sorted(
        matches)
    # with open(mountpoint.joinpath('diag.txt'), 'r') as fd:
    #     print("Test Diag Result:")
    #     print(fd.read())
