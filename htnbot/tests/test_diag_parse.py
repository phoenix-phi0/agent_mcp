import ast
import json
import os
from pathlib import Path

import pytest

from planbot.diag.parse import (clean_text, norm_path, parse_locate, parse_probe, parse_report,
                                parse_run_test, safe_expr)


def test_clean_text_basics():
    assert clean_text('a\ud800b').encode('utf-8') == b'a?b'
    assert clean_text('x' * 10, 6) == 'xxx...'
    assert clean_text('abc', 3) == 'abc'
    assert clean_text(None) == 'None'


def test_clean_text_failing_str_returns_empty():
    class Bad:
        def __str__(self):
            raise ValueError('no')

    assert clean_text(Bad()) == ''


@pytest.mark.parametrize('text', ['x', 'a.b.c', 'xs[0]', 'd["k"]', 'xs[-1]', 'len(xs)', 'type(a.b)'])
def test_safe_expr_accepts(text):
    assert safe_expr(text) is True


@pytest.mark.parametrize('text', [
    'f(x)', 'x+1', 'xs[i]', 'xs[1:2]', 'len(x, y)', '__import__("os")', '', '1', '\ud800',
    'x' * 81, 'xs[True]', 'len(x=1)', 'len(*a)', 'a.b(c)', '[x for x in y]', 'lambda: 1',
    'x y', 'xs[--1]', 'a\0b', None, 5,
])
def test_safe_expr_rejects(text):
    assert safe_expr(text) is False


def test_safe_expr_length_limit_boundary():
    assert safe_expr('x' * 80) is True


@pytest.mark.parametrize('path', ['a/./b.py', 'a//b.py', 'a\\b.py'])
def test_norm_path_text_normalises(path):
    assert norm_path(path) == 'a/b.py'


@pytest.mark.parametrize('path', [
    '../x.py', 'a/../../x.py', '/abs/x.py', '', '.', None, 123, '\ud800.py', 'a\0b', '..',
])
def test_norm_path_text_rejects(path):
    assert norm_path(path) is None


@pytest.fixture
def tree(tmp_path):
    root = tmp_path / 'root'
    (root / 'a').mkdir(parents=True)
    (root / 'a' / 'b.py').write_text('x = 1\n')
    outside = tmp_path / 'outside.py'
    outside.write_text('y = 2\n')
    return root, outside


def test_norm_path_with_root_same_file_same_result(tree):
    root, _ = tree
    for path in ('a/b.py', './a/b.py', 'a//b.py', str(root / 'a' / 'b.py')):
        assert norm_path(path, str(root)) == 'a/b.py'


def test_norm_path_with_root_rejects_outside(tree):
    root, outside = tree
    for path in ('../outside.py', str(outside), str(root), '.', '', None):
        assert norm_path(path, str(root)) is None


def test_norm_path_with_root_rejects_symlink_escape(tree):
    root, outside = tree
    try:
        os.symlink(outside, root / 'link.py')
    except (OSError, NotImplementedError):
        pytest.skip('symlinks not supported')
    assert norm_path('link.py', str(root)) is None


# ---- parse_run_test / parse_report ----

FIXTURE = Path(__file__).parent / 'fixtures' / 'diag_real.json'
EMPTY_REPORT = {'unrunnable': False, 'location': None, 'failures': []}
BAD_INPUTS = [None, 'text', 5, [], {}, {'status': 'ok', 'exit_code': 1}, {'output': 123, 'exit_code': 1}]


@pytest.fixture(scope='module')
def cases():
    return json.loads(FIXTURE.read_text(encoding='utf-8'))['cases']


def test_fixture_passing_case_is_passed(cases):
    passed = [c for c in cases if c['calls']['run_test']['exit_code'] == 0]
    assert len(passed) == 1
    info = parse_run_test(passed[0]['calls']['run_test'])
    assert info['outcome'] == 'passed' and info['failed'] == []
    assert parse_report(passed[0]['calls']['test_report'], passed[0]['test']) == EMPTY_REPORT


