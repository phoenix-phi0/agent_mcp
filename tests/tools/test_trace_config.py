"""查看器的运行配置（POST /api/configure 和运行页的「运行配置」面板）：离线，不开端口、不调模型。

- 接口：改确认规则、尝试上限、按角色换模型 / 换卡，写进控制文件；不给的键不改；
  换到不存在的卡、模型没写全、类型不对、什么都没给 → 400，控制文件不变；只读和跨站 → 403；
- 页面：jsdom 里按人的操作改配置（tests/e2e/trace_config_check.js），
  把页面真发出的请求交给真的查看服务，核对控制文件。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import json
import subprocess
import tempfile

from tools import trace_server
from tools import workflow_ctl as wc
from test_trace_confirm import call, ordinary_review, post


def ctl(s):
    return json.loads((ROOT / s['run']).with_suffix('.ctl').read_text(encoding='utf-8'))


def test_configure_all(tmp):
    s, _ = ordinary_review(tmp)
    code, out = post(s, 'configure', confirm_before=['ENGINEER*'], confirm_after=['ARCHITECT', '验收'],
                     max_attempts=6, models={'ARCHITECT': 'cli:claude/haiku'},
                     roles={'ENGINEER': 'ENGINEER_GPT'})
    assert code == 200 and out['ok'] is True, out
    c = ctl(s)
    assert c['confirm_before'] == ['ENGINEER*'] and c['confirm_after'] == ['ARCHITECT', '验收']
    assert c['max_attempts'] == 6
    assert c['models'] == {'ARCHITECT': 'cli:claude/haiku'} and c['roles'] == {'ENGINEER': 'ENGINEER_GPT'}
    last = c['history'][-1]
    assert last['op'] == 'configure' and last['actor'] == 'viewer', last
    code, data = call(trace_server.make_handler((ROOT / s['run']).parent), 'GET',
                      '/api/run?name=' + (ROOT / s['run']).name)
    assert data['_control']['roles'] == {'ENGINEER': 'ENGINEER_GPT'} and data['_control']['max_attempts'] == 6


def test_configure_partial_and_clear(tmp):
    s, _ = ordinary_review(tmp)
    post(s, 'configure', roles={'ENGINEER': 'ENGINEER_GPT'}, models={'ENGINEER': 'cli:claude/haiku'})
    code, _ = post(s, 'configure', max_attempts=3)
    c = ctl(s)
    assert code == 200 and c['max_attempts'] == 3 and c['roles'] == {'ENGINEER': 'ENGINEER_GPT'}, '不给的键不改'
    assert c['confirm_after'] == ['ARCHITECT']
    code, _ = post(s, 'configure', roles={}, models={})
    c = ctl(s)
    assert code == 200 and c['roles'] == {} and c['models'] == {}, '给空对象清空覆盖'


def test_configure_rejects(tmp):
    s, _ = ordinary_review(tmp)
    before = (ROOT / s['run']).with_suffix('.ctl').read_bytes()
    for body, message in [({}, '没有要改的配置'),
                          ({'roles': {'ENGINEER': 'NO_SUCH_CARD'}}, '没有这张角色卡'),
                          ({'models': {'ENGINEER': 'haiku'}}, '模型名无效'),
                          ({'max_attempts': 0}, 'max_attempts 无效'),
                          ({'max_attempts': '3'}, 'max_attempts 无效'),
                          ({'confirm_after': 'ARCHITECT'}, '要是列表'),
                          ({'roles': ['ENGINEER']}, '要是对象'),
                          ({'confirm_before': ['有 空格']}, '确认规则无效')]:
        code, out = post(s, 'configure', **body)
        assert code == 400 and out['ok'] is False and message in out['error'], (body, out)
    assert (ROOT / s['run']).with_suffix('.ctl').read_bytes() == before, '拒掉的请求不动控制文件'


def test_configure_write_guard(tmp):
    s, _ = ordinary_review(tmp)
    p = ROOT / s['run']
    code, out = call(trace_server.make_handler(p.parent), 'POST', '/api/configure',
                     {'name': p.name, 'max_attempts': 2})
    assert code == 403 and '只读' in out['error']
    code, out = call(trace_server.make_handler(p.parent, write=True), 'POST', '/api/configure',
                     {'name': p.name, 'max_attempts': 2}, {'Origin': 'https://other.example'})
    assert code == 403 and 'Origin' in out['error']
    assert ctl(s).get('max_attempts') != 2


def test_page():
    from test_trace_view import jsdom_env
    node, env = jsdom_env()
    if not node:
        print('  - 跳过页面：没有 node 或 jsdom（装到项目 node_modules，或设 NODE_PATH）')
        return
    with tempfile.TemporaryDirectory(prefix='trace-config-page-', dir=ROOT / 'data/tmp') as folder:
        tmp = Path(folder)
        s, _ = ordinary_review(tmp)
        trace = trace_server.read_trace(ROOT / s['run'])
        data, req = tmp / 'trace.json', tmp / 'request.json'
        data.write_text(json.dumps(trace, ensure_ascii=False, default=str), encoding='utf-8')
        r = subprocess.run([node, str(ROOT / 'tests/e2e/trace_config_check.js'), str(ROOT / 'tools/trace_view.html'),
                            str(data), str(req)], env=env, capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stderr + r.stdout
        body = json.loads(req.read_text(encoding='utf-8'))
        assert body['name'] == (ROOT / s['run']).name and body['max_attempts'] == 5, body
        p = ROOT / s['run']
        code, out = call(trace_server.make_handler(p.parent, write=True), 'POST', '/api/configure', body)
        assert code == 200 and out['ok'] is True, out
        c = ctl(s)
        assert c['max_attempts'] == 5 and c['confirm_before'] == body['confirm_before']
        assert c['models'] == body['models'] and c['roles'] == body['roles']
        assert list(c['roles'].values()) == ['ENGINEER_GPT'] and list(c['models'].values()) == ['cli:claude/haiku']
        print(' ', r.stdout.strip())
        print('  ✓ 页面发出的请求交给真的查看服务，控制文件和页面上改的一致')


CASES = [test_configure_all, test_configure_partial_and_clear, test_configure_rejects, test_configure_write_guard]


def run():
    (ROOT / 'data/tmp').mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='trace-config-', dir=ROOT / 'data/tmp') as folder:
        for case in CASES:
            tmp = Path(folder) / case.__name__
            tmp.mkdir()
            case(tmp)
            print('  ✓', case.__name__)
    test_page()
    print(f'查看器运行配置：通过 {len(CASES)} 项接口检查；页面检查完成')


if __name__ == '__main__':
    run()
