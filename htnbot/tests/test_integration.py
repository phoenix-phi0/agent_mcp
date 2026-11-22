import json
from pathlib import Path

from planbot import core
from planbot.cli import main
from test_examples_release import git, repos  # noqa: F401
import test_baseline_unchanged
import test_generality

ROOT = Path(__file__).resolve().parent.parent
REL = str(ROOT / 'examples' / 'release' / 'domain.json')
SVC = str(ROOT / 'examples' / 'services' / 'domain.json')
sim = core.load_python(str(ROOT / 'examples' / 'services' / 'sim.py'))
CHAIN = {'web': ['api'], 'api': ['db'], 'db': []}


def run(capsys, *argv):
    code = main(list(argv))
    cap = capsys.readouterr()
    return code, cap.out, cap.err


def commits(repo):
    return int(git(repo, 'rev-list', '--all', '--count').strip())


def plan_lines(out):
    return [ln for ln in out.splitlines() if ln.startswith('  ') and '. start(' in ln]


def test_release_dry_run_execute_repeat(repos, capsys):
    """场景:真实仓库的发布:空跑 → 执行 → 重复执行"""
    tmp, remote, work = repos
    (work / 'new.txt').write_text('x\n')
    base = commits(remote)
    argv = ['run', '--domain', REL, '--cwd', str(work), '--goal', 'published()',
            '--allow-irreversible', 'push', '--memory-file', str(tmp / 'm.json')]
    code, out, _ = run(capsys, *argv)
    assert code == 0 and 'dirty()' in out
    assert 'plan: 2 steps' in out and '1. commit()' in out and '2. push() [irreversible]' in out
    assert ' -- ' in out and out.rstrip().endswith('mode: dry-run')
    assert commits(remote) == base
    code, out, _ = run(capsys, *argv, '--execute')
    assert code == 0 and 'status: done' in out
    assert commits(remote) == base + 1
    code, out, _ = run(capsys, *argv, '--execute')
    assert code == 0 and 'status: already_satisfied' in out
    assert commits(remote) == base + 1


def test_irreversible_requires_explicit_allow(repos, capsys):
    """场景:不可撤销动作必须显式允许"""
    tmp, remote, work = repos
    (work / 'new.txt').write_text('x\n')
    before = (commits(work), commits(remote))
    for argv in (['explain', '--goal', 'published()'],
                 ['run', '--execute', '--goal', 'published()', '--allow', 'commit,sync',
                  '--memory-file', str(tmp / 'm.json')]):
        code, out, _ = run(capsys, argv[0], '--domain', REL, '--cwd', str(work), '--json', *argv[1:])
        failure = json.loads(out)['plan']['failure']
        assert code == 1
        assert failure['kind'] == 'no_producer'
        assert 'push' in failure['details'][0]['excluded']
    assert (commits(work), commits(remote)) == before


def _svc(capsys, fault_times):
    sim.reset(CHAIN)
    sim.set_fault('start', 'api', fault_times)
    return run(capsys, 'run', '--domain', SVC, '--goal', 'running(web)', '--execute', '--json',
               '--max-replans', '3', '--no-memory')


def test_mismatch_replan_then_limit(capsys):
    """场景:效果与预期不符时重排,到上限停下并报告"""
    code, out, _ = _svc(capsys, 1)
    rep = json.loads(out)
    assert code == 0 and rep['status'] == 'done' and rep['replans'] == 1
    bad = [e for e in rep['executed'] if not e['matched']]
    assert len(bad) == 1 and bad[0]['missing'] == ['running(api)']
    assert 'running(web)' in rep['final_facts']
    code, out, _ = _svc(capsys, 99)
    rep = json.loads(out)
    assert code == 1 and rep['status'] == 'stuck'
    assert rep['stuck']['reason'] == 'replan_limit' and rep['replans'] == 3
    assert rep['stuck']['step'] == 'start(api)'
    assert rep['stuck']['missing'] == ['running(api)']


def test_procedure_memory_lifecycle(capsys, tmp_path):
    """场景:规程记忆:存、取、校验、关闭、列出、清除"""
    mem = str(tmp_path / 'm.json')
    base = ['run', '--domain', SVC, '--goal', 'running(web)', '--memory-file', mem]
    sim.reset(CHAIN)
    assert run(capsys, *base, '--execute')[0] == 0
    code, out, _ = run(capsys, 'memory', 'list', '--memory-file', mem)
    assert code == 0 and len(out.strip().splitlines()) == 1
    sim.reset(CHAIN)
    _, out, _ = run(capsys, *base)
    assert 'source: memory' in out
    same = plan_lines(out)
    assert len(same) == 3
    sim.reset(CHAIN, running=['db'])
    _, out, _ = run(capsys, *base)
    assert 'source: search' in out
    sim.reset(CHAIN)
    _, out, _ = run(capsys, *base, '--no-memory')
    assert 'source: search' in out and plan_lines(out) == same
    _, out, _ = run(capsys, 'memory', 'clear', '--memory-file', mem)
    assert out.strip() == 'cleared 1'
    _, out, _ = run(capsys, 'memory', 'list', '--memory-file', mem)
    assert out.strip() == '(empty)'


def test_engine_generality(repos):
    """场景:引擎通用性"""
    test_generality.test_both_domains_dry_run_in_same_process(repos)
    test_generality.test_engine_source_has_no_domain_vocabulary()


def test_determinism_and_search_limit(capsys):
    """场景:确定性与搜索上限"""
    for extra in ([], ['--json']):
        outs = []
        for _ in range(2):
            sim.reset(CHAIN)
            code, out, _ = run(capsys, 'run', '--domain', SVC, '--goal', 'running(web)',
                               '--no-memory', *extra)
            assert code == 0
            outs.append(out)
        assert outs[0] == outs[1]
    sim.reset(CHAIN)
    code, out, _ = run(capsys, 'explain', '--domain', SVC, '--goal', 'running(web)', '--max-nodes', '1')
    assert code == 1 and 'no plan: limit' in out and 'search limit 1 reached' in out


# ---- HTN scenarios ----
from planbot import executor, planner, runtime
from test_examples_diagnose import make_fake, DOMAIN as DIAG

TASK = ['--task', 'diagnose(t_a.py)']


def dmain(capsys, runner, *argv):
    code = main(list(argv), cmd_runner=runner)
    cap = capsys.readouterr()
    return code, cap.out, cap.err


