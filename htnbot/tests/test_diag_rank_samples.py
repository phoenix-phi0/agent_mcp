"""sample_plan (where the session takes pass/fail samples) and rank's sample ordering."""
import json

import pytest

from planbot.diag.parse import safe_expr
from planbot.diag.rank import WEIGHTS, rank, sample_plan

MOD = '''\
def f(a, b):
    c = a + b
    d = len(c) + b
    e = g(a)
    h = c[0]
    i = d
    j = e
    return j


def g(z):
    return z
'''
SOURCES = {'m.py': MOD, 't.py': 'import m\nassert m.f(1, 2)\n'}
TEST_FILE = 't.py'


def row(file, line, susp=0.5, fail=1, passed=0):
    return {'file': file, 'line': line, 'susp': susp, 'fail': fail, 'passed': passed}


def frame(file, line):
    return {'file': file, 'line': line, 'func': 'x', 'code': ''}


def report(*frames):
    failure = {'test': 'T.test_a', 'exc_type': 'AssertionError', 'message': 'x',
               'frames': list(frames), 'assert_line': None}
    return {'unrunnable': False, 'location': None, 'failures': [failure]}


def test_loc_order_then_innermost_frame_then_candidates():
    loc = [row('m.py', 2), row('t.py', 2), row('m.py', 3), row('m.py', 4),
           row('m.py', 5), row('m.py', 6), row('m.py', 7)]
    cands = [{'file': 'm.py', 'line': 2}, {'file': 'm.py', 'line': 11},
             {'file': 'm.py', 'line': 12}, {'file': 'm.py', 'line': 1}]
    rep = report(frame('t.py', 2), frame('m.py', 8))
    plan = sample_plan(rep, loc, cands, SOURCES, TEST_FILE)
    assert plan['at'] == ['m.py:2', 'm.py:3', 'm.py:4', 'm.py:5', 'm.py:6', 'm.py:8',
                          'm.py:11', 'm.py:12']
    assert len(set(plan['at'])) == len(plan['at'])
    exprs = plan['exprs']
    assert exprs == ['c', 'a', 'b', 'd', 'e', 'g', 'h', 'i']
    assert len(exprs) <= 8 and all(safe_expr(e) for e in exprs)
    assert 'len' not in exprs and 'g' in exprs        # builtin dropped, called name kept
    assert 'z' not in exprs                           # filler lines give no expressions


def test_result_depends_on_loc_order():
    loc = [row('m.py', n) for n in range(2, 9)]
    forward = sample_plan(report(), loc, [], SOURCES, TEST_FILE)
    backward = sample_plan(report(), loc[::-1], [], SOURCES, TEST_FILE)
    assert forward['at'] == ['m.py:%d' % n for n in range(2, 7)]
    assert backward['at'] == ['m.py:%d' % n for n in range(8, 3, -1)]
    assert sample_plan(report(), loc, [], SOURCES, TEST_FILE) == forward


def test_invalid_loc_rows_only_frame_and_candidates():
    loc = [row('m.py', 2, susp=0.0, fail=0), row('m.py', 3, susp=0.0, fail=0)]
    cands = [{'file': 'm.py', 'line': 11}, {'file': 'm.py', 'line': 4}]
    plan = sample_plan(report(frame('m.py', 5)), loc, cands, SOURCES, TEST_FILE)
    assert plan['at'] == ['m.py:5', 'm.py:11', 'm.py:4']
    assert plan['exprs'] == ['h', 'c']


def test_susp_alone_makes_a_row_valid():
    plan = sample_plan(report(), [row('m.py', 4, susp=0.2, fail=0)], [], SOURCES, TEST_FILE)
    assert plan['at'] == ['m.py:4']


def test_innermost_frame_may_be_in_the_test_file_and_needs_sources():
    plan = sample_plan(report(frame('m.py', 2), frame('t.py', 2)), [], [], SOURCES, TEST_FILE)
    assert plan['at'] == ['t.py:2']
    assert plan['exprs'] == ['m']
    # innermost frame whose file has no source is skipped for the next one out
    plan = sample_plan(report(frame('m.py', 2), frame('x.py', 9)), [], [], SOURCES, TEST_FILE)
    assert plan == {'at': ['m.py:2'], 'exprs': ['c', 'a', 'b']}
    assert sample_plan(report(frame('x.py', 9)), [], [], SOURCES, TEST_FILE) == {'at': [], 'exprs': []}


