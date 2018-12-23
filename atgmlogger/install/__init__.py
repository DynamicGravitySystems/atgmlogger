# -*- coding: utf-8 -*-
# This file is part of ATGMLogger https://github.com/bradyzp/atgmlogger

import os
import shlex
import logging
import subprocess
import pkg_resources
from textwrap import dedent
from pathlib import Path

from .. import POSIX, LOG_LVLMAP

__all__ = ['install', 'uninstall']

BASEPKG = __name__.split('.')[0]
PREFIX = ''

LOG = logging.getLogger(__name__)
# LOG.propagate = True
LOG.setLevel(logging.WARNING)
LOG.addHandler(logging.FileHandler('install.log', encoding='utf-8'))

_SERVICE_NAME = "atgmlogger.service"
_MOUNT_NAME = "media-removable.mount"
_UNIT_PATH = '/etc/systemd/system/'
_UDEV_PATH = '/etc/udev/rules.d/'

_file_map = {
    'atgmlogger.json': '%s/etc/%s/atgmlogger.json' % (PREFIX, BASEPKG),
    'atgmlogger-mqtt.json': '%s/etc/%s/atgmlogger-mqtt.json' % (PREFIX, BASEPKG)
}


def _write_str(path: str, content: str, mode=0o644, encoding='utf-8', fix_indent=True):
    try:
        if fix_indent:
            content = dedent(content)
        content = content.encode(encoding)
    except UnicodeEncodeError:
        LOG.exception("Exception encoding supplied content string.")
        return
    else:
        _write_bytes(path, content, mode)


def _write_bytes(path: str, bytearr, mode=0o644):
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT, mode)
        os.write(fd, bytearr)
        os.close(fd)
    except OSError:
        LOG.exception("Exception writing template to file: %s", str(path))


def _sys_command(cmd, verbose=True):
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


def _install_plugin_user_files():
    plugin_dir = pkg_resources.resource_listdir(BASEPKG, 'plugins')
    plugin_mod = '.'.join([BASEPKG, 'plugins'])
    dest_path = '/etc/atgmlogger/plugins/'
    if not os.path.exists(dest_path):
        os.mkdir(dest_path, mode=0o644)

    for file in plugin_dir:
        if not pkg_resources.resource_isdir(plugin_mod, file):
            plugin_str = pkg_resources.resource_string(plugin_mod, file)
            _write_bytes(os.path.join(dest_path, file), plugin_str)
        else:
            continue


def _install_service_units(execstart=None, environment=None, workingdir=None, user=None):
    environment = environment or ""
    workingdir = workingdir or '/etc/atgmlogger'
    execstart = execstart or '/usr/local/bin/atgmlogger -vv run'

    logger_service = """
    [Unit]
    Description=DgS ATGM-Serial Logger Daemon
    
    [Service]
    Type=simple
    ExecStart={execstart}
    WorkingDirectory={workingdir}
    Environment={environment}
    Restart=always
    
    [Install]
    WantedBy=multi-user.target
    """
    LOG.info("Writing atgmlogger service file to %s/%s", _UNIT_PATH, _SERVICE_NAME)
    _write_str(os.path.join(_UNIT_PATH, _SERVICE_NAME), logger_service.format(
        execstart=execstart, workingdir=workingdir, environment=environment))

    LOG.info("Writing removable storage device UDEV rule to %s", _UDEV_PATH)
    removable_udev = 'ACTION=="add", KERNEL=="sd?1", SUBSYSTEMS=="block", SYMLINK+="usbstick"'
    _write_str(os.path.join(_UDEV_PATH, '90-removable.rules'), removable_udev)

    removable_mount = """
    [Unit]
    Description=Automount removable USB device to /media/removable
    BindsTo=dev-usbstick.device
    After=dev-usbstick.device
    
    [Mount]
    What=/dev/usbstick
    Where=/media/removable
    ForceUnmount=True
    
    [Install]
    WantedBy=multi-user.target
    """
    LOG.info("Writing removable storage systemd mount file to %s/%s", _UNIT_PATH, _MOUNT_NAME)
    _write_str(os.path.join(_UNIT_PATH, _MOUNT_NAME), removable_mount)


