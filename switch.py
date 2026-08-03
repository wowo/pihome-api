#!/usr/bin/python

from datetime import datetime, timedelta
import json
import socket
from xml.dom.minidom import parseString
import os
import re
import redis
import subprocess
import timeit
import time
import requests

from celery import Celery
import yaml

from celery.task.control import revoke
import celeryconfig

import jwt
import logging

from pprint import pformat
from collections import OrderedDict

def dthandler(obj):
    return obj.isoformat() if isinstance(obj, datetime) else None

class SwitchService:
    def __init__(self):
        path = os.path.dirname(os.path.realpath(__file__)) + '/config.yml'
        self.config = yaml.load(open(path).read(), Loader=yaml.FullLoader)['switch']
        self.cache = redis.StrictRedis(host='localhost', port=6379, db=0)
        self.__schedule = None
        self.__revoked = None

    def get_list(self, fresh):
        switches = {}
        self.__schedule = None
        self.__revoked = None
        if not fresh:
            switches = self.cache.hgetall('_switches')
            switches = {k.decode(): json.loads(v) for k, v in switches.items()}
        else:
            self.cache.delete('_switches')

        # load remaining switches defined in config but absent in _switches hash Redis entry
        for key in set(self.config['devices'].keys()) - set(switches.keys()):
            start = timeit.default_timer()
            switches[key] = self.__get_switch(str(key))
            logging.warning('  %s GET in %.3fs' % (key, timeit.default_timer() - start))

        EthernetSwitch.led_api_cache = None

        return OrderedDict(sorted(switches.items()))

    def get_state(self, device):
        return self.__get_switch_driver(device).get_state()

    def toggle(self, key, new_state, duration=None, user=None):
        start = timeit.default_timer()
        if not self.__can_set_duration_for_off(key, new_state):
            logging.warning('Can not set duration for state 0 for %s' % (key))
            duration = None
        logging.warning('TOGGLE %s' % (key))
        device = self.config['devices'][key]
        driver = self.__get_switch_driver(device)
        driver.set_state(new_state, user)
        logging.warning('TOGGLE %s set_state %.3f' % (key, timeit.default_timer() - start))
        self.__revoke_scheduled(str(key))
        logging.warning('TOGGLE %s revoke_scheduled %.3f' % (key, timeit.default_timer() - start))

        duration = driver.get_duration(new_state) if 'get_duration' in dir(driver) else duration
        if duration is not None:
            from tasks import toggle_switch
            eta = datetime.utcnow() + duration
            toggle_switch.apply_async((key, driver.get_opposite_state(new_state), True), eta=eta)
            self.__schedule = None
            self.__revoked = None
        logging.warning('TOGGLE %s set duration %.3f' % (key, timeit.default_timer() - start))

        EthernetSwitch.led_api_cache = None
        info = self.__get_switch(str(key))
        logging.warning('TOGGLE %s get info %.3f' % (key, timeit.default_timer() - start))

        return info

    def __revoke_scheduled(self, key):
        revoked = self.__get_revoked()
        for entry in self.__get_schedule():
            args = eval(entry['request']['args'])
            # toggle_switch(key, state, revoke_other); skip short args (e.g. wicket_step)
            if len(args) >= 3 and args[0] == key and args[2] and entry['request']['id'] not in revoked:
                logging.warning('revoking ' + key)
                revoke(entry['request']['id'], Terminate=True)
                self.__schedule = None
                self.__revoked = None

    def run_wicket_step(self, key, step):
        device = self.config['devices'][key]
        driver = self.__get_switch_driver(device)
        if not isinstance(driver, ClickSequenceSwitch):
            return
        driver.run_step(step)
        EthernetSwitch.led_api_cache = None
        self.__get_switch(str(key))

    def __get_switch(self, key):
        device = self.config['devices'][key]
        driver = self.__get_switch_driver(device)

        scheduled = None
        if isinstance(driver, ClickSequenceSwitch):
            scheduled = driver.get_sequence_scheduled()
        elif driver.allow_show_schedule():
            revoked = self.__get_revoked()
            for entry in self.__get_schedule():
                args = eval(entry['request']['args'])
                if len(args) >= 2 and args[0] == key and entry['request']['id'] not in revoked:
                    scheduled = {'when': entry['eta'], 'state': args[1]}
                    break
        info = {'key': key,
                'name': device['name'],
                'state': self.get_state(device),
                'when': str(datetime.now()),
                'scheduled': scheduled,
                'stateless': device['stateless'] if 'stateless' in device else False,
                'durations': device['durations'] if 'durations' in device else False,
                'icon': device['icon'],
                'group': device['group'],
                'type': device['type']}

        self.cache.hset('_switches', key, json.dumps(info, default=dthandler))
        try:
            from store import StoringService
            StoringService().upsert_switch_state(info)
        except Exception:
            pass

        return info

    @staticmethod
    def __get_celery():
        task_celery = Celery('tasks')
        task_celery.config_from_object(celeryconfig)
        return task_celery

    def __get_schedule(self):
        if self.__schedule is None:
            try:
                self.__schedule = self.__get_celery().control.inspect().scheduled()['celery@raspberrypi']
            except (socket.error, TypeError):
                self.__schedule = []

        return self.__schedule

    def __get_revoked(self):
        if self.__revoked is None:
            try:
                self.__revoked = self.__get_celery().control.inspect().revoked()['celery@raspberrypi']
            except (socket.error, TypeError):
                self.__revoked = []

        return self.__revoked

    def __get_switch_driver(self, params):
        """
        :rtype : AbstractSwitch
        """
        if 'aggregate' in params:
            switches = []
            for switch in params['aggregate']:
                switches.append(self.__get_switch_driver(self.config['devices'][switch]))
            return AggregateSwitch(switches, self.cache)
        if 'ethernet' == params['type']:
            return EthernetSwitch(params['id'],
                                  self.config['ethernet']['subnet'],
                                  params['address'],
                                  self.cache)
        elif 'two_way' == params['type'] and 'rpi' == params['backend']:
            return TwoWaySwitch(
                params['id'],
                RaspberrySwitch(params['up_pin']),
                RaspberrySwitch(params['down_pin']),
                params['seconds'])
        elif 'two_way' == params['type'] and 'ethernet' == params['backend']:
            return TwoWaySwitch(
                params['id'],
                EthernetSwitch(params['id'],
                                  self.config['ethernet']['subnet'],
                                  params['up_pin'],
                                  self.cache),
                EthernetSwitch(params['id'],
                                  self.config['ethernet']['subnet'],
                                  params['down_pin'],
                                  self.cache),
                params['seconds'])
        elif 'click' == params['type']:
            return ClickSwitch(
                params['id'],
                params['pin'],
                params['busy_delay'] if 'busy_delay' in params else None
            )
        elif 'raspberry' == params['type']:
            return RaspberrySwitch(params['pin'])
        elif 'click_sequence' == params['type']:
            return ClickSequenceSwitch(
                params['id'],
                params['sequence'],
                self.cache,
                params.get('open_seconds', 5),
                params.get('wait_seconds', 60),
                params.get('close_ui_seconds', 5),
            )
        else:
            raise RuntimeError('Unknown switch driver ' + params['type'])

    def __can_set_duration_for_off(self, key, new_state):
        try:
            if int(new_state) == 1:
                return True
        except ValueError: # up/down
            return True

        device = self.config['devices'][key]
        if not 'durations' in device:
            return False

        try:
            return True if device['durations'].index('X') > -1 else False
        except ValueError:
            return False


