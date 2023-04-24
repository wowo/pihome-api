from abc import ABC
import logging
import sys
import os
import yaml
from datetime import datetime, timedelta
from pymongo import MongoClient

class AbstractDumper(ABC):
    @staticmethod
    def get_logger():
        root = logging.getLogger()
        root.setLevel(logging.DEBUG)

        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        ch.setFormatter(formatter)
        root.addHandler(ch)
        return root


    @staticmethod
    def get_db():
        with open(os.path.dirname(os.path.realpath(__file__)) + '/../../config.yml', 'r') as file:
            config = yaml.safe_load(file)['storing']['mongo']
        conn = MongoClient(config['host'], config['port'])
        db = conn[config['collection']]
        db.authenticate(config['user'], config['pass'], source='admin')
        return db


    def ensure_dirs(self, dirs):
        if not os.path.exists(dirs):
            self.get_logger().debug('Dirs %s do not exist, will create it' % dirs)
            os.makedirs(dirs)


    def get_file(self, filename):
        if filename not in file_handlers:
            file_handlers[filename] = open(filename, 'a+')
        return file_handlers[filename]