def test_htn_dry_run_only_tree_and_actions(capsys):
    """场景:HTN 空跑:只输出分解树与动作序列,不执行"""
    runner, calls = make_fake({'t_a.py': {'run_test': 'green'}})
    code, out, _ = dmain(capsys, runner, 'task', '--domain', DIAG, *TASK, '--no-memory')
    lines = out.splitlines()
    assert code == 0 and lines[0] == 'task: diagnose(t_a.py)' and 'facts:' not in out
    assert 'tree:' in lines and any('[method: first_run]' in ln for ln in lines)
    assert any(ln.strip() == 'why: not test_ran(t_a.py)' for ln in lines)
    assert any('skipped already_green: precondition: test_green(t_a.py)' in ln for ln in lines)
    assert any(ln.strip() == '1. run_test(t_a.py)' for ln in lines)
    assert 'plan: 1 steps (source: decompose)' in lines and '  1. run_test(t_a.py)' in lines
    assert lines[-1] == 'mode: dry-run'
    assert {c[0] for c in calls} == {'diag_state'}
    code, out, _ = dmain(capsys, runner, 'task', '--domain', DIAG, *TASK, '--no-memory', '--json')
    data = json.loads(out)
    assert code == 0 and set(data) == {'mode', 'plan', 'task'} and data['plan']['tree'] and data['plan']['steps']
    code, out, _ = dmain(capsys, runner, 'explain', '--domain', DIAG, *TASK)
    assert code == 0 and out.startswith('task: diagnose(t_a.py)') and 'tree:' in out
    assert 'mode:' not in out and 'facts:' not in out
    assert {c[0] for c in calls} == {'diag_state'}
    domain = core.load_domain(DIAG, cmd_runner=runner)
    res = executor.dry_run_task(domain, ('diagnose', 't_a.py'), planner.allowed_actions(domain, None, None))
    assert 'facts' in res


def test_htn_backtrack_and_permissions(capsys):
    """场景:HTN 方法回溯与权限"""
    st = {'t_a.py': {'ran': 'yes', 'result': 'red'}}
    runner, calls = make_fake({'t_a.py': {'run_test': 'red'}}, st)
    code, out, _ = dmain(capsys, runner, 'task', '--domain', DIAG, *TASK, '--no-memory')
    assert code == 0
    assert 'skipped already_green' in out and 'skipped first_run' in out and '[method: investigate]' in out
    assert '[method: by_locate]' in out
    assert '  1. test_report(t_a.py)' in out and '  2. locate(t_a.py)' in out
    for cmd in (['task', '--no-memory'], ['explain']):
        runner, calls = make_fake({'t_a.py': {}}, st)
        code, out, _ = dmain(capsys, runner, *cmd, '--domain', DIAG, *TASK,
                             '--allow', 'run_test,test_report')
        assert code == 1 and 'no decomposition: no_method' in out
        assert 'investigate' in out and 'find_cause(t_a.py)' in out
        assert 'skipped by_locate: not_allowed: locate' in out
        assert {c[0] for c in calls} == {'diag_state'}


def test_htn_execute_resume_after_completed_children(capsys):
    """场景:HTN 执行:效果不符后从已完成子项之后恢复(领域三两次恢复)"""
    runner, calls = make_fake({'t_a.py': {'run_test': 'red', 'locate': False, 'probe': True}})
    code, out, _ = dmain(capsys, runner, 'task', '--domain', DIAG, *TASK, '--execute', '--no-memory')
    assert code == 0 and 'status: done' in out and 'replans: 2' in out
    ex = [ln.strip() for ln in out.split('executed:')[1].split('replans:')[0].strip().splitlines()]
    assert len(ex) == 4
    assert ex[0].startswith('1. run_test(t_a.py) MISMATCH missing: test_green(t_a.py)') and '(failed)' in ex[0]
    assert ex[1].startswith('2. test_report(t_a.py) ok')
    assert ex[2].startswith('3. locate(t_a.py) MISMATCH missing: cause_found(t_a.py)')
    assert ex[3].startswith('4. probe(t_a.py) ok')
    assert all(' @ ' in e for e in ex)
    assert ex[3].endswith(' @ diagnose(t_a.py)#0 > find_cause(t_a.py)#1')
    assert ('redo diagnose(t_a.py)#0 after step 1 (mismatch: run_test(t_a.py)): '
            'test_report(t_a.py) ; locate(t_a.py)') in out
    assert ('redo find_cause(t_a.py)#1 after step 3 (mismatch: locate(t_a.py)): '
            'probe(t_a.py)') in out
    names = [c[0] for c in calls if c[0] != 'diag_state']
    assert sorted(names) == ['locate', 'probe', 'run_test', 'test_report']
    runner, calls = make_fake({'t_a.py': {'run_test': 'red', 'locate': False, 'probe': False}})
    code, out, _ = dmain(capsys, runner, 'task', '--domain', DIAG, *TASK, '--execute', '--no-memory')
    assert code == 1 and 'status: stuck' in out
    assert 'stuck at: probe(t_a.py) (no_plan) in diagnose(t_a.py)#0 > find_cause(t_a.py)#1' in out
    assert 'trigger: mismatch probe(t_a.py)' in out and 'skipped by_locate' in out


def _pack(tmp_path, name, actions, methods, preds, derived=(), goals=()):
    (tmp_path / 'cb.py').write_text('CALLBACKS = {}\n')
    data = {'name': name, 'python': 'cb.py', 'predicates': preds, 'derived': list(derived),
            'goals': list(goals),
            'sensors': [{'name': 's', 'run': {'callback': 'sense'},
                         'extract': [{'type': 'regex', 'pattern': r'^(.+)$', 'facts': ['{1}']}]}],
            'actions': actions, 'tasks': [{'name': 'T', 'params': []}], 'methods': methods}
    p = tmp_path / (name + '.json')
    p.write_text(json.dumps(data))
    return str(p)


def _act(name, pre=(), add=()):
    return {'name': name, 'params': [], 'pre': list(pre), 'add': list(add), 'del': [],
            'run': {'callback': name}, 'irreversible': False}


def _meth(name, subtasks, pre=()):
    return {'name': name, 'task': 'T', 'params': [], 'pre': list(pre), 'subtasks': subtasks}


def _exec(path, store, cbs, max_replans=3):
    counts = {}

    def mk(n):
        def f(binding, ctx):
            counts[n] = counts.get(n, 0) + 1
            cbs[n](store, counts[n])
        return f
    cb = {n: mk(n) for n in cbs}
    cb['sense'] = lambda ctx: '\n'.join(sorted(store))
    d = core.load_domain(path, callbacks=cb)
    rep = executor.execute_task(d, ('T',), planner.allowed_actions(d, None, None), memory=None,
                                max_replans=max_replans)
    return rep, counts


