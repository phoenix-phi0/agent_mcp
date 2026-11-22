import ast
import json
import random
from pathlib import Path

import pytest

from planbot.diag import rank as rank_mod
from planbot.diag.rank import WEIGHTS, needs_probe, rank

RANK_PY = Path(rank_mod.__file__)
SRC = 'm.py'
TEST = 't_m.py'

FUNC_SOURCE = '\n'.join([
    'def check(n):',                    # 1
    '    total = 0',                    # 2
    '    for i in range(3):',           # 3
    '        total = total + i',        # 4
    '    if n <= 0:',                   # 5
    '        msg = "bad"',              # 6
    '        raise ValueError(msg)',    # 7
    '    return total',                 # 8
    '',                                 # 9
    'def other():',                     # 10
    '    return 1',                     # 11
    '',                                 # 12
]) + '\n'


def row(line, susp=0.5, fail=1, passed=0, file=SRC):
    return {'file': file, 'line': line, 'susp': susp, 'fail': fail, 'passed': passed}


def frame(line, file=SRC, func='f'):
    return {'file': file, 'line': line, 'func': func, 'code': ''}


def report(*frames, exc='ValueError'):
    return {'unrunnable': False, 'location': None, 'failures': [
        {'test': 't', 'exc_type': exc, 'message': 'm', 'frames': list(frames), 'assert_line': None}]}


EMPTY = {'unrunnable': False, 'location': None, 'failures': []}


def lines_of(cands):
    return [c['line'] for c in cands]


def raw_only(got, rep, loc):
    """Keep the candidates of the original pool: every loc row plus every stack frame row."""
    pool = {(r['file'], r['line']) for r in loc}
    pool |= {(f['file'], f['line']) for fail in rep['failures'] for f in fail['frames']}
    return [c for c in got if (c['file'], c['line']) in pool]


def test_deterministic_and_loc_order_independent():
    loc = [row(n, susp=0.5) for n in range(1, 10)]
    rep = report(frame(7))
    first = rank(rep, loc, {SRC: FUNC_SOURCE}, TEST, limit=9)
    second = rank(rep, loc, {SRC: FUNC_SOURCE}, TEST, limit=9)
    assert json.dumps(first) == json.dumps(second)
    shuffled = list(loc)
    random.Random(7).shuffle(shuffled)
    assert json.dumps(rank(rep, shuffled, {SRC: FUNC_SOURCE}, TEST, limit=9)) == json.dumps(first)


def test_ties_are_broken_boundary_compare_first():
    loc = [row(n, susp=0.5, fail=2, passed=1) for n in range(1, 10)]
    rep = report(frame(7))
    got = rank(rep, loc, {SRC: FUNC_SOURCE}, TEST)
    assert got[0]['line'] == 5 and 'compare' in got[0]['reasons']
    assert 1 not in lines_of(got[:3]) and 7 not in lines_of(got[:3])
    # baseline: susp, then in-stack first -> the raise line wins
    baseline = sorted(loc, key=lambda r: (-r['susp'], 0 if r['line'] == 7 else 1, r['line']))
    assert baseline[0]['line'] == 7


def test_limit_and_empty_inputs():
    loc = [row(n) for n in range(1, 9)]
    assert len(rank(EMPTY, loc, {SRC: FUNC_SOURCE}, limit=3)) == 3
    assert len(rank(EMPTY, loc, {SRC: FUNC_SOURCE})) == 5
    assert rank(EMPTY, loc, {SRC: FUNC_SOURCE}, limit=0) == []
    assert rank(EMPTY, loc, {SRC: FUNC_SOURCE}, limit=-1) == []
    assert rank(EMPTY, [], {SRC: FUNC_SOURCE}) == []
    assert rank(report(), [], {}) == []


@pytest.mark.parametrize('bad', [None, 3, 'x', [1], {'failures': 5}])
def test_garbage_inputs_do_not_raise(bad):
    assert rank(bad, bad, bad) == []


def test_no_sources_still_ranks_by_susp_fail_only_and_stack():
    loc = [row(1, susp=0.2, fail=1, passed=0), row(2, susp=0.9, fail=1, passed=1),
           row(3, susp=0.9, fail=1, passed=0), row(4, susp=0.9, fail=1, passed=1)]
    got = rank(report(frame(4)), loc, {}, TEST)
    # line 3 gets fail_only; line 4 is in the stack and wins the tie with line 2
    assert lines_of(got) == [3, 4, 2, 1]
    assert all(c['snippet'] == [] and c['probe'] == [] for c in got)
    assert got[0]['reasons'] == ['susp=1.000', 'fail_only']
    assert got[1]['reasons'] == ['susp=1.000', 'in_stack']
    assert got[0]['score'] == 1.3


