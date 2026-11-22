import json
import re

import pytest

from planbot.diag import Session
from planbot.diag.parse import norm_path, parse_report, safe_expr

FAIL_OUT = 'FAIL: test_a (t.T)\n'
SOURCE = ''.join('line%d = %d\n' % (i, i) for i in range(1, 11))


def ok(output='', code=0):
    return {'status': 'ok', 'exit_code': code, 'output': output}


def report(*blocks):
    return ok('test_report t.py：\n' + ''.join(blocks))


def block(exc, frame, chain='', test='T.test_a'):
    tail = '；调用链 ' + chain if chain else ''
    return '[1] 失败 %s\n    %s\n    最内层仓库内帧 %s (f)%s\n' % (test, exc, frame, tail)


UNRUNNABLE = 'test_report t.py：测试跑不起来——导入测试文件时SyntaxError: invalid syntax\n'


class Fake:
    """Runner that replays scripted results per command name and records calls."""

    def __init__(self, **script):
        self.script = {k: list(v) if isinstance(v, list) else [v] for k, v in script.items()}
        self.seen = []

    def __call__(self, name, args):
        self.seen.append((name, args))
        queue = self.script[name]
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def repo(tmp_path):
    (tmp_path / 'pkg').mkdir()
    (tmp_path / 'pkg' / 'm.py').write_text(SOURCE)
    return tmp_path


def state(s, path='t.py'):
    rows = json.loads(s.run('diag_state', {})['output'])['files']
    return {r['file']: r for r in rows}.get(path)


def test_passed_run():
    s = Session(Fake(run_test=ok('1 passed')))
    assert s.run('run_test', {'path': 't.py'})['exit_code'] == 0
    f = s.finding('t.py')
    assert (f['status'], f['source'], f['candidates']) == ('passed', None, [])
    assert f['file'] == 't.py'
    assert json.dumps(f)


def test_diag_state_follows_commands():
    fake = Fake(run_test=ok(FAIL_OUT, 1), test_report=report(block('ValueError: x', 'pkg/m.py:3')))
    s = Session(fake)
    out = s.run('diag_state', {})
    assert out['exit_code'] == 0 and json.loads(out['output']) == {'files': []}
    s.run('run_test', {'path': 'b.py'})
    s.run('run_test', {'path': 't.py'})
    assert state(s) == {'file': 't.py', 'ran': 'yes', 'result': 'red', 'report': 'no',
                        'locate': 'no', 'probe': 'no', 'cause': 'no'}
    s.run('test_report', {'path': 't.py'})
    assert state(s)['report'] == 'yes' and state(s)['cause'] == 'no'
    assert [r['file'] for r in json.loads(s.run('diag_state', {})['output'])['files']] == ['b.py', 't.py']
    assert 'diag_state' not in [n for n, _ in fake.seen]
    assert [c['name'] for c in s.calls] == ['run_test', 'run_test', 'test_report']
    s2 = Session(Fake(run_test=ok('ok')))
    s2.run('run_test', {'path': 't.py'})
    assert state(s2)['result'] == 'green'


def test_unknown_and_bad_args_do_not_reach_runner():
    fake = Fake(run_test=ok())
    s = Session(fake)
    r = s.run('other', {'path': 'x'})
    assert (r['status'], r['exit_code'], r['output']) == ('error', 2, 'unknown command')
    for args in (None, [], {}, {'path': 3}):
        r = s.run('run_test', args)
        assert (r['exit_code'], r['output']) == (2, 'bad args')
    assert fake.seen == [] and s.calls == [] and state(s, 'x') is None


@pytest.mark.parametrize('bad', [RuntimeError('boom'), {}, None,
                                 {'status': 'ok', 'exit_code': '0', 'output': 'x'},
                                 {'status': 'ok', 'exit_code': True, 'output': 'x'}])
