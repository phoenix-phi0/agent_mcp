import json
from collections import Counter

import pytest

from planbot import PlanbotError, load_domain
from planbot.core import parse_literal
from planbot.executor import dry_run_task, execute_task, resolve_task, task_fingerprint
from planbot.htn import decompose_task
from planbot.memory import Memory


def _noop(*_args, **_kwargs):
    raise AssertionError('actions must not be executed')


def _act(name, pre=(), add=(), delete=()):
    return {'name': name, 'params': [], 'pre': list(pre), 'add': list(add), 'del': list(delete),
            'run': {'callback': 'noop'}}


def _domain(tmp_path, second_subtask='a2()', file='domain.json'):
    data = {
        'name': 'mini', 'predicates': {'p': 0, 'q': 0, 'r': 0, 'u': 0}, 'sensors': [], 'goals': [],
        'derived': [{'head': 'd()', 'body': ['u()']}],
        'actions': [_act('a1', add=['p()']), _act('a2', pre=['p()'], add=['q()', 'u()']), _act('a3')],
        'tasks': [{'name': 'T', 'params': []}],
        'methods': [{'name': 'm', 'task': 'T', 'params': [], 'pre': ['not q()'],
                     'subtasks': ['a1()', second_subtask, {'goal': ['d()']}]}],
    }
    path = tmp_path / file
    path.write_text(json.dumps(data), encoding='utf-8')
    return load_domain(str(path), callbacks={'noop': _noop})


def _facts(*texts):
    return frozenset(parse_literal(text).atom for text in texts)


def _tree(domain, base):
    result = decompose_task(domain, base, ('T',), frozenset(domain.actions))
    assert result['found']
    return result['tree']


def _goal_save(memory, domain, base):
    goal = (parse_literal('q()'),)
    memory.save(domain, goal, base, [['a1', []], ['a2', []]])


def test_goal_and_task_entries_coexist(tmp_path):
    domain = _domain(tmp_path)
    memory = Memory(str(tmp_path / 'mem' / 'memory.json'))
    base = _facts('r()')
    tree = _tree(domain, base)
    _goal_save(memory, domain, base)
    memory.save_task(domain, 'T()', base, tree, 'fp')

    goal_entry = memory.list()[1]
    task_entry = memory.list()[0]
    assert set(goal_entry) == {'domain', 'goal', 'predicates', 'start', 'steps'}
    assert {'task', 'tree', 'steps', 'fingerprint'} <= set(task_entry)
    assert (task_entry['task'], task_entry['goal'], task_entry['fingerprint']) == ('T()', [], 'fp')
    assert task_entry['steps'] == [['a1', []], ['a2', []]]
    # method pre, goal subtask and derived expansion are all part of the relevant predicates
    assert task_entry['predicates'] == ['p', 'q', 'u']
    assert task_entry['start'] == []
    assert memory.candidates(domain, (parse_literal('q()'),), base) == [[['a1', []], ['a2', []]]]
    assert memory.candidates_task(domain, 'T()', base, 'fp') == [tree]


def test_old_format_file_is_readable(tmp_path):
    domain = _domain(tmp_path)
    memory = Memory(str(tmp_path / 'memory.json'))
    _goal_save(memory, domain, frozenset())
    assert len(memory.list()) == 1
    assert memory.candidates(domain, (parse_literal('q()'),), frozenset()) == [[['a1', []], ['a2', []]]]
    assert memory.candidates_task(domain, 'T()', frozenset(), 'fp') == []
    assert Memory(str(tmp_path / 'missing.json')).candidates_task(domain, 'T()', frozenset(), 'fp') == []


def test_fingerprint_mismatch_or_missing_key_is_not_returned_but_kept(tmp_path):
    domain = _domain(tmp_path)
    path = tmp_path / 'memory.json'
    memory = Memory(str(path))
    tree = _tree(domain, frozenset())
    memory.save_task(domain, 'T()', frozenset(), tree, 'fp')
    assert memory.candidates_task(domain, 'T()', frozenset(), 'other') == []

    data = json.loads(path.read_text(encoding='utf-8'))
    del data['entries'][0]['fingerprint']
    path.write_text(json.dumps(data), encoding='utf-8')
    assert memory.candidates_task(domain, 'T()', frozenset(), 'fp') == []
    assert json.loads(path.read_text(encoding='utf-8')) == data
    assert len(memory.list()) == 1


