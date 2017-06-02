# coding=utf-8

import time
import os

import serial
from serial.tools.list_ports import comports

# Utility to send data over serial for testing.


def sendline(serial_hdl, data):
    enc_data = data.encode('latin-1')
    return serial_hdl.write(enc_data)


def get_handle(device=None, baudrate=57600):
    if device is None:
        try:
            device = comports()[0].device
        except serial.SerialException:
            print('Error determining port to open')
            return 1
    serial_hdl = serial.Serial(port=device, baudrate=baudrate, stopbits=serial.STOPBITS_ONE,
                               parity=serial.PARITY_NONE)
    return serial_hdl


def run(source, rate=1):
    data = open(source, 'r', encoding='utf-8')
    ser_hdl = get_handle()
    line = data.readline()
    while line is not '':
        print("sending line: {}".format(line))
        sendline(ser_hdl, line)
        time.sleep(rate)
        line = data.readline()
    sendline(ser_hdl, '\n')
    print("Exhausted data")
    ser_hdl.close()

if __name__ == "__main__":
    run('data.txt')

