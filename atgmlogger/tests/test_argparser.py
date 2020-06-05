# -*- coding: utf-8 -*-

import shlex
from argparse import Namespace

import pytest

from atgmlogger.__main__ import parse_args


@pytest.fixture
def namespace():
    """Return a namespace with global defaults set"""
    return Namespace(debug=False, trace=False, verbose=0)


def test_run_command_parse():
    """Test insertion of default command when non specified (run)"""
    test_args = "run --device com1 --logdir /etc/atgmlogger"
    result = parse_args(argv=shlex.split(test_args))

    assert result.command == "run"
    assert result.mountdir is None
