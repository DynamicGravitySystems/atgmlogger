# -*- coding: utf-8 -*-
# This file is part of ATGMLogger https://github.com/bradyzp/atgmlogger

import json
import logging
from datetime import datetime
from uuid import uuid4

from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient

from . import PluginInterface
from atgmlogger.runconfig import rcParams

LOG = logging.getLogger(__name__)

"""
MQTTClient Plugin (mqtt)

Logger plugin to publish messages to an AWS IoT MQTT Message queue.

Configurations can be applied to this plugin under the 'mqtt' directive in
the configuration json file. See the available options below.
This implementation connects to the AWS IoT device manager via port 8883,
authenticating with a X509 certificate/private-key.

Dependencies
------------
AWSIoTPythonSDK (available from PyPi via pip)

    >>> pip install AWSIoTPythonSDK

Notes
-----
Full line of data is approx 124 bytes, or approx 160 bytes when wrapped with JSON and device metadata

TODO
----
Option to batch send data as Json list of maps (reduce IoT cost if each message < 5kb)
Option to send fraction of data, e.g. send data point every 10 seconds, every minute etc


MQTT Plugin configuration options:
----------------------------------
sensorid : String
    Unique identifier for this device
topicid : String, optional
    Optional topicid to publish messages to, will use sensorid by default
topic_pfx : String, optional
    Optional prefix branch to publish message to, uses gravity by default
endpoint : String
    Required, AWSIoT Endpoint URL
rootca : String
    Optional, path to root CA Certificate for AWS IoT. Relative to the configuration
    path. Defaults to root-CA.crt
prikey : String
    Optional name of private key file for this IoT device. Relative to config path.
    Defaults to iot.private.key    
devcert : String
    Optional name of device certificate (PEM) file for this IoT device. Relative to
    config path. Defaults to iot.cert.pem

"""


def join_cfg(path):
    """Append the application base config directory to given path."""
    return str(rcParams.path.parent.joinpath(path))


def convert_gps_time(gpsweek, gpsweekseconds):
    """
    Converts a GPS time format (weeks + seconds since 6 Jan 1980) to a UNIX
    timestamp (seconds since 1 Jan 1970) without correcting for UTC leap
    seconds.

    Static values gps_delta and gpsweek_cf are defined by the below functions
    (optimization) gps_delta is the time difference (in seconds) between UNIX
    time and GPS time.

    gps_delta = (dt.datetime(1980, 1, 6) - dt.datetime(1970, 1, 1)).total_seconds()

    gpsweek_cf is the coefficient to convert weeks to seconds
    gpsweek_cf = 7 * 24 * 60 * 60  # 604800

    Parameters
    ----------
    gpsweek : int
        Number of weeks since beginning of GPS time (1980-01-06 00:00:00)

    gpsweekseconds : float
        Number of seconds since the GPS week parameter

    Returns
    -------
    float
        UNIX timestamp (number of seconds since 1970-01-01 00:00:00) without
        leapseconds subtracted
    """
    gps_delta = 315964800.0
    gpsweek_cf = 604800
    gps_ticks = (float(gpsweek) * gpsweek_cf) + float(gpsweekseconds)

    return gps_delta + gps_ticks


"""
Marine Data Fields/Sample

$UW,20083,-1369,-940,5104887,252,466,212,4502,400,-24,-16,4430,5128453,39.9092261667,-105.0747506667,0.0040330.9400,20171206173348
$UW,-9696,-7781,4628,4118252,257,409,199,32888,128,73,-42,4362,4139315,39.9092032667,-105.0747801500,0.0000,0.0000,00000000000022


"""


def get_timestamp(fields):
    timestamp = datetime.utcnow().timestamp()
    if len(fields) == 13:
        # Assume Marine data - GPS week/second format
        try:
            week = int(fields[11])
            seconds = float(fields[12])
            timestamp = convert_gps_time(week, seconds)
        except ValueError:
            LOG.exception("Exception resolving timestamp from fields: " + ','.join(fields))
    elif len(fields) == 19:
        # Assume Airborne data - YMD format
        date = str(fields[18])
        fmt = "%Y%m%d%H%M%S"
        try:
            timestamp = datetime.strptime(date, fmt).timestamp()
        except ValueError:
            timestamp = datetime.utcnow().timestamp()

    return timestamp


class MQTTClient(PluginInterface):
    options = ['sensorid', 'topicid', 'topic_pfx', 'endpoint', 'rootca', 'prikey', 'devcert', 'batch', 'interval']
    topic_pfx = 'gravity'
    endpoint = None
    rootca = 'root-CA.crt'
    prikey = 'iot.private.key'
    devcert = 'iot.cert.pem'
    interval = 1

    def __init__(self):
        super().__init__()
        # Set AWSIoTPythonSDK logger level from default
        logging.getLogger('AWSIoTPythonSDK').setLevel(logging.WARNING)
        self.client = None
        self.tick = 0
        self.sensorid = None

    @staticmethod
    def consumer_type() -> set:
        return {str}

    def _batch_process(self):
        # TODO: Implement batch publish feature, perhaps collect items in a queue until a limit is reached
        # then publish as a list of json maps
        sendqueue = []
        limit = 10

    def configure_client(self):
        if self.endpoint is None:
            raise ValueError("No endpoint provided for MQTT Plugin.")
        try:
            self.sensorid = getattr(self, 'sensorid', str(uuid4())[0:8])
            topicid = getattr(self, 'topicid', self.sensorid)

            self.client = AWSIoTMQTTClient(self.sensorid, useWebsocket=False)
            self.client.configureEndpoint(self.endpoint, 8883)
            self.client.configureOfflinePublishQueueing(10000)
            self.client.configureConnectDisconnectTimeout(10)
            self.client.configureCredentials(join_cfg(self.rootca),
                                             join_cfg(self.prikey),
                                             join_cfg(self.devcert))
            self.client.configureDrainingFrequency(2)
            self.client.configureMQTTOperationTimeout(5)
            self.client.connect()

            topic = '/'.join([self.topic_pfx, topicid])
        except AttributeError:
            LOG.exception("Missing attributes from configuration for MQTT plugin.")
            raise
        except:
            LOG.exception("Error running MQTTClient Plugin")
            raise RuntimeError("Error instantiating MQTTClient.")
        return topic

    def run(self):
        topic = self.configure_client()
        while not self.exiting:
            item = self.get(block=True, timeout=None)
            self.tick += 1
            if item is None or item == "" or self.tick % self.interval:
                self.task_done()
                continue
            else:
                try:
                    self.tick = 0  # reset tick count
                    fields = item.split(',')
                    timestamp = get_timestamp(fields)
                    if len(fields):
                        gravity = fields[1]
                    else:
                        gravity = 0

                    small_data = ','.join([str(gravity)])

                    item_json = json.dumps({'d': self.sensorid, 't': timestamp, 'v': small_data})
                    # Note: returns bool value on success/fail of publish
                    self.client.publish(topic, item_json, 0)
                    self.task_done()
                except:
                    LOG.exception("Exception occured in mqtt-run loop. Item value: %s", item)

        self.client.disconnect()


__plugin__ = MQTTClient
