import unittest
import unittest.mock as mock
import SerialLogger
import logging
import tempfile
import yaml
import uuid
import shutil
import sys
import os
import zipfile
import tarfile
import time


class TestSerialLogger(unittest.TestCase):
    def setUp(self):
        self.sl = SerialLogger.SerialLogger
        self.sl_args = ['test.py', '-vvv', '--logdir=./logs']
        self.rsh = SerialLogger.RemovableStorageHandler
        self.rsh_args = []
        self.basedir = os.getcwd()

    @classmethod
    def tearDownClass(cls):
        logging.shutdown()
        shutil.rmtree('./logs')
        shutil.rmtree('./device')

    def test_level_filter(self):
        lvl_filter = SerialLogger.level_filter(60)
        data_record = logging.makeLogRecord({'name': 'test_level_filter',
                                        'levelno': 60,
                                        'msg': 'line of data at level 60'})
        info_record = logging.makeLogRecord({'name': 'test_level_filter',
                                             'levelno': int(logging.INFO),
                                             'msg': 'informational message'})
        self.assertFalse(lvl_filter(data_record))
        self.assertTrue(lvl_filter(info_record))

    def test_set_verbosity(self):
        result = self.sl.set_verbosity(4, lvlmax=3)
        self.assertEqual(result, 3)
        result = self.sl.set_verbosity(-1)
        self.assertEqual(result, 0)
        result = self.sl.set_verbosity(None)
        self.assertEqual(result, 0)

    def test_load_config(self):
        """Test static method load_config()"""
        config = 'logging.yaml'
        with open(config, 'r') as source:
            src_yaml = yaml.load(source)
        result = self.sl.load_config(config)
        self.assertDictEqual(src_yaml, result)

        test_empty = self.sl.load_config('nonexistant.yaml')
        self.assertIsNone(test_empty)

        test_defaults = self.sl.load_config('nonexistant.yaml', default_opts={
            'version': 0.2,
            'usb': {'mount': '/media/removable', 'poll_int': 3, 'copy_level': 'all'}
        })
        self.assertEqual(test_defaults['version'], 0.2)
        self.assertEqual(test_defaults['usb']['poll_int'], 3)

    def test_decode(self):
        """Test static method decode()"""
        raw_data = bytes('abcd!%*\t\r\n', encoding='latin_1')
        raw_data += bytes(chr(255), encoding='latin_1')
        raw_data += bytes(chr(0), encoding='latin_1')
        self.assertIsInstance(raw_data, bytes)
        result = self.sl.decode(raw_data)
        self.assertEqual(result, 'abcd!%*')
        self.assertIsInstance(result, str)

    def test_SerialLogger_init(self):
        # Can't capture logging output here as the init function initializes logging
        inst = SerialLogger.SerialLogger(self.sl_args)
        self.assertEqual('./logs', inst.logdir)

    def test_init_logging(self):
        pass

    def test_RSH_copy_logs(self):
        paths = './logs', './device'
        for path in paths:
            if not os.path.exists(path):
                os.mkdir(path)
        u = self.rsh(*paths, None, None, verbosity=3)
        u.copy_logs()

    def test_write(self):
        """Test RemovableStorageHandler static Write utility"""
        write = self.rsh.write
        dest = './device/test_write.txt'
        write(dest, 'hello this is line 1', 'this is line 2', customkey='blargl')
        with open(dest, 'r') as fd:
            self.assertEqual(fd.readline(), 'hello this is line 1\n')
            self.assertEqual(fd.readline(), 'this is line 2\n')
            self.assertEqual(fd.readline(), 'customkey: blargl\n')

    @unittest.skipIf(sys.platform.startswith('win'), "Tested function not supported on windows.")
    def test_run_diag(self):
        inst = SerialLogger.RemovableStorageHandler('.', '.', None, None, verbosity=3)
        inst.run_diag()

    def test_watch_files(self):
        if not os.path.exists('./device'):
            os.mkdir('./device')
        with self.assertLogs(level=logging.INFO) as al:
            rsh = SerialLogger.RemovableStorageHandler('.', './device', None, None, verbosity=3)
            self.assertEqual(al.output, ['INFO:root:RemovableStorageHandler Initialized'])

        triggers = ['logging.yml', 'dgsdiag', 'dgsdiag.txt', 'false_trigger']
        # Generate trigger files to test
        for trigger in triggers:
            with open(os.path.join('./device', trigger), 'w') as fd:
                fd.write('')
                fd.flush()
        try:
            # Suppress expected logging on windows
            if sys.platform.startswith('win'):
                with self.assertLogs(level=logging.INFO):
                    res = rsh.watch_files()
            else:
                res = rsh.watch_files()
        except NotImplementedError:
            print("Function not implemented in watch_files")

    def test_compress_files(self):
        # Test zipfile creation
        with tempfile.TemporaryDirectory() as temp:
            for i in range(5):
                fd = open(os.path.join(temp, str(uuid.uuid4()) + '.ext'), 'w')
                fd.write('Contents of file ' + str(i))
                fd.close()

            files = [os.path.abspath(file.path) for file in os.scandir(temp) if file.is_file()]

            fnames = [os.path.basename(file) for file in files]
            for comp_mode in ['bzip', 'lzma']:
                ziparc_path = SerialLogger.RemovableStorageHandler._compress(temp, *files, compression=comp_mode)
                with zipfile.ZipFile(ziparc_path) as zf:
                    zipfiles = zf.namelist()
                tararc_path = SerialLogger.RemovableStorageHandler._compress(temp, *files, method='tar',
                                                                             compression=comp_mode)
                tf = tarfile.open(tararc_path, 'r')
                tarfiles = tf.getnames()
                tf.close()

                self.assertListEqual(fnames, zipfiles)
                self.assertListEqual(fnames, tarfiles)

    def test_gpio_handler_exit(self):
        config = {'data_led': 5, 'usb_led': 6, 'aux_led': 7}
        SerialLogger.gpio = mock.NonCallableMock()
        gph = SerialLogger.GpioHandler(config, verbose=True)
        gph.start()
        self.assertTrue(gph.is_alive())
        with self.assertLogs(level=logging.INFO):
            gph.exit(join=True)
        self.assertFalse(gph.is_alive())

    def test_gpio_handler_signal(self):
        gpio = mock.NonCallableMock()
        gpio.output = mock.Mock()
        SerialLogger.gpio = gpio
        config = {'data_led': 5, 'usb_led': 6, 'aux_led': 7, 'mode': 'board'}
        gph = SerialLogger.GpioHandler(config, verbose=True)
        try:
            gph.start()
            gph.blink(14, 2)
            time.sleep(.1)
            gpio.output.assert_any_call(14, True)

            # print("Turning on led 23 until stopped")
            gph.blink(23, -1, force=True)
            time.sleep(.1)
            gpio.output.assert_any_call(23, True)

            # print("Trying to blink 99 once")
            gph.blink(99, force=True)
            time.sleep(.1)
            gpio.output.assert_any_call(99, True)
            with self.assertLogs(level=logging.INFO):
                gph.exit(join=True)
            self.assertFalse(gph.is_alive())
        except AssertionError:
            raise
        finally:
            gph.exit(join=True)

