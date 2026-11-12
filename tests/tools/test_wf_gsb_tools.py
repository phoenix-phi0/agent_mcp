import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))  # 项目根，run_all 不设 PYTHONPATH
"""agentic 角色挂 gsb_tools 的探针 / 独立审查：只开 probe、review（和各自的 *_wait），
别的（run_wait 任意 shell、read_files 任意路径……）角色卡里写了也拒；按 gsb_mcp 给的配置起服务，
tools/list 正好是这四个。不调模型。"""
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from tools import llm_router
from tools.dsl import DSLEngine
from tools.dsl_core import DSLError

ROOT = Path(__file__).resolve().parents[2]


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print('  ✓', msg)


def tools_list(server):
    env = dict(os.environ, **server['env'])
    p = subprocess.Popen([server['command'], *server['args']], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True, encoding='utf-8', env=env, cwd=tempfile.gettempdir())
    try:
        for i, (m, params) in enumerate([('initialize', {'protocolVersion': '2025-06-18'}), ('tools/list', {})], 1):
            p.stdin.write(json.dumps({'jsonrpc': '2.0', 'id': i, 'method': m, 'params': params}) + '\n')
            p.stdin.flush()
            r = json.loads(p.stdout.readline())
        return [t['name'] for t in r['result']['tools']]
    finally:
        p.stdin.close()
        p.wait(10)


def load(tmp, mcp_tools):
    import importlib.util
    spec = importlib.util.spec_from_file_location('ag', ROOT / 'verbs/workflow/_agents.py')
    ag = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ag)
    card = tmp / 'agents' / 'X'
    card.mkdir(parents=True, exist_ok=True)
    (card / 'SOUL.md').write_text('# X', encoding='utf-8')
    (card / 'agent.json').write_text(json.dumps({'model': 'cli:claude/haiku', 'agentic': {
        'cwd': '.', 'allowed_tools': ['Read'], 'mcp_tools': mcp_tools}}), encoding='utf-8')
    return ag.load_agent(DSLEngine(workdir=tmp, verbose=False), 'X')


def run():
    server, names = llm_router.gsb_mcp(['probe', 'review'])
    check(names == ['mcp__gsb__probe', 'mcp__gsb__probe_wait', 'mcp__gsb__review', 'mcp__gsb__review_wait'],
          '放行的工具名：probe、review 和各自的 wait')
    check(tools_list(server) == ['probe', 'probe_wait', 'review', 'review_wait'],
          '按这份配置起 gsb_tools，tools/list 正好是这四个，没有 run_wait、read_files')
    check(tools_list(llm_router.gsb_mcp(['probe'])[0]) == ['probe', 'probe_wait'], '只要 probe 就只有 probe 两个')
    check(llm_router.gsb_mcp([]) == (None, []) and llm_router.gsb_mcp(['run_wait']) == (None, []),
          '空的、或不在白名单里的：不挂服务')
    # 后台跑编排的进程 PATH 里可能没有 claude 所在目录（真跑时 review 报过「找不到 claude」）：
    # PATH 只剩系统目录时，配置里照样带上 claude 的绝对路径
    old_path = os.environ.get('PATH', '')
    os.environ['PATH'] = '/usr/bin:/bin'
    try:
        bin_ = llm_router.gsb_mcp(['review'])[0]['env'].get('GSB_CLAUDE_BIN')
    finally:
        os.environ['PATH'] = old_path
    if shutil.which('claude') or (Path.home() / '.local/bin/claude').is_file():
        check(bin_ and os.access(bin_, os.X_OK), f'PATH 里没有 claude 时也传绝对路径：{bin_}')
    else:
        print('  - 跳过：这台机器没装 claude')

    # 每个节点的实际用量：claude 结果里的费用和 token，加上 cost_log 里记的工具内部花费
    tmpd = Path(tempfile.mkdtemp())
    log = tmpd / 'tool.jsonl'
    log.write_text(json.dumps({'cost_usd': 0.004}) + '\n' + json.dumps({'cost_usd': 0.006}) + '\n')
    u = llm_router._usage({'total_cost_usd': 0.02, 'num_turns': 7, 'usage': {'input_tokens': 10, 'output_tokens': 5}},
                          log, 12.34)
    check(u['cost_usd'] == 0.02 and u['tool_calls'] == 2 and u['tool_cost_usd'] == 0.01 and u['total_usd'] == 0.03
          and u['turns'] == 7 and u['seconds'] == 12.3, '用量：claude 的费用加工具的费用，记轮数和耗时')
    check(llm_router._usage({'total_cost_usd': 0.05})['total_usd'] == 0.05, '没有工具花费：合计就是 claude 的费用')
    check(llm_router._usage(None) is None, '什么都拿不到：None')
    check(llm_router._last_json('noise\n{"total_cost_usd": 1}\n') == {'total_cost_usd': 1}, '从输出里取最后一行 JSON')
    check(llm_router.agent_mcp(['algo']) == ({}, []), '推理机已去掉：写 algo 什么都不挂')
    shutil.rmtree(tmpd)

    tmp = Path(tempfile.mkdtemp())
    try:
        prof = load(tmp, ['probe'])
        check(prof['agentic']['mcp_tools'] == ['probe'], '角色卡的 agentic.mcp_tools 带进调用参数')
        for bad in (['run_wait'], ['read_files'], ['algo'], 'probe'):
            try:
                load(tmp, bad)
                raise AssertionError(f'应当拒绝 {bad}')
            except DSLError as e:
                check('mcp_tools 只能从' in str(e), f'角色卡写 {bad!r}：拒绝')
        # 写成「等于」而不是「属于白名单」：卡里漏了 mcp_tools 时空集合也属于白名单，那样测不出来（真漏过一次）
        for name, want in (('ENGINEER', ['probe', 'review']), ('ENGINEER_SENIOR', ['probe', 'review']),
                           ('QA_ENGINEER', ['probe']), ('ENGINEER_LITE', []), ('TEST_ENGINEER', [])):
            d = json.loads((ROOT / 'workflow_demo/agents' / name / 'agent.json').read_text(encoding='utf-8'))
            check(d['agentic'].get('mcp_tools', []) == want, f'workflow_demo 的 {name} 卡挂的工具：{want}')
    finally:
        shutil.rmtree(tmp)
    print('wf gsb tools passed')


if __name__ == '__main__':
    run()
