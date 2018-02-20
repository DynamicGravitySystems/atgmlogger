# -*- coding: utf-8 -*-

import os
import re
import sys
import time
import uuid
import shutil
import functools
import threading
import subprocess
from pathlib import Path
from typing import List

from atgmlogger import APPLOG
from . import PluginInterface


def get_dest_dir(scheme='date', prefix=None, datefmt='%y%m%d-%H%M'):
    """
    Generate a unique directory name to copy files to.

    Parameters
    ----------
    scheme : str, Optional
        Scheme to use for generating directory names.
        uuid or date, or None
        uuid scheme generates a unique name based on the uuid4 specification
        Otherwise, a name is generated based on the current UTC time.
        Note: The time may not be accurate if the logging system has
        not been synchronized to GPS time
    prefix : str, Optional
        Optional prefix to pre-pend to the directory name
        Prefix will be trimmed to length of 5
    datefmt : str, Optional
        Optional override default strftime date/time format

    Returns
    -------
    String: Directory Name
        Directory name as a string which must be appended to the output
        path.
    """

    if scheme.lower() == 'uuid':
        dir_name = str(uuid.uuid4())
    else:
        dir_name = time.strftime(datefmt+'UTC', time.gmtime(time.time()))
    if prefix:
        dir_name = prefix[:5]+dir_name

    illegals = '\\:<>?*/\"'  # Illegal characters
    dir_name = "".join([c for c in dir_name if c not in illegals])
    return dir_name


def umount(path):
    if sys.platform == 'win32':
        APPLOG.warning("umount not supported on Windows Platform")
        return -1
    try:
        result = subprocess.check_output(['/bin/umount', str(path)])
    except OSError:
        result = 1
        APPLOG.exception("Error occurred attempting to un-mount device: {}"
                         .format(path))
    return result


def _runhook(priority=5):
    def inner(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            return func(self, *args, **kwargs)
        wrapper.runhook = priority
        return wrapper
    return inner


def _filehook(pattern):
    def inner(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            return func(self, *args, **kwargs)
        wrapper.filehook = pattern
        return wrapper
    return inner


class RemovableStorageHandler(PluginInterface):
    options = ['mountpath', 'logdir', 'patterns']
    consumerType = str
    oneshot = True

    @classmethod
    def condition(cls):
        return False

    def __init__(self):
        super().__init__()

        self.mountpath = Path('/media/removable')
        self.log_dir = None
        self.patterns = ['*.dat', '*.log']

        self._current_path = None
        self._last_copy_time = None
        self._umount_flag = threading.Event()

        self._run_hooks = list()
        self._file_hooks = dict()
        for member in self.__class__.__dict__.values():
            # Inspect for decorated methods
            if hasattr(member, 'runhook'):
                self._run_hooks.append(self.__getattribute__(member.__name__))
            elif hasattr(member, 'filehook'):
                self._file_hooks[member.filehook] = self.__getattribute__(
                    member.__name__)

    def run(self):
        if not self.configured:
            raise ValueError("RemovableStorageHandler has not been configured.")
        if not os.path.ismount(self.mountpath):
            APPLOG.error("{path} is not mounted or is not a valid mount point."
                         .format(path=self.mountpath))
            return 1

        for functor in sorted(self._run_hooks, key=lambda x: x.runhook):
            th = threading.Thread(target=functor)
            th.start()
            th.join()

        try:
            os.sync()
        except AttributeError:
            # os.sync is not available on Windows
            pass
        finally:
            umount(self.mountpath)

    def configure(self, **options):
        super().configure(**options)
        if 'mountpath' in options:
            self.mountpath = Path(self.mountpath)
        if 'logdir' in options:
            self.log_dir = Path(getattr(self, 'logdir'))
            if not self.log_dir.is_dir():
                self.log_dir = self.log_dir.parent

    @_runhook(priority=1)
    def copy_logs(self):
        APPLOG.debug("Processing copy_logs")
        file_list = []  # type: List[Path]
        copy_size = 0   # Accumulated size of logs in bytes

        for pattern in self.patterns:
            file_list.extend(self.log_dir.glob(pattern))

        for file in file_list:
            copy_size += file.stat().st_size

        APPLOG.info("Total log size to be copied: {} KiB".format(
            copy_size/1024))

        def get_free(path):
            try:
                statvfs = os.statvfs(str(path.resolve()))
            except AttributeError:
                return -1
            return statvfs.f_bsize * statvfs.f_bavail

        if copy_size > get_free(self.mountpath):
            APPLOG.warning("Total size of datafiles to be copied is greater "
                         "than free-space on device.")

        dest_dir = self.mountpath.resolve().joinpath(get_dest_dir(prefix='DATA-'))
        dest_dir.mkdir()

        for srcfile in file_list:
            fname = srcfile.name
            src_path = str(srcfile.resolve())
            dest_path = str(dest_dir.joinpath(fname))

            try:
                shutil.copy(src_path, dest_path)
                APPLOG.info("Copied file %s to %s", fname, dest_path)
            except OSError:
                APPLOG.exception("Exception encountered copying log file.")
                continue

        self._current_path = dest_dir
        self._last_copy_time = time.time()

    @_runhook(priority=2)
    def watch_files(self):
        APPLOG.debug("Processing watch_files")
        root_files = [file.name for file in self.mountpath.iterdir() if
                      file.is_file()]
        files = " ".join(root_files)
        for pattern in self._file_hooks.keys():
            match = re.search(pattern, files)
            if match:
                self._file_hooks[pattern](self, match.group())

    @_filehook('^clear(\.txt)?')
    def clear_logs(self, pattern):
        print("self is: ", self)
        print("pattern is: ", pattern)


__plugin__ = RemovableStorageHandler
