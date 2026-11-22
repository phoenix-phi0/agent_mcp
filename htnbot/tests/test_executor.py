import json
from collections import Counter
from pathlib import Path

import pytest

from planbot.core import PlanbotError, format_atom, load_domain, parse_literal
from planbot import executor
from planbot.executor import dry_run, execute, resolve_plan
from planbot.memory import Memory
from planbot.runtime import observe


def _load(tmp_path, facts=(('p', 'x'),), missed_effects=None):
    state = {'facts': set(facts)}
    calls = Counter()
    missed_effects = dict(missed_effects or {})

    def sensor(ctx):
        calls['sense'] += 1
        return '\n'.join(sorted(map(format_atom, state['facts'])))

    def prepare(binding, ctx):
        calls['prepare'] += 1
        if calls['prepare'] > missed_effects.get('prepare', 0):
            state['facts'].add(('stage',))

    def finish(binding, ctx):
        calls['finish'] += 1
        if calls['finish'] > missed_effects.get('finish', 0):
            state['facts'].add(('done', binding['x']))
            state['facts'].discard(('marker',))

    data = {
        'name': 'mini', 'objects': ['x', 'y'],
        'predicates': {'p': 1, 'blocked': 0, 'stage': 0, 'done': 1, 'marker': 0, 'other': 0},
        'derived': [{'head': 'ready()', 'body': ['p(x)', 'not blocked()']}],
        'sensors': [{'name': 'sense', 'run': {'callback': 'sense'}, 'extract': [
            {'type': 'regex', 'pattern': r'^(.+)$', 'facts': ['{1}']},
        ]}],
        'actions': [
            {'name': 'prepare', 'params': [], 'pre': ['ready()'], 'add': ['stage()'],
             'del': [], 'run': {'callback': 'prepare'}},
            {'name': 'finish', 'params': ['x'], 'pre': ['stage()'], 'add': ['done(?x)'],
             'del': ['marker()'], 'run': {'callback': 'finish'}},
        ],
        'goals': ['done', 'ready'],
    }
    path = tmp_path / 'domain.json'
    path.write_text(json.dumps(data), encoding='utf-8')
    callbacks = {'sense': sensor, 'prepare': prepare, 'finish': finish}
    return load_domain(str(path), callbacks=callbacks), state, calls


def test_memory_replaces_entry_at_front(tmp_path):
    domain, _, _ = _load(tmp_path)
    path = tmp_path / 'memory.json'
    memory = Memory(str(path))
    goal = (parse_literal('done(x)'),)
    start_a = frozenset({('p', 'x')})
    start_b = start_a | {('stage',)}
    steps = [['prepare', []], ['finish', ['x']]]
    entry_a = {
        'domain': 'mini', 'goal': ['done(x)'], 'predicates': ['blocked', 'done', 'marker', 'p', 'stage'],
        'start': ['p(x)'], 'steps': steps,
    }
    entry_b = {**entry_a, 'start': ['p(x)', 'stage()']}
    memory.save(domain, goal, start_a, steps)
    memory.save(domain, goal, start_b, steps)
    assert memory.list() == [entry_b, entry_a]

    replacement = {**entry_a, 'steps': [['prepare', []]], 'predicates': ['blocked', 'done', 'p', 'stage']}
    memory.save(domain, goal, start_a, replacement['steps'])
    assert Memory(str(path)).list() == [replacement, entry_b]
    assert path.read_text(encoding='utf-8').strip() == json.dumps(
        {'entries': [replacement, entry_b]}, sort_keys=True,
    )


def test_memory_matches_relevant_facts_in_file_order(tmp_path):
    domain, _, _ = _load(tmp_path)
    memory = Memory(str(tmp_path / 'memory.json'))
    goal = (parse_literal('ready()'), parse_literal('not done(y)'))
    base = observe(domain)['base'] | {('marker',)}
    first = [['prepare', []], ['finish', ['x']]]
    second = [['prepare', []]]
    memory.save(domain, goal, base, first)
    memory.save(domain, goal, base, second)
    assert memory.list()[0]['goal'] == ['not done(y)', 'ready()']
    assert memory.candidates(domain, goal[::-1], base) == [second, first]
    assert memory.candidates(domain, goal, base | {('other',)}) == [second, first]
    assert memory.candidates(domain, goal, base - {('marker',)}) == [second]
    assert memory.candidates(domain, goal, base | {('blocked',)}) == []
    assert memory.candidates(domain, goal, base - {('p', 'x')}) == []
    assert memory.candidates(domain, (parse_literal('ready()'),), base) == []
    domain.name = 'different'
    assert memory.candidates(domain, goal, base) == []


