"""Assert-based check for Redis outbox enqueue/flush helpers."""
import json
import os
import sys
import tempfile

# Use a fake redis if real one isn't available.
class FakeRedis(object):
    def __init__(self):
        self.lists = {}

    def rpush(self, key, value):
        self.lists.setdefault(key, []).append(value)

    def lpop(self, key):
        lst = self.lists.get(key) or []
        if not lst:
            return None
        return lst.pop(0)

    def lpush(self, key, value):
        self.lists.setdefault(key, []).insert(0, value)


import supabase_client as sc

calls = []

def fake_request(method, table, payload=None, params=None, queue_on_fail=True):
    if table == 'fail':
        if queue_on_fail:
            sc.enqueue(method, table, payload, params)
        return False
    calls.append((method, table, payload))
    return True

fake = FakeRedis()
sc._redis = lambda: fake
sc._request = fake_request
sc._config = lambda: {'url': 'https://example.supabase.co', 'service_role_key': 'x'}

sc.enqueue('POST', 'switch_events', [{'switch': 'a'}])
assert fake.lists[sc.QUEUE_KEY], 'expected queued item'
n = sc.flush_queue()
assert n == 1, n
assert calls[0][1] == 'switch_events'
assert not fake.lists.get(sc.QUEUE_KEY), 'queue should be empty'

sc.enqueue('POST', 'fail', [{'x': 1}])
n = sc.flush_queue()
assert n == 0
assert fake.lists[sc.QUEUE_KEY], 'failed item should remain'
print('test_supabase_queue ok')
