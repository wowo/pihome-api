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

app.run(host='0.0.0.0', port=8999, debug=True)