def test_memory_missing_file_and_clear(tmp_path):
    domain, _, _ = _load(tmp_path)
    path = tmp_path / 'nested' / 'memory.json'
    memory = Memory(str(path))
    goal = (parse_literal('done(x)'),)
    base = frozenset()
    assert memory.candidates(domain, goal, base) == []
    assert memory.list() == []
    assert memory.clear() == 0
    assert not path.exists()

    memory.save(domain, goal, base, [['finish', ['x']]])
    assert path.is_file()
    assert memory.candidates(domain, goal, base) == [[['finish', ['x']]]]
    assert memory.clear() == 1
    assert json.loads(path.read_text(encoding='utf-8')) == {'entries': []}
    assert memory.list() == []


@pytest.mark.parametrize('content', ['not json', '[]', '{}', '{"entries": {}}',
                                    '{"entries": [null]}', '{"entries": [{}]}',
                                    '{"entries": [{"domain": "mini", "goal": [], "predicates": [],'
                                    ' "start": [], "steps": [["prepare", null]]}]}'])
def test_memory_rejects_invalid_file(tmp_path, content):
    path = tmp_path / 'memory.json'
    path.write_text(content, encoding='utf-8')
    with pytest.raises(PlanbotError) as exc:
        Memory(str(path)).list()
    assert exc.value.code == 'USAGE'


def test_dry_run_observes_once_without_actions_or_memory_write(tmp_path):
    domain, _, calls = _load(tmp_path, facts=(('p', 'x'), ('marker',)))
    path = tmp_path / 'memory.json'
    goal = tuple(map(parse_literal, ('ready()', 'not done(y)', 'done(x)')))
    sensor = domain.callbacks['sense']

    def sense(ctx):
        assert ctx['cwd'] == str(tmp_path)
        return sensor(ctx)

    domain.callbacks['sense'] = sense
    report = dry_run(domain, goal, frozenset(domain.actions), Memory(str(path)), cwd=str(tmp_path))
    assert report['goal'] == ['done(x)', 'not done(y)', 'ready()']
    assert report['facts'] == ['marker()', 'p(x)', 'ready()']
    assert report['satisfied'] is False
    assert report['plan']['found'] is True
    assert [step['text'] for step in report['plan']['steps']] == ['prepare()', 'finish(x)']
    assert calls == {'sense': 1}
    assert not path.exists()


def test_dry_run_satisfied_derived_goal_bypasses_memory(tmp_path):
    domain, _, calls = _load(tmp_path)
    path = tmp_path / 'memory.json'
    path.write_text('invalid JSON', encoding='utf-8')
    report = dry_run(domain, (parse_literal('ready()'),), frozenset(), Memory(str(path)))
    assert report['satisfied'] is True
    assert report['plan'] == {'found': True, 'source': 'search', 'steps': [], 'failure': None}
    assert calls == {'sense': 1}


def test_dry_run_memory_hit_then_miss_when_relevant_fact_changes(tmp_path):
    domain, state, calls = _load(tmp_path)
    path = tmp_path / 'memory.json'
    memory = Memory(str(path))
    goal = (parse_literal('done(x)'),)
    allowed = frozenset(domain.actions)
    memory.save(domain, goal, frozenset(state['facts']), [['prepare', []], ['finish', ['x']]])
    snapshot = (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_ino)

    assert dry_run(domain, goal, allowed, memory)['plan']['source'] == 'memory'
    state['facts'].add(('marker',))
    assert dry_run(domain, goal, allowed, memory)['plan']['source'] == 'search'
    assert (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_ino) == snapshot
    assert calls == {'sense': 2}


