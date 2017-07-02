import os
import re
import sys
import glob
import time
import uuid
import yaml
import shlex
import shutil
import zipfile
import tarfile
import logging
import logging.config
import argparse
import functools
import threading
import subprocess

import serial


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
    def __init__(self, logdir, mount_path, activity_signal, error_signal, poll_interval=1,
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
        self.err_signal = error_signal
        self.act_signal = activity_signal
        self.poll_int = poll_interval
        self.log = logging.getLogger()
        self.verbosity = verbosity

        # Instance Fields
        self.datetime_fmt = '%y-%m-%d %H:%M:%S'
        self.copy_pattern = copy_level_map[copy_level]
        self.last_copy_path = ''
        self.last_copy_time = 0
        self.last_copy_stats = {}

        if self.verbosity > 1:
            self.log.info('{} Initialized'.format(self.__class__.__name__))

    @staticmethod
    def write(dest, *args, append=True, encoding='utf-8', delim=': ', eol='\n', **kwargs):
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
                    fd.write(line + eol)
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
            try:
                tf = tarfile.open(path, mode=mode)
                for file in inputs:
                    tf.add(file, arcname=os.path.basename(file))
            except FileExistsError:
                log.exception("Tarfile already exists")
            finally:
                tf.close()
        return path

    @_filehook(r'(dgs)?diag(nostics)?\.?(txt|trigger|dat)?')
    def run_diag(self, *args, **kwargs):
        """
        Execute series of diagnostic commands and return dictionary of results in form dict[cmd] = result
        :param args: For compatability with hook call
        :param kwargs: For compatability with hook call
        :return: Dict. of diagnostic commands = results
        """
        diag_cmds = ['top -b -n1', 'df -H', 'free -h', 'dmesg']
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

        return diag

    @_filehook(r'config.ya?ml')
    def update_config(self, match, *args):
        """Copy new configuration file from USB and reload program configuration"""
        src = os.path.abspath(os.path.join(self.device, match))
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
            self.err_signal.set()
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
                self.err_signal.set()
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
                self.file_hooks[pattern](match.group(), self.last_copy_path)

    @staticmethod
    def _unmount(mount_path):
        log = logging.getLogger()
        try:
            result = subprocess.check_output(['/bin/umount', mount_path])
        except OSError:
            log.exception("Error occured while attempting to unmount device: {}".format(mount_path))
        return result

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
            self.act_signal.set()

            for run_hook in self.run_hooks:
                run_hook()
            os.sync()

            # Finally:
            umount = self._unmount(self.device)
            self.log.info("Unmount operation returned with exit code: {}".format(umount))
            self.act_signal.clear()


class SerialLogger:
    def __init__(self, argv):
        parser = argparse.ArgumentParser(prog=argv[0],
                                         description="Serial Data Logger")
        parser.add_argument('-V', '--version', action='version',
                            version='0.1')
        parser.add_argument('-v', '--verbose', action='count')
        parser.add_argument('-l', '--logdir', action='store', default='/var/log/dgs')
        parser.add_argument('-d', '--device', action='store')
        parser.add_argument('-c', '--configuration', action='store', default='config.yaml')
        opts = parser.parse_args(argv[1:])

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
                'device': '/dev/ttyS0',
                'baudrate': 57600,
                'bytesize': 8,
                'parity': 'N',
                'stopbits': 1,
                'flowctrl': 0,
                'timeout': 1
            },
            'signal': {
                'data_led': 16,
                'usb_led': 18,
                'aux_led': 22
            }
        }

        config = self.load_config(opts.configuration, defaults)
        # Config sub subleafs
        self.c_usb = config.get('usb', defaults['usb'])
        self.c_logging = config.get('logging', defaults['logging'])
        self.c_serial = config.get('serial', defaults['serial'])
        self.c_signal = config.get('signal', defaults['signal'])

        self.thread_poll_interval = 1   # Seconds to sleep between run loops
        self.usb_poll_interval = 3  # Seconds to sleep between checking for USB device

        # Logging definitions
        if opts.logdir is None:
            self.logdir = self.c_logging['logdir']
        else:
            self.logdir = opts.logdir
        self.log = None
        self.data_level = 60
        self.verbosity = self.set_verbosity(opts.verbose)
        self.verbosity_map = {0: logging.CRITICAL, 1: logging.WARNING, 2: logging.INFO, 3: logging.DEBUG}

        self.init_logging()

        # Thread signal definitions
        self.exit_signal = threading.Event()
        self.data_signal = threading.Event()
        self.usb_signal = threading.Event()
        self.err_signal = threading.Event()
        self.reload_signal = threading.Event()

        # Serial Port Settings
        if opts.device is None:
            self.device = self.c_serial['device']
        else:
            self.device = opts.device

        # USB Mount Path
        copy_level_map = {'all': '*.*', 'application': '*.log*', 'data': '*.dat*'}
        self.copy_level = copy_level_map[self.c_usb['copy_level']]

        # Thread List Object
        self.threads = []

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
        except Exception as e:
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
            if thread.is_alive():
                self.log.debug("Thread {} is still alive, joining.".format(thread.name))
                thread.join()
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

    def device_listener(self, device=None):
        """
        Target function for serial data collection thread, called from run() method.
        :param device: Full path to the serial device to listen on e.g. /dev/ttyS0
        :return: Int exit_code. 0 = success, 1 = error.
        """
        try:
            handle = serial.Serial(device, baudrate=self.c_serial['baudrate'], parity=self.c_serial['parity'],
                                   stopbits=self.c_serial['stopbits'], bytesize=self.c_serial['bytesize'],
                                   timeout=self.c_serial['timeout'])
            self.log.info("Opened serial handle on device:{device} baudrate:{baudrate}, parity:{parity}, "
                          "stopbits:{stopbits}, bytesize:{bytesize}".format(device=device,
                                                                            baudrate=self.c_serial['baudrate'],
                                                                            parity=self.c_serial['parity'],
                                                                            stopbits=self.c_serial['stopbits'],
                                                                            bytesize=self.c_serial['bytesize']))
        except serial.SerialException:
            self.log.exception('Exception encountered attempting to open serial comm port %s', device)
            return 1
        while not self.exit_signal.is_set():
            try:
                data = self.decode(handle.readline())
                if data == '':
                    continue
                if data is not None:
                    self.log.log(self.data_level, data)
                    self.data_interval = time.time() - self.last_data
                    self.last_data = time.time()
                    self.log.debug("Last data received at {} UTC".format(time.strftime("%H:%M:%S",
                                                                                       time.gmtime(self.last_data))))
                    self.data_signal.set()
                    self.log.debug(data)

            except serial.SerialException:
                self.log.exception('Exception encountered attempting to read from device %s', device)
                handle.close()
                return 1
        if self.exit_signal.is_set():
            self.log.info('Exit signal received, exiting thread %s', device)
        handle.close()
        return 0

    def led_signaler(self):
        try:
            import RPi.GPIO as GPIO
        except ImportError:
            self.log.warning("Raspberry PI GPIO Module is not available, LED signaling disabled.")
            return 1  # Return and exit thread

        # Initialize Raspberry Pi GPIO pins
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BOARD)

        def blink_led(gpio_pin, duration=.1):
            """Turn an output at pin on for duration, then off"""
            # Gets the current state of an output (not necessary currently)
            # state = gpio.input(pin)
            GPIO.output(gpio_pin, True)
            time.sleep(duration)
            GPIO.output(gpio_pin, False)
            time.sleep(duration)

        data_l = self.c_signal['data_led']
        usb_l = self.c_signal['usb_led']
        aux_l = self.c_signal['aux_led']
        outputs = [data_l, usb_l, aux_l]
        for pin in outputs:
            GPIO.setup(pin, GPIO.OUT)
            blink_led(pin)  # Test single blink on each LED

        while not self.exit_signal.is_set():
            # USB signal takes precedence over data recording
            if self.usb_signal.is_set():
                blink_led(usb_l, duration=.1)
                # Don't clear the signal, the transfer logic will clear when complete
            elif self.data_signal.is_set():
                blink_led(data_l, duration=.1)
                self.data_signal.clear()

            if self.err_signal.is_set():
                GPIO.output(aux_l, True)
            else:
                GPIO.output(aux_l, False)
            time.sleep(.01)  # Rate limit the loop to cut down CPU hogging

        # Exiting: Turn off all outputs, then call cleanup()
        for pin in outputs:
            GPIO.output(pin, False)
        GPIO.cleanup()
        self.log.info("Led thread gracefully exited")

    def run(self):
        self.threads = []

        # Initialize utility threads
        led_thread = threading.Thread(target=self.led_signaler, name='ledsignal')
        led_thread.start()
        self.threads.append(led_thread)

        usb_handler_opts = {
            'log_src': self.logdir,
            'device_path': self.c_usb['mount'],
            'activity_signal': self.usb_signal,
            'error_signal': self.err_signal,
            'copy_level': self.c_usb['copy_level'],
            'verbosity': self.verbosity
        }

        usb_handler = RemovableStorageHandler(**usb_handler_opts)
        usb_handler.start()
        self.threads.append(usb_handler)

        self.log.debug("Entering main loop.")
        while not self.exit_signal.is_set():
            if self.reload_signal.is_set():
                self.init_logging()
                self.reload_signal.clear()

            # Filter out dead threads
            self.threads = list(filter(lambda x: x.is_alive(), self.threads[:]))
            if self.device not in [t.name for t in self.threads]:
                self.log.debug("Spawning new thread for device {}".format(self.device))
                dev_thread = threading.Thread(target=self.device_listener,
                                              name=self.device, kwargs={'device': self.device})
                dev_thread.start()
                self.threads.append(dev_thread)

            time.sleep(self.thread_poll_interval)
        return 0


if __name__ == "__main__":
    main = SerialLogger(sys.argv)
    exit_code = 1
    try:
        exit_code = main.run()
    except KeyboardInterrupt:
        print("KeyboardInterrupt intercepted in __name__ block. Exiting Program.")
        main.clean_exit()
    finally:
        exit(exit_code)
