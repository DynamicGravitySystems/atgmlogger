#!/usr/bin/python3
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


def sendlines(ser_hdl, lines, rate=1, limit=None):
    count = 0
    try:
        print("Starting sendlines limit = {}".format(limit))

        for line in lines:
            print("Sending: {}".format(line))
            sendline(ser_hdl, line)
            count += 1
            time.sleep(rate)
            if limit and count >= limit:
                print("Limit exceeded, returning count {}".format(count))
    except KeyboardInterrupt:
        print("Sendlines interrupted, total count this iteration: {}".format(count))
        raise KeyboardInterrupt
    #finally:
    #    return count


def run(source, rate, count=-1, repeat=False):
    log = logging.getLogger(__name__)
    log.setLevel(logging.DEBUG)
    std_hdlr = logging.StreamHandler(stream=sys.stdout)
    std_hdlr.setLevel(logging.DEBUG)
    log.addHandler(std_hdlr)

    log.info("Preparing data-source for transmission")
    with open(source, 'r', encoding='utf-8') as data:
        alldata = data.readlines()
    log.info("Data loaded into memory, sample length: {}".format(len(alldata)))
    log.info("Sending line every {} seconds".format(rate))

    send_count = 0
    ser_hdl = get_handle()

    if repeat:
        while True:
            try:
                send_count += sendlines(ser_hdl, alldata, rate=rate)
            except KeyboardInterrupt:
                # This does not give an accurate count yet
                print("Got KI in repeat loop, total count={}".format(send_count))
                break
    else:
        try:
            send_count = sendlines(ser_hdl, alldata, limit=count)
        except KeyboardInterrupt:
            print("Execution finished, total send count= {}".format(send_count))

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
