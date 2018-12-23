# -*- coding: utf-8 -*-

from atgmlogger.plugins.mqtt import MQTTClient as client

data = '$UW,20083,-1369,-940,5104887,252,466,212,4502,400,-24,-16,4430,5128453,39.9092261667,-105.0747506667,' \
       '0.0040330.9400,20171206173348'


def test_extract_fields_ordered():
    client.fields = ['gravity', 'long', 'cross']

    expected = {"gravity": 20083, "long": -1369, "cross": -940}

    extracted = client.extract_fields(data)

    assert expected == extracted


def test_extract_fields_unordered():
    client.fields = ['long', 'longitude', 'cross', 'latitude', 'gravity']
    expected = {'gravity': 20083, 'long': -1369, 'cross': -940, 'latitude': 39.9092261667, 'longitude':
                -105.0747506667}
    result = client.extract_fields(data)

    assert expected == result