def test_syntax_error_source_is_treated_as_missing():
    broken = 'def f(:\n    x = 1\n'
    loc = [row(2), row(1, susp=0.1)]
    got = rank(EMPTY, loc, {SRC: broken}, TEST)
    assert lines_of(got) == [2, 1]
    assert all(c['snippet'] == [] for c in got)
    assert rank(EMPTY, loc, {SRC: None}, TEST)[0]['snippet'] == []


def test_snippet_edges_and_middle():
    text = '\n'.join('x%d = %d' % (n, n) for n in range(1, 11)) + '\n'
    got = {c['line']: c for c in rank(EMPTY, [row(n) for n in (1, 5, 10)], {SRC: text}, limit=9)}
    assert [s['line'] for s in got[1]['snippet']] == [1, 2, 3]
    assert [s['line'] for s in got[5]['snippet']] == [3, 4, 5, 6, 7]
    assert [s['line'] for s in got[10]['snippet']] == [8, 9, 10]
    assert got[5]['snippet'][2] == {'line': 5, 'text': 'x5 = 5'}


def test_snippet_text_is_cleaned_and_truncated():
    text = 'x = 1\r\ny = "' + 'a' * 300 + '"\r\nz = 3\r\n'
    got = rank(EMPTY, [row(2)], {SRC: text})
    texts = [s['text'] for s in got[0]['snippet']]
    assert len(texts) == 3 and all(len(t) <= 160 for t in texts) and len(texts[1]) == 160
    assert texts[0] == 'x = 1' and texts[2] == 'z = 3'


def test_pool_loc_fail_lines_and_frames_merge():
    loc = [row(2, fail=1), row(3, fail=0, susp=0.9), row(4, fail=2)]
    got = rank(report(frame(4), frame(6), frame(2, file=TEST)), loc, {}, TEST, limit=9)
    assert sorted((c['file'], c['line']) for c in got) == [(SRC, 2), (SRC, 4), (SRC, 6)]
    assert [c['reasons'].count('in_stack') for c in got if c['line'] == 4] == [1]


def test_pool_all_fail_zero_uses_positive_susp():
    loc = [row(1, susp=0.0, fail=0), row(2, susp=0.4, fail=0), row(3, susp=0.8, fail=0)]
    assert lines_of(rank(EMPTY, loc, {}, TEST)) == [3, 2]


def test_pool_test_file_frames_only_as_last_resort():
    rep = report(frame(3, file=TEST), frame(4, file=TEST))
    assert lines_of(rank(rep, [], {}, TEST)) == [3, 4]
    assert lines_of(rank(report(frame(3, file=TEST), frame(9)), [], {}, TEST)) == [9]


def test_pool_drops_blank_comment_and_out_of_file_lines_with_source():
    text = 'a = 1\n\n# note\nb = 2\n'
    loc = [row(n) for n in (1, 2, 3, 4, 5, 99)]
    assert sorted(lines_of(rank(EMPTY, loc, {SRC: text}, limit=9))) == [1, 4]
    assert sorted(lines_of(rank(EMPTY, loc, {}, limit=9))) == [1, 2, 3, 4, 5, 99]


def test_susp_is_normalised_over_the_pool():
    got = rank(report(frame(9)), [row(1, susp=4.0), row(2, susp=2.0)], {})
    by_line = {c['line']: c for c in got}
    assert by_line[1]['reasons'][0] == 'susp=1.000'
    assert by_line[2]['reasons'][0] == 'susp=0.500'
    assert by_line[9]['reasons'][0] == 'susp=0.000'


