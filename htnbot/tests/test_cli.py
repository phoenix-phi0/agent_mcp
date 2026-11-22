import json
import subprocess
import sys

import pytest

from planbot import cli
from planbot.cli import main


def _write_domain(tmp_path, callback_source=None, **fields):
    if callback_source is None:
        callback_source = (
            'from pathlib import Path\n\n'
            'def sense(ctx):\n'
            '    return (Path(ctx["cwd"]) / "facts.txt").read_text(encoding="utf-8")\n\n'
            'CALLBACKS = {"sense": sense}\n'
        )
    (tmp_path / 'callbacks.py').write_text(callback_source, encoding='utf-8')
    (tmp_path / 'facts.txt').write_text('p(z)\np(a)\n', encoding='utf-8')
    domain = {
        'name': 'mini', 'python': 'callbacks.py', 'predicates': {'p': 1},
        'derived': [{'head': 'q(?x)', 'body': ['p(?x)']}],
        'sensors': [{'name': 'sense', 'run': {'callback': 'sense'}, 'extract': [
            {'type': 'regex', 'pattern': r'^(.+)$', 'facts': ['{1}']},
        ]}],
        'actions': [], 'goals': ['p', 'q'],
    }
    domain.update(fields)
    path = tmp_path / 'domain.json'
    path.write_text(json.dumps(domain), encoding='utf-8')
    return ['--domain', str(path), '--cwd', str(tmp_path)]


def test_observe_text_and_json(tmp_path, capsys):
    argv = ['observe', *_write_domain(tmp_path)]
    assert main(argv) == 0
    assert capsys.readouterr().out.splitlines() == ['facts:', '  p(a)', '  p(z)', '  q(a)', '  q(z)']
    assert main([*argv, '--json']) == 0
    expected = {'facts': ['p(a)', 'p(z)', 'q(a)', 'q(z)'], 'base': ['p(a)', 'p(z)']}
    captured = capsys.readouterr()
    assert json.loads(captured.out) == expected
    assert captured.out == json.dumps(expected, ensure_ascii=False, indent=2, sort_keys=True) + '\n'


def test_observe_without_facts(tmp_path, capsys):
    argv = ['observe', *_write_domain(tmp_path, sensors=[])]
    assert main(argv) == 0
    assert capsys.readouterr().out == 'facts:\n  (none)\n'


@pytest.mark.parametrize('exists', [False, True])
def test_memory_empty_text_and_json(tmp_path, capsys, exists):
    path = tmp_path / 'memory.json'
    if exists:
        path.write_text('{"entries": []}', encoding='utf-8')
    for command, line, expected in (
        ('list', '(empty)', {'entries': []}), ('clear', 'cleared 0', {'cleared': 0}),
    ):
        argv = ['memory', command, '--memory-file', str(path)]
        assert main(argv) == 0
        assert capsys.readouterr().out == line + '\n'
        assert main([*argv, '--json']) == 0
        assert json.loads(capsys.readouterr().out) == expected
    assert path.exists() is exists


def test_memory_list_and_clear_entries(tmp_path, capsys):
    entry = {
        'domain': '领域', 'goal': ['p(a)', 'p(b)'], 'predicates': ['p'],
        'start': ['p(z)'], 'steps': [['one', []], ['two', ['a', 'b']]],
    }
    entries = {'entries': [entry, {**entry, 'start': []}]}
    path = tmp_path / 'memory.json'
    path.write_text(json.dumps(entries), encoding='utf-8')
    options = ['--memory-file', str(path)]
    assert main(['memory', 'list', *options]) == 0
    assert capsys.readouterr().out.splitlines() == [
        '领域: p(a), p(b) <- p(z) => one() ; two(a,b)',
        '领域: p(a), p(b) <- - => one() ; two(a,b)',
    ]
    assert main(['memory', 'list', *options, '--json']) == 0
    assert capsys.readouterr().out == json.dumps(entries, ensure_ascii=False, indent=2, sort_keys=True) + '\n'
    assert main(['memory', 'clear', *options]) == 0
    assert capsys.readouterr().out == 'cleared 2\n'
    assert json.loads(path.read_text(encoding='utf-8')) == {'entries': []}


