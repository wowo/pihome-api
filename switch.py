#!/usr/bin/python

from celery.task.control import inspect, revoke
from datetime import datetime, timedelta
from xml.dom.minidom import parseString
import json
import memcache
import os
import pika
import subprocess
import time
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
        self.__revoke_scheduled(str(key))
        self.cache.delete(str(key))

        duration = driver.get_duration(new_state) if 'get_duration' in dir(driver) else duration
        if duration is not None:
            from tasks import toggle_switch
            eta = datetime.utcnow() + duration
            toggle_switch.apply_async((key, driver.get_opposite_state(new_state)), eta=eta)
            self.__schedule = None
            self.__revoked = None

        return self.__get_switch(str(key))

    def __revoke_scheduled(self, key):
        revoked = self.__get_revoked()
        for entry in self.__get_schedule():
            args = eval(entry['request']['args'])
            if args[0] == key and entry['request']['id'] not in revoked:
                revoke(entry['request']['id'], Terminate=True)
                self.__schedule = None
                self.__revoked = None

    def __get_switch(self, key):
        info = self.cache.get(key)
        if info is None:
            device = self.config['devices'][key]

            scheduled = None
            if self.__get_switch_driver(device).allow_show_schedule():
                revoked = self.__get_revoked()
                for entry in self.__get_schedule():
                    args = eval(entry['request']['args'])
                    if args[0] == key and entry['request']['id'] not in revoked:
                        scheduled = {'when': entry['eta'], 'state': args[1]}
                        break

            info = {'key': key,
                    'name': device['name'],
                    'state': self.get_state(device),
                    'when': str(datetime.now()),
                    'scheduled': scheduled,
                    'type': device['type']}
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
        """
        :rtype : AbstractSwitch
        """
        if 'aggregate' in params:
            switches = []
            for switch in params['aggregate']:
                switches.append(self.__get_switch_driver(self.config['devices'][switch]))
            return AggregateSwitch(switches)
        if 'ethernet' == params['type']:
            return EthernetSwitch(params['id'],
                                  self.config['ethernet']['address'],
                                  params['address'])
        elif 'two_way' == params['type']:
            return TwoWaySwitch(
                params['id'],
                RaspberrySwitch(params['up_pin']),
                RaspberrySwitch(params['down_pin']),
                params['seconds'])
        elif 'click' == params['type']:
            return ClickSwitch(
                params['id'],
                params['pin'],
            )
        else:
            raise RuntimeError('Unknown switch driver')


class AbstractSwitch:
    def __init__(self):
        pass

    def set_state(self, new_state):
        raise NotImplementedError("Please implement this method")

    def get_state(self):
        raise NotImplementedError("Please implement this method")

    @staticmethod
    def notify_state_change(sensor_key, new_state):
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

    def get_opposite_state(self, new_state):
        return 1 if int(new_state) == 0 else 0

    def allow_show_schedule(self):
        return True


class EthernetSwitch(AbstractSwitch):
    def __init__(self, port_id, url, address):
        AbstractSwitch.__init__(self)
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
    def __init__(self, pin):
        AbstractSwitch.__init__(self)
        self.pin = pin
        os.system('gpio mode %s out' % str(self.pin))

    def get_state(self):
        state = subprocess.check_output(['gpio', 'read', str(self.pin)]).strip()
        return int(state)

    def set_state(self, new_state):
        if new_state != self.get_state():
            os.system('gpio write %s %s' % (str(self.pin), str(new_state)))


class TwoWaySwitch(AbstractSwitch):
    def __init__(self, switch_id, up, down, seconds):
        AbstractSwitch.__init__(self)
        self.switch_id = switch_id  # type: str
        self.up = up  # type: RaspberrySwitch
        self.down = down  # type: RaspberrySwitch
        self.seconds = seconds  # type: int

    def get_state(self):
        state = 'stop'
        if self.up.get_state() == 1:
            state = 'up'
        elif self.down.get_state() == 1:
            state = 'down'

        return state

    def set_state(self, new_state):
        if 'stop' == new_state:
            self.up.set_state(0)
            self.down.set_state(0)
        elif 'up' == new_state:
            self.down.set_state(0)
            self.up.set_state(1)
            self.notify_state_change(self.switch_id, new_state)
        elif 'down' == new_state:
            self.up.set_state(0)
            self.down.set_state(1)
            self.notify_state_change(self.switch_id, new_state)

    def get_opposite_state(self, new_state):
        return 'stop'

    def get_duration(self, new_state):
        return timedelta(seconds=int(self.seconds)) if 'stop' != new_state else None

    def allow_show_schedule(self):
        return False


class ClickSwitch(AbstractSwitch):
    def __init__(self, switch_id, pin):
        AbstractSwitch.__init__(self)
        self.switch_id = switch_id  # type: str
        self.pin = pin  # type: int
        os.system('gpio mode %s out' % str(self.pin))

    def get_state(self):
        return 0

    def set_state(self, new_state):
        os.system('gpio write %s 1' % (str(self.pin)))
        time.sleep(0.5)
        os.system('gpio write %s 0' % (str(self.pin)))
        self.notify_state_change(self.switch_id, 'click')


class AggregateSwitch(AbstractSwitch):
    def __init__(self, switches):
        AbstractSwitch.__init__(self)
        self.switches = switches  # type: list

    def get_state(self):
        return self.switches[-1].get_state()

    def set_state(self, new_state):
        for switch in self.switches:
            switch.set_state(new_state)
