"""Pure text-rendering functions for decomposition results (hand-built dicts)."""

import json

import pytest

from planbot import core, executor, htn, planner
from planbot.cli import _fmt_path, _render_attempts, _render_htn_plan, _render_tree, main
from planbot.memory import Memory


def _node(kind, text, idx=0, **kw):
    base = {'kind': kind, 'name': text.split('(')[0], 'args': [], 'goal': [], 'text': text,
            'idx': idx, 'path': [], 'method': None, 'binding': None, 'why': [],
            'tried': [], 'done': [], 'children': [], 'step': None}
    base.update(kw)
    return base


def _step(text, irreversible=False):
    return {'action': text.split('(')[0], 'args': [], 'text': text,
            'irreversible': irreversible, 'path': []}


def _result(tree, steps, source='decompose'):
    return {'found': True, 'source': source, 'agenda': [], 'steps': steps,
            'tree': tree, 'failure': None}


def _attempt(method, reason, detail=(), sub=None):
    return {'method': method, 'binding': {}, 'reason': reason, 'detail': list(detail), 'sub': sub}


def test_fmt_path():
    assert _fmt_path([{'text': 'a()', 'idx': 0}, {'text': 'b(x)', 'idx': 2}]) == 'a()#0 > b(x)#2'
    assert _fmt_path([]) == ''


def test_two_level_tree_and_plan_numbers_match():
    leaf1 = _node('action', 'a1(x)', 0, step=1)
    leaf2 = _node('action', 'a2(x)', 1, step=2)
    inner = _node('task', 'sub(x)', 0, method='m2', why=['q(x)'], children=[leaf1, leaf2])
    root = _node('task', 'top()', 0, method='m1', binding={'z': '2', 'a': '1'},
                 why=['p(a)', 'p(b)'], tried=[_attempt('m0', 'precondition', ['p(a)'])],
                 children=[inner])
    result = _result([root], [_step('a1(x)'), _step('a2(x)')])
    assert _render_tree(result) == [
        'tree:',
        '  top() [method: m1] {a=1, z=2}',
        '    why: p(a), p(b)',
        '    skipped m0: precondition: p(a)',
        '    sub(x) [method: m2]',
        '      why: q(x)',
        '      1. a1(x)',
        '      2. a2(x)',
    ]
    assert _render_htn_plan(result) == [
        'plan: 2 steps (source: decompose)', '  1. a1(x)', '  2. a2(x)']


def test_done_line_before_why_and_empty_why():
    root = _node('task', 'top()', 0, method='m1',
                 done=[{'text': 'x()', 'idx': 0}, {'text': 'y()', 'idx': 1}],
                 children=[_node('action', 'z()', 2, step=1)])
    assert _render_tree(_result([root], [_step('z()')])) == [
        'tree:', '  top() [method: m1]', '    done: x(), y()', '    why: -', '    1. z()']


def test_goal_node_and_multi_detail_joined():
    goal = _node('goal', 'goal p(a), q(b)', 0, children=[_node('action', 'act()', 0, step=1)])
    root = _node('task', 't()', 0, method='m', why=['w()'],
                 tried=[_attempt('m0', 'not_allowed', ['x', 'y'])], children=[goal])
    assert _render_tree(_result([root], [_step('act()')])) == [
        'tree:', '  t() [method: m]', '    why: w()', '    skipped m0: not_allowed: x, y',
        '    goal p(a), q(b)', '      1. act()']


def test_later_failed_nested():
    sub = {'item': 't2()', 'detail': [],
           'tried': [_attempt('m3', 'not_allowed', ['act'])]}
    tried = [_attempt('m1', 'later_failed', ['t2()'], sub)]
    assert _render_attempts(tried, 4) == [
        '    skipped m1: later_failed: t2()',
        '      t2()',
        '        skipped m3: not_allowed: act',
    ]
    root = _node('task', 't()', 0, method='m2', why=[], tried=tried)
    assert _render_tree(_result([root], []))[3:] == [
        '    skipped m1: later_failed: t2()',
        '      t2()',
        '        skipped m3: not_allowed: act',
    ]


def test_sub_detail_joined_with_semicolon():
    sub = {'item': 'foo()', 'detail': ['no methods', 'depth limit 3'], 'tried': []}
    assert _render_attempts([_attempt('m', 'subtask_failed', ['foo()'], sub)], 0) == [
        'skipped m: subtask_failed: foo()', '  foo(): no methods; depth limit 3']


