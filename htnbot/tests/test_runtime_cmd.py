import ast
import json
import sys
from pathlib import Path

import pytest

from planbot import PlanbotError, load_domain
from planbot.runtime import observe, run_action


def _domain(tmp_path, runner, args=None):
    data = {
        'name': 'mini',
        'predicates': {'p': 1},
        'sensors': [],
        'actions': [
            {
                'name': 'act', 'params': ['s'], 'pre': [], 'add': ['p(?s)'], 'del': [],
                'run': {'cmd': {'name': 'do_it', 'args': args if args is not None else {'path': '{s}'}}},
            },
            {
                'name': 'cb', 'params': [], 'pre': [], 'add': [], 'del': [],
                'run': {'callback': 'cb'},
            },
        ],
        'goals': ['p'],
    }
    path = tmp_path / 'domain.json'
    path.write_text(json.dumps(data), encoding='utf-8')
    return load_domain(str(path), callbacks={'cb': lambda b, c: 'x'}, cmd_runner=runner)


def _recorder(result=None, raises=None):
    calls = []

    def fake(*a, **kw):
        calls.append((a, kw))
        if raises is not None:
            raise raises
        return result if result is not None else {'status': 'ok', 'exit_code': 0, 'output': 'fine'}

    return fake, calls


def test_substitution_recurses_and_keeps_non_strings(tmp_path):
    args = {
        'a': 'pre-{s}-post',
        'list': ['{s}', ['{s}x', 3], {'k': '{s}', '{s}': 'v'}],
        'n': 5, 'b': True, 'f': False, 'z': None,
        'obj': {'inner': ['{s}', 1.5]},
    }
    fake, calls = _recorder()
    domain = _domain(tmp_path, fake, args)
    run_action(domain, 'act', ('V',))
    assert len(calls) == 1
    a, kw = calls[0]
    assert kw == {}
    assert a == ('do_it', {
        'a': 'pre-V-post',
        'list': ['V', ['Vx', 3], {'k': 'V', '{s}': 'v'}],
        'n': 5, 'b': True, 'f': False, 'z': None,
        'obj': {'inner': ['V', 1.5]},
    })
    assert domain.actions['act'].run['cmd']['args']['a'] == 'pre-{s}-post'


def test_exit_code_decides_ok(tmp_path):
    fake, _ = _recorder({'status': 'ok', 'exit_code': 0, 'output': 'hello'})
    assert run_action(_domain(tmp_path, fake), 'act', ('V',)) == {'ok': True, 'output': 'hello'}
    fake, _ = _recorder({'status': 'ok', 'exit_code': 2, 'output': 'bad'})
    assert run_action(_domain(tmp_path, fake), 'act', ('V',)) == {'ok': False, 'output': 'bad'}
    fake, _ = _recorder({'status': 'error', 'exit_code': 0})
    assert run_action(_domain(tmp_path, fake), 'act', ('V',)) == {'ok': True, 'output': ''}
    fake, _ = _recorder({'status': 'ok', 'exit_code': '0', 'output': 'o'})
    assert run_action(_domain(tmp_path, fake), 'act', ('V',))['ok'] is False
    fake, _ = _recorder({'status': 'ok', 'output': 'o'})
    assert run_action(_domain(tmp_path, fake), 'act', ('V',))['ok'] is False


def test_error_paths_do_not_raise(tmp_path):
    fake, _ = _recorder(raises=RuntimeError('boom'))
    result = run_action(_domain(tmp_path, fake), 'act', ('V',))
    assert result['ok'] is False and 'boom' in result['output']

    fake, _ = _recorder(result=['not', 'dict'])
    assert run_action(_domain(tmp_path, fake), 'act', ('V',)) == {'ok': False, 'output': 'invalid cmd result'}

    assert run_action(_domain(tmp_path, None), 'act', ('V',)) == {'ok': False, 'output': 'no cmd runner'}


def test_cwd_is_ignored_for_cmd(tmp_path):
    fake, calls = _recorder()
    domain = _domain(tmp_path, fake)
    run_action(domain, 'act', ('sub/x.py',))
    run_action(domain, 'act', ('sub/x.py',), cwd='/some/dir')
    (a1, kw1), (a2, kw2) = calls
    assert a1 == a2 == ('do_it', {'path': 'sub/x.py'})
    assert 'cwd' not in a2[1]
    assert len(a2) == 2 and kw1 == kw2 == {}


def test_callback_branch_still_gets_cwd(tmp_path):
    seen = []
    domain = _domain(tmp_path, None)
    domain.callbacks['cb'] = lambda b, c: seen.append((b, c)) or 'x'
    assert run_action(domain, 'cb', (), cwd='/d') == {'ok': True, 'output': 'x'}
    assert seen == [({}, {'cwd': '/d'})]