def test_htn_switch_method_keeps_completed_prefix(tmp_path):
    """场景:恢复时换方法要接上已完成前缀(中性小领域包)"""
    def b_cb(s, n):
        s.add('m()')
    P = {'m': 0, 'da': 0, 'db': 0, 'dc': 0}
    acts = [_act('a', add=['da()']), _act('b', pre=['not m()'], add=['db()']), _act('c', add=['dc()'])]
    path = _pack(tmp_path, 'one', acts, [_meth('m1', ['a()', 'b()']), _meth('m2', ['a()', 'c()'])], P)
    rep, counts = _exec(path, set(), {'a': lambda s, n: s.add('da()'), 'b': b_cb,
                                      'c': lambda s, n: s.add('dc()')})
    assert rep['status'] == 'done' and rep['replans'] == 1
    assert [e['text'] for e in rep['executed']] == ['a()', 'b()', 'c()']
    assert counts == {'a': 1, 'b': 1, 'c': 1}

    path = _pack(tmp_path, 'two', [_act('x', add=['xa()']), _act('y', add=['py()'])],
                 [_meth('m1', ['x()', 'x()', 'y()'])], {'xa': 0, 'py': 0})

    def x_cb(s, n):
        if n == 2:
            s.discard('xa()')  # second call has no effect (and the state shows it)
        else:
            s.add('xa()')
    rep, counts = _exec(path, set(), {'x': x_cb, 'y': lambda s, n: s.add('py()')})
    assert rep['status'] == 'done' and counts == {'x': 3, 'y': 1}

    path = _pack(tmp_path, 'three', acts[:2], [_meth('m1', ['a()', 'b()'])], P)
    rep, counts = _exec(path, set(), {'a': lambda s, n: s.add('da()'), 'b': b_cb})
    assert rep['status'] == 'stuck' and rep['stuck']['reason'] == 'no_plan' and counts['a'] == 1


def test_htn_goal_node_completion_check(tmp_path):
    """场景:goal 节点完成检查(派生目标)"""
    acts = [_act('add_p', add=['p(x)']), _act('add_q', add=['q(x)']), _act('z', add=['dz()'])]
    meths = [_meth('m', [{'goal': ['ready(x)']}, 'z()'])]
    path = _pack(tmp_path, 'goalpack', acts, meths, {'p': 1, 'q': 1, 'dz': 0},
                 derived=[{'head': 'ready(?x)', 'body': ['p(?x)', 'q(?x)']}], goals=['ready'])

    def add_p(s, n):
        s.add('p(x)')
        if n == 1:
            s.discard('q(x)')
    rep, counts = _exec(path, {'q(x)'}, {'add_p': add_p, 'add_q': lambda s, n: s.add('q(x)'),
                                        'z': lambda s, n: s.add('dz()')})
    assert rep['executed'][0]['text'] == 'add_p()' and rep['executed'][0]['matched'] is True
    assert rep['replans'] == 1 and rep['status'] == 'done'
    assert rep['replanned'][0]['trigger']['kind'] == 'goal'
    assert rep['replanned'][0]['resume'].startswith('goal ')
    assert [e['text'] for e in rep['executed']] == ['add_p()', 'add_q()', 'z()']


def test_no_progress_stops(tmp_path, capsys):
    """场景:没有进展即停(中性小领域包 + 领域三)"""
    # (a) a never takes effect and changes no fact -> stuck right after the first recovery
    P = {'p': 0, 'f': 0}
    path = _pack(tmp_path, 'np_a', [_act('a', add=['p()'])], [_meth('m', ['a()'])], P)
    rep, counts = _exec(path, set(), {'a': lambda s, n: None}, max_replans=3)
    assert rep['status'] == 'stuck'
    assert rep['stuck']['reason'] == 'no_progress'
    assert rep['stuck']['step'] == 'a()'
    assert rep['stuck']['failure'] is None
    assert rep['replans'] == 1 and len(rep['replanned']) == 1
    assert rep['replanned'][0]['steps'][0] == 'a()'
    assert counts == {'a': 1}
    assert len(rep['executed']) == 1

    # (b) same scenario, but every useless run flips a marker fact -> runs to replan_limit
    path = _pack(tmp_path, 'np_b', [_act('a', add=['p()'])], [_meth('m', ['a()'])], P)
    rep, counts = _exec(path, set(), {'a': lambda s, n: s.symmetric_difference_update({'f()'})},
                        max_replans=3)
    assert rep['status'] == 'stuck'
    assert rep['stuck']['reason'] == 'replan_limit'
    assert rep['replans'] == 3
    assert counts == {'a': 4}

    # (c) m1=[w,x,b], m2=[w,x,x,c]; w breaks b's precondition, x leaves the state unchanged
    path = _pack(tmp_path, 'np_c',
                 [_act('w', add=['j()']), _act('x', add=['s()']), _act('b', pre=['h()'], add=['e()']),
                  _act('c', add=['e()'])],
                 [_meth('m1', ['w()', 'x()', 'b()']), _meth('m2', ['w()', 'x()', 'x()', 'c()'])],
                 {'j': 0, 'h': 0, 's': 0, 'e': 0})

    def w_cb(s, n):
        s.add('j()')
        s.discard('h()')
    rep, counts = _exec(path, {'h()', 's()'}, {'w': w_cb, 'x': lambda s, n: None,
                                                'b': lambda s, n: None,
                                                'c': lambda s, n: s.add('e()')})
    assert rep['status'] == 'done'
    assert rep['stuck'] is None
    assert [e['text'] for e in rep['executed']] == ['w()', 'x()', 'x()', 'c()']
    assert counts == {'w': 1, 'x': 2, 'c': 1}

    # (d) the (a) domain through the command line
    cli = tmp_path / 'cli'
    cli.mkdir()
    count_file = cli / 'count.txt'
    (cli / 'cb.py').write_text(
        'def sense(ctx):\n    return ""\n\n'
        'def act(binding, ctx):\n'
        '    with open(%r, "a") as handle:\n        handle.write("x")\n\n'
        'CALLBACKS = dict(sense=sense, act=act)\n' % str(count_file), encoding='utf-8')
    (cli / 'dom.json').write_text(json.dumps({
        'name': 'np_cli', 'python': 'cb.py', 'predicates': {'p': 0}, 'goals': ['p'],
        'sensors': [{'name': 's', 'run': {'callback': 'sense'},
                     'extract': [{'type': 'regex', 'pattern': r'^(.+)$', 'facts': ['{1}']}]}],
        'actions': [{'name': 'a', 'params': [], 'pre': [], 'add': ['p()'], 'del': [],
                     'run': {'callback': 'act'}}],
        'tasks': [{'name': 'T', 'params': []}],
        'methods': [{'name': 'm', 'task': 'T', 'params': [], 'pre': [], 'subtasks': ['a()']}],
    }), encoding='utf-8')
    code, out, err = run(capsys, 'task', '--domain', str(cli / 'dom.json'), '--task', 'T()',
                         '--execute', '--no-memory')
    assert code == 1 and err == ''
    assert 'stuck at: a() (no_progress) in T()#0' in out.splitlines()
    assert len(count_file.read_text()) == 1

    # (e) third domain: test_report changes no state -> no_progress at the goal node's child
    runner, _ = make_fake({'t_a.py': {'run_test': 'red'}})
    report_calls = []

    def inert_report(name, args):
        if name == 'test_report':
            report_calls.append(args)
            return {'status': 'ok', 'exit_code': 0, 'output': ''}
        return runner(name, args)
    code, out, err = dmain(capsys, inert_report, 'task', '--domain', DIAG, *TASK, '--execute',
                           '--no-memory')
    assert code == 1 and err == ''
    assert ('stuck at: test_report(t_a.py) (no_progress) in diagnose(t_a.py)#0 > '
            'goal has_report(t_a.py)#0') in out.splitlines()
    assert len(report_calls) == 1