def test_start_mismatch_and_replacement_by_same_start(tmp_path):
    domain = _domain(tmp_path)
    memory = Memory(str(tmp_path / 'memory.json'))
    tree = _tree(domain, frozenset())
    memory.save_task(domain, 'T()', frozenset(), tree, 'fp1')
    assert memory.candidates_task(domain, 'T()', _facts('u()'), 'fp1') == []
    assert memory.candidates_task(domain, 'T()', _facts('r()'), 'fp1') == [tree]  # r is not relevant

    memory.save_task(domain, 'T()', _facts('r()'), tree, 'fp2')
    assert [entry['fingerprint'] for entry in memory.list()] == ['fp2']
    memory.save_task(domain, 'T()', _facts('u()'), tree, 'fp2')
    assert len(memory.list()) == 2
    assert memory.list()[0]['start'] == ['u()']


def test_task_fingerprint(tmp_path):
    domain = _domain(tmp_path)
    allowed = frozenset({'a1', 'a2'})
    original = task_fingerprint(domain, allowed, 20)
    assert len(original) == 64 and int(original, 16) >= 0
    assert task_fingerprint(domain, frozenset({'a1', 'a2'}), 20) == original
    assert task_fingerprint(domain, allowed | {'a3'}, 20) != original
    assert task_fingerprint(domain, allowed, 10) != original
    changed = _domain(tmp_path, second_subtask='a3()', file='changed.json')
    assert changed.name == domain.name and changed.digest != domain.digest
    assert task_fingerprint(changed, allowed, 20) != original


def test_corrupt_memory_file_is_usage_error(tmp_path):
    domain = _domain(tmp_path)
    path = tmp_path / 'memory.json'
    for text in ('{not json', '{"entries": [{"domain": "mini", "task": "T()"}]}'):
        path.write_text(text, encoding='utf-8')
        with pytest.raises(PlanbotError) as caught:
            Memory(str(path)).candidates_task(domain, 'T()', frozenset(), 'fp')
        assert caught.value.code == 'USAGE'


_ALLOWED = frozenset({'a1', 'a2', 'a3'})


def _world(tmp_path, file='world.json', second_subtask='a2()', facts=('r()',)):
    state = {'facts': set(facts), 'broken': False}
    calls = Counter()

    def sense(_ctx):
        calls['sense'] += 1
        if state['broken']:
            raise RuntimeError('sensor down')
        return '\n'.join(sorted(state['facts']))

    def act(_binding, _ctx):
        calls['act'] += 1

    def action(name, pre, add):
        return {'name': name, 'params': [], 'pre': pre, 'add': add, 'del': [], 'run': {'callback': 'act'}}

    data = {
        'name': 'mini', 'predicates': {'p': 0, 'q': 0, 'r': 0, 'u': 0}, 'goals': [],
        'sensors': [{'name': 'sense', 'run': {'callback': 'sense'}, 'extract': [
            {'type': 'regex', 'pattern': r'^(.+)$', 'facts': ['{1}']},
        ]}],
        'derived': [{'head': 'd()', 'body': ['u()']}],
        'actions': [
            action('a1', [], ['p()']),
            action('a2', ['p()'], ['q()', 'u()']),
            action('a3', [], []),
            action('a4', [], []),
        ],
        'tasks': [{'name': 'T', 'params': []}],
        'methods': [{'name': 'm', 'task': 'T', 'params': [], 'pre': ['not q()'],
                     'subtasks': ['a1()', second_subtask, {'goal': ['d()']}]}],
    }
    path = tmp_path / file
    path.write_text(json.dumps(data), encoding='utf-8')
    domain = load_domain(str(path), callbacks={'sense': sense, 'act': act})
    return domain, state, calls


def _save_fresh(domain, memory, base, allowed, max_depth=20):
    fresh = decompose_task(domain, base, ('T',), allowed, max_depth)
    memory.save_task(domain, 'T()', base, fresh['tree'], task_fingerprint(domain, allowed, max_depth))
    return fresh