SHAPES = [
    ('def f(a):\n    pass\n', 1, 'structural'),
    ('def f(a):\n    pass\n', 2, 'structural'),
    ('import os\n', 1, 'structural'),
    ('def f():\n    """doc"""\n    return 1\n', 2, 'structural'),
    ('@dec\ndef f():\n    return 1\n', 1, 'structural'),
    ('try:\n    a = 1\nfinally:\n    b = 2\n', 1, 'structural'),
    ('try:\n    a = 1\nfinally:\n    b = 2\n', 3, 'structural'),
    ('if a:\n    b = 1\nelse:\n    b = 2\n', 3, 'structural'),
    ('def f():\n    raise ValueError(1)\n', 2, 'structural'),
    ('if n <= 0:\n    x = 1\n', 1, 'compare'),
    ('if n == 0:\n    x = 1\n', 1, 'compare'),
    ('if n == m:\n    x = 1\n', 1, 'compare_other'),
    ('if n in m:\n    x = 1\n', 1, 'compare_other'),
    ('y = n - 1\n', 1, 'arith'),
    ('total += x\n', 1, 'arith'),
    ('y = xs[1:]\n', 1, 'slice'),
    ('y = xs[i - 1]\n', 1, 'slice'),
    ('y = (a and b)\n', 1, 'boolop'),
    ('y = not a\n', 1, 'boolop'),
    ('y = [a, b]\n', 1, 'value_stmt'),
    ('def f():\n    return None\n', 2, 'value_stmt'),
]


@pytest.mark.parametrize('text,line,label', SHAPES)
def test_shape_feature_labels(text, line, label):
    loc = [row(line)]
    got = raw_only(rank(EMPTY, loc, {SRC: text}, limit=50), EMPTY, loc)
    assert label in got[0]['reasons']


@pytest.mark.parametrize('text,line', [
    ('print(xs[i])\n', 1), ('y = a + b\n', 1), ('y = f(x)\n', 1), ('y = a\n', 1), ('y = n - 9\n', 1)])
def test_plain_lines_get_no_shape_label(text, line):
    assert rank(EMPTY, [row(line)], {SRC: text})[0]['reasons'] == ['susp=1.000']


def test_shape_scores_use_weights_and_cap():
    cases = {'if n <= 0:\n    x = 1\n': 1.5, 'if n == m:\n    x = 1\n': 1.25,
             'def f():\n    pass\n': 0.0,
             'y = xs[i - 1] + 1 if (a and b) else [n - 1]\n': 1.8}
    for text, expected in cases.items():
        assert rank(EMPTY, [row(1)], {SRC: text})[0]['score'] == expected, text


def test_shape_uses_the_line_not_the_whole_statement():
    text = 'if n <= 0:\n    x = 1\n    y = 2\n'
    got = {c['line']: c for c in rank(EMPTY, [row(1), row(3)], {SRC: text})}
    assert 'compare' in got[1]['reasons'] and 'compare' not in got[3]['reasons']


def test_tie_break_distance_to_innermost_frame_then_position(monkeypatch):
    # the frame-relative and flow features legitimately split these lines; switch them off so
    # that the scores really tie and only the tie-break rule is under test
    for key in ('flow', 'near', 'at_frame', 'after_frame', 'guard'):
        monkeypatch.setitem(WEIGHTS, key, 0.0)
    text = 'def f():\n' + ''.join('    v%d = g%d\n' % (n, n) for n in range(2, 8)) + '\ndef g():\n    k = h\n'
    loc = [row(n, susp=1.0) for n in (2, 3, 4, 5, 10)]
    rep = report(frame(4))
    full = rank(rep, loc, {SRC: text}, TEST, limit=50)
    got = raw_only(full, rep, loc)
    # all five tie on score, so the order below comes from the tie-break rule alone
    assert len({c['score'] for c in got}) == 1
    # line 4 is in the stack; then nearest lines; line 10 (other function) is last
    assert lines_of(got) == [4, 3, 5, 2, 10]
    assert 9 not in lines_of(full)


def test_tie_break_file_and_line_order_without_frame():
    loc = [row(5, file='b.py'), row(7, file='a.py'), row(3, file='b.py')]
    got = rank(EMPTY, loc, {})
    assert [(c['file'], c['line']) for c in got] == [('a.py', 7), ('b.py', 3), ('b.py', 5)]


def test_probes_argument_is_accepted_and_ignored_for_now():
    got = rank(EMPTY, [row(1)], {}, probes=[{'at': 'm.py:1', 'expr': 'x', 'value': '1'}])
    assert got[0]['probe'] == []


@pytest.mark.parametrize('scores,expected', [
    ([1.000, 0.950], True), ([1.000, 0.949], False), ([1.000, 0.700, 0.951], True),
    ([1.000], False), ([], False)])
def test_needs_probe_threshold_and_precision(scores, expected):
    assert needs_probe([{'score': s} for s in scores]) is expected


def test_needs_probe_reads_threshold_each_call(monkeypatch):
    monkeypatch.setitem(WEIGHTS, 'probe_gap', 0.0)
    assert needs_probe([{'score': 1.0}, {'score': 0.999}]) is False
    assert needs_probe([{'score': 1.0}, {'score': 1.0}]) is True


