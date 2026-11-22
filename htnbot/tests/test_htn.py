import ast
import copy
import json
import re
import sys
from pathlib import Path

import pytest

from planbot import PlanbotError, load_domain
from planbot.core import parse_literal
from planbot.htn import decompose, decompose_task, from_memory, goal_checks, remaining_agenda

ROOT = Path(__file__).resolve().parent.parent
NODE_KEYS = {'kind', 'name', 'args', 'goal', 'text', 'idx', 'path', 'method', 'binding', 'why',
             'tried', 'done', 'children', 'step'}


def _noop(*_args, **_kwargs):
    raise AssertionError('actions must not be executed')


def act(name, params=(), pre=(), add=(), delete=()):
    return {'name': name, 'params': list(params), 'pre': list(pre), 'add': list(add),
            'del': list(delete), 'run': {'callback': 'noop'}}


def meth(name, task, subtasks, params=(), pre=()):
    return {'name': name, 'task': task, 'params': list(params), 'pre': list(pre),
            'subtasks': list(subtasks)}


def make_domain(tmp_path, actions, tasks, methods, predicates=None, derived=None, file='domain.json'):
    """Write a neutral domain package under tmp_path and load it; tasks maps name -> params."""
    data = {'name': 'mini', 'predicates': predicates or {}, 'derived': derived or [],
            'sensors': [], 'actions': actions, 'goals': [],
            'tasks': [{'name': name, 'params': list(params)} for name, params in tasks.items()],
            'methods': methods}
    path = tmp_path / file
    path.write_text(json.dumps(data), encoding='utf-8')
    return load_domain(str(path), callbacks={'noop': _noop})


def facts(*texts):
    return frozenset(parse_literal(text).atom for text in texts)


def everything(domain):
    return frozenset(domain.actions)


def run_task(domain, task, base=(), allowed=None, **kwargs):
    allowed = everything(domain) if allowed is None else frozenset(allowed)
    return decompose_task(domain, facts(*base), task, allowed, **kwargs)


def texts(result):
    return [step['text'] for step in result['steps']]


def el(text, idx):
    return {'text': text, 'idx': idx}


def ti(items):
    return [(item['text'], item['idx']) for item in items]


def test_single_method_steps_idx_path_and_node_fields(tmp_path):
    domain = make_domain(tmp_path, [act('a1', add=['p()']), act('a2', ['x'], pre=['p()'], add=['q(?x)']),
                                    act('a3')],
                         {'T': ['x']}, [meth('m', 'T', ['a1()', 'a2(?x)', 'a3()'], ['x'], ['not q(?x)'])],
                         {'p': 0, 'q': 1})
    result = run_task(domain, ('T', 'k'))
    root = {'kind': 'task', 'name': 'T', 'args': ['k'], 'goal': [], 'text': 'T(k)', 'idx': 0, 'resume': None}
    assert set(result) == {'found', 'source', 'agenda', 'steps', 'tree', 'failure'}
    assert (result['found'], result['source'], result['failure']) == (True, 'decompose', None)
    assert result['agenda'] == [root]
    assert texts(result) == ['a1()', 'a2(k)', 'a3()']
    [node] = result['tree']
    assert set(node) == NODE_KEYS
    assert (node['idx'], node['path'], node['step'], node['done'], node['tried']) == (0, [], None, [], [])
    assert (node['method'], node['binding'], node['why']) == ('m', {'x': 'k'}, ['not q(k)'])
    assert [c['idx'] for c in node['children']] == [0, 1, 2]
    assert [c['step'] for c in node['children']] == [1, 2, 3]
    assert node['children'][1] == {
        'kind': 'action', 'name': 'a2', 'args': ['k'], 'goal': [], 'text': 'a2(k)', 'idx': 1,
        'path': [el('T(k)', 0)], 'method': None, 'binding': None, 'why': [], 'tried': [], 'done': [],
        'children': [], 'step': 2}
    assert result['steps'][1] == {'action': 'a2', 'args': ['k'], 'text': 'a2(k)', 'irreversible': False,
                                  'path': [el('T(k)', 0)]}
    assert all(step['path'] == [el('T(k)', 0)] for step in result['steps'])


