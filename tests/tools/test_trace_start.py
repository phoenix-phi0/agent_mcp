"""查看器上启动运行（GET /api/entries、POST /api/start 和列表页的「新建运行」）：离线，不开端口、不调模型。

- 入口清单：只列工作目录下调「编排执行」的 .zs，带流程里的节点名和角色、agents/ 下的卡；只读服务不给；
- 启动：逐步模式只走到第一个节点前停，不调模型；自动模式交给后台（这里替换掉，只核对有没有交）；
  入口越界、不存在、不是编排入口，换到不存在的卡，参数不对 → 400，也不留下运行记录；
- 页面：jsdom 里按人的操作填一遍（tests/e2e/trace_start_check.js），把页面真发出的请求交给真的查看服务启动，
  核对控制文件。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import json
import os
import subprocess
import tempfile
from unittest.mock import patch

os.environ.setdefault('ZHIPU_API_KEY', 'dummy-for-offline-tests')   # 引擎建默认客户端要它；这里一次模型都不调

from tools import trace_server
from tools import workflow_ctl as wc
from test_trace_confirm import call
from test_workflow_ctl import demo_copy


def workdir(tmp):
    wd = demo_copy(tmp, 'wd')
    (wd / 'runs').mkdir(exist_ok=True)
    (wd / 'plain.zs').write_text('# 不是编排入口\n打印 你好\n', encoding='utf-8')
    return wd


def handler(wd, write=True):
    return trace_server.make_handler(wd / 'runs', write=write)


def start(wd, **body):
    return call(handler(wd), 'POST', '/api/start', body)


def ctl(wd, name):
    return json.loads((wd / 'runs' / name).with_suffix('.ctl').read_text(encoding='utf-8'))


def test_entries(tmp):
    wd = workdir(tmp)
    code, out = call(handler(wd), 'GET', '/api/entries')
    assert code == 200, out
    names = [e['entry'] for e in out['entries']]
    assert 'run_project.zs' in names and 'plain.zs' not in names, names
    proj = next(e for e in out['entries'] if e['entry'] == 'run_project.zs')
    assert proj['workflow'] == 'project_workflow' and proj['title'].startswith('整项目流程')
    assert proj['nodes'][:2] == ['架构设计', '架构审查'] and '模块验收' in proj['nodes'], proj['nodes']
    assert {'ARCHITECT', 'QA_ENGINEER', 'TEST_ENGINEER', 'ENGINEER_LITE'} <= set(proj['roles']), proj['roles']
    assert '如果 arch_review.decide == 需修改' not in proj['nodes'], '「如果」不是节点'
    assert 'ENGINEER_GPT' in [a['name'] for a in out['agents']]
    code, out = call(handler(wd, write=False), 'GET', '/api/entries')
    assert code == 403 and '只读' in out['error']


def test_start_rejects(tmp):
    wd = workdir(tmp)
    for body, message in [({}, '.zs 文件名'),
                          ({'entry': '../run.zs'}, '.zs 文件名'),
                          ({'entry': 'README.md'}, '.zs 文件名'),
                          ({'entry': 'nope.zs'}, '不是能启动的入口脚本'),
                          ({'entry': 'plain.zs'}, '不是能启动的入口脚本'),
                          ({'entry': 'run_project.zs', 'roles': {'ENGINEER': 'NO_SUCH_CARD'}}, '没有这张角色卡'),
                          ({'entry': 'run_project.zs', 'mode': 'fast'}, 'mode 只能是'),
                          ({'entry': 'run_project.zs', 'max_attempts': 0}, 'max_attempts 无效'),
                          ({'entry': 'run_project.zs', 'models': {'QA_ENGINEER': 'haiku'}}, '模型名无效'),
                          ({'entry': 'run_project.zs', 'confirm_after': '架构设计'}, '要是列表')]:
        code, out = start(wd, **body)
        assert code == 400 and out['ok'] is False and message in out['error'], (body, out)
    assert not list((wd / 'runs').glob('*.json')), '拒掉的请求不留运行记录'
    code, out = call(handler(wd, write=False), 'POST', '/api/start', {'entry': 'run_project.zs'})
    assert code == 403
    code, out = call(handler(wd), 'POST', '/api/start', {'entry': 'run_project.zs'}, {'Origin': 'https://other.example'})
    assert code == 403 and 'Origin' in out['error']
    assert not list((wd / 'runs').glob('*.json'))


def test_start_step(tmp):
    wd = workdir(tmp)
    with patch.object(wc, '_continue', side_effect=AssertionError('逐步模式不该交给后台')):
        code, out = start(wd, entry='run_project.zs', mode='step', confirm_after=['架构设计'], max_attempts=3,
                          roles={'ENGINEER': 'ENGINEER_GPT'}, models={'QA_ENGINEER': 'cli:claude/haiku'})
    assert code == 200 and out['ok'] is True, out
    name = out['name']
    assert (wd / 'runs' / name).is_file() and out['status']['status'] == 'waiting'
    assert out['status']['pending']['name'] == '架构设计' and out['status']['steps'][0]['status'] == 'waiting'
    c = ctl(wd, name)
    assert c['mode'] == 'step' and c['confirm_after'] == ['架构设计'] and c['max_attempts'] == 3
    assert c['roles'] == {'ENGINEER': 'ENGINEER_GPT'} and c['models'] == {'QA_ENGINEER': 'cli:claude/haiku'}
    assert c['history'][0]['op'] == 'start' and c['history'][0]['actor'] == 'viewer'
    code, runs = call(handler(wd), 'GET', '/api/runs')
    assert [r['name'] for r in runs['runs']] == [name] and runs['runs'][0]['controlled'] is True


def test_start_auto_hands_off(tmp):
    wd = workdir(tmp)
    with patch.object(wc, '_continue') as cont:
        code, out = start(wd, entry='run_project.zs')
    assert code == 200 and out['ok'] is True, out
    assert ctl(wd, out['name'])['mode'] == 'auto', '不给 mode 默认自动'
    assert cont.call_count == 1 and cont.call_args[0][1] is False, '自动模式交给后台、不等'


def test_page():
    from test_trace_view import jsdom_env
    node, env = jsdom_env()
    if not node:
        print('  - 跳过页面：没有 node 或 jsdom（装到项目 node_modules，或设 NODE_PATH）')
        return
    with tempfile.TemporaryDirectory(prefix='trace-start-page-', dir=ROOT / 'data/tmp') as folder:
        tmp = Path(folder)
        wd = workdir(tmp)
        code, entries = call(handler(wd), 'GET', '/api/entries')
        assert code == 200
        data, req = tmp / 'entries.json', tmp / 'request.json'
        data.write_text(json.dumps(entries, ensure_ascii=False), encoding='utf-8')
        r = subprocess.run([node, str(ROOT / 'tests/e2e/trace_start_check.js'), str(ROOT / 'tools/trace_view.html'),
                            str(data), str(req)], env=env, capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stderr + r.stdout
        body = json.loads(req.read_text(encoding='utf-8'))
        assert body == {'entry': 'run_project.zs', 'mode': 'step', 'max_attempts': 3, 'confirm_after': ['架构设计'],
                        'models': {'QA_ENGINEER': 'cli:claude/haiku'}, 'roles': {'ENGINEER': 'ENGINEER_GPT'}}, body
        code, out = call(handler(wd), 'POST', '/api/start', body)
        assert code == 200 and out['ok'] is True, out
        c = ctl(wd, out['name'])
        assert c['mode'] == 'step' and c['confirm_after'] == ['架构设计'] and c['max_attempts'] == 3
        assert c['roles'] == body['roles'] and c['models'] == body['models']
        print(' ', r.stdout.strip())
        print('  ✓ 页面发出的启动请求交给真的查看服务，启动出来的运行和页面上填的一致')


CASES = [test_entries, test_start_rejects, test_start_step, test_start_auto_hands_off]


def run():
    (ROOT / 'data/tmp').mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='trace-start-', dir=ROOT / 'data/tmp') as folder:
        for case in CASES:
            tmp = Path(folder) / case.__name__
            tmp.mkdir()
            case(tmp)
            print('  ✓', case.__name__)
    test_page()
    print(f'查看器启动运行：通过 {len(CASES)} 项接口检查；页面检查完成')


if __name__ == '__main__':
    run()