def test_needs_probe_tolerates_bad_candidates():
    assert needs_probe([{'score': 1.0}, {}]) is False
    assert needs_probe([{}, {}]) is True
    assert needs_probe(None) is False
    assert needs_probe([{'score': 1.0}, 'x']) is False


def test_generality_of_rank_source():
    text = RANK_PY.read_text(encoding='utf-8')
    assert ('tr' + 'uth') not in text.lower()
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(a.name in ('ast', 'math', 're') for a in node.names)
        if isinstance(node, ast.ImportFrom):
            assert node.module == 'planbot.diag.parse'
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert '.py' not in node.value and '/' not in node.value
    weights_node = next(n for n in tree.body if isinstance(n, ast.Assign)
                        and getattr(n.targets[0], 'id', '') == 'WEIGHTS')
    inside = {id(n) for n in ast.walk(weights_node)}
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and node.value == 0.05 and type(node.value) is float:
            assert id(node) in inside


def test_weights_initial_values():
    expected = {'susp': 1.0, 'fail_only': 0.3, 'structural': -1.0, 'compare': 0.5, 'arith': 0.4,
                'slice': 0.4, 'boolop': 0.3, 'value_stmt': 0.2, 'shape_cap': 0.8, 'exc': 0.5,
                'flow': 0.4, 'msg_name': 0.2, 'near': 0.3, 'at_frame': 0.15, 'after_frame': -0.3,
                'guard': 0.3, 'ret_on_path': 0.2, 'probe_diff': 0.2, 'probe_gap': 0.05}
    for key, value in expected.items():
        assert WEIGHTS[key] == value
    assert WEIGHTS['probe'] == 0.4


# ---------------------------------------------------------------------------
# features (4)-(7): exception affinity, data flow, frame position, probe values
# ---------------------------------------------------------------------------

def failing(exc, message='', frames=(), assert_line=None, test='test_x'):
    return {'unrunnable': False, 'location': None, 'failures': [
        {'test': test, 'exc_type': exc, 'message': message, 'frames': list(frames),
         'assert_line': assert_line}]}


EXC_SOURCE = '\n'.join([
    'def f(xs, i, d):',                  # 1
    '    n = len(xs)',                   # 2
    '    a = xs[i]',                     # 3
    '    b = d / n',                     # 4
    '    c = None',                      # 5
    '    e = int(a)',                    # 6
    '    w = xs.append(a)',              # 7
    '    t = "x".join(xs)',              # 8
    '    return a',                      # 9
]) + '\n'


@pytest.mark.parametrize('exc,message,hit_lines,label', [
    ('IndexError', 'list index out of range', {2, 3}, 'exc~subscript'),
    ('builtins.KeyError', "'k'", {2, 3}, 'exc~subscript'),
    ('ZeroDivisionError', 'division by zero', {4}, 'exc~div'),
    ('TypeError', "'NoneType' object is not subscriptable", {5, 7, 8}, 'exc~none'),
    ('AttributeError', 'x', {5, 7, 8}, 'exc~none'),
    ('ValueError', 'bad', {6}, 'exc~value'),
    ('AssertionError', 'assert 5 == 4', set(), 'exc~boundary'),
    ('AssertionError', 'assert True == False', set(), 'exc~bool'),
    ('AssertionError', 'assert [1, 2] == [1]', {3, 7}, 'exc~seq'),
    ('AssertionError', "assert 'ab' == 'abc'", {8}, 'exc~str'),
])
def test_exception_affinity_labels(exc, message, hit_lines, label):
    loc = [row(n, susp=0.5) for n in range(2, 10)]
    got = rank(failing(exc, message), loc, {SRC: EXC_SOURCE}, TEST, limit=20)
    hits = {c['line'] for c in got if label in c['reasons']}
    assert hits == hit_lines


def test_assertion_affinity_depends_on_value_types_not_text():
    loc = [row(n, susp=0.5) for n in range(2, 10)]
    src = {SRC: EXC_SOURCE}
    for exc, message in (('AssertionError', 'assert 500 == 4'), ('AssertionError', 'assert x'),
                         ('CustomError', 'assert 5 == 4')):
        got = rank(failing(exc, message), loc, src, TEST, limit=20)
        assert not any(r.startswith('exc~') for c in got for r in c['reasons'])