def test_precondition_fallback_with_free_variable_negation_and_derived(tmp_path):
    domain = make_domain(tmp_path, [act('ok')], {'T': []}, [
        meth('m0', 'T', ['ok()'], pre=['e(?y)']),
        meth('m1', 'T', ['ok()'], pre=['p()', 'not d()', 'r()']),
        meth('m2', 'T', ['ok()'], pre=['d()', 'not p()']),
    ], {'p': 0, 'q': 0, 'r': 0, 'e': 1}, [{'head': 'd()', 'body': ['q()']}])
    node = run_task(domain, ('T',), ['q()', 'r()'])['tree'][0]
    assert (node['method'], node['why']) == ('m2', ['d()', 'not p()'])
    assert node['tried'] == [
        {'method': 'm0', 'binding': {}, 'reason': 'precondition', 'detail': ['e(?y)'], 'sub': None},
        {'method': 'm1', 'binding': {}, 'reason': 'precondition', 'detail': ['not d()', 'p()'], 'sub': None},
    ]


def test_nested_task_sees_expected_effects_of_earlier_subtask(tmp_path):
    domain = make_domain(tmp_path, [act('put', ['x'], add=['q(?x)']), act('fin')], {'T': ['x'], 'U': ['y']}, [
        meth('mt', 'T', ['put(?x)', 'U(?x)'], ['x']),
        meth('mu', 'U', ['fin()'], ['y'], ['q(?y)']),
    ], {'q': 1})
    result = run_task(domain, ('T', 'k'))
    assert texts(result) == ['put(k)', 'fin()']
    sub = result['tree'][0]['children'][1]
    assert (sub['text'], sub['idx'], sub['path']) == ('U(k)', 1, [el('T(k)', 0)])
    assert (sub['method'], sub['binding'], sub['why']) == ('mu', {'y': 'k'}, ['q(k)'])
    assert result['steps'][1]['path'] == [el('T(k)', 0), el('U(k)', 1)]


def _fallback_domain(tmp_path):
    return make_domain(tmp_path, [act('ok'), act('need', pre=['p()'])], {'T': [], 'V': []}, [
        meth('m1', 'T', ['ok()', 'need()']), meth('m2', 'T', ['V()']), meth('m3', 'T', ['ok()']),
        meth('mv', 'V', ['ok()'], pre=['p()']),
    ], {'p': 0})


def test_subtask_failed_backtracks_to_next_method(tmp_path):
    result = run_task(_fallback_domain(tmp_path), ('T',))
    assert texts(result) == ['ok()']
    node = result['tree'][0]
    assert node['method'] == 'm3'
    assert node['tried'] == [
        {'method': 'm1', 'binding': {}, 'reason': 'subtask_failed', 'detail': ['need()'],
         'sub': {'item': 'need()', 'detail': ['missing: p()'], 'tried': []}},
        {'method': 'm2', 'binding': {}, 'reason': 'subtask_failed', 'detail': ['V()'],
         'sub': {'item': 'V()', 'detail': [], 'tried': [
             {'method': 'mv', 'binding': {}, 'reason': 'precondition', 'detail': ['p()'], 'sub': None}]}},
    ]


def _later_domain(tmp_path):
    return make_domain(tmp_path, [act('setp', add=['p()']), act('ok'), act('banned')],
                       {'R': [], 'A': [], 'B': []}, [
        meth('mr', 'R', ['A()', 'B()']),
        meth('a1', 'A', ['setp()']), meth('a2', 'A', ['ok()']),
        meth('b1', 'B', ['ok()'], pre=['not p()']), meth('b2', 'B', ['banned()']),
    ], {'p': 0})


def test_later_failed_records_trace_of_later_sibling(tmp_path):
    domain = _later_domain(tmp_path)
    result = run_task(domain, ('R',), allowed=everything(domain) - {'banned'})
    assert texts(result) == ['ok()', 'ok()']
    a_node, b_node = result['tree'][0]['children']
    assert (a_node['method'], b_node['method'], b_node['tried']) == ('a2', 'b1', [])
    assert a_node['tried'] == [{'method': 'a1', 'binding': {}, 'reason': 'later_failed', 'detail': ['B()'],
                                'sub': {'item': 'B()', 'detail': [], 'tried': [
        {'method': 'b1', 'binding': {}, 'reason': 'precondition', 'detail': ['not p()'], 'sub': None},
        {'method': 'b2', 'binding': {}, 'reason': 'not_allowed', 'detail': ['banned'], 'sub': None}]}}]