def test_missing_domain_text_and_json(tmp_path, capsys):
    argv = ['observe', '--domain', str(tmp_path / 'missing.json')]
    assert main(argv) == 2
    captured = capsys.readouterr()
    assert captured.out == ''
    prefix = 'error: DOMAIN_INVALID: '
    assert captured.err.startswith(prefix)
    message, = captured.err.removeprefix(prefix).splitlines()
    assert main([*argv, '--json']) == 2
    captured = capsys.readouterr()
    assert captured.err == ''
    assert json.loads(captured.out) == {'error': {'code': 'DOMAIN_INVALID', 'message': message}}


def test_observe_reports_sensor_failure(tmp_path, capsys):
    source = 'def sense(ctx):\n    raise ValueError("sensor failed")\nCALLBACKS = {"sense": sense}\n'
    assert main(['observe', *_write_domain(tmp_path, source)]) == 2
    assert capsys.readouterr().err.startswith('error: SENSOR_FAILED: ')


def test_memory_reports_corrupt_file(tmp_path, capsys):
    path = tmp_path / 'memory.json'
    path.write_text('invalid JSON', encoding='utf-8')
    assert main(['memory', 'list', '--memory-file', str(path)]) == 2
    assert capsys.readouterr().err.startswith('error: USAGE: ')


@pytest.mark.parametrize('argv', [
    [], ['observe'], ['memory'], ['run', '--domain', 'domain.json'],
    ['explain', '--domain', 'domain.json'],
    ['run', '--domain', 'domain.json', '--goal', 'p(a)', '--max-nodes', 'bad'],
])
def test_argparse_errors_return_two(argv, capsys):
    assert main(argv) == 2
    assert 'usage:' in capsys.readouterr().err


def test_planning_options(monkeypatch):
    monkeypatch.delenv('PLANBOT_MEMORY', raising=False)
    parser = cli._build_parser()
    required = ['--domain', 'domain.json', '--goal', 'p(a)', '--goal', 'q(a)']
    run = parser.parse_args(['run', *required])
    assert run.goal == ['p(a)', 'q(a)']
    assert run.cwd == '.'
    assert run.allow is run.allow_irreversible is None
    assert (run.max_nodes, run.max_replans) == (10000, 3)
    assert not run.execute and not run.no_memory and not run.json
    run = parser.parse_args(['run', *required, '--execute', '--max-replans', '0'])
    assert run.execute and run.max_replans == 0
    explain = parser.parse_args(['explain', *required, '--allow', 'a,b', '--allow-irreversible', 'c,d',
                                 '--max-nodes', '12', '--no-memory', '--json'])
    assert explain.allow == ['a', 'b']
    assert explain.allow_irreversible == ['c', 'd']
    assert (explain.max_nodes, explain.no_memory, explain.json) == (12, True, True)
    assert not hasattr(explain, 'execute') and not hasattr(explain, 'max_replans')


def test_memory_path_defaults_and_no_memory(tmp_path, monkeypatch):
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.delenv('PLANBOT_MEMORY', raising=False)
    required = ['run', '--domain', 'domain.json', '--goal', 'p(a)']
    assert cli._build_parser().parse_args(required).memory_file == str(tmp_path / '.planbot/memory.json')
    override = str(tmp_path / 'override.json')
    monkeypatch.setenv('PLANBOT_MEMORY', override)
    args = cli._build_parser().parse_args([*required, '--no-memory'])
    assert args.memory_file == override

    def unexpected_memory(path):
        pytest.fail(f'Memory was constructed for {path}')

    monkeypatch.setattr(cli, 'Memory', unexpected_memory)
    assert cli._memory_from_args(args) is None


