#!/usr/bin/python

from datetime import datetime, timedelta
from pymongo import MongoClient
import json
import logging
import os
import pika
import sys
import yaml
import traceback


def get_logger():
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    root.addHandler(ch)
    return root


def get_db():
    path = file(os.path.dirname(os.path.realpath(__file__)) + '/../../config.yml')
    config = yaml.load(path)['storing']['mongo']
    conn = MongoClient(config['host'], config['port'])
    db = conn[config['collection']]
    db.authenticate(config['user'], config['pass'])
    return db


def ensure_dirs(dirs):
    if not os.path.exists(dirs):
        logger.debug('Dirs %s do not exist, will create it' % dirs)
        os.makedirs(dirs)


def get_file(filename):
    if filename not in file_handlers:
        file_handlers[filename] = open(filename, 'a+')
    return file_handlers[filename]


if len(sys.argv) == 1:
    raise Exception('Please specify output path as first argument')

output_path = sys.argv[1].rstrip('/')
logger = get_logger()
file_handlers = {}

criteria = {'sensors': {'$exists': True}}
iterator = get_db().temperatures.find(criteria).sort('date', 1)
for document in iterator:
    for uid in document['sensors']:
        try:
            path = '%s/%s' % (output_path, document['sensors'][uid]['id'])
            filename = '%s/temeratures-%d-%02d.csv' % (
                path,
                document['date'].year,
                document['date'].month)
            ensure_dirs(path)
            logger.debug('Attempting to write %s data to file %s' % (document['sensors'][uid], filename))
            get_file(filename).write('%s,%.2f\n' % (
                document['date'].strftime('%Y-%m-%d %H:%M:%S'),
                document['sensors'][uid]['temperature']))
        except KeyError:
            logger.warning('Missing temerature key in %s, skipping' % document['sensors'][uid])
        except:
            logger.critical('Unexpected error: ' + sys.exc_info()[0])

for filename in file_handlers:
    file_handlers[filename].close()
