import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))  # 项目根，run_all 不设 PYTHONPATH
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))
"""查看器里交给 Muse 的步骤不显示成「暂停」（用户报的：Muse 在做的时候页面写「暂停 · 等外部决定」）。

离线假模型跑整项目流程、工程师换成 ENGINEER_MUSE，停在 Muse 的步骤，往临时的 musebatch 队列投任务，
用 jsdom（tests/e2e/trace_view_check.js）渲染 trace_view.html：
1. 排队时：概要、流程图、节点详情都说「交给 Muse · 等它认领」，详情里有队列任务号；没有「暂停 · 等外部决定」。
2. 认领后：「Muse 在做」，详情写「Muse 已认领，在做」。
3. 普通的暂停（不是 Muse、不是人）照旧写「暂停 … 等外部决定」。
jsdom 找的是 node_modules（项目根、或环境变量 NODE_PATH）；没装就跳过页面这一半。
"""
import json
import shutil
import tempfile
from pathlib import Path

from dsl.client import ScriptClient
from tools import musebatch as mb, workflow_ctl as wc
from test_trace_view import check, jsdom_env, render
from test_wf_project import ENTRY, arch, assign, review

ROOT = Path(__file__).resolve().parents[2]


def run():
    (ROOT / 'data/tmp').mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix='viewmuse-', dir=ROOT / 'data/tmp'))
    old_jobs = mb.JOBS
    mb.JOBS = tmp / 'jobs'
    try:
        node, env = jsdom_env()
        demo = tmp / 'p'
        shutil.copytree(ROOT / 'workflow_demo', demo, ignore=shutil.ignore_patterns('runs', 'work', '*.bak-*', '__pycache__'))
        (demo / 'run_test.zs').write_text(ENTRY, encoding='utf-8')
        c = ScriptClient([arch('v1'), review('通过'), assign(('建表和数据层函数', 'ENGINEER'))])
        c.offline = True
        s = wc.start(demo, entry='run_test.zs', mode='auto', roles={'ENGINEER': 'ENGINEER_MUSE'}, wait=True, client=c)
        run_id = s['run']
        pend = wc.status(run_id, detail=True)['pending']
        check(pend['reason'] == 'muse', f'停在第 {pend["step"]} 步等 Muse')
        jid = mb.post(ROOT / run_id)
        if not node:
            print('  - 跳过页面：没有 node 或 jsdom（装到项目 node_modules，或设 NODE_PATH）')
            return
        line = pend['line']

        out = render(node, env, tmp, run_id, line)
        check('交给 Muse' in out['summary'] and '等它认领' in out['summary'] and '等外部决定' not in out['summary'],
              f'概要：交给 Muse · 等它认领（{out["summary"][:60]}）')
        check('交给 Muse' in out['flow'] and '步等外部' not in out['flow'], '流程图：节点和结尾都写交给 Muse')
        check('交给 Muse 做' in out['detail'] and jid in out['detail'] and '排队等 Muse 认领' in out['detail']
              and '默认会这样执行' not in out['detail'], '节点详情：交给 Muse 做、队列任务号、排队等认领（不写「默认会这样执行」）')

        mb.claim(jid)
        out = render(node, env, tmp, run_id, line)
        check('Muse 在做' in out['summary'] and 'Muse 已认领，在做' in out['detail'], '认领以后：Muse 在做')

        # 普通的暂停：step 模式停在第 1 步
        c2 = ScriptClient([])
        c2.offline = True
        r2 = wc.start(demo, entry='run_test.zs', mode='step', client=c2)['run']
        out = render(node, env, tmp, r2)
        check('暂停在第 1 步 · 等外部决定' in out['summary'] and 'Muse' not in out['summary'],
              '普通的暂停照旧：暂停在第 1 步 · 等外部决定')
    finally:
        mb.JOBS = old_jobs
        shutil.rmtree(tmp, ignore_errors=True)
    print('查看器里的 Muse 步骤：全部通过')


if __name__ == '__main__':
    run()
