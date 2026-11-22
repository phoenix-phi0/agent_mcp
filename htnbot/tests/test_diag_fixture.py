import json
import math
import os
import re
import tempfile
import time
from pathlib import Path

import pytest

from planbot.core import PlanbotError
from planbot.diag.parse import norm_path, parse_locate, parse_report, parse_run_test
from planbot.diag.replay import load_cases, replay_case

FIXTURE = 'tests/fixtures/diag_real.json'
DOMAIN = 'examples/diagnose/domain.json'

_CACHE = {}


def cases():
    if 'cases' not in _CACHE:
        _CACHE['cases'] = load_cases(FIXTURE)
    return _CACHE['cases']


def replayed(case_id):
    """Replay each fixture case at most once per test session."""
    if case_id not in _CACHE:
        case = next(c for c in cases() if c['id'] == case_id)
        _CACHE[case_id] = replay_case(case, DOMAIN)
    return _CACHE[case_id]


def walk_keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from walk_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk_keys(item)


def write_fixture_copy(tmp_path, edit):
    with open(FIXTURE, encoding='utf-8') as handle:
        data = json.load(handle)
    edit(data['cases'])
    path = tmp_path / 'inner' / 'fixture.json'
    path.parent.mkdir()
    path.write_text(json.dumps(data), encoding='utf-8')
    return str(path)


def code_of(exc_info):
    return exc_info.value.code


def test_load_cases_shape():
    loaded = cases()
    assert len(loaded) == 11
    for case in loaded:
        assert set(case) == {'id', 'test_file', 'sources', 'outputs'}
        assert 'run_test' in case['outputs']
        assert set(case['outputs']) <= {'run_test', 'test_report', 'locate', 'probe'}
        for result in case['outputs'].values():
            assert set(result) == {'status', 'exit_code', 'output'}
    assert 'truth' not in set(walk_keys(loaded))
    assert len({c['id'] for c in loaded}) == 11


@pytest.mark.parametrize('bad', ['../evil.py', '/abs/evil.py'])
def test_load_cases_rejects_escaping_source_key(tmp_path, bad):
    target = {}

    def edit(raw):
        key = next(iter(raw[1]['sources']))
        raw[1]['sources'][bad] = raw[1]['sources'].pop(key)
        target['id'] = raw[1]['test']

    path = write_fixture_copy(tmp_path, edit)
    with pytest.raises(PlanbotError) as exc:
        load_cases(path)
    assert exc.value.code == 'USAGE'
    assert target['id'] in exc.value.message
    assert bad in exc.value.message
    assert sorted(p.name for p in tmp_path.iterdir()) == ['inner']
    assert sorted(p.name for p in tmp_path.parent.iterdir() if p.name == 'evil.py') == []


def test_load_cases_rejects_duplicate_normalised_keys(tmp_path):
    def edit(raw):
        key = next(iter(raw[1]['sources']))
        raw[1]['sources']['./' + key] = raw[1]['sources'][key]

    with pytest.raises(PlanbotError) as exc:
        load_cases(write_fixture_copy(tmp_path, edit))
    assert exc.value.code == 'USAGE'


def test_load_cases_normalises_keys(tmp_path):
    def edit(raw):
        key = next(iter(raw[1]['sources']))
        raw[1]['sources']['./' + key] = raw[1]['sources'].pop(key)

    loaded = load_cases(write_fixture_copy(tmp_path, edit))
    assert set(loaded[1]['sources']) == set(cases()[1]['sources'])


def test_replay_case_rejects_escaping_key():
    case = {'id': 'x', 'test_file': 'tests/t.py', 'sources': {'../x.py': 'pass\n'},
            'outputs': {'run_test': {'status': 'ok', 'exit_code': 0, 'output': ''}}}
    with pytest.raises(PlanbotError) as exc:
        replay_case(case, DOMAIN)
    assert exc.value.code == 'USAGE'


def test_load_cases_missing_file(tmp_path):
    with pytest.raises(PlanbotError) as exc:
        load_cases(str(tmp_path / 'nope.json'))
    assert exc.value.code == 'USAGE'


