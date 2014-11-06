#!/usr/bin/python

from flask import Flask, jsonify, request
from switch import SwitchService
from sensor import SensorService
import json
import sys

app = Flask(__name__)

def hal_response(data):
    return jsonify({'count': len(data), 'total': len(data), '_embedded': data})

@app.route('/switch', methods = ['GET'])
def switch_list():
    switch = SwitchService()

    return hal_response(switch.get_list())


@app.route('/switch/<key>', methods = ['PATCH'])
def switch_toggle(key):
    switch = SwitchService()
    input = json.loads(request.data)
    data = switch.toggle(key, input['state'])

    return jsonify(data)

@app.route('/sensor', methods = ['GET'])
def sensor_list():
    sensor = SensorService()

    return hal_response(sensor.get_list())


@app.after_request
def add_cors(resp):
    """ Ensure all responses have the CORS headers. This ensures any failures are also accessible
        by the client. """
    resp.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin','*')
    resp.headers['Access-Control-Allow-Credentials'] = 'true'
    resp.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS, GET, PATCH'
    resp.headers['Access-Control-Allow-Headers'] = request.headers.get('Access-Control-Request-Headers', 'Authorization')

    return resp


if __name__ != 'pihome-api': # wsgi
    if __name__ == "__main__" and len(sys.argv) == 1:
        app.run(host='0.0.0.0', port=8999, debug=True)
