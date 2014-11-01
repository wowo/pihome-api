#!/usr/bin/python

from datetime import datetime
from xml.dom.minidom import parseString
import os
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
            return EthernetSwitch(self.config['ethernet']['address'], params['address'])
        elif 'raspberry' == params['type']:
            return RaspberrySwitch(params)
        else:
            raise RuntimeError('Unknown switch driver')

class EthernetSwitch:
    def __init__(self, url, address):
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

class RaspberrySwitch:
    def get_state(self):
        return -1