def test_lines_without_source_give_no_expressions():
    plan = sample_plan(report(), [row('other.py', 3)], [], SOURCES, TEST_FILE)
    assert plan == {'at': ['other.py:3'], 'exprs': []}
    broken = sample_plan(report(), [row('m.py', 2)], [], {'m.py': 'def ('}, TEST_FILE)
    assert broken == {'at': ['m.py:2'], 'exprs': []}


def test_empty_and_garbage_inputs_do_not_raise():
    assert sample_plan({}, [], [], {}) == {'at': [], 'exprs': []}
    assert sample_plan({'failures': []}, [], [], {}, '') == {'at': [], 'exprs': []}
    for bad in (None, 3, 'x', [None, 1], {'failures': 'x'}):
        out = sample_plan(bad, bad, bad, bad, bad)
        assert set(out) == {'at', 'exprs'}


# ---------------------------------------------------------------------------
# rank: sample ordering
# ---------------------------------------------------------------------------
PLAIN = '''\
def f(a, b):
    c = a
    d = b
    e = c
    g = d
    h = e
    i = g
    return h
'''
BRANCHY = '''\
def f(a, b):
    c = a
    if c > b:
        d = b
    return d
'''


def loc_row(line, susp, file='m.py'):
    return row(file, line, susp=susp, fail=2, passed=1)


def val(line, expr, value, outcome, file='m.py'):
    return {'at': '%s:%d' % (file, line), 'expr': expr, 'value': value,
            'test': None, 'outcome': outcome}


def run(src, loc, probes=None, frames=(), limit=50):
    return rank(report(*frames), loc, {'m.py': src}, 't.py', probes=probes, limit=limit)


def lines(result):
    return [c['line'] for c in result]


def four_rows():
    return [loc_row(2, 1.0), loc_row(3, 1.0), loc_row(4, 0.8), loc_row(5, 0.6)]


def test_differing_row_first_then_susp_order():
    probes = [val(5, 'x', '3', 'fail'), val(5, 'x', '2', 'pass'),
              val(2, 'x', '5', 'fail'), val(2, 'x', '5', 'pass')]
    assert lines(run(PLAIN, four_rows()))[:4] == [2, 3, 4, 5]
    assert lines(run(PLAIN, four_rows(), probes))[:4] == [5, 2, 3, 4]


@pytest.mark.parametrize('fails,passes,differs', [
    (('1', '2'), ('2',), False),
    (('1',), (), False),
    (('1',), ('2', '3'), True),
])
def test_diff_definition(fails, passes, differs):
    probes = [val(5, 'x', v, 'fail') for v in fails] + [val(5, 'x', v, 'pass') for v in passes]
    got = run(PLAIN, four_rows(), probes)
    assert (lines(got)[0] == 5) is differs
    if not differs:
        assert lines(got)[:4] == [2, 3, 4, 5]


def _score_of(got, line):
    return {c['line']: c['score'] for c in got}[line]


def _probe_diff_scores(fails, passes):
    """(score of row 5 with the given values, score of row 5 without the pass values)."""
    fail_vals = [val(5, 'x', v, 'fail') for v in fails]
    pass_vals = [val(5, 'x', v, 'pass') for v in passes]
    with_pass = _score_of(run(PLAIN, four_rows(), fail_vals + pass_vals), 5)
    without_pass = _score_of(run(PLAIN, four_rows(), fail_vals), 5)
    return with_pass, without_pass


def test_probe_diff_score_not_added_when_value_sets_intersect():
    # no failure in the report -> no actual value; values are not None either,
    # so only probe_diff could change the score
    with_pass, without_pass = _probe_diff_scores(('1', '2'), ('2',))
    assert with_pass == without_pass


def test_probe_diff_score_added_when_value_sets_are_disjoint():
    with_pass, without_pass = _probe_diff_scores(('1',), ('2', '3'))
    assert WEIGHTS['probe_diff'] > 0
    assert WEIGHTS['probe_diff'] <= WEIGHTS['probe_cap']
    assert round(with_pass - without_pass, 3) == round(WEIGHTS['probe_diff'], 3)