def test_htn_task_memory_and_fingerprint(tmp_path, capsys):
    """场景:复合任务的规程记忆与指纹"""
    mem = str(tmp_path / 'mem.json')
    MF = ['--memory-file', mem]

    def go(*extra, domain=DIAG):
        runner, _ = make_fake({'t_a.py': {'run_test': 'green'}})
        return dmain(capsys, runner, 'task', '--domain', domain, *TASK, *MF, *extra)
    code, out, _ = go('--execute')
    assert code == 0 and 'status: done' in out
    _, out, _ = dmain(capsys, None, 'memory', 'list', *MF)
    assert out.strip() == 'test_triage: task diagnose(t_a.py) <- - => run_test(t_a.py)'
    _, out, _ = go()
    assert 'plan: 1 steps (source: memory)' in out and 'tree:' in out
    assert 'source: decompose' in go('--no-memory')[1]
    assert 'source: decompose' in go('--max-depth', '10')[1]
    assert 'source: decompose' in go('--allow', 'run_test,test_report,locate')[1]
    data = json.loads(Path(DIAG).read_text())
    data['methods'][1]['subtasks'] = [{'goal': ['test_ran(?f)']}]
    copy = tmp_path / 'copy.json'
    copy.write_text(json.dumps(data))
    assert 'source: decompose' in go(domain=str(copy))[1]
    sim.reset(CHAIN)
    mem2 = str(tmp_path / 'mem2.json')
    run(capsys, 'run', '--domain', SVC, '--goal', 'running(db)', '--execute', '--memory-file', mem2)
    entries = json.loads(Path(mem2).read_text())['entries']
    assert sorted(entries[0]) == ['domain', 'goal', 'predicates', 'start', 'steps']


def _tiny(tmp_path, name, cmd_sensor=True):
    data = {'name': 'tiny', 'python': 'cb.py', 'predicates': {'seen': 1, 'done': 1}, 'goals': [],
            'sensors': [{'name': 'cb', 'run': {'callback': 'cbs'}, 'extract': []}],
            'actions': [{'name': 'act', 'params': ['f'], 'pre': [], 'add': ['done(?f)'], 'del': [],
                         'run': {'cmd': {'name': 'doit', 'args': {'path': '{f}', 'l': ['{f}']}}},
                         'irreversible': False}],
            'tasks': [{'name': 't', 'params': ['f']}],
            'methods': [{'name': 'm', 'task': 't', 'params': ['f'], 'subtasks': ['act(?f)']}]}
    if cmd_sensor:
        data['sensors'].append({'name': 'cs', 'run': {'cmd': {'name': 'sense', 'args': {}}},
                                'extract': [{'type': 'regex', 'pattern': r'^(\w+)$', 'facts': ['seen({1})']}]})
    (tmp_path / 'cb.py').write_text('CALLBACKS = {"cbs": lambda ctx: ""}\n')
    p = tmp_path / name
    p.write_text(json.dumps(data))
    return str(p)


def test_htn_cmd_runner_injection_and_cwd(tmp_path, capsys):
    """场景:cmd 执行方式、注入与 cwd"""
    D = str(tmp_path / 'D')
    Path(D).mkdir()
    calls, ctxs = [], []

    def fake(*a, **k):
        assert not k and len(a) == 2
        calls.append(a)
        return {'status': 'ok', 'exit_code': 0, 'output': 'alpha\n' if a[0] == 'sense' else ''}
    path = _tiny(tmp_path, 'tiny.json')
    cbs = {'cbs': lambda ctx: ctxs.append(ctx) or ''}
    d = core.load_domain(path, callbacks=cbs, cmd_runner=fake)
    obs = runtime.observe(d, cwd=D)
    assert ctxs == [{'cwd': D}] and ('seen', 'alpha') in obs['base']
    runtime.run_action(d, 'act', ('sub/x.py',), cwd=D)
    want = ('doit', {'path': 'sub/x.py', 'l': ['sub/x.py']})
    assert calls[-1] == want
    calls.clear()
    dmain(capsys, fake, 'task', '--domain', path, '--task', 't(sub/x.py)', '--execute', '--cwd', D,
          '--no-memory')
    assert want in calls
    p2 = _tiny(tmp_path, 'nosensor.json', cmd_sensor=False)
    code, out, _ = dmain(capsys, None, 'task', '--domain', p2, '--task', 't(sub/x.py)', '--no-memory')
    assert code == 0
    code, out, err = dmain(capsys, None, 'task', '--domain', p2, '--task', 't(sub/x.py)',
                           '--execute', '--no-memory')
    assert code == 2 and 'error: USAGE:' in err and 'no cmd runner' in err and out == ''
    d = core.load_domain(path, callbacks=cbs)
    try:
        runtime.observe(d)
        assert False
    except core.PlanbotError as e:
        assert e.code == 'SENSOR_FAILED'


def test_htn_error_codes_priority_and_midrun_sensor_failure(capsys, tmp_path):
    """场景:错误码、优先级与执行中观察失败"""
    runner, calls = make_fake({'t_a.py': {'run_test': 'green'}})
    bad = tmp_path / 'bad.json'
    bad.write_text('{}')
    mem = tmp_path / 'badmem.json'
    mem.write_text('not json')
    cases = [(str(bad), 'diagnose(t_a.py)', [], 'DOMAIN_INVALID'),
             (DIAG, 'nope(x)', [], 'GOAL_INVALID'),
             (DIAG, 'diagnose(t_a.py)', ['--max-depth', '-1'], 'USAGE'),
             (DIAG, 'diagnose(t_a.py)', ['--memory-file', str(mem)], 'USAGE')]
    for dom, task, extra, name in cases:
        for js in ([], ['--json']):
            c, out, err = dmain(capsys, runner, 'task', '--domain', dom, '--task', task, *extra, *js)
            assert c == 2
            if js:
                assert json.loads(out)['error']['code'] == name
            else:
                assert out == '' and err.startswith('error: %s: ' % name)
    assert not calls
    for dom, task, expect in ((str(bad), 'nope(x)', 'DOMAIN_INVALID'), (DIAG, 'nope(x)', 'GOAL_INVALID'),
                              (DIAG, 'diagnose(t_a.py)', 'USAGE')):
        c, _, err = dmain(capsys, runner, 'task', '--domain', dom, '--task', task,
                          '--max-depth', '-1', '--memory-file', str(mem))
        assert c == 2 and err.startswith('error: %s:' % expect)
    inner, _ = make_fake({'t_a.py': {'run_test': 'green'}})
    n = {'obs': 0}

    def flaky(name, args):
        if name == 'diag_state':
            n['obs'] += 1
            if n['obs'] == 2:
                return {'status': 'error', 'exit_code': 1, 'output': ''}
        return inner(name, args)
    c, out, err = dmain(capsys, flaky, 'task', '--domain', DIAG, *TASK, '--execute', '--no-memory')
    assert c == 2 and 'SENSOR_FAILED' in err and 'after 1 executed step(s)' in err
    assert 'run_test(t_a.py)' in err and ' @ ' in err and 're-observe' in err
    runner, calls = make_fake({'t_a.py': {'run_test': 'red'}})
    c, out, _ = dmain(capsys, runner, 'task', '--domain', DIAG, *TASK, '--execute',
                      '--no-memory', '--max-replans', '0')
    assert c == 1 and 'status: stuck' in out and 'replan_limit' in out
    assert len([x for x in calls if x[0] != 'diag_state']) == 1


