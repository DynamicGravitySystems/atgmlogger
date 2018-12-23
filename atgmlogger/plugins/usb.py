# -*- coding: utf-8 -*-

# This file is part of ATGMLogger https://github.com/bradyzp/atgmlogger
import json
import os
import re
import sys
import time
import uuid
import shlex
import shutil
import logging
import functools
import subprocess
from pathlib import Path
from typing import List

from . import PluginDaemon
from .. import runconfig

__plugin__ = 'RemovableStorageHandler'
CHECK_PLATFORM = True
LOG = logging.getLogger(__name__)


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
        Prefix will be trimmed to length of 8
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
        dir_name = prefix[:8]+dir_name

    illegals = frozenset('\\:<>?*/\"')  # Known illegal characters
    dir_name = "".join([c for c in dir_name if c not in illegals])
    return dir_name


def umount(path):
    if CHECK_PLATFORM and not sys.platform.startswith('linux'):
        LOG.warning("umount not supported on Windows Platform")
        return -1
    try:
        result = subprocess.check_output(['/bin/umount', str(path)])
    except OSError:
        result = 1
        LOG.exception("Error occurred attempting to un-mount device: {}"
                      .format(path))
    else:
        LOG.info("Successfully unmounted %s", str(path))
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
        wrapper.filehook = re.compile(pattern, re.IGNORECASE)
        return wrapper
    return inner


