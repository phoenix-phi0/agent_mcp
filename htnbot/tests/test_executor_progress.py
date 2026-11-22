"""execute_task stops with reason 'no_progress' when a step changed nothing and the recovery
re-decomposition schedules the very same action instance again."""
import json
import types
from collections import Counter

from planbot import executor, load_domain
from planbot.htn import decompose, decompose_task


class World:
    """Facts, per-action call counters / behaviours, and a record of every observation."""

    def __init__(self, facts=()):
        self.facts = set(facts)
        self.calls = Counter()
        self.behave = {}
        self.observed = []

    def sense(self, _ctx):
        out = '\n'.join(sorted(self.facts))
        self.observed.append(out)
        return out

    def callback(self, name):
        def run(_binding, _ctx):
            self.calls[name] += 1
            self.behave[name](self.calls[name])
        return run


def _act(name, pre=(), add=(), delete=()):
    return {'name': name, 'params': [], 'pre': list(pre), 'add': list(add), 'del': list(delete),
            'run': {'callback': name}}


def _build(tmp_path, world, actions, methods, tasks=('T',), preds='mnpqrsehj', derived=()):
    data = {
        'name': 'tiny', 'goals': [], 'predicates': {name: 0 for name in preds},
        'derived': list(derived),
        'sensors': [{'name': 'sense', 'run': {'callback': 'sense'}, 'extract': [
            {'type': 'regex', 'pattern': r'^(.+)$', 'facts': ['{1}']}]}],
        'actions': actions,
        'tasks': [{'name': name, 'params': []} for name in tasks],
        'methods': [{'name': name, 'task': task, 'params': [], 'pre': pre, 'subtasks': subtasks}
                    for name, task, pre, subtasks in methods],
    }
    path = tmp_path / 'tiny.json'
    path.write_text(json.dumps(data), encoding='utf-8')
    callbacks = {'sense': world.sense}
    callbacks.update({a['name']: world.callback(a['name']) for a in actions})
    return load_domain(str(path), callbacks=callbacks)


def _run(domain, task=('T',), **kwargs):
    return executor.execute_task(domain, task, frozenset(domain.actions), **kwargs)


def _patch_recovery(monkeypatch, replacement):
    """Replace only the decompose call that executor makes on recovery (htn's own internals keep
    using the real one)."""
    proxy = types.SimpleNamespace(**vars(executor.htn))
    proxy.decompose = replacement
    monkeypatch.setattr(executor, 'htn', proxy)


def _single_failing(tmp_path, behave):
    world = World()
    world.behave['a'] = behave(world)
    domain = _build(tmp_path, world, [_act('a', add=['p()'])], [('m', 'T', [], ['a()'])])
    return world, domain


def test_no_change_and_same_instance_is_no_progress(tmp_path):
    world, domain = _single_failing(tmp_path, lambda w: lambda n: None)
    report = _run(domain, max_replans=3)

    assert report['status'] == 'stuck'
    stuck = report['stuck']
    assert stuck['reason'] == 'no_progress'
    assert stuck['step'] == 'a()'
    assert stuck['node'] == 'T()'
    assert stuck['failure'] is None
    assert stuck['missing'] == ['p()']
    assert stuck['unexpected'] == []
    assert (stuck['idx'], stuck['path']) == (0, [])
    assert report['trigger'] == {'kind': 'mismatch', 'step': 'a()'}
    assert report['replans'] == 1
    assert len(report['replanned']) == 1
    assert report['replanned'][0]['found'] is True
    assert report['replanned'][0]['steps'][0] == 'a()'
    assert len(report['executed']) == 1
    assert world.calls['a'] == 1


def test_changed_state_is_not_no_progress(tmp_path):
    world, domain = _single_failing(
        tmp_path, lambda w: lambda n: w.facts.symmetric_difference_update({'h()'}))
    report = _run(domain, max_replans=3)

    assert report['status'] == 'stuck'
    assert report['stuck']['reason'] == 'replan_limit'
    assert report['replans'] == 3
    assert world.calls['a'] == 4


def test_max_replans_zero_stays_replan_limit(tmp_path):
    world, domain = _single_failing(tmp_path, lambda w: lambda n: None)
    report = _run(domain, max_replans=0)

    assert report['status'] == 'stuck'
    assert report['stuck']['reason'] == 'replan_limit'
    assert report['replans'] == 0
    assert report['replanned'] == []
    assert world.calls['a'] == 1


def test_different_action_after_recovery_is_not_no_progress(tmp_path, monkeypatch):
    world = World()
    world.behave['a'] = lambda n: None
    world.behave['c'] = lambda n: world.facts.add('r()')
    domain = _build(
        tmp_path, world, [_act('a', add=['p()']), _act('c', add=['r()'])],
        [('m1', 'T', [], ['a()']), ('m2', 'T2', [], ['c()'])], tasks=('T', 'T2'))
    real_task = decompose_task

    def fixed(dom, base, _agenda, allowed, *_args, **_kwargs):
        return real_task(dom, base, ('T2',), allowed)

    _patch_recovery(monkeypatch, fixed)
    report = _run(domain)

    assert world.observed[0] == world.observed[1]
    assert report['replanned'][0]['found'] is True
    assert report['replanned'][0]['steps'][0] == 'c()'
    assert [item['text'] for item in report['executed']] == ['a()', 'c()']
    assert world.calls['c'] == 1
    assert report['status'] == 'done'
    assert report['stuck'] is None