def test_no_decomposition_no_method_and_limit():
    failure = {'kind': 'no_method', 'item': 'top()', 'detail': ['no methods'],
               'tried': [_attempt('m0', 'precondition', ['p(a)', 'q(a)']),
                         _attempt('m1', 'not_allowed', ['act'])],
               'max_depth': 20, 'max_nodes': 10000}
    result = {'found': False, 'source': 'decompose', 'agenda': [], 'steps': [],
              'tree': [], 'failure': failure}
    assert _render_tree(result) == [
        'no decomposition: no_method',
        '  top(): no methods',
        '    skipped m0: precondition: p(a), q(a)',
        '    skipped m1: not_allowed: act',
    ]
    assert _render_htn_plan(result) == []
    failure2 = {'kind': 'limit', 'item': None, 'detail': [], 'tried': [],
                'max_depth': 20, 'max_nodes': 1}
    result2 = {**result, 'failure': failure2}
    assert _render_tree(result2) == ['no decomposition: limit', '  search limit 1 reached']
    assert _render_htn_plan(result2) == []


def test_no_method_without_detail_has_bare_item_line():
    failure = {'kind': 'no_method', 'item': 'top()', 'detail': [], 'tried': [],
               'max_depth': 20, 'max_nodes': 10}
    result = {'found': False, 'source': 'decompose', 'agenda': [], 'steps': [],
              'tree': [], 'failure': failure}
    assert _render_tree(result) == ['no decomposition: no_method', '  top()']


def test_irreversible_in_tree_and_plan():
    root = _node('task', 't()', 0, method='m', why=[],
                 children=[_node('action', 'safe()', 0, step=1),
                           _node('action', 'push()', 1, step=2)])
    result = _result([root], [_step('safe()'), _step('push()', True)])
    assert _render_tree(result) == [
        'tree:', '  t() [method: m]', '    why: -', '    1. safe()', '    2. push() [irreversible]']
    assert _render_htn_plan(result) == [
        'plan: 2 steps (source: decompose)', '  1. safe()', '  2. push() [irreversible]']


def test_plan_nothing_to_do_and_memory_source():
    assert _render_htn_plan(_result([], [])) == ['plan: nothing to do']
    assert _render_tree(_result([], [])) == ['tree:']
    assert _render_htn_plan(_result([], [_step('a()')], source='memory')) == [
        'plan: 1 steps (source: memory)', '  1. a()']


# ---------------------------------------------------------------- command level

_CALLBACKS = '''
import os

def _log(ctx, name):
    with open(os.path.join(ctx["cwd"], name + ".log"), "a", encoding="utf-8") as handle:
        handle.write("x\\n")

def sense(ctx):
    _log(ctx, "sense")
    if os.path.exists(os.path.join(ctx["cwd"], "fail_sensor")):
        raise RuntimeError("boom")
    with open(os.path.join(ctx["cwd"], "state.txt"), encoding="utf-8") as handle:
        return handle.read()

def act(binding, ctx):
    _log(ctx, "act")

CALLBACKS = dict(sense=sense, act=act)
'''

_SENSOR = {'name': 's', 'run': {'callback': 'sense'},
           'extract': [{'type': 'regex', 'pattern': r'^(.+)$', 'facts': ['{1}']}]}


def _action(name, pre=(), add=(), irreversible=False, run=None):
    return {'name': name, 'params': [], 'pre': list(pre), 'add': list(add), 'del': [],
            'run': run or {'callback': 'act'}, 'irreversible': irreversible}


def _method(name, task, subtasks, pre=()):
    return {'name': name, 'task': task, 'params': [], 'pre': list(pre), 'subtasks': subtasks}


def _setup(tmp_path, actions, methods, tasks=('top',), state='', sensors=(_SENSOR,), name='dom',
           callbacks=_CALLBACKS):
    (tmp_path / 'callbacks.py').write_text(callbacks, encoding='utf-8')
    (tmp_path / 'state.txt').write_text(state, encoding='utf-8')
    data = {'name': 'mini', 'python': 'callbacks.py', 'predicates': {'p': 0, 'q': 0, 'r': 0, 'k': 0},
            'sensors': list(sensors), 'goals': [], 'actions': actions,
            'tasks': [{'name': t, 'params': []} for t in tasks], 'methods': methods}
    path = tmp_path / f'{name}.json'
    path.write_text(json.dumps(data), encoding='utf-8')
    return str(path)


