import json
import sys
from pathlib import Path

import pytest

from planbot import PlanbotError, load_domain
from planbot.runtime import observe, run_action


def _print_cmd(text):
    return [sys.executable, '-c', f'import sys; sys.stdout.write({text!r})']


def _load(tmp_path, sensors, derived=None, callbacks=None, goals=None, actions=None):
    data = {
        'name': 'mini',
        'predicates': {'p': 1, 'q': 2, 'z': 0},
        'derived': derived or [],
        'sensors': sensors,
        'actions': actions or [],
        'goals': goals or ['p'],
    }
    path = tmp_path / 'domain.json'
    path.write_text(json.dumps(data), encoding='utf-8')
    return load_domain(str(path), callbacks=callbacks)


def test_regex_numbered_and_named_groups(tmp_path):
    sensor = {
        'name': 's',
        'run': {'cmds': [_print_cmd('item a 1\nnoise\nitem b 2\n')]},
        'extract': [
            {'type': 'regex', 'pattern': r'^item (\w+) (\w+)$', 'facts': ['q({1},{2})']},
            {'type': 'regex', 'pattern': r'^item (?P<n>\w+) 2$', 'facts': ['p({n})']},
        ],
    }
    result = observe(_load(tmp_path, [sensor]))
    assert result['base'] == frozenset({('q', 'a', '1'), ('q', 'b', '2'), ('p', 'b')})


def test_multiple_cmds_are_concatenated_and_braces_are_literal(tmp_path):
    cmd = [sys.executable, '-c', 'import sys; sys.stdout.write(sys.argv[1])', '{x}']
    sensor = {
        'name': 's',
        'run': {'cmds': [cmd, _print_cmd('\nz\n')]},
        'extract': [{'type': 'regex', 'pattern': r'^\{x\}$', 'facts': ['p(brace)']},
                    {'type': 'regex', 'pattern': r'^z$', 'facts': ['z']}],
    }
    result = observe(_load(tmp_path, [sensor]))
    assert result['base'] == frozenset({('p', 'brace'), ('z',)})


def test_json_path_where_and_scalar_value(tmp_path):
    payload = json.dumps({'items': [
        {'id': 'a', 'kind': 'x', 'n': 1},
        {'id': 'b', 'kind': 'y', 'n': 2},
        {'id': 'c', 'kind': 'x', 'n': 3},
    ], 'names': ['u', 'v']})
    sensor = {
        'name': 's',
        'run': {'callback': 'cb'},
        'extract': [
            {'type': 'json', 'path': ['items'], 'where': {'kind': 'x'}, 'facts': ['p({id})']},
            {'type': 'json', 'path': ['items', 1], 'facts': ['q({id},{n})']},
            {'type': 'json', 'path': ['names'], 'facts': ['p({value})']},
            {'type': 'json', 'path': ['missing'], 'facts': ['p(none)']},
            {'type': 'json', 'path': ['names'], 'where': {'k': 'v'}, 'facts': ['p(bad)']},
        ],
    }
    seen = {}

    def cb(ctx):
        seen.update(ctx)
        return payload

    domain = _load(tmp_path, [sensor], callbacks={'cb': cb})
    result = observe(domain, cwd=str(tmp_path))
    assert seen == {'cwd': str(tmp_path)}
    assert result['base'] == frozenset({
        ('p', 'a'), ('p', 'c'), ('q', 'b', '2'), ('p', 'u'), ('p', 'v')})


def test_facts_include_derived_but_base_does_not(tmp_path):
    sensor = {'name': 's', 'run': {'cmds': [_print_cmd('a\n')]},
              'extract': [{'type': 'regex', 'pattern': r'^(\w)$', 'facts': ['p({1})']}]}
    derived = [{'head': 'r(?x)', 'body': ['p(?x)']}]
    result = observe(_load(tmp_path, [sensor], derived=derived, goals=['r']))
    assert ('r', 'a') in result['facts']
    assert ('r', 'a') not in result['base']
    assert ('p', 'a') in result['base']


def test_command_nonzero_exit_fails(tmp_path):
    cmd = [sys.executable, '-c', 'import sys; sys.exit(3)']
    domain = _load(tmp_path, [{'name': 'bad', 'run': {'cmds': [cmd]}, 'extract': []}])
    with pytest.raises(PlanbotError) as exc:
        observe(domain)
    assert exc.value.code == 'SENSOR_FAILED'
    assert 'bad' in exc.value.message


def test_command_cannot_start_fails(tmp_path):
    cmd = [str(tmp_path / 'no_such_program')]
    domain = _load(tmp_path, [{'name': 'bad', 'run': {'cmds': [cmd]}, 'extract': []}])
    with pytest.raises(PlanbotError) as exc:
        observe(domain)
    assert exc.value.code == 'SENSOR_FAILED'


