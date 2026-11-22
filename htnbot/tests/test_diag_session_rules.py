"""Session rules: locate limit, auto probe sample points, sample ranking."""
import json
from pathlib import Path

import pytest

from planbot.diag import Session, diagnose

DOMAIN = str(Path(__file__).resolve().parent.parent / 'examples' / 'diagnose' / 'domain.json')
FAIL_OUT = 'FAIL: test_a (t.T)\n'
BODY = ''.join('v%d = %d\n' % (i, i) for i in range(1, 13))
CASE_FAIL, CASE_PASS = '（用例 test_a 失败）', '（用例 test_b 通过）'


def ok(output='', code=0):
    return {'status': 'ok', 'exit_code': code, 'output': output}


def report_of(frame):
    return ok('test_report t.py：\n[1] 失败 T.test_a\n    ValueError: x\n    最内层仓库内帧 %s (f)\n' % frame)


def loc_of(*refs, score='0.5'):
    rows = ''.join(' %d. %s  %s  失败 1/1  通过 0/1  | x\n' % (i, r, score) for i, r in enumerate(refs, 1))
    return ok('locate t.py：header\n' + rows)


class Script:
    """Runner that answers per command (a result or a callable on args) and records the calls."""

    def __init__(self, **script):
        self.script = script
        self.seen = []

    def __call__(self, name, args):
        self.seen.append((name, args))
        item = self.script[name]
        return item(args) if callable(item) else item

    def args_of(self, name):
        return [a for n, a in self.seen if n == name]


@pytest.fixture
def repo(tmp_path):
    (tmp_path / 'pkg').mkdir()
    (tmp_path / 'pkg' / 'm.py').write_text(BODY)
    (tmp_path / 'pkg' / 'n.py').write_text(BODY)
    return tmp_path


def drive(session, path='t.py'):
    for name in ('run_test', 'test_report', 'locate'):
        session.run(name, {'path': path})


# ---- locate asks for 50 rows ----

def test_locate_args_from_diagnose_carry_limit(repo):
    runner = Script(run_test=ok(FAIL_OUT, 1), test_report=report_of('pkg/m.py:3'),
                    locate=loc_of('pkg/m.py:3', score='0.9'))
    out = diagnose(DOMAIN, 't.py', runner, execute=True, repo_root=str(repo))
    assert runner.args_of('locate') == [{'path': 't.py', 'limit': 50}]
    call = [c for c in out['calls'] if c['name'] == 'locate'][0]
    assert call['args'] == {'path': 't.py', 'limit': 50}
    for name in ('run_test', 'test_report'):
        assert runner.args_of(name) == [{'path': 't.py'}]


def test_locate_limit_is_overridden_and_input_not_mutated(repo):
    runner = Script(run_test=ok(FAIL_OUT, 1), test_report=report_of('pkg/m.py:3'),
                    locate=loc_of('pkg/m.py:3', score='0.9'))
    s = Session(runner, str(repo))
    s.run('run_test', {'path': 't.py'})
    s.run('test_report', {'path': 't.py'})
    given = {'path': 't.py', 'limit': 3}
    s.run('locate', given)
    assert runner.args_of('locate') == [{'path': 't.py', 'limit': 50}]
    assert given == {'path': 't.py', 'limit': 3}
    assert s.calls[-1]['args'] == {'path': 't.py', 'limit': 50}


def test_probe_args_have_no_limit(repo):
    runner = Script(run_test=ok(FAIL_OUT, 1), test_report=report_of('pkg/n.py:4'),
                    locate=loc_of('pkg/m.py:1', 'pkg/m.py:2'), probe=ok(''))
    s = Session(runner, str(repo))
    drive(s)
    s.run('probe', {'path': 't.py'})
    sent = runner.args_of('probe')
    assert len(sent) == 2 and all('limit' not in a for a in sent)


