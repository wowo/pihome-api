#!/usr/bin/python

from datetime import datetime
import json
import paho.mqtt.subscribe as subscribe
import redis 
import sys
import time


print("Starting topic %s key %s" % (sys.argv[1], sys.argv[2]))
redis = redis.StrictRedis(host='localhost', port=6379, db=0)

def on_msg(client, userdata, message):
    print("message received " + str(message.payload.decode("utf-8")))
    data = json.loads(message.payload.decode("utf-8"))
    data['value'] = data['temperature']
    data['when'] = str(datetime.now())
    redis.lpush(sys.argv[2], json.dumps(data))
    redis.ltrim(sys.argv[2], 0, 50)


subscribe.callback(on_msg, sys.argv[1], hostname='localhost')

# $1 - topic name
# $2 - redis key name
#echo "$0 fetching from MQTT topic $1 and saving to Redis list $2"
#mosquitto_sub -t $1 -F %I,%p | parallel redis-cli lpush $2 