def test_dry_run_skips_memory_plan_with_disallowed_action(tmp_path):
    domain, state, _ = _load(tmp_path, facts=(('p', 'x'), ('stage',)))
    memory = Memory(str(tmp_path / 'memory.json'))
    goal = (parse_literal('done(x)'),)
    memory.save(domain, goal, frozenset(state['facts']), [['prepare', []], ['finish', ['x']]])
    plan = dry_run(domain, goal, frozenset({'finish'}), memory)['plan']
    assert plan['source'] == 'search'
    assert plan['found'] is True
    assert [step['text'] for step in plan['steps']] == ['finish(x)']


def test_dry_run_without_memory_uses_search_and_node_limit(tmp_path):
    domain, _, _ = _load(tmp_path)
    goal = (parse_literal('done(x)'),)
    plan = dry_run(domain, goal, frozenset(domain.actions), memory=None, max_nodes=0)['plan']
    assert plan == {'found': False, 'source': 'search', 'steps': [],
                    'failure': {'kind': 'limit', 'details': [], 'max_nodes': 0}}


def test_resolve_plan_tries_older_candidate_after_invalid_candidate(tmp_path):
    domain, state, _ = _load(tmp_path, facts=(('p', 'x'), ('stage',), ('marker',)))
    memory = Memory(str(tmp_path / 'memory.json'))
    goal = (parse_literal('done(x)'),)
    base = frozenset(state['facts'])
    memory.save(domain, goal, base, [['finish', ['x']]])
    memory.save(domain, goal, base, [['prepare', []]])
    plan = resolve_plan(domain, base, goal, frozenset(domain.actions), memory)
    assert plan['source'] == 'memory'
    assert [step['text'] for step in plan['steps']] == ['finish(x)']


@pytest.mark.parametrize('broken', ['sensor', 'memory'])
def test_dry_run_propagates_dependency_errors(tmp_path, broken):
    domain, state, _ = _load(tmp_path)
    path = tmp_path / 'memory.json'
    if broken == 'sensor':
        state['facts'].add(('undeclared',))
        expected = 'SENSOR_FAILED'
    else:
        path.write_text('invalid JSON', encoding='utf-8')
        expected = 'USAGE'
    with pytest.raises(PlanbotError) as exc:
        dry_run(domain, (parse_literal('done(x)'),), frozenset(domain.actions), Memory(str(path)))
    assert exc.value.code == expected


def _goal(*texts):
    return tuple(map(parse_literal, texts))


def test_execute_already_satisfied_runs_nothing_and_is_repeatable(tmp_path):
    domain, state, calls = _load(tmp_path)
    allowed = frozenset(domain.actions)
    report = execute(domain, _goal('ready()'), allowed)
    assert report['status'] == 'already_satisfied'
    assert report['executed'] == [] and report['replans'] == 0 and report['stuck'] is None
    assert report['plan']['found'] is True and report['plan']['steps'] == []
    assert report['initial_facts'] == report['final_facts'] == ['p(x)', 'ready()']
    assert report['saved_to_memory'] is False
    assert 'prepare' not in calls and 'finish' not in calls

    first = execute(domain, _goal('done(x)'), allowed)
    assert first['status'] == 'done'
    count = (calls['prepare'], calls['finish'])
    second = execute(domain, _goal('done(x)'), allowed)
    assert second['status'] == 'already_satisfied'
    assert (calls['prepare'], calls['finish']) == count


def test_execute_done_when_effects_match(tmp_path):
    domain, state, calls = _load(tmp_path, facts=(('p', 'x'), ('marker',)))
    report = execute(domain, _goal('done(x)', 'not marker()'), frozenset(domain.actions))
    assert report['status'] == 'done'
    assert report['replans'] == 0 and report['stuck'] is None
    assert report['goal'] == ['done(x)', 'not marker()']
    assert [e['text'] for e in report['executed']] == [s['text'] for s in report['plan']['steps']]
    assert [e['text'] for e in report['executed']] == ['prepare()', 'finish(x)']
    assert all(e == {'text': e['text'], 'ok': True, 'matched': True, 'missing': [], 'unexpected': [], 'cleanup': None, 'output': ''}
               for e in report['executed'])
    assert report['initial_facts'] == ['marker()', 'p(x)', 'ready()']
    assert report['final_facts'] == ['done(x)', 'p(x)', 'ready()', 'stage()']
    assert report['saved_to_memory'] is False
    assert calls['prepare'] == 1 and calls['finish'] == 1


