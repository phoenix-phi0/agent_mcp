import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))  # 项目根，run_all 不设 PYTHONPATH
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))
"""查看器接入外部控制和格式提交：用离线假模型造三份受控记录，交给 trace_server.read_trace
（带上 _control、_formats），再用 jsdom 打开 trace_view.html 渲染，检查页面上看得到：

- 暂停在第几步、默认会怎么执行、提示词和格式定义（外部能照着自己执行）
- 外部交的结果、换卡换模型的步骤有标记
- 失败的尝试带原始回复、上次失败的原因
- 中止的状态

jsdom 找的是 node_modules（项目根、或环境变量 NODE_PATH）；没装就只跑 Python 这一半，并说明跳过了。
"""
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from dsl.client import ScriptClient
from tools import trace_server
from tools import workflow_ctl as wc
from wf_fixtures import REPLIES, contract

ROOT = Path(__file__).resolve().parents[2]
VIEW = ROOT / 'tools' / 'trace_view.html'
CHECK = ROOT / 'tests' / 'e2e' / 'trace_view_check.js'


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print('  ✓', msg)


def client(replies):
    c = ScriptClient(list(replies))
    c.offline = True
    return c


def demo_copy(tmp, name):
    dst = tmp / name
    shutil.copytree(ROOT / 'workflow_demo', dst,
                    ignore=shutil.ignore_patterns('runs', 'work', '*.bak-*', '__pycache__'))
    return dst


def jsdom_env():
    env = dict(os.environ)
    paths = [p for p in (env.get('NODE_PATH', ''), str(ROOT / 'node_modules')) if p]
    env['NODE_PATH'] = os.pathsep.join(paths)
    node = shutil.which('node')
    if not node:
        return None, env
    r = subprocess.run([node, '-e', "require('jsdom')"], env=env, capture_output=True, text=True)
    return (node if r.returncode == 0 else None), env


def render(node, env, tmp, run, line=None):
    data = trace_server.read_trace(ROOT / run)
    f = tmp / (Path(run).stem + '.view.json')
    f.write_text(json.dumps(data, ensure_ascii=False, default=str), encoding='utf-8')
    cmd = [node, str(CHECK), str(VIEW), str(f)] + ([str(line)] if line else [])
    r = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise AssertionError(f'node 出错：{r.stderr[-1500:]}')
    out = json.loads(r.stdout)
    if out['errors']:
        raise AssertionError(f'页面脚本报错：{out["errors"]}')
    return out


def cls(out, line):
    return dict(out['classes']).get(str(line), '')


def run():
    (ROOT / 'data/tmp').mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix='wfview-', dir=ROOT / 'data/tmp'))
    try:
        # A：外部交第 1 步、内置跑第 2 步、换卡换模型跑第 3 步，停在第 4 步
        a = demo_copy(tmp, 'a')
        ca = client(REPLIES[1:])
        ra = wc.start(a, client=ca)['run']
        wc.submit(ra, REPLIES[0], client=ca)
        wc.execute(ra, wait=True, client=ca)
        wc.execute(ra, model='cli:goose/glm-5.3', role='ARCHITECT_GLM', wait=True, client=ca)
        data = trace_server.read_trace(ROOT / ra)
        check(data['_control']['mode'] == 'step' and [h['op'] for h in data['_control']['history']]
              == ['start', 'submit', 'execute', 'execute'], 'read_trace 带上控制文件：模式、操作记录')
        check(sorted(data['_formats']) == ['acceptance', 'assignment', 'contract', 'contract_revision',
                                           'implementation', 'review'], 'read_trace 带上脚本里用到的 6 个格式定义')
        runs = trace_server.list_runs(a / 'runs')
        check(runs[0]['status'] == 'waiting' and runs[0]['waiting_step'] == 4 and runs[0]['controlled']
              and runs[0]['calls'] == 3, '运行列表：暂停在第 4 步、受控、3 次执行（停住那条不算）')

        # B：第 1 步模型回的不是 JSON，停在第 1 步
        b = demo_copy(tmp, 'b')
        cb = client(['这不是 JSON'])
        rb = wc.start(b, client=cb)['run']
        wc.execute(rb, wait=True, client=cb)

        # C：中止
        c = demo_copy(tmp, 'c')
        rc = wc.start(c, client=client([]))['run']
        wc.submit(rc, contract('v1'), client=client([]))
        wc.abort(rc)

        node, env = jsdom_env()
        if not node:
            print('  - 跳过页面渲染：没有 node 或 jsdom（装到项目 node_modules，或设 NODE_PATH）')
            print('trace view passed（只跑了 Python 部分）')
            return

        o = render(node, env, tmp, ra)
        check('暂停 · 等外部决定' in o['summary'] and '停在' in o['summary'] and '第 4 步' in o['summary'],
              '概况：暂停 · 等外部决定，停在第 4 步')
        check('外部控制' in o['summary'] and '逐步，每步停' in o['summary'], '概况：外部控制的模式')
        check('workflow.submit' in o['note'], '提示里写了外部能做什么')
        check('格式 contract' in o['flow'] and '格式 review' in o['flow'], '流程图节点上有格式名')
        check('暂停 · 第 4 步等外部' in o['flow'] and 'waiting' in cls(o, 7), '停住的节点（任务研讨）标成暂停')
        check('外部交' in o['flow'] and '换卡 · 换模型' in o['flow'], '外部交过、换过卡和模型的节点有标记')
        check(o['bars'] == 3, '耗时条只画 3 次执行，停住的不算')
        check('第 4 步 · 暂停' in o['detail'] and '默认会这样执行' in o['detail']
              and '提示词（外部自己执行时照这个发）' in o['detail'] and '系统提示（角色卡）' in o['detail'],
              '默认选中停住的节点：摊开默认执行方式、提示词、角色卡')
        check('格式定义' in o['detail'] and 'decide' in o['detail'], '详情里能看格式定义')

        o = render(node, env, tmp, ra, line=14)
        check(o['head'].startswith('接口修改') and '换卡 ARCHITECT → ARCHITECT_GLM' in o['detail']
              and '换模型 cli:goose/glm-5.3' in o['detail'] and '外部指定执行' in o['detail'],
              '点「接口修改」：看得到换卡、换模型、来源')
        o = render(node, env, tmp, ra, line=1)
        check('外部提交结果' in o['detail'], '点「接口约定」：看得到是外部交的结果')

        o = render(node, env, tmp, rb)
        check('err' in cls(o, 1) and 'waiting' in cls(o, 1), '失败后停住的节点同时标出错和暂停')
        check('模型的原始回复' in o['detail'] and '这不是 JSON' in o['detail'] and '上次失败的原因' in o['detail'],
              '失败那次带原始回复，暂停那条带上次失败的原因')
        check('这一步上次失败' in o['note'], '概况提示里也写了上次失败')

        o = render(node, env, tmp, rc)
        check('已中止' in o['summary'] and '已中止' in o['flow'], '中止的运行：概况和结束节点都写已中止')
        o = render(node, env, tmp, rc, line=-2)
        check('外部控制的操作' in o['detail'] and 'abort' in o['detail'], '结束节点详情里列出外部控制的操作')
        print('trace view passed')
    finally:
        shutil.rmtree(tmp)


if __name__ == '__main__':
    run()
