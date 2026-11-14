"""查看器人工确认：离线运行，直接调用 HTTP handler，不开端口。

新增用例放入 CASES；每个用例使用独立目录，便于后续追加写接口和页面测试。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import json
import tempfile
from email.message import Message
from io import BytesIO
from urllib.parse import urlencode
from unittest.mock import patch

from dsl.client import ScriptClient
from tools import trace_server
from tools import workflow_ctl as wc
from test_workflow_ctl import demo_copy
from test_wf_cost import demo_copy as cost_demo, plan
from wf_fixtures import REPLIES, acceptance, contract, impl, review


def call(handler_cls, method, path, body=None, headers=None):
    """跳过 BaseHTTPRequestHandler 的 socket 初始化，保留真实响应序列化。"""
    raw = b'' if body is None else json.dumps(body).encode('utf-8')
    handler = handler_cls.__new__(handler_cls)
    handler.rfile = BytesIO(raw)
    handler.wfile = BytesIO()
    handler.headers = Message()
    defaults = {'Host': '127.0.0.1', 'Content-Type': 'application/json',
                'Content-Length': str(len(raw))}
    defaults.update(headers or {})
    for key, value in defaults.items():
        handler.headers[key] = value
    handler.path = path
    handler.command = method
    handler.request_version = 'HTTP/1.1'
    handler.requestline = f'{method} {path} HTTP/1.1'
    handler.close_connection = True
    getattr(handler, 'do_' + method)()
    head, payload = handler.wfile.getvalue().split(b'\r\n\r\n', 1)
    return int(head.split(b' ', 2)[1]), json.loads(payload)


def client(replies):
    c = ScriptClient(list(replies))
    c.offline = True
    return c


def ordinary_review(tmp, name='ordinary', **kw):
    """普通节点结束后确认；返回状态和可继续使用的离线客户端。"""
    c = client(REPLIES)
    s = wc.start(demo_copy(tmp, name), mode='auto', confirm_after=['ARCHITECT'],
                 client=c, **kw)
    assert s['pending']['phase'] == 'after' and 'plan' not in s['pending']
    assert len(c.calls) == 1
    return s, c


def assignment_review(tmp, name='assignment'):
    """带三项清单、角色清单和预算的任务分配结束后确认。"""
    folder = tmp / name
    folder.mkdir()
    assigned = plan('ENGINEER_LITE', 'ENGINEER', 'ENGINEER')
    c = client([contract('v1'), review('通过'), assigned,
                impl('甲'), impl('乙'), impl('丙'), acceptance('通过')])
    s = wc.start(cost_demo(folder), entry='run_cost.zs', mode='auto',
                 confirm_after=['任务分配'], client=c)
    pending = s['pending']
    assert pending['phase'] == 'after' and 'item' not in pending
    assert pending['plan']['record'] == 'assignment'
    assert pending['plan']['budget'] == 7 and 'ENGINEER' in pending['plan']['roster']
    return s, c


def item_before(tmp, name='item-before'):
    """第一项已完成，停在遍历第二项之前，后续项尚未执行。"""
    s, c = assignment_review(tmp, name)
    s = wc.approve(s['run'], item_controls=[None, {'confirm_before': True}, None], client=c)
    assert s['pending']['phase'] == 'before'
    assert s['pending']['item']['index'] == 2 and s['pending']['item']['total'] == 3
    assert len(c.calls) == 4
    return s, c


def endpoint(s, record='assignment'):
    p = ROOT / s['run']
    query = {'name': p.name}
    if record is not None:
        query['record'] = record
    return trace_server.make_handler(p.parent), '/api/plan?' + urlencode(query)


def test_read_control_values(tmp):
    s, _ = ordinary_review(tmp, max_attempts=7, confirm_before=['ENGINEER'])
    p = ROOT / s['run']
    cf = p.with_suffix('.ctl')
    cfg = json.loads(cf.read_text(encoding='utf-8'))
    cfg['notes'] = {key: [{'text': f'{key}-{i}'} for i in range(count)]
                    for key, count in [('9', 12), ('1', 1), ('3', 0)]}
    fields = dict(rev=1, kind='approve', attempt=1, actor='viewer', at='now', note='说明')
    cfg['revisions'] = {'9': [dict(fields, result={'secret': '全文'}, extra='不可暴露')], '1': []}
    cfg['item_controls'] = {'assignment': {'rows': [None, {'model': 'offline'}]}}
    cf.write_text(json.dumps(cfg, ensure_ascii=False), encoding='utf-8')
    before = cf.read_bytes()
    out = trace_server.read_control(p)
    assert out['confirm_before'] == ['ENGINEER'] and out['confirm_after'] == ['ARCHITECT']
    assert out['max_attempts'] == 7
    assert out['notes'] == {key: value[-10:] for key, value in cfg['notes'].items()}
    assert out['revisions'] == {'9': [fields], '1': []}
    assert out['item_controls'] == cfg['item_controls']
    assert cf.read_bytes() == before
    code, data = call(trace_server.make_handler(p.parent), 'GET', '/api/run?' + urlencode({'name': p.name}))
    assert code == 200 and data['_control'] == out


def test_read_control_empty(tmp):
    p = tmp / 'empty.json'
    assert trace_server.read_control(p) is None
    p.with_suffix('.ctl').write_text('{}', encoding='utf-8')
    out = trace_server.read_control(p)
    assert {key: out[key] for key in ('confirm_before', 'confirm_after', 'max_attempts',
                                      'notes', 'revisions', 'item_controls')} == {
        'confirm_before': [], 'confirm_after': [], 'max_attempts': None,
        'notes': {}, 'revisions': {}, 'item_controls': {}}


def test_plan_normal(tmp):
    s, _ = assignment_review(tmp)
    handler, url = endpoint(s)
    code, out = call(handler, 'GET', url)
    assert code == 200 and out == wc.plan(s['run'], record='assignment')
    assert out['budget'] == out['total'] == 7 and len(out['rows']) == 3


def test_plan_record_optional(tmp):
    s, _ = assignment_review(tmp)
    handler, url = endpoint(s, record=None)
    code, out = call(handler, 'GET', url)
    assert code == 200 and out == wc.plan(s['run'])


def test_plan_missing_run(tmp):
    code, out = call(trace_server.make_handler(tmp), 'GET', '/api/plan?name=missing.json')
    assert code == 400 and isinstance(out['error'], str) and out['error']


def test_plan_control_error(tmp):
    s, _ = ordinary_review(tmp)
    handler, url = endpoint(s)
    try:
        wc.plan(s['run'], record='assignment')
    except wc.ControlError as error:
        expected = str(error)
    else:
        raise AssertionError('普通运行不应有分配清单')
    assert call(handler, 'GET', url) == (400, {'error': expected})


def test_plan_item_before(tmp):
    s, _ = item_before(tmp)
    handler, url = endpoint(s)
    code, out = call(handler, 'GET', url)
    assert code == 200 and out == wc.plan(s['run'])
    assert [row['state'] for row in out['rows']] == ['done', 'waiting', 'todo']


def test_plan_existing_get_checks(tmp):
    handler = trace_server.make_handler(tmp, token='test-token', base='/trace')
    assert call(handler, 'GET', '/api/plan?name=missing.json')[0] == 404
    for name in ('', '../outside.json', '\ud800'):
        code, out = call(handler, 'GET', '/trace/test-token/api/plan?' + urlencode({'name': name}, errors='surrogatepass'))
        assert code == 400 and out == {'error': '文件名不对'}


def test_call_post(tmp):
    code, out = call(trace_server.make_handler(tmp), 'POST', '/api/submit', {'name': 'missing.json'})
    assert code == 403 and out['ok'] is False
    handler = trace_server.make_handler(tmp, write=True)
    code, out = call(handler, 'POST', '/api/submit', {}, {'Origin': 'https://other.example'})
    assert code == 403 and 'Origin' in out['error']


def post(s, op, **body):
    p = ROOT / s['run']
    return call(trace_server.make_handler(p.parent, write=True), 'POST',
                '/api/' + op, {'name': p.name, **body})


def offline_continue(c):
    """保留真实控制操作和回放；仅替换后台入口，不起进程或真模型。"""
    original = wc._continue

    def advance(path, wait, supplied_client):
        assert wait is False and supplied_client is None
        original(path, wait, c)
    return patch.object(wc, '_continue', side_effect=advance)


def test_approve_missing_attempt(tmp):
    s, _ = ordinary_review(tmp)
    code, out = post(s, 'approve')
    assert code == 400 and 'attempt' in out['error']


def test_approve_wrong_attempt(tmp):
    s, _ = ordinary_review(tmp)
    try:
        wc.approve(s['run'], attempt=99)
    except wc.ControlError as error:
        expected = str(error)
    else:
        raise AssertionError('旧 attempt 必须拒绝')
    assert post(s, 'approve', attempt=99) == (400, {'ok': False, 'error': expected})


def test_approve_advances(tmp):
    s, c = ordinary_review(tmp)
    wc.configure(s['run'], confirm_before=['ARCHITECT_GLM'])
    with offline_continue(c) as continued:
        code, out = post(s, 'approve', attempt=s['pending']['attempt'], step=s['pending']['step'])
    assert code == 200 and out['ok'] is True and continued.call_count == 1
    assert out['status'] == wc.status(s['run'])
    assert out['status']['pending']['phase'] == 'before'
    assert out['status']['pending']['step'] > s['pending']['step']


def test_approve_invalid_result(tmp):
    from tools.wf_submit import validate
    s, _ = ordinary_review(tmp)
    code, out = post(s, 'approve', attempt=s['pending']['attempt'], result={})
    assert code == 400 and out['error'].startswith('结果不符合格式')
    pending = json.loads((ROOT / s['run']).read_text(encoding='utf-8'))['pending']
    assert out['errors'] == validate(pending['schema'], {}) and out['errors']


def test_approve_revised_result(tmp):
    s, c = ordinary_review(tmp)
    wc.configure(s['run'], confirm_before=['ARCHITECT_GLM'])
    changed = contract('人工修订')
    with offline_continue(c):
        code, out = post(s, 'approve', attempt=s['pending']['attempt'],
                         result=changed, note='确认修订')
    assert code == 200 and out['ok'] is True
    data = json.loads((ROOT / s['run']).read_text(encoding='utf-8'))
    event = next(e for e in data['events'] if e.get('type') == 'task')
    assert event['result'] == changed and event['revisions'][-1]['note'] == '确认修订'


def test_approve_plan_controls_and_preview(tmp):
    s, c = assignment_review(tmp)
    controls = [None, {'confirm_before': True}, None]
    changed = plan('ENGINEER_LITE', 'ENGINEER', 'ENGINEER_LITE')
    with offline_continue(c):
        code, out = post(s, 'approve', attempt=s['pending']['attempt'], result=changed,
                         item_controls=controls)
    assert code == 200 and out['status'] == wc.status(s['run']) | {
        'cost_preview': out['status']['cost_preview']}
    assert out['status']['cost_preview']['total'] == 5
    assert out['status']['pending']['item']['index'] == 2


def test_reject_missing_attempt(tmp):
    s, _ = ordinary_review(tmp)
    code, out = post(s, 'reject', note='重做')
    assert code == 400 and 'attempt' in out['error']


def test_reject_wrong_attempt(tmp):
    s, _ = ordinary_review(tmp)
    code, out = post(s, 'reject', attempt=99, note='重做')
    assert code == 400 and out['error'] == '结果已经换了（现在是第 1 次），刷新后再确认'


def test_reject_empty_note(tmp):
    s, _ = ordinary_review(tmp)
    for body in ({}, {'note': ''}, {'note': '   '}):
        assert post(s, 'reject', attempt=s['pending']['attempt'], **body) == (
            400, {'ok': False, 'error': '打回要写意见'})


def test_reject_role(tmp):
    s, _ = ordinary_review(tmp)
    c = client([REPLIES[0]])
    wc.configure(s['run'], confirm_after=['*'])
    with offline_continue(c) as continued:
        code, out = post(s, 'reject', attempt=s['pending']['attempt'], step=s['pending']['step'],
                         note='换卡重做', role='ARCHITECT_GLM', model='cli:goose/glm-5.3')
    assert code == 200 and out['ok'] is True and continued.call_count == 1
    assert out['status']['pending']['attempt'] == 2
    data = json.loads((ROOT / s['run']).read_text(encoding='utf-8'))
    events = [e for e in data['events'] if e.get('type') == 'task']
    assert [e['status'] for e in events] == ['rejected', 'review']
    assert events[-1]['role'] == 'ARCHITECT_GLM'
    assert events[-1]['model_override'] == 'cli:goose/glm-5.3'


def test_edit_plan_done_item(tmp):
    s, _ = item_before(tmp)
    tasks = plan('ENGINEER_LITE', 'ENGINEER', 'ENGINEER')['tasks']
    tasks[0]['content'] = '已跑项的修改'
    assert post(s, 'edit_plan', tasks=tasks) == (
        400, {'ok': False, 'error': '第 1 项已经跑过，不能改'})


def test_edit_plan_over_budget(tmp):
    s, _ = item_before(tmp)
    tasks = plan('ENGINEER_LITE', 'ENGINEER', 'ENGINEER_SENIOR')['tasks']
    code, out = post(s, 'edit_plan', tasks=tasks)
    assert code == 400 and '改后合计 12，预算 7' in out['error']


def test_edit_plan_todo_item(tmp):
    s, _ = item_before(tmp)
    tasks = plan('ENGINEER_LITE', 'ENGINEER', 'ENGINEER_LITE')['tasks']
    tasks[2]['content'] = '未跑项的修改'
    controls = [None, None, {'confirm_after': True}]
    code, out = post(s, 'edit_plan', tasks=tasks, item_controls=controls, record='assignment')
    assert code == 200 and out['ok'] is True
    assert out['status']['cost_preview']['total'] == 5
    rows = wc.plan(s['run'], record='assignment')['rows']
    assert rows[2]['item'] == tasks[2] and rows[2]['confirm_after'] is True
    assert [r['state'] for r in rows] == ['done', 'waiting', 'todo']


def test_pause(tmp):
    s, _ = ordinary_review(tmp)
    code, out = post(s, 'pause')
    assert code == 200 and out == {'ok': True, 'status': wc.status(s['run'])}
    assert out['status']['mode'] == 'step'


def test_four_writes_readonly(tmp):
    s, _ = ordinary_review(tmp)
    p = ROOT / s['run']
    for op in ('approve', 'reject', 'edit_plan', 'pause'):
        code, out = call(trace_server.make_handler(p.parent), 'POST', '/api/' + op, {'name': p.name})
        assert code == 403 and out['ok'] is False and '只读' in out['error']


def test_four_writes_origin(tmp):
    s, _ = ordinary_review(tmp)
    p = ROOT / s['run']
    for op in ('approve', 'reject', 'edit_plan', 'pause'):
        code, out = call(trace_server.make_handler(p.parent, write=True), 'POST', '/api/' + op,
                         {'name': p.name}, {'Origin': 'https://other.example'})
        assert code == 403 and 'Origin' in out['error']


def test_write_string_encoding(tmp):
    s, _ = ordinary_review(tmp)
    for op, body in [('approve', {'note': '\ud800'}), ('reject', {'note': '\ud800'})]:
        code, out = post(s, op, attempt=s['pending']['attempt'], **body)
        assert code == 400 and out['error'] == '说明必须是有效的 UTF-8 字符串'
    for body, message in [({'role': '\ud800'}, '角色卡名无效'),
                          ({'model': 'cli:x/\ud800'}, '模型名无效')]:
        code, out = post(s, 'reject', attempt=s['pending']['attempt'], note='重做', **body)
        assert code == 400 and message in out['error']
    s, _ = item_before(tmp, 'encoding-items')
    tasks = plan('ENGINEER_LITE', 'ENGINEER', 'ENGINEER')['tasks']
    tasks[2]['content'] = '\ud800'
    code, out = post(s, 'edit_plan', tasks=tasks)
    assert code == 400 and out['error'] == '结果必须是有效的 UTF-8 JSON 对象'
    assert post(s, 'pause', name='\ud800')[0] == 400


def test_page_confirmation():
    """jsdom 页面确认测试：沿用查看器的 NODE_PATH 检测；全程假 fetch。"""
    import subprocess
    from test_trace_view import jsdom_env
    node, env = jsdom_env()
    if not node:
        print('  - 跳过页面确认：没有 node 或 jsdom（装到项目 node_modules，或设 NODE_PATH）')
        return
    with tempfile.TemporaryDirectory(prefix='trace-page-', dir=ROOT / 'data/tmp') as folder:
        tmp = Path(folder)
        fixtures, runs = [], []
        for index, (global_after, before) in enumerate([
                (False, 'effective'), (True, 'original'), (False, 'step'), (True, 'node')]):
            dest = tmp / str(index)
            dest.mkdir()
            demo = cost_demo(dest)
            (demo / 'cost_workflow.wf').write_text(
                '角色清单 roster ENGINEER ENGINEER_GPT\n'
                '分配\n    任务 分配\n    角色 ARCHITECT\n'
                '    格式 cost_assignment\n    记录 assignment\n'
                '遍历 x 于 assignment.tasks\n    实施\n'
                '        角色 x.who\n        任务 x.task\n'
                '        格式 implementation\n        记录 result\n', encoding='utf-8')
            fmt = demo / 'formats/cost_assignment.json'
            fmt.write_text(fmt.read_text(encoding='utf-8').replace('"agent"', '"who"')
                           .replace('"content"', '"task"'), encoding='utf-8')
            assigned = {'tasks': [{'who': 'ENGINEER', 'task': '原文' + str(i), 'reason': '保留'}
                                  for i in range(2)]}
            c = client([assigned])
            s = wc.start(demo, entry='run_cost.zs', mode='auto', confirm_after=['分配'], client=c)
            wc.configure(s['run'], roles={'ENGINEER': 'ENGINEER_GPT'},
                         confirm_before=[{'effective': 'ENGINEER_GPT', 'original': 'ENGINEER',
                                          'step': '不匹配', 'node': '实*'}[before]],
                         confirm_after=['实施'] if global_after else [])
            first_control = {'confirm_after': not global_after, 'model': 'cli:claude/haiku'}
            if before == 'step':
                first_control['confirm_before'] = True
            s = wc.approve(s['run'], item_controls=[first_control, {'confirm_before': False}], client=c)
            assert s['pending']['phase'] == 'before'
            if before == 'step':
                # 切到逐步模式后，默认仍应在开始前停，而结束后不受 mode 影响。
                cf = (ROOT / s['run']).with_suffix('.ctl')
                cfg = json.loads(cf.read_text(encoding='utf-8'))
                cfg['mode'] = 'step'
                cf.write_text(json.dumps(cfg), encoding='utf-8')
            handler, path = endpoint(s)
            code, actual_plan = call(handler, 'GET', path)
            assert code == 200 and actual_plan['rows'][0]['item'] == assigned['tasks'][0]
            fixtures.append({'trace': trace_server.read_trace(ROOT / s['run']),
                             'plan': actual_plan, 'globalAfter': global_after})
            runs.append(s['run'])
        data, requests = tmp / 'fixtures.json', tmp / 'requests.json'
        data.write_text(json.dumps(fixtures, ensure_ascii=False), encoding='utf-8')
        assignment, assignment_client = assignment_review(tmp, 'revised-length')
        assignment_data, approval_request = tmp / 'assignment.json', tmp / 'approval.json'
        assignment_data.write_text(json.dumps(trace_server.read_trace(ROOT / assignment['run']),
                                               ensure_ascii=False), encoding='utf-8')
        out = subprocess.run([node, str(ROOT / 'tests/e2e/trace_confirm_check.js'),
                              str(ROOT / 'tools/trace_view.html'), str(data), str(requests),
                              str(assignment_data), str(approval_request)],
                             env=env, capture_output=True, text=True, timeout=60)
        assert out.returncode == 0, out.stderr
        approval = json.loads(approval_request.read_text(encoding='utf-8'))
        assert 'item_controls' not in approval
        assert len(approval['result']['tasks']) == 2
        assert approval['result']['tasks'] == assignment['pending']['result']['tasks'][1:]
        with offline_continue(assignment_client):
            code, approved = call(trace_server.make_handler((ROOT / assignment['run']).parent, write=True),
                                  'POST', '/api/approve', approval)
        assert code == 200, approved
        assert approved['ok'] is True
        assert [row['item'] for row in wc.plan(assignment['run'])['rows']] == approval['result']['tasks']
        bodies = json.loads(requests.read_text(encoding='utf-8'))
        assert len(bodies) == len(runs) * 2
        for index, run in enumerate(runs):
            # 将页面的真实 POST 请求交给真实控制逻辑，核对恢复默认后的服务端值。
            reset, edit = bodies[index * 2:index * 2 + 2]
            wc.edit_plan(run, record=reset['record'], item_controls=reset['item_controls'])
            actual = wc.plan(run)
            assert actual['rows'][0]['confirm_after'] == fixtures[index]['globalAfter']
            assert actual['rows'][1]['control'] == fixtures[index]['plan']['rows'][1]['control']
            wc.edit_plan(run, record=edit['record'], tasks=edit['tasks'])
            assert [row['item'] for row in wc.plan(run)['rows']] == edit['tasks']
        print(out.stdout.strip())


CASES = [test_read_control_values, test_read_control_empty, test_plan_normal,
         test_plan_record_optional, test_plan_missing_run, test_plan_control_error,
         test_plan_item_before, test_plan_existing_get_checks, test_call_post,
         test_approve_missing_attempt, test_approve_wrong_attempt, test_approve_advances,
         test_approve_invalid_result, test_approve_revised_result, test_approve_plan_controls_and_preview,
         test_reject_missing_attempt, test_reject_wrong_attempt, test_reject_empty_note, test_reject_role,
         test_edit_plan_done_item, test_edit_plan_over_budget, test_edit_plan_todo_item, test_pause,
         test_four_writes_readonly, test_four_writes_origin, test_write_string_encoding]


def run():
    (ROOT / 'data/tmp').mkdir(parents=True, exist_ok=True)
    passed = 0
    with tempfile.TemporaryDirectory(prefix='trace-confirm-', dir=ROOT / 'data/tmp') as folder:
        for case in CASES:
            tmp = Path(folder) / case.__name__
            tmp.mkdir()
            case(tmp)
            passed += 1
            print('  ✓', case.__name__)
    test_page_confirmation()
    print(f'查看器人工确认：通过 {passed} 项；页面确认检查完成')


if __name__ == '__main__':
    run()
