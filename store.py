#!/usr/bin/python

from datetime import datetime
import logging
import os
import sys
import traceback

from pymongo import MongoClient
import pika
import yaml

from sensor import SensorService

DATE_FORMAT = '%Y-%m-%d %H:%M'


class StoringService:
    def __init__(self):
        path = os.path.dirname(os.path.realpath(__file__)) + '/config.yml'
        self.base_config = yaml.load(file(path))
        self.config = self.base_config['storing']['mongo']
        self.retry_delay = 10 * 1000

    def __get_db(self):
        self.conn = MongoClient(self.config['host'], self.config['port'])
        db = self.conn[self.config['collection']]
        db.authenticate(self.config['user'], self.config['pass'], source='admin')

        return db

    def get_events_history(self, page, count):
        events = []
        devices_config = self.base_config['switch']['devices']
        iterator = self.__get_db().switches.find().sort('date', -1)
        for document in iterator[page * count - count:page * count]:
            document['name'] = devices_config[document['switch']]['name']
            del document['created_at']
            del document['_id']
            events.append(document)

        return events

    def get_reading_list(self, since, until=None):
        criteria = {'date': {'$gte': since}}
        if until:
            criteria['date']['$lte'] = until

        data = []
        iterator = self.__get_db().temperatures.find(criteria).sort('date', -1)
        for document in iterator:
            row = {'x': document['date'].strftime(DATE_FORMAT)}
            for address in document['sensors']:
                if document['sensors'][address]['temperature'] < 85:
                    id = document['sensors'][address]['id']
                    row[id] = document['sensors'][address]['temperature']
            data.append(row)

        return data

    def store_switch_state(self, sensor_key, new_state, date):
        self.__get_db().switches.insert({
            'date': date,
            'created_at': date,
            'switch': sensor_key,
            'state': new_state
        })

    def store_sensors_state(self):
        try:
            data = {}
            sensor = SensorService()
            sensors = sensor.get_list()
            for key in sensors:
                print('> store %.2f for sensor %s' % (sensors[key]['value'], sensors[key]['key']))
                data[sensors[key]['address']] = {
                    'temperature':  sensors[key]['value'],
                    'id': key,
                    'name': sensors[key]['name']
                }

            self.__get_db().temperatures.insert({
                'date': datetime.now(),
                'sensors': data
            })
            self.conn.close()
        except Exception as e:
            print "\t%s occured with: %s" % (type(e), e)
            traceback.print_exc()

    def consume_switch_state(self):
        path = os.path.dirname(os.path.realpath(__file__)) + '/config.yml'
        config = yaml.load(file(path))['storing']['rabbitmq']
        credentials = pika.PlainCredentials(config['user'], config['pass'])
        parameters = pika.ConnectionParameters(config['host'], credentials=credentials)
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()

        channel.exchange_declare(exchange='switch_state', type='direct')
        channel.queue_declare(queue='switch_state', durable=True)
        channel.queue_bind('switch_state',
                           'switch_state',
                           routing_key='switch_state')

        channel.exchange_declare(exchange='dlx', type='direct')
        dead_letter_queue = channel.queue_declare(
            queue='dead_letter',
            durable=True,
            arguments={'x-message-ttl': self.retry_delay,
                       'x-dead-letter-exchange': 'switch_state',
                       'x-dead-letter-routing-key': 'switch_state'})
        channel.queue_bind(exchange='dlx',
                           routing_key='switch_state',
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
