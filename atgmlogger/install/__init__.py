# -*- coding: utf-8 -*-

import os
import sys
import shlex
import logging
import subprocess
from textwrap import dedent
from pathlib import Path

import pkg_resources as pkg

__all__ = ['install', 'uninstall']

BASEPKG = __name__.split('.')[0]
PREFIX = ''

_log = logging.getLogger(__name__)
_log.propagate = False
_log.setLevel(logging.WARNING)
if sys.platform.startswith('linux'):
    _install_log_path = 'install.log'
else:
    _install_log_path = 'install.log'

_log.addHandler(logging.FileHandler(_install_log_path,
                                    encoding='utf-8'))


_file_map = {
    '.atgmlogger': '%s/etc/%s/.atgmlogger' % (PREFIX, BASEPKG),
    'media-removable.mount':
        '%s/lib/systemd/system/media-removable.mount' % PREFIX,
    '90-removable-storage.rules':
        '%s/etc/udev/rules.d/90-removable-storage.rules' % PREFIX,
    'atgmlogger.service': '%s/lib/systemd/system/atgmlogger.service' % PREFIX
}


def write_bytes(path, bytearr, mode=0o644):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT, mode)
    os.write(fd, bytearr)
    os.close(fd)


def sys_command(cmd):
    try:
        return subprocess.check_output(shlex.split(cmd))
    except (OSError, subprocess.SubprocessError):
        return -1


def _install_logrotate_config(log_path=None):
    # Create atgmlogger logrotate file in /etc/logrotate.d/atgmlogger
    # If atgmlogger config is dropped above, no further action needed as
    # there should already be a daily logrotate cron entry
    dest_path = Path('%s/etc/logrotate.d/%s' % (PREFIX, BASEPKG))
    log_path = Path(log_path) or Path('/var/log/%s' % BASEPKG)
    config = """
    {logpath}/*.log {{
        missingok
        daily
        dateext
        dateyesterday
        dateformat %Y-%m-%d
        rotate 30
        compress
    }}
    {logpath}/*.dat {{
        missingok
        daily
        dateext
        dateyesterday
        dateformat %Y-%m-%d
        rotate 30
        compress
    }}
    """.format(logpath=str(log_path.resolve()))
    try:
        fd = os.open(str(dest_path), os.O_WRONLY | os.O_CREAT, mode=0o640)
        hdl = os.fdopen(fd, mode='w')
        hdl.write(dedent(config))
    except IOError:
        _log.exception("Exception creating atgmlogger logrotate config.")


def install(verbose=True):
    if verbose:
        _log.setLevel(logging.DEBUG)
    _log.info("Running first-install script.")
    _log.info("Package base name is %s", BASEPKG)
    if not sys.platform.startswith('linux'):
        _log.warning("Invalid system platform for installation.")
        return

    df_mode = 0o640
    for src, dest in _file_map.items():
        _log.info("Installing source file: %s to %s", src, dest)
        parent = os.path.split(dest)[0]
        if not os.path.exists(parent):
            try:

                os.mkdir(parent, df_mode)
            except OSError:
                _log.exception("Error creating directory: %s" % parent)
                continue
        try:
            src_bytes = pkg.resource_string(__name__, src)
            write_bytes(dest, src_bytes, df_mode)
        except (FileNotFoundError, OSError):
            _log.exception("Error writing resource to dest file.")

    sys_command('systemctl daemon-reload')
    sys_command('systemctl enable media-removable.mount')
    sys_command('systemctl enable atgmlogger.service')


def uninstall(verbose=True):
    if verbose:
        _log.setLevel(logging.DEBUG)

    sys_command('systemctl disable media-removable.mount && '
                'systemctl disable atgmlogger.service')

    for src, dest in _file_map.items():
        try:
            os.remove(dest)
        except (IOError, OSError):
            _log.exception("Unable to remove installed file: %s", dest)

