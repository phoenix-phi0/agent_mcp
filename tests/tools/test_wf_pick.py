import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))  # 项目根，run_all 不设 PYTHONPATH
"""编排脚本的「文本」「存储」写几项：只把下一步要用的部分交出去。

- 文本 a b.c {d}：拼成 {"a":…, "b.c":…, "d":…}，模型拿到的参考文本只有这几项；
- 存储 x k=a.b …：每次只存挑出来的字段；
- 只写一个引用、写普通文字：和原来一样；
- 引用取不到值、键重复：报错。
全程离线假模型。
"""
import json
import tempfile
import unittest
from pathlib import Path

from dsl.client import ScriptClient
from tools.dsl import DSLEngine, DSLError

ROOT = Path(__file__).resolve().parents[2]

FLOW = '''清空 built
遍历 m 于 arch.modules
    实现
        任务 实现 {m.name}
        角色 ENGINEER
        文本 m built arch.stack
        记录 impl
    验收
        任务 验收
        角色 QA_ENGINEER
        文本 impl
        记录 check
    存储 built name=m.name api={check.api} diff=check.deviations
收尾
    任务 汇总
    角色 ARCHITECT
    文本 built
    记录 summary
'''

ARCH = {'stack': 'flask', 'modules': [{'name': 'a', 'big': 'x' * 500}, {'name': 'b', 'big': 'y' * 500}],
        'integration': ['z' * 2000]}
REPLIES = [
    {'v': 'A'}, {'api': ['f()'], 'deviations': [], 'checked': ['c' * 300]},
    {'v': 'B'}, {'api': ['g()'], 'deviations': ['g 多了参数'], 'checked': ['c' * 300]},
    {'summary': 'ok'},
]


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


def run_flow(directory, flow, replies):
    c = ScriptClient(list(replies))
    c.offline = True
    Path(directory, 'flow.wf').write_text(flow, encoding='utf-8')
    engine = DSLEngine(client=c, workdir=directory, verbose=False, verbs_root=ROOT / 'verbs')
    engine.vars['arch'] = ARCH
    engine.run('用包 workflow\n编排执行 flow.wf')
    return engine, c


def context_of(prompt):
    line = next(x for x in prompt.splitlines() if x.startswith('参考文本：'))
    return json.loads(line[len('参考文本：'):])


def test_pick():
    with tempfile.TemporaryDirectory() as d:
        profiles(d)
        engine, c = run_flow(d, FLOW, REPLIES)
        built = engine.vars['built']
        check(built == [{'name': 'a', 'api': ['f()'], 'diff': []},
                        {'name': 'b', 'api': ['g()'], 'diff': ['g 多了参数']}],
              '存储只存挑出来的字段（checked 没存进来），键用等号前的名字')
        first = context_of(c.calls[0]['prompt'])
        check(first == {'m': ARCH['modules'][0], 'built': [], 'arch.stack': 'flask'},
              '第一个模块的参考文本：自己的模块、空的 built、技术栈，没有别的模块和 integration')
        second = context_of(c.calls[2]['prompt'])
        check(second['m']['name'] == 'b' and second['built'] == built[:1] and 'integration' not in json.dumps(second),
              '第二个模块拿到第一个模块的实际接口')
        check(context_of(c.calls[1]['prompt']) == {'v': 'A'}, '只写一个引用：和原来一样给整个值')
        events = json.loads(Path(engine.vars['workflow_trace']).read_text(encoding='utf-8'))['events']
        req = [e for e in events if e['type'] == 'task']
        check(req and req[0]['context']['arch.stack'] == 'flask', '运行记录里的参考文本也是拼好的对象')


def test_list_fields():
    flow = ('问\n    任务 说说\n    角色 ARCHITECT\n    文本 mods=arch.modules[name] stack=arch.stack\n    记录 r\n'
            '如果 r.issues != []\n    追问\n        任务 有问题\n        角色 ARCHITECT\n        文本 r.issues\n        记录 r2\n')
    with tempfile.TemporaryDirectory() as d:
        profiles(d)
        engine, c = run_flow(d, flow, [{'issues': []}])
        check(context_of(c.calls[0]['prompt']) == {'mods': [{'name': 'a'}, {'name': 'b'}], 'stack': 'flask'},
              '列表取字段：每个模块只留 name，big 没传')
        check(len(c.calls) == 1, '列表为空：「如果 x != []」不成立')
        engine, c = run_flow(d, flow, [{'issues': ['缺接口']}, {'ok': 1}])
        check(len(c.calls) == 2 and context_of(c.calls[1]['prompt']) == ['缺接口'], '列表不空：条件成立，往下问')
        bad = flow.replace('arch.modules[name]', 'arch.stack[name]')
        with unittest.TestCase().assertRaisesRegex(DSLError, r'只能用在对象或对象列表上'):
            run_flow(d, bad, [{'issues': []}])
        print('  ✓ 取字段用在字符串上：报错')


def test_plain_text_unchanged():
    flow = '问\n    任务 说说\n    角色 ARCHITECT\n    文本 一段 普通的 说明\n    记录 r\n'
    with tempfile.TemporaryDirectory() as d:
        profiles(d)
        _, c = run_flow(d, flow, [{'ok': 1}])
        check('参考文本：一段 普通的 说明' in c.calls[0]['prompt'], '普通的几个词：照旧当文字')


def test_errors():
    with tempfile.TemporaryDirectory() as d:
        profiles(d)
        bad = FLOW.replace('文本 m built arch.stack', '文本 m built arch.nothing')
        with unittest.TestCase().assertRaisesRegex(DSLError, '文本里的 arch.nothing 没有值'):
            run_flow(d, bad, REPLIES)
        print('  ✓ 文本里有一项取不到：报错，不悄悄漏掉')
        bad = FLOW.replace('diff=check.deviations', 'name=check.deviations')
        with unittest.TestCase().assertRaisesRegex(DSLError, '存储里 name 写了两次'):
            run_flow(d, bad, REPLIES)
        print('  ✓ 键重复：报错')
        bad = FLOW.replace('diff=check.deviations', 'diff=check.nope')
        with unittest.TestCase().assertRaisesRegex(DSLError, '存储里的 check.nope 没有值'):
            run_flow(d, bad, REPLIES)
        print('  ✓ 存储的字段取不到：报错')


if __name__ == '__main__':
    for name, fn in list(globals().items()):
        if name.startswith('test_'):
            print(name)
            fn()
    print('全部通过')