def _basic(tmp_path, **kw):
    return _setup(tmp_path, [_action('a1', add=['p()']), _action('a2', pre=['p()'], add=['q()']),
                             _action('a3', pre=['q()'], add=['r()'], irreversible=True)],
                  [_method('skipme', 'top', ['a1()'], pre=['k()']),
                   _method('chosen', 'top', ['a1()', 'a2()'])], **kw)


def _later_failed(tmp_path):
    return _setup(
        tmp_path,
        [_action('a1', add=['p()']), _action('a2', add=['q()']),
         _action('a3', pre=['p()'], add=['r()']), _action('a4', pre=['q()'], add=['r()'])],
        [_method('first', 'pick', ['a1()']), _method('second', 'pick', ['a2()']),
         _method('via_a3', 'rest', ['a3()'], pre=['p()']),
         _method('via_a4', 'rest', ['a4()'], pre=['q()']),
         _method('whole', 'top', ['pick()', 'rest()'])],
        tasks=('top', 'pick', 'rest'))


def _irreversible(tmp_path):
    return _setup(tmp_path, [_action('a1', add=['p()']),
                             _action('push', pre=['p()'], add=['q()'], irreversible=True)],
                  [_method('only', 'top', ['a1()', 'push()'])])


def _bad_domain(tmp_path):
    path = _basic(tmp_path)
    with open(path, encoding='utf-8') as handle:
        data = json.load(handle)
    data['methods'][1]['subtasks'].append('undeclared()')
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(data, handle)
    return path


def _argv(command, domain, tmp_path, *extra):
    return [command, '--domain', domain, '--cwd', str(tmp_path), '--no-memory', *extra]


def _run(argv, capsys, **kw):
    code = main(argv, **kw)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _count(tmp_path, name):
    path = tmp_path / f'{name}.log'
    return len(path.read_text().splitlines()) if path.exists() else 0


def test_task_dry_run_text(tmp_path, capsys):
    domain = _basic(tmp_path)
    code, out, _ = _run(_argv('task', domain, tmp_path, '--task', 'top()'), capsys)
    assert code == 0
    lines = out.splitlines()
    assert lines[0] == 'task: top()'
    assert 'facts:' not in out
    assert lines[-1] == 'mode: dry-run'
    assert lines.index('tree:') < lines.index('plan: 2 steps (source: decompose)')
    assert '    skipped skipme: precondition: k()' in lines
    assert '  top() [method: chosen]' in lines
    assert '    1. a1()' in lines and '  1. a1()' in lines
    assert _count(tmp_path, 'act') == 0


def test_task_dry_run_json(tmp_path, capsys):
    domain = _basic(tmp_path)
    code, out, _ = _run(_argv('task', domain, tmp_path, '--task', 'top()', '--json'), capsys)
    data = json.loads(out)
    assert code == 0
    assert set(data) == {'mode', 'plan', 'task'}
    assert data['mode'] == 'dry-run' and data['task'] == 'top()'
    assert {'found', 'source', 'agenda', 'steps', 'tree', 'failure'} <= set(data['plan'])
    assert {'idx', 'done', 'path'} <= set(data['plan']['tree'][0])
    assert out == json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + '\n'


@pytest.mark.parametrize('command', ['task', 'explain'])
def test_later_failed_shown_nested(tmp_path, capsys, command):
    domain = _later_failed(tmp_path)
    code, out, _ = _run(_argv(command, domain, tmp_path, '--task', 'top()',
                              '--allow', 'a1,a2,a4'), capsys)
    lines = out.splitlines()
    assert code == 0
    at = next(i for i, line in enumerate(lines) if line.strip() == 'skipped first: later_failed: rest()')
    assert lines[at + 1].strip() == 'rest()'
    assert any(line.strip() == 'skipped via_a3: not_allowed: a3' for line in lines[at + 2:])
    assert 'facts:' not in out and ('mode: dry-run' in lines) == (command == 'task')
    assert _count(tmp_path, 'act') == 0


