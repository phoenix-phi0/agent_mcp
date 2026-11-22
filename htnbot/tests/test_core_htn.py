import copy
import dataclasses
import json
import re

from planbot import PlanbotError, load_domain
from planbot.core import match_all, parse_literal, parse_task
import pytest


def _pack(action_run=None, sensor_run=None, **extra):
    data = {
        'name': 'demo',
        'predicates': {'p': 0},
        'sensors': [{
            'name': 'sn',
            'run': sensor_run if sensor_run is not None else {'cmds': [['true']]},
            'extract': [],
        }],
        'actions': [{
            'name': 'act', 'params': ['s'], 'pre': [], 'add': ['p()'], 'del': [],
            'run': action_run if action_run is not None else {'cmds': [['true']]},
        }],
        'goals': ['p'],
    }
    data.update(extra)
    return data


def _write(tmp_path, data, name='domain.json'):
    path = tmp_path / name
    path.write_text(json.dumps(data))
    return str(path)


def _load(tmp_path, data, **kwargs):
    return load_domain(_write(tmp_path, data), **kwargs)


def _invalid(tmp_path, data):
    with pytest.raises(PlanbotError) as exc:
        _load(tmp_path, data)
    assert exc.value.code == 'DOMAIN_INVALID'
    return exc.value


def test_plain_pack_has_empty_htn_fields(tmp_path):
    domain = _load(tmp_path, _pack())
    assert domain.tasks == {}
    assert domain.methods == []
    assert domain.cmd_runner is None


def test_cmd_run_loads_and_args_defaults_to_empty(tmp_path):
    domain = _load(tmp_path, _pack(action_run={'cmd': {'name': 'x', 'args': {'p': '{s}'}}}))
    assert domain.actions['act'].run == {'cmd': {'name': 'x', 'args': {'p': '{s}'}}}
    domain = _load(tmp_path, _pack(action_run={'cmd': {'name': 'x'}}, sensor_run={'cmd': {'name': 'y'}}))
    assert domain.actions['act'].run == {'cmd': {'name': 'x', 'args': {}}}
    assert domain.sensors[0].run == {'cmd': {'name': 'y', 'args': {}}}


@pytest.mark.parametrize('args', [
    {'p': '{zz}'},
    {'p': ['a', '{zz}']},
    {'p': {'q': ['x', {'r': 'v{zz}w'}]}},
])
def test_cmd_placeholder_not_in_params(tmp_path, args):
    error = _invalid(tmp_path, _pack(action_run={'cmd': {'name': 'x', 'args': args}}))
    assert 'act' in error.message
    assert 'zz' in error.message


def test_cmd_name_must_be_nonempty_string(tmp_path):
    for name in ('', 3, None):
        _invalid(tmp_path, _pack(action_run={'cmd': {'name': name}}))
    _invalid(tmp_path, _pack(action_run={'cmd': {}}))
    _invalid(tmp_path, _pack(action_run={'cmd': 'x'}))


@pytest.mark.parametrize('args', [['a'], 'a', 3, None])
def test_cmd_args_must_be_object(tmp_path, args):
    _invalid(tmp_path, _pack(action_run={'cmd': {'name': 'x', 'args': args}}))


def test_run_with_cmds_and_cmd_is_invalid(tmp_path):
    run = {'cmds': [['true']], 'cmd': {'name': 'x'}}
    assert 'act' in _invalid(tmp_path, _pack(action_run=run)).message
    assert 'sn' in _invalid(tmp_path, _pack(sensor_run=run)).message


def test_sensor_cmd_args_are_not_checked_for_placeholders(tmp_path):
    domain = _load(tmp_path, _pack(sensor_run={'cmd': {'name': 'x', 'args': {'p': ['{x}']}}}))
    assert domain.sensors[0].run['cmd']['args'] == {'p': ['{x}']}


def test_cmd_runner_is_stored_not_called(tmp_path):
    def runner(name, args):
        raise AssertionError('must not be called')

    domain = load_domain(_write(tmp_path, _pack(action_run={'cmd': {'name': 'x'}})), cmd_runner=runner)
    assert domain.cmd_runner is runner


def test_digest_stable_hex_and_content_sensitive(tmp_path):
    data = _pack()
    first = _load(tmp_path, data).digest
    assert first == _load(tmp_path, data).digest
    assert re.fullmatch(r'[0-9a-f]{64}', first)
    changed = copy.deepcopy(data)
    changed['actions'][0]['add'] = []
    assert _load(tmp_path, changed).digest != first


def test_digest_ignores_key_order_and_callbacks(tmp_path):
    data = _pack()
    reordered = dict(reversed(list(data.items())))
    assert _load(tmp_path, data).digest == _load(tmp_path, reordered, callbacks={'k': print}).digest


