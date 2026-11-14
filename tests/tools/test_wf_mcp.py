"""DESIGN 6.1：流程 MCP 骨架、鉴权和范围；独立离线脚本，不开端口。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import tempfile
import json
import asyncio
from io import BytesIO
from urllib.parse import urlencode
from unittest.mock import patch

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from dsl.client import ScriptClient
from tools import workflow_ctl as wc
from tools import wf_mcp_server as server
from test_workflow_ctl import demo_copy

KEY = '测试密钥-0123456789abcdef'
TOKEN = 'viewer-token-0123456789'


# 保持独立脚本入口，同时允许用 pytest 执行全部本项用例。
if 'pytest' in sys.modules:
    @sys.modules['pytest'].fixture
    def tmp():
        (ROOT / 'data/tmp').mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='wf-mcp-pytest-', dir=ROOT / 'data/tmp') as folder:
            yield Path(folder)


def rejects(kind, fn):
    try:
        fn()
    except kind as error:
        return str(error)
    raise AssertionError(f'应当抛出 {kind.__name__}')


def service(tmp, **kw):
    return server.build_server('127.0.0.1', 8765, '/trace', False, KEY, TOKEN,
                               root=tmp, workdirs=['workflow_demo', 'other'], **kw)


def test_6_1_startup_missing_key(tmp):
    message = rejects(server.StartupError, lambda: server.load_key({}, tmp))
    assert 'secrets.token_urlsafe(24)' in message and 'chmod 600' in message
    assert 'wf_mcp.key' in message


def test_6_1_startup_short_key(tmp):
    for key in ('short-secret', '', '\ud800' * 16):
        message = rejects(server.StartupError, lambda: server.load_key({'WF_MCP_KEY': key}, tmp))
        if key:
            assert key not in message


def test_6_1_startup_key_file_and_environment(tmp):
    path = tmp / '.config/agent_mcp/wf_mcp.key'
    path.parent.mkdir(parents=True)
    path.write_text('  ' + KEY + '\n', encoding='utf-8')
    assert server.load_key({}, tmp) == KEY
    assert server.load_key({'WF_MCP_KEY': KEY + 'x'}, tmp) == KEY + 'x'
    path.write_text('short-file-key', encoding='utf-8')
    assert 'short-file-key' not in rejects(server.StartupError, lambda: server.load_key({}, tmp))


def test_6_1_startup_trace_token(tmp):
    for env in ({}, {'TRACE_TOKEN': 'short'}, {'TRACE_TOKEN': TOKEN + '!'},
                {'TRACE_TOKEN': '中文' * 16}, {'TRACE_TOKEN': '\ud800' * 16}):
        message = rejects(server.StartupError, lambda: server.load_trace_token(env))
        if env:
            assert env['TRACE_TOKEN'] not in message
    assert server.load_trace_token({'TRACE_TOKEN': TOKEN}) == TOKEN
    assert server.load_trace_token({'TRACE_TOKEN': 'a' * 16}) == 'a' * 16
    assert server.load_key({'WF_MCP_KEY': 'a' * 16}, tmp) == 'a' * 16


def test_6_1_auth_wrong_missing(tmp):
    svc = service(tmp)
    assert isinstance(svc.mcp, FastMCP) and svc.mcp.name == 'workflow'
    assert set(svc.tools) == {
        'runs', 'start', 'status', 'submit', 'execute', 'approve', 'reject', 'plan',
        'edit_plan', 'pause', 'resume', 'abort', 'configure', 'rewind', 'agents', 'viewer'}
    for invoke in (lambda: svc.tools['runs'](), lambda: svc.tools['runs'](None),
                   lambda: svc.tools['runs']('wrong-secret'),
                   lambda: svc.tools['runs']('\ud800'), lambda: svc.tools['runs'](42)):
        assert rejects(ToolError, invoke) == '鉴权失败'


def test_6_1_runs_name(tmp):
    demo = demo_copy(tmp, 'workflow_demo')
    c = ScriptClient([])
    c.offline = True
    state = wc.start(demo, client=c)
    svc = service(tmp)
    expected = [dict(row, name=Path(row['run']).name) for row in wc.list_runs(demo)]
    assert svc.tools['runs'](KEY) == expected
    assert expected[0]['name'] == Path(state['run']).name
    assert svc.tools['runs'](KEY, 'workflow_demo') == expected
    assert svc.tools['runs'](KEY, 'other') == []
    assert c.calls == []


def test_6_1_resolve_run(tmp):
    runs = tmp / 'workflow_demo/runs'
    runs.mkdir(parents=True)
    good = runs / 'ok.json'
    good.write_text('{}')
    other = tmp / 'other/runs'
    other.mkdir(parents=True)
    second = other / 'second.json'
    second.write_text('{}')
    cfg = service(tmp).cfg
    assert server.resolve_run('ok.json', cfg) == good.resolve()
    assert server.resolve_run('workflow_demo/runs/ok.json', cfg) == good.resolve()
    assert server.resolve_run('other/runs/second.json', cfg) == second.resolve()
    outside = tmp / 'outside.json'
    outside.write_text('{}')
    (runs / 'escape.json').symlink_to(outside)
    (runs / 'bad.txt').write_text('{}')
    for value in ('outside.json', 'workflow_demo/../outside.json', '../outside.json',
                  str(outside), '/etc/passwd', 'escape.json', 'missing.json',
                  'bad.txt', '', '\ud800', 'a\\..\\outside.json', None):
        rejects(wc.ControlError, lambda: server.resolve_run(value, cfg))
    (tmp / 'other/runs').rename(tmp / 'other/original')
    (tmp / 'other/runs').symlink_to(tmp, target_is_directory=True)
    rejects(wc.ControlError, lambda: server.resolve_run('other/runs/outside.json', cfg))


def test_6_1_workdir_allowlist(tmp):
    cfg = service(tmp).cfg
    assert server.parse_workdirs({}) == ['workflow_demo']
    assert server.parse_workdirs({'WF_WORKDIRS': ' workflow_demo, other '}) == ['workflow_demo', 'other']
    assert server.resolve_workdir(None, cfg) == (tmp / 'workflow_demo').resolve()
    assert server.resolve_workdir('other', cfg) == (tmp / 'other').resolve()
    for value in ('elsewhere', '../workflow_demo', '', '\ud800', 123):
        rejects(wc.ControlError, lambda: server.resolve_workdir(value, cfg))
    for value in ('', '../outside', '/tmp', 'workflow_demo,,other', '\ud800'):
        rejects(wc.ControlError, lambda: server.parse_workdirs({'WF_WORKDIRS': value}))


def test_6_1_entry_rejected(tmp):
    (tmp / 'ok.zs').write_text('')
    assert server.check_entry(tmp, 'ok.zs') == 'ok.zs'
    for entry in ('sub/ok.zs', 'sub\\ok.zs', '../ok.zs', 'missing.zs',
                  'ok.json', '', '\ud800', None):
        rejects(wc.ControlError, lambda: server.check_entry(tmp, entry))
    # 目标即使存在，也不能通过 entry 符号链接访问目录外。
    with tempfile.TemporaryDirectory(dir=tmp) as folder:
        target = Path(folder) / 'nested.zs'
        target.write_text('')
        (tmp / 'linked.zs').symlink_to(target)
        rejects(wc.ControlError, lambda: server.check_entry(tmp, 'linked.zs'))


def test_6_1_tool_errors(tmp):
    svc = service(tmp)
    original = wc.ControlError('业务错误')
    with patch.object(wc, 'list_runs', side_effect=original):
        try:
            svc.tools['runs'](KEY)
        except wc.ControlError as error:
            assert error is original
        else:
            raise AssertionError('应保留 ControlError')
    with patch.object(wc, 'list_runs', side_effect=ValueError('unexpected')):
        assert rejects(ToolError, lambda: svc.tools['runs'](KEY)) == '内部错误：ValueError: unexpected'
    with patch.object(wc, 'list_runs', side_effect=ValueError(KEY + TOKEN)):
        message = rejects(ToolError, lambda: svc.tools['runs'](KEY))
        assert KEY not in message and TOKEN not in message
    rejects(wc.ControlError, lambda: svc.tools['runs'](KEY, '\ud800'))


def test_6_1_main_startup(tmp):
    with patch.object(server, 'load_key', side_effect=server.StartupError('缺少启动密钥')):
        assert rejects(SystemExit, lambda: server.main([])) == '1'
    with patch.object(server, 'load_key', return_value=KEY), \
            patch.object(server, 'load_trace_token', side_effect=server.StartupError('缺少查看口令')):
        assert rejects(SystemExit, lambda: server.main([])) == '1'
    with patch.object(server, 'load_key', return_value=KEY), \
            patch.object(server, 'load_trace_token', return_value=TOKEN), \
            patch.object(FastMCP, 'run'), \
            patch.dict(server.os.environ, {'WF_WORKDIRS': 'workflow_demo'}):
        cfg = server.main([]).cfg
        assert (cfg.host, cfg.port, cfg.base, cfg.write) == ('127.0.0.1', 8765, '/trace', False)
        cfg = server.main(['--host', 'localhost', '--port', '9000', '--base', '/wf', '--write']).cfg
        assert (cfg.host, cfg.port, cfg.base, cfg.write) == ('localhost', 9000, '/wf', True)


def start_offline(tmp):
    demo_copy(tmp, 'workflow_demo')
    c = ScriptClient([])
    c.offline = True
    svc = service(tmp)
    original = wc.start
    with patch.object(wc, 'start', side_effect=lambda *a, **kw: original(*a, client=c, **kw)) as call:
        state = svc.tools['start'](KEY, 'workflow_demo', 'run.zs')
    assert call.call_args.kwargs['wait'] is False
    assert not c.calls
    return svc, state


def test_6_1_start_status(tmp):
    svc, state = start_offline(tmp)
    assert state['status'] == 'waiting' and state['pending']['step'] == 1
    assert svc.tools['status'](KEY, Path(state['run']).name) == state
    json.dumps(state)
    options = dict(mode='auto', stop_roles=['ARCHITECT'], confirm_before=['ARCHITECT'],
                   confirm_after=['ENGINEER'], max_attempts=7,
                   models={'ENGINEER': 'cli:claude/haiku'}, roles={'ENGINEER': 'ENGINEER_LITE'})
    with patch.object(wc, 'start', return_value=state) as call:
        assert svc.tools['start'](KEY, 'workflow_demo', 'run.zs', **options) == state
        call.assert_called_once_with((tmp / 'workflow_demo').resolve(), entry='run.zs', wait=False, **options)


def test_6_1_start_entry_scope(tmp):
    demo_copy(tmp, 'workflow_demo')
    svc = service(tmp)
    for entry in ('sub/run.zs', '../run.zs', 'missing.zs', '', '\ud800'):
        rejects(wc.ControlError, lambda: svc.tools['start'](KEY, 'workflow_demo', entry))
    for wd in ('outside', '../workflow_demo', '\ud800'):
        rejects(wc.ControlError, lambda: svc.tools['start'](KEY, wd, 'run.zs'))
    for options in (dict(mode='\ud800'), dict(models={'ENGINEER': '\ud800'}),
                    dict(roles={'ENGINEER': '\ud800'}), dict(confirm_after=['\ud800'])):
        rejects(wc.ControlError, lambda: svc.tools['start'](KEY, 'workflow_demo', 'run.zs', **options))


def test_6_1_status_detail_truncation(tmp):
    svc, state = start_offline(tmp)
    path = ROOT / state['run']
    trace = json.loads(path.read_text(encoding='utf-8'))
    long = '长' * 20001
    trace['pending'].update(result={'text': long}, context=[long], task=long,
                            prompt=long, system='界' * 20000)
    path.write_text(json.dumps(trace, ensure_ascii=False), encoding='utf-8')
    out = svc.tools['status'](KEY, path.name, detail=True)
    expected = long[:20000] + '（已截断，共 20001 字）'
    for actual in (out['pending']['result']['text'], out['pending']['context'][0],
                   out['pending']['task'], out['pending']['prompt']):
        assert actual == expected
    assert out['pending']['system'] == '界' * 20000
    assert json.loads(path.read_text(encoding='utf-8'))['pending']['task'] == long
    json.dumps(out)


def test_6_1_plan_assignment(tmp):
    from test_wf_cost import demo_copy as cost_demo, plan
    from wf_fixtures import contract, review
    svc = service(tmp)
    c = ScriptClient([contract('v1'), review('通过'), plan('ENGINEER')])
    c.offline = True
    state = wc.start(cost_demo(tmp), entry='run_cost.zs', mode='auto',
                     confirm_after=['任务分配'], client=c)
    name = Path(state['run']).name
    assert svc.tools['plan'](KEY, name) == wc.plan(state['run'])
    assert svc.tools['plan'](KEY, name, 'assignment') == wc.plan(state['run'], 'assignment')
    assert svc.tools['plan'](KEY, name)['rows']
    for record in ('missing', '\ud800'):
        rejects(wc.ControlError, lambda: svc.tools['plan'](KEY, name, record))


def test_6_1_agents_cards(tmp):
    demo_copy(tmp, 'workflow_demo')
    svc = service(tmp)
    rows = svc.tools['agents'](KEY)
    assert rows and rows == svc.tools['agents'](KEY, 'workflow_demo')
    assert all(set(row) == {'name', 'model', 'cost', 'description'} for row in rows)
    assert any(row['name'] == 'ENGINEER' and row['model'] for row in rows)
    assert svc.tools['agents'](KEY, 'other') == []
    rejects(wc.ControlError, lambda: svc.tools['agents'](KEY, '\ud800'))
    json.dumps(rows)


def test_6_1_viewer_url(tmp):
    svc, state = start_offline(tmp)
    name = Path(state['run']).name
    with patch.dict(server.os.environ, {}, clear=True):
        assert svc.tools['viewer'](KEY) == {'url': f'http://127.0.0.1:8765/trace/{TOKEN}/'}
        assert svc.tools['viewer'](KEY, name)['url'] == f'http://127.0.0.1:8765/trace/{TOKEN}/#run={name}'
    with patch.dict(server.os.environ, {'WF_PUBLIC_URL': 'https://example.test/workflow/'}):
        assert svc.tools['viewer'](KEY, name) == {'url': f'https://example.test/workflow/{TOKEN}/#run={name}'}


def test_6_1_read_tools_errors(tmp):
    svc, state = start_offline(tmp)
    for tool, args in [('start', ('workflow_demo', 'run.zs')), ('status', (Path(state['run']).name,)),
                       ('plan', (Path(state['run']).name,)), ('agents', ()), ('viewer', ())]:
        assert rejects(ToolError, lambda: svc.tools[tool]('wrong', *args)) == '鉴权失败'
        assert svc.tools[tool].__doc__
    for tool in ('status', 'plan', 'viewer'):
        for run in ('../escape.json', '/etc/passwd', 'missing.json', '\ud800', ''):
            rejects(wc.ControlError, lambda: svc.tools[tool](KEY, run))
    for tool, module, function, args in [
            ('start', wc, 'start', ('workflow_demo', 'run.zs')),
            ('status', wc, 'status', (Path(state['run']).name,)),
            ('plan', wc, 'plan', (Path(state['run']).name,)),
            ('agents', server.trace_server, 'read_agents', ())]:
        original = wc.ControlError('业务错误')
        with patch.object(module, function, side_effect=original):
            try:
                svc.tools[tool](KEY, *args)
            except wc.ControlError as error:
                assert error is original
            else:
                raise AssertionError('应原样抛出 ControlError')
        with patch.object(module, function, side_effect=ValueError('unexpected')):
            assert rejects(ToolError, lambda: svc.tools[tool](KEY, *args)) == '内部错误：ValueError: unexpected'



def invoke_offline(svc, tool, client, *args, **kwargs):
    original = getattr(wc, tool)
    with patch.object(wc, tool, side_effect=lambda *a, **kw: original(*a, client=client, **kw)) as call:
        out = svc.tools[tool](KEY, *args, **kwargs)
    if tool in ('submit', 'execute', 'approve', 'reject', 'resume'):
        assert call.call_args.kwargs['wait'] is False
    return out


def test_6_1_submit_approve(tmp):
    from wf_fixtures import REPLIES
    svc, state = start_offline(tmp)
    name = Path(state['run']).name
    svc.tools['configure'](KEY, name, confirm_after=['ARCHITECT_GLM'])
    c = ScriptClient([REPLIES[1]])
    c.offline = True
    state = invoke_offline(svc, 'submit', c, name, REPLIES[0], step=1)
    assert state['pending']['step'] == 2 and not c.calls
    state = invoke_offline(svc, 'execute', c, name, step=2)
    assert state['pending']['phase'] == 'after' and state['pending']['step'] == 2
    for options in ({}, {'attempt': None}):
        rejects((ToolError, wc.ControlError), lambda: svc.tools['approve'](KEY, name, **options))
    rejects(wc.ControlError, lambda: svc.tools['approve'](KEY, name, 999))
    state = invoke_offline(svc, 'approve', c, name, state['pending']['attempt'], note='通过', step=2)
    assert state['pending']['step'] == 3 and state['pending']['phase'] == 'before'
    assert len(c.calls) == 1


def test_6_1_execute_reject(tmp):
    from wf_fixtures import REPLIES, contract
    svc, state = start_offline(tmp)
    name = Path(state['run']).name
    svc.tools['configure'](KEY, name, confirm_after=['ARCHITECT'])
    c = ScriptClient([REPLIES[0], contract('retry')])
    c.offline = True
    state = invoke_offline(svc, 'execute', c, name, note='检查边界', step=1)
    assert state['pending']['phase'] == 'after' and len(c.calls) == 1
    attempt = state['pending']['attempt']
    for note in ('', '  \t\n', None):
        rejects(wc.ControlError, lambda: svc.tools['reject'](KEY, name, attempt, note))
    rejects((ToolError, wc.ControlError), lambda: svc.tools['reject'](KEY, name, note='重做'))
    rejects(wc.ControlError, lambda: svc.tools['reject'](KEY, name, None, '重做'))
    state = invoke_offline(svc, 'reject', c, name, attempt, '补充错误码', step=1)
    assert state['status'] == 'waiting'
    assert state['pending']['phase'] == 'after' and state['pending']['step'] == 1
    assert state['pending']['attempt'] == attempt + 1 == 2
    assert [(row['step'], row['attempt'], row['status']) for row in state['steps']] == [
        (1, 1, 'rejected'), (1, 2, 'review')]
    assert len(c.calls) == 2
    trace = json.loads((ROOT / state['run']).read_text(encoding='utf-8'))
    history = [event for event in trace['events'] if event.get('type') == 'task']
    assert history[0]['reject']['text'] == '补充错误码'
    assert history[0]['confirm'][-1]['action'] == 'reject'
    assert history[1]['result'] == contract('retry')
    notes = server.trace_server.read_control(ROOT / state['run'])['notes']['1']
    assert notes[-1]['kind'] == 'reject' and notes[-1]['text'] == '补充错误码'
    assert notes[-1]['attempt'] == attempt


def test_6_1_edit_plan_cost_preview(tmp):
    from test_wf_cost import demo_copy as cost_demo, plan
    from wf_fixtures import contract, review
    c = ScriptClient([contract('v1'), review('通过'), plan('ENGINEER')])
    c.offline = True
    state = wc.start(cost_demo(tmp), entry='run_cost.zs', mode='auto',
                     confirm_after=['任务分配'], client=c)
    svc = service(tmp)
    name = Path(state['run']).name
    state = invoke_offline(svc, 'approve', c, name, state['pending']['attempt'],
                           item_controls=[{'confirm_before': True}])
    assert state['cost_preview']['total'] == 3
    state = invoke_offline(svc, 'edit_plan', c, name, tasks=plan('ENGINEER_LITE')['tasks'],
                           item_controls=[{'confirm_before': True}], record='assignment')
    assert state['cost_preview']['total'] == 1
    assert svc.tools['plan'](KEY, name)['rows'][0]['item']['agent'] == 'ENGINEER_LITE'
    assert state['pending']['phase'] == 'before'


def test_6_1_pause_resume_abort_configure_rewind(tmp):
    from wf_fixtures import REPLIES
    svc, state = start_offline(tmp)
    name = Path(state['run']).name
    state = svc.tools['configure'](KEY, name, stop_roles=['*'], confirm_before=['*'],
                                   confirm_after=['ARCHITECT'], max_attempts=7,
                                   models={'ENGINEER': 'cli:claude/haiku'}, roles={'ENGINEER': 'ENGINEER_LITE'})
    assert state['confirm_before'] == ['*'] and state['confirm_after'] == ['ARCHITECT']
    assert state['max_attempts'] == 7
    assert state['models'] == {'ENGINEER': 'cli:claude/haiku'}
    assert state['roles'] == {'ENGINEER': 'ENGINEER_LITE'}
    c = ScriptClient([])
    c.offline = True
    assert invoke_offline(svc, 'resume', c, name)['mode'] == 'auto'
    assert svc.tools['pause'](KEY, name)['mode'] == 'step'
    state = invoke_offline(svc, 'submit', c, name, REPLIES[0])
    assert state['pending']['step'] == 2
    state = invoke_offline(svc, 'rewind', c, name, 1)
    assert state['pending']['step'] == 1 and state['pending']['phase'] == 'before'
    assert svc.tools['abort'](KEY, name)['status'] == 'aborted'
    assert not c.calls


def operation_options():
    return {'submit': {'result': {'contract': 'x'}}, 'execute': {}, 'approve': {'attempt': 1},
            'reject': {'attempt': 1, 'note': '重做'}, 'edit_plan': {}, 'pause': {},
            'resume': {}, 'abort': {}, 'configure': {}, 'rewind': {'step': 1}}


def test_6_1_operation_guards(tmp):
    svc, state = start_offline(tmp)
    name = Path(state['run']).name
    for tool, options in operation_options().items():
        assert svc.tools[tool].__doc__
        for key in ('wrong', None, '\ud800'):
            assert rejects(ToolError, lambda: svc.tools[tool](key, name, **options)) == '鉴权失败'
        for run in ('../escape.json', '/etc/passwd', 'missing.json', '\ud800', ''):
            rejects(wc.ControlError, lambda: svc.tools[tool](KEY, run, **options))
        original = wc.ControlError('业务错误')
        with patch.object(wc, tool, side_effect=original):
            try:
                svc.tools[tool](KEY, name, **options)
            except wc.ControlError as error:
                assert error is original
            else:
                raise AssertionError('应原样抛出 ControlError')
        with patch.object(wc, tool, side_effect=ValueError('unexpected')):
            assert rejects(ToolError, lambda: svc.tools[tool](KEY, name, **options)) == '内部错误：ValueError: unexpected'


def test_6_1_operation_unicode(tmp):
    svc, state = start_offline(tmp)
    name = Path(state['run']).name
    bad_options = {'submit': {'result': {'contract': '\ud800'}},
                   'execute': {'model': '\ud800', 'note': '\ud800'},
                   'approve': {'attempt': 1, 'result': {'text': '\ud800'}},
                   'reject': {'attempt': 1, 'note': '\ud800'},
                   'edit_plan': {'tasks': [{'content': '\ud800'}]},
                   'configure': {'roles': {'ENGINEER': '\ud800'}},
                   'rewind': {'step': '\ud800'}}
    for tool, options in bad_options.items():
        with patch.object(wc, tool) as call:
            rejects(wc.ControlError, lambda: svc.tools[tool](KEY, name, **options))
            call.assert_not_called()


def asgi_request(svc, path, method='GET', query='', body=b'', headers=None, receive_override=None):
    """直接调用 ASGI，包含真实 lifespan；不使用客户端库或网络。"""
    async def invoke():
        app = server.make_app(svc)
        request_headers = {'host': '127.0.0.1:8765', 'content-length': str(len(body))}
        request_headers.update(headers or {})
        scope = {'type': 'http', 'asgi': {'version': '3.0', 'spec_version': '2.3'},
                 'http_version': '1.1', 'method': method, 'scheme': 'http',
                 'path': path, 'raw_path': path.encode('utf-8'), 'root_path': '',
                 'query_string': query.encode('utf-8'),
                 'headers': [(k.encode('latin-1'), v.encode('latin-1'))
                             for k, v in request_headers.items()],
                 'server': ('127.0.0.1', 8765), 'client': ('127.0.0.1', 12345)}
        messages = []
        received = False
        pending = asyncio.Event()

        async def receive():
            nonlocal received
            if not received:
                received = True
                return {'type': 'http.request', 'body': body, 'more_body': False}
            await pending.wait()
            return {'type': 'http.disconnect'}

        async def send(message):
            messages.append(message)

        async with app.router.lifespan_context(app):
            await app(scope, receive_override or receive, send)
        start = next(m for m in messages if m['type'] == 'http.response.start')
        data = b''.join(m.get('body', b'') for m in messages
                        if m['type'] == 'http.response.body')
        return start['status'], dict(start['headers']), data
    return asyncio.run(invoke())


def web_service(tmp, write=False, base='/trace'):
    return server.build_server('127.0.0.1', 8765, base, write, KEY, TOKEN,
                               root=tmp, workdirs=['workflow_demo', 'other'])


def web_post(svc, op, payload, headers=None):
    request_headers = {'origin': 'http://127.0.0.1:8765', 'content-type': 'application/json'}
    request_headers.update(headers or {})
    return asgi_request(svc, f'{svc.cfg.base}/{TOKEN}/api/{op}', 'POST',
                        body=json.dumps(payload).encode('utf-8'), headers=request_headers)


def test_6_1_web_page(tmp):
    svc = web_service(tmp, base='/workflow/nested')
    code, headers, body = asgi_request(svc, f'/workflow/nested/{TOKEN}/')
    assert code == 200 and b'<html' in body.lower()
    assert headers[b'content-type'].startswith(b'text/html')
    assert headers[b'referrer-policy'] == b'no-referrer'
    assert headers[b'content-length'] == str(len(body)).encode()


def test_6_1_web_wrong_token(tmp):
    code, _, body = asgi_request(web_service(tmp), '/trace/wrong-token/')
    assert code == 404 and json.loads(body)['error'] == '没有这个地址'


def test_6_1_web_runs(tmp):
    svc, state = start_offline(tmp)
    other = tmp / 'other/runs'
    other.mkdir(parents=True)
    (other / 'excluded.json').write_text('{}')
    code, _, body = asgi_request(svc, f'/trace/{TOKEN}/api/runs')
    rows = json.loads(body)['runs']
    assert code == 200 and len(rows) == 1
    assert rows[0]['name'] == Path(state['run']).name


def test_6_1_web_run(tmp):
    svc, state = start_offline(tmp)
    code, _, body = asgi_request(svc, f'/trace/{TOKEN}/api/run',
                                 query=urlencode({'name': Path(state['run']).name}))
    assert code == 200
    assert json.loads(body) == server.trace_server.read_trace(ROOT / state['run'])
    code, _, _ = asgi_request(svc, f'/trace/{TOKEN}/api/run', query='name=missing.json')
    assert code == 404


def test_6_1_web_plan(tmp):
    from test_wf_cost import demo_copy as cost_demo, plan
    from wf_fixtures import contract, review
    c = ScriptClient([contract('v1'), review('通过'), plan('ENGINEER')])
    c.offline = True
    state = wc.start(cost_demo(tmp), entry='run_cost.zs', mode='auto',
                     confirm_after=['任务分配'], client=c)
    code, _, body = asgi_request(web_service(tmp), f'/trace/{TOKEN}/api/plan',
                                 query=urlencode({'name': Path(state['run']).name,
                                                  'record': 'assignment'}))
    assert code == 200 and json.loads(body) == wc.plan(state['run'], 'assignment')


def test_6_1_web_readonly(tmp):
    svc, state = start_offline(tmp)
    for op in server.trace_server._WRITE_OPS:
        code, _, body = web_post(svc, op, {'name': Path(state['run']).name})
        assert code == 403 and json.loads(body)['ok'] is False
    assert svc.tools['status'](KEY, Path(state['run']).name) == state


def test_6_1_web_approve(tmp):
    from wf_fixtures import REPLIES
    svc, state = start_offline(tmp)
    name = Path(state['run']).name
    svc.tools['configure'](KEY, name, confirm_after=['ARCHITECT'])
    c = ScriptClient([REPLIES[0]])
    c.offline = True
    state = invoke_offline(svc, 'execute', c, name, step=1)
    assert state['pending']['phase'] == 'after'
    original = wc.approve
    with patch.object(wc, 'approve', side_effect=lambda *a, **kw: original(*a, client=c, **kw)) as call:
        code, _, body = web_post(web_service(tmp, write=True), 'approve',
                                 {'name': name, 'attempt': state['pending']['attempt'], 'step': 1})
    assert call.call_args.kwargs['wait'] is False
    out = json.loads(body)
    assert code == 200 and out['ok'] is True
    assert svc.tools['status'](KEY, name)['pending']['step'] == 2
    assert len(c.calls) == 1


def test_6_1_web_cross_origin(tmp):
    svc, state = start_offline(tmp)
    code, _, body = web_post(web_service(tmp, write=True), 'abort',
                             {'name': Path(state['run']).name},
                             {'origin': 'https://evil.example'})
    assert code == 403 and json.loads(body)['ok'] is False
    assert svc.tools['status'](KEY, Path(state['run']).name) == state


def test_6_1_web_request_validation(tmp):
    svc = web_service(tmp, write=True)
    for headers, expected in [({'content-type': 'text/plain'}, 415),
                               ({'content-length': str(server.trace_server._MAX_BODY + 1)}, 413)]:
        code, _, _ = web_post(svc, 'approve', {}, headers)
        assert code == expected
    code, _, _ = asgi_request(svc, f'/trace/{TOKEN}/api/approve', 'POST', body=b'{',
                              headers={'content-type': 'application/json'})
    assert code == 400
    code, _, _ = web_post(svc, 'approve', {'name': '\ud800'})
    assert code == 400


def test_6_1_web_mcp_endpoint(tmp):
    for base in ('/trace', '/workflow/nested'):
        svc = web_service(tmp, base=base)
        for method in ('GET', 'POST'):
            with patch.object(server.trace_server, 'route') as route:
                code, _, _ = asgi_request(svc, base + '/mcp', method)
            assert code in (400, 406, 415)
            route.assert_not_called()


def test_6_1_handler_body_read_order(tmp):
    """内存 handler：拒绝请求不能读取承诺但尚未发送的正文。"""
    trace_server = server.trace_server
    runs = tmp / 'runs'
    runs.mkdir()
    (runs / 'ok.json').write_text('{}')
    payload = json.dumps({'name': 'ok.json'}).encode('utf-8')

    class Body:
        def __init__(self, allowed):
            self.allowed = allowed
            self.reads = []

        def read(self, size):
            self.reads.append(size)
            assert self.allowed, 'BODY_READ_BEFORE_REJECTION'
            return payload

    cases = [
        ('/wrong', TOKEN, True, {}, 404),
        ('/trace/wrong/api/abort', TOKEN, True, {}, 404),
        (f'/trace/{TOKEN}/api/unknown', TOKEN, True, {}, 404),
        (f'/trace/{TOKEN}/api/abort', TOKEN, False, {}, 403),
        (f'/trace/{TOKEN}/api/abort', TOKEN, True, {'Origin': 'https://evil.example'}, 403),
        (f'/trace/{TOKEN}/api/abort', TOKEN, True, {'Origin': 'null'}, 403),
        ('/trace/api/abort', None, True, {'Host': 'evil.example', 'Origin': ''}, 403),
        (f'/trace/{TOKEN}/api/abort', TOKEN, True, {'Content-Type': 'text/plain'}, 415),
        (f'/trace/{TOKEN}/api/abort', TOKEN, True, {'Content-Length': '-1'}, 413),
        (f'/trace/{TOKEN}/api/abort', TOKEN, True, {'Content-Length': 'bad'}, 413),
        (f'/trace/{TOKEN}/api/abort', TOKEN, True,
         {'Content-Length': str(trace_server._MAX_BODY + 1)}, 413),
        (f'/trace/{TOKEN}/api/abort', TOKEN, True,
         {'Content-Length': str(len(payload))}, 200),
    ]
    for path, token, write, overrides, expected in cases:
        handler = object.__new__(trace_server.make_handler(runs, token, '/trace', write))
        handler.path = path
        handler.headers = {'Host': '127.0.0.1:8765', 'Origin': 'http://127.0.0.1:8765',
                           'Content-Type': 'application/json', 'Content-Length': '1'}
        handler.headers.update(overrides)
        handler.rfile = Body(expected == 200)
        handler.wfile = BytesIO()
        with patch.object(handler, 'send_response') as response, \
                patch.object(handler, 'send_header'), patch.object(handler, 'end_headers'), \
                patch.object(trace_server, 'route', wraps=trace_server.route) as route, \
                patch.object(trace_server, 'control', return_value=(200, {'ok': True})) as control:
            handler.do_POST()
        response.assert_called_once_with(expected)
        route.assert_called_once()
        if expected == 200:
            assert handler.rfile.reads == [len(payload)]
            control.assert_called_once_with('abort', (runs / 'ok.json').resolve(), {'name': 'ok.json'})
            assert json.loads(handler.wfile.getvalue()) == {'ok': True}
        else:
            assert handler.rfile.reads == []
            control.assert_not_called()
            assert json.loads(handler.wfile.getvalue())['ok'] is False


def test_6_1_asgi_body_read_order(tmp):
    """头部拒绝必须在首次 receive 前完成，也检查多个错误的优先级。"""
    path = f'/trace/{TOKEN}/api/abort'
    cases = [
        ('/trace/wrong/api/abort', False, {}, 404),
        (f'/trace/{TOKEN}/api/unknown', False, {}, 404),
        (path, False, {}, 403),
        (path, True, {'origin': 'https://evil.example'}, 403),
        (path, True, {'origin': 'null'}, 403),
        (path, True, {'host': 'other.example'}, 403),
        (path, True, {'content-type': 'text/plain'}, 415),
        (path, True, {'content-length': '-1'}, 413),
        (path, True, {'content-length': 'bad'}, 413),
        (path, True, {'content-length': '9' * 5000}, 413),
        (path, True, {'content-length': '4194305'}, 413),
    ]

    async def forbidden_receive():
        raise AssertionError('BODY_READ_BEFORE_REJECTION')

    for address, write, overrides, expected in cases:
        headers = {'origin': 'http://127.0.0.1:8765',
                   'content-type': 'text/plain' if expected in (403, 404) else 'application/json',
                   'content-length': '4194305'}
        headers.update(overrides)
        with patch.object(server.trace_server, 'control') as control:
            code, _, body = asgi_request(web_service(tmp, write=write), address, 'POST',
                                         headers=headers, receive_override=forbidden_receive)
        assert code == expected
        assert json.loads(body)['ok'] is False
        control.assert_not_called()


def test_6_1_asgi_body_limit(tmp):
    """声明长度不能代替流式上限：超过 4MiB 后不再读取下一块。"""
    for declared in ('1', str(server.trace_server._MAX_BODY)):
        reads = []

        async def receive():
            reads.append(1)
            assert len(reads) <= 5, 'BODY_READ_AFTER_LIMIT'
            return {'type': 'http.request',
                    'body': b'x' * (1024 * 1024) if len(reads) <= 4 else b'x',
                    'more_body': True}

        with patch.object(server.trace_server, 'control') as control:
            code, _, body = asgi_request(web_service(tmp, write=True),
                                         f'/trace/{TOKEN}/api/abort', 'POST',
                                         headers={'content-type': 'application/json',
                                                  'content-length': declared},
                                         receive_override=receive)
        assert code == 413 and json.loads(body)['ok'] is False
        assert len(reads) == 5
        control.assert_not_called()


def test_6_1_asgi_chunked_body(tmp):
    runs = tmp / 'workflow_demo/runs'
    runs.mkdir(parents=True)
    (runs / 'ok.json').write_text('{}')
    payload = b'{"name": "ok.json"}'
    # 包含恰好上限的合法 JSON，证明边界和多次 receive 都能正常处理。
    for size in (len(payload), server.trace_server._MAX_BODY):
        data = payload + b' ' * (size - len(payload))
        chunks = [data[:5], data[5:11], data[11:]]
        reads = []

        async def receive():
            reads.append(1)
            assert chunks, 'BODY_READ_AFTER_END'
            chunk = chunks.pop(0)
            return {'type': 'http.request', 'body': chunk, 'more_body': bool(chunks)}

        with patch.object(server.trace_server, 'control', return_value=(200, {'ok': True})) as control:
            code, _, body = asgi_request(web_service(tmp, write=True),
                                         f'/trace/{TOKEN}/api/abort', 'POST',
                                         headers={'content-type': 'application/json',
                                                  'content-length': str(size)},
                                         receive_override=receive)
        assert code == 200 and json.loads(body) == {'ok': True}
        assert len(reads) == 3
        control.assert_called_once_with('abort', (runs / 'ok.json').resolve(), {'name': 'ok.json'})


def test_6_1_http_launch(tmp):
    with patch.object(server, 'load_key', return_value=KEY), \
            patch.object(server, 'load_trace_token', return_value=TOKEN), \
            patch.object(FastMCP, 'run') as run:
        svc = server.main([])
        run.assert_called_once_with(transport='http', host='127.0.0.1', port=8765,
                                    path='/trace/mcp')
        run.reset_mock()
        svc = server.main(['--host', 'localhost', '--port', '9000', '--base', '/wf', '--write'])
        run.assert_called_once_with(transport='http', host='localhost', port=9000, path='/wf/mcp')
        assert svc.cfg.write is True


CASES = [test_6_1_startup_missing_key, test_6_1_startup_short_key,
         test_6_1_startup_key_file_and_environment, test_6_1_startup_trace_token,
         test_6_1_auth_wrong_missing, test_6_1_runs_name, test_6_1_resolve_run,
         test_6_1_workdir_allowlist, test_6_1_entry_rejected, test_6_1_tool_errors,
         test_6_1_main_startup]

CASES += [test_6_1_start_status, test_6_1_start_entry_scope, test_6_1_status_detail_truncation,
          test_6_1_plan_assignment, test_6_1_agents_cards, test_6_1_viewer_url,
          test_6_1_read_tools_errors]


CASES += [test_6_1_submit_approve, test_6_1_execute_reject, test_6_1_edit_plan_cost_preview,
          test_6_1_pause_resume_abort_configure_rewind, test_6_1_operation_guards,
          test_6_1_operation_unicode]


CASES += [test_6_1_web_page, test_6_1_web_wrong_token, test_6_1_web_runs,
          test_6_1_web_run, test_6_1_web_plan, test_6_1_web_readonly,
          test_6_1_web_approve, test_6_1_web_cross_origin, test_6_1_web_request_validation,
          test_6_1_web_mcp_endpoint, test_6_1_http_launch, test_6_1_handler_body_read_order]


CASES += [test_6_1_asgi_body_read_order, test_6_1_asgi_body_limit, test_6_1_asgi_chunked_body]


def run():
    (ROOT / 'data/tmp').mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='wf-mcp-', dir=ROOT / 'data/tmp') as folder:
        for case in CASES:
            tmp = Path(folder) / case.__name__
            tmp.mkdir()
            case(tmp)
            print('  ✓', case.__name__)
    print(f'流程管理 MCP：通过 {len(CASES)} 项')


if __name__ == '__main__':
    run()
