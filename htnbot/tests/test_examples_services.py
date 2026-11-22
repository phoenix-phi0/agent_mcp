import json
from pathlib import Path

from planbot import core, executor, planner
from planbot.cli import main
from planbot.memory import Memory

DOMAIN = str(Path(__file__).resolve().parent.parent / 'examples' / 'services' / 'domain.json')
sim = core.load_python(str(Path(DOMAIN).with_name('sim.py')))
CHAIN = {'web': ['api'], 'api': ['db'], 'db': []}


def _setup(running=(), locked=()):
    sim.reset(CHAIN, running=running, locked=locked)
    domain = core.load_domain(DOMAIN)
    goal = core.parse_goal(domain, ['running(web)'])
    return domain, goal, planner.allowed_actions(domain, None, None)


def test_plan_follows_dependency_order_with_reasons():
    domain, goal, allowed = _setup()
    plan = executor.dry_run(domain, goal, allowed)['plan']
    assert plan['found'] and [s['text'] for s in plan['steps']] == ['start(db)', 'start(api)', 'start(web)']
    first, last = plan['steps'][0]['reasons'], plan['steps'][-1]['reasons']
    assert {'literal': 'not blocked(api)', 'for_step': 2, 'for_text': 'start(api)'} in first
    assert last == [{'literal': 'running(web)', 'for_step': None, 'for_text': 'goal'}]
    assert sim.calls() == []


def test_single_fault_replans_and_succeeds():
    domain, goal, allowed = _setup()
    sim.set_fault('start', 'api', 1)
    report = executor.execute(domain, goal, allowed)
    assert report['status'] == 'done' and report['replans'] == 1
    assert sim.calls().count(('start', 'api')) == 2


def test_persistent_fault_hits_replan_limit():
    domain, goal, allowed = _setup()
    sim.set_fault('start', 'db', 1000)
    report = executor.execute(domain, goal, allowed)
    assert report['status'] == 'stuck'
    assert report['stuck']['reason'] == 'replan_limit'
    assert report['stuck']['step'] == 'start(db)'
    assert 'running(db)' in report['stuck']['missing']


def test_locked_goal_service_is_blocked():
    domain, goal, allowed = _setup(locked=['web'])
    plan = executor.dry_run(domain, goal, allowed)['plan']
    assert plan['found'] is False
    assert plan['failure']['kind'] == 'blocked'
    assert any('not locked(web)' in d['missing'] for d in plan['failure']['details'])


def test_memory_hit_and_no_memory(tmp_path):
    domain, goal, allowed = _setup()
    memory = Memory(str(tmp_path / 'mem.json'))
    report = executor.execute(domain, goal, allowed, memory=memory)
    assert report['status'] == 'done' and report['saved_to_memory'] is True
    _setup()
    assert executor.dry_run(domain, goal, allowed, memory=memory)['plan']['source'] == 'memory'
    assert executor.dry_run(domain, goal, allowed, memory=None)['plan']['source'] == 'search'


def test_cli_text_and_json(tmp_path, capsys):
    _setup()
    argv = ['run', '--domain', DOMAIN, '--goal', 'running(web)', '--memory-file', str(tmp_path / 'mem.json')]
    assert main([*argv, '--execute']) == 0
    out = capsys.readouterr().out
    assert 'plan: 3 steps (source: search)' in out and 'status: done' in out
    assert sim.calls() == [('start', 'db'), ('start', 'api'), ('start', 'web')]
    _setup()
    assert main([*argv, '--json']) == 0
    data = json.loads(capsys.readouterr().out)
    assert data['mode'] == 'dry-run' and data['plan']['source'] == 'memory'
    assert [s['text'] for s in data['plan']['steps']] == ['start(db)', 'start(api)', 'start(web)']
