#!/usr/bin/python

import yaml
import os
import urllib2
from xml.dom.minidom import parseString

class SwitchService:
    def __init__(self):
        self.config = yaml.load(file(os.path.dirname(os.path.realpath(__file__)) + '/config.yml'))['switch']

    def get_list(self):
        switches = {}
        for key,device in self.config['devices'].iteritems():
            switches[key] = {
                'key': key,
                'name': device['name'],
                'status': self.get_status(device),
            }

        return switches

    def get_status(self, device):
        return self.__get_switch(device['type'], device).get_status()

    def __get_switch(self, type, params):
        if 'ethernet' == type:
            return EthernetSwitch(self.config['ethernet']['address'], params['address'])
        elif 'raspberry' == type:
            return RaspberrySwitch(params)

class EthernetSwitch:
    def __init__(self, url, address):
        self.address = address
        self.url = url

    def get_status(self):
        statusXml = urllib2.urlopen('http://' + self.url + '/status.xml').read()
        xml = parseString(statusXml)

        return xml.getElementsByTagName('led' + str(self.address))[0].firstChild.nodeValue

class RaspberrySwitch:
    def get_status(self):
        return -1
