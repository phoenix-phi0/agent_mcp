"""parse_probe on the real '#n <test> [失败|通过|出错]  e=v ; e=v' lines."""
import pytest

from planbot.diag.parse import parse_probe

_HEAD = '== pkg/m.py:3 | total = 0   命中 1 次\n'


def _run(*lines):
    return parse_probe({'status': 'ok', 'exit_code': 0, 'output': _HEAD + '\n'.join(lines) + '\n'})


def _brief(values):
    return [(v['expr'], v['value'], v['test'], v['outcome'], v['at']) for v in values]


def test_failed_line_gives_one_value_per_item_with_full_test_name():
    got = _run('#1 K.test_a (v=[1, 2]) [失败]  x=1 ; y=abc')
    assert _brief(got) == [
        ('x', '1', 'K.test_a (v=[1, 2])', 'fail', 'pkg/m.py:3'),
        ('y', 'abc', 'K.test_a (v=[1, 2])', 'fail', 'pkg/m.py:3'),
    ]


@pytest.mark.parametrize('mark,outcome', [('通过', 'pass'), ('失败', 'fail'), ('出错', 'fail')])
def test_marks_map_to_outcomes(mark, outcome):
    got = _run('#2 K.test_b [%s]  n=5' % mark)
    assert [(v['expr'], v['value'], v['test'], v['outcome']) for v in got] == [('n', '5', 'K.test_b', outcome)]


def test_comparison_operators_do_not_split_items():
    got = _run('#1 K.test_c [通过]  a==b=ok ; c<=d=1 ; e!=f=2 ; g>=h=3')
    assert _brief(got) == [
        ('a==b', 'ok', 'K.test_c', 'pass', 'pkg/m.py:3'),
        ('c<=d', '1', 'K.test_c', 'pass', 'pkg/m.py:3'),
        ('e!=f', '2', 'K.test_c', 'pass', 'pkg/m.py:3'),
        ('g>=h', '3', 'K.test_c', 'pass', 'pkg/m.py:3'),
    ]


@pytest.mark.parametrize('line', [
    '#1 \udc80� garbage ;;; ==',
    '#1 K.test_a x=1 ; y=2',
    '#1 K.test_a [失败]',
    '#1 K.test_a [失败]   ',
    '#1 K.test_a [失败]x=1',
    '#1 K.test_a [失败]  no equals here',
])
def test_garbage_unmarked_or_itemless_lines_yield_no_marked_values_and_do_not_raise(line):
    got = _run(line)
    assert isinstance(got, list)
    assert not [v for v in got if v['outcome'] in ('fail', 'pass')]


def test_deterministic():
    line = '#1 K.test_a (v=[1, 2]) [失败]  x=1 ; y=abc'
    assert _run(line) == _run(line)
