#!/usr/bin/python
import os

from crontab import CronTab
from datetime import datetime, timedelta
from flask import Flask, jsonify, request, Response
import yaml
from sensor import SensorService
from store import StoringService
from switch import SwitchService
import dateutil.parser
import json
import sys
import uuid

app = Flask(__name__)


def hal_response(data):
    def dthandler(obj):
        return obj.isoformat() if isinstance(obj, datetime) else None

    payload = {'count': len(data),
               'total': len(data),
               '_embedded': data}

    return Response(response=json.dumps(payload, default=dthandler),
                    status=200,
                    mimetype='application/json')


@app.route('/switch', methods=['GET'])
def switch_list():
    switch = SwitchService()

    return hal_response(switch.get_list(request.args.get('fresh', False)))


@app.route('/switch/<key>', methods=['PATCH'])
def switch_toggle(key):
    switch = SwitchService()
    input_data = json.loads(request.data)
    duration = timedelta(minutes=int(input_data['duration'])) if 'duration' in input_data else None
    data = switch.toggle(key,
                         input_data['state'],
                         duration)

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
        until = dateutil.parser.parse(request.args['until'] + ' 23:59:59')

    service = StoringService()

    return hal_response(service.get_reading_list(since, until))


@app.route('/history', methods=['GET'])
def history_list():
    page = int(request.args['page']) if 'page' in request.args else 1
    count = int(request.args['count']) if 'count' in request.args else 25
    storing = StoringService()

    return hal_response(storing.get_events_history(page, count))


@app.route('/cron', methods=['GET'])
def cron_list():
    cron = CronTab(user=True)
    result = []

    path = os.path.dirname(os.path.realpath(__file__)) + '/config.yml'
    config = yaml.load(file(path))['switch']
    for job in cron:
        if job.comment.find('pihome-api') != -1:
            task_data = json.loads(job.comment.replace('pihome-api ', ''))
            task_data['name'] = config['devices'][task_data['switch']]['name']
            result.append(task_data)

    return hal_response(result)


@app.route('/cron', methods=['POST'])
def cron_create():
    input_data = json.loads(request.data)
    new_id = str(uuid.uuid4())
    command = 'curl localhost/api/switch/%s -XPATCH -d \'{"state": "%d", "duration": "%d"}\'  -H \'Content-Type: application/json\'' % (
        input_data['switch'], input_data['state'], int(input_data['duration']))
    cron = CronTab(user=True)
    job = cron.new(command=command)
    job.setall(input_data["schedule"])
    comment = {
        'id': new_id,
        'switch': input_data['switch'],
        'state': input_data['state'],
        'duration': input_data['duration'] if 'duration' in input_data else 0,
        'schedule': job.slices.render(),
    }
    job.comment = 'pihome-api ' + json.dumps(comment)
    cron.write()

    return jsonify(comment)


@app.route('/cron/<cron_id>', methods=['DELETE'])
def cron_delete(cron_id):
    cron = CronTab(user=True)
    for job in cron:
        if job.comment.find(cron_id) != -1:
            cron.remove(job)
            cron.write()

    return ''


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