def test_exception_affinity_weight_and_no_failures():
    src = 'xs = [1]\ny = xs[i + 1]\n'
    plain = rank(failing('KeyError'), [row(2)], {SRC: src}, TEST)[0]
    assert 'exc~subscript' in plain['reasons']
    assert plain['score'] == 1.0 + WEIGHTS['shape_cap'] + WEIGHTS['exc']
    assert rank(EMPTY, [row(2)], {SRC: src}, TEST)[0]['score'] == 1.8


def test_boundary_affinity_hits_boundary_shapes():
    loc = [row(n, susp=0.5) for n in range(1, 9)]
    got = rank(failing('AssertionError', 'assert 5 == 4'), loc, {SRC: FUNC_SOURCE}, TEST, limit=9)
    assert {c['line'] for c in got if 'exc~boundary' in c['reasons']} == {5}
    got = rank(failing('AssertionError', 'assert 5 == 400'), loc, {SRC: FUNC_SOURCE}, TEST, limit=9)
    assert not any('exc~boundary' in c['reasons'] for c in got)


FLOW_SOURCE = '\n'.join([
    'def top(x):',                      # 1
    '    y = helper(x)',                # 2
    '    return y',                     # 3
    '',                                 # 4
    'def helper(x):',                   # 5
    '    z = deep(x)',                  # 6
    '    return z',                     # 7
    '',                                 # 8
    'def deep(x):',                     # 9
    '    q = leaf(x)',                  # 10
    '    return q',                     # 11
    '',                                 # 12
    'def leaf(x):',                     # 13
    '    return x',                     # 14
    '',                                 # 15
    'def unrelated(x):',                # 16
    '    return x',                     # 17
]) + '\n'
FLOW_TEST = '\n'.join([
    'def test_x():',                    # 1
    '    r = top(3)',                   # 2
    '    assert r == 4',                # 3
]) + '\n'
ASSERT_TOP = {'file': TEST, 'line': 3, 'func': 'test_x', 'code': 'assert top(3) == 4'}


def test_flow_follows_calls_from_the_test_down_two_layers():
    loc = [row(n, susp=0.5) for n in (3, 7, 11, 14, 17)]
    rep = failing('AssertionError', 'assert 3 == 4', frames=[frame(3, file=TEST)],
                  assert_line=ASSERT_TOP)
    got = raw_only(rank(rep, loc, {SRC: FLOW_SOURCE, TEST: FLOW_TEST}, TEST, limit=50), rep, loc)
    # the test calls top (layer 0); two more layers down are helper and deep, not leaf
    assert {c['line'] for c in got if 'flow' in c['reasons']} == {3, 7, 11}
    # no assertion code and no test source: only the stack gives flow
    bare_rep = failing('AssertionError', 'assert 3 == 4', frames=[frame(3)])
    bare = raw_only(rank(bare_rep, loc, {SRC: FLOW_SOURCE}, TEST, limit=50), bare_rep, loc)
    assert {c['line'] for c in bare if 'flow' in c['reasons']} == {3}


def test_flow_follows_the_test_body_when_the_assertion_code_is_missing():
    rep = failing('AssertionError', 'assert 3 == 4', frames=[frame(3, file=TEST)])
    loc = [row(3), row(17)]
    got = raw_only(rank(rep, loc, {SRC: FLOW_SOURCE, TEST: FLOW_TEST}, TEST, limit=50), rep, loc)
    assert {c['line'] for c in got if 'flow' in c['reasons']} == {3}


def test_flow_uses_the_stack_function_and_msg_name():
    src = 'def f(n):\n    count = n\n    return count\n\ndef g(n):\n    count = n\n'
    rep = failing('ValueError', 'bad count', frames=[frame(3)])
    got = rank(rep, [row(2), row(3), row(6)], {SRC: src}, TEST, limit=9)
    by = {c['line']: c['reasons'] for c in got}
    assert 'flow' in by[2] and 'flow' in by[3] and 'flow' not in by[6]
    assert all('msg_name' in by[n] for n in (2, 3, 6))
    names = rank(failing('ValueError', 'bad index of range', frames=[frame(3)]), [row(2)],
                 {SRC: src}, TEST)
    assert 'msg_name' not in names[0]['reasons']          # builtin names do not count


def test_msg_name_also_reads_the_assertion_code():
    src = 'def f(a):\n    offset = a\n    other = a\n'
    rep = failing('AssertionError', 'assert 1 == 2', frames=[frame(3)],
                  assert_line={'file': TEST, 'line': 1, 'func': 't', 'code': 'assert total == offset'})
    by = {c['line']: c['reasons'] for c in rank(rep, [row(2), row(3)], {SRC: src}, TEST)}
    assert 'msg_name' in by[2] and 'msg_name' not in by[3]