def test_free_variable_bindings_tried_in_sorted_order(tmp_path):
    domain = make_domain(tmp_path, [act('use', ['v'], pre=['good(?v)'])], {'T': []},
                         [meth('m', 'T', ['use(?v)'], pre=['cand(?v)'])], {'cand': 1, 'good': 1})
    result = run_task(domain, ('T',), ['cand(b)', 'cand(a)', 'good(b)'])
    node = result['tree'][0]
    assert (texts(result), node['binding'], node['why']) == (['use(b)'], {'v': 'b'}, ['cand(b)'])
    assert node['tried'] == [{'method': 'm', 'binding': {'v': 'a'}, 'reason': 'subtask_failed',
                              'detail': ['use(a)'],
                              'sub': {'item': 'use(a)', 'detail': ['missing: good(a)'], 'tried': []}}]


def _goal_domain(tmp_path):
    return make_domain(tmp_path, [act('mk1', add=['p()']), act('mk2', pre=['p()'], add=['q()']), act('fin'),
                                  act('mkz', add=['z()'])],
                       {'T': [], 'G': []}, [
        meth('mt', 'T', ['fin()', {'goal': ['q()', 'p()']}, 'fin()']),
        meth('mg', 'G', [{'goal': ['z()']}]), meth('alt', 'G', ['fin()']),
    ], {'p': 0, 'q': 0, 'z': 0})


def test_goal_subtask_plans_and_already_satisfied(tmp_path):
    domain = _goal_domain(tmp_path)
    result = run_task(domain, ('T',))
    assert texts(result) == ['fin()', 'mk1()', 'mk2()', 'fin()']
    goal = result['tree'][0]['children'][1]
    assert (goal['kind'], goal['text'], goal['goal'], goal['idx']) == ('goal', 'goal q(), p()', ['q()', 'p()'], 1)
    assert (goal['method'], goal['binding'], goal['step']) == (None, None, None)
    assert [(c['text'], c['idx'], c['step'], c['path']) for c in goal['children']] == [
        ('mk1()', 0, 2, [el('T()', 0), el('goal q(), p()', 1)]),
        ('mk2()', 1, 3, [el('T()', 0), el('goal q(), p()', 1)])]
    assert result['steps'][1]['path'] == [el('T()', 0), el('goal q(), p()', 1)]
    satisfied = run_task(domain, ('T',), ['p()', 'q()'])
    assert texts(satisfied) == ['fin()', 'fin()']
    assert satisfied['tree'][0]['children'][1]['children'] == []


def test_goal_subtask_without_plan_abandons_method(tmp_path):
    domain = _goal_domain(tmp_path)
    tried = run_task(domain, ('G',), allowed=['fin', 'mk1', 'mk2'])['tree'][0]['tried']
    assert tried == [{'method': 'mg', 'binding': {}, 'reason': 'subtask_failed', 'detail': ['goal z()'],
                      'sub': {'item': 'goal z()', 'detail': ['no plan: no_producer', 'excluded: mkz'],
                              'tried': []}}]
    plain = make_domain(tmp_path, [act('fin')], {'G': []}, [meth('mg', 'G', [{'goal': ['z()']}]),
                                                            meth('alt', 'G', ['fin()'])], {'z': 0}, file='g.json')
    assert run_task(plain, ('G',))['tree'][0]['tried'][0]['sub']['detail'] == ['no plan: no_producer']


