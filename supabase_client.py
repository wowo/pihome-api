"""Minimal Supabase PostgREST client with Redis offline queue.

ponytail: at-least-once queue via Redis list; upgrade to outbox table if volume grows.
"""
from __future__ import absolute_import, print_function

import json
import logging
import os
from datetime import datetime

import requests
import yaml

QUEUE_KEY = 'supabase_outbox'
JWKS_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), '.supabase_jwks.json')


def _config():
    path = os.path.dirname(os.path.realpath(__file__)) + '/config.yml'
    cfg = yaml.load(open(path), Loader=yaml.FullLoader)
    return cfg.get('storing', {}).get('supabase', {})


def _redis():
    import redis
    return redis.StrictRedis(host='localhost', port=6379, db=0)


def _headers(service=True):
    cfg = _config()
    key = cfg.get('service_role_key') if service else cfg.get('anon_key')
    return {
        'apikey': key,
        'Authorization': 'Bearer ' + key,
        'Content-Type': 'application/json',
        'Prefer': 'resolution=merge-duplicates,return=minimal',
    }


def _url(table):
    cfg = _config()
    return cfg['url'].rstrip('/') + '/rest/v1/' + table


def enqueue(method, table, payload, params=None):
    item = {
        'method': method,
        'table': table,
        'payload': payload,
        'params': params or {},
        'queued_at': datetime.utcnow().isoformat() + 'Z',
    }
    _redis().rpush(QUEUE_KEY, json.dumps(item, default=str))


def _request(method, table, payload=None, params=None, queue_on_fail=True):
    cfg = _config()
    if not cfg.get('url') or not cfg.get('service_role_key'):
        logging.warning('supabase not configured; enqueue skipped for %s %s', method, table)
        return False
    try:
        res = requests.request(
            method,
            _url(table),
            headers=_headers(True),
            params=params,
            json=payload,
            timeout=8,
        )
        if res.status_code >= 400:
            raise RuntimeError('supabase %s %s -> %s %s' % (method, table, res.status_code, res.text[:200]))
        return True
    except Exception as e:
        logging.warning('supabase request failed: %s', e)
        if queue_on_fail:
            enqueue(method, table, payload, params)
        return False


def insert_rows(table, rows):
    if not rows:
        return True
    return _request('POST', table, rows)


def upsert_rows(table, rows, on_conflict='key'):
    if not rows:
        return True
    params = {'on_conflict': on_conflict}
    # Prefer header already set for merge-duplicates
    return _request('POST', table, rows, params=params)


def flush_queue(max_items=50):
    """Pop and retry queued writes. Returns number flushed."""
    r = _redis()
    flushed = 0
    for _ in range(max_items):
        raw = r.lpop(QUEUE_KEY)
        if not raw:
            break
        item = json.loads(raw)
        ok = _request(
            item['method'],
            item['table'],
            item.get('payload'),
            item.get('params'),
            queue_on_fail=False,
        )
        if ok:
            flushed += 1
        else:
            # put back at head and stop to preserve order
            r.lpush(QUEUE_KEY, raw)
            break
    return flushed


def fetch_jwks(force=False):
    """Download and cache project JWKS for offline JWT verify."""
    cfg = _config()
    if not force and os.path.exists(JWKS_PATH):
        return json.load(open(JWKS_PATH))
    url = cfg.get('jwks_url') or (cfg.get('url', '').rstrip('/') + '/auth/v1/.well-known/jwks.json')
    res = requests.get(url, timeout=8)
    res.raise_for_status()
    data = res.json()
    with open(JWKS_PATH, 'w') as f:
        json.dump(data, f)
    return data
