# -*- coding: utf-8 -*-
# This file is part of ATGMLogger https://github.com/bradyzp/atgmlogger

import os
import shlex
import logging
import subprocess
import pkg_resources
from textwrap import dedent
from pathlib import Path

from .. import POSIX

__all__ = ['install', 'uninstall']

BASEPKG = __name__.split('.')[0]
PREFIX = ''

_log = logging.getLogger(__name__)
_log.propagate = True
_log.setLevel(logging.WARNING)
if POSIX:
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


def write_bytes(path: str, bytearr, mode=0o644):
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT, mode)
        os.write(fd, bytearr)
        os.close(fd)
    except OSError:
        _log.exception("Exception writing template to file: %s", str(path))


def sys_command(cmd, verbose=True):
    try:
        if verbose:
            _log.info("Executing system command: '%s'", cmd)
        return subprocess.check_output(shlex.split(cmd))
    except (OSError, subprocess.SubprocessError, subprocess.CalledProcessError):
        if verbose:
            _log.exception("Exception encountered executing command: '%s'", cmd)
        else:
            _log.warning("Exception encountered executing command: '%s'", cmd)
        return -1


def _install_logrotate_config(log_path=None):
    # Create atgmlogger logrotate file in /etc/logrotate.d/atgmlogger
    # If atgmlogger config is dropped above, no further action needed as
    # there should already be a daily logrotate cron entry
    dest_path = Path('%s/etc/logrotate.d/%s' % (PREFIX, BASEPKG))
    if log_path is not None:
        log_path = Path(log_path)
    else:
        log_path = Path('/var/log/%s' % BASEPKG)
        if not log_path.exists():
            log_path.mkdir()

    postscript = """
        postrotate
            if [ -x /usr/bin/killall ]; then
            killall -HUP atgmlogger
            fi
        endscript
    """
    config = """
    {logpath}/*.log {{
        missingok
        daily
        dateext
        dateyesterday
        dateformat .%Y-%m-%d
        rotate 30
        compress
    }}
    {logpath}/*.dat {{
        missingok
        daily
        dateext
        dateyesterday
        dateformat .%Y-%m-%d
        rotate 30
        compress
        {postrotate}
    }}
    """.format(logpath=str(log_path.resolve()), postrotate=postscript)
    try:
        _log.info("Installing logrotate configuration in %s", str(dest_path))
        fd = os.open(str(dest_path), os.O_WRONLY | os.O_CREAT, mode=0o640)
        hdl = os.fdopen(fd, mode='w')
        hdl.write(dedent(config))
    except IOError:
        _log.exception("Exception creating atgmlogger logrotate config.")


# TODO: What about checking/updating /boot/cmdline.txt and adding
# enable_uart=1 to /boot/config.txt?
# Use sed to keep it simple? yes probably.
def install(verbose=True):
    if verbose:
        _log.setLevel(logging.DEBUG)
    if not POSIX:
        _log.warning("Invalid system platform for installation.")
        return 1

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
            src_bytes = pkg_resources.resource_string(__name__, src)
            write_bytes(dest, src_bytes, df_mode)
        except (FileNotFoundError, OSError):
            _log.exception("Error writing resource to dest file.")
    _install_logrotate_config()

    # Try to install dependencies for USB removable storage formats
    sys_command('apt-get install -y ntfs-3g exfat-fuse exfat-utils')

    sys_command('systemctl daemon-reload')
    sys_command('systemctl enable media-removable.mount')
    sys_command('systemctl enable atgmlogger.service')
    _log.critical("Installation of atgmlogger completed successfully.")
    return 0


def uninstall(verbose=True):
    if verbose:
        _log.setLevel(logging.DEBUG)
    _log.info("Stopping and disabling services.")
    sys_command('systemctl stop atgmlogger.service')
    sys_command('systemctl disable media-removable.mount')
    sys_command('systemctl disable atgmlogger.service')

    for src, dest in _file_map.items():
        try:
            _log.info("Removing file: %s", dest)
            os.remove(dest)
        except (IOError, OSError):
            if verbose:
                _log.exception("Unable to remove installed file: %s", dest)
            else:
                _log.warning("Unable to remove installed file: %s", dest)
    _log.info("Successfully completed uninstall.")
    return 0