def test_not_allowed_methods_and_all_excluded(tmp_path):
    domain = make_domain(tmp_path, [act('ok'), act('banned'), act('zb')], {'T': [], 'S': []}, [
        meth('m1', 'T', ['zb()', 'banned()', 'zb()']), meth('m2', 'T', ['ok()']),
        meth('s1', 'S', ['banned()']),
    ])
    allowed = ['ok']
    node = run_task(domain, ('T',), allowed=allowed)['tree'][0]
    assert node['method'] == 'm2'
    assert node['tried'] == [{'method': 'm1', 'binding': {}, 'reason': 'not_allowed',
                              'detail': ['banned', 'zb'], 'sub': None}]
    result = run_task(domain, ('S',), allowed=allowed)
    assert (result['found'], result['steps'], result['tree']) == (False, [], [])
    assert result['failure'] == {'kind': 'no_method', 'item': 'S()', 'detail': [], 'tried': [
        {'method': 's1', 'binding': {}, 'reason': 'not_allowed', 'detail': ['banned'], 'sub': None}],
        'max_depth': 20, 'max_nodes': 10000}


def test_depth_limit_and_attempt_limit(tmp_path):
    domain = make_domain(tmp_path, [act('ok')], {'L': []}, [meth('ml', 'L', ['L()'])])
    result = run_task(domain, ('L',), max_depth=5)
    assert result['found'] is False and result['failure']['kind'] == 'no_method'
    trace = result['failure']
    for _ in range(5):
        assert [a['reason'] for a in trace['tried']] == ['subtask_failed']
        trace = trace['tried'][0]['sub']
    assert trace == {'item': 'L()', 'detail': ['depth limit 5'], 'tried': []}
    limited = run_task(_fallback_domain(tmp_path), ('T',), max_nodes=1)
    assert (limited['found'], limited['steps'], limited['tree']) == (False, [], [])
    assert limited['failure'] == {'kind': 'limit', 'item': None, 'detail': [], 'tried': [],
                                  'max_depth': 20, 'max_nodes': 1}


def test_wide_method_without_recursion_error(tmp_path):
    names = [f'c{i}' for i in range(500)]
    domain = make_domain(tmp_path, [act('n', ['x']), act('mark', add=['p()']), act('need', pre=['not p()'])],
                         {'W': [], 'Top': [], 'Tail': []}, [
        meth('w1', 'W', ['mark()'] + [f'n({c})' for c in names[:499]]),
        meth('w2', 'W', [f'n({c})' for c in names]),
        meth('top', 'Top', ['W()', 'Tail()']),
        meth('t1', 'Tail', ['need()'], pre=['p()']), meth('t2', 'Tail', ['need()']),
    ], {'p': 0})
    plain = decompose(domain, frozenset(), [{'kind': 'task', 'name': 'W', 'args': [], 'goal': [],
                                             'text': 'W()', 'idx': 0, 'resume': None}],
                      everything(domain), max_nodes=10000)
    assert plain['found'] is True and texts(plain)[:2] == ['mark()', 'n(c0)'] and len(plain['steps']) == 500
    result = run_task(domain, ('Top',))
    assert result['found'] is True
    assert texts(result) == [f'n({c})' for c in names] + ['need()']
    w_node = result['tree'][0]['children'][0]
    assert (w_node['method'], w_node['tried'][0]['reason']) == ('w2', 'later_failed')
    assert w_node['tried'][0]['sub']['item'] == 'Tail()'


def test_empty_method_and_determinism(tmp_path):
    domain = make_domain(tmp_path, [act('ok')], {'E': []}, [meth('me', 'E', [])])
    result = run_task(domain, ('E',))
    assert (result['found'], result['steps'], result['tree'][0]['children']) == (True, [], [])
    later = _later_domain(tmp_path)
    allowed = everything(later) - {'banned'}
    first = json.dumps(run_task(later, ('R',), allowed=allowed), sort_keys=True)
    assert first == json.dumps(run_task(later, ('R',), allowed=allowed), sort_keys=True)
    assert decompose(domain, frozenset(), [], frozenset())['tree'] == []


def _resume_domain(tmp_path):
    return make_domain(tmp_path, [act('a1'), act('a2'), act('a3', pre=['p()']), act('a4')], {'T': [], 'U': []}, [
        meth('mt', 'T', ['a1()', 'U()', 'a4()']), meth('mu', 'U', ['a2()', 'a3()']),
    ], {'p': 0})


def _ref(kind, text, idx):
    return {'kind': kind, 'name': text[:-2], 'args': [], 'goal': [], 'text': text, 'idx': idx}


def _item(kind, text, idx, resume=None):
    return dict(_ref(kind, text, idx), resume=resume)