def test_determinism_third_domain_task_dry_run(capsys):
    """场景:确定性与搜索上限(第 3 步:领域三 task 空跑,文本和 --json 各两次逐字节相同)"""
    for extra in ([], ['--json']):
        results = []
        for _ in range(2):
            runner, calls = make_fake({'t_a.py': {'run_test': 'green'}})
            code, out, err = dmain(capsys, runner, 'task', '--domain', DIAG, *TASK, '--no-memory', *extra)
            assert {c[0] for c in calls} == {'diag_state'}
            results.append((code, out, err))
        assert results[0] == results[1]
        assert results[0][0] == 0 and results[0][1] and results[0][2] == ''
        assert results[0][1].encode('utf-8') == results[1][1].encode('utf-8')


BASELINE_MAIN = b'import sys\n\nfrom .cli import main\n\nsys.exit(main())\n'


def test_whole_suite_commands_scope():
    """场景:整体测试命令(导入扫描与规模约束由 test_generality 覆盖)"""
    test_generality.test_engine_imports_only_stdlib_or_itself()
    test_generality.test_test_source_is_at_most_twice_the_implementation()
    # planner.py (rule 1b exception) and its tests are pinned to baseline hashes.
    test_baseline_unchanged.test_planner_py_unchanged_from_baseline()
    test_baseline_unchanged.test_test_planner_py_unchanged_from_baseline()
    # __main__.py is byte-identical to the baseline copy (work/planbot1).
    assert (ROOT / 'planbot' / '__main__.py').read_bytes() == BASELINE_MAIN


# ---- 适配层场景(新增/改动) ----
import re

import pytest

from planbot.diag import Session, diagnose, summarize
from planbot.diag.replay import load_cases, main as replay_main
from planbot.diag.rank import rank as syn_rank
from test_diag_session_rules import (Script, ok, report_of, loc_of, FAIL_OUT, DOMAIN as DIAG_DOMAIN,
                                     LOCATED, FRAME, CASE_FAIL, CASE_PASS, BODY)


@pytest.fixture
def arepo(tmp_path):
    (tmp_path / 'pkg').mkdir()
    for n in ('m.py', 'n.py'):
        (tmp_path / 'pkg' / n).write_text(BODY)
    return tmp_path


def test_adapter_real_flow_with_fake_runner(arepo):
    """场景:适配层:一次真实流程的排查(假执行函数)"""
    runner = Script(run_test=ok(FAIL_OUT, 1), test_report=report_of('pkg/m.py:3'),
                    locate=loc_of('pkg/m.py:3', score='0.9'), probe=ok(''))
    r = diagnose(DIAG_DOMAIN, 't.py', runner, execute=True, repo_root=str(arepo))
    assert set(r) == {'report', 'calls', 'finding'} and r['report']['status'] == 'done'
    assert [c['name'] for c in r['calls']] == ['run_test', 'test_report', 'locate']
    assert runner.args_of('locate') == [{'path': 't.py', 'limit': 50}]
    f = r['finding']
    assert (f['status'], f['source']) == ('found', 'locate') and 1 <= len(f['candidates']) <= 5
    c = f['candidates'][0]
    assert (c['file'], c['line']) == ('pkg/m.py', 3) and c['snippet'] and 'score' in c
    text = summarize(f)
    assert len(text) <= 2500 and text.splitlines()[0] == 'status: found (source: locate)'
    assert text.splitlines()[-1].startswith('hint: ')
    dry = Script(run_test=ok(FAIL_OUT, 1))
    d = diagnose(DIAG_DOMAIN, 't.py', dry, execute=False, repo_root=str(arepo))
    assert dry.seen == [] and d['finding']['status'] == 'not_found'
    # tied locate rows (7 rows, same score): candidate shape and the summary text
    runner = Script(run_test=ok(FAIL_OUT, 1), test_report=report_of(FRAME), locate=loc_of(*LOCATED),
                    probe=ok(''))
    r = diagnose(DIAG_DOMAIN, 't.py', runner, execute=True, allow=None, repo_root=str(arepo))
    assert [c['name'] for c in r['calls']] == ['run_test', 'test_report', 'locate', 'probe']
    assert runner.args_of('locate') == [{'path': 't.py', 'limit': 50}]
    f = r['finding']
    assert (f['status'], f['source']) == ('found', 'locate') and 1 <= len(f['candidates']) <= 5
    for c in f['candidates']:
        assert isinstance(c['file'], str) and isinstance(c['line'], int)
        assert isinstance(c['score'], float) and c['reasons'] and all(isinstance(x, str) for x in c['reasons'])
        assert isinstance(c['probe'], list)
        lines = [s['line'] for s in c['snippet']]
        assert c['line'] in lines and len(lines) <= 5
        assert lines == list(range(max(1, c['line'] - 2), min(12, c['line'] + 2) + 1))
        assert all(s['text'] == 'v%d = %d' % (s['line'], s['line']) for s in c['snippet'])
    text = summarize(f)
    rows = text.splitlines()
    assert len(text) <= 2500 and rows[0] == 'status: found (source: locate)'
    assert rows[2].startswith('failed: ') and rows[2] != 'failed: -'
    assert rows[3] == 'exception: ValueError: x' and rows[-1].startswith('hint: ')
    top = f['candidates'][0]
    assert '  >> %d | v%d = %d' % (top['line'], top['line'], top['line']) in rows
    assert sum(1 for x in rows if x.startswith('  >> ')) == len(f['candidates'])
    assert 'tree:' not in text and 'plan:' not in text and 'decompos' not in text
    broken = json.loads(json.dumps(f))
    broken['exception']['message'] = 'a\nb\r\nc'
    broken['failed_tests'] = ['t\nx']
    esc = summarize(broken)
    assert 'exception: ValueError: a\\nb\\r\\nc' in esc.splitlines() and 'failed: t\\nx' in esc.splitlines()
    assert all(len(x.splitlines()) == 1 for x in esc.splitlines())


FUNC_SRC = ('def calc(a, b):\n    t = a + b\n    u = t * 2\n    w = u - 1\n    x = w + a\n'
            '    y = x - b\n    z = y + 1\n    return z\n')