def test_no_decomposition_kinds(tmp_path, capsys):
    domain = _basic(tmp_path)
    code, out, _ = _run(_argv('task', domain, tmp_path, '--task', 'top()', '--allow', 'a2'), capsys)
    lines = out.splitlines()
    assert code == 1
    assert lines[:2] == ['task: top()', 'no decomposition: no_method']
    assert any(line.strip() == 'skipped chosen: not_allowed: a1' for line in lines)
    assert not any(line.startswith('plan:') for line in lines)
    assert lines[-1] == 'mode: dry-run'

    code, out, _ = _run(_argv('task', domain, tmp_path, '--task', 'top()', '--max-nodes', '1'), capsys)
    assert code == 1
    assert out.splitlines()[1:3] == ['no decomposition: limit', '  search limit 1 reached']


@pytest.mark.parametrize('command', ['task', 'explain'])
def test_irreversible_needs_permission(tmp_path, capsys, command):
    domain = _irreversible(tmp_path)
    code, out, _ = _run(_argv(command, domain, tmp_path, '--task', 'top()'), capsys)
    assert code == 1
    assert 'no decomposition' in out
    assert any('skipped only:' in line and 'not_allowed' in line and 'push' in line
               for line in out.splitlines())
    code, out, _ = _run(_argv(command, domain, tmp_path, '--task', 'top()',
                              '--allow-irreversible', 'push'), capsys)
    assert code == 0
    assert '  2. push() [irreversible]' in out.splitlines()


def test_explain_task_ignores_memory_and_json_keys(tmp_path, capsys):
    domain_path = _basic(tmp_path)
    domain = core.load_domain(domain_path)
    allowed = planner.allowed_actions(domain, None, None)
    tree = htn.decompose_task(domain, frozenset(), ('top',), allowed)['tree']
    memory_path = str(tmp_path / 'memory.json')
    Memory(memory_path).save_task(domain, 'top()', frozenset(), tree,
                                  executor.task_fingerprint(domain, allowed, 20))
    base_argv = ['--domain', domain_path, '--cwd', str(tmp_path), '--memory-file', memory_path]
    code, out, _ = _run(['task', *base_argv, '--task', 'top()', '--json'], capsys)
    assert code == 0 and json.loads(out)['plan']['source'] == 'memory'
    code, out, _ = _run(['explain', *base_argv, '--task', 'top()', '--json'], capsys)
    data = json.loads(out)
    assert code == 0 and set(data) == {'plan', 'task'} and data['plan']['source'] == 'decompose'
    code, out, _ = _run(['explain', *base_argv, '--task', 'top()'], capsys)
    assert 'source: decompose' in out and 'facts:' not in out and 'mode:' not in out


@pytest.mark.parametrize('command', ['task', 'explain'])
@pytest.mark.parametrize('scenario, expected', [
    ('domain', 'DOMAIN_INVALID'), ('task', 'GOAL_INVALID'), ('depth', 'USAGE'),
    ('memory', 'USAGE'), ('sensor', 'SENSOR_FAILED'),
])
@pytest.mark.parametrize('as_json', [False, True])
def test_error_codes(tmp_path, capsys, command, scenario, expected, as_json):
    if command == 'explain' and scenario == 'memory':
        # explain --task never opens the memory file, so a corrupt one is not an error
        (tmp_path / 'memory.json').write_text('not json', encoding='utf-8')
        argv = ['explain', '--domain', _basic(tmp_path), '--cwd', str(tmp_path),
                '--memory-file', str(tmp_path / 'memory.json'), '--task', 'top()']
        assert _run(argv, capsys)[0] == 0
        return
    domain = _bad_domain(tmp_path) if scenario == 'domain' else _basic(tmp_path)
    memory = tmp_path / 'memory.json'
    task, extra = 'nosuch()' if scenario == 'task' else 'top()', []
    if scenario == 'depth':
        extra = ['--max-depth', '-1']
    elif scenario == 'memory':
        memory.write_text('not json', encoding='utf-8')
    elif scenario == 'sensor':
        (tmp_path / 'fail_sensor').write_text('')
    argv = [command, '--domain', domain, '--cwd', str(tmp_path), '--memory-file', str(memory),
            '--task', task, *extra, *(['--json'] if as_json else [])]
    code, out, err = _run(argv, capsys)
    assert code == 2
    if as_json:
        assert err == ''
        error = json.loads(out)['error']
        assert set(error) == {'code', 'message'} and error['code'] == expected
    else:
        assert out == ''
        assert err.startswith(f'error: {expected}: ') and err.count('\n') == 1


