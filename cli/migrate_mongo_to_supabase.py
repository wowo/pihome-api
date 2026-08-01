#!/usr/bin/env python3
"""One-off: Mongo switches/temperatures/light -> Supabase switch_events/readings.

Usage (on a machine that can reach Mongo + Supabase):
  SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... \\
  MONGO_URI=mongodb://user:pass@host:port/pithermo \\
  python cli/migrate_mongo_to_supabase.py

Or set storing.mongo / storing.supabase in config.yml and run from repo root.
"""
from __future__ import print_function

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml
import requests
from pymongo import MongoClient


def load_cfg():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.yml')
    if os.path.exists(path):
        return yaml.load(open(path), Loader=yaml.FullLoader)
    return {}


def supabase_insert(url, key, table, rows):
    if not rows:
        return
    endpoint = url.rstrip('/') + '/rest/v1/' + table
    # chunk to keep payloads small
    for i in range(0, len(rows), 200):
        chunk = rows[i:i + 200]
        res = requests.post(
            endpoint,
            headers={
                'apikey': key,
                'Authorization': 'Bearer ' + key,
                'Content-Type': 'application/json',
                'Prefer': 'return=minimal',
            },
            json=chunk,
            timeout=60,
        )
        if res.status_code >= 400:
            raise SystemExit('insert %s failed: %s %s' % (table, res.status_code, res.text[:500]))
        print('  inserted %s rows into %s (%s/%s)' % (len(chunk), table, i + len(chunk), len(rows)))


def main():
    cfg = load_cfg()
    mongo_cfg = cfg.get('storing', {}).get('mongo', {})
    sb = cfg.get('storing', {}).get('supabase', {})
    url = os.environ.get('SUPABASE_URL') or sb.get('url')
    key = os.environ.get('SUPABASE_SERVICE_ROLE_KEY') or sb.get('service_role_key')
    if not url or not key:
        raise SystemExit('Need SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY')

    mongo_uri = os.environ.get('MONGO_URI')
    if mongo_uri:
        client = MongoClient(mongo_uri)
        db = client.get_default_database()
    else:
        client = MongoClient(mongo_cfg['host'], mongo_cfg['port'])
        db = client[mongo_cfg['collection']]
        if mongo_cfg.get('user'):
            db.authenticate(mongo_cfg['user'], mongo_cfg['pass'], source='admin')

    print('Migrating switch_events...')
    events = []
    # No .sort() — old Mongo sort buffer is tiny; order doesn't matter for insert.
    for doc in db.switches.find(no_cursor_timeout=True).batch_size(200):
        events.append({
            'date': doc['date'].isoformat() if hasattr(doc['date'], 'isoformat') else str(doc['date']),
            'switch': doc.get('switch'),
            'state': str(doc.get('state')),
            'user_email': doc.get('user'),
        })
        if len(events) >= 500:
            supabase_insert(url, key, 'switch_events', events)
            events = []
    supabase_insert(url, key, 'switch_events', events)

    print('Migrating readings (temperatures + light)...')
    for collection, kind, value_key in (
        ('temperatures', 'temperature', 'temperature'),
        ('light', 'light', 'value'),
    ):
        readings = []
        print('  collection', collection)
        for doc in db[collection].find(no_cursor_timeout=True).batch_size(100):
            date = doc['date'].isoformat() if hasattr(doc['date'], 'isoformat') else str(doc['date'])
            for _addr, sensor in (doc.get('sensors') or {}).items():
                val = sensor.get(value_key)
                if val is None:
                    continue
                readings.append({
                    'date': date,
                    'sensor_key': sensor.get('id') or sensor.get('name') or _addr,
                    'value': val,
                    'kind': kind,
                })
            if len(readings) >= 500:
                supabase_insert(url, key, 'readings', readings)
                readings = []
        supabase_insert(url, key, 'readings', readings)
    print('Done.')


if __name__ == '__main__':
    main()
