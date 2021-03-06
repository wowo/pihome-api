#!/usr/bin/env python3
"""
virtualenv -p python3 venv
source venv/bin/activate
pip install -r requirements.txt
gunicorn sockets:app --bind 0.0.0.0:5000 --worker-class eventlet -w 1 --access-logfile gunicorn.log --log-level DEBUG --reload  --forwarded-allow-ips  "*"
"""

from flask import Flask
from flask_socketio import SocketIO, join_room, emit
from threading import Lock
from sensor import SensorService
from OpenSSL import SSL

app = Flask(__name__)
socketio = SocketIO(app)
thread = None
thread_lock = Lock()


@app.route('/')
def index():
    return 'Nothing to see here'


def background_thread():
    sensor = SensorService()
    sensors = sensor.get_list(with_readings=False)
    while True:
        socketio.sleep(1)
        for key in sensors:
            data = sensor.get_sensor_data(key, with_readings=True)
            print(data)
            socketio.emit('sensors', data)


@socketio.on('connect')
def on_connect():
    global thread
    with thread_lock:
        if thread is None:
            thread = socketio.start_background_task(target=background_thread)
    sensor = SensorService()
    data = list(sensor.get_list(with_readings=False).values())
    print('--------------------------------------------------------------------------------')
    print('Socket.io connect')
    emit('sensors', {'all_sensors': data})

if __name__ == '__main__':
    context = SSL.Context(SSL.SSLv23_METHOD)
    context.use_privatekey_file('/etc/letsencrypt/live/pihome.sznapka.pl/privkey.pem')
    context.use_certificate_file('/etc/letsencrypt/live/pihome.sznapka.pl/fullchain.pem')
    socketio.run(app, debug=True, host='0.0.0.0', port=5005)
