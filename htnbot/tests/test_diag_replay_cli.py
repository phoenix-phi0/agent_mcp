import json
import os
import re
import subprocess
import sys

import pytest

from planbot.core import PlanbotError
from planbot.diag import replay as replay_module
from planbot.diag.replay import load_cases, main

FIXTURE = 'tests/fixtures/diag_real.json'
DOMAIN = 'examples/diagnose/domain.json'
MISSING = 'no/such/file.json'
# measured totals; they agree with the per-case table EXPECTED in test_diag_fixture.py
# (with the recorded probe replayed, every failing case is found)
TOTALS = {'cases': 11, 'passed': 1, 'found': 10, 'not_found': 0}
TOTAL_LINE = 'cases: 11 passed: 1 found: 10 not_found: 0'
IDS = [c['id'] for c in load_cases(FIXTURE)]

_RUNS = {}


def run(capsys, *argv):
    code = main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err


def run_once(capsys, *argv):
    """The full-fixture runs are slow-ish; each distinct argv is computed once."""
    if argv not in _RUNS:
        _RUNS[argv] = run(capsys, *argv)
    return _RUNS[argv]


def fixture_copy(tmp_path, edit):
    with open(FIXTURE, encoding='utf-8') as handle:
        data = json.load(handle)
    edit(data['cases'])
    path = tmp_path / 'fixture.json'
    path.write_text(json.dumps(data), encoding='utf-8')
    return str(path)


def error_json(out):
    obj = json.loads(out)
    assert set(obj) == {'error'} and set(obj['error']) == {'code', 'message'}
    return obj['error']


# 1. text output

def test_text_full_run(capsys, tmp_path):
    code, out, err = run_once(capsys, 'replay', '--fixture', FIXTURE)
    assert code == 0 and err == ''
    lines = out.splitlines()
    assert sum(1 for line in lines if line.startswith('case: ')) == 11
    assert [line[6:] for line in lines if line.startswith('case: ')] == IDS
    assert lines[-1] == TOTAL_LINE
    assert sum(1 for line in lines if line.startswith('engine: stuck (')) == 0
    assert 'truth' not in out.lower()
    # the replay root is a fresh directory under the system temp dir; no absolute path may leak
    assert str(tmp_path) not in out and not re.search(r'(^|[\s:(\[])/(tmp|var|private|home|root)/', out)
    assert not re.search(r'tmp[a-z0-9_]{8}', out)


def test_text_block_shape(capsys):
    _, out, _ = run_once(capsys, 'replay', '--fixture', FIXTURE)
    first = out.split('case: ')[1].splitlines()
    keys = [line.split(':')[0] for line in first if not line.startswith(' ')]
    assert keys == ['%s' % IDS[0], 'status', 'failed', 'exception', 'engine', 'calls', 'candidates']


def test_text_single_case(capsys):
    code, out, _ = run(capsys, 'replay', '--fixture', FIXTURE, '--case', IDS[2])
    assert code == 0
    lines = out.splitlines()
    assert sum(1 for line in lines if line.startswith('case: ')) == 1
    assert lines[0] == 'case: ' + IDS[2]
    assert lines[-1].startswith('cases: 1 passed: ')


def test_text_case_follows_fixture_order(capsys):
    _, out, _ = run(capsys, 'replay', '--fixture', FIXTURE, '--case', IDS[3], '--case', IDS[1])
    assert [x[6:] for x in out.splitlines() if x.startswith('case: ')] == [IDS[1], IDS[3]]


def test_text_summary(capsys):
    code, out, _ = run_once(capsys, 'replay', '--fixture', FIXTURE, '--summary')
    assert code == 0
    blocks = out.split('case: ')[1:]
    assert len(blocks) == 11
    for block in blocks:
        assert '\nsummary:\n' in block
        assert block.split('\nsummary:\n')[1].count('  hint: ') == 1
    assert out.splitlines()[-1] == TOTAL_LINE
    assert 'truth' not in out.lower()


# 2. json output

def test_json_full_run(capsys):
    code, out, err = run_once(capsys, 'replay', '--fixture', FIXTURE, '--json')
    assert code == 0 and err == ''
    obj = json.loads(out)
    assert set(obj) == {'cases', 'totals'}
    assert obj['totals'] == TOTALS
    assert len(obj['cases']) == 11
    stuck = [c for c in obj['cases'] if c['engine']['status'] == 'stuck']
    assert stuck == []
    assert all(c['engine']['reason'] is None for c in obj['cases'] if c['engine']['status'] != 'stuck')
    for case in obj['cases']:
        assert set(case) == {'calls', 'engine', 'finding', 'id'}
        assert set(case['engine']) == {'status', 'reason', 'replans'}
        for call in case['calls']:
            assert set(call) == {'name', 'args', 'exit_code'}
    assert out == json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + '\n'
    assert 'truth' not in out.lower()


def test_json_summary(capsys):
    code, out, _ = run_once(capsys, 'replay', '--fixture', FIXTURE, '--json', '--summary')
    assert code == 0
    obj = json.loads(out)
    for case in obj['cases']:
        assert set(case) == {'calls', 'engine', 'finding', 'id', 'summary'}
        assert 'hint: ' in case['summary']
    assert obj['totals'] == TOTALS


# 3. error codes and order

