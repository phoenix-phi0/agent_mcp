import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))  # 项目根，run_all 不设 PYTHONPATH
"""后台进程交给服务接手（workflow_ctl._spawn / pick_up）和起不来时的报错。

真事：Muse 在自己的环境里交结果（tools.muse_flow / musebatch），那边没有智谱的 key，
起的后台进程一建引擎就退出，记录停在 running、查看器上显示「中断」，要人手动 resume。

1. 判断：建不了默认客户端（没有智谱 key）→ 交给服务；WF_WORKER_HERE=1 / 0 强制。
2. 交给服务：不起进程，控制文件记 handoff；status 照旧是 running（带 handoff）；一分钟内的操作报「几秒后再试」。
3. pick_up：在本进程起（local=True），清掉标记；被中止的不接；没有标记的不动。
4. 超过一分钟没人接：status 显示 interrupted，下一次操作作废标记、照常进行。中止也作废标记。
5. 后台进程起不来（建引擎就报错）：记录改成 error，写明原因，不再停在 running。
"""
import json
import os
import shutil
import tempfile
from pathlib import Path

from dsl.client import ScriptClient
from tools import workflow_ctl as wc

ROOT = Path(__file__).resolve().parents[2]
_sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_wf_project import ENTRY, arch  # noqa: E402


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print('  ✓', msg)


def raises(fn, words, msg):
    try:
        fn()
    except wc.ControlError as e:
        check(all(w in str(e) for w in words), f'{msg}（{e}）')
        return
    raise AssertionError(msg + '：没有报错')


def ctl(run):
    return json.loads((ROOT / run).with_suffix('.ctl').read_text(encoding='utf-8'))


def set_ctl(run, **kw):
    f = (ROOT / run).with_suffix('.ctl')
    d = json.loads(f.read_text(encoding='utf-8'))
    d.update(kw)
    f.write_text(json.dumps(d, ensure_ascii=False), encoding='utf-8')


def new_run(demo):
    c = ScriptClient([arch('v1')])
    c.offline = True
    return wc.start(demo, entry='run_test.zs', mode='step', client=c)['run']


def run():
    (ROOT / 'data/tmp').mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix='wfhandoff-', dir=ROOT / 'data/tmp'))
    old_env = os.environ.pop('WF_WORKER_HERE', None)
    real_spawn = wc._spawn
    try:
        demo = tmp / 'p'
        shutil.copytree(ROOT / 'workflow_demo', demo, ignore=shutil.ignore_patterns('runs', 'work', '*.bak-*', '__pycache__'))
        (demo / 'run_test.zs').write_text(ENTRY, encoding='utf-8')

        print('判断')
        import tools.zhipu as zh
        real_client = zh.ZhipuClient

        class NoKey:
            def __init__(self, *a, **k):
                raise ValueError('缺少 API Key')
        zh.ZhipuClient = NoKey
        try:
            check('智谱' in (wc._cant_run_here() or ''), '建不了默认客户端（没有智谱 key）：交给服务')
            os.environ['WF_WORKER_HERE'] = '1'
            check(wc._cant_run_here() is None, 'WF_WORKER_HERE=1：强制本地起')
        finally:
            zh.ZhipuClient = real_client
            os.environ.pop('WF_WORKER_HERE', None)
        os.environ['WF_WORKER_HERE'] = '0'
        check(wc._cant_run_here() == 'WF_WORKER_HERE=0', 'WF_WORKER_HERE=0：强制交给服务')

        print('交给服务')
        run_id = new_run(demo)
        check(wc.status(run_id)['status'] == 'waiting', '运行停在第 1 步')
        wc._spawn(ROOT / run_id)                     # WF_WORKER_HERE=0：不起进程
        c = ctl(run_id)
        s = wc.status(run_id)
        check(c['worker'] is None and c['handoff']['why'] == 'WF_WORKER_HERE=0', '不起进程，控制文件记 handoff')
        check(s['status'] == 'running' and s['handoff']['why'] == 'WF_WORKER_HERE=0',
              'status 照旧是 running（带 handoff），不显示成中断')
        raises(lambda: wc.execute(run_id), ['几秒后再试'], '一分钟内的操作：等服务接手')
        log = (ROOT / run_id).with_suffix('.log').read_text(encoding='utf-8')
        check('交给服务接手（WF_WORKER_HERE=0）' in log, '日志里记了一笔')

        print('pick_up')
        calls = []
        wc._spawn = lambda trace, local=False: calls.append((Path(trace), local))
        got = wc.pick_up(demo)
        check(got == [(ROOT / run_id).resolve()] or [p.resolve() for p in got] == [(ROOT / run_id).resolve()],
              'pick_up 接手了这一条')
        check(calls and calls[0][1] is True and 'handoff' not in ctl(run_id), '在本进程起（local=True），清掉标记')
        calls.clear()
        check(wc.pick_up(demo) == [] and calls == [], '没有标记的不动')
        set_ctl(run_id, handoff={'at': wc._stamp(), 'why': 'x'})
        t = json.loads((ROOT / run_id).read_text(encoding='utf-8'))
        t['status'] = 'aborted'
        (ROOT / run_id).write_text(json.dumps(t, ensure_ascii=False), encoding='utf-8')
        check(wc.pick_up(demo) == [] and calls == [] and 'handoff' not in ctl(run_id), '记录已经不是 running（被中止）：不接，标记清掉')
        wc._spawn = real_spawn

        print('没人接')
        run2 = new_run(demo)
        wc._spawn(ROOT / run2)
        set_ctl(run2, handoff={'at': '2026-01-01T00:00:00+0800', 'why': 'WF_WORKER_HERE=0'})
        s = wc.status(run2)
        check(s['status'] == 'interrupted' and 'handoff' in s, '超过一分钟没人接：显示 interrupted（带 handoff，看得出原因）')
        cfg = ctl(run2)
        wc._idle(cfg)
        check('handoff' not in cfg, '下一次操作：标记作废，照常进行')
        run3 = new_run(demo)
        wc._spawn(ROOT / run3)
        wc.abort(run3)
        check('handoff' not in ctl(run3) and wc.status(run3)['status'] == 'aborted', '中止：标记作废')

        print('起不来')
        os.environ.pop('WF_WORKER_HERE', None)
        run4 = new_run(demo)
        t = json.loads((ROOT / run4).read_text(encoding='utf-8'))
        t['status'] = 'running'
        (ROOT / run4).write_text(json.dumps(t, ensure_ascii=False), encoding='utf-8')
        real_adv = wc._advance

        def boom(*a, **k):
            raise ValueError('缺少 API Key。请在 config.json 里填 api_key\n第二行')
        wc._advance = boom
        try:
            code = wc._main(['advance', str(ROOT / run4)])
        finally:
            wc._advance = real_adv
        s = wc.status(run4)
        check(code == 1 and s['status'] == 'error' and s['error'].startswith('后台进程起不来：ValueError: 缺少 API Key')
              and '第二行' not in s['error'], '后台进程起不来：记录改成 error，写明原因（只留第一行）')
    finally:
        wc._spawn = real_spawn
        os.environ.pop('WF_WORKER_HERE', None)
        if old_env is not None:
            os.environ['WF_WORKER_HERE'] = old_env
        shutil.rmtree(tmp, ignore_errors=True)
    print('后台进程交给服务接手：全部通过')


if __name__ == '__main__':
    run()