def test_bad_runner_result(bad):
    fake = Fake(run_test=ok(FAIL_OUT, 1), test_report=bad)
    s = Session(fake)
    s.run('run_test', {'path': 't.py'})
    r = s.run('test_report', {'path': 't.py'})
    assert r['status'] == 'error' and r['exit_code'] == 1 and isinstance(r['output'], str)
    assert state(s)['report'] == 'no' and state(s)['result'] == 'red'
    assert len(s.calls) == 2 and s.calls[1]['status'] == 'error' and s.calls[1]['exit_code'] is None
    assert s.calls[1]['output'] == r['output']
    assert s.finding('t.py')['source'] is None
    if isinstance(bad, Exception):
        assert r['output'] == 'boom'


def test_empty_valid_report_counts():
    s = Session(Fake(run_test=ok(FAIL_OUT, 1), test_report=ok('nothing useful')))
    s.run('run_test', {'path': 't.py'})
    s.run('test_report', {'path': 't.py'})
    assert state(s)['report'] == 'yes'
    f = s.finding('t.py')
    assert (f['status'], f['source'], f['candidates'], f['exception']) == ('not_found', 'report_only', [], None)
    assert f['failed_tests']


def test_unrunnable_with_location(repo):
    (repo / 't.py').write_text(SOURCE)
    rep = ok(UNRUNNABLE + '  位置 pkg/m.py:5 (<module>)\n')
    s = Session(Fake(run_test=ok('collect error', 2), test_report=rep), str(repo))
    s.run('run_test', {'path': 't.py'})
    s.run('test_report', {'path': 't.py'})
    f = s.finding('t.py')
    assert (f['status'], f['source']) == ('found', 'unrunnable')
    c = f['candidates'][0]
    assert (c['file'], c['line'], c['score'], c['reasons']) == ('pkg/m.py', 5, 1.0, ['unrunnable'])
    assert [x['line'] for x in c['snippet']] == [3, 4, 5, 6, 7]
    assert c['snippet'][2]['text'] == 'line5 = 5' and c['probe'] == []
    assert state(s)['cause'] == 'yes'


def test_unrunnable_without_location():
    s = Session(Fake(run_test=ok('collect error', 2), test_report=ok(UNRUNNABLE)))
    s.run('run_test', {'path': 't.py'})
    s.run('test_report', {'path': 't.py'})
    f = s.finding('t.py')
    assert (f['status'], f['source'], f['candidates']) == ('not_found', 'unrunnable', [])
    assert state(s)['cause'] == 'no'


def stack_part(cands, rep, root):
    """Candidates (original order) that sit on a stack frame of the report `rep` (a runner result)."""
    frames = {(norm_path(fr['file'], str(root)) or fr['file'], fr['line'])
              for f in parse_report(rep, 't.py')['failures'] for fr in f['frames']}
    return [c for c in cands if (c['file'], c['line']) in frames]


def assert_ranked(cands):
    """Scores and reasons come from the ranking, not from the bare stack fallback."""
    for c in cands:
        assert isinstance(c['score'], float) and round(c['score'], 3) == c['score']
        assert isinstance(c['reasons'], list) and c['reasons'] and c['reasons'] != ['stack']
        assert all(isinstance(r, str) for r in c['reasons'])


def test_stack_frames_only_is_report_only(repo):
    rep = report(block('KeyError: k', 'pkg/m.py:4', 'pkg/m.py:9 → pkg/m.py:4'))
    s = Session(Fake(run_test=ok(FAIL_OUT, 1), test_report=rep), str(repo))
    s.run('run_test', {'path': 't.py'})
    s.run('test_report', {'path': 't.py'})
    f = s.finding('t.py')
    assert (f['status'], f['source']) == ('not_found', 'report_only')
    assert f['exception'] == {'type': 'KeyError', 'message': 'k'}
    mine = stack_part(f['candidates'], rep, repo)
    assert [(c['file'], c['line']) for c in mine] == [('pkg/m.py', 4), ('pkg/m.py', 9)]
    assert_ranked(mine)
    assert f['candidates'][0]['snippet'][0]['line'] == 2
    assert state(s)['cause'] == 'no'


