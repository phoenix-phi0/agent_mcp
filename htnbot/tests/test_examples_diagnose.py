import json
from pathlib import Path

from planbot import core, executor, planner

DOMAIN = str(Path(__file__).resolve().parent.parent / 'examples' / 'diagnose' / 'domain.json')
KEYS = ('ran', 'report', 'locate', 'probe', 'cause')


def _blank():
    st = {k: 'no' for k in KEYS}
    st['result'] = 'none'
    return st


def make_fake(script, state=None):
    """Fake cmd runner driven by a per-file script; returns (runner, calls)."""
    files = {}
    for name in sorted(set(script) | set(state or {})):
        st = _blank()
        st.update((state or {}).get(name, {}))
        files[name] = st
    calls = []

    def reply(code, output=''):
        return {'status': 'ok' if code == 0 else 'error', 'exit_code': code, 'output': output}

    def runner(name, args):
        calls.append((name, args))
        if name == 'diag_state':
            rows = [dict(files[n], file=n) for n in sorted(files)]
            return reply(0, json.dumps({'files': rows}))
        path = args.get('path')
        st = files.setdefault(path, _blank())
        plan = script.get(path, {})
        if name == 'run_test':
            st['ran'] = 'yes'
            st['result'] = plan.get('run_test', 'green')
            if st['result'] == 'red':
                return reply(1, 'FAILED %s: 1 failed' % path)
            return reply(0, 'ok')
        if name == 'test_report':
            st['report'] = 'yes'
            return reply(0)
        if name in ('locate', 'probe'):
            st[name] = 'yes'
            if plan.get(name):
                st['cause'] = 'yes'
            return reply(0)
        return reply(2, 'unknown command %s' % name)

    return runner, calls


def _load(script, state=None):
    runner, calls = make_fake(script, state)
    return core.load_domain(DOMAIN, cmd_runner=runner), calls


def test_load_without_cmd_runner():
    domain = core.load_domain(DOMAIN)
    assert domain.name == 'test_triage'


def test_dry_run_facts_match_fake_state():
    state = {'t_a.py': {'ran': 'yes', 'result': 'red', 'report': 'yes'}}
    domain, calls = _load({'t_a.py': {}}, state)
    allowed = planner.allowed_actions(domain, None, None)
    out = executor.dry_run_task(domain, core.parse_task(domain, 'diagnose(t_a.py)'), allowed)
    assert out['facts'] == sorted(['has_report(t_a.py)', 'test_ran(t_a.py)', 'test_red(t_a.py)'])
    assert {c[0] for c in calls} == {'diag_state'}


def test_smoke_red_then_probe_succeeds():
    domain, calls = _load({'t_a.py': {'run_test': 'red', 'locate': False, 'probe': True}})
    allowed = planner.allowed_actions(domain, None, None)
    report = executor.execute_task(domain, core.parse_task(domain, 'diagnose(t_a.py)'), allowed)
    assert report['status'] == 'done'
    names = [c[0] for c in calls]
    for n in ('run_test', 'test_report', 'locate', 'probe'):
        assert names.count(n) == 1


# ---- success path, backtracking, cli ----
from planbot import cli

GREEN = {'t_a.py': {'run_test': 'green'}}
RED_STATE = {'t_a.py': {'ran': 'yes', 'result': 'red', 'report': 'yes', 'locate': 'yes'}}


def _dry(domain, text='diagnose(t_a.py)', allowed=None):
    allowed = allowed or planner.allowed_actions(domain, None, None)
    return executor.dry_run_task(domain, core.parse_task(domain, text), allowed)['plan']


def _exec(domain, text='diagnose(t_a.py)', **kw):
    allowed = planner.allowed_actions(domain, None, None)
    return executor.execute_task(domain, core.parse_task(domain, text), allowed, **kw)


