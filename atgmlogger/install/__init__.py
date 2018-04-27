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

LOG = logging.getLogger(__name__)
# LOG.propagate = True
LOG.setLevel(logging.WARNING)
if POSIX:
    _install_log_path = 'install.log'
else:
    _install_log_path = 'install.log'

LOG.addHandler(logging.FileHandler(_install_log_path,
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
        LOG.exception("Exception writing template to file: %s", str(path))


def sys_command(cmd, verbose=True):
    try:
        if verbose:
            LOG.info("Executing system command: '%s'", cmd)
        return subprocess.check_output(shlex.split(cmd))
    except (OSError, subprocess.SubprocessError, subprocess.CalledProcessError):
        if verbose:
            LOG.exception("Exception encountered executing command: '%s'", cmd)
        else:
            LOG.warning("Exception encountered executing command: '%s'", cmd)
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
        LOG.info("Installing logrotate configuration in %s", str(dest_path))
        fd = os.open(str(dest_path), os.O_WRONLY | os.O_CREAT, mode=0o640)
        hdl = os.fdopen(fd, mode='w')
        hdl.write(dedent(config))
    except IOError:
        LOG.exception("Exception creating atgmlogger logrotate config.")


def configure_rpi():
    """Check/set parameters in /boot/config.txt and /boot/cmdline.txt to
    configure Raspberry Pi for GPIO serial IO.
    Specifically this requires adding `enable_uart=1` to the end of config.txt
    and removing a clause from the cmdline.txt file to disable TTY over the GPIO
    serial interface."""

    sys_command("sed -i -r 's/console=serial0,115200 //' /boot/cmdline.txt")

    try:
        with open('/boot/config.txt', 'r') as fd:
            if 'enable_uart=1' in fd.read():
                LOG.info("enable_uart is already set in config.txt, no action taken.")
                return
        with open('/boot/config.txt', 'a') as fd:
            fd.write("enable_uart=1\n")
            LOG.critical("enable_uart set, system reboot required for configuration to take effect.")
    except (IOError, OSError):
        LOG.exception("Error reading/writing from /boot/config.txt")


def install(verbose=True):
    if verbose:
        LOG.setLevel(logging.DEBUG)
    if not POSIX:
        LOG.warning("Invalid system platform for installation.")
        return 1

    df_mode = 0o640
    for src, dest in _file_map.items():
        LOG.info("Installing source file: %s to %s", src, dest)
        parent = os.path.split(dest)[0]
        if not os.path.exists(parent):
            try:
                os.mkdir(parent, df_mode)
            except OSError:
                LOG.exception("Error creating directory: %s" % parent)
                continue
        try:
            src_bytes = pkg_resources.resource_string(__name__, src)
            write_bytes(dest, src_bytes, df_mode)
        except (FileNotFoundError, OSError):
            LOG.exception("Error writing resource to dest file.")
    _install_logrotate_config()

    # Try to install dependencies for USB removable storage formats
    sys_command('apt-get update')
    sys_command('apt-get install -y ntfs-3g exfat-fuse exfat-utils')

    sys_command('systemctl daemon-reload')
    sys_command('systemctl enable media-removable.mount')
    sys_command('systemctl enable atgmlogger.service')
    configure_rpi()
    LOG.critical("Installation of atgmlogger completed successfully.")
    return 0


def uninstall(verbose=True):
    if verbose:
        LOG.setLevel(logging.DEBUG)
    LOG.info("Stopping and disabling services.")
    sys_command('systemctl stop atgmlogger.service')
    sys_command('systemctl disable media-removable.mount')
    sys_command('systemctl disable atgmlogger.service')

    for src, dest in _file_map.items():
        try:
            LOG.info("Removing file: %s", dest)
            os.remove(dest)
        except (IOError, OSError):
            if verbose:
                LOG.exception("Unable to remove installed file: %s", dest)
            else:
                LOG.warning("Unable to remove installed file: %s", dest)
    LOG.info("Successfully completed uninstall.")
    return 0