def test_paths_normalised_and_outside_root_not_read(repo, tmp_path_factory):
    other = tmp_path_factory.mktemp('sibling') / 'x.py'
    other.write_text(SOURCE)
    absolute = str(repo / 'pkg' / 'm.py')
    rep = report(block('ValueError: v', 'pkg/./m.py:3', absolute + ':3 → pkg/./m.py:3'),
                 )
    s = Session(Fake(run_test=ok(FAIL_OUT, 1), test_report=rep), str(repo))
    s.run('run_test', {'path': 't.py'})
    s.run('test_report', {'path': 't.py'})
    cands = s.finding('t.py')['candidates']
    assert [(c['file'], c['line']) for c in cands] == [('pkg/m.py', 3)]
    assert cands[0]['snippet']
    rep2 = report(block('ValueError: v', '%s:2' % other))
    s2 = Session(Fake(run_test=ok(FAIL_OUT, 1), test_report=rep2), str(repo))
    s2.run('run_test', {'path': 't.py'})
    s2.run('test_report', {'path': 't.py'})
    c = s2.finding('t.py')['candidates'][0]
    assert c['file'] == str(other) and c['snippet'] == []


def test_new_round_clears_previous_evidence(repo):
    rep = report(block('ValueError: v', 'pkg/m.py:3'))
    s = Session(Fake(run_test=ok(FAIL_OUT, 1), test_report=rep), str(repo))
    s.run('run_test', {'path': 't.py'})
    s.run('test_report', {'path': 't.py'})
    assert s.finding('t.py')['candidates']
    s.run('run_test', {'path': 't.py'})
    row = state(s)
    assert (row['report'], row['locate'], row['probe'], row['cause']) == ('no',) * 4
    f = s.finding('t.py')
    assert (f['candidates'], f['exception'], f['source']) == ([], None, None)
    assert [c['name'] for c in s.calls] == ['run_test', 'test_report', 'run_test']


def test_unseen_file_and_long_message():
    s = Session(Fake(run_test=ok(FAIL_OUT, 1), test_report=report(block('ValueError: ' + 'm' * 400, 'a.py:1'))))
    assert s.finding('zz.py') == {'file': 'zz.py', 'status': 'not_found', 'source': None,
                                  'failed_tests': [], 'exception': None, 'candidates': []}
    s.run('run_test', {'path': 't.py'})
    s.run('test_report', {'path': 't.py'})
    msg = s.finding('t.py')['exception']['message']
    assert len(msg) == 300 and msg.endswith('...')


# ---- locate / probe / auto probe ----

def loc_out(*rows):
    return ok('locate t.py：header\n' + ''.join(' %d. %s\n' % (i, r) for i, r in enumerate(rows, 1)))


def prb_out(*items):
    """items: (at, expr, value) triples; one '== at' header per item."""
    return ok('probe t.py\n' + ''.join('== %s | x\n  #1 %s = %s\n' % t for t in items))


SPREAD = loc_out('pkg/m.py:3  0.9  失败 1/1  通过 0/1  | x', 'pkg/m.py:8  0.1  失败 1/1  通过 1/1  | y')
TIED = loc_out('pkg/m.py:3  0.5  失败 1/1  通过 0/1  | x', 'pkg/m.py:4  0.5  失败 1/1  通过 0/1  | y')
EMPTY_LOC = loc_out()
ZERO_LOC = loc_out('pkg/m.py:3  0.0  失败 0/1  通过 1/1  | x', 'pkg/m.py:4  0.0  失败 0/1  通过 1/1  | y')
FRAME_REPORT = report(block('ValueError: x', 'pkg/m.py:3'))
NOFRAME_REPORT = ok('test_report t.py：\n[1] 失败 T.test_a\n    ValueError: x\n')


def names(s):
    return [c['name'] for c in s.calls]


def play(repo, locate, rep=NOFRAME_REPORT, probe=None, **kw):
    script = dict(run_test=ok(FAIL_OUT, 1), test_report=rep, locate=locate)
    if probe is not None:
        script['probe'] = probe
    fake = Fake(**script)
    s = Session(fake, str(repo), **kw)
    for n in ('run_test', 'test_report', 'locate'):
        s.run(n, {'path': 't.py'})
    return s, fake


