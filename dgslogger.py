#!/usr/bin/python3.5

import io
import os.path
import sys
import time
import serial
import logging
import logging.handlers
import datetime
import configparser

class SerialRecorder:
    """Record all data from a serial port and log it to a rotating file
    
   Designed as a backup system to run on a Raspberry Pi computer, utilizing pySerial
   to access a hardware serial port and record all data via pythons logging class.
   
    Expected input is line delimited ASCII data from an AT1X Gravity Meter
    Input format is unimportant however, this class is designed to log data
    without modification, to a text file on the system; for retrieval in the
    event of the primary controller malfunction.

    Configuration is accomplished via the .dgslogger config file by specifying
    properties in the [SERIAL] and [DATA] sections:
    e.g.
    ----------------------------
    [SERIAL]
    port = ttyS0
    baudrate = 57600
    parity = none
    stopbits = 1
    timeout = 0

    [DATA]
    logdir = /var/log/dgslogger
    meterid = AT1X-TEST
    log_interval = 1d
    ----------------------------
    Where port = the serial device name on the local system (use: dmesg | grep tty)
    and the other [SERIAL] fields should correspond to the meter settings.
    
    Defaults should work without modification for the current AT1X meters
    """

    port = None
    baudrate = 57600
    parity = serial.PARITY_NONE
    stopbits = serial.STOPBITS_ONE
    bytesize = serial.EIGHTBITS
    flowcontrol = False
    timeout = None

    #TODO: Allow overwrite via config file
    logformat = '%(levelname)s:%(name)s:%(asctime)s -> %(message)s'
    logdatefmt = '%Y-%m-%d %H:%M:%S'

    def __init__(self, config='.dgslogger'):
        self.start_applog()
        try:
            self.read_config(config)
        except FileNotFoundError as err:
            self.log.exception("Configuration file not found")
            #Try to set using defaults
            self.set_default_port()
        self.start_datalog()

    def set_default_port(self):
        import serial.tools.list_ports
        try:
            self.port = serial.tools.list_ports.comports()[0].name
        except IndexError:
            #Log exception and exit as we cannot continue without serial port
            self.log.exception("No serial port available")
            sys.exit()

    def start_applog(self):
        """
        Initializes the application log (self.log)
        
        Application log is designed to log application data e.g. start/stop actions,
        exceptions, errors etc.
        """

        logfilename = 'debug.log'
        loglevel = logging.DEBUG

        self.log = logging.getLogger(__name__)
        self.log.setLevel(logging.DEBUG)

        formatter = logging.Formatter(fmt=self.logformat, 
                datefmt=self.logdatefmt)

        sh = logging.StreamHandler(sys.stdout)
        sh.setLevel(logging.WARNING)
        sh.setFormatter(formatter)
        self.log.addHandler(sh)

        self.trfh = logging.handlers.TimedRotatingFileHandler(logfilename, when='midnight', interval=1,
                backupCount=31)
        self.trfh.setLevel(loglevel)
        self.trfh.setFormatter(formatter)
        self.log.addHandler(self.trfh)
        self.log.info('Initialized Application Log')

    def start_datalog(self):
        """
        Initializes the data logger (self.datalogger)

        The Data Logger is used to record data from the serial stream, and also uses a 
        TimedRotatingFileHandler to control the rotation of logfiles and deletion
        of stale historical logs
        """

        self.datalogger = logging.getLogger('DataLogger')
        self.datalogger.setLevel(logging.INFO)
        dataHandler = logging.handlers.TimedRotatingFileHandler('data/sensordata.dat', when='H', interval=6,
                backupCount = 31)
        dataFormatter = logging.Formatter(fmt = '%(message)s')
        dataHandler.setFormatter(dataFormatter)
        self.datalogger.addHandler(dataHandler)


    def read_config(self, fconfig):
        config = configparser.ConfigParser()
        if not os.path.isfile(fconfig):
            raise FileNotFoundError(fconfig)
            return

        config.read(fconfig)
        self.log.info('Configuration read from: ' + os.path.abspath(fconfig)) 
        self.port = config['SERIAL']['port']
        self.baudrate = config.getint('SERIAL', 'baudrate')

        #Map string values to serial class constant
        parity_map = {'none' : serial.PARITY_NONE,
                      'even' : serial.PARITY_EVEN,
                      'odd' : serial.PARITY_ODD,
                      'mark' : serial.PARITY_MARK,
                      'space' : serial.PARITY_SPACE
                        }
        self.parity = parity_map[(config['SERIAL']['parity']).lower()]

        stopbits_map = {'1' : serial.STOPBITS_ONE,
                '1.5' : serial.STOPBITS_ONE_POINT_FIVE,
                '2' : serial.STOPBITS_TWO
                }
        self.stopbits = stopbits_map[config['SERIAL']['stopbits']]
        
        #TODO: Implement use of these paths in start_datalog
        self.logdir = config['DATA']['logdir']
        self.meterid = config['DATA']['meterid']
        
    def set_serial(self):
        """Generates a dictionary of serial port paramaters""" 
        self.serialconfig = {
                'port' : self.port, 'baudrate' : self.baudrate,
                'parity' : self.parity, 'stopbits' : self.stopbits,
                'bytesize' : self.bytesize, 'xonxoff' : self.flowcontrol,
                'timeout' : self.timeout
                }
        return self.serialconfig

    def start(self):

        with serial.Serial(**self.serialconfig) as ser:
            while True:
                line = ser.readline()
                self.datalogger.info(line)


    def init_logfile(path):
        cdate = datetime.datetime


    def __del__(self):
        self.log.info('Exiting dgslogger and shutting down logging')
        logging.shutdown()


if __name__ == "__main__":
    recorder = SerialRecorder()



