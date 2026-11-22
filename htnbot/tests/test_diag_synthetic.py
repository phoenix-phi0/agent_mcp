"""Four hand-made bugs (not from the fixture): coverage is collected by really running them."""
import importlib.util
import re
import sys
import traceback

import pytest

from planbot.diag.rank import rank
from test_diag_fixture import baseline_pick, norm_path

# '#@' marks the root-cause line; the marker is stripped before the file is written.
CASES = {
    'boundary': ('''\
"""Budget helpers."""

MIN_PRICE = 0


def count_in_budget(prices, budget):
    """How many prices are strictly below the budget."""
    count = 0
    seen = 0
    for price in prices:
        if price <= MIN_PRICE:
            continue
        seen += 1
        if price <= budget:  #@
            count += 1
    if seen == 0:
        return 0
    return count
''', '''\
from boundary import count_in_budget


def test_at_the_limit():
    got = count_in_budget([5, 10, 15], 10)
    assert got == 1, '%d != 1' % got


def test_all_below():
    assert count_in_budget([1, 2, 3], 10) == 3
'''),
    'slice': ('''\
"""Window sums."""


def last_k_sum(values, k):
    """Sum of the last k values."""
    if k <= 0:
        return 0
    total = 0
    size = len(values)
    taken = 0
    for offset in range(k):
        if taken >= size:
            break
        total += values[size - offset]  #@
        taken += 1
    return total


def mean_of_last(values, k):
    return last_k_sum(values, k) / max(k, 1)
''', '''\
from slice import last_k_sum


def test_last_two():
    assert last_k_sum([1, 2, 3, 4], 2) == 7


def test_nothing():
    assert last_k_sum([1, 2, 3], 0) == 0
'''),
    'boolop': ('''\
"""Shipping rules."""


def can_ship(stock, address_ok, blocked, region):
    """Ship only when in stock and the address is valid."""
    if region in blocked:
        return False
    has_stock = stock > 0
    ready = has_stock or address_ok  #@
    if not ready:
        return False
    if stock > 1000:
        return True
    return True


def label(stock, address_ok, blocked, region):
    return 'ship' if can_ship(stock, address_ok, blocked, region) else 'hold'
''', '''\
from boolop import can_ship


def test_no_stock_is_held():
    assert can_ship(0, True, [], 'eu') is False, 'shipped without stock'


def test_normal_order():
    assert can_ship(3, True, [], 'eu') is True
'''),
    'noreturn': ('''\
"""Discount codes."""


def apply_discount(price, code):
    """Price after applying a code such as HALF or SAVE10."""
    if code is None:
        return price
    if code == 'HALF':
        return price / 2
    if code.startswith('SAVE'):
        percent = int(code[4:])
        discounted = price * (100 - percent) / 100  #@
    else:
        return price


def total_with_discount(prices, code):
    total = 0
    for price in prices:
        total += apply_discount(price, code)
    return total


def describe(prices, code):
    return 'total=%s' % total_with_discount(prices, code)
''', '''\
from noreturn import total_with_discount


def test_percent_code():
    assert total_with_discount([100, 50], 'SAVE10') == 135


def test_half_code():
    assert total_with_discount([100, 50], 'HALF') == 75
'''),
}


def trace_run(fn, target):
    """Run fn under sys.settrace; return (executed lines of target, exception or None)."""
    seen = set()

    def local(frame, event, arg):
        if event == 'line':
            seen.add(frame.f_lineno)
        return local

    def glob(frame, event, arg):
        if frame.f_code.co_filename == target:
            seen.add(frame.f_lineno)
            return local

    sys.settrace(glob)
    try:
        fn()
        exc = None
    except BaseException as caught:
        exc = caught
    finally:
        sys.settrace(None)
    return seen, exc


def frames_of(exc, root):
    out = []
    for item in traceback.extract_tb(exc.__traceback__):
        rel = norm_path(item.filename[len(root) + 1:]) if item.filename.startswith(root + '/') else None
        if rel:
            out.append({'file': rel, 'line': item.lineno, 'func': item.name, 'code': item.line or ''})
    return out


def collect(tmp_path, name, monkeypatch):
    """Write the example, run its tests under settrace, return (report, loc, sources, root, test_file)."""
    mod_text, test_text = CASES[name]
    lines = mod_text.splitlines()
    root = next(i for i, ln in enumerate(lines, 1) if ln.endswith('#@'))
    mod_text = '\n'.join(ln.removesuffix('  #@') for ln in lines) + '\n'
    assert 15 <= len(lines) <= 40
    mod_file, test_file = name + '.py', 'test_%s.py' % name
    (tmp_path / mod_file).write_text(mod_text)
    (tmp_path / test_file).write_text(test_text)
    monkeypatch.syspath_prepend(str(tmp_path))
    spec = importlib.util.spec_from_file_location('t_' + name, str(tmp_path / test_file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    target = str(tmp_path / mod_file)
    fail, passed, failures = {}, {}, []
    for test_name in sorted(n for n in vars(module) if n.startswith('test_')):
        seen, exc = trace_run(getattr(module, test_name), target)
        for line in seen:
            counts = passed if exc is None else fail
            counts[line] = counts.get(line, 0) + 1
        if exc is not None:
            frames = frames_of(exc, str(tmp_path))
            inside = [f for f in frames if f['file'] == test_file]
            failures.append({'test': test_name, 'exc_type': type(exc).__name__, 'message': str(exc),
                             'frames': frames, 'assert_line': inside[-1] if inside else None})
    assert failures and passed, 'each example needs a failing and a passing test'
    loc = [{'file': mod_file, 'line': n, 'susp': 1.0, 'fail': fail.get(n, 0), 'passed': passed.get(n, 0)}
           for n in sorted(set(fail) | set(passed))]
    report = {'unrunnable': False, 'location': None, 'failures': failures}
    return report, loc, {mod_file: mod_text, test_file: test_text}, (mod_file, root), test_file


def position(pairs, root):
    return next((i for i, pair in enumerate(pairs, 1) if pair == root), None)


@pytest.fixture(scope='module')
def results(tmp_path_factory):
    out = {}
    with pytest.MonkeyPatch.context() as monkeypatch:
        for name in CASES:
            report, loc, sources, root, test_file = collect(tmp_path_factory.mktemp(name), name, monkeypatch)
            cands = rank(report, loc, sources, test_file)
            out[name] = (position([(c['file'], c['line']) for c in cands], root),
                         position(baseline_pick(report, loc), root))
    return out


def test_bug_types_are_distinct():
    assert len(CASES) >= 4 and len({m for m, _ in CASES.values()}) == len(CASES)


def test_root_cause_always_in_top_five(results):
    assert all(new is not None and new <= 5 for new, _ in results.values()), results


def test_root_cause_in_top_three_for_most(results):
    assert sum(new is not None and new <= 3 for new, _ in results.values()) >= 3, results


def test_root_cause_first_for_some(results):
    assert sum(new == 1 for new, _ in results.values()) >= 2, results


def test_baseline_rule_often_misses_first_place(results):
    assert sum(old != 1 for _, old in results.values()) >= 2, results