def test_fixture_failing_cases_run_test_and_report(cases):
    failing = [c for c in cases if c['calls']['run_test']['exit_code'] != 0
               and 'import' not in c['test']]
    assert len(failing) == 9
    for c in failing:
        info = parse_run_test(c['calls']['run_test'])
        assert info['outcome'] == 'failed' and info['failed'] == sorted(set(info['failed']))
        assert info['failed'] and len(info['summary']) <= 200
        rep = parse_report(c['calls']['test_report'], c['test'])
        assert rep['unrunnable'] is False and rep['location'] is None and rep['failures']
        json.dumps(rep)
        for f in rep['failures']:
            assert f['exc_type'] and f['frames']
            assert all(type(fr['line']) is int and fr['line'] > 0 for fr in f['frames'])
            assert f['assert_line'] is not None and f['assert_line']['file'] == c['test']


def test_fixture_import_error_case_is_unrunnable(cases):
    c = next(c for c in cases if 'import' in c['test'])
    assert parse_run_test(c['calls']['run_test'])['outcome'] == 'unrunnable'
    rep = parse_report(c['calls']['test_report'], c['test'])
    assert rep['unrunnable'] is True and rep['failures'] == []
    assert rep['location'] == {'file': c['test'], 'line': 3}


def test_report_frames_order_and_message_original(cases):
    c = next(c for c in cases if c['test'].endswith('test_demo_error.py'))
    f = parse_report(c['calls']['test_report'], c['test'])['failures'][0]
    assert f['test'] == 'T.test_ratio' and f['exc_type'] == 'ZeroDivisionError'
    assert f['message'] == 'division by zero'
    assert [(fr['file'], fr['line']) for fr in f['frames']] == [
        ('tests/htn_demo/test_demo_error.py', 17), ('data/tmp/htn_demo/buggy2.py', 5)]
    assert f['frames'][-1]['func'] == 'ratio' and f['frames'][-1]['code'] == 'return a / diff'
    assert f['assert_line']['line'] == 17
    assert parse_report(c['calls']['test_report'])['failures'][0]['assert_line'] is None


def test_report_multiline_message_not_truncated(cases):
    c = next(c for c in cases if c['test'].endswith('test_demo_branch.py'))
    f = parse_report(c['calls']['test_report'])['failures'][0]
    assert f['message'] == "'D' != 'C'\n- D\n+ C"


SYNTAX_RUN = ('LOG=x.log\n  File "/r/tests/t.py", line 7\n    def (:\n        ^\n'
              'SyntaxError: invalid syntax\nEXIT=1\n')
SYNTAX_REPORT = ('test_report tests/t.py：测试跑不起来——导入测试文件时SyntaxError: invalid syntax\n'
                 '  位置 tests/t.py:7 (<module>)\n      7  def (:\n')


def test_unrunnable_with_and_without_location():
    run = {'status': 'failed', 'exit_code': 1, 'output': SYNTAX_RUN}
    assert parse_run_test(run)['outcome'] == 'unrunnable'
    rep = parse_report({'status': 'failed', 'exit_code': 2, 'output': SYNTAX_REPORT})
    assert rep['unrunnable'] is True and rep['location'] == {'file': 'tests/t.py', 'line': 7}
    bare = 'test_report tests/t.py：测试跑不起来——导入测试文件时SyntaxError: invalid syntax\n'
    rep = parse_report({'status': 'failed', 'exit_code': 2, 'output': bare})
    assert rep['unrunnable'] is True and rep['location'] is None


def test_unrunnable_location_takes_last_position():
    out = SYNTAX_REPORT.replace('位置 tests/t.py:7 (<module>)', '位置 a.py:2 (<module>)；调用链 a.py:2 → b.py:9')
    assert parse_report({'output': out})['location'] == {'file': 'b.py', 'line': 9}


@pytest.mark.parametrize('bad', BAD_INPUTS)
def test_bad_inputs_do_not_raise(bad):
    info = parse_run_test(bad)
    assert info['outcome'] == 'unrunnable' and info['failed'] == []
    if not isinstance(bad, dict):
        assert info['summary'] == 'invalid result'
    assert parse_report(bad) == EMPTY_REPORT


