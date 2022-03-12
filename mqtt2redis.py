#!/usr/bin/python

from datetime import datetime
import json
import paho.mqtt.subscribe as subscribe
import redis 
import sys
import time

sensor_key = 'temperature' if len(sys.argv) == 3 else sys.argv[3]
print('Starting topic %s key %s, parameter: %s' % (sys.argv[1], sys.argv[2], sensor_key))
redis = redis.StrictRedis(host='localhost', port=6379, db=0)

def on_msg(client, userdata, message):
    print('message received %s, searching for %s' % (str(message.payload.decode('utf-8')), sensor_key))
    data = json.loads(message.payload.decode('utf-8'))
    data['value'] = data[sensor_key]
    data['when'] = str(datetime.now())
    redis.lpush(sys.argv[2], json.dumps(data))
    redis.ltrim(sys.argv[2], 0, 50)


subscribe.callback(on_msg, sys.argv[1], hostname='localhost')

# $1 - topic name
# $2 - redis key name
#echo '$0 fetching from MQTT topic $1 and saving to Redis list $2'
#mosquitto_sub -t $1 -F %I,%p | parallel redis-cli lpush $2 