def _error_of(argv, capsys):
    code, out, _ = _run([*argv, '--json'], capsys)
    assert code == 2
    return json.loads(out)['error']['code']


def test_error_priority(tmp_path, capsys):
    domain = _basic(tmp_path)
    (tmp_path / 'fail_sensor').write_text('')
    memory = tmp_path / 'memory.json'
    memory.write_text('not json', encoding='utf-8')
    argv = ['task', '--domain', domain, '--cwd', str(tmp_path), '--memory-file', str(memory)]
    assert _error_of([*argv, '--task', 'nosuch()', '--max-depth', '-1'], capsys) == 'GOAL_INVALID'
    assert _error_of([*argv, '--task', 'top()', '--max-depth', '-1'], capsys) == 'USAGE'
    assert _error_of([*argv, '--task', 'top()'], capsys) == 'USAGE'
    assert _count(tmp_path, 'sense') == 0
    memory.write_text('{"entries": []}', encoding='utf-8')
    assert _error_of([*argv, '--task', 'top()'], capsys) == 'SENSOR_FAILED'
    assert _count(tmp_path, 'sense') == 1
    argv[2] = _bad_domain(tmp_path)
    assert _error_of([*argv, '--task', 'nosuch()', '--max-depth', '-1'], capsys) == 'DOMAIN_INVALID'


@pytest.mark.parametrize('option', ['--max-nodes', '--max-replans'])
def test_negative_numbers_are_usage_and_zero_is_valid(tmp_path, capsys, option):
    domain = _basic(tmp_path)
    assert _error_of(_argv('task', domain, tmp_path, '--task', 'top()', option, '-1'), capsys) == 'USAGE'
    code, _, _ = _run(_argv('task', domain, tmp_path, '--task', 'top()', option, '0'), capsys)
    assert code == (1 if option == '--max-nodes' else 0)


def test_unknown_allow_name_is_usage(tmp_path, capsys):
    domain = _basic(tmp_path)
    assert _error_of(_argv('task', domain, tmp_path, '--task', 'top()', '--allow', 'zzz'), capsys) == 'USAGE'


def _syntax_exit_code(argv):
    try:
        return main(argv)
    except SystemExit as exc:
        return exc.code


def test_argument_errors_are_exit_2_without_observing(tmp_path, capsys):
    domain = _basic(tmp_path)
    cases = [
        _argv('task', domain, tmp_path),
        _argv('task', domain, tmp_path, '--task', 'top()', '--max-depth', 'abc'),
        _argv('task', domain, tmp_path, '--task', 'top()', '--task', 'top()'),
        _argv('explain', domain, tmp_path),
        _argv('explain', domain, tmp_path, '--task', 'top()', '--goal', 'p()'),
    ]
    for argv in cases:
        assert _syntax_exit_code(argv) == 2
    capsys.readouterr()
    assert _count(tmp_path, 'sense') == 0


def test_cmd_sensor_without_runner_and_cmd_action_dry_run(tmp_path, capsys):
    cmd_sensor = {'name': 's', 'run': {'cmd': {'name': 'probe', 'args': {}}},
                  'extract': _SENSOR['extract']}
    domain = _basic(tmp_path, sensors=(cmd_sensor,))
    code, out, err = _run(_argv('task', domain, tmp_path, '--task', 'top()'), capsys)
    assert code == 2 and out == '' and err.startswith('error: SENSOR_FAILED')

    calls = []

    def runner(name, args):
        calls.append(name)
        return {'status': 'ok', 'exit_code': 0, 'output': ''}

    code, out, _ = _run(_argv('task', domain, tmp_path, '--task', 'top()'), capsys, cmd_runner=runner)
    assert code == 0 and calls == ['probe']

    cmd_action = _action('a1', add=['p()'], run={'cmd': {'name': 'do', 'args': {}}})
    domain = _setup(tmp_path, [cmd_action], [_method('only', 'top', ['a1()'])], name='cmd')
    code, out, _ = _run(_argv('task', domain, tmp_path, '--task', 'top()'), capsys)
    assert code == 0 and '  1. a1()' in out.splitlines()
    assert _count(tmp_path, 'act') == 0