def _install_logrotate_config(log_path=None, keep=90):
    # Create atgmlogger logrotate file in /etc/logrotate.d/atgmlogger
    # If atgmlogger config is dropped above, no further action needed as
    # there should already be a daily logrotate cron entry
    LOG.info("Installing Logrotate configuration files")
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
        notifempty
        size 100k
        dateext
        dateyesterday
        dateformat .%Y-%m-%d
        rotate 12
        compress
    }}
    {logpath}/*.dat {{
        missingok
        notifempty
        daily
        dateext
        dateyesterday
        dateformat .%Y-%m-%d
        rotate {keep}
        {postrotate}
    }}
    """.format(logpath=str(log_path.resolve()),
               keep=keep,
               postrotate=postscript)
    LOG.info("Installing logrotate configuration in %s", str(dest_path))
    _write_str(str(dest_path), config)


def _chk_boot_config():
    with open('/boot/config.txt', 'r') as fd:
        return 'enable_uart=1' in fd.read()


def _chk_cmdline_config():
    with open('/boot/cmdline.txt', 'r') as fd:
        return 'console=serial0,115200' not in fd.read()


def _configure_rpi():
    """Check/set parameters in /boot/config.txt and /boot/cmdline.txt to
    configure Raspberry Pi for GPIO serial IO.
    Specifically this requires adding `enable_uart=1` to the end of config.txt
    and removing a clause from the cmdline.txt file to disable TTY over the GPIO
    serial interface."""
    LOG.info("Running raspberry Pi serial configuration.")
    if _chk_cmdline_config():
        _sys_command("sed -i -r 's/console=serial0,115200 //' /boot/cmdline.txt")
    else:
        LOG.info("Commandline serial terminal configuration is already disabled.")

    if _chk_boot_config():
        LOG.info("enable_uart is already set in config.txt, no action taken.")
        return
    else:
        with open('/boot/config.txt', 'a') as fd:
            fd.write("enable_uart=1\n")
            LOG.critical("enable_uart set, system reboot required for configuration to take effect.")


def install(args):
    if args.debug or args.trace:
        LOG.setLevel(logging.DEBUG)
    else:
        LOG.setLevel(LOG_LVLMAP.get(args.verbose))
    if not POSIX:
        LOG.critical("Invalid system platform for installation. (Not POSIX)")
        return 1

    df_mode = 0o640
    if not args.service:
        try:
            del _file_map['atgmlogger.service']
        except KeyError:
            pass

    if args.with_mqtt:
        LOG.info("Installing MQTT plugin and AWS IoT dependency")
        try:
            import pip
            pip.main(['install', 'AWSIoTPythonSDK'])

        except ImportError:
            pass

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
            _write_bytes(dest, src_bytes, df_mode)
        except (FileNotFoundError, OSError):
            LOG.exception("Error writing resource to dest file.")

    if args.configure:
        _configure_rpi()

    if args.logrotate:
        _install_logrotate_config()

    _install_plugin_user_files()

    if args.service:
        _install_service_units()
        _sys_command('systemctl daemon-reload')
        _sys_command('systemctl enable %s' % _MOUNT_NAME)
        _sys_command('systemctl enable %s' % _SERVICE_NAME)

    if args.dependencies:
        LOG.debug("Installing system dependencies (ntfs-3g exfat-fuse exfat-utils)")
        # Try to install dependencies for USB removable storage formats
        _sys_command('apt-get update')
        # TODO: Extract dependencies into module variable
        _sys_command('apt-get install -y ntfs-3g exfat-fuse exfat-utils')

    LOG.critical("Installation of atgmlogger completed successfully.")
    return 0


def uninstall(args):
    if args.debug or args.trace:
        LOG.setLevel(logging.DEBUG)
        verbosity = 5
    else:
        LOG.setLevel(LOG_LVLMAP.get(args.verbose))
        verbosity = args.verbose
    LOG.info("Stopping and disabling services.")
    _sys_command('systemctl stop %s' % _SERVICE_NAME)
    _sys_command('systemctl disable %s' % _MOUNT_NAME)
    _sys_command('systemctl disable %s' % _SERVICE_NAME)

    for src, dest in _file_map.items():
        try:
            LOG.info("Removing file: %s", dest)
            os.remove(dest)
        except FileNotFoundError:
            pass
        except (IOError, OSError):
            if verbosity > 2:
                LOG.exception("Unable to remove installed file: %s", dest)
            else:
                LOG.warning("Unable to remove installed file: %s", dest)
    LOG.info("Successfully completed uninstall.")
    return 0


def chkinstall(args):
    LOG.setLevel(logging.INFO)
    warnings = []
    LOG.info("Verifying installation files exist.")
    atgmconfig = False
    for path in _file_map.values():
        if not os.path.exists(path):
            atgmconfig = True
            warnings.append("%s does not exist" % path)

    LOG.info("Verifying dependencies are installed.")
    dependencies = False
    # TODO: How to check if apt installed packages are present?
    if dependencies:
        warnings.append("Resolve dependency issues by executing `atgmlogger install --dependencies`")

    LOG.info("Verifying raspberry Pi serial configuration.")
    piconfig = False
    if not _chk_boot_config():
        warnings.append('enable_uart=1 configuration is not present in /boot/config.txt')
    if not _chk_cmdline_config():
        warnings.append('TTY over GPIO serial is still enabled in /boot/cmdline.txt')
    if piconfig:
        warnings.append("Resolve Pi configuration issues by executing `atgmlogger install --configure`")

    LOG.info("Verifying systemd unit-files are enabled.")
    services = False
    for file in [os.path.join(_UNIT_PATH, _SERVICE_NAME), os.path.join(_UNIT_PATH, _MOUNT_NAME),
                 os.path.join(_UDEV_PATH, '90-removable-storage.rules')]:
        if not os.path.exists(file):
            warnings.append("Service file %s was not found" % file)
    if services:
        warnings.append("Resolve systemd service file issues by executing `atgmlogger install --service`")

    for warning in warnings:
        LOG.warning(warning)
