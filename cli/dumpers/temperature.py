#!/usr/bin/python3

from datetime import datetime, timedelta
from pymongo import MongoClient
import json
import logging
import os
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
    path = open(os.path.dirname(os.path.realpath(__file__)) + '/../../config.yml')
    config = yaml.load(path, Loader=yaml.FullLoader)['storing']['mongo']
    conn = MongoClient(config['host'], config['port'])
    db = conn[config['collection']]
    db.authenticate(config['user'], config['pass'], source='admin')
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
collection = 'temperatures' if len(sys.argv) == 2 else sys.argv[2]
value_field = 'temperature' if len(sys.argv) == 3 else sys.argv[3]


criteria = {'sensors': {'$exists': True}}
iterator = get_db()[collection].find(criteria).sort('date', 1)
for document in iterator:
    for uid in document['sensors']:
        try:
            path = '%s/%s' % (output_path, document['sensors'][uid]['id'])
            filename = '%s/%s-%d-%02d.csv' % (
                path,
                collection,
                document['date'].year,
                document['date'].month)
            ensure_dirs(path)
            logger.debug('Attempting to write %s data to file %s' % (document['sensors'][uid], filename))
            get_file(filename).write('%s,%.2f\n' % (
                document['date'].strftime('%Y-%m-%d %H:%M:%S'),
                document['sensors'][uid][value_field]))
        except KeyError:
            logger.warning('Missing %s key in %s, skipping' % (value_field, document['sensors'][uid]))
        except:
            logger.critical('Unexpected error: ' + sys.exc_info()[0])

for filename in file_handlers:
    file_handlers[filename].close()