def test_probe_diff_score_not_added_without_pass_values():
    only_fail = _score_of(run(PLAIN, four_rows(), [val(5, 'x', '1', 'fail')]), 5)
    no_values = _score_of(run(PLAIN, four_rows()), 5)
    assert only_fail == no_values


def test_null_outcome_values_do_not_count_for_diff():
    probes = [val(5, 'x', '1', 'fail'), val(5, 'x', '2', None),
              val(3, 'x', '1', None), val(3, 'x', '2', None)]
    assert lines(run(PLAIN, four_rows(), probes))[:4] == [2, 3, 4, 5]


def test_susp_before_score_only_with_samples():
    loc = [loc_row(2, 0.9), loc_row(3, 0.7)]
    assert lines(run(BRANCHY, loc))[:2] == [3, 2]
    for probes in ([val(4, 'x', '1', 'fail')], [val(2, 'x', '1', 'pass')]):
        got = run(BRANCHY, loc, probes)
        assert lines(got)[:2] == [2, 3]
        by_line = {c['line']: c for c in got}
        assert by_line[3]['score'] > by_line[2]['score']   # score field stays the plain sum


def test_ties_score_then_stack_then_position(monkeypatch):
    # same susp, same diff state: higher score first, although its line is larger
    loc = [loc_row(2, 0.5), loc_row(3, 0.5)]
    got = run(BRANCHY, loc, [val(2, 'x', '1', 'fail')])
    assert lines(got)[:2] == [3, 2]
    # equal score: the row in the stack first, then nearer to the frame, then file/line
    for key in ('flow', 'near', 'at_frame', 'after_frame', 'guard'):
        monkeypatch.setitem(WEIGHTS, key, 0.0)
    loc = [loc_row(2, 1.0), loc_row(3, 1.0), loc_row(4, 1.0), loc_row(6, 1.0)]
    probes = [val(2, 'x', '1', 'fail')]
    got = run(PLAIN, loc, probes, frames=[frame('m.py', 6)])
    assert len({c['score'] for c in got[:4]}) == 1
    assert lines(got)[:4] == [6, 4, 3, 2]
    got = run(PLAIN, loc[::-1], probes)           # no frame: file, line ascending
    assert len({c['score'] for c in got[:4]}) == 1
    assert lines(got)[:4] == [2, 3, 4, 6]


def test_sample_ordering_is_deterministic_and_order_free():
    loc = four_rows()
    probes = [val(5, 'x', '3', 'fail'), val(5, 'x', '2', 'pass'),
              val(2, 'x', '5', 'fail'), val(2, 'x', '5', 'pass')]
    first = run(PLAIN, loc, probes)
    assert json.dumps(first) == json.dumps(run(PLAIN, loc, probes))

    def key(res):
        return [(c['file'], c['line'], c['score']) for c in res]
    assert lines(first)[:4] == [5, 2, 3, 4]
    assert key(run(PLAIN, loc[::-1], probes[::-1])) == key(first)
    assert key(run(PLAIN, loc[::-1], probes)) == key(first)
    assert key(run(PLAIN, loc, probes[::-1])) == key(first)


def test_unmatched_values_change_nothing():
    stray = [val(99, 'x', '3', 'fail'), val(99, 'x', '2', 'pass'),
             val(2, 'x', '3', 'fail', file='other.py'), val(2, 'x', '2', 'pass', file='other.py')]
    base = run(PLAIN, four_rows())
    assert run(PLAIN, four_rows(), stray) == base
    assert run(PLAIN, four_rows(), stray, limit=3) == base[:3]


def test_no_sample_forms_are_equivalent():
    loc = [loc_row(2, 0.9), loc_row(3, 0.7)]
    nulls = [val(2, 'x', '77', None), val(3, 'x', '88', None), val(4, 'x', '99', None)]
    seqs = [[(c['file'], c['line']) for c in run(BRANCHY, loc, p)] for p in (None, [], nulls)]
    assert seqs[0] == seqs[1] == seqs[2]
    assert [line for _, line in seqs[0]][:2] == [3, 2]


def test_empty_pool_and_nonpositive_limit():
    assert rank(report(), [], {'m.py': PLAIN}, 't.py', probes=[val(2, 'x', '1', 'fail')]) == []
    assert run(PLAIN, four_rows(), [val(5, 'x', '3', 'fail')], limit=0) == []


