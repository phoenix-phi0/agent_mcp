import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))  # 项目根，run_all 不设 PYTHONPATH
import unittest
import tempfile
import json
from pathlib import Path

from tools.dsl import DSLEngine, DSLError
from dsl.client import ScriptClient


SCRIPT = '''接口约定
    任务 {content}
    角色 ARCHITECT
    记录 contract
标记:a
任务研讨
    任务 {content}
    角色 ARCHITECT_GLM
    文本 contract
    记录 discussion
如果 discussion.decide == 需修改
    接口修改
        任务 {content}
        文本 discussion
        角色 ARCHITECT
        记录 contract
    跳转 a 最大 5
任务分配
    文本 contract
    角色 ARCHITECT
    记录 assignment
遍历 task 于 assignment.tasks
    任务实现
        任务 task.content
        角色 task.agent
        记录 task_result
    存储 task_results task_result
标记:b
测试
    任务 {test_content}
    角色 QA_ENGINEER
    记录 test_discussion
如果 test_discussion.decide == 需修改
    代码修改
        任务 test_discussion.task
        角色 ENGINEER
        记录 task_result
    跳转 b 最大 5
'''


def profiles(directory):
    for name in ('ARCHITECT', 'ARCHITECT_GLM', 'QA_ENGINEER',
                 'ENGINEER', 'ENGINEER_A', 'ENGINEER_B'):
        folder = Path(directory, 'agents', name)
        folder.mkdir(parents=True)
        (folder / 'SOUL.md').write_text(f'你是 {name}。', encoding='utf-8')
        (folder / 'agent.json').write_text(json.dumps({
            'model': 'cli:claude/sonnet', 'effort': 'medium',
            'tools': [], 'skills': [], 'packages': []}), encoding='utf-8')


def test_workflow_jump_roles_and_records():
    client = ScriptClient([
        {'version': 1},
        {'decide': '需修改'},
        {'version': 2},
        {'decide': '通过'},
        {'tasks': [{'content': '做 A', 'agent': 'ENGINEER_A'},
                   {'content': '做 B', 'agent': 'ENGINEER_B'}]},
        {'done': 'A'}, {'done': 'B'},
        {'decide': '需修改', 'task': '修 A'},
        {'done': '修复'},
        {'decide': '通过'},
    ])
    client.offline = True
    with tempfile.TemporaryDirectory() as directory:
        profiles(directory)
        Path(directory, 'flow.wf').write_text(SCRIPT, encoding='utf-8')
        engine = DSLEngine(client=client, workdir=directory, verbose=False,
                           verbs_root=Path(__file__).resolve().parents[2] / 'verbs')
        engine.vars.update(content='做项目', test_content='测试项目')
        engine.run('用包 workflow\n编排执行 flow.wf')
    assert engine.vars['contract'] == {'version': 2}
    assert engine.vars['task_results'] == [{'done': 'A'}, {'done': 'B'}]
    assert engine.vars['task_result'] == {'done': '修复'}
    assert len(client.calls) == 10
    assert 'ENGINEER_A' in client.calls[5].get('prompt', '') or '做 A' in client.calls[5]['prompt']


def test_jump_limit_fails():
    client = ScriptClient([{'x': 1}, {'decide': '需修改'}])
    client.offline = True
    with tempfile.TemporaryDirectory() as directory:
        profiles(directory)
        Path(directory, 'flow.wf').write_text(SCRIPT.replace('最大 5', '最大 1', 1), encoding='utf-8')
        engine = DSLEngine(client=client, workdir=directory, verbose=False,
                           verbs_root=Path(__file__).resolve().parents[2] / 'verbs')
        engine.vars['content'] = 'x'
        with unittest.TestCase().assertRaisesRegex(DSLError, '超过最大 1 次'):
            engine.run('用包 workflow\n编排执行 flow.wf')


def test_old_dsl_still_works():
    engine = DSLEngine(client=ScriptClient([]), verbose=False)
    assert engine.run('设 x = 2\n如果 {x} == 2\n打印 ok\n结束') == 'ok'


def test_zs_review_verb():
    client = ScriptClient([{'result': {'decision': '需修改', 'issues': ['缺测试']},
                            'status': '成功', 'reason': ''}])
    engine = DSLEngine(client=client, verbose=False,
                       verbs_root=Path(__file__).resolve().parents[2] / 'verbs')
    engine.run('用包 workflow\n设 review = 审查任务 材料 标准')
    assert engine.vars['review']['result']['decision'] == '需修改'
    assert engine.vars['review']['result']['issues'] == ['缺测试']
    assert len(client.calls) == 1


if __name__ == "__main__":
    for test in (test_workflow_jump_roles_and_records, test_jump_limit_fails, test_old_dsl_still_works, test_zs_review_verb):
        test()
    print("4 workflow tests passed")