def test_run_test_exit_code_rules():
    assert parse_run_test({'status': 'x', 'exit_code': 0, 'output': ''})['outcome'] == 'passed'
    assert parse_run_test({'status': 'x', 'exit_code': True, 'output': ''})['outcome'] == 'unrunnable'
    assert parse_run_test({'status': 'failed', 'exit_code': 0, 'output': 'FAIL: x (m.T.x)'})['outcome'] == 'passed'
    out = 'FAIL: test_b (__main__.T.test_b)\nFAIL: test_a (__main__.T.test_a)\nFAIL: test_a (__main__.T.test_a) (i=1)\nFAILED (failures=2)\nEXIT=1\n'
    info = parse_run_test({'status': 'ok', 'exit_code': 1, 'output': out})
    assert info == {'outcome': 'failed', 'failed': ['T.test_a', 'T.test_b'], 'summary': 'FAILED (failures=2)'}
    assert len(parse_run_test({'exit_code': 1, 'output': 'x' * 500})['summary']) == 200


def test_report_assert_line_with_absolute_test_file():
    out = '[1] 失败 T.t\n    AssertionError: x\n    最内层仓库内帧 /r/tests/t.py:3 (t)\n'
    assert parse_report({'output': out}, '/r/tests/t.py')['failures'][0]['assert_line']['line'] == 3
    assert parse_report({'output': out}, 'tests/t.py')['failures'][0]['assert_line']['line'] == 3
    assert parse_report({'output': out}, '/x/other.py')['failures'][0]['assert_line'] is None


def test_report_surrogates_are_cleaned():
    out = '[1] 失败 T.t\n    ValueError: bad \ud800 value\n    最内层仓库内帧 a\ud800.py:3 (f)\n'
    rep = parse_report({'output': out})
    assert rep['failures'][0]['message'] == 'bad ? value'
    for f in rep['failures']:
        f['message'].encode('utf-8')
        f['frames'][0]['file'].encode('utf-8')


# ---- parse_locate / parse_probe ----

def _loc(rows):
    return {'status': 'ok', 'exit_code': 0, 'output': 'locate t.py：header\n失败用例：T.t (AssertionError)\n' + '\n'.join(rows) + '\n'}


def _probe(output, code=0):
    return {'status': 'ok' if code == 0 else 'failed', 'exit_code': code, 'output': output}


PROBE_OUT = ('probe t.py\n== d/m.py:7 | return total\n'
             '  #1 total = 6\n  #2 xs = [1, 2, 3]\n  #3 nope  求值出错: NameError: name \'nope\' is not defined\n'
             '  #4 a.b = NameError: boom\n')


def test_fixture_locate_outputs_parse(cases):
    failing = [c for c in cases if c['calls']['run_test']['exit_code'] != 0]
    assert len(failing) == 10
    empty = []
    for c in failing:
        lines = parse_locate(c['calls']['locate'])
        if not lines:  # the real output itself says "no suspicious line" / "cannot run"
            empty.append(c['test'])
        json.dumps(lines)
        for ln in lines:
            assert ln['fail'] >= 0 and ln['passed'] >= 0
            assert type(ln['susp']) is float and type(ln['line']) is int and ln['line'] > 0
            assert ln['file'] and ln['fail'] >= 1
    assert sorted(Path(t).name for t in empty) == ['test_demo_import.py', 'test_demo_inline.py']
    passed = next(c for c in cases if c['calls']['run_test']['exit_code'] == 0)
    assert parse_locate(passed['calls']['locate']) == []


def test_locate_fixture_row_values(cases):
    c = next(c for c in cases if c['test'].endswith('test_demo_fail.py'))
    lines = parse_locate(c['calls']['locate'])
    assert [(ln['file'], ln['line'], ln['susp'], ln['fail'], ln['passed']) for ln in lines][-1] == (
        'data/tmp/htn_demo/buggy.py', 2, 0.707, 1, 1)
    assert [ln['line'] for ln in lines] == [4, 5, 6, 7, 2]