def test_locate_found(repo):
    s, fake = play(repo, SPREAD, FRAME_REPORT)
    f = s.finding('t.py')
    assert (f['status'], f['source']) == ('found', 'locate')
    assert 1 <= len(f['candidates']) <= 5
    for c in f['candidates']:
        assert {'file', 'line', 'score', 'reasons', 'snippet', 'probe'} <= set(c)
    assert names(s) == ['run_test', 'test_report', 'locate']
    assert [n for n, _ in fake.seen] == names(s)
    assert state(s)['locate'] == 'yes' and state(s)['cause'] == 'yes' and state(s)['probe'] == 'no'
    assert json.dumps(f)


@pytest.mark.parametrize('loc', [EMPTY_LOC, ZERO_LOC])
def test_locate_without_valid_lines_is_report_only(repo, loc):
    s, _ = play(repo, loc, FRAME_REPORT)
    f = s.finding('t.py')
    assert (f['status'], f['source']) == ('not_found', 'report_only')
    mine = stack_part(f['candidates'], FRAME_REPORT, repo)
    assert [(c['file'], c['line']) for c in mine] == [('pkg/m.py', 3)]
    assert_ranked(mine)
    row = state(s)
    assert (row['locate'], row['cause'], row['probe']) == ('yes', 'no', 'no')
    assert names(s) == ['run_test', 'test_report', 'locate']


def test_locate_bad_result_keeps_progress(repo):
    s, _ = play(repo, RuntimeError('boom'), FRAME_REPORT)
    assert state(s)['locate'] == 'no' and state(s)['cause'] == 'no'
    assert s.calls[-1]['status'] == 'error' and s.calls[-1]['exit_code'] is None
    assert s.finding('t.py')['source'] == 'report_only'


class Probing(Fake):
    """Fake that keeps the arguments each probe call received."""

    def __init__(self, **script):
        super().__init__(**script)
        self.probe_args = []

    def __call__(self, name, args):
        if name == 'probe':
            self.probe_args.append(args)
        return super().__call__(name, args)


def test_explicit_probe_found_and_arguments(repo):
    fake = Probing(run_test=ok(FAIL_OUT, 1), test_report=FRAME_REPORT, locate=EMPTY_LOC,
                   probe=prb_out(('pkg/./m.py:3', 'line3', '3')))
    s = Session(fake, str(repo))
    for n in ('run_test', 'test_report', 'locate'):
        s.run(n, {'path': 't.py'})
    assert names(s) == ['run_test', 'test_report', 'locate']
    s.run('probe', {'path': 't.py'})
    sent = fake.probe_args[0]
    assert set(sent) == {'path', 'at', 'exprs'} and sent['path'] == 't.py'
    assert 1 <= len(sent['at']) <= 8 and 1 <= len(sent['exprs']) <= 8
    assert all(re.fullmatch(r'.+:\d+', a) for a in sent['at'])
    assert all(safe_expr(e) for e in sent['exprs'])
    f = s.finding('t.py')
    assert (f['status'], f['source']) == ('found', 'probe')
    assert f['candidates'] and all(c['probe'] for c in f['candidates'])
    assert f['candidates'][0]['probe'][0]['value'] == '3'
    assert state(s)['probe'] == 'yes' and state(s)['cause'] == 'yes'


@pytest.mark.parametrize('values', [
    prb_out(('pkg/m.py:7', 'line3', '3')),           # position not sent
    prb_out(('pkg/m.py:3', 'zzz', '3')),             # expression not sent
    prb_out(('other/x.py:3', 'line3', '3')),         # file not sent
    ok(''), ok('probe: failed', 1)])
def test_explicit_probe_unmatched_is_report_only(repo, values):
    s, _ = play(repo, EMPTY_LOC, FRAME_REPORT, probe=values)
    r = s.run('probe', {'path': 't.py'})
    assert r == values
    f = s.finding('t.py')
    assert (f['status'], f['source']) == ('not_found', 'report_only')
    mine = stack_part(f['candidates'], FRAME_REPORT, repo)
    assert len(mine) == 1
    assert_ranked(mine)
    assert state(s)['probe'] == 'yes' and state(s)['cause'] == 'no'


