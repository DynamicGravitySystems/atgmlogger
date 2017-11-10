#!/usr/bin/python3.6
# coding: utf-8
import os
import re
import sys
import glob
import time
import uuid
import shlex
import queue
import signal
import shutil
import zipfile
import tarfile
import logging
import logging.config
import argparse
import functools
import threading
import subprocess

import yaml

import serial
try:
    import RPi.GPIO as gpio
except ImportError:
    """Allows the utility to run, but without GPIO LED signalling capability."""
    gpio = None


def level_filter(level):
    """Return a filter function to be used by a logging handler.
    This function is referenced in the default logging config file."""
    def _filter(record):
        """Filter a record based on level, allowing only records less than
        the specified level."""
        if record.levelno < level:
            return True
        return False
    return _filter


def convert_gps_time(gpsweek: int, gpsweekseconds: float):
    """
    convert_gps_time :: (int -> float) -> float
    Simplified method from DynamicGravityProcessor application:
    https://github.com/DynamicGravitySystems/DGP

    Converts a GPS time format (weeks + seconds since 6 Jan 1980) to a UNIX timestamp
    (seconds since 1 Jan 1970) without correcting for UTC leap seconds.

    Static values gps_delta and gpsweek_cf are defined by the below functions (optimization)
    gps_delta is the time difference (in seconds) between UNIX time and GPS time.
    gps_delta = (dt.datetime(1980, 1, 6) - dt.datetime(1970, 1, 1)).total_seconds()

    gpsweek_cf is the coefficient to convert weeks to seconds
    gpsweek_cf = 7 * 24 * 60 * 60  # 604800

    :param gpsweek: Number of weeks since beginning of GPS time (1980-01-06 00:00:00)
    :param gpsweekseconds: Number of seconds since the GPS week parameter
    :return: (float) unix timestamp (number of seconds since 1970-01-01 00:00:00)
    """
    # GPS time begins 1980 Jan 6 00:00, UNIX time begins 1970 Jan 1 00:00
    gps_delta = 315964800.0
    gpsweek_cf = 604800

    gps_ticks = (float(gpsweek) * gpsweek_cf) + float(gpsweekseconds)

    timestamp = gps_delta + gps_ticks

    return timestamp


def set_time(timestamp):
    # Set date using UNIX timestamp
    # OS Command: date +%s -s @<timestamp>
    # +%s sets format to Unix timestamp
    # -s/--set= sets the date to the specified timestamp
    cmd = 'date +%s -s @{ts}'.format(ts=timestamp)
    output = subprocess.check_output(shlex.split(cmd)).decode('utf-8')
    return output


def _homedir():
    return os.path.abspath(__file__)


