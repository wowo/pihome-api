#!/usr/bin/python

from celery.task.control import inspect
from celery.task.control import revoke
from datetime import datetime, timedelta
from xml.dom.minidom import parseString
import json
import memcache
import os
import pika
import urllib2
import yaml

class SwitchService:
    def __init__(self):
        self.config = yaml.load(file(os.path.dirname(os.path.realpath(__file__)) + '/config.yml'))['switch']
        self.cache = memcache.Client(['localhost:11211'], debug=0)
        self.__schedule = None
        self.__revoked = None


    def get_list(self, fresh):
        switches = {}
        for key in self.config['devices']:
            if fresh:
                self.cache.delete(key)
            switches[key] = self.__get_switch(str(key))

        return switches


    def get_state(self, device):
        return self.__get_switch_driver(device).get_state()


    def toggle(self, key, new_state, duration=None):
        device = self.config['devices'][key]
        self.__get_switch_driver(device).set_state(new_state)
        self.cache.delete(str(key))

        if duration is not None:
            eta = datetime.utcnow() + timedelta(minutes=duration)
            from tasks import toggle_switch
            toggle_switch.apply_async((key, 1 if new_state == "0" else 0), eta=eta)
            self.__schedule = None
            self.__revoked = None

        return self.__get_switch(str(key))


    def __get_switch(self, key):
        info = self.cache.get(key)
        if info is None:
            device = self.config['devices'][key]

            scheduled = None
            revoked = self.__get_revoked()
            for entry in self.__get_schedule():
                args = eval(entry['request']['args'])
                if args[0] == key and entry['request']['id'] not in revoked:
                    scheduled = {'when': entry['eta'], 'state': args[1]}
                    break

            info = {
                'key': key,
                'name': device['name'],
                'state': self.get_state(device),
                'when': str(datetime.now()),
                'scheduled': scheduled
            }
            self.cache.set(key, info)
        
        return info

    def __get_schedule(self):
        if self.__schedule is None:
            self.__schedule = inspect().scheduled()['celery@raspberrypi']

        return self.__schedule


    def __get_revoked(self):
        if self.__revoked is None:
            self.__revoked = inspect().revoked()['celery@raspberrypi']

        return self.__revoked


    def __get_switch_driver(self, params):
        if 'ethernet' == params['type']:
            return EthernetSwitch(params['id'], self.config['ethernet']['address'], params['address'])
        elif 'raspberry' == params['type']:
            return RaspberrySwitch(params)
        else:
            raise RuntimeError('Unknown switch driver')

class AbstractSwitch:
    def notify_state_change(self, sensor_key, new_state):
        connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
        channel = connection.channel()
        channel.basic_publish(exchange='',
                              routing_key='switch_state',
                              properties=pika.BasicProperties(delivery_mode = 2), # make message persistent
                              body=json.dumps({'key': sensor_key, 'state': new_state, 'date': str(datetime.now())}))

class EthernetSwitch(AbstractSwitch):
    def __init__(self, id, url, address):
        self.id = id
        self.address = address
        self.url = 'http://' + url

    def get_state(self):
        statusXml = urllib2.urlopen(self.url + '/status.xml').read()
        xml = parseString(statusXml)

        return xml.getElementsByTagName('led' + str(self.address))[0].firstChild.nodeValue

    def set_state(self, new_state):
        current_state = self.get_state()
        if current_state != new_state:
            urllib2.urlopen(self.url + '/leds.cgi?led=' + str(self.address)).read()
            self.notify_state_change(self.id, new_state)

class RaspberrySwitch(AbstractSwitch):
    def get_state(self):
        return -1