def test_probe_no_points_short_circuits(repo):
    s, fake = play(repo, EMPTY_LOC, NOFRAME_REPORT, probe=prb_out(('pkg/m.py:3', 'line3', '3')))
    r = s.run('probe', {'path': 't.py'})
    assert (r['status'], r['exit_code'], r['output']) == ('error', 1, 'no probe points')
    assert 'probe' not in [n for n, _ in fake.seen] and names(s) == ['run_test', 'test_report', 'locate']
    assert state(s)['probe'] == 'yes'


def test_unrunnable_without_location_makes_no_real_calls(repo):
    fake = Fake(run_test=ok('collect error', 2), test_report=ok(UNRUNNABLE), locate=SPREAD,
                probe=prb_out(('pkg/m.py:3', 'line3', '3')))
    s = Session(fake, str(repo))
    s.run('run_test', {'path': 't.py'})
    s.run('test_report', {'path': 't.py'})
    r1 = s.run('locate', {'path': 't.py'})
    r2 = s.run('probe', {'path': 't.py'})
    assert r1 == {'status': 'ok', 'exit_code': 0, 'output': 'skipped: test cannot run'}
    assert r2 == {'status': 'error', 'exit_code': 1, 'output': 'skipped: test cannot run'}
    assert [n for n, _ in fake.seen] == ['run_test', 'test_report'] == names(s)
    f = s.finding('t.py')
    assert (f['status'], f['source']) == ('not_found', 'unrunnable')
    row = state(s)
    assert (row['locate'], row['probe'], row['cause']) == ('yes', 'yes', 'no')


def test_unrunnable_with_location_also_skips_locate(repo):
    rep = ok(UNRUNNABLE + '  位置 pkg/m.py:5 (<module>)\n')
    fake = Fake(run_test=ok('collect error', 2), test_report=rep, locate=SPREAD)
    s = Session(fake, str(repo))
    for n in ('run_test', 'test_report', 'locate'):
        s.run(n, {'path': 't.py'})
    assert [n for n, _ in fake.seen] == ['run_test', 'test_report']
    f = s.finding('t.py')
    assert (f['status'], f['source']) == ('found', 'unrunnable')


def test_tie_triggers_auto_probe(repo):
    probe = prb_out(('pkg/m.py:3', 'line3', '3'), ('pkg/m.py:9', 'line3', '3'),
                    ('pkg/m.py:4', 'zzz', '4'))
    fake = Probing(run_test=ok(FAIL_OUT, 1), test_report=NOFRAME_REPORT, locate=TIED, probe=probe)
    s = Session(fake, str(repo))
    for n in ('run_test', 'test_report', 'locate'):
        s.run(n, {'path': 't.py'})
    assert names(s) == ['run_test', 'test_report', 'locate', 'probe']
    args = fake.probe_args[0]
    assert set(args) == {'path', 'at', 'exprs'} and args['path'] == 't.py'
    assert 'pkg/m.py:3' in args['at'] and 'pkg/m.py:4' in args['at']
    f = s.finding('t.py')
    assert (f['status'], f['source']) == ('found', 'locate')
    probed = {c['line']: c['probe'] for c in f['candidates']}
    assert probed[3] == [{'expr': 'line3', 'value': '3'}]      # matched value reranks
    assert probed[4] == []                                      # unmatched expr discarded
    assert state(s)['probe'] == 'no'                            # auto probe does not touch progress


def test_tie_probe_not_allowed(repo):
    probe = prb_out(('pkg/m.py:3', 'line3', '3'))
    s, fake = play(repo, TIED, probe=probe, allow_probe=False)
    assert names(s) == ['run_test', 'test_report', 'locate']
    assert s.finding('t.py')['source'] == 'locate'
    r = s.run('probe', {'path': 't.py'})
    assert (r['status'], r['exit_code'], r['output']) == ('error', 1, 'probe not allowed')
    assert [n for n, _ in fake.seen] == names(s) and state(s)['probe'] == 'yes'


