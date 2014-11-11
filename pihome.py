#!/usr/bin/python

from datetime import datetime
from flask import Flask, jsonify, request, Response
from sensor import SensorService
from store import StoringService
from switch import SwitchService
import json
import sys

app = Flask(__name__)

def hal_response(data):
    dthandler = lambda obj: obj.isoformat() if isinstance(obj, datetime) else None

    return Response(response=json.dumps(({'count': len(data), 'total': len(data), '_embedded': data}), default=dthandler),
             status = 200,
             mimetype='application/json')

@app.route('/switch', methods = ['GET'])
def switch_list():
    switch = SwitchService()

    return hal_response(switch.get_list())


@app.route('/switch/<key>', methods = ['PATCH'])
def switch_toggle(key):
    switch = SwitchService()
    input = json.loads(request.data)
    data = switch.toggle(key, input['state'], input['duration'] if 'duration' in input else None)

    return jsonify(data)

@app.route('/sensor', methods = ['GET'])
def sensor_list():
    sensor = SensorService()

    return hal_response(sensor.get_list())

@app.route('/history', methods = ['GET'])
def history_list():
    page = int(request.args['page']) if 'page' in request.args else 1
    count = int(request.args['count']) if 'count' in request.args else 25
    storing = StoringService()

    return hal_response(storing.get_events_history(page, count))


@app.after_request
def add_cors(resp):
    """ Ensure all responses have the CORS headers. This ensures any failures are also accessible
        by the client. """
    resp.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin','*')
    resp.headers['Access-Control-Allow-Credentials'] = 'true'
    resp.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS, GET, PATCH'
    resp.headers['Access-Control-Allow-Headers'] = request.headers.get('Access-Control-Request-Headers', 'Authorization')

    return resp

if not app.debug:
    import logging
    from logging import FileHandler
    file_handler = FileHandler('/tmp/app.log')
    file_handler.setLevel(logging.WARNING)
    app.logger.addHandler(file_handler)

if __name__ != 'pihome-api': # wsgi
    if __name__ == "__main__" and len(sys.argv) == 1:
        app.run(host='0.0.0.0', port=8999, debug=True)
