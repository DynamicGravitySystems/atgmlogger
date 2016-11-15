#!/usr/bin/python3.5

import io
import time
import serial
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

    def __init__(self, config= './dgslogger.conf'):
        self.config = config
        self.read_config(self.config)


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
    
    def open_serial(self):
        ser = serial.Serial(
                port = self.port,
                baudrate = self.baudrate,
                parity = self.parity,
                stopbits = self.stopbits,
                bytesize = self.bytesize,
                xonxoff = self.flowcontrol,
                timeout = self.timeout
            )

    def init_logfile(path):
        cdate = datetime.datetime

