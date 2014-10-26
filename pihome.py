#!/usr/bin/python

from flask import Flask, jsonify, request
from switch import SwitchService

app = Flask(__name__)

@app.route('/switch', methods = ['GET'])
def switch_list():
    switch = SwitchService()
    data = switch.get_list()

    return jsonify({'count': len(data), 'total': len(data), '_embedded': data})


@app.route('/switch/<key>', methods = ['PATCH'])
def switch_toggle(key):
    switch = SwitchService()
    data = switch.toggle(key, request.values.get('state'))

    return jsonify(data)


if __name__ != 'pihome-api': # wsgi
    if __name__ == "__main__" and len(sys.argv) == 1:
        app.run(host='0.0.0.0', port=8999, debug=True)
