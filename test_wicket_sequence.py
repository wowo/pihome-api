#!/usr/bin/env python3
"""Self-check: Furtka phase ETAs and transitions (no GPIO)."""
from datetime import datetime, timedelta
import json
import sys
import types


def _stub_heavy_imports():
    """Avoid needing redis/celery/yaml installed just to exercise ClickSequenceSwitch."""
    if 'redis' not in sys.modules:
        m = types.ModuleType('redis')
        m.StrictRedis = object
        sys.modules['redis'] = m
    if 'celery' not in sys.modules:
        celery = types.ModuleType('celery')

        class Celery(object):
            def __init__(self, *a, **k):
                pass

            def config_from_object(self, *a, **k):
                pass

            def task(self, f=None, **k):
                if f:
                    return f
                return lambda fn: fn

        celery.Celery = Celery
        sys.modules['celery'] = celery
        control = types.ModuleType('celery.task.control')
        control.revoke = lambda *a, **k: None
        sys.modules['celery.task'] = types.ModuleType('celery.task')
        sys.modules['celery.task.control'] = control
    if 'celeryconfig' not in sys.modules:
        sys.modules['celeryconfig'] = types.ModuleType('celeryconfig')
    if 'yaml' not in sys.modules:
        yaml = types.ModuleType('yaml')
        yaml.load = lambda *a, **k: {}
        yaml.FullLoader = object
        sys.modules['yaml'] = yaml
    if 'jwt' not in sys.modules:
        sys.modules['jwt'] = types.ModuleType('jwt')
    if 'requests' not in sys.modules:
        sys.modules['requests'] = types.ModuleType('requests')


class FakeRedis:
    def __init__(self):
        self.d = {}

    def get(self, k):
        return self.d.get(k)

    def set(self, k, v):
        self.d[k] = v

    def delete(self, k):
        self.d.pop(k, None)


class FakeAsync:
    def __init__(self, tid):
        self.id = tid


def main():
    _stub_heavy_imports()
    import switch as sw

    pulses = []
    scheduled = []
    counter = [0]

    def fake_pulse(self, user):
        pulses.append((self.switch_id, user))

    def fake_apply(args, eta=None):
        counter[0] += 1
        tid = 't%d' % counter[0]
        scheduled.append((args, eta, tid))
        return FakeAsync(tid)

    def fake_revoke(tid, Terminate=False):
        scheduled[:] = [s for s in scheduled if s[2] != tid]

    cache = FakeRedis()
    seq = [{'switch': 'gate_main', 'pin': 6}]
    driver = sw.ClickSequenceSwitch('gate_main_door_mode', seq, cache, 5, 60, 5)

    sw.ClickSequenceSwitch._pulse = fake_pulse
    import tasks
    tasks.wicket_step.apply_async = fake_apply
    sw.revoke = fake_revoke

    before = datetime.utcnow()
    driver.set_state('click', 'user')
    assert pulses == [('gate_main_door_mode', 'user')], pulses
    data = json.loads(cache.get('wicket:gate_main_door_mode'))
    assert data['phase'] == 'opening'
    ends = datetime.strptime(data['ends_at'].rstrip('Z').split('.')[0], '%Y-%m-%dT%H:%M:%S')
    delta = (ends - before.replace(microsecond=0)).total_seconds()
    assert 4 <= delta <= 6, delta
    assert len(data['task_ids']) == 2
    assert len(scheduled) == 2
    stop_eta = scheduled[0][1]
    close_eta = scheduled[1][1]
    assert 4 <= (stop_eta - before).total_seconds() <= 6
    assert 64 <= (close_eta - before).total_seconds() <= 66

    sched = driver.get_sequence_scheduled()
    assert sched['kind'] == 'wicket' and sched['phase'] == 'opening'
    assert sched['open_s'] == 5 and sched['wait_s'] == 60

    # Opening: ignore
    driver.set_state('click', 'user')
    assert len(pulses) == 1

    # stop → waiting
    driver.run_step('stop')
    assert len(pulses) == 2
    data = json.loads(cache.get('wicket:gate_main_door_mode'))
    assert data['phase'] == 'waiting'
    assert len(data['task_ids']) == 1  # close remains

    # early close
    before2 = datetime.utcnow()
    driver.set_state('click', 'user')
    assert len(pulses) == 3
    data = json.loads(cache.get('wicket:gate_main_door_mode'))
    assert data['phase'] == 'closing'
    ends = datetime.strptime(data['ends_at'].rstrip('Z').split('.')[0], '%Y-%m-%dT%H:%M:%S')
    delta = (ends - before2.replace(microsecond=0)).total_seconds()
    assert 4 <= delta <= 6, delta

    # closing: ignore
    driver.set_state('click', 'user')
    assert len(pulses) == 3

    driver.run_step('clear')
    assert cache.get('wicket:gate_main_door_mode') is None
    assert driver.get_sequence_scheduled() is None

    # Natural close path
    pulses[:] = []
    scheduled[:] = []
    counter[0] = 0
    driver.set_state('click', 'user')
    driver.run_step('stop')
    driver.run_step('close')
    data = json.loads(cache.get('wicket:gate_main_door_mode'))
    assert data['phase'] == 'closing'
    assert len(pulses) == 3  # start + stop + close

    print('ok')
    return 0


if __name__ == '__main__':
    sys.exit(main())
