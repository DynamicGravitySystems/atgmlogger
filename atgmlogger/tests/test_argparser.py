# -*- coding: utf-8 -*-

import shlex
from argparse import Namespace
import pytest

from atgmlogger.__main__ import parse_args


@pytest.fixture
def namespace():
    """Return a namespace with global defaults set"""
    return Namespace(debug=False, trace=False, verbose=0)


@pytest.fixture
def inst_namespace(namespace):
    """Namespace defaults for 'install' sub-command"""
    namespace.command = "install"
    namespace.service = True
    namespace.dependencies = False
    namespace.configure = False
    namespace.check_install = False
    namespace.logrotate = True
    namespace.with_mqtt = False
    return namespace


def test_install_parse_args(inst_namespace):
    test_args = "install --dependencies --configure"

    result = parse_args(argv=shlex.split(test_args))
    inst_namespace.dependencies = True
    inst_namespace.configure = True

    assert inst_namespace == result

def test_install_override_defaults(inst_namespace):
    """Test override syntax for default_true arguments"""
    test_args = "install --logrotate=false"

    inst_namespace.logrotate = False


def test_uninstall_parse_args(namespace):
    test_args = "uninstall"

    result = parse_args(shlex.split(test_args))
    namespace.command = "uninstall"
    namespace.keep_config = False

    assert namespace == result


def test_run_command_parse():
    """Test insertion of default command when non specified (run)"""
    test_args = "run --device com1 --logdir /etc/atgmlogger"
    result = parse_args(argv=shlex.split(test_args))

    assert result.command == "run"
    assert result.mountdir is None
