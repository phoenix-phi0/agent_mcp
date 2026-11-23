import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))  # 项目根，run_all 不设 PYTHONPATH
"""流程里给 Muse 的接口（tools/muse_flow.py，卡的 model 写 "muse"）。离线假模型跑整项目流程，工程师换成 ENGINEER_MUSE：

1. 卡：ENGINEER_MUSE 能加载（model=muse，在 work/{project} 里干活，带工程师技能，技能和 ENGINEER_GPT 一字不差）；
   model=muse 的卡写 tools / effort / allowed_tools 报错。
2. 停下：auto 模式走到实现就停（reason=muse），不调模型；queue 列得出；execute 不让跑（提示等 Muse 或换卡）。
3. 取请求：request 给 system（SOUL + 技能）、prompt、schema、绝对路径的 cwd 和项目 python。
4. 交结果：不合格当场报逐条问题，流程原地不动、可以接着交；步号 / 次数不对报「不用做了」；
   合格就往下走，下一个模块的实现又停给 Muse；来源记 mcp:muse。
5. 投任务：测试喂假客户端时不投；notify 往 musebatch 投一条、同一步同一次不重投，不在等 Muse 时不投。
6. 命令行：show 退出码 0，submit 不合格 1、步号不对 2、合格 0。
"""
import contextlib
import io
import json
import shutil
import tempfile
from pathlib import Path

from dsl.client import ScriptClient
from tools import muse_flow as mf, musebatch, workflow_ctl as wc

ROOT = Path(__file__).resolve().parents[2]
_sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_wf_project import ENTRY, arch, assign, impl, mcheck, review  # noqa: E402


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print('  ✓', msg)


def raises(fn, words, msg, exc=mf.MuseFlowError):
    try:
        fn()
    except exc as e:
        check(all(w in str(e) for w in words), f'{msg}（{str(e)[:160]}）')
        return
    raise AssertionError(msg + '：没有报错')