def test_load_cases_not_json_or_unknown_structure(tmp_path):
    bad = tmp_path / 'bad.json'
    bad.write_text('{not json', encoding='utf-8')
    with pytest.raises(PlanbotError) as exc:
        load_cases(str(bad))
    assert exc.value.code == 'USAGE'
    for body in ('[]', '{"cases": 3}', '{"cases": [{"test": "t.py"}]}'):
        bad.write_text(body, encoding='utf-8')
        with pytest.raises(PlanbotError) as exc:
            load_cases(str(bad))
        assert exc.value.code == 'USAGE'


def test_replay_case_returns_finding_without_temp_path(monkeypatch):
    made = []
    real = tempfile.TemporaryDirectory

    def recording(*args, **kwargs):
        directory = real(*args, **kwargs)
        made.append(directory.name)
        return directory

    monkeypatch.setattr(tempfile, 'TemporaryDirectory', recording)
    case = cases()[1]
    result = replay_case(case, DOMAIN)
    assert {'report', 'calls', 'finding'} <= set(result)
    assert len(made) == 1
    text = json.dumps(result)
    assert made[0] not in text
    assert os.path.join(tempfile.gettempdir(), 'tmp') not in text
    assert not os.path.exists(made[0])
    _CACHE[case['id']] = result


# ---------------------------------------------------------------------------
# accuracy on the real fixture (hand-labelled truth is read only here)
# ---------------------------------------------------------------------------

PASSING = 'tests/htn_demo/test_demo_pass.py'

# id -> (finding.status, finding.source, engine report status), as measured.
OUTCOME = {
    'tests/htn_demo/test_demo_pass.py': ('passed', None, 'done'),
    'tests/htn_demo/test_demo_fail.py': ('found', 'locate', 'done'),
    'tests/htn_demo/test_demo_branch.py': ('found', 'locate', 'done'),
    'tests/htn_demo/test_demo_error.py': ('found', 'locate', 'done'),
    'tests/htn_demo/test_demo_inline.py': ('found', 'probe', 'done'),
    'tests/htn_demo/test_demo_import.py': ('found', 'unrunnable', 'done'),
    'tests/htn_bench/test_cmd_k1.py': ('found', 'locate', 'done'),
    'tests/htn_bench/test_cmd_k2.py': ('found', 'locate', 'done'),
    'tests/htn_bench/test_cmd_k3.py': ('found', 'locate', 'done'),
    'tests/htn_bench/test_cmd_k5.py': ('found', 'locate', 'done'),
    'tests/htn_bench/test_cmd_k6.py': ('found', 'locate', 'done'),
}

# id -> rank (1-5) of the labelled root-cause line among the candidates, or None.
EXPECTED = {
    'tests/htn_demo/test_demo_pass.py': None,
    'tests/htn_demo/test_demo_fail.py': 1,
    'tests/htn_demo/test_demo_branch.py': 3,
    'tests/htn_demo/test_demo_error.py': 2,
    'tests/htn_demo/test_demo_inline.py': 1,
    'tests/htn_demo/test_demo_import.py': 1,
    'tests/htn_bench/test_cmd_k1.py': 2,
    'tests/htn_bench/test_cmd_k2.py': 5,
    'tests/htn_bench/test_cmd_k3.py': None,
    'tests/htn_bench/test_cmd_k5.py': 1,
    'tests/htn_bench/test_cmd_k6.py': None,
}

# Same measure for the rule currently used by reference/htn_diag_v2.py.
BASELINE = {
    'tests/htn_demo/test_demo_pass.py': None,
    'tests/htn_demo/test_demo_fail.py': 4,
    'tests/htn_demo/test_demo_branch.py': 3,
    'tests/htn_demo/test_demo_error.py': 2,
    'tests/htn_demo/test_demo_inline.py': None,
    'tests/htn_demo/test_demo_import.py': 1,
    'tests/htn_bench/test_cmd_k1.py': 3,
    'tests/htn_bench/test_cmd_k2.py': None,
    'tests/htn_bench/test_cmd_k3.py': None,
    'tests/htn_bench/test_cmd_k5.py': None,
    'tests/htn_bench/test_cmd_k6.py': None,
}


@pytest.fixture(scope='module', autouse=True)
def _clock():
    _CACHE['t0'] = time.monotonic()


def truth_lines():
    with open(FIXTURE, encoding='utf-8') as handle:
        raw = json.load(handle)['cases']
    out = {}
    for item in raw:
        marks = item['truth'] if isinstance(item['truth'], list) else [item['truth']]
        out[item['test']] = {(norm_path(m.rpartition(':')[0]), int(m.rpartition(':')[2]))
                             for m in marks if m}
    return out


