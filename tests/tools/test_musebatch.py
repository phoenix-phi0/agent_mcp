import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))  # 项目根，run_all 不设 PYTHONPATH
"""musebatch：流程里交给 Muse 的步骤按 mbatch 的方式排队、认领、写回（tools/musebatch.py）。
离线假模型跑整项目流程、工程师换成 ENGINEER_MUSE，任务目录换成临时目录：

1. 投任务：真跑（client=None）停在 Muse 步骤时默认投一条，DSL_MUSE_WAKE=off 不投；同一步同一次不重投。
   job.json 和 mbatch 同样的字段，多一个 flow；cwd 是项目目录；提示词里有角色说明、工作环境、任务、Schema、怎么交。
2. 认领：没 claim 不能写；认领后超时 reclaim_stuck 退回 queued，再认领。
3. 写回：不合格抛错、逐条列问题、什么都不写（还是 running，流程不动）；合格交进流程（来源 mcp:muse），整批 done，
   流程往下走到下一个 Muse 步骤。
4. 流程不等了（别人交了）：sweep / claim 把任务取消，claim 报「不用做了」。
5. 失败：set_task failed 记下原因、整批 failed，流程还停着。
6. 命令行：queued / jobs 打印 JSON；set_task 不合格退出码 1。
"""
import contextlib
import io
import json
import os
import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from dsl.client import ScriptClient
from tools import musebatch as mb, workflow_ctl as wc

ROOT = Path(__file__).resolve().parents[2]
_sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_wf_project import ENTRY, arch, assign, final, impl, mcheck, review  # noqa: E402


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print('  ✓', msg)


def raises(fn, words, msg):
    try:
        fn()
    except mb.MuseBatchError as e:
        check(all(w in str(e) for w in words), f'{msg}（{str(e)[:150]}）')
        return
    raise AssertionError(msg + '：没有报错')


def replay(run_id):
    """按真跑那样回放（client=None）：前面的步骤都有结果，回放到 Muse 的步骤停下，不调模型。"""
    cfg = json.loads((ROOT / run_id).with_suffix('.ctl').read_text(encoding='utf-8'))
    wc._advance(ROOT / run_id, cfg, client=None)


def start(demo, replies):
    c = ScriptClient(replies)
    c.offline = True
    s = wc.start(demo, entry='run_test.zs', mode='auto', roles={'ENGINEER': 'ENGINEER_MUSE'}, wait=True, client=c)
    return c, s['run'], s['pending']


def cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = mb.main(list(argv))
    return code, out.getvalue() + err.getvalue()


