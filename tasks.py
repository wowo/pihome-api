#!/usr/bin/python

import json
import requests
from datetime import datetime

from celery import Celery

import celeryconfig
from store import StoringService

celery = Celery('tasks')
celery.config_from_object(celeryconfig)


@celery.task
def toggle_switch(key, new_state, revoke_other_scheduled):
    url = 'http://localhost/api/switch/' + key
    data = {'state': new_state}
    print('Toggle switch task, url: %s, data : %s' % (url, data))
    requests.patch(url, json=data).raise_for_status()


@celery.task
def notify_state_change(sensor_key, new_state, user='n/a'):
    date = datetime.now()
    print('> Store switch %s state %s at %s by %s' % (sensor_key, new_state, date, user))

    service = StoringService()
    service.store_switch_state(sensor_key, new_state, date, user)
