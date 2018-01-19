#!/usr/bin/python3
# coding: utf-8

import time
import sys
import logging
import itertools
import argparse
from pathlib import Path
from typing import List

import serial
from serial.tools.list_ports import comports


_log = logging.getLogger(__name__)
_log.setLevel(logging.DEBUG)

ENCODING = 'latin-1'
AT1Baud = 57600


def get_at1_handle(device=None, read_timeout=1):
    """Open a serial handle with parameter set to emulate AT1 Gravity Meter
    serial data flow.

    Parameters
    ----------
    device : str, optional
        Specify serial/usb device path. Else the path will be automatically
        determined.

    read_timeout : int, optional
        Specify read timeout for serial handle

    """

    device = device or comports()[0].device
    _log.debug("Selected serial device: {}".format(device))

    handle = serial.Serial(port=device, baudrate=AT1Baud,
                           stopbits=serial.STOPBITS_ONE,
                           parity=serial.PARITY_NONE,
                           timeout=read_timeout)
    return handle


def send(handle, data: List, interval=1.0, count=None,
         repeat=False, copy_output=None):
    """

    Parameters
    ----------
    handle :
        Serial or function handle with callable attribute write(str)
    data
    interval : float, Optional
        Specify interval to sleep between sending data line, default 1.0 seconds
    count : int
        If int specified, send lines until count is reached
    repeat : bool, Optional
        If True, input data will be sent and cycled endlessly
    copy_output : Callable, Optional
        Not yet implemented.
        When sending data via handle, send additional identical copy to
        copy_output.

    Returns
    -------
    int : status code

    """
    if repeat:
        data = itertools.cycle(data)
    else:
        # Convert list to generator (allows use of next())
        data = (line for line in data)

    send_count = 0
    while True:
        if count is not None and count >= send_count:
            _log.info("Send Count reached, exiting main loop.")
            break

        try:
            line = next(data)  # type: str
        except StopIteration:
            _log.info("Data source exhausted, {} lines sent.".format(send_count))
            break
        enc_line = line.encode(ENCODING)
        handle.write(enc_line)
        send_count += 1
        time.sleep(interval)

    _log.info("Exiting send loop. # Lines Sent: {}".format(send_count))
    return send_count


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        prog="send", description="Send arbitrary data over a serial port")
    parser.add_argument('-c', '--count', type=int, default=None)
    parser.add_argument('-r', '--repeat', action='store_true')
    parser.add_argument('-i', '--interval', type=float, default=1.0)
    parser.add_argument('-f', '--file', required=True)

    opts = parser.parse_args(sys.argv[1:])

    hdl = get_at1_handle()

    path = Path(opts.file)
    if not path.exists():
        _log.error("Invalid file path specified. {} does not exist."
                   .format(str(path)))
        sys.exit(1)

    contents = None
    with path.open('r') as fd:
        contents = fd.readlines()
    if not len(contents):
        _log.error("Input file contains no data.")
        sys.exit(1)

    res = send(hdl, data=contents, interval=opts.interval, count=opts.count)
    print("send completed, result: ", res)