def test_mismatch_at_goal_node_is_no_progress(tmp_path):
    world = World()
    world.behave['b'] = lambda n: None
    domain = _build(tmp_path, world, [_act('b', add=['p()'])],
                    [('m', 'T', [], [{'goal': ['p()']}])])
    report = _run(domain)

    assert report['status'] == 'stuck'
    assert report['stuck']['reason'] == 'no_progress'
    assert report['trigger'] == {'kind': 'mismatch', 'step': 'b()'}
    assert report['stuck']['step'] == 'b()'
    assert report['stuck']['node'] == 'goal p()'
    assert report['replans'] == 1
    assert report['stuck']['failure'] is None
    assert [item['text'] for item in report['executed']] == ['b()']
    assert world.calls['b'] == 1


def _goal_trigger_domain(tmp_path, world, subtasks):
    world.behave['a'] = lambda n: world.facts.update({'m()', 'p()', 'n()'})
    world.behave['b'] = lambda n: None
    return _build(
        tmp_path, world,
        [_act('a', add=['m()']), _act('b', pre=['m()'], add=['p()'])],
        [('mt', 'T', [], subtasks)],
        preds='mpn', derived=[{'head': 'g()', 'body': ['p()', 'not n()']}])


def _strip_pn(monkeypatch):
    def stripped(dom, base, agenda, allowed, *args, **kwargs):
        cut = frozenset(f for f in base if f[0] not in ('p', 'n'))
        return decompose(dom, cut, agenda, allowed, *args, **kwargs)

    _patch_recovery(monkeypatch, stripped)


def test_goal_trigger_without_patch_is_no_plan(tmp_path):
    world = World()
    report = _run(_goal_trigger_domain(tmp_path, world, ['a()', {'goal': ['g()']}]))

    assert report['status'] == 'stuck'
    assert report['trigger'] == {'kind': 'goal', 'step': 'goal g()'}
    assert report['stuck']['reason'] == 'no_plan'


def test_goal_trigger_with_same_instance_is_no_progress(tmp_path, monkeypatch):
    world = World()
    domain = _goal_trigger_domain(tmp_path, world, ['a()', {'goal': ['g()']}])
    _strip_pn(monkeypatch)
    report = _run(domain)

    assert [s['text'] for s in report['plan']['steps']] == ['a()', 'b()']
    assert report['plan']['steps'][1]['path'][-1]['text'] == 'goal g()'
    assert report['status'] == 'stuck'
    assert report['stuck']['reason'] == 'no_progress'
    assert report['trigger'] == {'kind': 'goal', 'step': 'goal g()'}
    assert report['stuck']['step'] == 'b()'
    assert report['stuck']['node'] == 'goal g()'
    assert report['stuck']['failure'] is None
    assert report['replans'] == 1
    assert len(report['replanned']) == 1
    assert report['replanned'][0]['found'] is True
    assert report['replanned'][0]['steps'][0] == 'b()'
    # The resumed node is the goal node itself, i.e. the last element of b's own path.
    resumed = report['replanned'][0]
    assert (resumed['resume'], resumed['idx']) == ('goal g()', 1)
    assert resumed['path'] + [{'text': resumed['resume'], 'idx': resumed['idx']}] \
        == report['executed'][1]['path']
    assert [item['text'] for item in report['executed']] == ['a()', 'b()']
    assert world.calls['b'] == 1


def test_goal_trigger_sibling_then_goal_child_is_new_instance(tmp_path, monkeypatch):
    world = World()
    domain = _goal_trigger_domain(tmp_path, world, ['a()', 'b()', {'goal': ['g()']}])
    _strip_pn(monkeypatch)
    report = _run(domain)

    assert report['status'] == 'stuck'
    assert report['stuck']['reason'] == 'no_progress'
    assert report['trigger'] == {'kind': 'goal', 'step': 'goal g()'}
    assert report['stuck']['step'] == 'b()'
    assert report['stuck']['node'] == 'goal g()'
    # The first recovery re-plans b *under the goal node* (path T>goal g()#2, idx 0), which is a
    # different instance from the original b (path T, idx 1), so it is executed; only the second
    # recovery returns that same instance again.
    assert report['replans'] == 2
    assert report['replanned'][0]['steps'] == ['b()'] == report['replanned'][1]['steps']
    assert [item['path'] for item in report['executed']][1:] == [
        [{'text': 'T()', 'idx': 0}], [{'text': 'T()', 'idx': 0}, {'text': 'goal g()', 'idx': 2}]]
    assert world.calls['b'] == 2


def test_same_name_sibling_on_resumed_path_is_not_no_progress(tmp_path):
    world = World({'h()', 's()'})
    world.behave['w'] = lambda n: (world.facts.add('j()'), world.facts.discard('h()'))
    world.behave['x'] = lambda n: None
    world.behave['b'] = lambda n: None
    world.behave['c'] = lambda n: world.facts.add('e()')
    domain = _build(
        tmp_path, world,
        [_act('w', add=['j()']), _act('x', add=['s()']), _act('b', pre=['h()'], add=['e()']),
         _act('c', add=['e()'])],
        [('m1', 'T', [], ['w()', 'x()', 'b()']), ('m2', 'T', [], ['w()', 'x()', 'x()', 'c()'])],
        preds='jhse')
    report = _run(domain)

    assert report['status'] == 'done'
    assert report['stuck'] is None
    assert report['trigger'] == {'kind': 'precondition', 'step': 'b()'}
    assert report['replans'] == 1
    assert report['replanned'][0]['trigger']['kind'] == 'precondition'
    assert [item['text'] for item in report['executed']] == ['w()', 'x()', 'x()', 'c()']
    assert world.calls['x'] == 2
    assert report['replanned'][0]['steps'] == ['x()', 'c()']
