# coding=utf-8

import time
import argparse
import sys
import logging
import logging.handlers

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


def run(source, rate, count=0, repeat=False):
    log = logging.getLogger(__name__)
    log.setLevel(logging.DEBUG)
    std_hdlr = logging.StreamHandler(stream=sys.stdout)
    std_hdlr.setLevel(logging.DEBUG)
    log.addHandler(std_hdlr)

    log.info("Preparing data-source for transmission")
    data = open(source, 'r', encoding='utf-8')
    alldata = data.readlines()
    data.close()
    log.info("Data loaded into memory")
    log.info("Sending line every {} seconds".format(rate))

    if count == 0:
        count = len(alldata)

    send_count = 0
    ser_hdl = get_handle()

    if repeat:
        while True:
            for line in alldata:
                pass
    else:
        for line in alldata:
            if send_count >= count:
                break
            try:
                sendline(ser_hdl, line)
                send_count += 1
                time.sleep(rate)
            except KeyboardInterrupt:
                print("Execution interrupted - total lines sent: {}".format(send_count))
                sendline(ser_hdl, '\n\n')
                ser_hdl.close()
                return 0
        print("Exhausted Data, total sent: {}".format(send_count))

    ser_hdl.close()


def main(argv=None):
    parser = argparse.ArgumentParser(prog="SendUtil", description="Send arbitrary data over a serial port")
    parser.add_argument('-c', '--count', type=int, default=0)
    parser.add_argument('-r', '--repeat', action='store_true')
    parser.add_argument('-i', '--interval', type=float, default=1)
    parser.add_argument('-f', '--file', required=True)

    opts = parser.parse_args(argv[1:])
    if opts.repeat:
        print("Sending data forever")

    run(opts.file, opts.interval, opts.count, opts.repeat)


if __name__ == "__main__":
    main(sys.argv)