def test_adapter_empty_locate_without_probe_permission(tmp_path, monkeypatch):
    """场景:适配层:一次真实流程的排查(空 locate:禁探针 / 读不到源码 / 探针取值匹配)"""
    from planbot.diag.parse import parse_report
    from planbot.diag.rank import rank
    (tmp_path / 'pkg').mkdir()
    (tmp_path / 'pkg' / 'f.py').write_text(FUNC_SRC)
    empty = ok('locate t.py：header\n')
    allow = ['run_test', 'test_report', 'locate']

    def go(frame, allow_=allow, probe=ok('')):
        r = Script(run_test=ok(FAIL_OUT, 1), test_report=report_of(frame), locate=empty, probe=probe)
        return diagnose(DIAG_DOMAIN, 't.py', r, execute=True, allow=allow_, repo_root=str(tmp_path)), r
    out, r = go('pkg/f.py:6')
    f = out['finding']
    assert (f['status'], f['source']) == ('not_found', 'report_only')
    assert [c['name'] for c in out['calls']] == ['run_test', 'test_report', 'locate']
    want = rank(parse_report(report_of('pkg/f.py:6'), 't.py'), [], {'pkg/f.py': FUNC_SRC}, 't.py', limit=5)
    assert len(f['candidates']) == 5 and len(want) == 5
    assert [(c['file'], c['line'], c['score'], c['reasons']) for c in f['candidates']] == \
        [(c['file'], c['line'], c['score'], c['reasons']) for c in want]
    assert ('pkg/f.py', 6) in [(c['file'], c['line']) for c in f['candidates']]
    assert {c['line'] for c in f['candidates']} <= set(range(2, 9))
    # frame file unreadable: stack frame as is
    out, _ = go('pkg/gone.py:7')
    f = out['finding']
    assert (f['status'], f['source']) == ('not_found', 'report_only')
    # (rank still returns the unreadable frame, score 0.0, no snippet; reasons are rank's, not asserted)
    assert [(c['file'], c['line'], c['score'], c['snippet']) for c in f['candidates']] == \
        [('pkg/gone.py', 7, 0.0, [])]
    # rank returning nothing: the stack-frame fallback (0.0, ['stack'])
    import planbot.diag.session as session_module
    monkeypatch.setattr(session_module, 'rank', lambda *a, **k: [])
    out, _ = go('pkg/gone.py:7')
    assert (out['finding']['status'], out['finding']['source']) == ('not_found', 'report_only')
    assert [(c['file'], c['line'], c['score'], c['reasons']) for c in out['finding']['candidates']] == \
        [('pkg/gone.py', 7, 0.0, ['stack'])]
    monkeypatch.undo()
    # allow=None: the engine's explicit probe returns a value at a sent position

    def answer(a):
        return ok('probe t.py\n== %s | x\n  #1 %s = 3\n' % (a['at'][0], a['exprs'][0]))
    out, r = go('pkg/f.py:6', allow_=None, probe=answer)
    f = out['finding']
    assert (f['status'], f['source']) == ('found', 'probe')
    assert [c['name'] for c in out['calls']] == ['run_test', 'test_report', 'locate', 'probe']
    assert f['candidates'] and any(c['probe'] for c in f['candidates']) and len(f['candidates']) <= 5


def test_adapter_tie_triggers_auto_probe_at_sample_points(arepo):
    """场景:适配层:一次真实流程的排查(并列触发自动探针,出点按 sample_plan)"""
    runner = Script(run_test=ok(FAIL_OUT, 1), test_report=report_of(FRAME), locate=loc_of(*LOCATED),
                    probe=ok(''))
    r = diagnose(DIAG_DOMAIN, 't.py', runner, execute=True, allow=None, repo_root=str(arepo))
    assert [c['name'] for c in r['calls']] == ['run_test', 'test_report', 'locate', 'probe']
    sent = runner.args_of('probe')[0]
    assert set(sent) == {'path', 'at', 'exprs'} and sent['at'][:5] == LOCATED[:5]
    assert r['finding']['source'] == 'locate'


def test_adapter_unrunnable_and_bad_results(arepo):
    """场景:适配层:测试跑不起来与坏结果"""
    bad = ok('test_report t.py：测试跑不起来——导入测试文件时SyntaxError: bad\n  位置 pkg/m.py:2 (<module>)\n')
    runner = Script(run_test=ok('collect error', 2), test_report=bad, locate=loc_of('pkg/m.py:1'),
                    probe=ok(''))
    r = diagnose(DIAG_DOMAIN, 't.py', runner, execute=True, repo_root=str(arepo))
    assert [c['name'] for c in r['calls']] == ['run_test', 'test_report']
    assert r['report']['status'] == 'done'
    assert (r['finding']['status'], r['finding']['source']) == ('found', 'unrunnable')
    c0 = r['finding']['candidates'][0]
    assert (c0['file'], c0['line']) == ('pkg/m.py', 2)
    nopos = Script(run_test=ok('collect error', 2),
                   test_report=ok('test_report t.py：测试跑不起来——导入测试文件时SyntaxError: bad\n'),
                   locate=loc_of('pkg/m.py:1'),
                   probe=lambda a: ok('probe t.py\n== %s | x\n  #1 %s = 3\n' % (a['at'][0], a['exprs'][0])))
    r = diagnose(DIAG_DOMAIN, 't.py', nopos, execute=True, allow=None, repo_root=str(arepo))
    assert (r['finding']['status'], r['finding']['source']) == ('not_found', 'unrunnable')
    assert [c['name'] for c in r['calls']] == ['run_test', 'test_report']
    assert [n for n, _ in nopos.seen] == ['run_test', 'test_report']
    assert nopos.args_of('locate') == [] and nopos.args_of('probe') == []
    boom = Script(run_test=ok(FAIL_OUT, 1), test_report=lambda a: 1 / 0)
    r = diagnose(DIAG_DOMAIN, 't.py', boom, execute=True, repo_root=str(arepo))
    assert r['report']['status'] == 'stuck' and r['report']['stuck']['reason'] == 'no_progress'
    assert len(boom.args_of('test_report')) == 1
    empty = Script(run_test=ok(FAIL_OUT, 1), test_report=lambda a: {})
    r = diagnose(DIAG_DOMAIN, 't.py', empty, execute=True, repo_root=str(arepo))
    assert r['report']['status'] == 'stuck' and r['report']['stuck']['reason'] == 'no_progress'
    assert len(empty.args_of('test_report')) == 1
    assert [c['status'] for c in r['calls'] if c['name'] == 'test_report'] == ['error']