def _runhook(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    wrapper.runhook = True
    return wrapper


def _filehook(pattern):
    def inner(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        wrapper.filehook = pattern
        return wrapper
    return inner


class RemovableStorageHandler(threading.Thread):
    def __init__(self, logdir, mount_path, gpio_h, poll_interval=.5,
                 copy_level='all', verbosity=0):
        super(RemovableStorageHandler, self).__init__(name='RemovableStorageHandler')
        copy_level_map = {'all': '*.*', 'application': '*.log*', 'data': '*.dat*'}

        self.run_hooks = []
        self.file_hooks = {}
        # Inspect class for functions with attribute runhook/filehook and append to respective hook list
        for member in self.__class__.__dict__.values():
            if hasattr(member, 'runhook'):
                self.run_hooks.append(functools.partial(member, self))
            elif hasattr(member, 'filehook'):
                self.file_hooks[getattr(member, 'filehook')] = functools.partial(member, self)

        # Assignments
        self.log_dir = logdir
        self.device = mount_path
        self.gpio_h = gpio_h
        self.poll_int = poll_interval
        self.log = logging.getLogger()
        self.verbosity = verbosity
        self.exit_signal = threading.Event()

        # Instance Fields
        self.datetime_fmt = '%y-%m-%d %H:%M:%S'
        self.copy_pattern = copy_level_map[copy_level]
        self.last_copy_path = ''
        self.last_copy_time = 0
        self.last_copy_stats = {}

        if self.verbosity > 1:
            self.log.info('{} Initialized'.format(self.__class__.__name__))

    @staticmethod
    def write_file(dest, *args, append=True, encoding='utf-8', delim=': ', eol='\n', **kwargs):
        """Write or append arbitrary data to specified dest file."""
        mode = {True: 'w+', False: 'w'}[append]
        lines = []
        for val in args:
            lines.append(str(val).strip('\'\"'))
        for key, val in kwargs.items():
            line = "".join([str(key), delim, str(val)]).strip('\'\"')
            lines.append(line)
        try:
            with open(os.path.abspath(dest), mode, encoding=encoding) as fd:
                for line in lines:
                    fd.write("".join([line, eol]))
                fd.flush()
        except OSError:
            print("Encountered OSError during write operation")
            return 1
        else:
            return 0

    def get_dest_dir(self, scheme=None, prefix=None, datefmt='%y%m%d-%H%M.%S'):
        """Generate and return unique path under self.device path to copy files.
        :param scheme: If uuid generate directory from uuid4(). Default: use current UTC time
        :param prefix: Optionally prepend a prefix to the directory name
        :param datefmt: Datetime string format used to name directory under default scheme
        """

        if scheme == 'uuid':
            dir_name = os.path.abspath(os.path.join(self.device, str(uuid.uuid4())))
        else:
            dir_name = time.strftime(datefmt+'UTC', time.gmtime(time.time()))
        if prefix:
            dir_name = prefix+dir_name

        illegals = '\\:<>?*/\"'  # Illegal filename characters
        dir_name = "".join([c for c in dir_name if c not in illegals])
        return os.path.abspath(os.path.join(self.device, dir_name))

    def _copy_file(self, src, dest, force=True):
        if not force and os.path.exists(dest):
            return None
        try:
            return shutil.copy(src, dest)
        except OSError:
            self.log.exception("Error copying file %s", src)
            return None

    def _backup_file(self, src, suffix='.bak', timestamp=True):
        if timestamp:
            date = time.strftime('-%y-%m-%d', time.gmtime(time.time()))
        else:
            date = ''
        src = os.path.abspath(src)
        dst = src + suffix + date
        return self._copy_file(src, dst)

    @staticmethod
    def _compress(path, *args, method=None, compression=None):
        log = logging.getLogger()

        ext = {'zip': '.zip', 'tar': '.tar'}
        tar_ext = {'lzma': '.lz', 'gzip': '.gz', 'bzip': '.bz2'}
        cmp_modes = {'zip': {None: zipfile.ZIP_STORED, 'lzma': zipfile.ZIP_LZMA, 'bzip': zipfile.ZIP_BZIP2,
                             'zlib': zipfile.ZIP_DEFLATED},
                     'tar': {None: '', 'lzma': 'xz', 'gzip': 'gz', 'bzip': 'bz2', 'bzip2': 'bz2'}
                     }

        if method not in ext.keys():
            method = 'zip'
        if os.path.isdir(path):
            # If the provided path is a directory create unique zipfile name
            arcname = str(uuid.uuid4())[:13] + ext[method]
            path = os.path.abspath(os.path.join(path, arcname))

        if compression and compression not in cmp_modes[method].keys():
            log.warning("Invalid compression method: '{}' defaulting to None for target: {}".format(compression, path))
            compression = None

        inputs = []
        for file in args:
            if os.path.exists(file) and os.path.isfile(file):
                inputs.append(os.path.abspath(file))

        if method == 'zip':
            try:
                with zipfile.ZipFile(path, mode="w", compression=cmp_modes[method][compression]) as zf:
                    for file in inputs:
                        zf.write(os.path.abspath(file), arcname=os.path.basename(file))
            except FileExistsError:
                log.exception("Zipfile already exists")
                return None

        elif method == 'tar':
            if compression:
                path += tar_ext[compression]
                mode = 'x:' + cmp_modes[method][compression]
            else:
                mode = 'x'
            tf = None
            try:
                tf = tarfile.open(path, mode=mode)
                for file in inputs:
                    tf.add(file, arcname=os.path.basename(file))
            except FileExistsError:
                log.exception("Tarfile already exists")
            finally:
                if tf:
                    tf.close()
        return path

    @_filehook(r'(dgs)?diag(nostics)?\.?(txt|trigger|dat)?')
    def run_diag(self, match):
        """
        Execute series of diagnostic commands and return dictionary of results in form dict[cmd] = result
        :return: Dict. of diagnostic commands = results
        """
        self.log.debug("Running diagnostics on system")
        diag_cmds = ['uptime', 'top -b -n1', 'df -H', 'free -h', 'dmesg']
        diag = {'Diagnostic Timestamp': time.strftime(self.datetime_fmt, time.gmtime(time.time()))}
        for cmd in diag_cmds:
            try:
                output = subprocess.check_output(shlex.split(cmd)).decode('utf-8')
                diag[cmd] = output
            except FileNotFoundError:
                self.log.warning('Command: {} not available on this system.'.format(cmd))
                continue

        if self.verbosity > 2:
            proc_cpuinfo = '/proc/cpuinfo'
            try:
                with open(proc_cpuinfo, 'r') as fd:
                    cpuinfo = fd.read()
                diag[proc_cpuinfo] = cpuinfo
            except FileNotFoundError:
                self.log.warning('{} not available on this system.'.format(proc_cpuinfo))

        self.write_file(os.path.join(self.last_copy_path, 'diag.txt'), delim=':\n', **diag)

    @_filehook(r'config.ya?ml')
    def update_config(self, match, *args):
        """Copy new configuration file from USB and reload program configuration"""
        # src = os.path.abspath(os.path.join(self.device, match))
        self._backup_file('./config.yaml')
        raise NotImplementedError

    @_filehook(r'log(ging)?.ya?ml')
    def update_log_config(self, match, *args):
        """Copy new configuration file from USB and reload logging configuration"""
        print("Performing logging config update")
        raise NotImplementedError

    @_runhook
    def copy_logs(self):
        """
        :return: 0 if copy success, 1 if error
        """
        file_list = []  # List of files to be copied to storage
        copy_size = 0   # Accumulated size of logs in bytes
        for log_file in glob.glob(os.path.join(self.log_dir, self.copy_pattern)):
            copy_size += os.path.getsize(log_file)
            file_list.append(os.path.normpath(log_file))
        self.log.info("Total log size to be copied: {} KiB".format(copy_size/1024))

        def get_free(path):
            try:
                statvfs = os.statvfs(os.path.abspath(path))
            except AttributeError:
                return 1000000000
            return statvfs.f_bsize * statvfs.f_bavail

        if copy_size > get_free(self.device):  # TODO: We should attempt to copy whatever will fit
            self.log.critical("USB Device does not have enough free space to copy logs")
            # self.err_signal.set()
            return 1

        # Else, copy the files:
        dest_dir = self.get_dest_dir()
        self.log.info("File Copy Job Destination: %s", dest_dir)
        os.mkdir(dest_dir)

        for src in file_list:
            _, file = os.path.split(src)
            try:
                dest_file = os.path.join(dest_dir, file)
                shutil.copy(src, dest_file)
                self.log.info("Copied file %s to %s", file, dest_file)
            except OSError:
                # self.err_signal.set()
                self.log.exception("Exception encountered while copying log file.")
                return 1

        self.last_copy_path = dest_dir
        self.last_copy_time = time.time()
        self.last_copy_stats = {'Total Copy Size (KiB)': copy_size, 'Files Copied': file_list,
                                'Destination Directory': dest_dir, 'Last Copy Time': self.last_copy_time}
        self.log.info("All log files in pattern %s copied successfully", self.copy_pattern)
        return 0

    @_runhook
    def watch_files(self):
        """List files on the device path, to check for anything we should take action on, e.g. config update"""
        root_files = [file.name for file in os.scandir(self.device) if file.is_file()]
        flist = " ".join(root_files)
        for pattern in self.file_hooks:
            match = re.search(pattern, flist)
            if match:
                self.log.info("Trigger file matched: {}".format(match.group()))
                self.file_hooks[pattern](match.group())

    @staticmethod
    def _unmount(mount_path):
        log = logging.getLogger()
        try:
            result = subprocess.check_output(['/bin/umount', mount_path])
            print(result)
        except OSError:
            result = None
            log.exception("Error occured while attempting to unmount device: {}".format(mount_path))
        return result

    def exit(self, join=False):
        self.exit_signal.set()
        if join:
            self.join()

    def run(self):
        """
        Target function for usb transfer thread. This function polls for the presence of a filesystem at an arbitrary
        mount point, and if it detects one it attempts to copy any relevant log/data files from the local SD card
        storage.
        :return:
        """
        while not self.exit_signal.is_set():
            time.sleep(self.poll_int)
            if not os.path.ismount(self.device):
                continue

            # Else:
            self.log.info("USB device detected at {}".format(self.device))
            self.gpio_h.blink(15, -1, .05)  # TODO: This needs to be fixed so as not to hardcode the pin num here

            for run_hook in self.run_hooks:
                run_hook()
            os.sync()

            # Finally:
            umount = self._unmount(self.device)
            self.log.info("Unmount operation returned with exit code: {}".format(str(umount)))
            self.gpio_h.clear()
        return 0


class GpioHandler(threading.Thread):
    """
    Threaded class used to handle raspberry pi GPIO signalling/output.
    Call start() method on this class after instantiating.
    """

    def __init__(self, config, queue_size=2, verbose=False):
        super(GpioHandler, self).__init__(name='GpioHandler')
        self.log = logging.getLogger(__name__)
        self._exit = threading.Event()

        self._resume = None
        self.queue = queue.Queue(queue_size)

        if not gpio:
            self.log.warning("RPi.GPIO Module is not available. GpioHandling disabled.")
            self._init = False
            return

        self.mode = {'board': gpio.BOARD, 'bcm': gpio.BCM}[config.get('mode', 'board')]

        self.pin_data = int(config['data_led'])
        self.pin_usb = int(config['usb_led'])
        self.pin_err = int(config['aux_led'])
        self.outputs = [self.pin_data, self.pin_err, self.pin_usb]
        self.inputs = []

        if not verbose:
            gpio.setwarnings(False)
        gpio.setmode(self.mode)
        self._setup(self.outputs, gpio.OUT)
        self._setup(self.inputs, gpio.IN)
        self._init = True
        self.log.debug("GpioHandler initialized with data_led = {}".format(self.pin_data))

    @staticmethod
    def _setup(pins, mode):
        for pin in pins:
            gpio.setup(pin, mode)

    @staticmethod
    def _output(pin, freq=.1):
        try:
            gpio.output(pin, True)
            time.sleep(freq)
            gpio.output(pin, False)
            time.sleep(freq)
        except AttributeError:
            print("GPIO not available to turn on pin {}".format(pin))
            time.sleep(freq)
            print("GPIO not available to turn off pin {}".format(pin))

    def blink(self, led, count=1, freq=0.01, priority=0, force=False):
        """
        Put a request to blink an led on the blink queue
        :param led:
        :param count: Number of times to repeat, to repeat forever pass -1
        :param freq:
        :param priority: Placeholder for future implementation
        :param force:
        :return:
        """
        if led not in self.outputs:
            # Prevent runtime error if invalid pin is triggered which has not been initialized
            return False

        # Condense parameters into a tuple
        blink_t = (led, count, freq, priority)
        if force:
            try:
                self._resume = self.queue.get(block=False)
                self.clear()
            except queue.Empty:
                self._resume = None
        try:
            self.queue.put(blink_t, block=force)
            return True
        except queue.Full:
            return False

    # TODO: Add ability to clear only specific signals (for a pin)
    def clear(self):
        """Clear the current signal(s) from queue"""
        while not self.queue.empty():
            self.queue.get(block=False)

    def exit(self, join=False):
        """
        Exit the GpioHandler thread by setting the _exit signal, clearing the current queue,
        then putting an "exit" on the queue (otherwise the loop will block until an item is avail).
        """
        if not self.is_alive():
            return True
        self.log.info("Exit called on thread:{} id:{}".format(self.name, self.ident))
        self._exit.set()
        self.clear()
        self.queue.put(None, False)  # Put an empty item on queue to force continue
        # Turn off all initialized pins
        if join:
            self.join()

    def run(self):
        """
        If persistent blink is set, then blink the specified LED until it is unset
        else:
        Wait for an intermittent blink
        priority is not currently evaluated, a thread can force a blink using the force param in blink()

        :return:
        """
        if not self._init:
            self.log.warning("GpioHandler not initialized, functionality disabled.")
            self._exit.set()
            return

        while not self._exit.is_set():
            item = self.queue.get(block=True)
            if item is None:
                continue

            pin, count, freq, priority = item
            if count == 0:
                continue
            elif count-1 != 0:
                # If the decremented count is not 0 we'll put it back on the queue to run again
                self.blink(pin, count-1, freq, priority, force=False)
            elif self._resume:
                # If the decremented count is 0, and we have an item to resume, put the resume item on the queue
                self.blink(*self._resume)

            self._output(pin, freq)

        # Clean up gpio before exiting
        if gpio:
            for pin in self.outputs:
                gpio.output(pin, False)
            gpio.cleanup()
        self.log.info("GpioHandler thread safely exited.")


class SerialLogger(threading.Thread):
    def __init__(self, argv):
        super(SerialLogger, self).__init__(name='SerialLogger')
        parser = argparse.ArgumentParser(prog=argv[0],
                                         description="Serial Data Logger")
        parser.add_argument('-V', '--version', action='version',
                            version='0.1')
        parser.add_argument('-v', '--verbose', action='count')
        parser.add_argument('-l', '--logdir', action='store', default='/var/log/dgs')
        parser.add_argument('-d', '--device', action='store')
        parser.add_argument('-c', '--configuration', action='store', default='config.yaml')
        args = parser.parse_args(argv[1:])

        # Default settings in the event of missing config.yaml file.
        defaults = {
            'version': 0.1,
            'usb': {
                'mount': '/media/removable',
                'copy_level': 'all'
            },
            'logging': {
                'logdir': '/var/log/dgs/'
            },
            'serial': {
                'port': '/dev/ttyS0',
                'baudrate': 57600,
                'bytesize': 8,
                'parity': 'N',
                'stopbits': 1,
                'xonxoff': False,
                'rtscts': False,
                'dsrdtr': False,
                'timeout': 1
            },
            'signal': {
                'data_led': 16,
                'usb_led': 18,
                'aux_led': 22
            }
        }

        config = self.load_config(args.configuration, defaults)
        # Config subleafs
        self.c_usb = config.get('usb', defaults['usb'])
        self.c_logging = config.get('logging', defaults['logging'])
        self.c_serial = config.get('serial', defaults['serial'])
        self.c_signal = config.get('signal', defaults['signal'])

        self.thread_poll_interval = 1   # Seconds to sleep between run loops
        self.usb_poll_interval = 3  # Seconds to sleep between checking for USB device

        # Logging definitions
        if args.logdir is None:
            self.logdir = self.c_logging['logdir']
        else:
            self.logdir = args.logdir
        self.log = None
        self.data_level = 60
        self.verbosity = self.set_verbosity(args.verbose)
        self.verbosity_map = {0: logging.CRITICAL, 1: logging.WARNING, 2: logging.INFO, 3: logging.DEBUG}

        self.init_logging()

        # Thread signal definitions
        self.exit_signal = threading.Event()
        self.reload_signal = threading.Event()
        self.err_signal = threading.Event()

        # Serial Port Settings
        if args.device is None:
            self.device = self.c_serial['port']
        else:
            self.device = args.device

        # USB Mount Path
        copy_level_map = {'all': '*.*', 'application': '*.log*', 'data': '*.dat*'}
        self.copy_level = copy_level_map[self.c_usb['copy_level']]

        # Thread List Object
        self.threads = []

        # Initialize Utility threads, but don't start them
        gpioh = GpioHandler(self.c_signal)
        self.data_signal = functools.partial(gpioh.blink, self.c_signal['data_led'], 1, 0.01)
        self.no_data_signal = functools.partial(gpioh.blink, self.c_signal['aux_led'], 1, 0.1)
        self.threads.append(gpioh)

        rsh_opts = {
            'logdir': self.logdir,
            'mount_path': self.c_usb['mount'],
            'gpio_h': gpioh,
            'copy_level': self.c_usb['copy_level'],
            'verbosity': self.verbosity
        }
        rsh = RemovableStorageHandler(**rsh_opts)
        self.threads.append(rsh)

        # Time synchronization check
        self.time_synced = False
        self.last_time_check = 0

        # Statistics tracking
        self.last_data = 0
        self.data_interval = 0

    @staticmethod
    def set_verbosity(level: int, lvlmax=3):
        # Covered
        if level is None or level <= 0:
            return 0
        if level > lvlmax:
            return lvlmax
        return level

    @staticmethod
    def load_config(config_path, default_opts=None):
        # Covered
        try:
            with open(os.path.abspath(config_path), 'r') as config_raw:
                config_dict = yaml.load(config_raw)
        except OSError:
            # print("Exception encountered loading configuration file, proceeding with defaults.")
            # print(e.__repr__())
            config_dict = default_opts
        return config_dict

    def init_logging(self):
        """
        Initialize logging facilities, defined in logging.yaml file.
        :return:
        """
        config_f = 'logging.yaml'
        with open(config_f, 'r') as log_yaml:
            log_dict = yaml.load(log_yaml)

        logdir = self.logdir

        # Apply base logdir to any filepaths in log_dict
        for hdlr, properties in log_dict.get('handlers').items():
            path = properties.get('filename', False)
            if path:
                # Rewrite log config path with self.logdir as the base
                _, fname = os.path.split(path)
                abs_path = os.path.join(logdir, fname)
                log_dict['handlers'][hdlr]['filename'] = abs_path

        # Check/create logging directory
        if not os.path.exists(logdir):
            os.makedirs(logdir, mode=0o755, exist_ok=False)

        # Apply configuration from imported YAML Dict
        logging.config.dictConfig(log_dict)

        self.log = logging.getLogger()
        self.log.setLevel(self.verbosity_map[self.verbosity])

        if self.verbosity > 2:
            self.log.debug("Log files will be saved to %s", logdir)

    def clean_exit(self):
        """
        Force a clean exit from the program, joining all threads before returning.
        :return: Int exit_code
        """
        self.exit_signal.set()
        self.log.warning("Application exiting, joining threads.")
        for thread in self.threads:
            try:
                thread.exit()
            except AttributeError:
                pass
            if thread.is_alive():
                self.log.debug("Thread {} is still alive, joining.".format(thread.name))
                thread.join()
                self.log.debug("Thread {} joined".format(thread.name))
        return 0

    @staticmethod
    def decode(bytearr, encoding='utf-8'):
        if isinstance(bytearr, str):
            return bytearr

        nonprintable = list(range(0, 32))
        illegal = [255]
        strip_chars = nonprintable + illegal  # Unprintable characters \x00 \xff
        try:
            raw = bytes([c for c in bytearr if c not in strip_chars])
            decoded = raw.decode(encoding, errors='ignore').strip('\r\n')
        except AttributeError:
            decoded = None
        return decoded

    def get_handle(self, **kwargs):
        se_handle = serial.Serial(**kwargs)
        self.log.info("Opened serial handle - device:{port} baudrate:{baudrate}, parity:{parity}, "
                      "stopbits:{stopbits}, bytesize:{bytesize}".format(**kwargs))
        return se_handle

    def run(self):
        """ TODO: Documentation """
        # Start utility threads
        for thread in self.threads:
            thread.start()

        try:
            se_handle = self.get_handle(**self.c_serial)
        except serial.SerialException:
            self.log.exception("Error opening serial port for listening, terminating execution.")
            return 1

        self.log.debug("Entering SerialLogger main loop.")
        tick = 0
        while not self.exit_signal.is_set():
            if self.reload_signal.is_set():
                self.init_logging()
                self.reload_signal.clear()

            if not se_handle.is_open:
                try:
                    se_handle.open()
                except serial.SerialException:
                    self.log.exception("Unable to reopen serial handle, exiting.")
                    return 1

            try:
                data = self.decode(se_handle.readline())
                tick += 1
                if data == '':
                    self.no_data_signal()  # Call partial function to blink LED every 1 second (timeout) if no data
                    continue
                if data is None:
                    continue

                self.log.log(self.data_level, data)  # Write data to gravdata log file using custom filter
                self.data_signal()
                self.data_interval = time.time() - self.last_data
                self.last_data = time.time()
                self.log.debug("Last data received at {} UTC".format(time.strftime("%H:%M:%S",
                                                                                   time.gmtime(self.last_data))))
                self.log.debug(data)

                # If time is not synced, check every 10 ticks, and set system time if GPS time is available.
                if not self.time_synced and (self.last_time_check > tick + 10):
                    self.last_time_check = tick
                    # Decode data string and look for GPS time
                    # TODO: Allow configuration of the GPS field no.
                    fields = data.split(',')
                    gpsweek = int(fields[11])
                    if gpsweek == 0:
                        # If gpsweek field is 0 then we can assume time is not synced on the sensor
                        self.time_synced = False
                        continue

                    gpssecond = float(fields[12])
                    timestamp = convert_gps_time(gpsweek, gpssecond)
                    set_time(timestamp)

            except serial.SerialException:
                self.log.exception("Exception encountered attempting to call readline() on serial handle")
                se_handle.close()

        se_handle.close()
        logging.shutdown()
        return 0


if __name__ == "__main__":
    main = SerialLogger(sys.argv)
    exit_code = 1
    try:
        print("Starting main thread.")
        main.start()
        # Wait (potentially forever) for main to finish.
        # main.join()
        signal.pause()  # This allows keyboard interrupt to be processed (I think)
    except KeyboardInterrupt:
        print("KeyboardInterrupt intercepted in __name__ block. Exiting Program.")
        main.clean_exit()
        exit_code = 0
    sys.exit(0)