def test_dry_run_task_decomposes_without_acting_or_writing(tmp_path):
    domain, _, calls = _world(tmp_path)
    memory_path = tmp_path / 'mem' / 'memory.json'
    memory = Memory(str(memory_path))

    result = dry_run_task(domain, ('T',), _ALLOWED, memory=memory)

    assert set(result) == {'task', 'facts', 'plan'}
    assert result['task'] == 'T()'
    assert result['facts'] == ['r()']
    assert result['plan']['found'] is True
    assert result['plan']['source'] == 'decompose'
    assert [step['action'] for step in result['plan']['steps']] == ['a1', 'a2']
    assert calls['act'] == 0
    assert not memory_path.exists()
    assert memory.list() == []


def test_unplannable_task_reports_not_found_without_raising(tmp_path):
    domain, _, calls = _world(tmp_path)
    result = dry_run_task(domain, ('T',), frozenset({'a2', 'a3'}))
    assert result['plan']['found'] is False
    assert result['plan']['steps'] == []
    assert calls['act'] == 0


def test_saved_task_is_reused_only_when_start_matches(tmp_path):
    domain, state, calls = _world(tmp_path)
    memory = Memory(str(tmp_path / 'memory.json'))
    base = frozenset({('r',)})
    fresh = _save_fresh(domain, memory, base, _ALLOWED)

    hit = dry_run_task(domain, ('T',), _ALLOWED, memory=memory)['plan']
    assert hit['source'] == 'memory'
    assert hit['tree'] == fresh['tree']
    assert hit['steps'] == fresh['steps']
    assert dry_run_task(domain, ('T',), _ALLOWED)['plan']['source'] == 'decompose'

    state['facts'].add('u()')  # start-relevant fact differs
    assert dry_run_task(domain, ('T',), _ALLOWED, memory=memory)['plan']['source'] == 'decompose'
    assert calls['act'] == 0


def test_resolve_task_uses_memory_and_rejects_negative_limits(tmp_path):
    domain, _, _ = _world(tmp_path)
    memory = Memory(str(tmp_path / 'memory.json'))
    base = frozenset({('r',)})
    fresh = _save_fresh(domain, memory, base, _ALLOWED)
    assert resolve_task(domain, base, ('T',), _ALLOWED, memory)['source'] == 'memory'
    assert resolve_task(domain, base, ('T',), _ALLOWED)['source'] == 'decompose'
    assert resolve_task(domain, base, ('T',), _ALLOWED)['steps'] == fresh['steps']
    with pytest.raises(PlanbotError) as caught:
        resolve_task(domain, base, ('T',), _ALLOWED, max_depth=-1)
    assert caught.value.code == 'USAGE'


def test_memory_entry_needs_same_fingerprint(tmp_path):
    domain, _, _ = _world(tmp_path)
    path = tmp_path / 'memory.json'
    memory = Memory(str(path))
    _save_fresh(domain, memory, frozenset({('r',)}), _ALLOWED)

    def source(target=domain, allowed=_ALLOWED, **kwargs):
        return dry_run_task(target, ('T',), allowed, memory=memory, **kwargs)['plan']['source']

    assert source() == 'memory'
    assert source(max_depth=10) == 'decompose'
    assert source(allowed=_ALLOWED | {'a4'}) == 'decompose'
    other, _, _ = _world(tmp_path, file='other.json', second_subtask='a3()')
    assert source(target=other) == 'decompose'

    data = json.loads(path.read_text(encoding='utf-8'))
    del data['entries'][0]['fingerprint']
    path.write_text(json.dumps(data), encoding='utf-8')
    assert source() == 'decompose'
    assert len(memory.list()) == 1


def test_no_memory_file_read_when_memory_is_none(tmp_path):
    domain, _, _ = _world(tmp_path)
    result = dry_run_task(domain, ('T',), _ALLOWED, memory=None)
    assert result['plan']['source'] == 'decompose'


@pytest.mark.parametrize('task', [(), ('nope',), ('T', 'x')])
def test_invalid_task_fails_before_observing(tmp_path, task):
    domain, _, calls = _world(tmp_path)
    with pytest.raises(PlanbotError) as caught:
        dry_run_task(domain, task, _ALLOWED)
    assert caught.value.code == 'GOAL_INVALID'
    assert calls['sense'] == 0


