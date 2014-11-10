#!/usr/bin/python

from datetime import datetime
from xml.dom.minidom import parseString
import json
import os
import pika
import urllib2
import yaml

class SwitchService:
    def __init__(self):
        self.config = yaml.load(file(os.path.dirname(os.path.realpath(__file__)) + '/config.yml'))['switch']


    def get_list(self):
        switches = {}
        for key in self.config['devices']:
            switches[key] = self.__get_switch(key)

        return switches


    def get_state(self, device):
        return self.__get_switch_driver(device).get_state()


    def toggle(self, key, new_state):
        device = self.config['devices'][key]
        self.__get_switch_driver(device).set_state(new_state)

        return self.__get_switch(key)



    def __get_switch(self, key):
        device = self.config['devices'][key]

        return {
            'key': key,
            'name': device['name'],
            'state': self.get_state(device),
            'when': str(datetime.now())
        }


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