class RemovableStorageHandler(PluginDaemon):
    options = {'mountpath': Path, 'logdir': Path, 'patterns': list}

    mountpath = Path('/media/removable')
    logdir = Path('/var/log/atgmlogger')
    patterns = ['*.dat', '*.dat.*', '*.log', '*.gz']

    @classmethod
    def condition(cls, *args):
        return os.path.ismount(str(cls.mountpath))

    def __init__(self, **kwargs):
        LOG.debug("Initializing RemovableStorageHandler")
        super().__init__(**kwargs)

        self._current_path = None
        self._last_copy_time = None

        self._run_hooks = list()
        self._file_hooks = list()
        for member in self.__class__.__dict__.values():
            # Inspect for decorated methods
            if hasattr(member, 'runhook'):
                self._run_hooks.append(self.__getattribute__(member.__name__))
                LOG.debug("Appending {} to runhooks".format(member))
            elif hasattr(member, 'filehook'):
                self._file_hooks.append((member.filehook,
                                        self.__getattribute__(member.__name__)))
                LOG.debug("Appending {} to filehooks".format(member))

    # TODO: Figure out best way to allow only one instance of a plugin to run
    def run(self):
        LOG.debug("Starting USB Handler thread")
        if not os.path.ismount(str(self.mountpath)):
            LOG.error("{path} is not mounted or is not a valid mount point."
                      .format(path=str(self.mountpath)))
            return

        if not self.logdir.is_dir():
            self.logdir = self.logdir.parent

        self.context.blink_until(led='usb')

        for functor in sorted(self._run_hooks, key=lambda x: x.runhook):
            result = functor()
            LOG.debug("USB Function {} returned: {}"
                      .format(functor, result))

        try:
            os.sync()
        except AttributeError:
            # os.sync is not available on all platforms (Windows)
            pass
        finally:
            umount(self.mountpath)
        self.context.blink_until(led='usb')

        LOG.debug("Returning from USB Handler")

    @_runhook(priority=1)
    def copy_logs(self):
        LOG.debug("Processing copy_logs")
        file_list = []  # type: List[Path]
        copy_size = 0   # Accumulated size of logs in bytes

        for pattern in self.patterns:
            file_list.extend(self.logdir.glob(pattern))

        for file in file_list:
            copy_size += file.stat().st_size

        LOG.info("Total log size to be copied: {} KiB".format(
            copy_size/1024))

        def get_free(path):
            try:
                statvfs = os.statvfs(str(path.resolve()))
            except AttributeError:
                return -1
            return statvfs.f_bsize * statvfs.f_bavail

        if copy_size > get_free(self.mountpath):
            LOG.warning("Total size of datafiles to be copied is greater "
                        "than free-space on device.")

        pfx = runconfig.rcParams['sensor.name'] or 'DATA'
        dest_dir = self.mountpath.resolve().joinpath(get_dest_dir(prefix=pfx))
        try:
            dest_dir.mkdir()
        except FileExistsError:
            LOG.warning("Copy Destination Directory already exists.")

        for srcfile in file_list:
            fname = srcfile.name
            src_path = str(srcfile.resolve())
            dest_path = str(dest_dir.joinpath(fname))

            try:
                shutil.copy(src_path, dest_path)
                LOG.info("Copied file %s to %s", fname, dest_path)
            except OSError:
                LOG.exception("Exception encountered copying log file.")
                continue

        self._current_path = dest_dir
        self._last_copy_time = time.time()

    @_runhook(priority=2)
    def watch_files(self, run=True):
        LOG.debug("Processing watch_files")
        root_files = [file.name for file in self.mountpath.iterdir() if
                      file.is_file()]
        files = " ".join(root_files)
        LOG.debug("Mount path root files: %s", files)
        matched = []
        for pattern, runner in self._file_hooks:
            LOG.debug("Looking for pattern: %s", pattern.pattern)
            match = pattern.search(files)
            if match:
                matched.append(match.group())
                LOG.debug("Matched on pattern: %s", pattern.pattern)
                if run:
                    path = self.mountpath.joinpath(match.group())
                    try:
                        runner(path)
                    except (AttributeError, TypeError):
                        LOG.exception("Exception executing watched file "
                                      "hook.")
            else:
                LOG.debug("No match on pattern: %s", pattern.pattern)
        return matched

    @_filehook(r'clear(\.txt)?')
    def clear_logs(self, match):
        LOG.info("Clearing old application logs and gravity data files.")
        for file in self.logdir.iterdir():  # type: Path
            if file.is_file() and file.suffix in ['.gz']:
                LOG.warning("Deleting archived file: %s", file.name)
                try:
                    os.remove(str(file.resolve()))
                except OSError:
                    LOG.exception("Error removing archived file.")

        try:
            # Remove the trigger file to prevent unintentional deletion next
            # time usb drive is used.
            os.remove(str(match.resolve()))
        except OSError:
            pass

    @_filehook(r'diag(nostic)?(\.txt)?')
    def run_diag(self, match):
        LOG.debug("Running system diagnostics and exporting result to: %s",
                  match)
        if CHECK_PLATFORM and not sys.platform.startswith('linux'):
            LOG.debug("Current platform does not support diagnostics "
                      "runner.")
            return

        dt = time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(
            time.time()))
        result = 'Diagnostic Results ({dt}):\n\n'.format(dt=dt)
        from .. import __version__
        result += 'ATGMLogger Version: ' + __version__

        commands = ['uptime', 'vcgencmd measure_temp', 'top -b -n1', 'df -H',
                    'free -h', 'dmesg']

        for cmd in commands:
            result += 'Command: %s\n' % cmd
            try:
                res = subprocess.check_output(shlex.split(cmd)).decode('utf-8')
            except (subprocess.SubprocessError, FileNotFoundError):
                LOG.exception("Exception executing diagnostic command: "
                              "%s", cmd)
                res = "Command Failed, see LOG for exception details."
            result += res + '\n\n'

        with match.open('w+') as fd:
            fd.write(result)

    @_filehook(r'get(_)?conf(ig)?(\.txt)?')
    def copy_config(self, match):
        try:
            from ..runconfig import rcParams
            with rcParams.path.open('r') as cfg:
                cfg_data = cfg.read()

            with match.open('w+') as fd:
                fd.write(cfg_data)
            LOG.info("Writing configuration to {}".format(str(match)))
        except (IOError, OSError):
            LOG.exception("Exception writing configuration.")

    @_filehook(r'\bconf(ig)?\.(json|txt|cfg)')
    def set_config(self, match):
        # Note, runtime configuration will not be applied until restart
        from ..runconfig import rcParams
        base_path = rcParams.path
        with match.open('r') as cfg:
            LOG.warning("Loading new configuration from USB device path: "
                        "%s", match)
            rcParams.load_config(cfg)

        rcParams.dump(path=base_path, exist_ok=True)
        LOG.info("New configuration file loaded from USB device. Changes "
                 "will not take effect until restart.")

    @_filehook(r'logrotate\.?(conf)?')
    def set_logrotate(self, match: Path):
        """Update atgmlogger logrotate conf file."""
        # TODO: Make this work
        with match.open('r') as fd:
            try:
                rotate_conf = json.loads(fd.read())
            except Exception as e:
                LOG.exception("Failed to read logrotate update.")
                return

        try:
            from .. install import _install_logrotate_config
        except ImportError:
            LOG.exception("Failed to import logrotate config ")
            return