@pytest.mark.parametrize('as_json', [False, True])
def test_error_cases(capsys, as_json):
    flag = ['--json'] if as_json else []
    cases = [
        (['replay', '--fixture', MISSING], 'USAGE'),
        (['replay', '--fixture', FIXTURE, '--case', 'nope.py'], 'USAGE'),
        (['replay', '--fixture', FIXTURE, '--max-replans', '-1'], 'USAGE'),
        (['replay', '--fixture', FIXTURE, '--domain', 'no/domain.json'], 'DOMAIN_INVALID'),
        (['replay', '--fixture', MISSING, '--domain', 'no/domain.json'], 'USAGE'),
        (['replay', '--fixture', FIXTURE, '--case', 'nope.py', '--max-replans', '-1',
          '--domain', 'no/domain.json'], 'USAGE'),
    ]
    for argv, want in cases:
        code, out, err = run(capsys, *argv, *flag)
        assert code == 2
        if as_json:
            assert err == ''
            assert error_json(out)['code'] == want
        else:
            assert out == ''
            assert err.startswith('error: %s: ' % want) and err.count('\n') == 1


def test_case_error_precedes_negative_replans(capsys):
    code, _, err = run(capsys, 'replay', '--fixture', FIXTURE, '--case', 'nope.py', '--max-replans', '-1')
    assert code == 2 and 'nope.py' in err
    code, _, err = run(capsys, 'replay', '--fixture', FIXTURE, '--max-replans', '-1',
                       '--domain', 'no/domain.json')
    assert code == 2 and err.startswith('error: USAGE: ')


# 4. argument syntax errors

@pytest.mark.parametrize('argv', [
    ['replay'],
    ['replay', '--fixture', FIXTURE, '--max-replans', 'abc'],
    ['replay', '--fixture', FIXTURE, '--nope'],
    ['other', '--fixture', FIXTURE],
    [],
])
def test_syntax_errors(capsys, argv):
    code, out, err = run(capsys, *argv)
    assert code == 2 and out == ''
    assert err.startswith('error: USAGE: ') and err.count('\n') == 1
    code, out, err = run(capsys, *argv, '--json')
    assert code == 2 and err == ''
    assert error_json(out)['code'] == 'USAGE'
    assert isinstance(error_json(out)['message'], str) and error_json(out)['message']


def test_help_is_default(capsys):
    with pytest.raises(SystemExit) as exc:
        main(['-h'])
    assert exc.value.code == 0
    assert 'replay' in capsys.readouterr().out


# 5. GOAL_INVALID

def test_goal_invalid(capsys, tmp_path):
    def edit(cases):
        cases[1]['test'] = 'a b.py'
    path = fixture_copy(tmp_path, edit)
    code, out, err = run(capsys, 'replay', '--fixture', path)
    assert code == 2 and out == ''
    assert err.startswith('error: GOAL_INVALID: case a b.py: ') and err.count('\n') == 1
    code, out, err = run(capsys, 'replay', '--fixture', path, '--json')
    assert code == 2 and err == ''
    error = error_json(out)
    assert error['code'] == 'GOAL_INVALID' and error['message'].startswith('case a b.py: ')


def test_fixture_source_key_out_of_root(capsys, tmp_path):
    def edit(cases):
        src = cases[0]['sources']
        src['../evil.py'] = src.pop(next(iter(src)))
    path = fixture_copy(tmp_path, edit)
    code, out, err = run(capsys, 'replay', '--fixture', path)
    assert code == 2 and out == '' and err.startswith('error: USAGE: ')


# 6. SENSOR_FAILED

def test_sensor_failed(capsys, monkeypatch):
    target = IDS[1]
    real = replay_module.replay_case

    def fake(case, domain_path, max_replans=3):
        if case['id'] == target:
            raise PlanbotError('SENSOR_FAILED', 'boom')
        return real(case, domain_path, max_replans)

    monkeypatch.setattr(replay_module, 'replay_case', fake)
    code, out, err = run(capsys, 'replay', '--fixture', FIXTURE)
    assert code == 2 and out == ''
    assert err == 'error: SENSOR_FAILED: case %s: boom\n' % target
    code, out, err = run(capsys, 'replay', '--fixture', FIXTURE, '--json')
    assert code == 2 and err == ''
    assert json.loads(out) == {'error': {'code': 'SENSOR_FAILED', 'message': 'case %s: boom' % target}}
    assert out == json.dumps(json.loads(out), ensure_ascii=False, indent=2, sort_keys=True) + '\n'


# 7. determinism

def test_deterministic(capsys):
    for extra in ([], ['--json'], ['--summary'], ['--json', '--summary']):
        argv = ['replay', '--fixture', FIXTURE] + extra
        first = run(capsys, *argv)
        second = run(capsys, *argv)
        assert first == second and first[0] == 0


# 8. python -m

def test_module_entry():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    done = subprocess.run([sys.executable, '-m', 'planbot.diag', 'replay', '--fixture', FIXTURE],
                          cwd=root, capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines()[-1] == TOTAL_LINE
    bad = subprocess.run([sys.executable, '-m', 'planbot.diag', 'replay'], cwd=root,
                         capture_output=True, text=True, timeout=60)
    assert bad.returncode == 2 and bad.stdout == '' and bad.stderr.startswith('error: USAGE: ')
