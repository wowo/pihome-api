#!/usr/bin/python

from flask import Flask, jsonify, request
from switch import SwitchService

app = Flask(__name__)

@app.route('/switch', methods = ['GET'])
def switch_list():
    switch = SwitchService()
    data = switch.get_list()

    response = jsonify({'count': len(data), 'total': len(data), '_embedded': data})
    response.headers['Access-Control-Allow-Origin'] = '*'

    return response

@app.route('/switch/<key>', methods = ['OPTIONS'])
def switch_options(key):
    response = jsonify({})
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET,PATCH'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'

    return response
@app.route('/switch/<key>', methods = ['PATCH'])
def switch_toggle(key):
    switch = SwitchService()
    data = switch.toggle(key, request.values.get('state'))

    response = jsonify(data)
    response.headers['Access-Control-Allow-Origin'] = '*'

    return response


app.run(host='0.0.0.0', port=8999, debug=True)