def test_short_circuited_locate_makes_no_runner_call(repo):
    unrunnable = ok('test_report t.py：测试跑不起来——导入测试文件时SyntaxError: bad\n')
    runner = Script(run_test=ok('collect error', 2), test_report=unrunnable, locate=loc_of('pkg/m.py:1'))
    s = Session(runner, str(repo))
    drive(s)
    assert [n for n, _ in runner.seen] == ['run_test', 'test_report']
    assert [c['name'] for c in s.calls] == ['run_test', 'test_report']


def test_wide_gap_keeps_three_calls(repo):
    runner = Script(run_test=ok(FAIL_OUT, 1), test_report=report_of('pkg/m.py:3'),
                    locate=loc_of('pkg/m.py:3', score='0.9'))
    out = diagnose(DOMAIN, 't.py', runner, execute=True, repo_root=str(repo))
    assert [c['name'] for c in out['calls']] == ['run_test', 'test_report', 'locate']
    assert json.dumps(out['finding'])


# ---- auto probe sampling ----

LOCATED = ['pkg/m.py:%d' % n for n in (1, 2, 3, 4, 5, 6, 7)]
FRAME = 'pkg/n.py:4'


def probe_runner(repo, fail_at=None, outcome=True, allow_probe=True):
    """Session whose probe answers, at the `fail_at`-th sent position, with two values of one expression."""
    def answer(args):
        if fail_at is None:
            return ok('')
        at, expr = args['at'][fail_at], args['exprs'][0]
        marks = (CASE_FAIL, CASE_PASS) if outcome else ('', '')
        return ok('probe t.py\n== %s | x\n  #1 %s = A%s\n  #2 %s = B%s\n' % (at, expr, marks[0], expr, marks[1]))
    runner = Script(run_test=ok(FAIL_OUT, 1), test_report=report_of(FRAME), locate=loc_of(*LOCATED),
                    probe=answer)
    s = Session(runner, str(repo), allow_probe=allow_probe)
    drive(s)
    return s, runner


def test_auto_probe_points_follow_locate_order_then_frame(repo):
    s, runner = probe_runner(repo)
    sent = runner.args_of('probe')
    assert len(sent) == 1 and set(sent[0]) == {'path', 'at', 'exprs'}
    assert sent[0]['path'] == 't.py'
    assert sent[0]['at'][:5] == LOCATED[:5]
    assert FRAME in sent[0]['at'][5:]
    assert len(sent[0]['at']) <= 8 and sent[0]['exprs']
    assert [c['name'] for c in s.calls] == ['run_test', 'test_report', 'locate', 'probe']
    assert 'limit' not in sent[0]


def test_sample_values_lift_the_row_whose_values_differ(repo):
    base, _ = probe_runner(repo, allow_probe=False)
    target = LOCATED[4]
    base_first = base.finding('t.py')['candidates'][0]
    assert '%s:%d' % (base_first['file'], base_first['line']) != target
    s, _ = probe_runner(repo, fail_at=4)
    f = s.finding('t.py')
    assert (f['status'], f['source']) == ('found', 'locate')
    first = f['candidates'][0]
    assert '%s:%d' % (first['file'], first['line']) == target
    assert {p['value'] for p in first['probe']} == {'A', 'B'}
    assert len(f['candidates']) <= 5


def test_values_without_outcome_do_not_enter_sample_ranking(repo):
    target = LOCATED[4]
    s, _ = probe_runner(repo, fail_at=4, outcome=False)
    f = s.finding('t.py')
    assert (f['status'], f['source']) == ('found', 'locate')
    first = f['candidates'][0]
    assert '%s:%d' % (first['file'], first['line']) != target


# ---- assert-variable rule ----

