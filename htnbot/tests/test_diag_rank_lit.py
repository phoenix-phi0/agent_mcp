"""A string constant compared on a line that is also quoted in a failing case's name gets a bonus."""
from planbot.diag.rank import WEIGHTS, rank

SRC = (
    "def pick(mode, xs):\n"
    "    if mode == 'up':\n"
    "        return sorted(xs)\n"
    "    if mode == 'down':\n"
    "        return sorted(xs)\n"
    "    return xs\n"
)


def _report(test):
    frame = {'file': 'lib.py', 'line': 6, 'func': 'pick', 'code': 'return xs'}
    return {'unrunnable': False, 'location': None, 'failures': [{
        'test': test, 'exc_type': 'AssertionError', 'message': 'x != y', 'frames': [frame],
        'assert_line': None}]}


def _loc():
    return [{'file': 'lib.py', 'line': n, 'susp': 0.7, 'fail': 1, 'passed': 0} for n in (2, 4)]


def _scores(test):
    got = rank(_report(test), _loc(), {'lib.py': SRC}, 't.py', limit=50)
    return {c['line']: c for c in got}


def test_constant_quoted_in_case_name_raises_the_line():
    with_lit = _scores("K.test_a (mode='down')")
    without = _scores('K.test_a')
    assert round(with_lit[4]['score'] - without[4]['score'], 3) == WEIGHTS['lit_match']
    assert with_lit[2]['score'] == without[2]['score']
    assert with_lit[4]['score'] > with_lit[2]['score']


def test_name_with_double_quotes_and_no_quotes():
    assert _scores('K.test_a (mode="up")')[2]['score'] > _scores('K.test_a (mode=up)')[2]['score']
