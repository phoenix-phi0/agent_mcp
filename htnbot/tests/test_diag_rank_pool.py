"""The candidate pool is every located row; `limit` only caps how many come back."""
from planbot.diag.rank import WEIGHTS, rank

MODULE = '''\
def pick(items, limit):
    out = []
    a = 1
    b = 2
    c = 3
    d = 4
    e = 5
    f = 6
    g = 7
    h = 8
    k = 9
    if len(items) <= limit:
        out.append(items)
    return out
'''
TEST = '''\
from mod import pick


def test_pick():
    assert pick([1, 2], 2) == []
'''
ROOT = ('mod.py', 12)
SOURCES = {'mod.py': MODULE, 'test_mod.py': TEST}


def make_report():
    frames = [{'file': 'test_mod.py', 'line': 5, 'func': 'test_pick', 'code': 'assert pick([1, 2], 2) == []'},
              {'file': 'mod.py', 'line': 12, 'func': 'pick', 'code': 'if len(items) <= limit:'}]
    failure = {'test': 'test_pick', 'exc_type': 'AssertionError', 'message': '[[1, 2]] != []',
               'frames': frames, 'assert_line': frames[0]}
    return {'unrunnable': False, 'location': None, 'failures': [failure]}


def make_loc():
    """Twelve rows with identical numbers; the root cause is the 11th of them."""
    return [{'file': 'mod.py', 'line': n, 'susp': 0.5, 'fail': 1, 'passed': 1} for n in range(2, 14)]


def run(loc, limit=5):
    return rank(make_report(), loc, SOURCES, 'test_mod.py', limit=limit)


def test_root_cause_after_the_ninth_row_still_makes_the_result():
    loc = make_loc()
    assert [row['line'] for row in loc].index(ROOT[1]) >= 9
    result = run(loc)
    assert len(result) == 5
    assert ROOT in [(c['file'], c['line']) for c in result]


def test_row_order_does_not_change_the_result():
    loc = make_loc()
    assert run(loc) == run(list(reversed(loc)))


def test_limit_three_is_the_head_of_limit_five():
    loc = make_loc()
    assert run(loc, limit=3) == run(loc, limit=5)[:3]


# ---------------------------------------------------------------------------
# (c): the whole function around a stack frame joins the pool
# ---------------------------------------------------------------------------

TWO_FUNCS = '''\
import os


def first(items, n):
    """Doc."""
    total = 0
    for item in items:
        if item > n:
            total += item
        else:
            total -= 1
    try:
        total = int(total)
    except ValueError:
        total = 0
    return total


def second(x):
    y = x + 1
    return y
'''
FIRST_BODY = {5, 6, 7, 8, 9, 11, 12, 13, 15, 16}   # statement starts of first(); 4 is the def line


def frame_report(file, line):
    frames = [{'file': file, 'line': line, 'func': 'f', 'code': ''}]
    failure = {'test': 't', 'exc_type': 'ValueError', 'message': 'bad', 'frames': frames,
               'assert_line': None}
    return {'unrunnable': False, 'location': None, 'failures': [failure]}


def lines_in(result, file='fn.py'):
    return {c['line'] for c in result if c['file'] == file}


def fn_loc(*lines):
    return [{'file': 'fn.py', 'line': n, 'susp': 0.5, 'fail': 1, 'passed': 0} for n in lines]


def test_function_around_the_frame_joins_the_pool():
    result = rank(frame_report('fn.py', 8), fn_loc(6, 8, 9), {'fn.py': TWO_FUNCS}, 'test_fn.py',
                  limit=50)
    got = lines_in(result)
    assert FIRST_BODY <= got
    assert not got & {19, 20, 21}           # the other function (def line included)
    assert not got & {1, 4, 10, 14}         # module level, def line, else / except headers
    extra = [c for c in result if c['line'] in FIRST_BODY - {6, 8, 9}]
    assert extra and all(c['reasons'][0] == 'susp=0.000' for c in extra)


def test_module_level_frame_does_not_expand():
    result = rank(frame_report('fn.py', 1), [], {'fn.py': TWO_FUNCS}, 'test_fn.py', limit=50)
    assert [(c['file'], c['line']) for c in result] == [('fn.py', 1)]


def test_pool_expansion_is_row_order_independent():
    loc = fn_loc(6, 8, 9)
    args = (frame_report('fn.py', 8),)
    assert rank(*args, loc, {'fn.py': TWO_FUNCS}, 'test_fn.py', limit=50) == rank(
        *args, list(reversed(loc)), {'fn.py': TWO_FUNCS}, 'test_fn.py', limit=50)


def test_unparsable_file_is_not_expanded_and_does_not_raise():
    result = rank(frame_report('fn.py', 2), [], {'fn.py': 'def broken(:\n    x = 1\n'},
                  'test_fn.py', limit=50)
    assert [(c['file'], c['line']) for c in result] == [('fn.py', 2)]


def test_frame_in_a_test_file_expands_too():
    text = 'def test_a():\n    x = 1\n    assert x == 2\n\n\ndef test_b():\n    pass\n'
    result = rank(frame_report('test_fn.py', 3), [], {'test_fn.py': text}, 'test_fn.py', limit=50)
    assert lines_in(result, 'test_fn.py') == {2, 3}


def test_frame_func_weight_is_read_on_every_call(monkeypatch):
    args = (frame_report('fn.py', 8), fn_loc(8), {'fn.py': TWO_FUNCS}, 'test_fn.py')
    before = {c['line']: c['score'] for c in rank(*args, limit=50)}
    monkeypatch.setitem(WEIGHTS, 'frame_func', 5.0)
    after = {c['line']: c['score'] for c in rank(*args, limit=50)}
    assert after[6] == round(before[6] + 5.0, 3) and after[8] == before[8]


