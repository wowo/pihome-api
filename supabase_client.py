"""Minimal Supabase PostgREST client with Redis offline queue.

ponytail: at-least-once queue via Redis list; upgrade to outbox table if volume grows.
HTTPS goes through curl under eventlet because requests/urllib3 SSL breaks
(wrap_socket ... _context) inside the gunicorn eventlet worker.
"""
from __future__ import absolute_import, print_function

import json
import logging
import os
import subprocess
import sys
from datetime import datetime

import yaml

try:
    from urllib.parse import urlencode
except ImportError:
    from urllib import urlencode

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


def _use_curl():
    # eventlet monkey-patches break requests HTTPS on this Pi stack
    return 'eventlet' in sys.modules


def _http(method, url, headers, payload=None, params=None, timeout=8):
    """Return (status_code, body_text)."""
    if params:
        url = url + ('&' if '?' in url else '?') + urlencode(params, doseq=True)
    body = None if payload is None else json.dumps(payload, default=str)

    if _use_curl():
        return _http_curl(method, url, headers, body, timeout)

    import requests
    res = requests.request(method, url, headers=headers, data=body, timeout=timeout)
    return res.status_code, res.text


def _http_curl(method, url, headers, body, timeout):
    cmd = [
        'curl', '-sS', '-X', method,
        '--max-time', str(timeout),
        '-w', '\n%{http_code}',
    ]
    for k, v in headers.items():
        if v is not None:
            cmd.extend(['-H', '%s: %s' % (k, v)])
    if body is not None:
        cmd.extend(['--data-binary', body])
    cmd.append(url)
    out = subprocess.check_output(cmd)
    text = out.decode('utf-8', 'replace')
    if '\n' not in text:
        return 0, text
    body_text, status_s = text.rsplit('\n', 1)
    try:
        status = int(status_s.strip())
    except ValueError:
        status = 0
    return status, body_text


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
        status, text = _http(method, _url(table), _headers(True), payload=payload, params=params)
        if status >= 400:
            raise RuntimeError('supabase %s %s -> %s %s' % (method, table, status, text[:200]))
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
    return _request('POST', table, rows, params=params)


def select_rows(table, params=None):
    """Read rows (service role). Returns list or [] on failure; does not enqueue."""
    cfg = _config()
    if not cfg.get('url') or not cfg.get('service_role_key'):
        return []
    try:
        status, text = _http('GET', _url(table), _headers(True), params=params or {})
        if status >= 400:
            raise RuntimeError('supabase GET %s -> %s %s' % (table, status, text[:200]))
        data = json.loads(text) if text else []
        return data if isinstance(data, list) else []
    except Exception as e:
        logging.warning('supabase select failed: %s', e)
        return []


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
    status, text = _http('GET', url, {}, timeout=8)
    if status >= 400:
        raise RuntimeError('jwks fetch failed: %s %s' % (status, text[:200]))
    data = json.loads(text)
    with open(JWKS_PATH, 'w') as f:
        json.dump(data, f)
    return data
