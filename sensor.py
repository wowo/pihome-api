#!/usr/bin/python3

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

    def get_list(self, with_readings=True, from_cache=False):
        sensors = {}
        for key in self.config['devices']:
            sensors[key] = self.get_sensor_data(key, with_readings, from_cache)

        return sensors

    def get_sensor_data(self, key, with_readings=True, from_cache=False):
        device = self.config['devices'][key]
        sensor = {
            'key': key,
            'address': device['address'],
            'name': device['name'],
            'type': device['type'],
            'collection': device['collection']
        }
        if with_readings:
            sensor.update(self.get_value(device, from_cache))
        
        return sensor

    def get_value(self, device, from_cache):
        if from_cache:
            return self.__get_sensor_driver(device).get_cached_value()
        else:
            return self.__get_sensor_driver(device).get_value()

    def __get_sensor_driver(self, params):
        if 'w1thermometer' == params['type']:
            return W1Thermometer(self.config['w1thermometer']['base_path'],
                                 params['address'])
        if 'mqtt_temperature' == params['type']:
            return MqttThermometer(params['address'])
        if 'mqtt_light' == params['type']:
            return MqttLight(params['address'])
        else:
            raise RuntimeError('Unknown sensor driver')


class CachedSensor(object):
    def __init__(self, cache_key):
        self.cache_key = cache_key
        self.redis = redis.StrictRedis(host='localhost', port=6379, db=0)

    def get_unit(self):
        return ''

    def get_respose_from_data(self, data):
        return {
            'value': round(data['value'], 1),
            'linkquality': data['linkquality'] if 'linkquality' in data else 0,
            'battery': data['battery'] if 'battery' in data else 0,
            'unit': self.get_unit(),
            'when': data['when']
        }

    def get_from_cache(self):
        json_text = self.redis.lrange(self.cache_key, 0, 0)
        data  = json.loads(json_text[0] if len(json_text) > 0 else '""')

        if not json_text or not data:
            return {
                'value': 'n/a',
                'when': str(datetime.fromtimestamp(data['when']))
            }
        return self.get_respose_from_data(data)



class W1Thermometer(CachedSensor):
    def __init__(self, base_path, address):
        self.address = address
        self.base_path = base_path
        CachedSensor.__init__(self, 'w1thermometer_' + address)

    def get_unit(self):
        return u'\N{DEGREE SIGN}C'

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
            'unit': self.get_unit(),
            'linkquality': None,
            'battery': None,
            'humidity': None,
            'when': str(datetime.now())
        }

    def get_cached_value(self):
        return self.get_from_cache()

class MqttThermometer(CachedSensor):
    def __init__(self, address):
        CachedSensor.__init__(self, address)

    def get_cached_value(self):
        return self.get_from_cache()

    def get_value(self):
        return self.get_from_cache()

    def get_unit(self):
        return u'\N{DEGREE SIGN}C'

    def get_respose_from_data(self, data):
        response  = super().get_respose_from_data(data)
        response['humidity'] =  data['humidity'] if 'humidity' in data else 0
        return response

class MqttLight(CachedSensor):
    def __init__(self, address):
        CachedSensor.__init__(self, address)

    def get_cached_value(self):
        return self.get_from_cache()

    def get_value(self):
        return self.get_from_cache()

    def get_unit(self):
        return ' lx'

    def get_respose_from_data(self, data):
        response  = super().get_respose_from_data(data)
        response['illuminance'] =  data['illuminance'] if 'illuminance' in data else 0
        response['illuminance_lux'] =  data['illuminance_lux'] if 'illuminance_lux' in data else 0
        return response