@pytest.mark.parametrize('kwargs', [{'max_nodes': -1}, {'max_depth': -1}])
def test_negative_limits_fail_before_observing(tmp_path, kwargs):
    domain, _, calls = _world(tmp_path)
    with pytest.raises(PlanbotError) as caught:
        dry_run_task(domain, ('T',), _ALLOWED, **kwargs)
    assert caught.value.code == 'USAGE'
    assert calls['sense'] == 0


def test_corrupt_memory_fails_before_observing(tmp_path):
    domain, _, calls = _world(tmp_path)
    path = tmp_path / 'memory.json'
    path.write_text('{not json', encoding='utf-8')
    with pytest.raises(PlanbotError) as caught:
        dry_run_task(domain, ('T',), _ALLOWED, memory=Memory(str(path)))
    assert caught.value.code == 'USAGE'
    assert calls['sense'] == 0


def test_task_error_takes_precedence_over_limits(tmp_path):
    domain, _, calls = _world(tmp_path)
    with pytest.raises(PlanbotError) as caught:
        dry_run_task(domain, (), _ALLOWED, max_depth=-1)
    assert caught.value.code == 'GOAL_INVALID'
    assert calls['sense'] == 0


def test_sensor_failure_is_passed_through(tmp_path):
    domain, state, _ = _world(tmp_path)
    state['broken'] = True
    with pytest.raises(PlanbotError) as caught:
        dry_run_task(domain, ('T',), _ALLOWED)
    assert caught.value.code == 'SENSOR_FAILED'


# ---------------------------------------------------------------- execute_task

class Sim:
    """A tiny world: facts, call counters, and per-action behaviour overrides."""

    def __init__(self, facts=()):
        self.facts = set(facts)
        self.calls = Counter()
        self.senses = 0
        self.fail_sense_at = None
        self.behave = {}
        self.effects = {}

    def sense(self, _ctx):
        self.senses += 1
        if self.senses == self.fail_sense_at:
            raise RuntimeError('sensor down')
        return '\n'.join(sorted(self.facts))

    def apply(self, name):
        add, delete = self.effects[name]
        self.facts -= set(delete)
        self.facts |= set(add)

    def callback(self, name):
        def run(_binding, _ctx):
            self.calls[name] += 1
            if name in self.behave:
                self.behave[name](self.calls[name])
            else:
                self.apply(name)
        return run


def _build(tmp_path, sim, actions, methods, tasks=('T',), cmd=(), file='sim.json', dom_name='net'):
    """actions: (name, pre, add, del); methods: (name, task, pre, subtasks)."""
    callbacks = {'sense': sim.sense}
    action_data = []
    for name, pre, add, delete in actions:
        sim.effects[name] = (add, delete)
        if name in cmd:
            run = {'cmd': {'name': name, 'args': {}}}
        else:
            callbacks[name] = sim.callback(name)
            run = {'callback': name}
        action_data.append({'name': name, 'params': [], 'pre': pre, 'add': add, 'del': delete, 'run': run})
    data = {
        'name': dom_name, 'goals': [],
        'predicates': {name: 0 for name in 'pqrmzkwgh'},
        'derived': [{'head': 'ready()', 'body': ['p()', 'q()']}],
        'sensors': [{'name': 'sense', 'run': {'callback': 'sense'}, 'extract': [
            {'type': 'regex', 'pattern': r'^(.+)$', 'facts': ['{1}']}]}],
        'actions': action_data,
        'tasks': [{'name': name, 'params': []} for name in tasks],
        'methods': [{'name': name, 'task': task, 'params': [], 'pre': pre, 'subtasks': subtasks}
                    for name, task, pre, subtasks in methods],
    }
    path = tmp_path / file
    path.write_text(json.dumps(data), encoding='utf-8')
    return load_domain(str(path), callbacks=callbacks)


def _run(domain, **kwargs):
    return execute_task(domain, ('T',), frozenset(domain.actions), **kwargs)


def _texts_of(report):
    return [item['text'] for item in report['executed']]


