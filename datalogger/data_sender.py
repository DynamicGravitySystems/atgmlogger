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
            print("Sending data via comport: {}".format(device))
        except serial.SerialException:
            print('Error determining port to open')
            return 1
    serial_hdl = serial.Serial(port=device, baudrate=baudrate, stopbits=serial.STOPBITS_ONE,
                               parity=serial.PARITY_NONE)
    return serial_hdl


def run(source, rate=.1):
    data = open(source, 'r', encoding='utf-8')
    send_count = 0
    ser_hdl = get_handle()
    line = data.readline()
    while line is not '':
        try:
            print("sending line: {}".format(line))
            sendline(ser_hdl, line)
            send_count +=1
            time.sleep(rate)
            line = data.readline()
        except KeyboardInterrupt:
            print("\nInterrupted - Total sent: {}".format(send_count))
            print("Cleaning up and exiting")
            sendline(ser_hdl, '\n')
            ser_hdl.close()
            return 0
    sendline(ser_hdl, '\n')
    print("Total Sent: {}".format(send_count))
    print("Exhausted data, exiting")
    ser_hdl.close()

def main(argv=None):
    parser = argparse.ArgumentParser(prog="SerialSender", description="Send arbitrary data over a serial port")






if __name__ == "__main__":
    run('data.txt')