POS_SOURCE = '\n'.join([
    'def f(items, n):',                 # 1
    '    out = []',                     # 2
    '    for k in items:',              # 3
    '        out.append(k)',            # 4
    '        if k > n:',                # 5
    '            raise ValueError(k)',  # 6
    '        out.append(0)',            # 7
    '    return out',                   # 8
    '',                                 # 9
    'def g():',                         # 10
    '    return 1',                     # 11
]) + '\n'


def test_position_relative_to_the_innermost_frame():
    loc = [row(n) for n in (2, 4, 5, 6, 7, 8, 11)]
    got = rank(failing('ValueError', 'm', frames=[frame(6)]), loc, {SRC: POS_SOURCE}, TEST, limit=9)
    by = {c['line']: c['reasons'] for c in got}
    assert 'near_frame:-1' in by[5] and 'near_frame:-2' in by[4] and 'near_frame:-4' in by[2]
    assert 'at_frame' in by[6]
    assert 'after_frame' not in by[7]                      # inside the loop around the frame
    assert 'after_frame' in by[8]                          # after the loop
    assert not any(r.startswith(('near', 'at_', 'after')) for r in by[11])
    assert 'guard' in by[5] and 'guard' not in by[4]


def test_position_scores_follow_the_formulas():
    src = 'a = z\nb = z\nc = z\nd = z\n'
    got = rank(failing('X', frames=[frame(3)]), [row(1), row(3), row(4)], {SRC: src}, TEST, limit=9)
    by = {c['line']: c for c in got}
    assert 'near_frame:-2' in by[1]['reasons']
    assert by[1]['score'] == round(1.0 + 0.3 / (1 + 2 / 5), 3)
    assert by[3]['score'] == 1.15
    assert by[4]['score'] == 0.7


def test_return_on_path_without_a_source_frame():
    rep = failing('AssertionError', 'assert 3 == 4', frames=[frame(3, file=TEST)],
                  assert_line=ASSERT_TOP)
    loc = [row(3, fail=2), row(11, fail=2), row(14, fail=2), row(2, fail=2),
           row(7, fail=0, susp=0.5)]
    got = rank(rep, loc, {SRC: FLOW_SOURCE, TEST: FLOW_TEST}, TEST, limit=9)
    by = {c['line']: c['reasons'] for c in got}
    assert 'ret_on_path' in by[3] and 'ret_on_path' in by[11]
    assert 'ret_on_path' not in by[14] and 'ret_on_path' not in by[2]   # too deep / not a return
    assert 7 not in by                                                   # not a failing line
    assert not any(r.startswith(('near', 'at_', 'after')) for r in by[11])


def test_boundary_compare_first_with_a_report_and_symptoms_demoted():
    loc = [row(n, susp=0.5, fail=2, passed=1) for n in range(1, 10)]
    got = rank(failing('ValueError', 'bad n', frames=[frame(7)]), loc, {SRC: FUNC_SOURCE}, TEST)
    assert got[0]['line'] == 5
    assert 1 not in lines_of(got[:3]) and 7 not in lines_of(got[:3])


PROBE_SOURCE = 'def f(a, b):\n    x = a\n    y = b\n    return x\n'
ASSERT_REP = failing('AssertionError', 'assert 5 == 3')


def probe_value(at, expr, value, outcome=None):
    return {'at': at, 'expr': expr, 'value': value, 'test': None, 'outcome': outcome}


def test_probe_value_equal_to_actual_breaks_a_tie():
    loc = [row(2), row(3)]
    plain = raw_only(rank(ASSERT_REP, loc, {SRC: PROBE_SOURCE}, TEST, limit=50), ASSERT_REP, loc)
    assert plain[0]['score'] == plain[1]['score'] and lines_of(plain) == [2, 3]
    probes = [probe_value('m.py:3', 'b', '5'), probe_value('m.py:3', 'len(b)', '2')]
    got = raw_only(rank(ASSERT_REP, loc, {SRC: PROBE_SOURCE}, TEST, probes=probes, limit=50),
                   ASSERT_REP, loc)
    assert lines_of(got) == [3, 2]
    assert 'probe' in got[0]['reasons'] and 'probe' not in got[1]['reasons']
    assert got[0]['probe'] == [{'expr': 'b', 'value': '5'}, {'expr': 'len(b)', 'value': '2'}]
    assert got[1]['probe'] == []
    assert round(got[0]['score'] - plain[1]['score'], 3) == WEIGHTS['probe']