def test_execute_replans_after_effect_missing_once(tmp_path):
    domain, state, calls = _load(tmp_path, missed_effects={'finish': 1})
    report = execute(domain, _goal('done(x)'), frozenset(domain.actions))
    assert report['status'] == 'done'
    assert report['replans'] == 1
    assert [e['text'] for e in report['executed']] == ['prepare()', 'finish(x)', 'finish(x)']
    bad = report['executed'][1]
    assert bad['matched'] is False and bad['ok'] is True
    assert bad['missing'] == ['done(x)'] and bad['unexpected'] == []
    assert report['executed'][2]['matched'] is True
    assert [s['text'] for s in report['plan']['steps']] == ['prepare()', 'finish(x)']


def test_execute_reports_unexpected_facts_that_stay(tmp_path):
    domain, state, _ = _load(tmp_path, facts=(('p', 'x'), ('marker',)), missed_effects={'finish': 1})
    original = domain.callbacks['finish']

    def finish(binding, ctx):
        original(binding, ctx)
        state['facts'].add(('marker',))

    domain.callbacks['finish'] = finish
    report = execute(domain, _goal('done(x)'), frozenset(domain.actions))
    assert report['status'] == 'done'
    assert report['executed'][1]['missing'] == ['done(x)']
    assert report['executed'][1]['unexpected'] == ['marker()']


def test_execute_stuck_at_replan_limit(tmp_path):
    domain, state, calls = _load(tmp_path, missed_effects={'finish': 99})
    report = execute(domain, _goal('done(x)'), frozenset(domain.actions), max_replans=2)
    assert report['status'] == 'stuck'
    assert report['replans'] == 2
    assert report['stuck'] == {'step': 'finish(x)', 'reason': 'replan_limit',
                               'missing': ['done(x)'], 'unexpected': [], 'failure': None, 'error': None}
    assert calls['finish'] == 3
    assert report['executed'][-1]['text'] == 'finish(x)'
    assert report['final_facts'] == ['p(x)', 'ready()', 'stage()']


def test_execute_stuck_with_zero_replans_allowed(tmp_path):
    domain, _, calls = _load(tmp_path, missed_effects={'finish': 99})
    report = execute(domain, _goal('done(x)'), frozenset(domain.actions), max_replans=0)
    assert report['status'] == 'stuck' and report['replans'] == 0
    assert report['stuck']['reason'] == 'replan_limit'
    assert calls['finish'] == 1


def test_execute_stuck_when_no_plan_from_new_state(tmp_path):
    domain, state, calls = _load(tmp_path)

    def prepare(binding, ctx):
        calls['prepare'] += 1
        state['facts'].discard(('p', 'x'))

    domain.callbacks['prepare'] = prepare
    report = execute(domain, _goal('done(x)'), frozenset(domain.actions))
    assert report['status'] == 'stuck'
    assert report['replans'] == 1
    assert report['stuck']['reason'] == 'no_plan'
    assert report['stuck']['step'] == 'prepare()'
    assert report['stuck']['missing'] == ['stage()']
    assert report['stuck']['failure']['kind'] == 'blocked'
    assert report['stuck']['failure']['details']
    assert calls['finish'] == 0


def test_execute_replans_when_goal_unmet_after_last_step(tmp_path):
    domain, state, calls = _load(tmp_path)
    original = domain.callbacks['finish']

    def finish(binding, ctx):
        original(binding, ctx)
        state['facts'].add(('other',))

    domain.callbacks['finish'] = finish
    report = execute(domain, _goal('done(x)', 'not other()'), frozenset(domain.actions))
    assert report['status'] == 'stuck'
    assert report['executed'][-1]['matched'] is True
    assert report['stuck']['reason'] == 'no_plan' and report['stuck']['step'] == 'finish(x)'
    assert report['stuck']['missing'] == [] and report['stuck']['failure'] is not None
    assert report['replans'] == 1