FILLER = ''.join('    f%d = %d\n' % (i, i) for i in range(1, 8))     # lines 3..9
TEST_SRC = (
    'def test_a():\n'                # 1
    '    total = 1\n'                # 2  earlier assignment
    + FILLER +
    '    total = sum([1, 2])\n'      # 10 <- last assignment before the assertion
    '    noise = 0\n'                # 11
    '    print(noise)\n'             # 12
    '    assert total == 6\n'        # 13
)
TOTAL_AT, ASSERT_AT = 10, 13
UNITTEST_SRC = (
    'class K:\n'                                       # 1
    '    def test_a(self):\n'                          # 2
    + ''.join('        f%d = %d\n' % (i, i) for i in range(1, 9)) +   # 3..10
    '        got = 1\n'                                # 11
    '        want = 2\n'                               # 12
    '        pad = 0\n'                                # 13
    '        self.assertEqual(got, want)\n'            # 14
)
SHORT_SRC = (
    'def test_a():\n'
    '    total = sum([1, 2])\n'      # 2
    '    assert total == 6\n'        # 3
)


def report_text(test, frame, chain=None):
    tail = '；调用链 ' + chain if chain else ''
    return ok('test_report t.py：\n[1] 失败 %s\n    AssertionError: x\n    最内层仓库内帧 %s (f)%s\n'
              % (test, frame, tail))


def scene(repo, src=TEST_SRC, test='T.test_a', frame='t.py:%d' % ASSERT_AT, chain=None, loc=None,
          probe=None, allow_probe=True):
    if src is not None:
        (repo / 't.py').write_text(src)
    script = dict(run_test=ok(FAIL_OUT, 1), test_report=report_text(test, frame, chain),
                  locate=loc or ok('locate t.py：header\n'))
    if probe is not None:
        script['probe'] = probe
    runner = Script(**script)
    s = Session(runner, str(repo), allow_probe=allow_probe)
    drive(s)
    return s, runner


def places(f):
    return [(c['file'], c['line']) for c in f['candidates']]


def test_assert_var_lists_last_assignment_inside_the_test(repo):
    s, _ = scene(repo)
    f = s.finding('t.py')
    assert (f['status'], f['source']) == ('not_found', 'report_only')
    first = f['candidates'][0]
    assert (first['file'], first['line']) == ('t.py', TOTAL_AT)
    assert 'assert_var' in first['reasons'] and first['snippet']
    assert ('t.py', 2) not in places(f)[:1] and len(f['candidates']) <= 5
    assert json.dumps(f)


def test_assert_var_already_ranked_keeps_its_place_and_gains_the_reason(repo):
    s, _ = scene(repo, SHORT_SRC, frame='t.py:3')
    f = s.finding('t.py')
    rows = places(f)
    assert rows.count(('t.py', 2)) == 1
    assert 'assert_var' in f['candidates'][rows.index(('t.py', 2))]['reasons']
    assert all('assert_var' not in c['reasons'] for c in f['candidates'] if c['line'] != 2)
    assert len(rows) <= 5


def test_assert_var_unittest_style_and_subtest_suffix(repo):
    s, _ = scene(repo, UNITTEST_SRC, test='K.test_a (v=1)', frame='t.py:14')
    f = s.finding('t.py')
    assert (f['status'], f['source']) == ('not_found', 'report_only')
    rows = places(f)
    assert rows[:2] == [('t.py', 12), ('t.py', 11)]  # nearest to the assertion first
    for c in f['candidates'][:2]:
        assert 'assert_var' in c['reasons']
    assert all('assert_var' not in c['reasons'] for c in f['candidates'][2:])
    assert ('t.py', 2) not in rows and len(rows) <= 5  # self has no assignment


def test_assert_var_after_the_ranked_rows_when_a_non_test_frame_exists(repo):
    chain = 't.py:%d → pkg/m.py:3' % ASSERT_AT
    s, _ = scene(repo, chain=chain, frame='pkg/m.py:3')
    f = s.finding('t.py')
    assert (f['status'], f['source']) == ('not_found', 'report_only')
    assert len(f['candidates']) <= 5
    last = f['candidates'][-1]
    assert (last['file'], last['line']) == ('t.py', TOTAL_AT) and 'assert_var' in last['reasons']
    assert all('assert_var' not in c['reasons'] for c in f['candidates'][:-1])