def test_success_dry_run():
    domain, calls = _load(GREEN)
    plan = _dry(domain)
    assert plan['found']
    assert [s['text'] for s in plan['steps']] == ['run_test(t_a.py)']
    root = plan['tree'][0]
    assert (root['method'], root['idx']) == ('first_run', 0)
    assert len(root['tried']) == 1
    t = root['tried'][0]
    assert (t['method'], t['reason'], t['detail']) == ('already_green', 'precondition', ['test_green(t_a.py)'])
    assert {c[0] for c in calls} == {'diag_state'}


def test_success_execute_then_again():
    domain, calls = _load(GREEN)
    rep = _exec(domain)
    assert rep['status'] == 'done' and rep['replans'] == 0 and rep['trigger'] is None
    assert [c for c in calls if c[0] == 'run_test'] == [('run_test', {'path': 't_a.py'})]
    assert _dry(domain)['tree'][0]['method'] == 'already_green'
    assert _exec(domain)['status'] == 'already_satisfied'
    assert [c[0] for c in calls].count('run_test') == 1


def test_backtrack_by_state():
    domain, _ = _load({'t_a.py': {}}, RED_STATE)
    plan = _dry(domain)
    root = plan['tree'][0]
    assert [(t['method'], t['reason']) for t in root['tried']] == [
        ('already_green', 'precondition'), ('first_run', 'precondition')]
    assert root['method'] == 'investigate'
    assert root['children'][0]['children'] == []
    fc = root['children'][1]
    assert [t['method'] for t in fc['tried']] == ['cause_known', 'by_locate']
    assert fc['method'] == 'by_probe'
    assert [s['text'] for s in plan['steps']] == ['probe(t_a.py)']


def test_backtrack_by_permission(capsys):
    state = {'t_a.py': {'ran': 'yes', 'result': 'red'}}
    runner, _ = make_fake({'t_a.py': {}}, state)
    domain = core.load_domain(DOMAIN, cmd_runner=runner)
    allowed = planner.allowed_actions(domain, ['run_test', 'test_report'], None)
    plan = _dry(domain, allowed=allowed)
    assert plan['found'] is False and plan['failure']['kind'] == 'no_method'
    inv = [t for t in plan['failure']['tried'] if t['method'] == 'investigate'][0]
    assert inv['reason'] == 'subtask_failed'
    bl = [t for t in inv['sub']['tried'] if t['method'] == 'by_locate'][0]
    assert (bl['reason'], bl['detail']) == ('not_allowed', ['locate'])
    code = cli.main(['explain', '--task', 'diagnose(t_a.py)', '--domain', DOMAIN, '--no-memory',
                     '--allow', 'run_test', '--allow', 'test_report'], cmd_runner=runner)
    assert code == 1
    assert 'skipped by_locate: not_allowed: locate' in capsys.readouterr().out


def test_cli_dry_run_text_and_json(capsys):
    runner, _ = make_fake(GREEN)
    argv = ['task', '--domain', DOMAIN, '--task', 'diagnose(t_a.py)', '--no-memory']
    assert cli.main(argv, cmd_runner=runner) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == 'task: diagnose(t_a.py)'
    assert not any(l.startswith('facts:') for l in lines)
    assert 'mode: dry-run' in lines
    assert cli.main(argv + ['--json'], cmd_runner=runner) == 0
    assert set(json.loads(capsys.readouterr().out)) == {'mode', 'plan', 'task'}


def test_relative_path_passed_verbatim(tmp_path):
    rel = 'tests/t_a.py'
    runner, calls = make_fake({rel: {'run_test': 'green'}})
    code = cli.main(['task', '--domain', DOMAIN, '--task', 'diagnose(%s)' % rel, '--no-memory',
                     '--cwd', str(tmp_path), '--execute'], cmd_runner=runner)
    assert code == 0
    assert [c[1] for c in calls if c[0] == 'run_test'] == [{'path': rel}]


RED = {'t_a.py': {'run_test': 'red', 'locate': False, 'probe': True}}
STUCK = {'t_a.py': {'run_test': 'red', 'locate': False, 'probe': False}}


def _names(calls):
    return [c[0] for c in calls]


