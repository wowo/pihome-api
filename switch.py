#!/usr/bin/python

from celery.task.control import inspect
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
        path = os.path.dirname(os.path.realpath(__file__)) + '/config.yml'
        self.config = yaml.load(file(path))['switch']
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
        driver = self.__get_switch_driver(device)
        driver.set_state(new_state)
        self.cache.delete(str(key))

        duration = driver.get_duration(new_state) if 'get_duration' in dir(driver) else duration

        if duration is not None:
            from tasks import toggle_switch
            eta = datetime.utcnow() + duration
            toggled = 1 if int(new_state) == 0 else 0
            toggle_switch.apply_async((key, toggled), eta=eta)
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
                    scheduled = {'when': entry['eta'],
                                 'state': args[1]}
                    break

            info = {'key': key,
                    'name': device['name'],
                    'state': self.get_state(device),
                    'when': str(datetime.now()),
                    'scheduled': scheduled}
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
            return EthernetSwitch(params['id'],
                                  self.config['ethernet']['address'],
                                  params['address'])
        elif 'raspberry' == params['type']:
            return RaspberrySwitch(params['pin'], params['seconds'])
        else:
            raise RuntimeError('Unknown switch driver')


class AbstractSwitch:
    def notify_state_change(self, sensor_key, new_state):
        payload = {'key': sensor_key,
                   'state': new_state,
                   'date': str(datetime.now())}
        parameters = pika.ConnectionParameters('localhost')
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        channel.basic_publish(exchange='',
                              routing_key='switch_state',
                              properties=pika.BasicProperties(delivery_mode=2),
                              body=json.dumps(payload))


class EthernetSwitch(AbstractSwitch):
    def __init__(self, port_id, url, address):
        self.port_id = port_id
        self.address = address
        self.url = 'http://' + url

    def get_state(self):
        status_xml = urllib2.urlopen(self.url + '/status.xml').read()
        xml = parseString(status_xml)
        node_name = 'led' + str(self.address)

        return xml.getElementsByTagName(node_name)[0].firstChild.nodeValue

    def set_state(self, new_state):
        current_state = self.get_state()
        if int(current_state) != int(new_state):
            address = self.url + '/leds.cgi?led=' + str(self.address)
            urllib2.urlopen(address).read()
            self.notify_state_change(self.port_id, new_state)


class RaspberrySwitch(AbstractSwitch):
    def __init__(self, pin, seconds):
        self.pin = pin
        self.seconds = seconds
        if not os.path.isdir('/sys/class/gpio/gpio' + str(self.pin)):
            export = open('/sys/class/gpio/export', 'w')
            export.write(str(self.pin))
            export.close()
            direction = open('/sys/class/gpio/gpio%s/direction' % str(self.pin), 'w')
            direction.write('out')
            direction.close()

    def __del__(self):
        export = open('/sys/class/gpio/unexport', 'w')
        export.write(str(self.pin))
        export.close()

    def get_state(self):
        value = open('/sys/class/gpio/gpio%s/value' % str(self.pin), 'r')
        state = value.read().strip()
        value.close()
        return int(state)

    def set_state(self, new_state):
        if int(new_state) != self.get_state():
            value = open('/sys/class/gpio/gpio%s/value' % str(self.pin), 'w')
            value.write(str(new_state))
            value.close()
            self.notify_state_change(self.pin, int(new_state))

    def get_duration(self, new_state):
        return timedelta(seconds=int(self.seconds)) if int(new_state) == 1 else None