@pytest.mark.parametrize('case', ['no_assert_line', 'unreadable', 'syntax', 'param_only', 'locate_valid'])
def test_assert_var_not_produced(repo, case):
    kw = {}
    if case == 'no_assert_line':
        kw = dict(frame='pkg/m.py:3')
    elif case == 'unreadable':
        kw = dict(src=None)
    elif case == 'syntax':
        kw = dict(src='def test_a(:\n    pass\n')
    elif case == 'param_only':
        kw = dict(src='def test_a(total):\n    pad = 0\n    assert total == 6\n', frame='t.py:3')
    elif case == 'locate_valid':
        kw = dict(loc=loc_of('pkg/m.py:3', score='0.9'), chain='t.py:%d → pkg/m.py:3' % ASSERT_AT,
                  frame='pkg/m.py:3')
    s, _ = scene(repo, **kw)
    f = s.finding('t.py')
    assert all('assert_var' not in c['reasons'] for c in f['candidates'])
    if case == 'locate_valid':
        assert (f['status'], f['source']) == ('found', 'locate')
    else:
        assert (f['status'], f['source']) == ('not_found', 'report_only')


def test_assert_var_assignment_forms(tmp_path):
    from planbot.diag.session import _assert_var_lines
    src = ('def test_a():\n'
           '    idx = 1\n'               # 2
           '    arr = [0, 0]\n'          # 3
           '    arr[idx] = 0\n'          # 4  item store: not a rebinding of arr or idx
           '    assert arr[idx] == 5\n')  # 5
    rep = {'failures': [{'test': 'T.test_a', 'assert_line': {'file': 't.py', 'line': 5}, 'frames': []}]}
    assert _assert_var_lines(rep, {'t.py': src}, 't.py') == [('t.py', 3), ('t.py', 2)]
    src = ('def test_a():\n'
           '    a, (b, c) = 1, (2, 3)\n'  # 2
           '    for d in range(2):\n'      # 3
           '        pass\n'
           '    with open(__file__) as e:\n'  # 5
           '        pass\n'
           '    if (g := 4):\n'            # 7
           '        pass\n'
           '    assert a + b + c + d + e + g == 0\n')
    rep['failures'][0]['assert_line']['line'] = 9
    # nearest two distinct lines first
    assert _assert_var_lines(rep, {'t.py': src}, 't.py') == [('t.py', 7), ('t.py', 5)]


def explicit_probe(args):
    at = args['at'][0]
    return ok('probe t.py\n== %s | x\n  #1 %s = 3\n' % (at, args['exprs'][0]))


def test_explicit_probe_keeps_the_assert_var_line(repo):
    s, _ = scene(repo, probe=explicit_probe)
    assert s.finding('t.py')['source'] == 'report_only'
    s.run('probe', {'path': 't.py'})
    f = s.finding('t.py')
    assert (f['status'], f['source']) == ('found', 'probe')
    cands = f['candidates']
    assert any(c['probe'] for c in cands)
    var_row = [c for c in cands if (c['file'], c['line']) == ('t.py', TOTAL_AT)]
    assert len(var_row) == 1 and 'assert_var' in var_row[0]['reasons']
    assert all(c['probe'] or 'assert_var' in c['reasons'] for c in cands) and len(cands) <= 5


def test_explicit_probe_without_assert_var_all_candidates_have_values(repo):
    s, _ = scene(repo, frame='pkg/m.py:3', probe=explicit_probe)
    s.run('probe', {'path': 't.py'})
    f = s.finding('t.py')
    assert (f['status'], f['source']) == ('found', 'probe')
    assert f['candidates'] and all(c['probe'] for c in f['candidates'])


# ---- fallback branch, canonical report, constraint scan, bad CallRecord ----

def test_report_only_outside_root_frame_is_listed_unread(repo, tmp_path_factory):
    outside = str(tmp_path_factory.mktemp('away') / 'x.py')
    runner = Script(run_test=ok(FAIL_OUT, 1), test_report=report_of('%s:7' % outside),
                    locate=ok('locate t.py：header\n'))
    s = Session(runner, str(repo))
    drive(s)
    f = s.finding('t.py')
    assert (f['status'], f['source']) == ('not_found', 'report_only')
    cands = f['candidates']
    assert [(c['file'], c['line']) for c in cands] == [(outside, 7)]
    for c in cands:
        assert c['score'] == 0.0 and c['snippet'] == []
        assert isinstance(c['reasons'], list) and c['reasons']
        assert all(isinstance(r, str) for r in c['reasons'])