def test_execute_task_done_saves_and_memory_replays(tmp_path):
    sim = Sim({'r()'})
    domain = _build(tmp_path, sim, [('a1', [], ['p()'], []), ('a2', ['p()'], ['q()'], [])],
                    [('m', 'T', [], ['a1()', 'a2()'])])
    memory = Memory(str(tmp_path / 'mem.json'))

    report = _run(domain, memory=memory)

    assert report['status'] == 'done'
    assert (report['task'], report['replans'], report['replanned'], report['trigger']) == ('T()', 0, [], None)
    assert report['stuck'] is None
    assert report['initial_facts'] == ['r()']
    assert report['final_facts'] == ['p()', 'q()', 'r()', 'ready()']
    assert _texts_of(report) == [step['text'] for step in report['plan']['steps']] == ['a1()', 'a2()']
    assert all(item['ok'] and item['matched'] and item['missing'] == [] and item['unexpected'] == []
               for item in report['executed'])
    assert [item['path'] for item in report['executed']] == [[{'text': 'T()', 'idx': 0}]] * 2
    assert report['saved_to_memory'] is True
    entries = memory.list()
    assert len(entries) == 1 and {'task', 'tree', 'steps', 'fingerprint'} <= set(entries[0])

    sim.facts = {'r()'}
    replay = dry_run_task(domain, ('T',), frozenset(domain.actions), memory=memory)
    assert replay['plan']['source'] == 'memory'

    sim.facts = {'r()'}
    other = _run(domain, memory=None)
    assert other['status'] == 'done' and other['saved_to_memory'] is False


def test_execute_task_empty_method_is_already_satisfied(tmp_path):
    sim = Sim()
    domain = _build(tmp_path, sim, [('a1', [], ['p()'], [])], [('m', 'T', [], [])])
    memory = Memory(str(tmp_path / 'mem.json'))
    report = _run(domain, memory=memory)
    assert report['status'] == 'already_satisfied'
    assert report['executed'] == [] and sim.calls['a1'] == 0
    assert report['saved_to_memory'] is False and memory.list() == []


def test_execute_task_no_decomposition_is_no_plan(tmp_path):
    sim = Sim()
    domain = _build(tmp_path, sim, [('a1', [], ['p()'], [])], [('m', 'T', ['q()'], ['a1()'])])
    report = _run(domain)
    assert report['status'] == 'no_plan'
    assert report['plan']['found'] is False
    assert report['executed'] == [] and report['stuck'] is None
    assert sim.calls['a1'] == 0


def test_execute_task_empty_prefix_reselects_method(tmp_path):
    sim = Sim()
    domain = _build(
        tmp_path, sim,
        [('a1', [], ['p()'], []), ('a2', [], ['q()'], []), ('a3', [], ['w()'], []), ('a4', [], ['h()'], [])],
        [('m', 'T', [], ['a1()', 'U()', 'a4()']),
         ('u1', 'U', ['not m()'], ['a2()']), ('u2', 'U', [], ['a3()'])],
        tasks=('T', 'U'))
    sim.behave['a2'] = lambda n: sim.facts.add('m()')  # no q(), but sets the marker
    memory = Memory(str(tmp_path / 'mem.json'))

    report = _run(domain, memory=memory)

    assert report['status'] == 'done' and report['replans'] == 1
    assert _texts_of(report) == ['a1()', 'a2()', 'a3()', 'a4()']
    assert sim.calls['a1'] == 1
    assert report['replanned'] == [{
        'after': 2, 'resume': 'U()', 'idx': 1, 'path': [{'text': 'T()', 'idx': 0}],
        'trigger': {'kind': 'mismatch', 'step': 'a2()'}, 'found': True, 'steps': ['a3()', 'a4()'],
    }]
    assert report['trigger'] == {'kind': 'mismatch', 'step': 'a2()'}
    assert report['executed'][1]['matched'] is False and report['executed'][1]['missing'] == ['q()']
    assert report['saved_to_memory'] is False and memory.list() == []


def _ab_domain(tmp_path, sim):
    return _build(
        tmp_path, sim,
        [('a', [], ['p()'], []), ('b', ['not m()'], ['q()'], []), ('c', [], ['w()'], [])],
        [('m1', 'T', [], ['a()', 'b()']), ('m2', 'T', [], ['a()', 'c()'])])


