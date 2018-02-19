# -*- coding: utf-8 -*-

import logging
import threading
import pytest
from atgmlogger.dispatcher import Dispatcher, load_plugin, ModuleInterface

root_log = logging.getLogger()
if len(root_log.handlers):
    hdl0 = root_log.handlers[0]
    hdl0.setFormatter(logging.Formatter("%(msecs)d - %(message)s"))


@pytest.fixture
def dispatcher():
    disp = Dispatcher()
    yield disp
    disp.exit()


def test_dispatch():
    from .dispatch_modules import BasicModule, ComplexModule, SimplePacket
    dispatcher = Dispatcher()
    for klass in [BasicModule, ComplexModule]:
        assert klass in dispatcher.registered_modules()

    dispatcher.start()
    rng = 5000
    for i in range(rng):
        dispatcher.put(SimplePacket(i))
    dispatcher.exit()

    bm = dispatcher.get_instance(BasicModule)
    cm = dispatcher.get_instance(ComplexModule)

    assert list(range(rng)) == bm.accumulator
    assert [i*10 for i in range(rng)] == cm.accumulator


def test_dispatch_selective_load(dispatcher):
    from .dispatch_modules import BasicModule, ComplexModule, SimplePacket
    assert not dispatcher.is_alive()
    dispatcher.detach(ComplexModule)
    dispatcher.start()
    rng = 5000
    for i in range(rng):
        dispatcher.put(SimplePacket(i))
    dispatcher.exit()

    bm = dispatcher.get_instance(BasicModule)
    cm = dispatcher.get_instance(ComplexModule)
    assert isinstance(bm, BasicModule)
    assert list(range(rng)) == bm.accumulator

    assert cm is None


def test_load_plugin(dispatcher):
    plugin = load_plugin('basic_plugin', path=__package__)
    plugin_opts = dict(smtp="smtp.google.com", username="testUser",
                       password="ask123a9")
    inst = plugin()
    inst.configure(**plugin_opts)

    assert issubclass(plugin, threading.Thread)
    assert issubclass(plugin, ModuleInterface)
    t_item = "TestStr"
    inst.put(t_item)
    assert t_item == inst.queue.get()

    dispatcher.register(plugin)
    assert plugin in dispatcher.registered_modules()