def test_remaining_agenda_with_nonempty_prefix_and_resuming(tmp_path):
    domain = _resume_domain(tmp_path)
    first = run_task(domain, ('T',), ['p()'])
    again = remaining_agenda(first, step=3)
    u_item = _item('task', 'U()', 1, {'method': 'mu', 'binding': {}, 'done': [_ref('action', 'a2()', 0)],
                                      'rest': [_item('action', 'a3()', 1)], 'switch': True})
    assert again == {'resume': 'U()', 'idx': 1, 'path': [el('T()', 0)], 'agenda': [
        _item('task', 'T()', 0, {'method': 'mt', 'binding': {}, 'done': [_ref('action', 'a1()', 0)],
                                 'rest': [u_item, _item('action', 'a4()', 2)], 'switch': False})]}
    assert first['steps'][2]['text'] == 'a3()'
    second = decompose(domain, facts('p()'), again['agenda'], everything(domain))
    assert texts(second) == ['a3()', 'a4()']
    root = second['tree'][0]
    assert ti(root['done']) == [('a1()', 0)] and ti(root['children']) == [('U()', 1), ('a4()', 2)]
    assert ti(root['children'][0]['done']) == [('a2()', 0)]
    assert ti(root['children'][0]['children']) == [('a3()', 1)]
    assert second['steps'][0]['path'] == [el('T()', 0), el('U()', 1)]
    # Second recovery: done accumulates and idx stays contiguous from 0.
    third = remaining_agenda(second, step=2)
    assert (third['resume'], third['idx'], third['path']) == ('T()', 0, [])
    resume = third['agenda'][0]['resume']
    assert (ti(resume['done']), ti(resume['rest']), resume['switch']) == (
        [('a1()', 0), ('U()', 1)], [('a4()', 2)], True)
    assert ti(remaining_agenda(second, step=1)['agenda'][0]['resume']['rest'][0]['resume']['done']) == [
        ('a2()', 0)]
    last = decompose(domain, facts(), third['agenda'], everything(domain))
    assert texts(last) == ['a4()'] and last['steps'][0]['path'] == [el('T()', 0)]


def test_remaining_agenda_with_empty_prefix(tmp_path):
    first = run_task(_resume_domain(tmp_path), ('T',), ['p()'])
    again = remaining_agenda(first, step=2)
    assert (again['resume'], again['idx']) == ('U()', 1)
    resume = again['agenda'][0]['resume']
    assert ti(resume['done']) == [('a1()', 0)]
    assert resume['rest'] == [_item('task', 'U()', 1), _item('action', 'a4()', 2)]
    assert remaining_agenda(first, step=1) == {'resume': 'T()', 'idx': 0, 'path': [],
                                               'agenda': [_item('task', 'T()', 0)]}
    assert first['tree'][0]['done'] == []


def _switch_domain(tmp_path, with_m3=True):
    methods = [meth('m1', 'T', ['a()', 'b()']), meth('m2', 'T', ['x()', 'c()'])]
    methods += [meth('m3', 'T', ['a()', 'c()'])] if with_m3 else []
    return make_domain(tmp_path, [act('a'), act('b', pre=['p()']), act('c'), act('x')], {'T': []}, methods,
                       {'p': 0}, file=f'switch{with_m3}.json')


def _switch_agenda(switch=True):
    return [_item('task', 'T()', 0, {'method': 'm1', 'binding': {}, 'done': [_ref('action', 'a()', 0)],
                                     'rest': [_item('action', 'b()', 1)], 'switch': switch})]


def test_resume_switches_to_candidate_matching_done_prefix(tmp_path):
    domain = _switch_domain(tmp_path)
    result = decompose(domain, frozenset(), _switch_agenda(), everything(domain))
    assert texts(result) == ['c()']
    root = result['tree'][0]
    assert (root['method'], ti(root['done']), ti(root['children'])) == ('m3', [('a()', 0)], [('c()', 1)])
    first, second = root['tried']
    assert (first['method'], first['reason']) == ('m1', 'subtask_failed')
    assert first['sub']['detail'][0].startswith('missing: ')
    assert second == {'method': 'm2', 'binding': {}, 'reason': 'prefix_mismatch', 'detail': ['a()'], 'sub': None}