# ---------------------------------------------------------------------------
# self-check, probe_plan, needs_probe, sample_plan edges, sample ordering edges
# ---------------------------------------------------------------------------
import ast as _ast
from pathlib import Path as _Path

from planbot.diag import rank as _rank_mod
from planbot.diag.rank import needs_probe, probe_plan

_RANK_SRC = (_Path(_rank_mod.__file__)).read_text(encoding='utf-8')


def _weights_assign(top):
    if isinstance(top, _ast.Assign):
        targets = top.targets
    elif isinstance(top, _ast.AnnAssign):
        targets = [top.target]
    else:
        return False
    return any(isinstance(t, _ast.Name) and t.id == 'WEIGHTS' for t in targets)


def test_rank_source_is_generic():
    tree = _ast.parse(_RANK_SRC)
    assert 'truth' not in _RANK_SRC
    allowed = {'ast', 're', 'math', 'tokenize', 'planbot.diag.parse'}
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Import):
            assert all(a.name in allowed for a in node.names)
        if isinstance(node, _ast.ImportFrom):
            assert node.level == 0 and node.module in allowed
    outside = []
    for top in tree.body:
        if _weights_assign(top):
            continue
        outside += [n for n in _ast.walk(top)
                    if isinstance(n, _ast.Constant) and n.value == 0.05
                    and not isinstance(n.value, bool)]
    assert outside == []
    for node in _ast.walk(tree):
        if isinstance(node, _ast.BinOp) and isinstance(node.op, _ast.Add):
            both = all(isinstance(s, _ast.Constant) and isinstance(s.value, str)
                       for s in (node.left, node.right))
            assert not both


MANY = '\n'.join('v%d = a%d + 1' % (i, i) for i in range(1, 13)) + '\n'


def test_probe_plan_caps_orders_and_dedups_candidates():
    cands = [{'file': 'm.py', 'line': n} for n in (1, 2, 2, 3, 4, 5, 6, 7, 8, 9, 10, 1)]
    plan = probe_plan(report(), cands, {'m.py': MANY}, 't.py')
    order = ['m.py:%d' % n for n in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10)]
    assert len(plan['at']) <= 8 and len(set(plan['at'])) == len(plan['at'])
    assert plan['at'] == order[:len(plan['at'])]
    assert 0 < len(plan['exprs']) <= 8
    assert all(safe_expr(e) for e in plan['exprs'])
    assert len(set(plan['exprs'])) == len(plan['exprs'])


def test_probe_plan_line_without_source_gives_no_exprs():
    plan = probe_plan(report(), [{'file': 'x.py', 'line': 3}], {'m.py': MANY}, 't.py')
    assert plan == {'at': ['x.py:3'], 'exprs': []}


def _c(*scores):
    return [{'score': s} for s in scores]


def test_needs_probe_threshold_and_missing_scores():
    assert needs_probe([]) is False
    assert needs_probe(_c(1.0)) is False
    assert needs_probe(_c(1.0, 0.95)) is True      # gap exactly 0.05
    assert needs_probe(_c(1.0, 0.949)) is False    # gap 0.051
    assert needs_probe([{'score': 0.04}, {}]) is True   # missing score counts as 0.0
    assert needs_probe([{'score': 0.06}, {}]) is False


def test_needs_probe_reads_threshold_each_call(monkeypatch):
    cs = _c(1.0, 0.85)
    assert needs_probe(cs) is False
    monkeypatch.setitem(WEIGHTS, 'probe_gap', 0.2)
    assert needs_probe(cs) is True


def test_sample_plan_truncates_dedups_and_ignores_empty_test_file():
    loc = [row('m.py', 2), row('m.py', 2), row('t.py', 2)] + [row('m.py', n) for n in range(3, 9)]
    plan = sample_plan(report(), loc, [{'file': 'm.py', 'line': n} for n in range(9, 20)],
                       SOURCES, TEST_FILE)
    assert len(plan['at']) == 8 and len(set(plan['at'])) == 8
    assert 't.py:2' not in plan['at']
    plan = sample_plan(report(), loc, [], SOURCES, '')
    assert plan['at'][0] == 'm.py:2' and 't.py:2' in plan['at']
    assert len(plan['at']) == len(set(plan['at']))