def test_execute_task_switches_candidate_without_redoing_prefix(tmp_path):
    sim = Sim()
    domain = _ab_domain(tmp_path, sim)
    sim.behave['b'] = lambda n: sim.facts.add('m()')

    report = _run(domain)

    assert report['status'] == 'done' and report['replans'] == 1
    assert _texts_of(report) == ['a()', 'b()', 'c()']
    assert (sim.calls['a'], sim.calls['c']) == (1, 1)
    assert report['replanned'][0]['resume'] == 'T()'
    assert report['replanned'][0]['steps'] == ['c()']


def test_execute_task_two_recoveries(tmp_path):
    sim = Sim()
    domain = _ab_domain(tmp_path, sim)
    sim.behave['b'] = lambda n: sim.facts.add('m()')
    # the failed first attempt still changes a declared fact, so it counts as progress
    sim.behave['c'] = lambda n: sim.apply('c') if n > 1 else sim.facts.add('h()')

    report = _run(domain)

    assert report['status'] == 'done' and report['replans'] == 2
    assert _texts_of(report) == ['a()', 'b()', 'c()', 'c()']
    assert sim.calls['a'] == 1


def test_execute_task_same_name_siblings(tmp_path):
    sim = Sim()
    domain = _build(tmp_path, sim,
                    [('x', [], ['k()'], []), ('y', ['k()'], ['w()'], [])],
                    [('m', 'T', [], ['x()', 'x()', 'y()'])])

    def x_behaviour(n):
        sim.facts.discard('k()')
        if n != 2:
            sim.facts.add('k()')

    sim.behave['x'] = x_behaviour

    report = _run(domain)

    assert report['status'] == 'done' and report['replans'] == 1
    assert (sim.calls['x'], sim.calls['y']) == (3, 1)
    assert _texts_of(report) == ['x()', 'x()', 'x()', 'y()']
    assert report['replanned'][0]['trigger'] == {'kind': 'mismatch', 'step': 'x()'}


def test_execute_task_prefix_cannot_be_continued(tmp_path):
    sim = Sim({'z()'})
    domain = _build(tmp_path, sim, [('a', [], ['p()'], []), ('b', ['z()'], ['q()'], [])],
                    [('m1', 'T', [], ['a()', 'b()'])])
    sim.behave['b'] = lambda n: sim.facts.discard('z()')

    report = _run(domain)

    assert report['status'] == 'stuck'
    assert report['stuck']['reason'] == 'no_plan'
    assert report['stuck']['failure']['kind'] == 'no_method'
    assert report['stuck']['node'] == 'T()'
    assert report['stuck']['step'] == 'b()' and report['stuck']['missing'] == ['q()']
    assert sim.calls['a'] == 1
    assert report['replanned'][0]['found'] is False and report['replanned'][0]['steps'] == []


def _always_failing(tmp_path, sim):
    domain = _build(tmp_path, sim, [('a', [], ['q()'], [])], [('m', 'T', [], ['a()'])])
    # never produces q(), but every attempt flips a declared fact so the state keeps changing
    sim.behave['a'] = lambda n: sim.facts.symmetric_difference_update({'h()'})
    return domain


def test_execute_task_replan_limit(tmp_path):
    sim = Sim()
    report = _run(_always_failing(tmp_path, sim), max_replans=2)
    assert report['status'] == 'stuck' and report['replans'] == 2
    assert len(report['executed']) == 3 and len(report['replanned']) == 2
    stuck = report['stuck']
    assert stuck['reason'] == 'replan_limit' and stuck['failure'] is None
    assert (stuck['step'], stuck['node'], stuck['idx'], stuck['path']) == ('a()', 'T()', 0, [])
    assert stuck['missing'] == ['q()'] and stuck['unexpected'] == []
    assert report['trigger'] == {'kind': 'mismatch', 'step': 'a()'}


def test_execute_task_max_replans_zero_stops_at_first_mismatch(tmp_path):
    sim = Sim()
    report = _run(_always_failing(tmp_path, sim), max_replans=0)
    assert report['status'] == 'stuck' and report['stuck']['reason'] == 'replan_limit'
    assert report['replans'] == 0 and report['replanned'] == []
    assert sim.calls['a'] == 1