def test_execute_disallowed_step_ends_without_running(tmp_path, monkeypatch):
    domain, _, calls = _load(tmp_path)
    plan = {'found': True, 'source': 'search', 'failure': None, 'steps': [
        {'action': 'finish', 'args': ['x'], 'text': 'finish(x)', 'irreversible': False, 'reasons': []},
    ]}
    monkeypatch.setattr(executor, 'resolve_plan', lambda *a, **k: plan)
    report = execute(domain, _goal('done(x)'), frozenset({'prepare'}))
    assert report['status'] == 'no_plan'
    assert report['executed'] == [] and report['stuck'] is None and report['replans'] == 0
    assert report['plan'] is plan
    assert report['saved_to_memory'] is False
    assert 'finish' not in calls


def test_execute_no_plan_initially(tmp_path):
    domain, _, calls = _load(tmp_path, facts=())
    report = execute(domain, _goal('done(x)'), frozenset(domain.actions))
    assert report['status'] == 'no_plan'
    assert report['plan']['found'] is False and report['plan']['failure'] is not None
    assert report['executed'] == [] and report['stuck'] is None
    assert report['final_facts'] == report['initial_facts'] == []
    assert 'prepare' not in calls


def test_execute_without_memory_creates_no_memory_file(tmp_path):
    domain, _, _ = _load(tmp_path)
    files_before = set(tmp_path.iterdir())
    report = execute(domain, _goal('done(x)'), frozenset(domain.actions), memory=None)
    assert report['status'] == 'done' and report['saved_to_memory'] is False
    assert set(tmp_path.iterdir()) == files_before


def test_execute_sensor_failure_before_and_after_action(tmp_path):
    domain, state, calls = _load(tmp_path)
    state['facts'].add(('undeclared',))
    with pytest.raises(PlanbotError) as exc:
        execute(domain, _goal('done(x)'), frozenset(domain.actions))
    assert exc.value.code == 'SENSOR_FAILED'
    state['facts'].remove(('undeclared',))
    original = domain.callbacks['prepare']
    def prepare(binding, ctx):
        original(binding, ctx)
        state['facts'].add(('undeclared',))
    domain.callbacks['prepare'] = prepare
    memory = Memory(str(tmp_path / 'mem.json'))
    report = execute(domain, _goal('done(x)'), frozenset(domain.actions), memory)
    assert report['status'] == 'stuck'
    assert report['stuck'] == {'step': 'prepare()', 'reason': 'observe_failed',
        'error': "sensor sense: fact 'undeclared()' is not a declared base predicate",
        'missing': [], 'unexpected': [], 'failure': None}
    assert report['final_facts'] == ['p(x)', 'ready()']
    assert report['executed'][0]['matched'] is False
    assert report['executed'][0]['missing'] == report['executed'][0]['unexpected'] == []
    assert not report['saved_to_memory'] and not memory.list() and calls['finish'] == 0


def test_execute_saves_initial_plan_and_reuses_it(tmp_path, monkeypatch):
    domain, state, _ = _load(tmp_path, facts=(('p', 'x'), ('marker',)))
    memory = Memory(str(tmp_path / 'memory.json'))
    goal = _goal('done(x)')
    allowed = frozenset(domain.actions)
    start = state['facts'].copy()

    first = execute(domain, goal, allowed, memory)
    assert first['status'] == 'done' and first['replans'] == 0
    assert first['plan']['source'] == 'search'
    assert first['saved_to_memory'] is True
    assert memory.list() == [{
        'domain': 'mini', 'goal': ['done(x)'],
        'predicates': ['blocked', 'done', 'marker', 'p', 'stage'],
        'start': ['marker()', 'p(x)'], 'steps': [['prepare', []], ['finish', ['x']]],
    }]

    def unexpected_save(*args):
        pytest.fail('A reused plan must not be saved again')

    monkeypatch.setattr(memory, 'save', unexpected_save)
    state['facts'] = start
    assert dry_run(domain, goal, allowed, memory)['plan']['source'] == 'memory'
    second = execute(domain, goal, allowed, memory)
    assert second['status'] == 'done' and second['replans'] == 0
    assert second['plan']['source'] == 'memory'
    assert second['saved_to_memory'] is False


