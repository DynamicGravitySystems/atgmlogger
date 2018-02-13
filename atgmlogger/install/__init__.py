# -*- coding: utf-8 -*-

import os
import sys
import subprocess
import pkg_resources as pkg

__all__ = ['run']

VERBOSE = True
BASEPKG = __name__.split('.')[0]

_file_map = {
    '.atgmlogger': '/etc/%s/.atgmlogger' % BASEPKG,
    'logging.json': '/etc/%s/logging.json' % BASEPKG,
    'media-removable.mount': '/lib/systemd/system/media-removable.mount',
    '90-removable-storage.rules':
        '/etc/udev/rules.d/90-removable-storage.rules',
    'atgmlogger.service': '/lib/systemd/system/atgmlogger.service'
}


def write_bytes(path, bytearr, mode=0o644):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT, mode)
    os.write(fd, bytearr)
    os.close(fd)


def run():
    print("Running first-install script.")
    if not sys.platform.startswith('linux'):
        print("Invalid system platform for installation.")
        return

    df_mode = 0o640
    for src, dest in _file_map.items():
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