def rank_in(entries, truth):
    for i, (file, line) in enumerate(entries, 1):
        if (norm_path(file), line) in truth:
            return i
    return None


def measured():
    truth = truth_lines()
    return {c['id']: rank_in([(x['file'], x['line']) for x in replayed(c['id'])['finding']['candidates']],
                             truth[c['id']]) for c in cases()}


def tally(table):
    return sum(v is not None for v in table.values()), sum(v == 1 for v in table.values())


def test_every_case_replays_with_expected_calls():
    for case in cases():
        result = replayed(case['id'])
        finding, names = result['finding'], [c['name'] for c in result['calls']]
        assert (finding['status'], finding['source'], result['report']['status']) == OUTCOME[case['id']]
        if case['id'] == PASSING:
            assert names == ['run_test']
            continue
        assert names.count('run_test') == 1 and names.count('test_report') == 1
        if finding['source'] == 'unrunnable':
            assert 'locate' not in names and 'probe' not in names
            continue
        assert names.count('locate') == 1 and 0 <= names.count('probe') <= 2
        locates = [c for c in result['calls'] if c['name'] == 'locate']
        assert locates[0]['args']['limit'] == 50
        if finding['source'] == 'locate':
            assert finding['status'] == 'found' and result['report']['status'] == 'done'
            assert 1 <= len(finding['candidates']) <= 5


def test_expected_ranks_match_table():
    assert set(EXPECTED) == {c['id'] for c in cases()} and len(EXPECTED) == 11
    assert measured() == EXPECTED


def test_table_summary_literals():
    assert tally(EXPECTED) == (8, 4)


def test_accuracy_hard_thresholds():
    in_candidates, first = tally(EXPECTED)
    assert in_candidates >= 8, 'root cause among candidates: %d of 10' % in_candidates
    assert first == 4, 'root cause ranked first (measured, recorded only): %d of 10' % first


def baseline_pick(report, loc):
    """reference/htn_diag_v2.py: sort rows by (-score, not in traceback), keep
    min(5, max(3, number of rows tied with the best score)); with no rows fall back
    to the position the report gives."""
    frames = [(norm_path(f['file']), f['line']) for fl in report['failures'] for f in fl['frames']]
    place = report['location'] and (norm_path(report['location']['file']), report['location']['line'])
    trace = set(frames) | ({place} if place else set())
    rows = [(norm_path(r['file']), r['line'], r['susp']) for r in loc]
    rows.sort(key=lambda r: (-r[2], (r[0], r[1]) not in trace))
    if not rows:
        return [place] if place else frames[-1:]
    count = min(5, max(3, sum(r[2] == rows[0][2] for r in rows)))
    return [(r[0], r[1]) for r in rows[:count]]


def test_baseline_reference_rule():
    truth = truth_lines()
    table = {c['id']: rank_in(baseline_pick(parse_report(c['outputs'].get('test_report'), c['test_file']),
                                            parse_locate(c['outputs'].get('locate'))), truth[c['id']])
             for c in cases()}
    assert table == BASELINE
    assert tally(BASELINE) == (5, 1)
    assert tally(EXPECTED)[0] > tally(BASELINE)[0] and tally(EXPECTED)[1] > tally(BASELINE)[1]


def test_diag_sources_do_not_name_fixture_objects_or_truth():
    words = set()
    for case in cases():
        for name in list(case['sources']) + [case['test_file']]:
            words.add(Path(name).stem)
        for test_id in parse_run_test(case['outputs']['run_test'])['failed']:
            words.add(re.split(r'[.:]', test_id)[-1])
    words = {w for w in words if len(w) >= 4}
    assert len(words) >= 20
    for path in sorted(Path('planbot/diag').glob('*.py')):
        text = path.read_text(encoding='utf-8')
        assert 'truth' not in text.lower(), path
        for word in sorted(words):
            assert not re.search(r'\b%s\b' % re.escape(word), text), (path, word)


def test_not_worse_than_reference_per_case():
    worse = []
    for case_id, new in measured().items():
        old = BASELINE[case_id]
        if (new if new is not None else math.inf) > (old if old is not None else math.inf):
            worse.append('%s: new rank %s, baseline rank %s' % (case_id, new, old))
    assert not worse, worse


def test_whole_file_runs_within_ten_seconds():
    assert time.monotonic() - _CACHE['t0'] < 10