class AbstractSwitch:
    def __init__(self):
        pass

    def set_state(self, new_state, user):
        raise NotImplementedError("Please implement this method")

    def get_state(self):
        raise NotImplementedError("Please implement this method")

    def get_opposite_state(self, new_state):
        return 1 if int(new_state) == 0 else 0

    def allow_show_schedule(self):
        return True


class EthernetSwitch(AbstractSwitch):
    led_api_cache = None

    def __init__(self, port_id, subnet, address, cache):
        AbstractSwitch.__init__(self)
        self.port_id = port_id
        self.address = address
        self.subnet = subnet
        self.cache = cache
        self.ip = self.cache.get('ethernet_ip').decode()

    def get_state(self):
        state = None
        logging.warning('ip  ' + self.ip)
        if self.ip:
            state = self.get_state_for_ips([self.ip])

        if not state:
            state = self.get_state_for_ips(self.get_alive_ips(self.subnet))

        return state

    def get_state_for_ips(self, ips):
        for ip in ips:
            try:
                xml = self.get_status_xml(ip)
                node_name = 'led' + str(self.address)
                return xml.getElementsByTagName(node_name)[0].firstChild.nodeValue
            except Exception as err:
                logging.error('get_state error for IP %s: %s' %(ip, err))
                pass

        return None

    @staticmethod
    def get_alive_ips(subnet):
        logging.warning('get_alive_ips!!!!!!!')
        nmap = subprocess.check_output('nmap -sP ' + subnet, shell=True)

        return re.findall('for ([0-9\.]+)', nmap.decode())

    def get_status_xml(self, ip):
        if self.__class__.led_api_cache is not None:
            return self.__class__.led_api_cache

        status_xml = requests.get('http://%s/status.xml' % ip)
        if status_xml.status_code is not 200:
            raise Exception('Got %s with %s from LEDs API' % (status_xml.status_code, status_xml.text))
        self.ip = ip
        self.cache.setex('ethernet_ip', 60 * 60 * 24 * 7, self.ip)  # cache for 7 days

        self.__class__.led_api_cache = parseString(status_xml.text)

        return self.__class__.led_api_cache

    def set_state(self, new_state, user):
        self.__class__.led_api_cache = None
        current_state = self.get_state()
        if int(current_state) != int(new_state):
            address = 'http://%s/leds.cgi?led=%s' % (self.ip, str(self.address))
            requests.get(address)
            from tasks import notify_state_change
            notify_state_change.apply_async((self.port_id, new_state, user))