def test_adapter_two_rounds_on_one_session(arepo):
    """场景:适配层:测试跑不起来与坏结果(同一个 Session 连续两轮,第二轮不带第一轮的东西)"""
    rounds = {'n': 0}

    def run_test(a):
        rounds['n'] += 1
        return ok(FAIL_OUT, 1)

    def report(a):
        exc, frame = (('ValueError: x', 'pkg/m.py:3'), ('KeyError: y', 'pkg/n.py:8'))[rounds['n'] - 1]
        return ok('test_report t.py：\n[1] 失败 T.test_a\n    %s\n    最内层仓库内帧 %s (f)\n' % (exc, frame))

    def locate(a):
        return loc_of(('pkg/m.py:3', 'pkg/n.py:8')[rounds['n'] - 1], score='0.9')
    s = Session(Script(run_test=run_test, test_report=report, locate=locate), str(arepo))
    seen = []
    for _ in range(2):
        for name in ('run_test', 'test_report', 'locate'):
            s.run(name, {'path': 't.py'})
        seen.append(s.finding('t.py'))
    first, second = seen
    assert first['exception']['type'] == 'ValueError'
    assert {c['file'] for c in first['candidates']} == {'pkg/m.py'}
    assert (second['status'], second['source']) == ('found', 'locate')
    assert second['exception'] == {'type': 'KeyError', 'message': 'y'}
    assert [(c['file'], c['line']) for c in second['candidates']] == [('pkg/n.py', 8)]
    assert [c['name'] for c in s.calls] == ['run_test', 'test_report', 'locate'] * 2


def test_adapter_domain_shape_and_probe_permission(arepo, tmp_path):
    """场景:适配层:领域形态与探针许可的零调用"""
    data = json.loads(Path(DIAG_DOMAIN).read_text(encoding='utf-8'))
    data['sensors'].append({'name': 'extra', 'run': {'cmd': {'name': 'other', 'args': {}}}, 'extract': []})
    p = tmp_path / 'd.json'
    p.write_text(json.dumps(data))
    runner = Script()
    with pytest.raises(core.PlanbotError) as e:
        diagnose(str(p), 't.py', runner, execute=True, repo_root=str(arepo))
    assert e.value.code == 'DOMAIN_INVALID' and runner.seen == []

    def mk():
        return Script(run_test=ok(FAIL_OUT, 1), test_report=report_of(FRAME), locate=loc_of(*LOCATED),
                      probe=ok(''))
    out = diagnose(DIAG_DOMAIN, 't.py', mk(), execute=True, allow=['run_test', 'test_report', 'locate'],
                   repo_root=str(arepo))
    assert out['finding']['source'] == 'locate' and 'probe' not in [c['name'] for c in out['calls']]
    data = json.loads(Path(DIAG_DOMAIN).read_text(encoding='utf-8'))
    for a in data['actions']:
        if a['name'] == 'probe':
            a['irreversible'] = True
    p2 = tmp_path / 'd2.json'
    p2.write_text(json.dumps(data))
    out = diagnose(str(p2), 't.py', mk(), execute=True, allow=None, repo_root=str(arepo))
    assert out['finding']['source'] == 'locate' and 'probe' not in [c['name'] for c in out['calls']]


def _sample_runner(fail_at, exit_code=0):
    def answer(args):
        at, expr = args['at'][fail_at], args['exprs'][0]
        return {'status': 'ok', 'exit_code': exit_code,
                'output': 'probe t.py\n== %s | x\n  #1 %s = A%s\n  #2 %s = B%s\n'
                          % (at, expr, CASE_FAIL, expr, CASE_PASS)}
    return Script(run_test=ok(FAIL_OUT, 1), test_report=report_of(FRAME), locate=loc_of(*LOCATED), probe=answer)


def test_adapter_probe_samples_take_part_in_ranking(arepo):
    """场景:适配层:探针样本参与排序(新)"""
    plain = diagnose(DIAG_DOMAIN, 't.py', _sample_runner(4, 1), execute=True, allow=None, repo_root=str(arepo))
    r = diagnose(DIAG_DOMAIN, 't.py', _sample_runner(4), execute=True, allow=None, repo_root=str(arepo))
    assert [c['name'] for c in r['calls']] == ['run_test', 'test_report', 'locate', 'probe']
    assert r['calls'][2]['args']['limit'] == 50
    f = r['finding']
    assert f['source'] == 'locate'
    first = f['candidates'][0]
    assert '%s:%d' % (first['file'], first['line']) == LOCATED[4]
    assert {p['value'] for p in first['probe']} == {'A', 'B'}
    pf = plain['finding']
    assert (pf['status'], pf['source']) == ('found', 'locate')
    assert '%s:%d' % (pf['candidates'][0]['file'], pf['candidates'][0]['line']) != LOCATED[4]
    # sample points: first 5 non-test locate rows in output order, then the innermost in-repo frame
    runner = _sample_runner(4)
    diagnose(DIAG_DOMAIN, 't.py', runner, execute=True, allow=None, repo_root=str(arepo))
    sent = runner.args_of('probe')[0]
    assert sent['at'][:5] == LOCATED[:5] and sent['at'][5] == FRAME
    assert len(sent['at']) <= 8 and len(set(sent['at'])) == len(sent['at'])
    # probe refused (exit_code 1): candidates equal the run without any probe permission
    off = _sample_runner(4)
    nop = diagnose(DIAG_DOMAIN, 't.py', off, execute=True, allow=['run_test', 'test_report', 'locate'],
                   repo_root=str(arepo))
    assert off.args_of('probe') == [] and nop['finding']['candidates'] == pf['candidates']
    assert plain['calls'][-1]['name'] == 'probe' and plain['calls'][-1]['exit_code'] == 1


def test_rank_direct_samples_order_by_value_difference_then_suspiciousness():
    from planbot.diag.rank import rank
    src = ''.join('v%d = %d\n' % (i, i) for i in range(1, 9))
    rep = {'unrunnable': False, 'location': None, 'failures': [
        {'test': 'T.test_a', 'exc_type': 'ValueError', 'message': 'x', 'frames': [], 'assert_line': None}]}
    susp = {1: 0.9, 2: 0.5, 3: 0.3, 4: 0.8}
    loc = [{'file': 'm.py', 'line': n, 'susp': s, 'fail': 1, 'passed': 0} for n, s in susp.items()]

    def sample(n, outcome, value):
        return {'at': 'm.py:%d' % n, 'expr': 'v%d' % n, 'value': value, 'test': 't', 'outcome': outcome}
    probes = [sample(3, 'fail', 'A'), sample(3, 'pass', 'B'), sample(2, 'fail', '1'), sample(2, 'pass', '2'),
              sample(4, 'fail', 'S'), sample(4, 'pass', 'S')]

    def lines(got):
        return [c['line'] for c in got]
    plain = rank(rep, loc, {'m.py': src}, 't.py')
    assert lines(rank(rep, loc, {'m.py': src}, 't.py', probes=None)) == lines(plain)
    assert rank(rep, loc, {'m.py': src}, 't.py', probes=None) == plain
    assert lines(plain) == [1, 4, 2, 3]
    got = rank(rep, loc, {'m.py': src}, 't.py', probes=probes)
    # rows whose fail/pass values differ first (higher suspiciousness first), then the others likewise
    assert lines(got) == [2, 3, 1, 4]
    assert lines(rank(rep, list(reversed(loc)), {'m.py': src}, 't.py', probes=list(reversed(probes)))) == lines(got)
    unlabeled = [dict(p, outcome=None) for p in probes]
    assert lines(rank(rep, loc, {'m.py': src}, 't.py', probes=unlabeled)) == lines(plain)