def test_locate_susp_fallback_per_file_max():
    rows = [' 1. a.py:1  失败 2/4  通过 0/3  | x', ' 2. a.py:2  失败 1/4  通过 3/3  | y',
            ' 3. b.py:1  失败 4/4  通过 0/3  | z', ' 4. b.py:2  失败 2/4  通过 2/3  | w',
            ' 5. b.py:3  通过 2/3  | v']
    got = parse_locate(_loc(rows))
    assert [ln['susp'] for ln in got] == pytest.approx([1.0, 0.35355, 1.0, 0.5, 0.0], abs=1e-4)
    assert [(ln['fail'], ln['passed']) for ln in got] == [(2, 0), (1, 3), (4, 0), (2, 2), (0, 2)]
    assert parse_locate(_loc([' 1. a.py:1  失败 0/1  通过 0/1  | x']))[0]['susp'] == 0.0
    assert all(type(ln['susp']) is float for ln in got)


def test_locate_given_susp_wins_and_dedupe_keeps_first_in_order():
    rows = [' 1. a.py:3  0.900  失败 1/1  通过 0/2  | x', ' 2. b.py:1  0.500  失败 1/1  通过 1/2  | y',
            ' 3. a.py:3  0.100  失败 1/1  通过 1/2  | x', ' 4. ./a.py:3  0.200  失败 1/1  通过 1/2  | x']
    got = parse_locate(_loc(rows))
    assert [(ln['file'], ln['line'], ln['susp']) for ln in got] == [
        ('a.py', 3, 0.9), ('b.py', 1, 0.5), ('./a.py', 3, 0.2)]


def test_locate_nonzero_exit_without_rows_and_junk_lines():
    assert parse_locate({'status': 'failed', 'exit_code': 2, 'output': 'locate: no such file\n'}) == []
    assert parse_locate(_loc([' 1. a.py:0  0.5', 'not a row', ' 2. a.py:5  0.5']))[0]['line'] == 5


def test_probe_keeps_good_values_drops_errors():
    got = parse_probe(_probe(PROBE_OUT))
    assert got == [{'at': 'd/m.py:7', 'expr': 'total', 'value': '6', 'test': None, 'outcome': None},
                   {'at': 'd/m.py:7', 'expr': 'xs', 'value': '[1, 2, 3]', 'test': None, 'outcome': None}]
    assert parse_probe(_probe(PROBE_OUT, 1)) == []
    assert parse_probe(_probe('')) == []
    assert parse_probe(_probe('  #1 x = 1\n')) == []  # no position header


def test_probe_case_outcome_when_distinguished():
    out = '== m.py:3 | line\n  #1 x = 1 (用例 T.a 失败)\n  #2 x = 2 [test: T.b pass]\n'
    got = parse_probe(_probe(out))
    assert [(v['expr'], v['value'], v['test'], v['outcome']) for v in got] == [
        ('x', '1', 'T.a', 'fail'), ('x', '2', 'T.b', 'pass')]


@pytest.mark.parametrize('bad', BAD_INPUTS + [{'exit_code': 0}, {'exit_code': 0, 'output': 5}])
def test_locate_probe_bad_inputs(bad):
    assert parse_locate(bad) == [] and parse_probe(bad) == []


def test_locate_probe_surrogates_encodable():
    loc = parse_locate(_loc([' 1. a\ud800.py:3  0.5  失败 1/1  通过 0/1  | x']))
    pro = parse_probe(_probe('== a\ud800.py:3 | x\n  #1 v\ud800 = \'\ud800\'\n'))
    assert loc and pro
    for item in loc + pro:
        for v in item.values():
            if isinstance(v, str):
                v.encode('utf-8')


def test_module_imports_stdlib_only_and_no_forbidden_word():
    src = (Path(__file__).parent.parent / 'planbot' / 'diag' / 'parse.py').read_text(encoding='utf-8')
    mods = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            mods.update(a.name.split('.')[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            mods.add((node.module or '').split('.')[0] if node.level == 0 else '.')
    assert mods <= {'json', 're', 'ast', 'os', 'posixpath', 'math'}
    assert ('tr' + 'uth') not in src
