# -*- coding: utf-8 -*-

import os
import logging
import threading

import pytest
from atgmlogger.plugins import PluginInterface, load_plugin

root_log = logging.getLogger()
if len(root_log.handlers):
    hdl0 = root_log.handlers[0]
    hdl0.setFormatter(logging.Formatter("%(msecs)d::%(levelname)s - "
                                        "%(funcName)s %(message)s"))

Q_LEN = int(os.getenv('QUEUELENGTH', '5000'))
LOG_LVL = os.getenv('LOGLVL', 'DEBUG')
root_log.setLevel(LOG_LVL)


def test_dispatch(dispatcher):
    """Test basic dispatcher functionality - discretionary pushing of
    received Queue items based on their type to registered listeners."""
    assert not dispatcher.is_alive()
    from .dispatch_modules import BasicModule, ComplexModule, SimplePacket
    dispatcher.register(BasicModule)
    dispatcher.register(ComplexModule)
    for klass in [BasicModule, ComplexModule]:
        assert klass in dispatcher.registered_listeners()

    dispatcher.start()
    for i in range(Q_LEN):
        dispatcher.put(SimplePacket(i))
    dispatcher.exit(join=True)

    bm = dispatcher.get_instance(BasicModule)
    cm = dispatcher.get_instance(ComplexModule)
    assert isinstance(bm, BasicModule)
    assert isinstance(cm, ComplexModule)

    assert Q_LEN == len(bm.accumulator)
    assert list(range(Q_LEN)) == bm.accumulator
    assert Q_LEN == len(cm.accumulator)
    assert [i*10 for i in range(Q_LEN)] == cm.accumulator


def test_dispatch_selective_load(dispatcher):
    assert not dispatcher.is_alive()
    from .dispatch_modules import BasicModule, ComplexModule, SimplePacket
    dispatcher.register(BasicModule)
    dispatcher.register(ComplexModule)
    dispatcher.detach(ComplexModule)
    dispatcher.start()
    for i in range(Q_LEN):
        dispatcher.put(SimplePacket(i))
    dispatcher.exit(join=True)

    bm = dispatcher.get_instance(BasicModule)
    cm = dispatcher.get_instance(ComplexModule)
    assert isinstance(bm, BasicModule)
    assert list(range(Q_LEN)) == bm.accumulator

    assert cm is None


def test_load_plugin(dispatcher):
    from . import plugins  # this is needed for some reason due to relative
    # import
    plugin = load_plugin('basic_plugin', path="%s.plugins" % __package__,
                         register=True)
    assert plugin in dispatcher.registered_listeners()
    plugin_opts = dict(smtp="smtp.google.com", username="testUser",
                       password="ask123a9")
    inst = plugin()
    inst.configure(**plugin_opts)
    assert "smtp.google.com" == inst.smtp

    assert issubclass(plugin, threading.Thread)
    assert issubclass(plugin, PluginInterface)
    t_item = "TestStr"
    inst.put(t_item)
    assert t_item == inst.queue.get()


def test_load_subclassed_plugin(dispatcher):
    from . import plugins
    plugin = load_plugin('subclassed_plugin', path="%s.plugins" % __package__,
                         register=False)
    assert plugin not in dispatcher.registered_listeners()
    inst = plugin()
    opts = dict(friendly_name="Subclassed Plugin", sleeptime=12, nullopt=None)
    assert not hasattr(inst, 'friendly_name')
    assert not hasattr(inst, 'sleeptime')

    inst.configure(**opts)
    assert "Subclassed Plugin" == inst.friendly_name
    assert 12 == inst.sleeptime
    assert not hasattr(inst, 'nullopt')


def test_bad_plugin_path():
    with pytest.raises(ImportError):
        load_plugin('basic_plugin', path='atgmlogger')

