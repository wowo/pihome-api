#!/usr/bin/python

from datetime import datetime, timedelta
from pymongo import MongoClient
import json
import os
import pika
import yaml

class StoringService:
    def __init__(self):
        self.config = yaml.load(file(os.path.dirname(os.path.realpath(__file__)) + '/config.yml'))['storing']['mongo']

    def store_switch_state(self,ch, method, properties, body):
        try:
            data = json.loads(body)
            print "Store switch %s state %s at %s" % (data['key'], data['state'], data['date'])

            conn = MongoClient(self.config['host'], self.config['port'])
            self.db = conn[self.config['collection']]
            self.db.authenticate(self.config['user'], self.config['pass'])

            date = datetime.strptime(data['date'], '%Y-%m-%d %H:%M:%S.%f')
            self.db.switches.insert({
                'date': date,
                'created_at': datetime.now(),
                'switch': data['key'],
                'state': data['state']
            })
            conn.disconnect()
            ch.basic_ack(delivery_tag = method.delivery_tag)
        except Exception as e:
            print "\t%s occured with: %s" % (type(e), e)

    def consume_queue(self):
        connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
        channel = connection.channel()
        channel.queue_declare(queue='switch_state', durable=True)
        channel.basic_consume(self.store_switch_state, queue='switch_state')
        channel.start_consuming()

service = StoringService()
service.consume_queue()