def test_probe_value_not_equal_to_actual_gets_no_bonus_but_is_listed():
    loc = [row(2), row(3)]
    got = raw_only(rank(ASSERT_REP, loc, {SRC: PROBE_SOURCE}, TEST,
                        probes=[probe_value('m.py:3', 'b', '9')], limit=50), ASSERT_REP, loc)
    assert lines_of(got) == [2, 3]
    assert got[1]['probe'] == [{'expr': 'b', 'value': '9'}] and 'probe' not in got[1]['reasons']


def test_probe_none_counts_for_type_class_exceptions():
    probes = [probe_value('m.py:3', 'b', 'None')]
    loc = [row(2), row(3)]
    got = rank(failing('AttributeError', 'no attribute'), loc, {SRC: PROBE_SOURCE}, TEST,
               probes=probes)
    assert 'probe' in next(c for c in got if c['line'] == 3)['reasons']
    other = rank(failing('ValueError', 'bad'), loc, {SRC: PROBE_SOURCE}, TEST, probes=probes)
    assert not any('probe' in c['reasons'] for c in other)


def test_probe_diff_between_failing_and_passing_runs():
    probes = [probe_value('m.py:3', 'b', '5', 'fail'), probe_value('m.py:3', 'b', '1', 'pass')]
    loc = [row(2), row(3)]
    base = rank(ASSERT_REP, loc, {SRC: PROBE_SOURCE}, TEST)[1]['score']
    got = rank(ASSERT_REP, loc, {SRC: PROBE_SOURCE}, TEST, probes=probes)
    assert got[0]['line'] == 3 and got[0]['reasons'][-2:] == ['probe', 'probe_diff']
    assert got[0]['score'] == round(base + WEIGHTS['probe'] + WEIGHTS['probe_diff'], 3)
    assert round(WEIGHTS['probe'] + WEIGHTS['probe_diff'], 3) <= WEIGHTS['probe_cap']
    same = [probes[0], probe_value('m.py:3', 'b', '5', 'pass')]
    again = rank(ASSERT_REP, loc, {SRC: PROBE_SOURCE}, TEST, probes=same)
    assert 'probe_diff' not in again[0]['reasons']


def test_probe_score_is_capped(monkeypatch):
    monkeypatch.setitem(WEIGHTS, 'probe_cap', 0.5)
    probes = [probe_value('m.py:3', 'b', '5', 'fail'), probe_value('m.py:3', 'b', '1', 'pass')]
    base = rank(ASSERT_REP, [row(3)], {SRC: PROBE_SOURCE}, TEST)[0]['score']
    got = rank(ASSERT_REP, [row(3)], {SRC: PROBE_SOURCE}, TEST, probes=probes)
    assert got[0]['score'] == round(base + 0.5, 3)


def test_probes_that_match_no_candidate_change_nothing():
    loc = [row(2), row(3)]
    junk = [probe_value('m.py:99', 'b', '5'), probe_value('other.py:3', 'b', '5', 'fail'),
            {'at': 'm.py:3 ', 'expr': 'b', 'value': '5'}, 'junk', {'at': 3}]
    plain = rank(ASSERT_REP, loc, {SRC: PROBE_SOURCE}, TEST)
    got = rank(ASSERT_REP, loc, {SRC: PROBE_SOURCE}, TEST, probes=junk)
    assert json.dumps(got) == json.dumps(plain)
    assert all(c['probe'] == [] for c in plain)


def test_probes_are_deterministic():
    probes = [probe_value('m.py:3', 'b', '5', 'fail'), probe_value('m.py:3', 'b', '1', 'pass')]
    first = rank(ASSERT_REP, [row(2), row(3)], {SRC: PROBE_SOURCE}, TEST, probes=probes)
    second = rank(ASSERT_REP, [row(3), row(2)], {SRC: PROBE_SOURCE}, TEST, probes=list(probes))
    assert json.dumps(first) == json.dumps(second)


def test_frames_only_input_and_garbage_probes_do_not_raise():
    rep = failing('IndexError', 'x', frames=[frame(3), frame(4)])
    got = raw_only(rank(rep, [], {SRC: PROBE_SOURCE}, TEST, probes='nope', limit=50), rep, [])
    assert sorted(lines_of(got)) == [3, 4]
    assert rank(failing('IndexError', frames=[{'file': 1}]), [], {}, TEST, probes=[None]) == []