def test_adapter_assert_var_candidates_from_stack_only(tmp_path):
    """场景:适配层:只有栈帧时的断言变量候选(新)"""
    (tmp_path / 't.py').write_text(
        'def helper():\n    return 1\n\n\nclass T:\n    def test_a(self):\n'
        '        total = 1\n        total = sum([1, 2])\n        x = 0\n        y = 0\n'
        '        z = 0\n        w = 0\n        assert total == 6\n')

    def mk(loc):
        def probe(a):
            e = a['exprs'][0]
            return ok('probe t.py\n== %s | x\n  #1 %s = A%s\n  #2 %s = B%s\n' % (a['at'][0], e, CASE_FAIL, e, CASE_PASS))
        return Script(run_test=ok(FAIL_OUT, 1),
                      test_report=ok('test_report t.py：\n[1] 失败 T.test_a\n    AssertionError: x\n'
                                     '    最内层仓库内帧 t.py:13 (test_a)\n'),
                      locate=loc, probe=probe)
    out = diagnose(DIAG_DOMAIN, 't.py', mk(ok('locate t.py：header\n')), execute=True,
                   allow=['run_test', 'test_report', 'locate'], repo_root=str(tmp_path))
    f = out['finding']
    assert (f['status'], f['source']) == ('not_found', 'report_only') and len(f['candidates']) <= 5
    av = [c for c in f['candidates'] if 'assert_var' in c['reasons']]
    assert [c['line'] for c in av] == [8] and av[0]['snippet']
    out = diagnose(DIAG_DOMAIN, 't.py', mk(ok('locate t.py：header\n')), execute=True, allow=None,
                   repo_root=str(tmp_path))
    assert (out['finding']['status'], out['finding']['source']) == ('found', 'probe')
    assert any('assert_var' in c['reasons'] for c in out['finding']['candidates'])
    out = diagnose(DIAG_DOMAIN, 't.py', mk(loc_of('t.py:8')), execute=True, allow=None,
                   repo_root=str(tmp_path))
    assert out['finding']['source'] == 'locate'


@pytest.fixture(scope='module')
def synth(tmp_path_factory):
    """Same procedure as tests/test_diag_synthetic.py::results, with the example modules re-imported."""
    import sys
    import test_diag_synthetic as syn
    out = {}
    for name in syn.CASES:
        sys.modules.pop(name, None)
        with pytest.MonkeyPatch.context() as monkeypatch:
            report, loc, sources, root, test_file = syn.collect(tmp_path_factory.mktemp(name), name, monkeypatch)
            cands = syn_rank(report, loc, sources, test_file)
        out[name] = syn.position([(c['file'], c['line']) for c in cands], root)
        sys.modules.pop(name, None)
    return out


def test_synthetic_examples_root_cause_ranks(synth):
    """场景:适配层:夹具离线重放与定位准确率(四个自造小例子:边界比较、切片偏一、布尔运算、漏返回值;
    与 tests/test_diag_synthetic.py 同口径)"""
    ranks = list(synth.values())
    assert len(ranks) == 4
    assert all(r is not None and r <= 5 for r in ranks), synth
    assert sum(r <= 3 for r in ranks) >= 3, synth
    assert sum(r == 1 for r in ranks) >= 2, synth


def test_fixture_replay_cli_and_errors(tmp_path, capsys):
    """场景:适配层:夹具离线重放与定位准确率(第 2 版夹具)"""
    fx = 'tests/fixtures/diag_real.json'
    assert replay_main(['replay', '--fixture', fx]) == 0
    text = capsys.readouterr().out
    assert text.count('case: ') == 11
    assert re.search(r'^cases: 11 passed: 1 found: \d+ not_found: \d+$', text, re.M)
    assert 'truth' not in text.lower()
    assert replay_main(['replay', '--fixture', fx]) == 0
    assert capsys.readouterr().out == text
    assert replay_main(['replay', '--fixture', fx, '--json']) == 0
    obj = json.loads(capsys.readouterr().out)
    assert set(obj) == {'cases', 'totals'} and obj['totals']['cases'] == 11
    for case in obj['cases']:
        names = [c['name'] for c in case['calls']]
        f = case['finding']
        if f['status'] == 'passed':
            assert names == ['run_test']
        elif f['source'] == 'unrunnable':
            assert names == ['run_test', 'test_report']
        else:
            assert names.count('run_test') == 1 and names.count('test_report') == 1
            assert names.count('locate') == 1 and 0 <= names.count('probe') <= 2
            assert [c for c in case['calls'] if c['name'] == 'locate'][0]['args']['limit'] == 50
            assert names[:3] == ['run_test', 'test_report', 'locate']
    assert replay_main(['replay', '--fixture', fx, '--summary']) == 0
    assert 'summary:' in capsys.readouterr().out
    assert replay_main(['replay']) == 2
    cap = capsys.readouterr()
    assert cap.out == '' and cap.err.startswith('error: USAGE: ') and len(cap.err.splitlines()) == 1
    # an observation failure inside one case (a domain whose sensor extracts an undeclared predicate)
    dom = json.loads(Path(DIAG_DOMAIN).read_text(encoding='utf-8'))
    dom['sensors'][0]['extract'][0]['facts'] = ['undeclared({file})']
    dpath = tmp_path / 'dom.json'
    dpath.write_text(json.dumps(dom))
    first = load_cases(fx)[0]['id']
    assert replay_main(['replay', '--fixture', fx, '--domain', str(dpath)]) == 2
    cap = capsys.readouterr()
    assert cap.out == '' and len(cap.err.splitlines()) == 1
    assert cap.err.startswith('error: SENSOR_FAILED: case %s: ' % first)
    assert replay_main(['replay', '--fixture', fx, '--domain', str(dpath), '--json']) == 2
    cap = capsys.readouterr()
    err = json.loads(cap.out)['error']
    assert cap.err == '' and set(json.loads(cap.out)) == {'error'} and set(err) == {'code', 'message'}
    assert err['code'] == 'SENSOR_FAILED' and err['message'].startswith('case %s: ' % first)
    assert replay_main(['replay', '--json']) == 2
    assert json.loads(capsys.readouterr().out)['error']['code'] == 'USAGE'
    data = json.loads(Path(fx).read_text(encoding='utf-8'))
    data['cases'][1]['test'] = 'a b.py'
    bad = tmp_path / 'bad.json'
    bad.write_text(json.dumps(data))
    assert replay_main(['replay', '--fixture', str(bad)]) == 2
    cap = capsys.readouterr()
    assert cap.out == '' and re.match(r'error: GOAL_INVALID: case ', cap.err)
    assert replay_main(['replay', '--fixture', str(bad), '--json']) == 2
    err = json.loads(capsys.readouterr().out)['error']
    assert err['code'] == 'GOAL_INVALID' and err['message'].startswith('case ')