def test_two_recoveries_after_mismatches():
    domain, calls = _load(RED)
    rep = _exec(domain)
    assert rep['status'] == 'done' and rep['replans'] == 2
    ex = rep['executed']
    assert [e['text'] for e in ex] == ['run_test(t_a.py)', 'test_report(t_a.py)', 'locate(t_a.py)', 'probe(t_a.py)']
    assert (ex[0]['ok'], ex[0]['matched'], ex[0]['missing']) == (False, False, ['test_green(t_a.py)'])
    assert (ex[2]['matched'], ex[2]['missing']) == (False, ['cause_found(t_a.py)'])
    r0, r1 = rep['replanned']
    assert (r0['resume'], r0['path']) == ('diagnose(t_a.py)', [])
    assert r0['trigger'] == {'kind': 'mismatch', 'step': 'run_test(t_a.py)'}
    assert r0['steps'] == ['test_report(t_a.py)', 'locate(t_a.py)']
    assert (r1['resume'], r1['idx']) == ('find_cause(t_a.py)', 1)
    assert r1['path'] == [{'text': 'diagnose(t_a.py)', 'idx': 0}]
    assert r1['steps'] == ['probe(t_a.py)']
    for n in ('run_test', 'test_report', 'locate', 'probe'):
        assert _names(calls).count(n) == 1
    assert 'cause_found(t_a.py)' in rep['final_facts']


def test_stuck_when_probe_finds_nothing():
    domain, _ = _load(STUCK)
    rep = _exec(domain)
    assert rep['status'] == 'stuck' and rep['replans'] == 3
    s = rep['stuck']
    assert (s['reason'], s['node'], s['idx'], s['step']) == ('no_plan', 'find_cause(t_a.py)', 1, 'probe(t_a.py)')
    assert s['path'] == [{'text': 'diagnose(t_a.py)', 'idx': 0}]
    assert rep['trigger'] == {'kind': 'mismatch', 'step': 'probe(t_a.py)'}


def test_stuck_via_cli(capsys):
    runner, _ = make_fake(STUCK)
    code = cli.main(['task', '--domain', DOMAIN, '--task', 'diagnose(t_a.py)', '--no-memory', '--execute'],
                    cmd_runner=runner)
    out = capsys.readouterr().out
    assert code == 1
    stuck = 'stuck at: probe(t_a.py) (no_plan) in diagnose(t_a.py)#0 > find_cause(t_a.py)#1'
    assert stuck in out and 'trigger: mismatch probe(t_a.py)' in out
    tail = out[out.index(stuck):]
    assert 'skipped by_locate:' in tail and 'skipped by_probe:' in tail


def test_max_replans_zero_via_cli(capsys):
    runner, calls = make_fake(STUCK)
    code = cli.main(['task', '--domain', DOMAIN, '--task', 'diagnose(t_a.py)', '--no-memory', '--execute',
                     '--max-replans', '0'], cmd_runner=runner)
    assert code == 1
    assert [n for n in _names(calls) if n != 'diag_state'] == ['run_test']
    assert '(replan_limit)' in capsys.readouterr().out


def test_task_memory_hit_list_and_fingerprint(tmp_path, capsys):
    path = str(tmp_path / 'm.json')
    mem = executor.Memory(path)
    domain, _ = _load(GREEN)
    assert _exec(domain, memory=mem)['saved_to_memory'] is True
    domain2, _ = _load(GREEN)
    task = core.parse_task(domain2, 'diagnose(t_a.py)')
    allowed = planner.allowed_actions(domain2, None, None)
    assert executor.dry_run_task(domain2, task, allowed, memory=mem)['plan']['source'] == 'memory'
    assert cli.main(['memory', 'list', '--memory-file', path]) == 0
    assert 'task diagnose(t_a.py)' in capsys.readouterr().out
    narrow = planner.allowed_actions(domain2, ['run_test', 'test_report', 'locate'], None)
    assert executor.dry_run_task(domain2, task, narrow, memory=mem)['plan']['source'] == 'decompose'