def _precondition_domain(tmp_path, sim, with_second_method):
    methods = [('m1', 'T', [], ['a()', 'b()'])]
    if with_second_method:
        methods.append(('m2', 'T', [], ['a()', 'c()']))
    domain = _build(tmp_path, sim,
                    [('a', [], ['p()'], []), ('b', ['z()'], ['q()'], []), ('c', [], ['w()'], [])], methods)
    sim.behave['a'] = lambda n: (sim.apply('a'), sim.facts.discard('z()'))  # matched, but breaks b's pre
    return domain


def test_execute_task_precondition_trigger_differs_from_last_step(tmp_path):
    sim = Sim({'z()'})
    report = _run(_precondition_domain(tmp_path, sim, False))
    assert report['status'] == 'stuck' and report['stuck']['reason'] == 'no_plan'
    assert report['trigger'] == {'kind': 'precondition', 'step': 'b()'}
    assert report['stuck']['step'] == 'a()' == report['executed'][-1]['text']
    assert report['executed'][-1]['matched'] is True
    assert sim.calls['b'] == 0


def test_execute_task_precondition_recovery_switches_candidate(tmp_path):
    sim = Sim({'z()'})
    report = _run(_precondition_domain(tmp_path, sim, True))
    assert report['status'] == 'done' and report['replans'] == 1
    assert _texts_of(report) == ['a()', 'c()'] and sim.calls['a'] == 1


def _goal_domain(tmp_path, sim, with_add_q):
    actions = [('add_p', [], ['p()'], [])]
    if with_add_q:
        actions.append(('add_q', [], ['q()'], []))
    domain = _build(tmp_path, sim, actions, [('m', 'T', [], [{'goal': ['ready()']}])])
    sim.behave['add_p'] = lambda n: (sim.facts.add('p()'), sim.facts.discard('q()'))
    return domain


def test_execute_task_goal_check_recovers(tmp_path):
    sim = Sim({'q()'})
    report = _run(_goal_domain(tmp_path, sim, True))
    assert report['status'] == 'done' and report['replans'] == 1
    assert report['executed'][0]['matched'] is True
    assert report['trigger'] == {'kind': 'goal', 'step': 'goal ready()'}
    assert report['replanned'][0]['resume'] == 'goal ready()'
    assert _texts_of(report) == ['add_p()', 'add_q()']


def test_execute_task_goal_check_without_remedy_is_stuck(tmp_path):
    sim = Sim({'q()'})
    report = _run(_goal_domain(tmp_path, sim, False))
    assert report['status'] == 'stuck' and report['stuck']['reason'] == 'no_plan'
    assert report['trigger']['kind'] == 'goal'
    assert report['stuck']['node'] == 'goal ready()'


def test_execute_task_zero_action_goal_is_checked(tmp_path):
    sim = Sim({'g()'})
    domain = _build(
        tmp_path, sim,
        [('a', [], ['p()'], []), ('b', [], ['q()'], []), ('fix_g', [], ['g()'], [])],
        [('m', 'T', [], ['a()', 'b()', {'goal': ['g()']}])])

    def b_behaviour(n):
        if n == 1:
            sim.facts.add('h()')  # failed attempt that still changes a declared fact
        else:
            sim.facts.add('q()')
            sim.facts.discard('g()')

    sim.behave['b'] = b_behaviour

    report = _run(domain)

    assert report['status'] == 'done' and report['replans'] == 2
    assert report['replanned'][0]['trigger'] == {'kind': 'mismatch', 'step': 'b()'}
    assert report['replanned'][1]['trigger'] == {'kind': 'goal', 'step': 'goal g()'}
    assert report['replanned'][1]['resume'] == 'goal g()'
    assert _texts_of(report) == ['a()', 'b()', 'b()', 'fix_g()']
    assert sim.calls['a'] == 1


