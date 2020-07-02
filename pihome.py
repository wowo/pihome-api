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
import jwt
import logging
from logging.handlers import RotatingFileHandler
from flask_socketio import SocketIO, join_room, emit
from threading import Lock
import timeit

app = Flask(__name__)
socketio = SocketIO(app)
thread_sensors = None
thread_switches = None
thread_lock_switches = Lock()
thread_lock_sensors = Lock()

SENSORS_SLEEP = 10
SWITCHES_SLEEP = 10
sensors_data = {}
switches_data = {}

def emit_sensors(sid):
    with app.test_request_context():
        service = SensorService()
        sensors = service.get_list(with_readings=False)
        while True:
            for key in sensors:
                data = service.get_sensor_data(key, with_readings=True)
                sensors_data[data['key']] = data
                socketio.emit('sensor', data, include_self=False, skip_sid=2)
            socketio.sleep(SENSORS_SLEEP)

def emit_switches(sid):
    with app.test_request_context():
        service = SwitchService()
        while True:
            for data in service.get_list(True).values():
                switches_data[data['key']] = data
                socketio.emit('switch', data, include_self=False, skip_sid=2)
            socketio.sleep(SWITCHES_SLEEP)

@socketio.on('connect')
def on_connect():
    print('Socket connected')
    logging.warning('socket connected. cached sensors: {}, cached switches: {}'.format(len(sensors_data.keys()), len(switches_data.keys())))
    for data in sensors_data.values():
        socketio.emit('sensor', data, include_self=False)

    for data in switches_data.values():
        socketio.emit('switch', data, include_self=False)

    global thread_sensors
    global thread_switches
    with thread_lock_sensors:
        if thread_sensors is None:
            thread_sensors = socketio.start_background_task(target=emit_sensors)
    with thread_lock_switches:
        if thread_switches is None:
            thread_switches = socketio.start_background_task(target=emit_switches)

def hal_response(data):
    def dthandler(obj):
        return obj.isoformat() if isinstance(obj, datetime) else None

    payload = {'count': len(data),
               'total': len(data),
               '_embedded': data}

    return Response(response=json.dumps(payload, default=dthandler),
                    status=200,
                    mimetype='application/json')


@app.route('/ping', methods=['get'])
def ping():
    return Response(response="pong")

@app.route('/switch', methods=['get'])
def switch_list():
    logging.warning('/switch starting') 
    start_main = timeit.default_timer()
    switch = SwitchService()
    res = hal_response(switch.get_list(request.args.get('fresh', False)))
    logging.warning('/switch endpoint %.3fs' % (timeit.default_timer() - start_main))

    return res


@app.route('/switch/<key>', methods=['PATCH'])
def switch_toggle(key):
    input_data = json.loads(request.data)
    app.logger.warning('switch toggle %s by %s new state: %s, duration: %s' % (key, get_authenticated_user(request), input_data['state'], input_data['duration'] if 'duration' in input_data else None))
    switch = SwitchService()
    duration = timedelta(minutes=int(input_data['duration'])) if 'duration' in input_data else None
    try:
        state = int(input_data['state'])
    except ValueError:
        state = input_data['state']

    data = switch.toggle(key,
                         state,
                         duration,
                         get_authenticated_user(request))

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
    config = yaml.load(open(path).read(), Loader=yaml.FullLoader)['switch']
    for job in cron:
        if job.comment.find('pihome-api') != -1:
            task_data = json.loads(job.comment.replace('pihome-api ', ''))
            task_data['name'] = config['devices'][task_data['switch']]['name']
            if '@hourly' == task_data['schedule']:
                task_data['schedule'] = '0 * * * *'
            elif '@daily' == task_data['schedule']:
                task_data['schedule'] = '0 0 * * *'
            elif '@weekly' == task_data['schedule']:
                task_data['schedule'] = '0 0 * * 0'
            elif '@monthly' == task_data['schedule']:
                task_data['schedule'] = '0 0 1 * *'

            result.append(task_data)

    result = sorted(result, key=lambda x: x['name'])
    return hal_response(result)


@app.route('/cron', methods=['POST'])
def cron_create():
    input_data = json.loads(request.data)

    cron = CronTab(user=True)
    job = cron.new(command=get_cron_command(input_data))
    job.setall(input_data["schedule"])
    job.comment = 'pihome-api ' + get_cron_comment(input_data, job)
    cron.write()

    logging.warning(job.comment)

    return get_cron_comment(input_data, job)


@app.route('/cron/<cron_id>', methods=['PUT'])
def cron_edit(cron_id):
    input_data = json.loads(request.data)

    cron = CronTab(user=True)
    for job in cron:
        if job.comment.find(cron_id) != -1:
            job.setall(input_data["schedule"])
            job.command = get_cron_command(input_data)
            job.comment = 'pihome-api ' + get_cron_comment(input_data, job)
            cron.write()

            return get_cron_comment(input_data, job)


def get_cron_comment(input_data, job):
    comment = {
        'id': str(uuid.uuid4()),
        'switch': input_data['switch'],
        'state': input_data['state'],
        'schedule': job.slices.render(),
    }
    if 'duration' in input_data:
        comment['duration'] = int(input_data['duration'])

    return json.dumps(comment)


def get_cron_command(input_data):
    payload = {
        'state': input_data['state']
    }
    if 'duration' in input_data:
        payload['duration'] = int(input_data['duration'])

    pattern = 'curl localhost/api/switch/%s -XPATCH -d \'%s\' -H \'Content-Type: application/json\''
    return pattern % (input_data['switch'], json.dumps(payload))

def get_authenticated_user(request):
    if 'CF_Authorization' not in request.cookies:
        return None

    token = jwt.decode(request.cookies.get('CF_Authorization'), verify=False)
    return token['email']

@app.route('/cron/<cron_id>', methods=['DELETE'])
def cron_delete(cron_id):
    cron = CronTab(user=True)
    for job in cron:
        if job.comment.find(cron_id) != -1:
            cron.remove(job)
            cron.write()

    return ''


if __name__ != 'pihome-api':  # wsgi
    if __name__ == "__main__" and len(sys.argv) == 1:
        handler = RotatingFileHandler('/tmp/app.log', maxBytes=10000, backupCount=2)
        handler.setLevel(logging.INFO)
        app.logger.addHandler(handler)
        app.run(host='0.0.0.0', port=8999, debug=True)
    elif len(sys.argv) > 1 and sys.argv[1] == '--store-sensors':
        print('> Store sensors state ' + datetime.now().strftime('%Y-%m-%d %H:%M'))
        service = StoringService()
        service.store_sensors_state()
