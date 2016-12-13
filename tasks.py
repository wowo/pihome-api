#!/usr/bin/python

from celery import Celery
import json
import os
import urllib2
import yaml

path = os.path.dirname(os.path.realpath(__file__)) + '/config.yml'
config = yaml.load(file(path))['storing']['rabbitmq']
celery = Celery('tasks', broker='amqp://%s:%s@%s//' % (config['user'], config['pass'], config['host']))
# celery.config_from_object('celeryconfig')


@celery.task
def toggle_switch(key, new_state, revoke_other_scheduled):
    url = 'http://localhost/api/switch/' + key
    data = json.dumps({'state': new_state})
    print 'Toggle switch task, url: %s, data : %s' % (url, data)

    request = urllib2.Request(url, data, {'Content-Type': 'application/json'})
    request.get_method = lambda: 'PATCH'
    urllib2.urlopen(request).read()