def test_resume_cannot_connect_and_switch_false(tmp_path):
    domain = _switch_domain(tmp_path, with_m3=False)
    result = decompose(domain, frozenset(), _switch_agenda(), everything(domain))
    assert (result['found'], result['failure']['kind'], result['failure']['item']) == (False, 'no_method', 'T()')
    assert [(a['method'], a['reason']) for a in result['failure']['tried']] == [
        ('m1', 'subtask_failed'), ('m2', 'prefix_mismatch')]
    fixed = _switch_domain(tmp_path)
    result = decompose(fixed, frozenset(), _switch_agenda(switch=False), everything(fixed))
    assert result['found'] is False
    assert [(a['method'], a['reason']) for a in result['failure']['tried']] == [('m1', 'subtask_failed')]


def test_same_name_siblings_are_told_apart_by_idx(tmp_path):
    domain = make_domain(tmp_path, [act('x'), act('y')], {'T': []}, [meth('m', 'T', ['x()', 'x()', 'y()'])])
    again = remaining_agenda(run_task(domain, ('T',)), step=2)
    resume = again['agenda'][0]['resume']
    assert ti(resume['done']) == [('x()', 0)]
    assert ti(resume['rest']) == [('x()', 1), ('y()', 2)]
    assert texts(decompose(domain, frozenset(), again['agenda'], everything(domain))) == ['x()', 'y()']


def test_goal_node_resume_and_usage_errors(tmp_path):
    domain = make_domain(tmp_path, [act('ok'), act('mk', add=['q()']), act('fin')], {'T': []},
                         [meth('m', 'T', ['ok()', {'goal': ['q()']}, 'fin()'])], {'q': 0})
    result = run_task(domain, ('T',))
    again = remaining_agenda(result, loc=[0, 1])
    goal = {'kind': 'goal', 'name': '', 'args': [], 'goal': ['q()'], 'text': 'goal q()', 'idx': 1, 'resume': None}
    assert (again['resume'], again['idx'], again['path']) == ('goal q()', 1, [el('T()', 0)])
    assert again['agenda'] == [_item('task', 'T()', 0, {
        'method': 'm', 'binding': {}, 'done': [_ref('action', 'ok()', 0)],
        'rest': [goal, _item('action', 'fin()', 2)], 'switch': False})]
    assert remaining_agenda(result, step=2) == again
    top = decompose(domain, frozenset(), [_item('action', 'ok()', 0)], everything(domain))
    for kwargs, source in [({'loc': [0, 0]}, result), ({'loc': [0, 5]}, result), ({'loc': []}, result),
                           ({'step': 1, 'loc': [0, 1]}, result), ({}, result), ({'step': 0}, result),
                           ({'step': 4}, result), ({'step': 1}, top)]:
        with pytest.raises(PlanbotError) as exc:
            remaining_agenda(source, **kwargs)
        assert exc.value.code == 'USAGE'