def test_digest_is_of_the_file_not_of_filled_defaults(tmp_path):
    with_default = _pack(action_run={'cmd': {'name': 'x'}})
    explicit = _pack(action_run={'cmd': {'name': 'x', 'args': {}}})
    assert _load(tmp_path, with_default).digest != _load(tmp_path, explicit).digest


def test_lone_surrogate_in_cmd_args_does_not_break_digest(tmp_path):
    path = tmp_path / 'domain.json'
    path.write_text(json.dumps(_pack(sensor_run={'cmd': {'name': 'x', 'args': {'k': 'MARK'}}})).replace('MARK', '\\ud800'))
    domain = load_domain(str(path))
    assert re.fullmatch(r'[0-9a-f]{64}', domain.digest)


def test_digest_changes_when_only_a_method_subtasks_change(tmp_path):
    data = _htn()
    d1 = _load(tmp_path, data)
    assert d1.digest == _load(tmp_path, data).digest
    assert re.fullmatch(r'[0-9a-f]{64}', d1.digest)
    changed = copy.deepcopy(data)
    assert changed['methods'][0]['subtasks'] == ['act(?s)']
    changed['methods'][0]['subtasks'] = ['act(?s)', 't2()']
    d2 = _load(tmp_path, changed)
    assert d2.name == d1.name
    assert d1.digest != d2.digest
    assert re.fullmatch(r'[0-9a-f]{64}', d2.digest)


def test_digest_does_not_take_part_in_domain_equality(tmp_path):
    d = _load(tmp_path, _htn())
    assert d.digest
    assert dataclasses.replace(d, digest='') == d


def _htn(tasks=None, methods=None):
    data = _pack(predicates={'p': 0, 'q': 1}, derived=[{'head': 'dq(?x)', 'body': ['q(?x)']}])
    data['tasks'] = tasks if tasks is not None else [
        {'name': 't1', 'params': ['a']}, {'name': 't2', 'params': []},
    ]
    data['methods'] = methods if methods is not None else [_method()]
    return data


def _method(**fields):
    method = {'name': 'm1', 'task': 't1', 'params': ['s'], 'pre': [], 'subtasks': ['act(?s)']}
    method.update(fields)
    return method


def test_tasks_and_methods_load_in_file_order(tmp_path):
    methods = [
        _method(name='m2', task='t2', params=[], subtasks=['t1(c)', {'goal': ['q(c)', 'not p()', 'dq(c)']}]),
        _method(subtasks=['act(?s)', 't2()', 't1(?s)']),
    ]
    domain = _load(tmp_path, _htn(
        tasks=[{'name': 'z', 'params': []}, {'name': 't1', 'params': ['a']}, {'name': 't2', 'params': []}],
        methods=methods))
    assert list(domain.tasks) == ['z', 't1', 't2']
    assert domain.tasks['t1'] == ('a',)
    assert [m.name for m in domain.methods] == ['m2', 'm1']
    sub = domain.methods[0].subtasks
    assert (sub[0].kind, sub[0].name, sub[0].args, sub[0].goal) == ('task', 't1', ('c',), ())
    assert sub[1].kind == 'goal' and (sub[1].name, sub[1].args) == ('', ())
    assert [(lit.positive, lit.atom) for lit in sub[1].goal] == [
        (True, ('q', 'c')), (False, ('p',)), (True, ('dq', 'c'))]
    kinds = [(s.kind, s.name, s.args) for s in domain.methods[1].subtasks]
    assert kinds == [('action', 'act', ('?s',)), ('task', 't2', ()), ('task', 't1', ('?s',))]
    assert domain.methods[1].params == ('s',)


def test_free_variable_from_positive_pre_is_usable(tmp_path):
    method = _method(pre=['q(?f)', 'not q(?s)'], subtasks=['act(?f)', {'goal': ['q(?f)']}])
    domain = _load(tmp_path, _htn(methods=[method]))
    assert domain.methods[0].subtasks[0].args == ('?f',)
    assert domain.methods[0].pre[1].positive is False


def _add_method(**fields):
    return lambda d: d['methods'].append(_method(name='mx', **fields))