def run():
    (ROOT / 'data/tmp').mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix='musebatch-', dir=ROOT / 'data/tmp'))
    old_jobs, old_env = mb.JOBS, os.environ.pop('DSL_MUSE_WAKE', None)
    mb.JOBS = tmp / 'jobs'
    try:
        demo = tmp / 'p'
        shutil.copytree(ROOT / 'workflow_demo', demo, ignore=shutil.ignore_patterns('runs', 'work', '*.bak-*', '__pycache__'))
        (demo / 'run_test.zs').write_text(ENTRY, encoding='utf-8')
        c, run_id, pend = start(demo, [arch('v1'), review('通过'), assign(('建表和数据层函数', 'ENGINEER')),
                                       mcheck('通过', 'create_todo(title: str) -> int'), assign(('路由和页面', 'ENGINEER'))])
        step = pend['step']
        check(pend['reason'] == 'muse' and mb.queued() == [], f'流程停在第 {step} 步等 Muse；喂假客户端时没投')

        print('投任务')
        os.environ['DSL_MUSE_WAKE'] = 'off'
        replay(run_id)
        check(mb.queued() == [], '真跑停在 Muse 步骤、DSL_MUSE_WAKE=off：不投')
        os.environ.pop('DSL_MUSE_WAKE')
        replay(run_id)
        q = mb.queued()
        check(len(q) == 1 and q[0]['flow']['run'] == run_id and q[0]['flow']['step'] == step
              and q[0]['flow']['card'] == 'ENGINEER_MUSE', '真跑停在 Muse 步骤：默认投一条（flow 写明运行、步号、卡）')
        replay(run_id)
        check(mb.post(ROOT / run_id) is None and len(mb.jobs(50)) == 1, '同一步同一次：不重投')
        jid = q[0]['job_id']
        d = mb.status(jid, full=True)
        prompt = d['tasks'][0]['prompt']
        cwd = str((demo / 'work/todo_test').resolve())
        check(d['executor'] == 'muse' and d['status'] == 'queued' and d['cwd'] == cwd and len(d['tasks']) == 1
              and {'claimed_by', 'claimed_at', 'started', 'finished', 'options'} <= set(d),
              'job.json：和 mbatch 同样的字段，cwd 是项目目录，一条 task')
        check('## 身份' in prompt and '【技能 skills/implementation.md】' in prompt and f'【工作环境】' in prompt
              and cwd + '/.venv/bin/python' in prompt and '建表和数据层函数' in prompt and '"verification"' in prompt
              and f'set_task("{jid}", 0' in prompt and f'tools.musebatch set_task {jid} 0 --file' in prompt,
              '提示词：角色说明和技能、工作环境（目录、venv）、任务、Schema、怎么交（函数和命令行）')

        from tools import trace_server as ts

        def viewer_row():
            return next(r for r in ts.list_runs(demo / 'runs') if r['name'] == Path(run_id).name)
        row = viewer_row()
        check(row['status'] == 'waiting' and row['waiting_reason'] == 'muse' and row['waiting_card'] == 'ENGINEER_MUSE'
              and row['muse']['status'] == 'queued' and row['muse']['job'] == jid,
              '查看器的运行列表：停下的原因是 muse，队列里这一步在排队（页面显示「等 Muse 认领」，不是「暂停」）')

        print('认领')
        raises(lambda: mb.set_task(jid, 0, output=json.dumps(impl('x'))), ['要先 claim'], '没 claim 不能写')
        d = mb.claim(jid)
        check(d['status'] == 'running' and d['claimed_by'] == 'muse' and d['tasks'][0]['status'] == 'running', 'claim：running')
        check(viewer_row()['muse']['status'] == 'running'
              and ts.read_trace(ROOT / run_id)['_muse']['status'] == 'running',
              '查看器：认领以后是 running（页面显示「Muse 在做」）')
        raises(lambda: mb.claim(jid), ['不是 queued'], '重复认领：报错')
        d = json.loads((mb.JOBS / jid / 'job.json').read_text(encoding='utf-8'))
        d['claimed_at'] = (datetime.now() - timedelta(hours=1)).isoformat(timespec='seconds')
        (mb.JOBS / jid / 'job.json').write_text(json.dumps(d, ensure_ascii=False), encoding='utf-8')
        check(mb.reclaim_stuck() == [jid] and mb.status(jid)['status'] == 'queued', '认领一小时没写回：reclaim_stuck 退回 queued')
        mb.claim(jid)

        print('写回')
        bad = impl('core_db')
        del bad['verification'], bad['summary']
        raises(lambda: mb.set_task(jid, 0, output=json.dumps(bad, ensure_ascii=False)),
               ['没交上', '2 条问题', 'verification', 'summary'], '不合格：抛错，逐条列出问题')
        d = mb.status(jid, full=True)
        check(d['status'] == 'running' and d['tasks'][0]['output'] == '' and wc.status(run_id)['pending']['step'] == step,
              '不合格什么都不写：还是 running，流程不动')
        raises(lambda: mb.set_task(jid, 0, output='做完了'), ['不是 JSON'], '写回的不是 JSON：抛错')
        good = json.dumps(impl('core_db'), ensure_ascii=False)
        r = mb.set_task(jid, 0, output=good, client=c, wait=True)
        d = mb.status(jid, full=True)
        check(r['ok'] and d['status'] == 'done' and d['tasks'][0]['status'] == 'done' and d['tasks'][0]['output'] == good
              and r['next']['reason'] == 'muse' and r['next']['step'] > step,
              '合格：交进流程，整批 done（不用 finish），流程走到下一个 Muse 步骤')
        hist = json.loads((ROOT / run_id).with_suffix('.ctl').read_text(encoding='utf-8'))['history']
        check(any(h.get('op') == 'submit' and h.get('step') == step and h.get('actor') == 'mcp:muse' for h in hist),
              '来源记 mcp:muse')

        print('流程不等了')
        step2 = r['next']['step']
        jid2 = mb.post(ROOT / run_id)
        check(jid2 and mb.status(jid2)['flow']['step'] == step2, '下一步：投了新任务')
        # 别人（人）先交了；在当前进程里用假客户端跑完剩下的（不起后台 worker、不调真模型）
        c.replies.extend([mcheck('通过', 'POST /todos'), impl('itest'), final('通过')])
        s = wc.submit(run_id, impl('web_by_human'), step=step2, wait=True, client=c)
        check(s['status'] == 'done', f'人交了 web 的实现，流程跑完（{s["status"]}）')
        raises(lambda: mb.claim(jid2), ['不用做了'], 'claim：流程已经不等这一步，报「不用做了」')
        check(mb.status(jid2)['status'] == 'cancelled', '任务被取消')

        print('失败')
        c2, run2, pend2 = start(demo, [arch('v1'), review('通过'), assign(('建表和数据层函数', 'ENGINEER'))])
        jid3 = mb.post(ROOT / run2)
        mb.claim(jid3)
        r = mb.set_task(jid3, 0, error='依赖装不上：没有网络', status='failed')
        d = mb.status(jid3, full=True)
        check(r['status'] == 'failed' and d['status'] == 'failed' and '没有网络' in d['tasks'][0]['error']
              and wc.status(run2)['pending']['reason'] == 'muse', 'set_task failed：记下原因，整批 failed，流程还停着')
        wc.abort(run2)
        check(mb.sweep() == [], 'sweep：没有在跑的任务要取消')

        print('命令行')
        code, out = cli('jobs', '5')
        check(code == 0 and len(json.loads(out)) == 3, 'jobs：打印 JSON')
        code, out = cli('queued')
        check(code == 0 and json.loads(out) == [], 'queued：打印 JSON')
        code, out = cli('set_task', jid3, '0', '--file', str(tmp / 'nope.json'))
        check(code == 1 and 'musebatch:' in out, 'set_task 出错：退出码 1')
        check('任务目录' in mb.describe() and '最近 3 个任务' in mb.describe(), 'describe：概况')

        print('MCP 白名单')
        import re
        src = (ROOT / 'fs_server_v2.py').read_text(encoding='utf-8')
        names = dict(re.findall(r'"musebatch\.(\w+)":\s*\("tools\.musebatch",\s*"(\w+)"\)', src))
        need = {'describe', 'queued', 'jobs', 'status', 'claim', 'set_task', 'finish', 'cancel', 'reclaim', 'reclaim_stuck'}
        check(set(names) == need and all(callable(getattr(mb, f, None)) for f in names.values()),
              'fs_server_v2 的 tool_call 白名单有 musebatch.*（同 mbatch.*），每个都对得上函数')
    finally:
        mb.JOBS = old_jobs
        os.environ.pop('DSL_MUSE_WAKE', None)
        if old_env is not None:
            os.environ['DSL_MUSE_WAKE'] = old_env
        shutil.rmtree(tmp, ignore_errors=True)
    print('musebatch：全部通过')


if __name__ == '__main__':
    run()
