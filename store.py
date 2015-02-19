#!/usr/bin/python

from datetime import datetime, timedelta
from pymongo import MongoClient
import json
import logging
import os
import pika
import sys
import yaml

DATE_FORMAT='%Y-%m-%d %H:%M'

class StoringService:
    def __init__(self):
        self.base_config = yaml.load(file(os.path.dirname(os.path.realpath(__file__)) + '/config.yml'))
        self.config = self.base_config['storing']['mongo']
        self.retry_delay = 10 * 1000

    def __get_db(self):
        self.conn = MongoClient(self.config['host'], self.config['port'])
        db = self.conn[self.config['collection']]
        db.authenticate(self.config['user'], self.config['pass'])

        return db

    def get_events_history(self, page, count):
        events = []
        for document in self.__get_db().switches.find().sort('date', -1)[page * count - count : page * count]:
            document['name'] = self.base_config['switch']['devices'][document['switch']]['name']
            del document['created_at']
            del document['_id']
            events.append(document)

        return events


    def get_reading_list(self, since, until = None):
        documents = []

        criteria = {'$gte': since}
        if until:
            criteria['$lte'] = until

        data = []
        for document in self.__get_db().temperatures.find({'date': criteria }).sort('date', -1):
            row = {'x': document['date'].strftime(DATE_FORMAT)}
            for address in document['sensors']:
                row[document['sensors'][address]['id']] = document['sensors'][address]['temperature']

            data.append(row)

        return data


    def store_switch_state(self,ch, method, properties, body):
        try:
            ch.basic_ack(delivery_tag = method.delivery_tag)
            data = json.loads(body)
            print "Store switch %s state %s at %s" % (data['key'], data['state'], data['date'])

            date = datetime.strptime(data['date'], '%Y-%m-%d %H:%M:%S.%f')
            self.__get_db().switches.insert({
                'date': date,
                'created_at': datetime.now(),
                'switch': data['key'],
                'state': data['state']
            })
            self.conn.disconnect()
        except Exception as e:
            print "\t%s occured with: %s" % (type(e), e)
            ch.basic_publish('dlx', 'switch_state', body, properties=properties)

    def consume_switch_state(self):
        connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
        channel = connection.channel()

        channel.exchange_declare(exchange='switch_state', type='direct')
        channel.queue_declare(queue='switch_state', durable=True)
        channel.queue_bind('switch_state', 'switch_state',routing_key='switch_state')

        channel.exchange_declare(exchange='dlx', type='direct') 
        dead_letter_queue = channel.queue_declare(queue='dead_letter', durable=True, arguments={
            'x-message-ttl': self.retry_delay,
            'x-dead-letter-exchange' : 'switch_state',
            'x-dead-letter-routing-key': 'switch_state'
        })
        channel.queue_bind(exchange='dlx',
                           routing_key='switch_state', # x-dead-letter-routing-key
                           queue=dead_letter_queue.method.queue)

        channel.basic_consume(self.store_switch_state, queue='switch_state')
        channel.start_consuming()

service = StoringService()
queue_to_handle = 'switch_state' if len(sys.argv) == 1 else sys.argv[1]

if __name__ == '__main__':
    print ' [*] Waiting for messages in ' + queue_to_handle

    logging.basicConfig()
    if queue_to_handle == 'switch_state':
        service.consume_switch_state()
    elif queue_to_handle == 'dead_letter':
        service.consume_dead_letter()
    else:
        print ' [X] Invalid queue: ' + queue_to_handle
