"""Recorded probe: precondition checks on the fixture, and replay of the recorded probe."""
import json
import re
from pathlib import Path

import pytest

import planbot.diag.replay as replay_module
from planbot.diag.parse import norm_path, parse_locate, parse_probe, parse_report
from planbot.diag.rank import sample_plan
from planbot.diag.replay import load_cases

_FIXTURE = Path(__file__).parent / 'fixtures' / 'diag_real.json'
_DOMAIN = str(Path(__file__).parent.parent / 'examples' / 'diagnose' / 'domain.json')


def _raw_failing():
    """Failing fixture cases (run_test exit_code != 0), read straight from the fixture file."""
    raw = json.loads(_FIXTURE.read_text(encoding='utf-8'))['cases']
    return [c for c in raw if c['calls']['run_test']['exit_code'] != 0]


_FAILING = _raw_failing()
_IDS = [c['test'] for c in _FAILING]


def _recorded(raw_case):
    return raw_case['calls'].get('probe')


def test_ten_failing_cases_in_fixture():
    assert len(_FAILING) == 10


# ---------------------------------------------------------------------------
# (A) precondition: the recorded probe chain is usable for ranking
# ---------------------------------------------------------------------------
_WITH = [c for c in _FAILING if _recorded(c) is not None]
_WITH_IDS = [c['test'] for c in _WITH]
_BOTH_SIDES = {'tests/htn_demo/test_demo_fail.py', 'tests/htn_demo/test_demo_branch.py',
               'tests/htn_bench/test_cmd_k5.py'}


def test_only_the_unimportable_case_has_no_probe_recording():
    assert [c['test'] for c in _FAILING if _recorded(c) is None] == [
        'tests/htn_demo/test_demo_import.py']
    assert len(_WITH) == 9


@pytest.mark.parametrize('raw', _WITH, ids=_WITH_IDS)
def test_recording_outcomes_after_parse(raw):
    text = _recorded(raw)['output']
    assert re.search(r'\[(失败|出错)\]', text)
    values = parse_probe(_recorded(raw))
    assert values
    assert all(v['outcome'] in ('fail', 'pass') for v in values)
    outcomes = {v['outcome'] for v in values}
    assert 'fail' in outcomes
    has_pass_side = '[通过]' in text
    assert ('pass' in outcomes) == has_pass_side
    if raw['test'] in _BOTH_SIDES:
        assert has_pass_side and outcomes == {'fail', 'pass'}


def test_cases_without_a_pass_side_recording():
    """Recorded probes whose original text has no passing-case line (reported, not required to have pass)."""
    names = [c['test'] for c in _WITH if '[通过]' not in _recorded(c)['output']]
    assert set(names).isdisjoint(_BOTH_SIDES)
    assert len(names) == len(_WITH) - sum(1 for c in _WITH if '[通过]' in _recorded(c)['output'])


# ---------------------------------------------------------------------------
# (B) load_cases / replay_case replay the recorded probe
# ---------------------------------------------------------------------------

def _walk_keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _walk_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_keys(item)


def _mini_fixture(tmp_path):
    raw = json.loads(_FIXTURE.read_text(encoding='utf-8'))['cases']
    with_probe = next(c for c in raw if c['test'] == 'tests/htn_demo/test_demo_fail.py')
    without = next(c for c in raw if c['test'] == 'tests/htn_demo/test_demo_import.py')
    path = tmp_path / 'mini.json'
    path.write_text(json.dumps({'cases': [with_probe, without]}), encoding='utf-8')
    return str(path), with_probe


def test_load_cases_carries_probe_only_when_recorded(tmp_path):
    path, raw = _mini_fixture(tmp_path)
    recorded, plain = load_cases(path)
    probe = recorded['outputs']['probe']
    assert probe == {'status': raw['calls']['probe']['status'], 'exit_code': raw['calls']['probe']['exit_code'],
                     'output': raw['calls']['probe']['output']}
    assert 'probe' not in plain['outputs']
    for case in (recorded, plain):
        keys = set(_walk_keys(case))
        assert 'truth' not in keys and 'at' not in keys and 'exprs' not in keys and 'args' not in keys


def test_unimportable_case_has_no_probe_key_in_the_real_fixture():
    loaded = {c['id']: c for c in load_cases(str(_FIXTURE))}
    no_probe = [i for i in _IDS if 'probe' not in loaded[i]['outputs']]
    assert no_probe == ['tests/htn_demo/test_demo_import.py']
    assert all('probe' in loaded[i]['outputs'] for i in _WITH_IDS)


def test_fake_runner_replays_recorded_probe_or_returns_no_values(tmp_path, monkeypatch):
    path, _ = _mini_fixture(tmp_path)
    recorded, plain = load_cases(path)
    seen = {}

    def spy(domain_path, test_file, runner, **kwargs):
        seen['runner'] = runner
        return {'report': None, 'calls': [], 'finding': None}

    monkeypatch.setattr(replay_module, 'diagnose', spy)
    args = {'path': 'x.py', 'at': ['a.py:1'], 'exprs': ['zzz']}
    replay_module.replay_case(recorded, _DOMAIN)
    assert seen['runner']('probe', args) == recorded['outputs']['probe']
    assert seen['runner']('probe', {}) == recorded['outputs']['probe']
    replay_module.replay_case(plain, _DOMAIN)
    assert seen['runner']('probe', args) == {'status': 'error', 'exit_code': 1, 'output': ''}
    assert seen['runner']('other', args) == {'status': 'error', 'exit_code': 1, 'output': ''}


def _norm_file(item):
    out = dict(item)
    out['file'] = norm_path(item['file']) or item['file']
    return out


def _norm_at(text):
    file, _, line = text.rpartition(':')
    return '%s:%s' % (norm_path(file) or file, line)


@pytest.mark.parametrize('raw', _FAILING, ids=_IDS)
def test_sample_plan_includes_recorded_at_and_exprs(raw):
    recorded = _recorded(raw)
    if recorded is None:
        return
    test_file = raw['test']
    sources = {norm_path(k): v for k, v in raw['sources'].items()}
    report = parse_report(raw['calls']['test_report'], test_file)
    for failure in report['failures']:
        failure['frames'] = [_norm_file(fr) for fr in failure['frames']]
    loc = [_norm_file(r) for r in parse_locate(raw['calls']['locate'])]
    plan = sample_plan(report, loc, [], sources, test_file)
    got_at = {_norm_at(a) for a in plan['at']}
    want_at = {_norm_at(a) for a in recorded['args']['at']}
    assert want_at <= got_at, 'missing at: %s (got %s)' % (sorted(want_at - got_at), plan['at'])
    missing = [e for e in recorded['args']['exprs'] if e not in plan['exprs']]
    assert not missing, 'missing exprs: %s (got %s)' % (missing, plan['exprs'])
