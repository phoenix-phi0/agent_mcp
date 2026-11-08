import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))  # 项目根，run_all 不设 PYTHONPATH
"""编排过程记录（runs/*.json）：完整跑一遍、中途出错各一次，检查文件内容。

在临时目录里复制一份 workflow_demo 跑，不往真 demo 目录写 runs/。
"""
import json
import shutil
import tempfile
from pathlib import Path

from dsl.client import ScriptClient
from tools.dsl import DSLEngine

ROOT = Path(__file__).resolve().parents[2]
_sys.path.insert(0, str(Path(__file__).resolve().parent))
from wf_fixtures import REPLIES, impl  # noqa: E402  每条都符合 workflow_demo 的节点格式


def demo_copy(tmp):
    dst = tmp / 'workflow_demo'
    shutil.copytree(ROOT / 'workflow_demo', dst,
                    ignore=shutil.ignore_patterns('runs', 'work', '*.bak-*', '__pycache__'))
    return dst


def engine_for(demo, replies):
    client = ScriptClient(replies)
    client.offline = True
    return DSLEngine(client=client, workdir=demo, verbs_root=ROOT / 'verbs', verbose=False), client


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print('  ✓', msg)


def run():
    tmp = Path(tempfile.mkdtemp())
    try:
        # 1. 完整跑一遍
        demo = demo_copy(tmp)
        engine, client = engine_for(demo, list(REPLIES))
        engine.run_file('run.zs')
        files = sorted((demo / 'runs').glob('*.json'))
        check(len(files) == 1, '生成一份过程记录')
        check(engine.vars['workflow_trace'] == str(files[0]), 'workflow_trace 变量指向这份文件')
        check(not list((demo / 'runs').glob('*.tmp')), '没有残留临时文件')
        t = json.loads(files[0].read_text(encoding='utf-8'))
        check(t['status'] == 'done' and t['error'] is None and t['finished'], '状态 done')
        check(t['workflow'] == 'workflow' and files[0].name.endswith('-workflow.json'), '文件名带脚本名')
        check(t['inputs'] == {'content': '实现用户接口', 'stack': 'Python3+pytest，第三方包写进requirements.txt',
                              'test_content': '验证用户接口'}, '记下输入变量')
        tasks = [e for e in t['events'] if e['type'] == 'task']
        check(tasks[0]['task'] == '实现用户接口。技术栈：Python3+pytest，第三方包写进requirements.txt', '技术栈交给接口约定')
        check(tasks[4]['task'].startswith('任务分配。技术栈：Python3+pytest'), '技术栈交给任务分配')
        check(len(tasks) == len(client.calls) == 10, '每次 agent 调用一条 task 事件')
        check([e['result'] for e in tasks] == REPLIES, '结果按顺序记录')
        check([e['role'] for e in tasks] == ['ARCHITECT', 'ARCHITECT_GLM', 'ARCHITECT', 'ARCHITECT_GLM',
                                            'ARCHITECT', 'ENGINEER', 'ENGINEER', 'QA_ENGINEER',
                                            'ENGINEER', 'QA_ENGINEER'], '角色顺序对')
        check(all(e['status'] == 'ok' and e['model'] and isinstance(e['seconds'], float) for e in tasks),
              '每条带模型、耗时、状态')
        check(tasks[2]['name'] == '接口修改' and tasks[2]['context'] == REPLIES[0]
              and '需修改' in tasks[2]['task'], '接口修改：任务是审查意见，参考文本是上一版约定')
        check(tasks[8]['task'] == '修边界条件', '代码修改：任务取自 QA 的 task')
        check(tasks[7]['context'] == [REPLIES[5], REPLIES[6]], '测试：参考文本是 task_results')
        check([e.get('format') for e in tasks] == ['contract', 'review', 'contract_revision', 'review',
                                                  'assignment', 'implementation', 'implementation',
                                                  'acceptance', 'implementation', 'acceptance'],
              '每步记下格式名')

        # 1b. 回复不符合格式（实现记录缺字段）：这一步失败，原样回复记进 raw
        demo3 = demo_copy(tmp / 'c')
        bad = impl('接口')
        del bad['verification']
        engine3, _ = engine_for(demo3, REPLIES[:5] + [bad])
        try:
            engine3.run_file('run.zs')
            raise AssertionError('应当报错')
        except AssertionError:
            raise
        except Exception as e:
            check('不符合格式 implementation' in str(e) and 'verification' in str(e), '格式不对：报错里写明哪个格式、缺什么')
        t3 = json.loads(next((demo3 / 'runs').glob('*.json')).read_text(encoding='utf-8'))
        last = [e for e in t3['events'] if e['type'] == 'task'][-1]
        check(last['status'] == 'error' and 'summary' in json.loads(last['raw']), '不合格的回复原样记进 raw')
        jumps = [e for e in t['events'] if e['type'] == 'jump']
        check([(j['target'], j['count']) for j in jumps] == [('a', 1), ('b', 1)], '两次跳转各一条')
        ifs = [e['value'] for e in t['events'] if e['type'] == 'if']
        check(ifs == [True, False, True, False], '条件判断的真假都记下')
        each = [e for e in t['events'] if e['type'] == 'each']
        check(len(each) == 1 and each[0]['count'] == 2, '遍历记条数')
        stores = [e['size'] for e in t['events'] if e['type'] == 'store']
        check(stores == [1, 2], '存储记累计条数')
        check([e['seq'] for e in t['events']] == list(range(1, len(t['events']) + 1)), 'seq 连续')

        # 2. 中途出错：第 6 次回复不是对象，ENGINEER 报错。前面 5 步 + 出错那步都要留下
        demo2 = demo_copy(tmp / 'b')
        engine2, _ = engine_for(demo2, REPLIES[:5] + ['不是 JSON'])
        try:
            engine2.run_file('run.zs')
            raise AssertionError('应当报错')
        except AssertionError:
            raise
        except Exception:
            pass
        t2 = json.loads(next((demo2 / 'runs').glob('*.json')).read_text(encoding='utf-8'))
        tasks2 = [e for e in t2['events'] if e['type'] == 'task']
        check(t2['status'] == 'error' and 'ENGINEER' in (t2['error'] or ''), '出错时状态 error、带原因')
        check(len(tasks2) == 6 and tasks2[-1]['status'] == 'error' and tasks2[-1]['role'] == 'ENGINEER',
              '出错那步也记下，前面 5 步都在')
        print('workflow trace passed')
    finally:
        shutil.rmtree(tmp)


if __name__ == '__main__':
    run()