@pytest.mark.parametrize('mutate, needle', [
    (lambda d: d['tasks'].append({'name': 'act', 'params': []}), 'act'),
    (lambda d: d['tasks'].append({'name': 't1', 'params': []}), 't1'),
    (lambda d: d['tasks'].append({'name': 'tx', 'params': ['a', 'a']}), 'tx'),
    (lambda d: d['methods'].append(_method()), 'm1'),
    (_add_method(task='nope'), 'mx'),
    (_add_method(params=['s', 'u']), 'mx'),
    (_add_method(task='t2'), 'mx'),
    (_add_method(task='t2', params=['s', 's']), 'mx'),
    (_add_method(params=['s', 's']), 'mx'),
    (_add_method(pre=['zz()']), 'mx'),
    (_add_method(pre=['q()']), 'mx'),
    (_add_method(pre=['not q(?u)']), 'mx'),
    (_add_method(pre=['q(?u)', 'not q(?v)']), 'mx'),
    (_add_method(subtasks=['ghost(?s)']), 'mx'),
    (_add_method(subtasks=['act()']), 'mx'),
    (_add_method(subtasks=['t2(c)']), 'mx'),
    (_add_method(subtasks=['act(?u)']), 'mx'),
    (_add_method(subtasks=['not act(?s)']), 'mx'),
    (_add_method(subtasks=['act(?s']), 'mx'),
    (_add_method(subtasks=[{'goal': []}]), 'mx'),
    (_add_method(subtasks=[{'goal': ['zz()']}]), 'mx'),
    (_add_method(subtasks=[{'goal': ['q(?u)']}]), 'mx'),
    (_add_method(subtasks=[{'goal': ['q()']}]), 'mx'),
    (lambda d: d['methods'][0].pop('subtasks'), 'm1'),
])
def test_invalid_tasks_and_methods(tmp_path, mutate, needle):
    data = _htn()
    mutate(data)
    assert needle in _invalid(tmp_path, data).message


def test_methods_without_tasks_is_invalid(tmp_path):
    assert 'm1' in _invalid(tmp_path, _pack(methods=[_method()])).message


def _lits(*texts):
    return tuple(parse_literal(t) for t in texts)


def _facts(*atoms):
    return frozenset(tuple(a.split()) for a in atoms)


def test_match_all_without_free_variables():
    facts = _facts('q a', 'r')
    binding = {'x': 'a'}
    ok = match_all(_lits('q(?x)', 'r()', 'not s()'), facts, binding)
    assert ok == [{'x': 'a'}] and ok[0] is not binding
    ok[0]['y'] = 'z'
    assert binding == {'x': 'a'}
    assert match_all(_lits('q(?x)', 'not r()'), facts, binding) == []
    assert match_all(_lits('q(?x)'), facts, {'x': 'b'}) == []
    empty = match_all((), facts, binding)
    assert empty == [{'x': 'a'}] and empty[0] is not binding
    assert match_all((), facts, {}) == [{}]


def test_match_all_returns_sorted_bindings_and_is_repeatable():
    facts = _facts('e c a', 'e b z', 'e b a', 'e a c', 'e a b', 'k a', 'k b')
    binding = {'w': 'w0'}
    lits = _lits('e(?y,?x)', 'k(?y)')
    expected = [
        # ordered by sorted (key, value) pairs: x first, then y
        {'w': 'w0', 'x': 'a', 'y': 'b'}, {'w': 'w0', 'x': 'b', 'y': 'a'},
        {'w': 'w0', 'x': 'c', 'y': 'a'}, {'w': 'w0', 'x': 'z', 'y': 'b'},
    ]
    first = match_all(lits, facts, binding)
    assert first == expected
    assert match_all(lits, frozenset(sorted(facts, reverse=True)), binding) == first
    assert binding == {'w': 'w0'}
    # repeated variable and duplicate literals do not produce duplicates
    assert match_all(_lits('e(?y,?x)', 'e(?y,?x)', 'e(?x,?x)'), _facts('e a a', 'e a b'), {}) == [
        {'x': 'a', 'y': 'a'}]


def test_match_all_negative_literals_filter():
    facts = _facts('e a b', 'e a c', 'e a d', 'bad c', 'bad d')
    assert match_all(_lits('e(a,?x)', 'not bad(?x)'), facts, {}) == [{'x': 'b'}]
    assert match_all(_lits('not bad(?x)', 'e(a,?x)'), facts, {}) == [{'x': 'b'}]
    assert match_all(_lits('e(a,?x)', 'not bad(?u)'), facts, {}) == []
    assert match_all(_lits('not bad(?u)'), facts, {}) == []
    assert match_all(_lits('not bad(?u)'), facts, {'u': 'b'}) == [{'u': 'b'}]


@pytest.mark.parametrize('text, expected', [
    ('t1(c)', ('t1', 'c')), (' t1( c ) ', ('t1', 'c')), ('t2()', ('t2',)), ('t2', ('t2',)),
])
def test_parse_task_ok(tmp_path, text, expected):
    assert parse_task(_load(tmp_path, _htn()), text) == expected


@pytest.mark.parametrize('text', [
    'ghost(c)', 't1()', 't1(a,b)', 't2(c)', 't1(?x)', 'not t1(c)', 'not t2()', '', 't1(c',
])
def test_parse_task_invalid(tmp_path, text):
    with pytest.raises(PlanbotError) as exc:
        parse_task(_load(tmp_path, _htn()), text)
    assert exc.value.code == 'GOAL_INVALID'
    assert text in exc.value.message