def _sensor_domain(tmp_path, runner):
    data = {
        'name': 'mini_sensors',
        'predicates': {'p': 1, 'r': 1, 'c': 1},
        'derived': [{'head': 'q(?x)', 'body': ['p(?x)']}],
        'sensors': [
            {'name': 'rx', 'run': {'cmd': {'name': 'rx_cmd', 'args': {'k': '{x}', 'n': [1, {'z': '{x}'}]}}},
             'extract': [{'type': 'regex', 'pattern': r'^item (\w+)$', 'facts': ['p({1})']}]},
            {'name': 'js', 'run': {'cmd': {'name': 'js_cmd', 'args': {}}},
             'extract': [{'type': 'json', 'path': ['rows'], 'where': {'ok': 'true'}, 'facts': ['r({name})']}]},
            {'name': 'cbs', 'run': {'callback': 'cbs'},
             'extract': [{'type': 'regex', 'pattern': r'^c (\w+)$', 'facts': ['c({1})']}]},
        ],
        'actions': [],
        'goals': ['p'],
    }
    path = tmp_path / 'sensors.json'
    path.write_text(json.dumps(data), encoding='utf-8')
    seen = []
    callbacks = {'cbs': lambda ctx: seen.append(ctx) or 'c k'}
    return load_domain(str(path), callbacks=callbacks, cmd_runner=runner), seen


_OUTPUTS = {
    'rx_cmd': 'item a\nnoise\nitem b\n',
    'js_cmd': json.dumps({'rows': [{'name': 'u', 'ok': True}, {'name': 'v', 'ok': False}]}),
}


def _by_name(calls=None):
    def fake(*a, **kw):
        if calls is not None:
            calls.append((a, kw))
        return {'status': 'ok', 'exit_code': 0, 'output': _OUTPUTS[a[0]]}
    return fake


def test_sensor_output_is_extracted_and_derived(tmp_path):
    domain, _ = _sensor_domain(tmp_path, _by_name())
    result = observe(domain)
    assert result['base'] == frozenset({('p', 'a'), ('p', 'b'), ('r', 'u'), ('c', 'k')})
    assert result['facts'] == result['base'] | {('q', 'a'), ('q', 'b')}
    assert ('q', 'a') not in result['base']


def test_sensor_args_are_not_substituted(tmp_path):
    calls = []
    domain, _ = _sensor_domain(tmp_path, _by_name(calls))
    observe(domain)
    assert calls[0] == (('rx_cmd', {'k': '{x}', 'n': [1, {'z': '{x}'}]}), {})
    assert calls[1] == (('js_cmd', {}), {})
    assert domain.sensors[0].run['cmd']['args']['k'] == '{x}'


def _raiser(*a):
    raise RuntimeError('boom')


@pytest.mark.parametrize('runner', [
    None,
    _raiser,
    lambda *a: {'status': 'ok', 'exit_code': 1, 'output': ''},
    lambda *a: {'status': 'ok', 'exit_code': '0', 'output': ''},
    lambda *a: {'status': 'ok', 'exit_code': 0, 'output': 5},
    lambda *a: {'status': 'ok', 'exit_code': 0},
    lambda *a: {'status': 'ok', 'output': ''},
    lambda *a: ['not', 'dict'],
])
def test_sensor_failures_raise_sensor_failed(tmp_path, runner):
    domain, _ = _sensor_domain(tmp_path, runner)
    with pytest.raises(PlanbotError) as info:
        observe(domain)
    assert info.value.code == 'SENSOR_FAILED'
    assert 'rx' in info.value.message


def test_sensor_cwd_not_passed_to_cmd_but_to_callback(tmp_path):
    calls = []
    domain, seen = _sensor_domain(tmp_path, _by_name(calls))
    observe(domain)
    observe(domain, cwd='/some/dir')
    assert calls[:2] == calls[2:]
    for a, kw in calls:
        assert len(a) == 2 and kw == {} and 'cwd' not in a[1]
    assert seen == [{'cwd': '.'}, {'cwd': '/some/dir'}]


def test_runtime_imports_only_stdlib_and_planbot():
    source = (Path(__file__).resolve().parent.parent / 'planbot' / 'runtime.py').read_text(encoding='utf-8')
    tops = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            tops.update(a.name.split('.')[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            tops.add((node.module or '').split('.')[0])
    assert tops
    assert tops <= set(sys.stdlib_module_names) | {'planbot'}
