#!/usr/bin/python
"""Persistence via Supabase. Mongo kept only for one-off migration scripts."""

from datetime import datetime
import logging
import os
import sys
import traceback

import yaml

from supabase_client import flush_queue, insert_rows, select_rows, upsert_rows

DATE_FORMAT = '%Y-%m-%d %H:%M'


class StoringService:
    def __init__(self):
        path = os.path.dirname(os.path.realpath(__file__)) + '/config.yml'
        self.base_config = yaml.load(open(path), Loader=yaml.FullLoader)

    def store_switch_state(self, sensor_key, new_state, date, user):
        row = {
            'date': date.isoformat() if isinstance(date, datetime) else str(date),
            'switch': sensor_key,
            'state': str(new_state),
            'user_email': user,
        }
        insert_rows('switch_events', [row])

    def upsert_switch_state(self, info):
        """Mirror live switch info into switch_state for Realtime subscribers."""
        row = {
            'key': info['key'],
            'state': None if info.get('state') is None else str(info.get('state')),
            'scheduled': info.get('scheduled'),
            'updated_at': datetime.utcnow().isoformat() + 'Z',
            'name': info.get('name'),
            'type': info.get('type'),
            'stateless': bool(info.get('stateless')),
            'durations': info.get('durations') if info.get('durations') else None,
        }
        upsert_rows('switch_state', [row], on_conflict='key')

    def flush_outbox(self):
        n = flush_queue()
        print('> flushed %s supabase outbox items' % n)
        return n

    def list_switch_events(self, page=1, count=25):
        """LAN / legacy clients: page switch_events from Supabase (service role)."""
        page = max(1, int(page or 1))
        count = max(1, min(100, int(count or 25)))
        offset = (page - 1) * count
        rows = select_rows(
            'switch_events',
            {
                'select': 'id,date,switch,state,user_email',
                'order': 'date.desc',
                'offset': offset,
                'limit': count,
            },
        )
        names = {
            k: v.get('name', k)
            for k, v in (self.base_config.get('switch') or {}).get('devices', {}).items()
        }
        out = []
        for row in rows:
            out.append({
                'id': row.get('id'),
                'date': row.get('date'),
                'switch': row.get('switch'),
                'state': row.get('state'),
                'user': row.get('user_email'),
                'user_email': row.get('user_email'),
                'name': names.get(row.get('switch'), row.get('switch')),
            })
        return out

    # Legacy CLI entrypoints kept as no-ops so existing cron lines don't crash.
    def store_sensors_state(self):
        print('> store-sensors retired (sensors out of MVP)')

    def cache_sensors_state(self):
        print('> cache-sensors retired (sensors out of MVP)')


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--flush-outbox':
        StoringService().flush_outbox()
