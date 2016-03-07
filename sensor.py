#!/usr/bin/python

from datetime import datetime
import os
import re
import sys
import yaml


class SensorService:
    def __init__(self):
        path = os.path.dirname(os.path.realpath(__file__)) + '/config.yml'
        self.config = yaml.load(file(path))['sensor']

    def get_list(self):
        sensors = {}
        for key in self.config['devices']:
            sensors[key] = self.__get_sensor(key)

        return sensors

    def get_value(self, device):
        return self.__get_sensor_driver(device).get_value()

    def __get_sensor(self, key):
        device = self.config['devices'][key]

        return {'key': key,
                'address': device['address'],
                'name': device['name'],
                'value': self.get_value(device),
                'when': str(datetime.now())}

    def __get_sensor_driver(self, params):
        if 'w1thermometer' == params['type']:
            return W1Thermometer(self.config['w1thermometer']['base_path'],
                                 params['address'])
        else:
            raise RuntimeError('Unknown sensor driver')


class W1Thermometer:
    def __init__(self, base_path,  address):
        self.address = address
        self.base_path = base_path

    def get_value(self):
        if not os.path.exists(self.base_path + self.address):
            return 'n/a '

        temperature = None
        while temperature is None:
            address = self.base_path + self.address + '/w1_slave'
            sensor = open(address, 'r').read().replace("\n", " ")
            if re.search(r"crc=.* YES", sensor):
                match = re.search(r"t=([0-9\-]+)", sensor)
                temperature = round(float(match.group(1)) / 1000, 1)

        return temperature