def test_sample_plan_syntax_error_source_gives_no_exprs():
    plan = sample_plan(report(frame('m.py', 2)), [row('m.py', 2)], [], {'m.py': 'def ('}, '')
    assert plan['exprs'] == []
    assert plan['at'] == ['m.py:2']


def test_sample_plan_does_not_mutate_inputs():
    loc = [row('m.py', 2), row('t.py', 2), row('m.py', 3)]
    cands = [{'file': 'm.py', 'line': 4, 'score': 1.0, 'reasons': ['a']}]
    rep = report(frame('t.py', 2), frame('m.py', 5))
    before = json.dumps([loc, cands, rep])
    sample_plan(rep, loc, cands, SOURCES, TEST_FILE)
    assert json.dumps([loc, cands, rep]) == before


def test_all_null_outcomes_equal_no_samples():
    loc = [loc_row(2, 0.9), loc_row(3, 0.7)]
    nulls = [val(2, 'x', '1', None), val(3, 'x', '2', None)]
    def key(res):
        return [(c['file'], c['line'], c['score']) for c in res]
    assert key(run(BRANCHY, loc, nulls)) == key(run(BRANCHY, loc))


def test_expansion_only_rows_do_not_break_sample_ordering():
    loc = [loc_row(3, 0.7)]
    got = run(BRANCHY, loc, [val(3, 'x', '1', 'fail'), val(3, 'x', '2', 'pass')])
    assert lines(got)[0] == 3
    assert {2, 4, 5} <= set(lines(got))


# ---------------------------------------------------------------------------
# sample_plan: one innermost frame per failure, whole-line identifiers
# ---------------------------------------------------------------------------

def multi_report(*frames):
    """One failure per frame, each with a single (innermost) frame."""
    failures = [{'test': 'T.test_%d' % i, 'exc_type': 'AssertionError', 'message': 'x',
                 'frames': [fr], 'assert_line': None} for i, fr in enumerate(frames)]
    return {'unrunnable': False, 'location': None, 'failures': failures}


def test_each_failures_innermost_frame_joins_after_the_loc_rows():
    loc = [row('m.py', n) for n in range(2, 8)]
    rep = multi_report(frame('m.py', 8), frame('m.py', 11), frame('t.py', 2))
    plan = sample_plan(rep, loc, [{'file': 'm.py', 'line': 12}], SOURCES, TEST_FILE)
    assert plan['at'] == ['m.py:%d' % n for n in range(2, 7)] + ['m.py:8', 'm.py:11', 't.py:2']


def test_only_three_failure_frames_fit_after_five_loc_rows():
    loc = [row('m.py', n) for n in range(2, 7)]
    rep = multi_report(frame('m.py', 7), frame('m.py', 8), frame('m.py', 11),
                       frame('m.py', 12), frame('t.py', 2))
    plan = sample_plan(rep, loc, [], SOURCES, TEST_FILE)
    assert plan['at'] == ['m.py:2', 'm.py:3', 'm.py:4', 'm.py:5', 'm.py:6',
                          'm.py:7', 'm.py:8', 'm.py:11']


def test_failure_frames_dedup_and_skip_failures_without_sources():
    loc = [row('m.py', 2), row('m.py', 3)]
    rep = multi_report(frame('m.py', 2), frame('x.py', 4), frame('m.py', 8), frame('m.py', 8))
    plan = sample_plan(rep, loc, [], SOURCES, TEST_FILE)
    assert plan['at'] == ['m.py:2', 'm.py:3', 'm.py:8']


LINE_SRC = (
    "x = foo(a, key='word')\n"
    "class K:\n"
    "    def meth(self, p):\n"
    "        return self.q + p\n"
)


def test_exprs_are_every_identifier_of_the_whole_line():
    plan = sample_plan(report(), [row('s.py', 1)], [], {'s.py': LINE_SRC}, TEST_FILE)
    assert plan['exprs'] == ['x', 'foo', 'a', 'key', 'word']
    assert not {'if', 'return', 'len', 'print', 'None', 'True'} & set(plan['exprs'])