NONE_SOURCE = '''\
def apply(price, code):
    if code == 'half':
        return price / 2
    if code:
        cut = price * 3
    else:
        return price
'''


def test_dropped_value_is_suspicious_only_for_a_no_value_error():
    loc = [{'file': 'fn.py', 'line': n, 'susp': 1.0, 'fail': 1, 'passed': 0} for n in (3, 5)]
    none_rep = frame_report('fn.py', 5)
    none_rep['failures'][0]['exc_type'] = 'TypeError'
    none_rep['failures'][0]['message'] = "unsupported operand type(s) for +=: 'int' and 'NoneType'"
    got = {c['line']: c['reasons'] for c in rank(none_rep, loc, {'fn.py': NONE_SOURCE}, 't.py', limit=9)}
    assert 'dead_store' in got[5] and 'dead_store' not in got[3]
    other = rank(frame_report('fn.py', 5), loc, {'fn.py': NONE_SOURCE}, 't.py', limit=9)
    assert all('dead_store' not in c['reasons'] for c in other)


# ---------------------------------------------------------------------------
# (c): the failing test function itself is not expanded; its helpers are
# ---------------------------------------------------------------------------

T_TEST = 'def test_a():\n    x = 1\n    y = 2\n    assert h(x) == y\n\n\ndef test_b():\n    z = 3\n'
T_HELP = 'def h(v):\n    a = v + 1\n    b = a * 2\n    return b\n'
T_SOURCES = {'test_fn.py': T_TEST, 'fn.py': T_HELP}


def two_frame_report(test_name='test_fn.py::test_a[p1]'):
    frames = [{'file': 'test_fn.py', 'line': 4, 'func': 'test_a', 'code': 'assert h(x) == y'},
              {'file': 'fn.py', 'line': 3, 'func': 'h', 'code': 'b = a * 2'}]
    failure = {'test': test_name, 'exc_type': 'AssertionError', 'message': 'x', 'frames': frames,
               'assert_line': frames[0]}
    return {'unrunnable': False, 'location': None, 'failures': [failure]}


def test_failing_test_function_is_not_expanded_but_its_helper_is():
    # the test's stack line is located too (a loc row), so it is in the pool; nothing else of the
    # test function is
    loc = [{'file': 'test_fn.py', 'line': 4, 'susp': 0.5, 'fail': 1, 'passed': 0}]
    result = rank(two_frame_report(), loc, T_SOURCES, 'test_fn.py', limit=50)
    assert lines_in(result, 'fn.py') == {2, 3, 4}
    assert lines_in(result, 'test_fn.py') == {4}


def test_last_resort_expands_the_failing_test_function_of_a_lone_test_frame():
    frames = [{'file': 'test_fn.py', 'line': 3, 'func': 'test_a', 'code': 'y = 2'}]
    failure = {'test': 'test_fn.py::test_a', 'exc_type': 'AssertionError', 'message': 'x',
               'frames': frames, 'assert_line': None}
    report = {'unrunnable': False, 'location': None, 'failures': [failure]}
    result = rank(report, [], T_SOURCES, 'test_fn.py', limit=50)
    assert lines_in(result, 'test_fn.py') == {2, 3, 4}      # whole body, no def line (1)
    assert lines_in(result, 'fn.py') == set()


def test_loc_row_in_the_failing_test_function_does_not_expand_it_either():
    loc = [{'file': 'test_fn.py', 'line': 3, 'susp': 0.5, 'fail': 1, 'passed': 0}]
    result = rank(two_frame_report(), loc, T_SOURCES, 'test_fn.py', limit=50)
    assert lines_in(result, 'test_fn.py') == {3}


def test_without_test_file_the_test_function_body_is_expanded():
    result = rank(two_frame_report(), [], T_SOURCES, '', limit=50)
    assert lines_in(result, 'fn.py') == {2, 3, 4}
    assert lines_in(result, 'test_fn.py') == {2, 3, 4}


def test_report_without_failure_names_has_no_exception():
    report = two_frame_report()
    del report['failures'][0]['test']
    result = rank(report, [], T_SOURCES, 'test_fn.py', limit=50)
    assert lines_in(result, 'test_fn.py') == {2, 3, 4}


# ---------------------------------------------------------------------------
# (c): lines of the innermost function around a located row expand too
# ---------------------------------------------------------------------------

def test_function_around_a_located_row_joins_the_pool_without_any_frame_in_it():
    far = {'file': 'other.py', 'line': 1, 'func': 'f', 'code': ''}
    failure = {'test': 't', 'exc_type': 'ValueError', 'message': 'bad', 'frames': [far],
               'assert_line': None}
    report = {'unrunnable': False, 'location': None, 'failures': [failure]}
    result = rank(report, fn_loc(8), {'fn.py': TWO_FUNCS, 'other.py': 'x = 1\n'}, 'test_fn.py', limit=50)
    got = lines_in(result)
    assert FIRST_BODY <= got and not got & {4, 19, 20, 21}


NESTED = '''\
def outer(a):
    first = a + 1

    def inner(b):
        c = b * 2
        return c

    second = inner(first)
    return second
'''


def test_located_row_in_the_outer_function_expands_nested_bodies_but_not_their_headers():
    result = rank(frame_report('fn.py', 2), fn_loc(2), {'fn.py': NESTED}, 'test_fn.py', limit=50)
    assert lines_in(result) == {2, 5, 6, 8, 9}


def test_located_row_in_a_nested_function_expands_only_that_function():
    result = rank(frame_report('fn.py', 5), fn_loc(5), {'fn.py': NESTED}, 'test_fn.py', limit=50)
    assert lines_in(result) == {5, 6}
