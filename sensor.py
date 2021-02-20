#!/usr/bin/python

from datetime import datetime
import json
import logging
import os
import re
import redis
import yaml


class SensorService:
    def __init__(self):
        path = os.path.dirname(os.path.realpath(__file__)) + '/config.yml'
        self.config = yaml.load(open(path), Loader=yaml.FullLoader)['sensor']

    def get_list(self, with_readings=True):
        sensors = {}
        for key in self.config['devices']:
            sensors[key] = self.get_sensor_data(key, with_readings)

        return sensors

    def get_sensor_data(self, key, with_readings=True):
        device = self.config['devices'][key]
        sensor = {
            'key': key,
            'address': device['address'],
            'name': device['name'],
        }
        if with_readings:
            sensor.update(self.get_value(device))
        
        return sensor

    def get_value(self, device):
        return self.__get_sensor_driver(device).get_value()

    def __get_sensor_driver(self, params):
        if 'w1thermometer' == params['type']:
            return W1Thermometer(self.config['w1thermometer']['base_path'],
                                 params['address'])
        if 'mqtt' == params['type']:
            return MqttThermometer(params['address'])
        else:
            raise RuntimeError('Unknown sensor driver')


class W1Thermometer:
    def __init__(self, base_path,  address):
        self.address = address
        self.base_path = base_path

    def get_value(self):
        if not os.path.exists(self.base_path + self.address):
            return 'n/a'

        temperature = None
        while temperature is None:
            address = self.base_path + self.address + '/w1_slave'
            sensor = open(address, 'r').read().replace("\n", " ")
            if re.search(r"crc=.* YES", sensor):
                match = re.search(r"t=([0-9\-]+)", sensor)
                temperature = round(float(match.group(1)) / 1000, 1)

        return {
            'value': temperature,
            'linkquality': None,
            'battery': None,
            'humidity': None,
            'when': str(datetime.now())
        }


class MqttThermometer:
    def __init__(self,  address):
        self.address = address
        self.redis = redis.StrictRedis(host='localhost', port=6379, db=0)

    def get_value(self):
        json_text = self.redis.lrange(self.address, 0, 0)
        data  = json.loads(json_text[0] if len(json_text) > 0 else '""')

        if not json_text or not data:
            return 'n/a'

        return {
            'value': round(data['payload']['temperature'], 1),
            'linkquality': data['payload']['linkquality'],
            'battery': data['payload']['battery'],
            'humidity': round(data['payload']['humidity']),
            'when': str(datetime.fromtimestamp(data['tst']))
        }