def test_exprs_drop_keywords_and_builtins_but_keep_attribute_roots():
    src = 'if not ok and len(v) > 0: print(None, True, obj.attr)\n'
    plan = sample_plan(report(), [row('s.py', 1)], [], {'s.py': src}, TEST_FILE)
    assert plan['exprs'] == ['ok', 'v', 'obj']


def test_exprs_drop_first_parameter_of_methods_only_when_parsable():
    plan = sample_plan(report(), [row('s.py', 4)], [], {'s.py': LINE_SRC}, TEST_FILE)
    assert plan['exprs'] == ['p']                       # first parameter dropped, .q is an attribute
    broken = LINE_SRC + 'def (\n'
    plan = sample_plan(report(), [row('s.py', 4)], [], {'s.py': broken}, TEST_FILE)
    assert plan['exprs'] == ['self', 'p']               # unparsable: nothing excluded
    plain = 'def fn(self):\n    return self\n'          # not a method: kept
    plan = sample_plan(report(), [row('s.py', 2)], [], {'s.py': plain}, TEST_FILE)
    assert plan['exprs'] == ['self']


def test_exprs_dedup_cap_and_filler_lines_give_none():
    src = '\n'.join('v%d = w%d' % (i, i) for i in range(1, 8)) + '\n'
    loc = [row('s.py', n) for n in range(1, 6)]
    plan = sample_plan(report(), loc, [{'file': 's.py', 'line': 7}], {'s.py': src}, TEST_FILE)
    assert plan['exprs'] == ['v1', 'w1', 'v2', 'w2', 'v3', 'w3', 'v4', 'w4']
    assert 's.py:7' in plan['at'] and 'v7' not in plan['exprs']


# ---------------------------------------------------------------------------
# sample_plan against the recorded fixture (only the recorded probe arguments and the
# test_report / locate outputs are read)
# ---------------------------------------------------------------------------
from pathlib import Path as _P

from planbot.diag.parse import norm_path as _norm, parse_locate as _parse_locate
from planbot.diag.parse import parse_report as _parse_report
from planbot.diag.replay import load_cases as _load_cases

_FIXTURE = _P(__file__).parent / 'fixtures' / 'diag_real.json'


def _recorded_probe_cases():
    raw = json.loads(_FIXTURE.read_text(encoding='utf-8'))['cases']
    probes = {c['test']: c['calls']['probe']['args'] for c in raw
              if isinstance(c.get('calls'), dict) and isinstance(c['calls'].get('probe'), dict)}
    return [(c, probes[c['id']]) for c in _load_cases(str(_FIXTURE)) if c['id'] in probes]


def _norm_file(item):
    out = dict(item)
    out['file'] = _norm(item['file']) or item['file']
    return out


def _fixture_plan(case):
    rep = _parse_report(case['outputs']['test_report'], case['test_file'])
    for failure in rep['failures']:
        failure['frames'] = [_norm_file(fr) for fr in failure['frames']]
    loc = [_norm_file(r) for r in _parse_locate(case['outputs']['locate'])]
    return sample_plan(rep, loc, [], case['sources'], case['test_file'])


def _norm_at(text):
    file, _, line = text.rpartition(':')
    return '%s:%s' % (_norm(file) or file, line)


_FIXTURE_CASES = _recorded_probe_cases()


def test_fixture_has_nine_recorded_probe_cases():
    # 10 failing cases; the one that cannot even be imported has no probe recording
    assert len(_FIXTURE_CASES) == 9


@pytest.mark.parametrize('case,probe', _FIXTURE_CASES, ids=[c['id'] for c, _ in _FIXTURE_CASES])
def test_sample_plan_covers_the_recorded_probe_arguments(case, probe):
    plan = _fixture_plan(case)
    at, recorded_at = {_norm_at(a) for a in plan['at']}, {_norm_at(a) for a in probe['at']}
    assert recorded_at <= at, 'missing at: %s (got %s)' % (sorted(recorded_at - at), plan['at'])
    missing = [e for e in probe['exprs'] if e not in plan['exprs']]
    assert not missing, 'missing exprs: %s (got %s)' % (missing, plan['exprs'])


def test_rank_source_has_no_self_literal():
    tree = _ast.parse(_RANK_SRC)
    assert not [n for n in _ast.walk(tree)
                if isinstance(n, _ast.Constant) and n.value == 'self']