# ---------------------------------------------------------------------------
# probe_plan and the generality self-check of the literals in rank.py
# ---------------------------------------------------------------------------

PLAN_SOURCE = 'def f(items, i, offset):\n    total = items[i] + offset.value\n    return len(total)\n'


def cand(line):
    return {'file': SRC, 'line': line, 'score': 0.0}


def plan(rep=EMPTY, cands=(), sources=None):
    return rank_mod.probe_plan(rep, list(cands), {SRC: PLAN_SOURCE} if sources is None else sources, TEST)


def test_probe_plan_at_takes_first_eight_candidates_deduped():
    assert plan(cands=[cand(n) for n in range(1, 11)])['at'] == ['m.py:%d' % n for n in range(1, 9)]
    assert plan(cands=[cand(2), cand(2), cand(1)])['at'] == ['m.py:2', 'm.py:1']


def test_probe_plan_at_uses_frames_non_test_first_innermost_first():
    rep = report(frame(1), frame(2, file=TEST), frame(3), frame(4, file=TEST))
    assert plan(rep)['at'] == ['m.py:3', 'm.py:1', 't_m.py:4', 't_m.py:2']
    assert plan(rep, [cand(2)])['at'] == ['m.py:2']


def test_probe_plan_exprs_from_a_subscript_and_attribute_line():
    got = plan(cands=[cand(2)])['exprs']
    assert {'items', 'offset.value', 'len(items)'} <= set(got)
    assert 'items[i]' not in got and 'len' not in got
    assert plan(cands=[cand(3)])['exprs'] == ['total']


def test_probe_plan_exprs_are_capped_safe_and_skip_keywords_and_callees():
    src = 'def f():\n    a = [x for x in b if c.d(e)] + g[0] + h[1] + k + l + m + n\n'
    got = plan(cands=[cand(2)], sources={SRC: src})['exprs']
    assert len(got) == 8 and all(rank_mod.safe_expr(e) for e in got)
    assert 'c.d' not in got and 'if' not in got
    assert plan(cands=[cand(1)], sources={SRC: 'for x in items:\n    pass\n'})['exprs'] == [
        'x', 'items', 'len(items)']


def test_probe_plan_without_source_or_with_syntax_error_and_determinism():
    assert plan(cands=[cand(2)], sources={}) == {'at': ['m.py:2'], 'exprs': []}
    assert plan(cands=[cand(2)], sources={SRC: 'def (:'})['exprs'] == []
    assert plan(cands=[cand(2)]) == plan(cands=[cand(2)])
    assert rank_mod.probe_plan(None, None, None) == {'at': [], 'exprs': []}


def test_rank_source_has_no_business_literals():
    import builtins
    import keyword
    tree = ast.parse(RANK_PY.read_text(encoding='utf-8'))
    weights = next(n for n in tree.body if isinstance(n, ast.Assign) and n.targets[0].id == 'WEIGHTS')
    inside = {id(n) for n in ast.walk(weights)}
    docs = {id(n.body[0].value) for n in ast.walk(tree) if isinstance(
        n, (ast.Module, ast.FunctionDef, ast.ClassDef)) and n.body and isinstance(n.body[0], ast.Expr)}
    labels = {'in_stack', 'compare_other', 'subscript', 'div', 'none', 'value', 'boundary', 'bool',
              'seq', 'str'}
    fields = {'file', 'line', 'score', 'reasons', 'snippet', 'text', 'expr', 'outcome', 'frames',
              'message', 'exc_type', 'failures', 'assert_line', 'code', 'test', 'susp', 'fail',
              'passed', 'pass', 'at', 'func', 'src', 'row', 'frame', 'ids', 'actual', 'type_class',
              'any_passed', 'exc_kind', 'flow_funcs', 'called_funcs', 'same_func', 'probe_items',
              'exprs'}
    allowed = (set(WEIGHTS) | labels | fields | set(dir(ast)) | set(dir(builtins)) | set(dir(str))
               | set(dir(list)) | set(keyword.kwlist)
               | {f for c in vars(ast).values() if isinstance(c, type) for f in getattr(c, '_fields', ())})
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or id(node) in docs:
            continue
        if isinstance(node.value, str) and node.value.isidentifier():
            assert node.value in allowed, node.value
        if type(node.value) is float and id(node) not in inside:
            assert node.value in (0.0, 1.0), node.value
