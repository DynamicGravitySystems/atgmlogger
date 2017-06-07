import os
import sys
import argparse
import time
import yaml
import logging
import logging.config
import threading
import shutil
import uuid

import serial
try:
    import RPi.GPIO as gpio
except ImportError:
    print("Raspberry PI GPIO Module is not available, LED signaling disabled.")
    gpio = False


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


class SerialLogger:
    def __init__(self, argv):
        parser = argparse.ArgumentParser(prog=argv[0],
                                         description="Serial Data Logger")
        parser.add_argument('-V', '--version', action='version',
                            version='0.1')
        parser.add_argument('-v', '--verbose', action='count')
        parser.add_argument('-l', '--logdir', action='store', default='/var/log/dgs')
        parser.add_argument('-d', '--device', action='store', default='/dev/ttyS0')
        opts = parser.parse_args(argv[1:])

        self.thread_poll_interval = 1   # Seconds to sleep between run loops
        self.usb_poll_interval = 3  # Seconds to sleep between checking for USB device

        # Logging definitions
        self.logdir = os.path.abspath(opts.logdir)
        self.logname = __name__
        self.log = None
        self.data_level = 60
        self.verbosity = opts.verbose
        self.init_logging()

        # Thread signal definitions
        self.exit_signal = threading.Event()
        self.data_signal = threading.Event()
        self.usb_signal = threading.Event()
        self.err_signal = threading.Event()

        # Serial Port Settings (TODO: Read these from configuration file)
        self.device = opts.device
        self.baudrate = 57600
        self.parity = serial.PARITY_NONE
        self.stopbits = serial.STOPBITS_ONE

        # LED Signal Settings
        self.data_led = 16
        self.usb_led = 18
        self.aux_led = 15

        # USB Mount Path
        self.usbdev = '/media/usb0'

        self.log.info("SerialLogger initialized.")

    def init_logging(self):
        """
        Initialize logging facilities, defined in logging.yaml file.
        :return:
        """
        config_f = 'logging.yaml'
        log_yaml = open(config_f, 'r')
        log_dict = yaml.load(log_yaml)

        # Apply base logdir to any filepaths in log_dict
        for hdlr, properties in log_dict.get('handlers').items():
            path = properties.get('filename', False)
            if path:
                # Rewrite log config path with self.logdir as the base
                _, fname = os.path.split(path)
                abs_path = os.path.join(self.logdir, fname)
                log_dict['handlers'][hdlr]['filename'] = abs_path

        # Check/create logging directory
        if not os.path.exists(self.logdir):
            os.makedirs(self.logdir, mode=0o755, exist_ok=False)

        logging.config.dictConfig(log_dict)

        # Select only the first logger defined in the log yaml
        self.logname = list(log_dict.get('loggers').keys())[0]
        self.log = logging.getLogger(self.logname)

        verbosity = {0: logging.CRITICAL, 1: logging.WARNING, 2: logging.INFO, 3: logging.DEBUG}
        self.log.setLevel(verbosity[self.verbosity])

        self.log.debug("Log files will be saved to %s", self.logdir)

    def clean_exit(self, threads):
        """
        Force a clean exit from the program, joining all threads before returning.
        :param threads:
        :return:
        """
        self.exit_signal.set()
        self.log.warning("Application exiting, joining threads.")
        for thread in threads:
            if thread.is_alive():
                self.log.debug("Thread {} is still alive, joining.".format(thread.name))
                thread.join()
        return 0

    @staticmethod
    def decode(bytearr, encoding='utf-8'):
        if isinstance(bytearr, str):
            return bytearr
        try:
            decoded = bytearr.decode(encoding).strip('\r\n')
        except UnicodeDecodeError:
            illegal = [0, 255]
            decoded = bytes([x for x in bytearr if x not in illegal]).decode(encoding)
        except AttributeError:
            decoded = None
        return decoded

    def device_listener(self, device=None):
        try:
            handle = serial.Serial(device, baudrate=self.baudrate, parity=self.parity,
                                   stopbits=self.stopbits, timeout=1)
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
        if not gpio:
            self.log.warning("GPIO Module is not available, LED signaling will not function.")
            return 1
        # Initialize Raspberry Pi GPIO pins
        gpio.setwarnings(False)
        gpio.setmode(gpio.BOARD)

        def blink_led(pin, duration=.1):
            """Turn an output at pin on for duration, then off"""
            # Gets the current state of an output (not necessary currently)
            # state = gpio.input(pin)
            gpio.output(pin, True)
            time.sleep(duration)
            gpio.output(pin, False)

        outputs = [self.data_led, self.usb_led, self.aux_led]
        for output in outputs:
            gpio.setup(output, gpio.OUT)
            blink_led(output)  # Test single blink on each LED

        while not self.exit_signal.is_set():
            # USB signal takes precedence over data recording
            if self.usb_signal.is_set():
                blink_led(self.usb_led)
                # Don't clear the signal, the transfer logic will clear when complete
            elif self.data_signal.is_set():
                blink_led(self.data_led)
                self.data_signal.clear()

    def usb_utility(self):
        copied = False

        def get_free(device_path):
            """Return available free bytes on device_path"""
            stat = os.statvfs(device_path)
            blk_size = stat.f_bsize
            blk_avail = stat.f_bavail

            avail_bytes = blk_size * blk_avail
            # avail_mib = avail_bytes / (1024 ** 1024)
            return avail_bytes

        while not self.exit_signal.is_set():
            if not os.path.ismount(self.usbdev):
                copied = False
                time.sleep(self.usb_poll_interval)
                continue

            if not copied:
                self.log.debug("USB device detected at {}".format(self.usbdev))
                self.usb_signal.set()

                copy_list = []
                log_files = os.listdir(self.logdir)
                log_size = 0  # Total size of logs in bytes
                for log in [data_f for data_f in log_files if (os.path.splitext(data_f)[1] == '.dat')]:
                    l_path = os.path.join(self.logdir, log)
                    l_size = os.path.getsize(l_path)
                    log_size += l_size
                    copy_list.append(l_path)

                if log_size > get_free(self.usbdev):
                    self.log.critical("USB Device does not have enough free space to copy logs")
                    self.err_signal.set()
                    copied = True
                    continue
                # Else:
                dir_uid = uuid.uuid4()
                dest_dir = os.path.abspath(os.path.join(self.usbdev, dir_uid))
                os.mkdir(dest_dir)

                for file in copy_list:
                    self.log.debug("Copying log file: %s", file)
                    shutil.copy(file, os.path.join(dest_dir, log))
                self.log.debug("All log files copied to USB device")
                copied = True
                os.sync()
                self.usb_signal.clear()
            else:
                pass  # Files were already copied

            time.sleep(self.usb_poll_interval)

    def run(self):
        threads = []

        # Initialize utility threads
        led_thread = threading.Thread(target=self.led_signaler, name='ledsignal')
        led_thread.start()
        threads.append(led_thread)

        usb_thread = threading.Thread(target=self.usb_utility, name='usbutility')
        usb_thread.start()
        threads.append(usb_thread)

        self.log.debug("Entering main loop.")
        while not self.exit_signal.is_set():
            try:
                # Filter out dead threads
                threads = list(filter(lambda x: x.is_alive(), threads[:]))
                if self.device not in [t.name for t in threads]:
                    self.log.debug("Spawning new thread for device {}".format(self.device))
                    dev_thread = threading.Thread(target=self.device_listener,
                                                  name=self.device, kwargs={'device': self.device})
                    dev_thread.start()
                    threads.append(dev_thread)
            except KeyboardInterrupt:
                return self.clean_exit(threads)

            time.sleep(self.thread_poll_interval)
        # Run loop exited - cleanup and return
        # TODO: This method and above try/except are never called as KeyboardInterrupt is captured outside in main block
        return self.clean_exit(threads)


if __name__ == "__main__":
    main = SerialLogger(sys.argv)
    exit_code = 1
    try:
        exit_code = main.run()
    except KeyboardInterrupt:
        print("KeyboardInterrupt intercepted in __name__ block. Exiting Program.")
        main.exit_signal.set()
    finally:
        exit(exit_code)