def test_main_uses_sys_argv_and_returns_help_exit_code(monkeypatch, capsys):
    monkeypatch.setattr(sys, 'argv', ['planbot', 'observe', '--help'])
    assert main() == 0
    assert 'usage:' in capsys.readouterr().out


def test_module_entry_point(tmp_path):
    result = subprocess.run([sys.executable, '-m', 'planbot', 'observe', *_write_domain(tmp_path)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith('facts:\n')


_PLAN_CALLBACKS = (
    'from pathlib import Path\n\n'
    'def sense(ctx):\n'
    '    return (Path(ctx["cwd"]) / "facts.txt").read_text(encoding="utf-8")\n\n'
    'def act(binding, ctx):\n'
    '    with (Path(ctx["cwd"]) / "calls.txt").open("a") as handle:\n'
    '        handle.write("called\\n")\n\n'
    'CALLBACKS = {"sense": sense, "act": act}\n'
)


def _plan_domain(tmp_path, **fields):
    action = {'params': ['x'], 'run': {'callback': 'act'}}
    actions = [
        {'name': 'first', 'pre': ['p(?x)'], 'add': ['r(?x)'], 'del': [], **action},
        {'name': 'second', 'pre': ['r(?x)'], 'add': ['s(?x)'], 'del': [], 'irreversible': True, **action},
    ]
    options = {'predicates': {'p': 1, 'r': 1, 's': 1}, 'derived': [], 'actions': actions,
               'goals': ['p', 'r', 's']}
    options.update(fields)
    return _write_domain(tmp_path, _PLAN_CALLBACKS, **options)


def test_run_dry_run_text_plan_and_reasons(tmp_path, capsys):
    domain = _plan_domain(tmp_path)
    argv = ['run', *domain, '--goal', 's(a)', '--allow-irreversible', 'second', '--no-memory']
    assert main(argv) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[:3] == ['facts:', '  p(a)', '  p(z)']
    assert lines[3] == 'goal: s(a)'
    assert lines[4] == 'plan: 2 steps (source: search)'
    assert lines[5].startswith('  1. ')
    assert lines[5] == '  1. first(a) -- r(a) -> step 2 second(a)'
    assert lines[6] == '  2. second(a) [irreversible] -- s(a) -> goal'
    assert lines[-1] == 'mode: dry-run'
    for line in lines[5:7]:
        assert ' -- ' in line
        for reason in line.split(' -- ', 1)[1].split('; '):
            if ' -> step ' in reason:
                number, text = reason.split(' -> step ', 1)[1].split(' ', 1)
                assert lines[4 + int(number)].startswith(f'  {number}. {text}')
    assert not (tmp_path / 'calls.txt').exists()
    assert (tmp_path / 'facts.txt').read_text(encoding='utf-8') == 'p(z)\np(a)\n'


def test_run_dry_run_already_satisfied(tmp_path, capsys):
    argv = ['run', *_plan_domain(tmp_path), '--goal', 'p(a)', '--no-memory']
    assert main(argv) == 0
    assert capsys.readouterr().out.splitlines()[-2:] == ['plan: goal already satisfied', 'mode: dry-run']


def test_run_no_plan_text_and_exit_code(tmp_path, capsys):
    domain = _plan_domain(tmp_path)
    assert main(['run', *domain, '--goal', 's(a)', '--no-memory']) == 1
    lines = capsys.readouterr().out.splitlines()
    index = lines.index('no plan: no_producer')
    assert lines[index + 1] == '  s(a): no usable action produces it (excluded: second)'
    assert lines[-1] == 'mode: dry-run'
    assert main(['explain', *domain, '--goal', 's(a)']) == 1
    assert capsys.readouterr().out.splitlines()[1] == 'no plan: no_producer'


def test_failure_lines_each_kind():
    assert cli._failure_lines({'kind': 'limit', 'details': [], 'max_nodes': 7}) == ['  search limit 7 reached']
    unreachable = {'kind': 'unreachable', 'details': [{'goal': 'g()'}], 'max_nodes': 5}
    assert cli._failure_lines(unreachable) == ['  g(): unreachable']
    blocked = {'kind': 'blocked', 'max_nodes': 5, 'details': [
        {'goal': 'g()', 'action': 'act(a)', 'missing': ['m()', 'not n()']}]}
    plan = {'found': False, 'source': 'search', 'steps': [], 'failure': blocked}
    assert cli._plan_lines(plan) == ['no plan: blocked', '  g(): act(a) blocked by m(), not n()']


def test_plan_lines_indirect_reason():
    step = {'text': 't()', 'irreversible': False,
            'reasons': [{'literal': '', 'for_step': None, 'for_text': 'indirect'}]}
    plan = {'found': True, 'source': 'memory', 'steps': [step], 'failure': None}
    assert cli._plan_lines(plan) == ['plan: 1 steps (source: memory)', '  1. t() -- indirect -> goal']


def test_run_dry_run_twice_identical_with_no_memory(tmp_path, capsys):
    domain = _plan_domain(tmp_path)
    for extra in ([], ['--json']):
        argv = ['run', *domain, '--goal', 's(a)', '--allow-irreversible', 'second', '--no-memory', *extra]
        assert main(argv) == 0
        first = capsys.readouterr().out
        assert main(argv) == 0
        assert capsys.readouterr().out == first


def test_run_and_explain_json(tmp_path, capsys):
    domain = _plan_domain(tmp_path)
    options = ['--goal', 's(a)', '--allow-irreversible', 'second', '--no-memory', '--json']
    assert main(['run', *domain, *options]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data['mode'] == 'dry-run'
    assert set(data) == {'goal', 'facts', 'satisfied', 'plan', 'mode'}
    assert data['plan']['found'] is True and data['satisfied'] is False
    assert main(['explain', *domain, *options]) == 0
    explained = json.loads(capsys.readouterr().out)
    assert set(explained) == {'goal', 'plan'}
    assert explained['plan'] == data['plan']


def test_explain_text_has_no_facts_and_runs_nothing(tmp_path, capsys):
    domain = _plan_domain(tmp_path)
    assert main(['explain', *domain, '--goal', 's(a)', '--allow-irreversible', 'second']) == 0
    lines = capsys.readouterr().out.splitlines()
    assert 'facts:' not in lines
    assert lines[:2] == ['goal: s(a)', 'plan: 2 steps (source: search)']
    assert not any(line.startswith('mode:') for line in lines)
    assert not (tmp_path / 'calls.txt').exists()


def test_run_and_explain_invalid_goal_predicate(tmp_path, capsys):
    domain = _plan_domain(tmp_path, goals=['p'])
    for command in ('run', 'explain'):
        assert main([command, *domain, '--goal', 's(a)']) == 2
        assert capsys.readouterr().err.startswith('error: GOAL_INVALID')


def test_run_unknown_allowed_action(tmp_path, capsys):
    assert main(['run', *_plan_domain(tmp_path), '--goal', 's(a)', '--allow', 'nope']) == 2
    assert capsys.readouterr().err.startswith('error: USAGE')


def test_dry_run_memory_options(tmp_path, capsys):
    domain = _plan_domain(tmp_path)
    memory = tmp_path / 'mem.json'
    base = ['run', *domain, '--goal', 's(a)', '--allow-irreversible', 'second']
    assert main([*base, '--no-memory', '--memory-file', str(memory)]) == 0
    assert 'source: search' in capsys.readouterr().out
    assert not memory.exists()
    entry = {'domain': 'mini', 'goal': ['s(a)'], 'predicates': ['p', 'r', 's'],
             'start': ['p(a)', 'p(z)'], 'steps': [['first', ['a']], ['second', ['a']]]}
    memory.write_text(json.dumps({'entries': [entry]}), encoding='utf-8')
    assert main([*base, '--memory-file', str(memory)]) == 0
    assert 'source: memory' in capsys.readouterr().out
    assert main([*base, '--no-memory', '--memory-file', str(memory)]) == 0
    assert 'source: search' in capsys.readouterr().out


_EXEC_CALLBACKS = (
    'from pathlib import Path\n\n'
    'STATE = {"ready(a)", "ready(b)"}\n\n'
    'def sense(ctx):\n'
    '    marker = Path(ctx["cwd"]) / "reset.txt"\n'
    '    if marker.exists():\n'
    '        marker.unlink()\n'
    '        STATE.clear()\n'
    '        STATE.update(["ready(a)", "ready(b)"])\n'
    '    return "\\n".join(sorted(STATE))\n\n'
    'def act(binding, ctx):\n'
    '    fault = (Path(ctx["cwd"]) / "fault.txt").read_text(encoding="utf-8").strip()\n'
    '    if fault in ("", "raise_after"):\n'
    '        STATE.add("running(" + binding["x"] + ")")\n'
    '    if fault in ("raise_after", "noop_raise"):\n'
    '        raise RuntimeError("boom")\n\n'
    'CALLBACKS = {"sense": sense, "act": act}\n'
)


def _exec_argv(tmp_path, fault='', *extra, goal='running(b)'):
    fields = {'predicates': {'ready': 1, 'running': 1}, 'derived': [], 'goals': ['running'], 'actions': [
        {'name': 'start', 'params': ['x'], 'pre': ['ready(?x)'], 'add': ['running(?x)'], 'del': [],
         'run': {'callback': 'act'}}]}
    domain = _write_domain(tmp_path, _EXEC_CALLBACKS, **fields)
    (tmp_path / 'fault.txt').write_text(fault, encoding='utf-8')
    (tmp_path / 'reset.txt').write_text('', encoding='utf-8')  # initial state again on the first observe
    return ['run', *domain, '--goal', goal, '--execute', *extra]


def test_execute_ok_text(tmp_path, capsys):
    assert main(_exec_argv(tmp_path, '', '--no-memory')) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[:4] == ['facts:', '  ready(a)', '  ready(b)', 'goal: running(b)']
    assert lines[4:] == ['plan: 1 steps (source: search)', '  1. start(b) -- running(b) -> goal',
                         'executed:', '  1. start(b) ok', 'replans: 0', 'status: done', 'mode: execute']


@pytest.mark.parametrize('fault, suffix', [
    ('raise_after', ' failed'),
    ('noop', ' MISMATCH missing: running(b); unexpected: -'),
    ('noop_raise', ' MISMATCH missing: running(b); unexpected: - (failed)'),
])
def test_execute_row_forms(tmp_path, capsys, fault, suffix):
    argv = _exec_argv(tmp_path, fault, '--no-memory', '--max-replans', '0')
    code = main(argv)
    lines = capsys.readouterr().out.splitlines()
    assert lines[lines.index('executed:') + 1] == '  1. start(b)' + suffix
    if fault == 'raise_after':
        assert code == 0 and 'status: done' in lines
        assert main([*_exec_argv(tmp_path, fault, '--no-memory'), '--json']) == 0
        item = json.loads(capsys.readouterr().out)['executed'][0]
        assert (item['ok'], item['matched']) == (False, True)
    else:
        assert code == 1


def test_execute_json(tmp_path, capsys):
    assert main(_exec_argv(tmp_path, '', '--no-memory', '--json')) == 0
    data = json.loads(capsys.readouterr().out)
    assert {'status', 'executed', 'mode'} <= set(data)
    assert (data['status'], data['mode']) == ('done', 'execute')


def test_execute_stuck_numbers_continue_across_replans(tmp_path, capsys):
    assert main(_exec_argv(tmp_path, 'noop', '--no-memory')) == 1
    lines = capsys.readouterr().out.splitlines()
    first = lines.index('executed:') + 1
    assert [line[:5] for line in lines[first:first + 4]] == ['  1. ', '  2. ', '  3. ', '  4. ']
    assert lines[-4:] == ['replans: 3', 'status: stuck', 'stuck at: start(b) (replan_limit)', 'mode: execute']


def test_execute_no_plan_and_stuck_no_plan_lines(tmp_path, capsys):
    assert main(_exec_argv(tmp_path, '', '--no-memory', goal='running(c)')) == 1
    lines = capsys.readouterr().out.splitlines()
    assert lines[lines.index('executed:') + 1:] == ['  (none)', 'replans: 0', 'status: no_plan', 'mode: execute']
    report = {'initial_facts': [], 'goal': ['g()'], 'plan': {'found': True, 'steps': [], 'failure': None},
              'executed': [], 'replans': 1, 'status': 'stuck', 'mode': 'execute',
              'stuck': {'step': 's()', 'reason': 'no_plan', 'missing': [], 'unexpected': [],
                        'failure': {'kind': 'unreachable', 'details': [{'goal': 'g()'}], 'max_nodes': 1}}}
    assert cli._report_lines(report)[-4:] == [
        'status: stuck', 'stuck at: s() (no_plan)', '  g(): unreachable', 'mode: execute']


def test_execute_memory_file(tmp_path, capsys):
    memory = tmp_path / 'mem.json'
    assert main(_exec_argv(tmp_path, '', '--no-memory', '--memory-file', str(memory))) == 0
    assert not memory.exists()
    assert main(_exec_argv(tmp_path, '', '--memory-file', str(memory))) == 0
    assert memory.exists()
    capsys.readouterr()
    assert main(['memory', 'list', '--memory-file', str(memory)]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1 and lines[0].startswith('mini: running(b) <- ')
    assert main(['memory', 'clear', '--memory-file', str(memory)]) == 0
    assert capsys.readouterr().out == 'cleared 1\n'


def test_cli_sources_have_no_domain_words():
    from pathlib import Path
    words = ['git', 'commit', 'push', 'branch', 'release', 'service', 'deploy', 'staged']
    for name in ('cli.py', '__main__.py'):
        source = (Path(cli.__file__).parent / name).read_text(encoding='utf-8').lower()
        assert not [word for word in words if word in source], name

@pytest.mark.parametrize('cleanup,matched', [(True, True), (False, False)])
def test_cleanup_line_forms(cleanup, matched):
    item = {'text': 'act()', 'ok': False, 'matched': matched, 'missing': [], 'unexpected': [],
            'cleanup': {'ok': cleanup}}
    expected = '  1. act() failed [cleanup ok]' if matched else (
        '  1. act() MISMATCH missing: -; unexpected: - (failed) [cleanup failed]')
    assert cli._executed_line(1, item) == expected


@pytest.mark.parametrize('cleanup_fails', [False, True])
def test_execute_observe_failure_text_and_exit(tmp_path, capsys, cleanup_fails):
    source = ('calls = 0\ndef sense(ctx):\n    global calls\n    calls += 1\n'
              '    if calls > 1: raise ValueError("sensor broke")\n    return "p(a)"\n'
              'def act(binding, ctx):\n    raise ValueError("first\\nlast line")\n'
              'def clean(binding, ctx):\n    pass\n'
              'CALLBACKS = {"sense": sense, "act": act, "clean": clean}\n')
    if cleanup_fails:
        source = source.replace('    pass\n', '    raise ValueError("cleanup broke")\n')
    action = {'name': 'act', 'params': ['x'], 'pre': ['p(?x)'], 'add': ['q(?x)'], 'del': [],
              'run': {'callback': 'act'}, 'on_fail': {'callback': 'clean'}}
    args = _write_domain(tmp_path, source, predicates={'p': 1, 'q': 1}, derived=[],
                         actions=[action], goals=['q'])
    assert main(['run', *args, '--goal', 'q(a)', '--execute', '--no-memory']) == 1
    output = capsys.readouterr().out
    assert f"(failed) [cleanup {'failed' if cleanup_fails else 'ok'}]" in output
    assert "  observe failed: sensor sense: callback raised ValueError('sensor broke')" in output
    assert '  last output: last line' in output
