#!/usr/bin/python

from datetime import datetime, timedelta
from flask import Flask, jsonify, request, Response
from sensor import SensorService
from store import StoringService
from switch import SwitchService
import dateutil.parser
import json
import sys

app = Flask(__name__)


def hal_response(data):
    def dthandler(obj):
        return obj.isoformat() if isinstance(obj, datetime) else None

    payload = {'count': len(data),
               'total': len(data),
               '_embedded': data}

    return Response(response=json.dumps((payload), default=dthandler),
                    status=200,
                    mimetype='application/json')


@app.route('/switch', methods=['GET'])
def switch_list():
    switch = SwitchService()

    return hal_response(switch.get_list(request.args.get('fresh', False)))


@app.route('/switch/<key>', methods=['PATCH'])
def switch_toggle(key):
    switch = SwitchService()
    input = json.loads(request.data)
    data = switch.toggle(key,
                         input['state'],
                         input['duration'] if 'duration' in input else None)

    return jsonify(data)


@app.route('/sensor', methods=['GET'])
def sensor_list():
    sensor = SensorService()

    return hal_response(sensor.get_list())


@app.route('/reading', methods=['GET'])
def reading_list():
    if 'since' in request.args:
        since = dateutil.parser.parse(request.args['since'])
    else:
        since = datetime.now() - timedelta(days=1)

    until = None
    if 'until' in request.args:
        until = dateutil.parser.parse(request.args['until'])

    service = StoringService()

    return hal_response(service.get_reading_list(since, until))


@app.route('/history', methods=['GET'])
def history_list():
    page = int(request.args['page']) if 'page' in request.args else 1
    count = int(request.args['count']) if 'count' in request.args else 25
    storing = StoringService()

    return hal_response(storing.get_events_history(page, count))


@app.after_request
def add_cors(resp):
    """ Ensure all responses have the CORS headers.
        This ensures any failures are also accessible by the client. """
    origin = request.headers.get('Origin', '*')
    auth = request.headers.get('Access-Control-Request-Headers',
                               'Authorization')
    resp.headers['Access-Control-Allow-Origin'] = origin
    resp.headers['Access-Control-Allow-Credentials'] = 'true'
    resp.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS, GET, PATCH'
    resp.headers['Access-Control-Allow-Headers'] = auth

    return resp

if not app.debug:
    import logging
    from logging import FileHandler
    file_handler = FileHandler('/tmp/app.log')
    file_handler.setLevel(logging.WARNING)
    app.logger.addHandler(file_handler)

if __name__ != 'pihome-api':  # wsgi
    if __name__ == "__main__" and len(sys.argv) == 1:
        app.run(host='0.0.0.0', port=8999, debug=True)