def test_report_only_falls_back_to_stack_frames_when_rank_is_empty(repo, tmp_path_factory, monkeypatch):
    import planbot.diag.session as session_module
    outside = str(tmp_path_factory.mktemp('away') / 'x.py')
    monkeypatch.setattr(session_module, 'rank', lambda *a, **k: [])
    runner = Script(run_test=ok(FAIL_OUT, 1), test_report=report_of('%s:7' % outside),
                    locate=ok('locate t.py：header\n'))
    s = Session(runner, str(repo))
    drive(s)
    f = s.finding('t.py')
    assert (f['status'], f['source']) == ('not_found', 'report_only')
    assert [(c['file'], c['line'], c['score'], c['reasons']) for c in f['candidates']] == \
        [(outside, 7, 0.0, ['stack'])]


def test_report_with_absolute_frame_is_canonical_in_locate_branch(repo):
    absolute = str(repo / 'pkg' / 'm.py')
    runner = Script(run_test=ok(FAIL_OUT, 1), test_report=report_of('%s:3' % absolute),
                    locate=loc_of('pkg/m.py:3', 'pkg/m.py:8', score='0.9'))
    s = Session(runner, str(repo))
    drive(s)
    f = s.finding('t.py')
    assert (f['status'], f['source']) == ('found', 'locate')
    assert f['candidates']
    for c in f['candidates']:
        assert not c['file'].startswith('/') and str(repo) not in c['file']
    assert ('pkg/m.py', 3) in places(f)


def test_session_and_package_sources_obey_constraints():
    import ast
    import os
    import re
    import subprocess
    import sys
    root = Path(__file__).resolve().parent.parent
    files = [root / 'planbot' / 'diag' / 'session.py', root / 'planbot' / 'diag' / '__init__.py']
    for p in files:
        text = p.read_text(encoding='utf-8')
        assert 'truth' not in text
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.Import):
                tops = [a.name.split('.')[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                tops = [(node.module or '').split('.')[0]] if node.level == 0 else ['planbot']
            else:
                continue
            for top in tops:
                assert top in sys.stdlib_module_names or top == 'planbot', (p.name, top)
    text = files[0].read_text(encoding='utf-8')
    assert len(re.findall(r'LOCATE_LIMIT\s*=\s*50\b', text)) == 1
    assert len(re.findall(r'\b50\b', text)) == 1
    env = dict(os.environ, PYTHONPATH=str(root))
    code = 'import sys, planbot; sys.exit(1 if "planbot.diag" in sys.modules else 0)'
    done = subprocess.run([sys.executable, '-c', code], env=env, cwd=str(root))
    assert done.returncode == 0


def diag_state(s):
    return json.loads(s.run('diag_state', {})['output'])


@pytest.mark.parametrize('bad', [RuntimeError('boom'), {'status': 'ok', 'exit_code': True, 'output': ''}])
def test_call_record_for_bad_results_and_progress_unchanged(repo, bad):
    def answer(args):
        if isinstance(bad, Exception):
            raise bad
        return bad
    runner = Script(run_test=ok(FAIL_OUT, 1), test_report=answer)
    s = Session(runner, str(repo))
    s.run('run_test', {'path': 't.py'})
    before = diag_state(s)
    r = s.run('test_report', {'path': 't.py'})
    rec = s.calls[-1]
    assert rec['name'] == 'test_report' and rec['status'] == 'error' and rec['exit_code'] is None
    expected = 'boom' if isinstance(bad, Exception) else 'invalid runner result'
    assert rec['output'] == expected
    assert (r['status'], r['exit_code'], r['output']) == ('error', 1, expected)
    assert diag_state(s) == before