def test_execute_task_missing_cmd_runner_is_usage_before_any_action(tmp_path):
    sim = Sim()
    domain = _build(tmp_path, sim,
                    [('cb', [], ['p()'], []), ('ext', [], ['q()'], [])],
                    [('m', 'T', [], ['cb()', 'ext()'])], cmd=('ext',))
    assert dry_run_task(domain, ('T',), frozenset(domain.actions))['plan']['found'] is True
    with pytest.raises(PlanbotError) as caught:
        _run(domain)
    assert caught.value.code == 'USAGE'
    assert 'no cmd runner' in caught.value.message and 'ext()' in caught.value.message
    assert sim.calls['cb'] == 0


def test_execute_task_sensor_failure_after_steps_carries_progress(tmp_path):
    sim = Sim()
    domain = _build(tmp_path, sim,
                    [('a1', [], ['p()'], []), ('a2', [], ['q()'], []), ('a3', [], ['w()'], [])],
                    [('m', 'T', [], ['a1()', 'a2()', 'a3()'])])
    sim.fail_sense_at = 3  # initial, after a1, after a2
    with pytest.raises(PlanbotError) as caught:
        _run(domain)
    error = caught.value
    assert error.code == 'SENSOR_FAILED'
    assert 'sensor sense' in error.message
    assert 'after 2 executed step(s)' in error.message
    assert 'last a2() @ T()#0' in error.message
    assert error.message.endswith('re-observe the current state before retrying')
    assert sim.calls['a3'] == 0


def test_execute_task_first_observation_failure_is_passed_through(tmp_path):
    sim = Sim()
    domain = _build(tmp_path, sim, [('a1', [], ['p()'], [])], [('m', 'T', [], ['a1()'])])
    sim.fail_sense_at = 1
    with pytest.raises(PlanbotError) as caught:
        _run(domain)
    assert caught.value.code == 'SENSOR_FAILED' and 'executed step' not in caught.value.message
    assert sim.calls['a1'] == 0


@pytest.mark.parametrize('task,kwargs,code', [
    ((), {}, 'GOAL_INVALID'),
    (('nope',), {}, 'GOAL_INVALID'),
    (('T', 'x'), {}, 'GOAL_INVALID'),
    (('T',), {'max_replans': -1}, 'USAGE'),
    (('T',), {'max_nodes': -1}, 'USAGE'),
    (('T',), {'max_depth': -1}, 'USAGE'),
    ((), {'max_depth': -1}, 'GOAL_INVALID'),
])
def test_execute_task_validation_precedes_observation(tmp_path, task, kwargs, code):
    sim = Sim()
    domain = _build(tmp_path, sim, [('a1', [], ['p()'], [])], [('m', 'T', [], ['a1()'])])
    with pytest.raises(PlanbotError) as caught:
        execute_task(domain, task, frozenset(domain.actions), **kwargs)
    assert caught.value.code == code
    assert sim.senses == 0 and sim.calls['a1'] == 0


def test_execute_task_corrupt_memory_fails_before_observing(tmp_path):
    sim = Sim()
    domain = _build(tmp_path, sim, [('a1', [], ['p()'], [])], [('m', 'T', [], ['a1()'])])
    path = tmp_path / 'memory.json'
    path.write_text('{not json', encoding='utf-8')
    with pytest.raises(PlanbotError) as caught:
        _run(domain, memory=Memory(str(path)))
    assert caught.value.code == 'USAGE'
    assert sim.senses == 0


def test_execute_task_recovered_run_is_not_saved_and_deleted_fingerprint_forces_decompose(tmp_path):
    sim = Sim()
    domain = _ab_domain(tmp_path, sim)
    sim.behave['b'] = lambda n: sim.facts.add('m()')
    memory = Memory(str(tmp_path / 'mem.json'))

    report = _run(domain, memory=memory)

    assert report['status'] == 'done' and report['replans'] == 1
    assert report['saved_to_memory'] is False
    assert memory.list() == []

    sim.facts = set()
    sim.behave.clear()
    assert _run(domain, memory=memory)['saved_to_memory'] is True
    path = tmp_path / 'mem.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    del data['entries'][0]['fingerprint']
    path.write_text(json.dumps(data), encoding='utf-8')
    sim.facts = set()
    plan = dry_run_task(domain, ('T',), frozenset(domain.actions), memory=memory)['plan']
    assert plan['source'] == 'decompose'
    assert len(memory.list()) == 1