class RaspberrySwitch(AbstractSwitch):
    def __init__(self, pin):
        AbstractSwitch.__init__(self)
        self.pin = pin
        os.system('gpio mode %s out' % str(self.pin))

    def get_state(self):
        try:
            state = subprocess.check_output(['gpio', 'read', str(self.pin)]).strip()
            return int(state)
        except subprocess.CalledProcessError:
            return None

    def set_state(self, new_state, user):
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

    def set_state(self, new_state, user):
        from tasks import notify_state_change
        if 'stop' == new_state:
            self.up.set_state(0, user)
            self.down.set_state(0, user)
        elif 'up' == new_state:
            self.down.set_state(0, user)
            self.up.set_state(1, user)
            notify_state_change.apply_async((self.switch_id, new_state, user))
        elif 'down' == new_state:
            self.up.set_state(0, user)
            self.down.set_state(1, user)
            notify_state_change.apply_async((self.switch_id, new_state, user))

    def get_opposite_state(self, new_state):
        return 'stop'

    def get_duration(self, new_state):
        return timedelta(seconds=int(self.seconds)) if 'stop' != new_state else None

    def allow_show_schedule(self):
        return False


class ClickSwitch(AbstractSwitch):
    def __init__(self, switch_id, pin, busy_delay):
        AbstractSwitch.__init__(self)
        self.switch_id = switch_id  # type: str
        self.pin = pin  # type: int
        self.busy_delay = busy_delay
        os.system('gpio mode %s out' % str(self.pin))

    def get_state(self):
        return 0

    def set_state(self, new_state, user):
        start = timeit.default_timer()
        os.system('gpio write %s 1' % (str(self.pin)))
        time.sleep(0.5)
        os.system('gpio write %s 0' % (str(self.pin)))
        from tasks import notify_state_change
        notify_state_change.apply_async((self.switch_id, 'click', user))
        if self.busy_delay is not None:
            logging.warning('execution so far %.3fs' % (timeit.default_timer() - start))
            busy_delay_effective = self.busy_delay - int(timeit.default_timer() - start)
            logging.warning(
                'Busy delay %s is %.1fs, setting delay to %.1fs' % (
                    self.switch_id,
                    self.busy_delay,
                    busy_delay_effective))
            time.sleep(busy_delay_effective)


class AggregateSwitch(AbstractSwitch):
    def __init__(self, switches, cache):
        AbstractSwitch.__init__(self)
        self.switches = switches  # type: list
        self.cache = cache

    def get_state(self):
        return self.switches[-1].get_state()

    def set_state(self, new_state, user):
        for switch in self.switches:
            switch.set_state(new_state, user)
            self.cache.delete('_switches')

    def get_duration(self, new_state):
        durations = []
        for switch in self.switches:
            if 'get_duration' in dir(switch):
                durations.append(switch.get_duration(new_state))

        return max(durations) if len(durations) > 0 else None

    def get_opposite_state(self, new_state):
        return 'stop'