def test_dry_run_is_deterministic(tmp_path, capsys):
    domain = _later_failed(tmp_path)
    for extra in ([], ['--json']):
        argv = _argv('task', domain, tmp_path, '--task', 'top()', '--allow', 'a1,a2,a4', *extra)
        first = _run(argv, capsys)
        assert first[1]
        assert first == _run(argv, capsys)


# ---------------------------------------------------------------- task --execute

_EXEC_CALLBACKS = _CALLBACKS + '''

def _edit(ctx, add=(), drop=()):
    path = os.path.join(ctx["cwd"], "state.txt")
    with open(path, encoding="utf-8") as handle:
        lines = [line for line in handle.read().splitlines() if line and line not in drop]
    lines.extend(fact for fact in add if fact not in lines)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\\n".join(lines))

def add_p(binding, ctx):
    _log(ctx, "act")
    _edit(ctx, add=["p()"])

def add_q(binding, ctx):
    _log(ctx, "act")
    _edit(ctx, add=["q()"])

def drop_k_only(binding, ctx):
    _log(ctx, "act")
    _edit(ctx, drop=["k()"])

def add_p_drop_k(binding, ctx):
    _log(ctx, "act")
    _edit(ctx, add=["p()"], drop=["k()"])

def add_p_break_sensor(binding, ctx):
    _log(ctx, "act")
    _edit(ctx, add=["p()"])
    open(os.path.join(ctx["cwd"], "fail_sensor"), "w").close()

CALLBACKS.update(add_p=add_p, add_q=add_q, drop_k_only=drop_k_only,
                 add_p_drop_k=add_p_drop_k, add_p_break_sensor=add_p_break_sensor)
'''


def _cb(name):
    return {'callback': name}


def _exec_setup(tmp_path, actions, methods, tasks=('top',), state='', **kw):
    return _setup(tmp_path, actions, methods, tasks=tasks, state=state,
                  callbacks=_EXEC_CALLBACKS, **kw)


def _success_domain(tmp_path, state=''):
    return _exec_setup(tmp_path, [_action('a1', add=['p()'], run=_cb('add_p')),
                                  _action('a2', pre=['p()'], add=['q()'], run=_cb('add_q'))],
                       [_method('only', 'top', ['a1()', 'a2()'], pre=['not r()'])], state=state)


def _mismatch_domain(tmp_path, with_second=True):
    """x1 claims to add p but only drops k; the first method needs k, so recovery switches."""
    methods = [_method('first', 'top', ['x1()', 'a2()'], pre=['k()'])]
    if with_second:
        methods.append(_method('second', 'top', ['x2()', 'a2()']))
    return _exec_setup(
        tmp_path,
        [_action('x1', add=['p()'], run=_cb('drop_k_only')), _action('x2', add=['p()'], run=_cb('add_p')),
         _action('a2', pre=['p()'], add=['q()'], run=_cb('add_q'))],
        methods, state='k()')


def _precondition_domain(tmp_path):
    return _exec_setup(
        tmp_path,
        [_action('a1', add=['p()'], run=_cb('add_p_drop_k')),
         _action('a2', pre=['p()', 'k()'], add=['q()'], run=_cb('add_q'))],
        [_method('only', 'top', ['a1()', 'a2()'])], state='k()')


def _exec_argv(domain, tmp_path, *extra):
    return _argv('task', domain, tmp_path, '--task', 'top()', '--execute', *extra)


def test_execute_success_text(tmp_path, capsys):
    domain = _success_domain(tmp_path)
    code, out, err = _run(_exec_argv(domain, tmp_path), capsys)
    lines = out.splitlines()
    assert code == 0 and err == ''
    assert lines[0] == 'facts:' and lines[1] == '  (none)' and lines[2] == 'task: top()'
    assert lines.index('tree:') < lines.index('plan: 2 steps (source: decompose)') < lines.index('executed:')
    at = lines.index('executed:')
    assert lines[at + 1:at + 3] == ['  1. a1() ok @ top()#0', '  2. a2() ok @ top()#0']
    assert lines[at + 3:] == ['replans: 0', 'status: done', 'mode: execute']
    assert _count(tmp_path, 'act') == 2


