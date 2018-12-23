# -*- coding: utf-8 -*-
import logging
from datetime import datetime
from json import JSONDecodeError
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import ConnectionError
from urllib3 import Retry

from . import PluginInterface


__plugin__ = 'HTTPSender'

LOG = logging.getLogger(__name__)


_marine_fieldmap = ['header', 'gravity', 'long_acc', 'cross_acc', 'beam',
                    's_temperature', 'pressure', 'e_temperature',
                    'vcc', 've', 'al', 'ax', 'status', 'checksum',
                    'latitude', 'longitude', 'speed', 'course', 'datetime']


def convert_time(meter_time):
    fmt = '%Y%m%d%H%M%S'
    try:
        return datetime.strptime(meter_time, fmt).timestamp()
    except ValueError:
        return datetime.utcnow().timestamp()


class HTTPSender(PluginInterface):
    options = ['sensorname', 'apikey', 'endpoint']
    sensorname = 'AT1X-0'
    sensortype = 'AT1M'
    apikey = 'invalid'
    lineheader = '$UW'
    endpoint = 'http://dgs-collector.dynamicgravitysystems.com/'
    fields = ['gravity', 'long_acc', 'cross_acc', 'beam', 'pressure',
              'e_temperature', 's_temperature', 'latitude', 'longitude',
              'datetime']
    _field_casts = {
        'header': str,
        'latitude': float,
        'longitude': float,
        'speed': float,
        'course': float,
        'datetime': convert_time
    }

    def __init__(self):
        super().__init__()

    @classmethod
    def _extract_fields(cls, data: str, fieldmap=None):
        if fieldmap is None:
            fieldmap = _marine_fieldmap
        extracted = {}
        data = data.split(',')
        if not len(data) == len(fieldmap):
            LOG.error("Data and field-map lengths do not match.\nData: {data}".format(data=data))
            return None
        for i, field in enumerate(fieldmap):
            if field.lower() in cls.fields:
                try:
                    extracted[field] = cls._field_casts.get(field.lower(), int)(data[i])
                except ValueError:
                    extracted[field] = data[i]
                except IndexError:
                    return None
        return extracted

    @staticmethod
    def consumer_type() -> set:
        return {str}

    def _handshake(self, session: requests.Session) -> int:
        url = urljoin(self.endpoint, '/sensor/{}'.format(self.sensorname))
        try:
            resp = session.get(url)
        except ConnectionError:
            LOG.warning("Unable to connect to endpoint")
            return -1

        if resp.status_code == 200:
            data: dict = resp.json()
            if data.get("Valid", False):
                sensor_id = data.get('SensorID', -1)
                LOG.debug("Got Sensor ID {} from server".format(sensor_id))
                return sensor_id
            else:
                LOG.debug("Sensor is not valid, attempting to create registration")
                return self._register_sensor(session)
        else:
            LOG.debug("Error connecting to server, status code: {}".format(resp.status_code))
            return -1

    def _register_sensor(self, session: requests.Session) -> int:
        """Attempt to register a new Sensor with the server"""

        # TODO: Add configuration payload here
        url = urljoin(self.endpoint,
                      '/sensor/{sname}?type={stype}'.format(
                          sname=self.sensorname, stype=self.sensortype))
        try:
            resp = session.post(url)
            data = resp.json()
            return data.get('SensorID', -1)
        except ConnectionError:
            LOG.warning("Unable to connect to sensor endpoint")
            return -1
        except JSONDecodeError:
            LOG.exception("Error decoding JSON response")
            return -1

    def _send_line(self, session: requests.Session, dest_uri, line_json):
        try:
            resp = session.post(dest_uri, json=line_json)
            return resp.json()
        except ConnectionError:
            LOG.error("Couldn't connect, exhausted max retries")
            return {'Status': 'FAIL', 'Reason': 'Max Retries Exhausted'}
        except JSONDecodeError:
            return {'Status': 'FAIL', 'Reason': 'JSONDecodeError'}

    def run(self):
        # NOTE: HTTP Sender only suitable for <= 1Hz data collection
        session = requests.Session()
        session.headers.update({'Authorization': 'Bearer: {key}'.format(key=self.apikey)})
        retries = Retry(total=2, backoff_factor=1, status_forcelist=[502, 503, 504])
        session.mount('http://', HTTPAdapter(max_retries=retries))
        session.mount('https://', HTTPAdapter(max_retries=retries))

        sid = -1
        while sid == -1:
            sid = self._handshake(session)

        collector_uri = urljoin(self.endpoint, '/collect/{sid}'.format(sid=sid))

        backlog = []
        while not self.exiting:
            item: str = self.get(block=True, timeout=None)
            if not item.startswith(self.lineheader):
                LOG.error("Invalid data line received, skipping: %s", item)
                self.task_done()
                continue

            data = self._extract_fields(item)
            if data is None:
                continue

            if len(backlog):
                pass

            resp = self._send_line(session, collector_uri, data)
            if resp.get('Status', 'FAIL') == 'OK':
                self.task_done()
                LOG.info("Send Status: {}, ID: {}".format(resp.get("Status"), resp.get('LineID', -1)))
            else:
                LOG.warning("Send line failed")
                LOG.warning(resp)

        if not self.exiting:
            LOG.error("HTTPSender unexpectedly exited.")
        else:
            LOG.info("HTTPSender exiting on exit signal.")

