import os
import sys
import argparse
import glob
import time
import yaml
import logging
import logging.config
import threading
import shutil
import subprocess
import uuid

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


class USBHandler:

    def __init__(self, source, dest, activity_signal, error_signal, poll_interval=1, log_facility=None,
                 copy_level='data'):
        copy_level_map = {'all': '*.*', 'application': '*.log*', 'data': '*.dat*'}

        self.fsource = source
        self.fdest = dest
        self.err_signal = error_signal
        self.act_signal = activity_signal
        self.poll_int = poll_interval
        self.log = log_facility
        self.copy_pattern = copy_level_map[copy_level]

    def copy_logs(self):
        """
        Copies application and data log files from self.logdir directory
        to the specified 'dest' directory. Files to be copied can be speicifed
        using a UNIX style glob pattern.
        :param dest: Destination directory to copy logs to
        :return: True if copy success, False if error
        """
        copy_list = []  # List of files to be copied to storage
        copy_size = 0  # Total size of logs in bytes
        for log_file in glob.glob(os.path.join(self.fsource, self.copy_pattern)):
            copy_size += os.path.getsize(log_file)
            copy_list.append(log_file)
        self.log.info("Total log size to be copied: {} KiB".format(copy_size/1024))

        def get_freebytes(path):
            statvfs = os.statvfs(os.path.abspath(path))
            return statvfs.f_bsize * statvfs.f_bavail

        if copy_size > get_freebytes(self.fdest):  # TODO: We should attempt to copy whatever will fit
            self.log.critical("USB Device does not have enough free space to copy logs")
            self.err_signal.set()
            return False

        # Else, copy the files:
        dest_dir = os.path.abspath(os.path.join(self.fdest, str(uuid.uuid4())))
        self.log.info("File Copy Job Destination: %s", dest_dir)
        os.mkdir(dest_dir)

        for src in copy_list:
            _, fname = os.path.split(src)
            try:
                dest_file = os.path.join(dest_dir, fname)
                shutil.copy(src, dest_file)
                self.log.info("Copied file %s to %s", fname, dest_file)
            except OSError:
                self.err_signal.set()
                self.log.exception("Exception encountered while copying log file.")
                return False

        diag = {'Total Copy Size': copy_size, 'Files Copied': copy_list, 'Destination Directory': dest_dir}
        self.write_diag(dest_dir, 'Diagnostic Information', **diag)

        self.log.info("All logfiles in pattern %s copied successfully", self.copy_pattern)
        return True

    @staticmethod
    def write_diag(dest, timestamp=True, delim=':', *args, **kwargs):
        """
        Write diagnostic file to copy directory
        :param dest:
        :param timestamp:
        :param delim:
        :return: 0
        """
        with open(os.path.join(dest, 'diag.log'), 'w', encoding='utf-8') as fd:
            if timestamp:
                fd.write(time.strftime('%y-%m-%d %H:%M:%S', time.gmtime(time.time())) + "(GMT) \n")
            for arg in args:
                fd.write(repr(arg) + "\n")
            for key, value in kwargs.items():
                fd.write(repr(key) + delim + repr(value) + "\n")
            fd.flush()
        return 0

    def poll(self):
        """
        Target function for usb transfer thread. This function polls for the presence of a filesystem at an arbitrary
        mount point, and if it detects one it attempts to copy any relevant log/data files from the local SD card
        storage.
        :return:
        """
        device_path = self.fdest
        while not self.exit_signal.is_set():
            if not os.path.ismount(device_path):
                pass
            else:
                self.log.info("USB device detected at {}".format(device_path))
                self.act_signal.set()

                copied = self.copy_logs(pattern=self.copy_level)
                if copied:
                    os.sync()
                    dismounted = subprocess.run(['umount', device_path])
                    self.log.info("Unmount operation returned with exit code: {}".format(dismounted))
                    time.sleep(1)
                    self.act_signal.clear()
                else:
                    self.log.info("Copy job failed, not retrying")

            # Finally:
            time.sleep(self.poll_int)


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

        # Deprecated - remove when dependencies resolved
        self.config = self.load_config(opts.configuration, defaults)

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
        self.logname = __name__
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

        # Serial Port Settings
        if opts.device is None:
            self.device = self.config['serial']['device']
        else:
            self.device = opts.device

        # USB Mount Path
        copy_level_map = {'all': '*.*', 'application': '*.log*', 'data': '*.dat*'}
        # self.usbdev = self.config['usb']['mount']
        self.copy_level = copy_level_map[self.c_usb['copy_level']]

        # Thread List Object
        self.threads = []

        # Statistics tracking
        self.last_data = 0
        self.data_interval = 0

        self.log.info("SerialLogger initialized.")

    @staticmethod
    def set_verbosity(level: int, lvlmax=3):
        if level is None or level <= 0:
            return 0
        if level > lvlmax:
            return lvlmax
        return level

    @staticmethod
    def load_config(config_path, default_opts=None):
        try:
            with open(os.path.abspath(config_path), 'r') as config_raw:
                config_dict = yaml.load(config_raw)
        except Exception as e:
            print("Exception encountered loading configuration file, proceeding with defaults.")
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

        # Select only the first logger defined in the log yaml
        logname = list(log_dict.get('loggers').keys())[0]
        self.log = logging.getLogger(logname)
        self.log.setLevel(self.verbosity_map[self.verbosity])

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

        usb_handler = USBHandler(self.logdir, self.c_usb['mount'], self.err_signal, self.log)
        usb_thread = threading.Thread(target=usb_handler.poll, name='usbutility')
        usb_thread.start()
        self.threads.append(usb_thread)

        self.log.debug("Entering main loop.")
        while not self.exit_signal.is_set():
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