class ClickSequenceSwitch(AbstractSwitch):
    """Wicket (Furtka): open pulse → stop pulse → wait → close pulse + fake closing UI."""

    def __init__(self, switch_id, sequence, cache, open_seconds=5, wait_seconds=60, close_ui_seconds=5):
        AbstractSwitch.__init__(self)
        self.switch_id = switch_id  # type: str
        self.sequence = sequence
        self.cache = cache
        self.open_seconds = int(open_seconds)
        self.wait_seconds = int(wait_seconds)
        self.close_ui_seconds = int(close_ui_seconds)
        self.target = sequence[0]

    def _redis_key(self):
        return 'wicket:' + self.switch_id

    def _load(self):
        raw = self.cache.get(self._redis_key())
        return json.loads(raw) if raw else None

    def _save(self, phase, ends_at, task_ids):
        self.cache.set(self._redis_key(), json.dumps({
            'phase': phase,
            'ends_at': ends_at,
            'task_ids': task_ids,
        }))

    def _clear(self):
        self.cache.delete(self._redis_key())

    def _pulse(self, user):
        ClickSwitch(self.target['switch'], self.target['pin'], None).set_state(1, user)

    def _ends_iso(self, seconds_from_now):
        return (datetime.utcnow() + timedelta(seconds=int(seconds_from_now))).isoformat() + 'Z'

    def get_sequence_scheduled(self):
        data = self._load()
        if not data:
            return None
        return {
            'kind': 'wicket',
            'phase': data['phase'],
            'ends_at': data['ends_at'],
            'open_s': self.open_seconds,
            'wait_s': self.wait_seconds,
            'close_ui_s': self.close_ui_seconds,
        }

    def get_state(self):
        return 0

    def set_state(self, new_state, user):
        data = self._load()
        if data:
            phase = data.get('phase')
            if phase in ('opening', 'closing'):
                return
            if phase == 'waiting':
                self._early_close(data, user)
                return
        self._start(user)

    def _start(self, user):
        from tasks import wicket_step
        self._pulse(user)
        now = datetime.utcnow()
        stop_eta = now + timedelta(seconds=self.open_seconds)
        close_eta = now + timedelta(seconds=self.open_seconds + self.wait_seconds)
        stop_id = wicket_step.apply_async((self.switch_id, 'stop'), eta=stop_eta).id
        close_id = wicket_step.apply_async((self.switch_id, 'close'), eta=close_eta).id
        self._save('opening', stop_eta.isoformat() + 'Z', [stop_id, close_id])

    def _early_close(self, data, user):
        from tasks import wicket_step
        for tid in data.get('task_ids') or []:
            revoke(tid, Terminate=True)
        self._pulse(user)
        clear_eta = datetime.utcnow() + timedelta(seconds=self.close_ui_seconds)
        clear_id = wicket_step.apply_async((self.switch_id, 'clear'), eta=clear_eta).id
        self._save('closing', clear_eta.isoformat() + 'Z', [clear_id])

    def run_step(self, step):
        data = self._load()
        if step == 'clear':
            self._clear()
            return
        if not data:
            return
        if step == 'stop':
            if data.get('phase') != 'opening':
                return
            self._pulse('system')
            # Keep remaining close task id(s); drop the stop id that just ran.
            remaining = (data.get('task_ids') or [])[1:]
            self._save('waiting', self._ends_iso(self.wait_seconds), remaining)
            return
        if step == 'close':
            if data.get('phase') != 'waiting':
                return
            from tasks import wicket_step
            self._pulse('system')
            clear_eta = datetime.utcnow() + timedelta(seconds=self.close_ui_seconds)
            clear_id = wicket_step.apply_async((self.switch_id, 'clear'), eta=clear_eta).id
            self._save('closing', clear_eta.isoformat() + 'Z', [clear_id])

    def allow_show_schedule(self):
        return False

    def get_opposite_state(self, new_state):
        return 0
