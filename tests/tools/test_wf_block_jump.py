import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))  # 项目根，run_all 不设 PYTHONPATH
"""编排脚本的块内跳转：标记可以写在「遍历」「如果」的子块里，跳转只能跳到同一层或外层的标记。

- 遍历里每一项各自返工：次数按项分开算，每项最多 max 次；
- 跳进别的子块、标记重名：解析时就拒，一次模型都不调；
- 原来的写法（如果里跳到最外层、遍历里跳到外层）照旧，次数照旧全局算；
- 受控运行：逐步停、每次从头回放，块内跳转走出来的步骤和一口气跑完一样；回退到中间某步再跑也一样。
全程离线假模型。
"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from dsl.client import ScriptClient
from tools.dsl import DSLEngine, DSLError
from tools import workflow_ctl as wc

ROOT = Path(__file__).resolve().parents[2]

FLOW = '''遍历 m 于 modules
    标记:r
    实现
        任务 m.name
        角色 ENGINEER
        记录 impl
    验收
        任务 m.name
        角色 QA_ENGINEER
        文本 impl
        记录 check
    如果 check.decide == 需修改
        跳转 r 最大 2
    存储 done impl
收尾
    任务 汇总
    角色 ARCHITECT
    文本 done
    记录 summary
'''

ENTRY = '用包 workflow\n编排执行 flow.wf\n'
# 受控运行用：模块清单由第一步「计划」给出（入口脚本里设不了列表）
PLANNED = '计划\n    任务 列模块\n    角色 ARCHITECT\n    记录 plan\n' + FLOW.replace('于 modules', '于 plan.modules')
PLAN = {'modules': [{'name': 'A'}, {'name': 'B'}]}

# A 返工两次（到上限）才过，B 返工一次
REPLIES = [
    {'v': 'A1'}, {'decide': '需修改'}, {'v': 'A2'}, {'decide': '需修改'}, {'v': 'A3'}, {'decide': '通过'},
    {'v': 'B1'}, {'decide': '需修改'}, {'v': 'B2'}, {'decide': '通过'},
    {'summary': 'ok'},
]
ROLES = ['ENGINEER', 'QA_ENGINEER'] * 5 + ['ARCHITECT']


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print('  ✓', msg)


def profiles(directory):
    for name in ('ARCHITECT', 'QA_ENGINEER', 'ENGINEER'):
        folder = Path(directory, 'agents', name)
        folder.mkdir(parents=True)
        (folder / 'SOUL.md').write_text(f'你是 {name}。', encoding='utf-8')
        (folder / 'agent.json').write_text(json.dumps({
            'model': 'cli:claude/sonnet', 'effort': 'medium', 'tools': [], 'skills': [], 'packages': []}),
            encoding='utf-8')


def client(replies):
    c = ScriptClient(list(replies))
    c.offline = True
    return c


def run_flow(directory, flow, replies, **vars_):
    c = client(replies)
    Path(directory, 'flow.wf').write_text(flow, encoding='utf-8')
    engine = DSLEngine(client=c, workdir=directory, verbose=False, verbs_root=ROOT / 'verbs')
    engine.vars.update(modules=[{'name': 'A'}, {'name': 'B'}], **vars_)
    engine.run('用包 workflow\n编排执行 flow.wf')
    return engine, c


def trace_of(engine):
    return json.loads(Path(engine.vars['workflow_trace']).read_text(encoding='utf-8'))


def test_each_item_reworks_separately():
    with tempfile.TemporaryDirectory() as d:
        profiles(d)
        engine, c = run_flow(d, FLOW, REPLIES)
        check(engine.vars['done'] == [{'v': 'A3'}, {'v': 'B2'}], '每个模块返工到通过，存的是最后一版')
        check(len(c.calls) == 11, '一共 11 次调用：A 三轮、B 两轮、收尾一次')
        jumps = [(e['count'], e['item']['index']) for e in trace_of(engine)['events'] if e['type'] == 'jump']
        check(jumps == [(1, 1), (2, 1), (1, 2)], '跳转次数按项分开算：A 用了 2 次，B 从 1 重新算，事件带第几项')


def test_item_limit():
    with tempfile.TemporaryDirectory() as d:
        profiles(d)
        replies = REPLIES[:4] + [{'v': 'A3'}, {'decide': '需修改'}]
        with unittest.TestCase().assertRaisesRegex(DSLError, '跳转 r 超过最大 2 次'):
            run_flow(d, FLOW, replies)
        print('  ✓ 一项返工超过上限：报错停下')


def test_exhausted_continue():
    with tempfile.TemporaryDirectory() as d:
        profiles(d)
        flow = FLOW.replace('跳转 r 最大 2', '跳转 r 最大 2 用完继续')
        replies = REPLIES[:4] + [{'v': 'A3'}, {'decide': '需修改'},
                                 {'v': 'B1'}, {'decide': '通过'}, {'summary': 'ok'}]
        engine, c = run_flow(d, flow, replies)
        events = [e for e in trace_of(engine)['events'] if e['type'] == 'jump_exhausted']
        line = next(i for i, row in enumerate(flow.splitlines(), 1) if '跳转 r' in row)
        check(len(events) == 1 and all(events[0].get(k) == v for k, v in {
            'line': line, 'target': 'r', 'count': 3, 'max': 2,
            'item': {'index': 1, 'total': 2}}.items()), '次数用完记录事件和遍历项')
        check(engine.vars['done'] == [{'v': 'A3'}, {'v': 'B1'}] and len(c.calls) == 9
              and engine.vars['summary'] == {'summary': 'ok'}, '用完后继续本项、下一项和收尾步骤')
        with unittest.TestCase().assertRaisesRegex(DSLError, '超过最大 2 次'):
            run_flow(d, FLOW, replies)
        print('  ✓ 不带用完继续时仍然报超限')


def test_parse_errors():
    with tempfile.TemporaryDirectory() as d:
        profiles(d)
        bad_into = FLOW + '如果 summary.summary == ok\n    跳转 r 最大 1\n'
        c = client([])
        Path(d, 'flow.wf').write_text(bad_into, encoding='utf-8')
        engine = DSLEngine(client=c, workdir=d, verbose=False, verbs_root=ROOT / 'verbs')
        engine.vars['modules'] = []
        with unittest.TestCase().assertRaisesRegex(DSLError, '只能跳到同一层或外层的标记'):
            engine.run('用包 workflow\n编排执行 flow.wf')
        check(len(c.calls) == 0, '从外面跳进遍历里的标记：开跑前就拒，没调模型')
        dup = FLOW.replace('收尾\n', '标记:r\n收尾\n')
        Path(d, 'flow.wf').write_text(dup, encoding='utf-8')
        with unittest.TestCase().assertRaisesRegex(DSLError, '标记重复'):
            engine.run('用包 workflow\n编排执行 flow.wf')
        sib = ('遍历 m 于 modules\n    标记:x\n    存储 out m\n'
               '遍历 n 于 modules\n    如果 n.name == A\n        跳转 x 最大 1\n')
        Path(d, 'flow.wf').write_text(sib, encoding='utf-8')
        with unittest.TestCase().assertRaisesRegex(DSLError, '只能跳到同一层或外层的标记'):
            engine.run('用包 workflow\n编排执行 flow.wf')
        print('  ✓ 标记重名、跳进另一个遍历的标记：都拒')


def test_outer_jump_unchanged():
    """原来的写法：遍历里跳到最外层的标记，离开遍历从头再来；次数全局算，不按项分开。"""
    flow = ('标记:t\n计划\n    任务 列模块\n    角色 ARCHITECT\n    记录 plan\n'
            '遍历 m 于 plan.modules\n    验收\n        任务 m\n        角色 QA_ENGINEER\n        记录 check\n'
            '    如果 check.decide == 需修改\n        跳转 t 最大 1\n')
    with tempfile.TemporaryDirectory() as d:
        profiles(d)
        replies = [{'modules': ['A', 'B']}, {'decide': '通过'}, {'decide': '需修改'},
                   {'modules': ['A', 'B']}, {'decide': '通过'}, {'decide': '通过'}]
        engine, c = run_flow(d, flow, replies)
        jumps = [e for e in trace_of(engine)['events'] if e['type'] == 'jump']
        check(len(c.calls) == 6 and len(jumps) == 1 and 'item' not in jumps[0],
              '遍历里跳到最外层：回到开头重新计划，事件不带项（不按项算）')
        replies = [{'modules': ['A']}, {'decide': '需修改'}, {'modules': ['A']}, {'decide': '需修改'}]
        with unittest.TestCase().assertRaisesRegex(DSLError, '超过最大 1 次'):
            run_flow(d, flow, replies)
        print('  ✓ 跳到最外层的次数全局算：第二次就超')


def test_controlled_replay():
    """受控运行：每一步都从头回放，块内跳转之后的步骤顺序和一口气跑完的一样。"""
    (ROOT / 'data/tmp').mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix='wfjump-', dir=ROOT / 'data/tmp'))
    try:
        demo = tmp / 'w'
        demo.mkdir()
        profiles(demo)
        (demo / 'flow.wf').write_text(PLANNED, encoding='utf-8')
        (demo / 'run.zs').write_text(ENTRY, encoding='utf-8')

        # 逐步：每一步单独执行（每次从头回放）
        c = client([PLAN] + REPLIES)
        s = wc.start(demo, client=c)
        run_id = s['run']
        while s['status'] == 'waiting':
            s = wc.execute(run_id, wait=True, client=c)
        check(s['status'] == 'done' and len(c.calls) == 12, '逐步执行：12 步跑完')
        roles = [x['role'] for x in s['steps']]
        check(roles == ['ARCHITECT'] + ROLES, '步骤顺序和一口气跑完一样（计划、A 三轮、B 两轮、收尾）')
        check([x['step'] for x in s['steps']] == list(range(1, 13)), '步号连续')

        # 回退到 B 的第一次验收（第 9 步），换一个结果：B 一次就过
        c2 = client([{'decide': '通过'}, {'summary': 'ok2'}])
        s = wc.rewind(run_id, 9, client=c2)
        check(s['status'] == 'waiting' and s['pending']['step'] == 9 and s['pending']['role'] == 'QA_ENGINEER',
              '回退到第 9 步：停在 B 的第一次验收')
        s = wc.resume(run_id, wait=True, client=c2)
        check(s['status'] == 'done' and len(c2.calls) == 2 and len(s['steps']) == 10,
              '回退后 B 一次就过：前 8 步回放，后面只调 2 次，共 10 步')
        t = json.loads((ROOT / run_id).read_text(encoding='utf-8'))
        jumps = [(e['count'], e['item']['index']) for e in t['events'] if e['type'] == 'jump']
        check(jumps == [(1, 1), (2, 1)], '回放出来的跳转记录：只剩 A 的两次')
        page_check(run_id, tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def page_check(run_id, tmp):
    """查看器：遍历里的返工回环画得出来，标明按项算（要 node 和 jsdom，没有就跳过）。"""
    import os
    import subprocess
    from tools import trace_server as ts
    data = ts.read_trace((ROOT / run_id).resolve())
    f = tmp / 'trace.json'
    f.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    cands = [x for x in os.environ.get('NODE_PATH', '').split(os.pathsep) if x] + [str(ROOT / 'tests/e2e/node_modules')]
    mods = next((x for x in cands if Path(x, 'jsdom').is_dir()), None)
    if not shutil.which('node') or not mods:
        print('  - 没有 node 或 jsdom，跳过页面检查')
        return
    p = subprocess.run(['node', str(ROOT / 'tests/e2e/trace_block_jump_check.js'), str(f)], capture_output=True,
                       text=True, timeout=120, env={**os.environ, 'NODE_PATH': mods})
    out = json.loads((p.stdout.strip().splitlines() or ['{}'])[-1])
    check(out.get('errors') == [] and any('共 2 次每项最多 2' in x for x in out.get('loops', [])),
          f'流程图：遍历里的回环画出来了，标「共 2 次 / 每项最多 2」（{out.get("loops")}）')
    check(out.get('perItem') and out.get('order'), '点回环：详情写明按项算，列出第几项第几次')


if __name__ == '__main__':
    for test in (test_each_item_reworks_separately, test_item_limit, test_exhausted_continue, test_parse_errors,
                 test_outer_jump_unchanged, test_controlled_replay):
        test()
    print('块内跳转：全部通过')