def test_engine_source_is_domain_neutral():
    source = (ROOT / 'planbot' / 'htn.py').read_text(encoding='utf-8')
    words = set()
    for path in sorted((ROOT / 'examples').glob('*/domain.json')):
        data = json.loads(path.read_text(encoding='utf-8'))
        words.add(data['name'])
        words.update(entry['name'] for key in ('actions', 'tasks', 'methods') for entry in data.get(key, []))
        words.update(data['predicates'])
        words.update(rule['head'].partition('(')[0] for rule in data.get('derived', []))
    tokens = {token.lower() for token in re.findall(r'[A-Za-z_][A-Za-z0-9_]*', source)}
    assert not tokens & {word.lower() for word in words}
    assert 'subprocess' not in source and 'cmd_runner' not in source and 'callbacks' not in source
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            assert all(alias.name.split('.')[0] in sys.stdlib_module_names for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 1 or node.module.split('.')[0] in sys.stdlib_module_names


def _goal_check_domain(tmp_path, file='goal_check.json'):
    return make_domain(tmp_path, [act('a1', add=['z()']), act('s1', add=['p()']), act('s2', pre=['p()'], add=['q()'])],
                       {'M': []}, [meth('mg', 'M', ['a1()', {'goal': ['q()']}, {'goal': ['q()']}])],
                       {'p': 0, 'q': 0, 'z': 0, 'r': 0}, file=file)


def test_goal_checks_report_goal_boundaries_in_order(tmp_path):
    domain = _goal_check_domain(tmp_path)
    result = run_task(domain, ('M',))
    assert texts(result) == ['a1()', 's1()', 's2()']
    first, second = result['tree'][0]['children'][1:]
    assert [c['step'] for c in first['children']] == [2, 3]
    assert second['children'] == []
    assert goal_checks(result, 3) == [
        {'loc': [0, 1], 'text': 'goal q()', 'goal': ['q()'], 'idx': 1, 'path': [el('M()', 0)]},
        {'loc': [0, 2], 'text': 'goal q()', 'goal': ['q()'], 'idx': 2, 'path': [el('M()', 0)]}]
    assert goal_checks(result, 2) == []


def test_goal_already_true_at_start_is_reported_at_zero(tmp_path):
    domain = make_domain(tmp_path, [act('ok')], {'M': []}, [meth('mh', 'M', [{'goal': ['p()']}, 'ok()'])],
                         {'p': 0})
    result = run_task(domain, ('M',), ['p()'])
    assert result['tree'][0]['children'][0]['children'] == []
    assert goal_checks(result, 0) == [
        {'loc': [0, 0], 'text': 'goal p()', 'goal': ['p()'], 'idx': 0, 'path': [el('M()', 0)]}]
    assert goal_checks(result, 1) == []


def test_from_memory_replays_unchanged_tree(tmp_path):
    domain = _goal_check_domain(tmp_path)
    fresh = run_task(domain, ('M',))
    replayed = from_memory(domain, facts(), ('M',), fresh['tree'], everything(domain))
    assert replayed['source'] == 'memory' and replayed['found'] is True
    assert replayed['steps'] == fresh['steps']
    assert replayed['failure'] is None
    assert replayed['tree'] == fresh['tree']
    assert replayed['agenda'] == [{'kind': 'task', 'name': 'M', 'args': [], 'goal': [], 'text': 'M()',
                                   'idx': 0, 'resume': None}]


def test_from_memory_returns_none_when_a_check_fails(tmp_path):
    domain = _goal_check_domain(tmp_path)
    tree = run_task(domain, ('M',))['tree']
    allowed = everything(domain)
    assert from_memory(domain, facts(), ('M',), tree, allowed) is not None
    pre_domain = make_domain(tmp_path, [act('use', pre=['p()'], add=['q()'])], {'M': []},
                             [meth('mu', 'M', ['use()'])], {'p': 0, 'q': 0}, file='pre.json')
    pre_tree = run_task(pre_domain, ('M',), ['p()'])['tree']
    assert from_memory(pre_domain, facts(), ('M',), pre_tree, everything(pre_domain)) is None
    assert from_memory(pre_domain, facts('p()'), ('M',), pre_tree, everything(pre_domain)) is not None
    assert from_memory(domain, facts(), ('M',), tree, allowed - {'s1'}) is None
    assert from_memory(domain, facts(), ('N',), tree, allowed) is None
    assert from_memory(domain, facts(), ('M', 'k'), tree, allowed) is None
    goal_false = copy.deepcopy(tree)
    goal_false[0]['children'][1]['goal'] = ['r()']
    assert from_memory(domain, facts(), ('M',), goal_false, allowed) is None
    goal_bad_text = copy.deepcopy(tree)
    goal_bad_text[0]['children'][1]['goal'] = ['((']
    assert from_memory(domain, facts(), ('M',), goal_bad_text, allowed) is None
    missing_key = copy.deepcopy(tree)
    del missing_key[0]['children']
    assert from_memory(domain, facts(), ('M',), missing_key, allowed) is None
    with_done = copy.deepcopy(tree)
    with_done[0]['done'] = [{'kind': 'action', 'name': 'a1', 'args': [], 'goal': [], 'text': 'a1()', 'idx': 0}]
    assert from_memory(domain, facts(), ('M',), with_done, allowed) is None
    assert from_memory(domain, facts(), ('M',), tree + tree, allowed) is None