def cli(*argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = mf.main(list(argv))
    return code, buf.getvalue()


def test_card(demo):
    from tools.dsl import DSLEngine
    from tools.dsl_core import DSLError
    from verbs.workflow import _agents as ag
    e = DSLEngine(client=ScriptClient([]), workdir=demo, verbs_root=ROOT / 'verbs', verbose=False)
    e.vars['project'] = 'muse_proj'
    prof = ag.load_agent(e, 'ENGINEER_MUSE')
    check(prof['model'] == 'muse' and prof['agentic']['cwd'] == (demo / 'work/muse_proj').resolve()
          and prof['agentic']['venv'] is True and '【技能 skills/implementation.md】' in prof['system']
          and 'musebatch.set_task' in prof['system'],
          'ENGINEER_MUSE：model=muse，在 work/{project} 里干活，用项目 venv，SOUL 写了经 musebatch 交，带工程师技能')
    gpt = (ROOT / 'workflow_demo/agents/ENGINEER_GPT/skills/implementation.md').read_text(encoding='utf-8')
    check((ROOT / 'workflow_demo/agents/ENGINEER_MUSE/skills/implementation.md').read_text(encoding='utf-8') == gpt,
          '技能和 ENGINEER_GPT 的 implementation.md 一字不差')
    check(ag.card_executor(demo, 'ENGINEER_MUSE') == 'muse' and ag.card_executor(demo, 'HUMAN') == 'human'
          and ag.card_executor(demo, 'ENGINEER') is None and ag.is_human_card(demo, 'ENGINEER_MUSE') is False,
          'card_executor 分得清 muse / human / 模型')
    card = demo / 'agents/ENGINEER_MUSE/agent.json'
    base = json.loads(card.read_text(encoding='utf-8'))
    for extra, words, msg in (({'tools': ['读文件']}, ['tools'], '写 tools'),
                              ({'effort': 'high'}, ['effort'], '写 effort'),
                              ({'agentic': dict(base['agentic'], allowed_tools=['Read'])}, ['allowed_tools'], '写 allowed_tools')):
        card.write_text(json.dumps(dict(base, **extra), ensure_ascii=False), encoding='utf-8')
        try:
            ag.load_agent(e, 'ENGINEER_MUSE')
        except DSLError as err:
            check(all(w in str(err) for w in words), f'model=muse 的卡{msg}：报错（{err}）')
        else:
            raise AssertionError(f'model=muse 的卡{msg}应报错')
    card.write_text(json.dumps(base, ensure_ascii=False, indent=2), encoding='utf-8')


def test_flow(demo, jobs):
    (demo / 'run_test.zs').write_text(ENTRY, encoding='utf-8')
    c = ScriptClient([arch('v1'), review('通过'), assign(('建表和数据层函数', 'ENGINEER')),
                      mcheck('通过', 'create_todo(title: str) -> int'), assign(('路由和页面', 'ENGINEER'))])
    c.offline = True
    s = wc.start(demo, entry='run_test.zs', mode='auto', roles={'ENGINEER': 'ENGINEER_MUSE'}, wait=True, client=c)
    run = s['run']
    p = s.get('pending') or {}
    check(s['status'] == 'waiting' and p.get('reason') == 'muse' and p.get('card') == 'ENGINEER_MUSE'
          and len(c.calls) == 3, f'auto 模式走到 core 的实现就停给 Muse（reason=muse），只调了 3 次模型（{s["status"]}）')
    step = p['step']
    check(not any(jobs.iterdir()) if jobs.exists() else True, '喂假客户端的运行不投唤醒任务')
    q = mf.queue(demo)
    check(len(q) == 1 and q[0]['run'] == run and q[0]['step'] == step and q[0]['card'] == 'ENGINEER_MUSE',
          'queue 列出这一步')
    raises(lambda: wc.execute(run, wait=True, client=c), ['Muse', '换卡'], 'execute 不让跑：提示等 Muse 或换卡',
           exc=wc.ControlError)

    req = mf.request(run)
    cwd = (demo / 'work/todo_test').resolve()
    check(req['step'] == step and req['attempt'] == 1 and req['format'] == 'implementation'
          and 'musebatch.set_task' in req['system'] and '【技能 skills/implementation.md】' in req['system']
          and '建表和数据层函数' in req['prompt'] and '"verification"' in json.dumps(req['schema']),
          'request：system（SOUL + 技能）、prompt（任务）、schema（实现记录的格式）')
    check(req['cwd'] == str(cwd) and req['python'] == str(cwd / '.venv/bin/python'),
          'request：cwd 是绝对路径的项目目录，python 是项目 venv')

    bad = impl('core_db')
    del bad['verification']
    raises(lambda: mf.submit(run, bad, step=step), ['不符合格式', 'verification'], '缺字段：当场报逐条问题')
    s = wc.status(run)
    check(s['status'] == 'waiting' and s['pending']['step'] == step and s['pending']['reason'] == 'muse',
          '不合格不动流程：还停在这一步等 Muse')
    raises(lambda: mf.submit(run, impl('x'), step=step + 5), ['不是第'], '步号不对：不用做了', exc=mf.NotWaiting)
    raises(lambda: mf.submit(run, impl('x'), step=step, attempt=2), ['第 1 次'], '次数不对：不用做了', exc=mf.NotWaiting)
    raises(lambda: mf.submit(run, '{坏的', step=step), ['不是 JSON'], '交的不是 JSON：报错')

    s = mf.submit(run, impl('core_db'), step=step, client=c, wait=True)
    p2 = s.get('pending') or {}
    check(s['status'] == 'waiting' and p2.get('reason') == 'muse' and p2['step'] > step and len(c.calls) == 5,
          '合格：往下走（模块验收、下一个模块分配），web 的实现又停给 Muse')
    t = json.loads((ROOT / run).read_text(encoding='utf-8'))
    done = [e for e in t['events'] if e.get('type') == 'task' and e.get('step') == step and e.get('status') == 'ok']
    check(done and done[-1].get('source') == 'external' and done[-1]['result']['summary'] == '做了core_db',
          'Muse 交的结果记进这一步（source=external）')
    hist = json.loads(Path(str(ROOT / run)[:-5] + '.ctl').read_text(encoding='utf-8')).get('history', []) \
        if Path(str(ROOT / run)[:-5] + '.ctl').is_file() else []
    if hist:
        check(any(h.get('op') == 'submit' and h.get('actor') == 'mcp:muse' for h in hist), '控制文件里的来源是 mcp:muse')
    raises(lambda: mf.request(run, step=step), ['不是第'], '旧步骤再 show：不用做了', exc=mf.NotWaiting)
    return run, p2


def test_notify(run, pend, jobs):
    """notify 交给 musebatch.post（队列本身的细节见 test_musebatch.py）。"""
    jid = mf.notify(run)
    check(jid and len(musebatch.queued()) == 1 and musebatch.queued()[0]['flow']['step'] == pend['step'],
          'notify：往 musebatch 投了这一步')
    check(mf.notify(run) is None and len(musebatch.jobs(50)) == 1, '同一步同一次：不重投')
    wc.abort(run)
    check(mf.notify(run) is None, '不在等 Muse（中止了）：不投')


def test_cli(demo, jobs):
    (demo / 'run_test.zs').write_text(ENTRY, encoding='utf-8')
    c = ScriptClient([arch('v1'), review('通过'), assign(('建表和数据层函数', 'ENGINEER')), mcheck('通过', 'x')])
    c.offline = True
    s = wc.start(demo, entry='run_test.zs', mode='auto', roles={'ENGINEER': 'ENGINEER_MUSE'}, wait=True, client=c)
    run, step = s['run'], s['pending']['step']
    code, out = cli('show', run)
    check(code == 0 and json.loads(out)['step'] == step, 'show：退出码 0，打印请求 JSON')
    code, out = cli('queue')
    check(code == 0 and isinstance(json.loads(out), list), 'queue：打印列表')
    f = demo / 'r.json'
    bad = impl('core_db')
    del bad['summary']
    f.write_text(json.dumps(bad, ensure_ascii=False), encoding='utf-8')
    code, out = cli('submit', run, '--step', str(step), '--file', str(f))
    check(code == 1 and '没交上' in out and 'summary' in out, 'submit 不合格：退出码 1，打印问题')
    code, out = cli('submit', run, '--step', str(step + 9), '--file', str(f))
    check(code == 2 and '不用做了' in out, 'submit 步号不对：退出码 2')
    wc.abort(run)


def run():
    (ROOT / 'data/tmp').mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix='museflow-', dir=ROOT / 'data/tmp'))
    old_jobs = musebatch.JOBS
    jobs = tmp / 'jobs'
    musebatch.JOBS = jobs               # 不碰真队列
    try:
        demo = tmp / 'p'
        shutil.copytree(ROOT / 'workflow_demo', demo, ignore=shutil.ignore_patterns('runs', 'work', '*.bak-*', '__pycache__'))
        print('test_card')
        test_card(demo)
        print('test_flow')
        run_id, pend = test_flow(demo, jobs)
        print('test_notify')
        test_notify(run_id, pend, jobs)
        print('test_cli')
        test_cli(demo, jobs)
    finally:
        musebatch.JOBS = old_jobs
        shutil.rmtree(tmp, ignore_errors=True)
    print('流程给 Muse 的接口：全部通过')


if __name__ == '__main__':
    run()