def test_execute_with_replan_does_not_save_to_memory(tmp_path):
    domain, _, _ = _load(tmp_path, missed_effects={'finish': 1})
    memory = Memory(str(tmp_path / 'memory.json'))
    report = execute(domain, _goal('done(x)'), frozenset(domain.actions), memory)
    assert report['status'] == 'done' and report['replans'] == 1
    assert report['saved_to_memory'] is False
    assert memory.list() == []


def test_execute_already_satisfied_does_not_save_to_memory(tmp_path):
    domain, _, _ = _load(tmp_path, facts=(('done', 'x'),))
    memory = Memory(str(tmp_path / 'memory.json'))
    report = execute(domain, _goal('done(x)'), frozenset(domain.actions), memory)
    assert report['status'] == 'already_satisfied'
    assert report['saved_to_memory'] is False
    assert memory.list() == []


def test_execute_propagates_usage_when_memory_is_corrupted_before_save(tmp_path):
    domain, _, _ = _load(tmp_path)
    path = tmp_path / 'memory.json'
    memory = Memory(str(path))
    original = domain.callbacks['finish']

    def finish(binding, ctx):
        original(binding, ctx)
        path.write_text('invalid JSON', encoding='utf-8')

    domain.callbacks['finish'] = finish
    with pytest.raises(PlanbotError) as exc:
        execute(domain, _goal('done(x)'), frozenset(domain.actions), memory)
    assert exc.value.code == 'USAGE'


def test_executor_and_memory_source_contain_no_example_domain_terms():
    package = Path(executor.__file__).parent
    for module in ('executor.py', 'memory.py'):
        source = (package / module).read_text(encoding='utf-8').lower()
        for term in ('git', 'service', 'release', 'branch', 'commit', 'push'):
            assert term not in source, (module, term)

@pytest.mark.parametrize('mode', ['failed', 'cleanup_failed', 'mismatch'])
def test_cleanup_callback_and_binding(tmp_path, mode):
    domain, state, calls = _load(tmp_path, facts=(('p', 'x'), ('stage',)))
    seen = []
    def act(binding, ctx):
        if mode != 'mismatch':
            raise ValueError('action problem')
    def clean(binding, ctx):
        seen.append((binding.copy(), ctx.copy()))
        if mode == 'cleanup_failed':
            raise ValueError('cleanup problem')
    domain.callbacks.update(finish=act, clean=clean)
    domain.actions['finish'].on_fail = {'callback': 'clean'}
    report = execute(domain, _goal('done(x)'), frozenset(domain.actions), max_replans=0, cwd=str(tmp_path))
    item = report['executed'][0]
    assert report['status'] == 'stuck'
    if mode == 'mismatch':
        assert seen == [] and item['cleanup'] is None and item['output'] == ''
    else:
        assert seen == [({'x': 'x'}, {'cwd': str(tmp_path)})]
        assert item['cleanup'] == {'ok': mode == 'failed'}
        assert item['output'] == 'action problem'


def test_cleanup_commands_continue_and_substitute(tmp_path):
    import sys
    domain, _, _ = _load(tmp_path, facts=(('p', 'x'), ('stage',)))
    def fail(binding, ctx):
        raise RuntimeError('bad')
    domain.callbacks['finish'] = fail
    domain.actions['finish'].on_fail = {'cmds': [
        [sys.executable, '-c', 'import sys; sys.exit(2)', '{x}'],
        [sys.executable, '-c', 'import pathlib,sys; pathlib.Path(sys.argv[1]).write_text(sys.argv[2])',
         'result-{x}', 'value-{x}']]}
    report = execute(domain, _goal('done(x)'), frozenset(domain.actions), max_replans=0, cwd=str(tmp_path))
    assert report['executed'][0]['cleanup'] == {'ok': False}
    assert (tmp_path / 'result-x').read_text() == 'value-x'
