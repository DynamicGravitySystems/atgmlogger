# -*- coding: utf-8 -*-

import json
import logging
from datetime import datetime
from uuid import uuid4
from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient
from . import PluginInterface
from .. import APPLOG
from atgmlogger.runconfig import rcParams


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
    return str(rcParams.path.parent.joinpath(path))


class MQTTClient(PluginInterface):
    options = ['sensorid', 'topicid', 'topic_pfx', 'endpoint', 'rootca', 'prikey', 'devcert']
    topic_pfx = 'gravity'
    endpoint = None
    rootca = 'root-CA.crt'
    prikey = 'iot.private.key'
    devcert = 'iot.cert.pem'

    def __init__(self):
        super().__init__()
        # Set AWSIoTPythonSDK logger level from default
        logging.getLogger('AWSIoTPythonSDK').setLevel(logging.WARNING)
        self.client = None

    @staticmethod
    def consumer_type() -> set:
        return {str}

    def run(self):
        if self.endpoint is None:
            raise ValueError("No endpoint provided for MQTT Plugin.")

        try:
            sensorid = getattr(self, 'sensorid', str(uuid4())[0:8])
            topicid = getattr(self, 'topicid', sensorid)

            self.client = AWSIoTMQTTClient(sensorid, useWebsocket=False)
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
            APPLOG.exception("Missing attributes from configuration for MQTT plugin.")
            raise
        except:
            APPLOG.exception("Error running MQTTClient Plugin")
            raise RuntimeError("Error instantiating MQTTClient.")

        while not self.exiting:
            item = self.get(block=True, timeout=None)
            if item is None:
                self.task_done()
                continue
            else:
                fields = item.split(',')
                timestamp = datetime.utcnow().timestamp()
                if len(fields) == 13:
                    # Assume marine data gps week/second format
                    week = int(fields[11])
                    seconds = float(fields[12])
                    gravity = float(fields[1])

                    # TODO: Need to do gps conversion
                elif len(fields) == 19:
                    # Assume airborne data - YMD format
                    date = str(fields[18])
                    gravity = float(fields[1])
                    fmt = "%Y%m%d%H%M%S"
                    try:
                        timestamp = datetime.strptime(date, fmt).timestamp()
                    except ValueError:
                        timestamp = datetime.utcnow().timestamp()
                else:
                    gravity = fields[1]

                small_data = ','.join([str(gravity), str(timestamp)])

                item_json = json.dumps({'d': sensorid, 'v': small_data})
                # Returns bool value on success/fail of publish
                response = self.client.publish(topic, item_json, 0)
                self.task_done()

        self.client.disconnect()


__plugin__ = MQTTClient