@pytest.mark.parametrize('bad', [ok('refused', 1), RuntimeError('boom'), None,
                                 prb_out(('pkg/m.py:9', 'line3', '3'))])
def test_rejected_auto_probe_keeps_locate_scores(repo, bad):
    base, _ = play(repo, TIED, allow_probe=False)
    s, _ = play(repo, TIED, probe=bad)
    assert names(s) == ['run_test', 'test_report', 'locate', 'probe']
    f = s.finding('t.py')
    assert (f['status'], f['source']) == ('found', 'locate')
    seq = lambda x: [(c['file'], c['line'], c['score']) for c in x['candidates']]
    assert seq(f) == seq(base.finding('t.py'))


def test_new_round_replaces_locate_candidates(repo):
    (repo / 'pkg' / 'n.py').write_text(SOURCE)
    r1 = report(block('ValueError: e1', 'pkg/m.py:3'))
    r2 = report(block('KeyError: e2', 'pkg/n.py:3'))
    fake = Fake(run_test=ok(FAIL_OUT, 1), test_report=[r1, r2],
                locate=[loc_out('pkg/m.py:3  0.9  失败 1/1  通过 0/1  | x'),
                        loc_out('pkg/n.py:3  0.9  失败 1/1  通过 0/1  | x')])
    s = Session(fake, str(repo))
    for _ in range(2):
        for n in ('run_test', 'test_report', 'locate'):
            s.run(n, {'path': 't.py'})
    f = s.finding('t.py')
    assert f['exception']['type'] == 'KeyError'
    assert f['candidates'] and {c['file'] for c in f['candidates']} == {'pkg/n.py'}
    assert (f['status'], f['source']) == ('found', 'locate')
    assert len(s.calls) == 6


def test_locate_lines_merge_equivalent_paths(repo):
    absolute = str(repo / 'pkg' / 'm.py')
    loc = loc_out('pkg/./m.py:3  0.9  失败 1/1  通过 0/1  | x', '%s:3  0.9  失败 1/1  通过 0/1  | x' % absolute)
    s, _ = play(repo, loc, FRAME_REPORT)
    f = s.finding('t.py')
    assert [(c['file'], c['line']) for c in f['candidates']] == [('pkg/m.py', 3)]
    assert f['candidates'][0]['snippet']


def test_session_source_has_no_gap_literal():
    from pathlib import Path
    import planbot.diag.session as mod
    assert '0.05' not in Path(mod.__file__).read_text()


# ---- diagnose / summarize / exports ----

import ast
import subprocess
import sys
from pathlib import Path

from planbot import PlanbotError
from planbot.diag import diagnose, summarize

DOMAIN = str(Path(__file__).resolve().parent.parent / 'examples' / 'diagnose' / 'domain.json')
COLLECT = ok(UNRUNNABLE + '  位置 pkg/m.py:5 (<module>)\n')
RED = ok(FAIL_OUT, 1)


def diag(repo, execute=True, runner=None, domain=DOMAIN, test_file='t.py', **kw):
    return diagnose(domain, test_file, runner, execute=execute, repo_root=str(repo), **kw)


def seen(fake):
    return [n for n, _ in fake.seen]


def domain_copy(tmp_path, edit):
    data = json.loads(Path(DOMAIN).read_text())
    edit(data)
    path = tmp_path / 'd.json'
    path.write_text(json.dumps(data))
    return str(path)


def test_diagnose_passed(repo):
    fake = Fake(run_test=ok('1 passed'))
    out = diag(repo, runner=fake)
    f = out['finding']
    assert (f['status'], f['source'], f['candidates']) == ('passed', None, [])
    assert [c['name'] for c in out['calls']] == ['run_test'] and seen(fake) == ['run_test']
    assert out['report']['status'] == 'done'


