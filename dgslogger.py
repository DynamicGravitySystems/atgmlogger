#!/usr/bin/python3.5

import io
import sys
import time
import serial
import logging
import logging.handlers
import datetime
import configparser

class SerialRecorder:
    port = None
    baudrate = 57600
    parity = serial.PARITY_NONE
    stopbits = serial.STOPBITS_ONE
    bytesize = serial.EIGHTBITS
    flowcontrol = False
    timeout = None

    logformat = '%(levelname)s:%(name)s:%(asctime)s -> %(message)s'
    logdatefmt = '%Y-%m-%d %H:%M:%S'

    def __init__(self, config='.dgslogger'):
        try:
            self.read_config(config)
        except ValueError:
            print('Error opening configuration file')

        self.setup_logging()

    def setup_logging(self):
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

        #fh = logging.FileHandler('debug.log')
        #fh.setLevel(loglevel)
        #fh.setFormatter(formatter)
        #self.log.addHandler(fh)
        self.log.info('Initializing DGS log')

        self.datalogger = logging.getLogger('DataLogger')
        self.datalogger.setLevel(logging.INFO)
        dataHandler = logging.handlers.TimedRotatingFileHandler('data/sensordata.dat', when='H', interval=6,
                backupCount = 31)
        dataFormatter = logging.Formatter(fmt = '%(message)s')
        dataHandler.setFormatter(dataFormatter)
        self.datalogger.addHandler(dataHandler)


    def read_config(self, fconfig):
        config = configparser.ConfigParser()
        config.read(fconfig)
        
        self.port = config['SERIAL']['port']
        self.baudrate = config.getint('SERIAL', 'baudrate')

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

        self.logdir = config['DATA']['logdir']
        self.meterid = config['DATA']['meterid']
        
        self.serialconfig = {
                'port' : self.port, 'baudrate' : self.baudrate,
                'parity' : self.parity, 'stopbits' : self.stopbits,
                'bytesize' : self.bytesize, 'xonxoff' : self.flowcontrol,
                'timeout' : self.timeout
                }

    def start(self):
        #Test for port existence

        #if os.path.isfile(os.path.join('/dev', self.port)


        with serial.Serial(**self.serialconfig) as ser:
            while True:
                line = ser.readline()
                self.datalogger.info(line)


    def init_logfile(path):
        cdate = datetime.datetime


    def __del__(self):
        #self.log.debug('Exiting and shutting down logging')
        self.trfh.close()
        self.log.removeHandler(self.trfh)
        logging.shutdown()


if __name__ == '__main__':
    recorder = SerialRecorder()