def test_execute_already_satisfied_and_no_plan(tmp_path, capsys):
    domain = _exec_setup(tmp_path, [_action('a1', add=['p()'], run=_cb('add_p'))],
                         [_method('empty', 'top', [])])
    code, out, _ = _run(_exec_argv(domain, tmp_path), capsys)
    lines = out.splitlines()
    assert code == 0
    assert lines[-5:] == ['executed:', '  (none)', 'replans: 0', 'status: already_satisfied',
                          'mode: execute']
    assert 'plan: nothing to do' in lines

    domain = _success_domain(tmp_path)
    code, out, _ = _run(_exec_argv(domain, tmp_path, '--allow', 'a2'), capsys)
    lines = out.splitlines()
    assert code == 1
    assert 'no decomposition: no_method' in lines
    assert lines[-4:] == ['  (none)', 'replans: 0', 'status: no_plan', 'mode: execute']
    assert not any(line.startswith('plan:') for line in lines)
    assert _count(tmp_path, 'act') == 0


def test_execute_mismatch_redo_line_and_json(tmp_path, capsys):
    domain = _mismatch_domain(tmp_path)
    code, out, _ = _run(_exec_argv(domain, tmp_path), capsys)
    lines = out.splitlines()
    assert code == 0
    assert lines[0] == 'facts:' and lines[1] == '  k()'
    assert '  1. x1() MISMATCH missing: p(); unexpected: - @ top()#0' in lines
    assert '  redo top()#0 after step 1 (mismatch: x1()): x2() ; a2()' in lines
    assert '  2. x2() ok @ top()#0' in lines and '  3. a2() ok @ top()#0' in lines
    assert lines[-4:] == ['replans: 1', '  redo top()#0 after step 1 (mismatch: x1()): x2() ; a2()',
                          'status: done', 'mode: execute']

    (tmp_path / 'state.txt').write_text('k()', encoding='utf-8')
    code, out, _ = _run(_exec_argv(domain, tmp_path, '--json'), capsys)
    data = json.loads(out)
    assert code == 0 and data['mode'] == 'execute' and data['status'] == 'done'
    assert data['trigger'] == {'kind': 'mismatch', 'step': 'x1()'}
    assert data['replanned'] == [{
        'after': 1, 'resume': 'top()', 'idx': 0, 'path': [], 'found': True,
        'trigger': {'kind': 'mismatch', 'step': 'x1()'}, 'steps': ['x2()', 'a2()']}]
    assert [item['text'] for item in data['executed']] == ['x1()', 'x2()', 'a2()']
    assert data['executed'][0]['path'] == [{'text': 'top()', 'idx': 0}]
    assert out == json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + '\n'


def test_execute_mismatch_without_alternative_is_stuck_no_plan(tmp_path, capsys):
    domain = _mismatch_domain(tmp_path, with_second=False)
    code, out, _ = _run(_exec_argv(domain, tmp_path), capsys)
    lines = out.splitlines()
    assert code == 1
    assert '  redo top()#0 after step 1 (mismatch: x1()): no decomposition' in lines
    at = lines.index('status: stuck')
    assert lines[at + 1:at + 4] == ['stuck at: x1() (no_plan) in top()#0',
                                    'trigger: mismatch x1()', 'no decomposition: no_method']
    assert lines[-1] == 'mode: execute'
    assert any(line.strip().startswith('skipped first: precondition') for line in lines[at:])


def test_execute_stuck_when_next_precondition_broken(tmp_path, capsys):
    domain = _precondition_domain(tmp_path)
    code, out, _ = _run(_exec_argv(domain, tmp_path, '--max-replans', '0'), capsys)
    lines = out.splitlines()
    assert code == 1
    assert '  1. a1() ok @ top()#0' in lines
    at = lines.index('stuck at: a1() (replan_limit) in top()#0')
    assert lines[at + 1] == 'trigger: precondition a2()'
    assert lines[at - 1] == 'status: stuck' and lines[-1] == 'mode: execute'
    assert _count(tmp_path, 'act') == 1

    (tmp_path / 'state.txt').write_text('k()', encoding='utf-8')
    code, out, _ = _run(_exec_argv(domain, tmp_path, '--max-replans', '0', '--json'), capsys)
    data = json.loads(out)
    assert code == 1 and data['status'] == 'stuck'
    assert data['stuck']['step'] == 'a1()' and data['trigger']['step'] == 'a2()'
    assert data['trigger']['kind'] == 'precondition' and data['stuck']['reason'] == 'replan_limit'