def test_diagnose_locate_found_and_summary(repo):
    out = diag(repo, runner=Fake(run_test=RED, test_report=FRAME_REPORT, locate=SPREAD))
    assert [c['name'] for c in out['calls']] == ['run_test', 'test_report', 'locate']
    assert (out['finding']['status'], out['finding']['source']) == ('found', 'locate')
    assert out['report']['status'] == 'done'
    text = summarize(out['finding'])
    lines = text.split('\n')
    assert lines[0] == 'status: found (source: locate)' and lines[-1].startswith('hint: ')
    for part in ('failed: ', 'exception: ', 'candidates:', 'pkg/m.py:3', '>> 3 | '):
        assert part in text
    assert 'tree:' not in text and '[method:' not in text and len(text) <= 2500


def test_diagnose_unrunnable(repo):
    out = diag(repo, runner=Fake(run_test=ok('collect error', 2), test_report=COLLECT))
    assert [c['name'] for c in out['calls']] == ['run_test', 'test_report']
    assert (out['finding']['status'], out['finding']['source']) == ('found', 'unrunnable')
    assert out['report']['status'] == 'done'
    fake = Fake(run_test=ok('collect error', 2), test_report=ok(UNRUNNABLE), locate=SPREAD,
                probe=prb_out(('pkg/m.py:3', 'line3', '3')))
    out = diag(repo, runner=fake)
    assert seen(fake) == ['run_test', 'test_report']
    assert (out['finding']['status'], out['finding']['source']) == ('not_found', 'unrunnable')
    assert out['report']['status'] == 'stuck'


@pytest.mark.parametrize('bad', [RuntimeError('boom'), {}, {'status': 'ok', 'exit_code': '0', 'output': 'x'}, None])
def test_diagnose_bad_report_is_no_progress(repo, bad):
    fake = Fake(run_test=RED, test_report=bad)
    out = diag(repo, runner=fake)
    stuck = out['report']['stuck']
    assert out['report']['status'] == 'stuck' and stuck['reason'] == 'no_progress'
    assert stuck['step'] == 'test_report(t.py)' and seen(fake).count('test_report') == 1


def test_diagnose_probe_permission(repo, tmp_path):
    def probes(**kw):
        fake = Fake(run_test=RED, test_report=NOFRAME_REPORT, locate=TIED, probe=ok(''))
        diag(repo, runner=fake, **kw)
        return 'probe' in seen(fake)
    assert probes() is True
    assert probes(allow=['run_test', 'test_report', 'locate']) is False
    irreversible = domain_copy(tmp_path, lambda d: d['actions'][3].update(irreversible=True))
    assert probes(domain=irreversible) is False


def test_diagnose_locate_empty_without_probe(repo):
    out = diag(repo, runner=Fake(run_test=RED, test_report=FRAME_REPORT, locate=EMPTY_LOC),
               allow=['run_test', 'test_report', 'locate'])
    assert (out['finding']['status'], out['finding']['source']) == ('not_found', 'report_only')


def test_diagnose_dry_run(repo):
    fake = Fake(run_test=RED)
    out = diag(repo, execute=False, runner=fake)
    assert fake.seen == [] and out['calls'] == [] and 'plan' in out['report']
    assert out['finding']['status'] == 'not_found' and out['finding']['source'] is None


def test_diagnose_shape_checked_before_observing(repo, tmp_path):
    sensor = {'name': 'x', 'run': {'cmd': {'name': 'other', 'args': {}}}, 'extract': []}
    action = {'name': 'extra', 'params': ['f'], 'pre': [], 'add': [], 'del': [],
              'run': {'cmd': {'name': 'other', 'args': {'path': '{f}'}}}}
    for edit in (lambda d: d['sensors'].append(sensor), lambda d: d['actions'].append(action)):
        fake = Fake(run_test=RED)
        with pytest.raises(PlanbotError) as err:
            diag(repo, runner=fake, domain=domain_copy(tmp_path, edit))
        assert err.value.code == 'DOMAIN_INVALID' and fake.seen == []


