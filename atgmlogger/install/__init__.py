# -*- coding: utf-8 -*-

import os
import sys
import logging
import subprocess
import pkg_resources as pkg

__all__ = ['install', 'uninstall']

BASEPKG = __name__.split('.')[0]
_log = logging.getLogger(__name__)
_log.setLevel(logging.WARNING)
_file_map = {
    '.atgmlogger': '/etc/%s/.atgmlogger' % BASEPKG,
    'media-removable.mount': '/lib/systemd/system/media-removable.mount',
    '90-removable-storage.rules':
        '/etc/udev/rules.d/90-removable-storage.rules',
    'atgmlogger.service': '/lib/systemd/system/atgmlogger.service'
}


def write_bytes(path, bytearr, mode=0o644):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT, mode)
    os.write(fd, bytearr)
    os.close(fd)


def install(verbose=True):
    if verbose:
        _log.setLevel(logging.DEBUG)
    _log.info("Running first-install script.")
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
                print("Error creating directory: %s" % parent)
                continue
        try:
            src_bytes = pkg.resource_string(__name__, src)
            write_bytes(dest, src_bytes, df_mode)
        except (FileNotFoundError, OSError):
            print("Error getting resource and/or writing to dest file.")
            print(sys.exc_info())

    try:
        subprocess.check_output(['systemctl', 'daemon-reload'])
        subprocess.check_output(['systemctl', 'enable',
                                 'media-removable.mount'])
        subprocess.check_output(['systemctl', 'enable', 'atgmlogger.service'])

    except OSError:
        pass


def uninstall(verbose=True):
    if verbose:
        _log.setLevel(logging.DEBUG)
    raise NotImplementedError("Uninstall function not yet implemented.")