def _cmd_domain(tmp_path):
    action = _action('a1', add=['p()'], run={'cmd': {'name': 'do', 'args': {}}})
    return _exec_setup(tmp_path, [action], [_method('only', 'top', ['a1()'])])


@pytest.mark.parametrize('as_json', [False, True])
def test_execute_without_cmd_runner_is_usage(tmp_path, capsys, as_json):
    domain = _cmd_domain(tmp_path)
    code, out, err = _run(_exec_argv(domain, tmp_path, *(['--json'] if as_json else [])), capsys)
    assert code == 2
    if as_json:
        error = json.loads(out)['error']
        assert error['code'] == 'USAGE' and 'no cmd runner' in error['message']
    else:
        assert out == '' and err.startswith('error: USAGE') and 'no cmd runner' in err
    assert _count(tmp_path, 'act') == 0


@pytest.mark.parametrize('as_json', [False, True])
def test_execute_observation_failure_after_a_step(tmp_path, capsys, as_json):
    domain = _exec_setup(tmp_path, [_action('a1', add=['p()'], run=_cb('add_p_break_sensor'))],
                         [_method('only', 'top', ['a1()'])])
    code, out, err = _run(_exec_argv(domain, tmp_path, *(['--json'] if as_json else [])), capsys)
    assert code == 2
    if as_json:
        error = json.loads(out)['error']
        assert error['code'] == 'SENSOR_FAILED'
        message = error['message']
    else:
        assert out == '' and err.startswith('error: SENSOR_FAILED') and err.count('\n') == 1
        message = err
    for part in ('after 1 executed step(s)', 'a1()', ' @ top()#0', 're-observe'):
        assert part in message


def test_execute_cwd_goes_only_to_executor_not_to_cmd_runner(tmp_path, capsys):
    work = tmp_path / 'work'
    work.mkdir()
    (work / 'state.txt').write_text('', encoding='utf-8')
    action = {'name': 'a1', 'params': ['f'], 'pre': [], 'add': ['p()'], 'del': [],
              'run': {'cmd': {'name': 'do', 'args': {'path': '{f}'}}}, 'irreversible': False}
    domain = _exec_setup(tmp_path, [action], [], tasks=())
    with open(domain, encoding='utf-8') as handle:
        data = json.load(handle)
    data['tasks'] = [{'name': 't', 'params': ['f']}]
    data['methods'] = [{'name': 'm', 'task': 't', 'params': ['f'], 'pre': [], 'subtasks': ['a1(?f)']}]
    with open(domain, 'w', encoding='utf-8') as handle:
        json.dump(data, handle)
    calls = []

    def runner(name, args):
        calls.append((name, args))
        (work / 'state.txt').write_text('p()', encoding='utf-8')
        return {'status': 'ok', 'exit_code': 0, 'output': ''}

    code, out, _ = _run(['task', '--domain', domain, '--no-memory', '--task', 't(sub/x.py)',
                         '--execute', '--cwd', str(work)], capsys, cmd_runner=runner)
    assert code == 0 and out.splitlines()[-2:] == ['status: done', 'mode: execute']
    assert calls == [('do', {'path': 'sub/x.py'})]
    assert (work / 'sense.log').exists() and not (tmp_path / 'sense.log').exists()


def test_memory_list_shows_task_entries_and_keeps_goal_lines(tmp_path, capsys):
    domain_path = _success_domain(tmp_path, state='p()')
    memory_path = str(tmp_path / 'memory.json')
    code, _, _ = _run(['task', '--domain', domain_path, '--cwd', str(tmp_path),
                       '--memory-file', memory_path, '--task', 'top()', '--execute'], capsys)
    assert code == 0
    domain = core.load_domain(domain_path)
    Memory(memory_path).save(domain, (core.parse_literal('q()'),), frozenset(),
                             [['a1', []], ['a2', []]])
    code, out, _ = _run(['memory', 'list', '--memory-file', memory_path], capsys)
    lines = out.splitlines()
    assert code == 0 and len(lines) == 2
    assert 'mini: task top() <- p() => a1() ; a2()' in lines
    assert 'mini: q() <- - => a1() ; a2()' in lines
    assert 'fingerprint' not in out
    code, out, _ = _run(['memory', 'list', '--memory-file', memory_path, '--json'], capsys)
    entries = json.loads(out)['entries']
    assert len(entries) == 2 and any('fingerprint' in entry for entry in entries)