def test_diagnose_errors(repo):
    fake = Fake(run_test=RED)

    def code(**kw):
        with pytest.raises(PlanbotError) as err:
            diag(repo, **dict(dict(runner=fake), **kw))
        return err.value.code
    assert code(domain=str(repo / 'nope.json')) == 'DOMAIN_INVALID'
    for name in ('', 'a b.py', '\ud800.py'):
        assert code(test_file=name) == 'GOAL_INVALID'
    assert code(runner=None) == 'USAGE' and code(allow=['nope']) == 'USAGE'
    assert code(max_replans=-1) == 'USAGE'
    assert code(domain=str(repo / 'nope.json'), runner=None) == 'DOMAIN_INVALID'
    assert code(test_file='a b.py', runner=None) == 'GOAL_INVALID'
    assert fake.seen == []


def test_diagnose_is_deterministic(repo):
    def once():
        out = diag(repo, runner=Fake(run_test=RED, test_report=FRAME_REPORT, locate=SPREAD))
        return json.dumps(out, sort_keys=True)
    assert once() == once()


def finding_with(message='boom', candidates=None, failed=None):
    return {'file': 't.py', 'status': 'found', 'source': 'locate', 'failed_tests': failed or ['T.a'],
            'exception': {'type': 'ValueError', 'message': message}, 'candidates': candidates or []}


def cand(line, text='x', probe=None, n=5):
    snippet = [{'line': line + i - 2, 'text': text} for i in range(n)]
    return {'file': 'pkg/m.py', 'line': line, 'score': 0.5, 'reasons': ['r'], 'snippet': snippet,
            'probe': probe or []}


def test_summarize_escapes_newlines():
    plain = summarize(finding_with('abc')).split('\n')
    text = summarize(finding_with('a\nb\r\nc'))
    assert 'exception: ValueError: a\\nb\\r\\nc' in text and len(text.split('\n')) == len(plain)


def test_summarize_budgets():
    tests = ['%02d' % i + 'f' * 28 for i in range(40)]
    line = next(x for x in summarize(finding_with(failed=tests)).split('\n') if x.startswith('failed: '))
    body = line[len('failed: '):]
    m = re.search(r' \(\+(\d+) more\)$', body)
    listed = body[:m.start()].count(', ') + 1
    assert len(body) <= 300 and m and int(m.group(1)) + listed == 40
    row = next(x for x in summarize(finding_with(candidates=[cand(3, 'y' * 160)])).split('\n') if ' | y' in x)
    text = row.split(' | ', 1)[1]
    assert len(text) <= 100 and text.endswith('...')


def test_summarize_compression_keeps_hint_and_first_location():
    cands = [cand(10 + i, 'z' * 160, [{'expr': 'e', 'value': 'v' * 200}]) for i in range(5)]
    text = summarize(finding_with('m' * 5000, cands))
    lines = text.split('\n')
    assert len(text) <= 2500 and lines[-1].startswith('hint: ')
    assert '  1. pkg/m.py:10 score=0.500 [r]' in lines
    assert summarize(finding_with('\ud800')).encode('utf-8')
    for junk in ({}, None, {'candidates': [1, {'snippet': 'x', 'line': 'a'}], 'exception': 3, 'failed_tests': 'x'}):
        assert summarize(junk).startswith('status: ')
    assert summarize({'status': 'passed'}).endswith('hint: test passes, nothing to fix.')


def test_exports_and_static_imports():
    root = Path(__file__).resolve().parent.parent
    for name in ('session.py', '__init__.py'):
        text = (root / 'planbot' / 'diag' / name).read_text()
        for word in ('truth', 'os.path.realpath', 'relpath', 'commonpath'):
            assert word not in text
        for node in ast.walk(ast.parse(text)):
            mods = ([a.name for a in node.names] if isinstance(node, ast.Import)
                    else [node.module] if isinstance(node, ast.ImportFrom) and node.level == 0 else [])
            assert all(m.split('.')[0] in sys.stdlib_module_names | {'planbot'} for m in mods)
    code = 'import sys, planbot; print("planbot.diag" in sys.modules)'
    run = subprocess.run([sys.executable, '-c', code], cwd=root, capture_output=True, text=True)
    assert run.stdout.strip() == 'False'