def test_callback_exception_and_non_str_fail(tmp_path):
    def boom(ctx):
        raise RuntimeError('boom')

    for cb in (boom, lambda ctx: 5):
        sensor = {'name': 'cbs', 'run': {'callback': 'cb'}, 'extract': []}
        domain = _load(tmp_path, [sensor], callbacks={'cb': cb})
        with pytest.raises(PlanbotError) as exc:
            observe(domain)
        assert exc.value.code == 'SENSOR_FAILED'
        assert 'cbs' in exc.value.message


@pytest.mark.parametrize('rule, output', [
    ({'type': 'json', 'path': [], 'facts': ['p(a)']}, 'not json'),
    ({'type': 'regex', 'pattern': 'x', 'facts': ['unknown(a)']}, 'x'),
    ({'type': 'regex', 'pattern': 'x', 'facts': ['q(a)']}, 'x'),
    ({'type': 'regex', 'pattern': 'x', 'facts': ['p({9})']}, 'x'),
])
def test_bad_extraction_fails(tmp_path, rule, output):
    sensor = {'name': 's', 'run': {'callback': 'cb'}, 'extract': [rule]}
    domain = _load(tmp_path, [sensor], callbacks={'cb': lambda ctx: output})
    with pytest.raises(PlanbotError) as exc:
        observe(domain)
    assert exc.value.code == 'SENSOR_FAILED'


def test_sensor_with_empty_extract_runs_for_side_effect(tmp_path):
    marker = tmp_path / 'marker'
    cmd = [sys.executable, '-c', f'open({str(marker)!r}, "w").close()']
    domain = _load(tmp_path, [{'name': 's', 'run': {'cmds': [cmd]}, 'extract': []}])
    assert observe(domain)['base'] == frozenset()
    assert marker.exists()


def _load_action(tmp_path, run, callbacks=None):
    action = {'name': 'a', 'params': ['x'], 'pre': [], 'add': [], 'del': [], 'run': run}
    return _load(tmp_path, [], callbacks=callbacks, actions=[action])


@pytest.mark.parametrize('arg', ['a b', '{x} a b'])
def test_action_substitutes_each_command_argument_once(tmp_path, arg):
    cmd = [sys.executable, '-c', 'import sys; print(sys.argv[1:])', '{x}']
    domain = _load_action(tmp_path, {'cmds': [cmd]})
    assert run_action(domain, 'a', (arg,)) == {'ok': True, 'output': f'{[arg]}\n'}


@pytest.mark.parametrize('failure', ['nonzero', 'missing', 'empty'])
def test_action_command_failure_stops_remaining_commands(tmp_path, failure):
    marker = tmp_path / 'marker'
    after = [sys.executable, '-c', f'open({str(marker)!r}, "w").close()']
    commands = {
        'nonzero': [sys.executable, '-c',
                    'import sys; print("out"); print("err", file=sys.stderr); sys.exit(3)'],
        'missing': [str(tmp_path / 'no_such_program')],
        'empty': [],
    }
    domain = _load_action(tmp_path, {'cmds': [_print_cmd('first\n'), commands[failure], after]})

    output = 'first\nout\nerr\n' if failure == 'nonzero' else 'first\n'
    assert run_action(domain, 'a', ('arg',), cwd=str(tmp_path)) == {
        'ok': False, 'output': output}
    assert not marker.exists()


@pytest.mark.parametrize('value, output', [(None, ''), (5, '5')])
def test_action_callback_receives_binding_and_cwd(tmp_path, value, output):
    seen = []

    def cb(binding, ctx):
        seen.append((binding, ctx))
        return value

    domain = _load_action(tmp_path, {'callback': 'cb'}, callbacks={'cb': cb})
    assert run_action(domain, 'a', ('arg',), cwd=str(tmp_path)) == {'ok': True, 'output': output}
    assert seen == [({'x': 'arg'}, {'cwd': str(tmp_path)})]


def test_action_callback_exception_is_returned(tmp_path):
    def cb(binding, ctx):
        raise RuntimeError('boom')

    domain = _load_action(tmp_path, {'callback': 'cb'}, callbacks={'cb': cb})
    assert run_action(domain, 'a', ('arg',)) == {'ok': False, 'output': 'boom'}


@pytest.mark.parametrize('name, args', [('unknown', ('arg',)), ('a', ())])
def test_action_usage_errors(tmp_path, name, args):
    domain = _load_action(tmp_path, {'cmds': [_print_cmd('')]})
    with pytest.raises(PlanbotError) as exc:
        run_action(domain, name, args)
    assert exc.value.code == 'USAGE'


def test_runtime_does_not_enable_shell():
    source = Path(__file__).resolve().parents[1] / 'planbot' / 'runtime.py'
    assert 'shell=True' not in source.read_text(encoding='utf-8')
