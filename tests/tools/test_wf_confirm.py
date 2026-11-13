"""开始前确认规则：独立脚本，离线运行，不依赖 pytest。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import json
import shutil
import tempfile
import threading

from test_workflow_ctl import ROOT, REPLIES, check, client, demo_copy, raises
from tools import workflow_ctl as wc


# 独立脚本仍不依赖 pytest；pytest 收集时提供同样位于项目内的临时目录。
if 'pytest' in sys.modules:
    @sys.modules['pytest'].fixture
    def tmp():
        (ROOT / 'data/tmp').mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='wfconfirm-', dir=ROOT / 'data/tmp') as folder:
            yield Path(folder)


def decision(rules, role='ENGINEER', name='任务实现', **cfg):
    config = dict(mode='auto', confirm_before=rules)
    config.update(cfg)
    return wc._Control(config).decide(dict(step=1, role=role, name=name))


def test_legacy(tmp):
    s = wc.start(demo_copy(tmp, 'legacy'), mode='auto', stop_roles=['QA_ENGINEER'],
                 client=client(REPLIES))
    check(s['pending']['step'] == 8 and s['pending']['role'] == 'QA_ENGINEER',
          '旧 stop_roles 调用仍在 QA 前停')
    check(s['confirm_before'] == s['stop_roles'] == ['QA_ENGINEER'], 'status 两个别名相等')
    path = wc._side(ROOT / s['run'], '.ctl')
    cfg = json.loads(path.read_text(encoding='utf-8'))
    check(cfg['confirm_before'] == cfg['stop_roles'], '新控制文件写两个相同的键')
    del cfg['confirm_before']
    wc._dump(path, cfg)
    s = wc.resume(s['run'], client=client([]))
    check(s['pending']['step'] == 8 and s['confirm_before'] == s['stop_roles'],
          '只有旧键的控制文件仍按旧规则停')
    check('confirm_before' not in wc._load(path), '读取旧控制文件不迁移')


def test_matching(tmp):
    for role in ['ENGINEER', 'ENGINEER_GPT_SENIOR']:
        d = decision(['ENGINEER*'], role=role)
        check(d['action'] == 'wait' and d['reason'] == 'rule:ENGINEER*', role + ' 前缀命中')
    check(decision(['ENGINEER*'], role='ARCHITECT')['action'] == 'run', 'ARCHITECT 不匹配')
    check(decision(['任务实现'])['reason'] == 'rule:任务实现', '中文节点名匹配')
    check(decision(['*'], role='ARCHITECT')['action'] == 'wait', '* 匹配全部')
    check(wc._match(['QA', 'ENGINEER*', '*'], {'ENGINEER'}) == 'ENGINEER*', '返回第一条命中规则')
    check(wc._match(['ENGINEER'], {'ENGINEER_SENIOR'}) is None, '普通规则精确匹配')
    check(wc._match([], {'ENGINEER'}) is None, '空规则无命中')
    for rules, step in [(['ENGINEER*'], 6), (['任务实现'], 6), (['*'], 1)]:
        s = wc.start(demo_copy(tmp, 'match' + str(step) + str(len(rules[0]))),
                     mode='auto', confirm_before=rules, client=client(REPLIES))
        check(s['pending']['step'] == step, str(rules) + ' 在实际编排中停下')


def test_roles(tmp):
    for rule in ['ENGINEER', 'ENGINEER_SENIOR']:
        d = decision([rule], roles={'ENGINEER': 'ENGINEER_SENIOR'})
        check(d['action'] == 'wait' and d['reason'] == 'rule:' + rule, '原卡和换后卡都匹配：' + rule)
    d = decision(['ENGINEER_SENIOR'], roles={'ENGINEER': 'ENGINEER_SENIOR'},
                 go={'1': {'role': 'ENGINEER_GPT_SENIOR'}})
    check(d['action'] == 'run' and d['role'] == 'ENGINEER_GPT_SENIOR', 'execute 换卡且优先于确认')
    d = decision(['*'], submitted={'1': {'ok': True}})
    check(d['action'] == 'result', '外部提交优先于确认')
    check(decision(['*'], mode='step')['reason'] == 'step', '逐步原因优先于规则')
    d = wc._Control(dict(mode='auto'), force_step=True).decide(dict(step=1, role='ENGINEER', name='任务实现'))
    check(d['action'] == 'wait' and d['reason'] == 'step', 'force_step 保持逐步停下')


def test_validation(tmp):
    demo = demo_copy(tmp, 'validation')
    s = wc.start(demo, client=client([]))
    for bad in ['', 'a*b', '**', 'a b', '../x', 'x\n', '\ud800', 'a' * 81, 3, None]:
        for key in ['confirm_before', 'stop_roles']:
            raises(lambda: wc.start(demo, client=client([]), **{key: [bad]}), '确认规则无效：')
            raises(lambda: wc.configure(s['run'], **{key: [bad]}), '确认规则无效：')
    for bad in ['ENGINEER', 3, {}]:
        raises(lambda: wc.start(demo, confirm_before=bad, client=client([])), '确认规则无效：')
        raises(lambda: wc.configure(s['run'], confirm_before=bad), '确认规则无效：')
    for call in [lambda: wc.start(demo, stop_roles=[], confirm_before=['*'], client=client([])),
                 lambda: wc.configure(s['run'], stop_roles=['QA'], confirm_before=['*'])]:
        raises(call, '两个是同一个设置，只给一个')
    check(True, 'start/configure 拒绝错误规则、孤立代理字符和别名冲突')
    valid = ['任务·实现.一-*', 'a' * 80 + '*']
    s = wc.configure(s['run'], confirm_before=valid, stop_roles=valid)
    check(s['confirm_before'] == s['stop_roles'] == valid, '允许中文标点和 80 字符前缀边界及相同别名')
    s = wc.configure(s['run'], models={})
    check(s['confirm_before'] == valid, 'None 保持设置')
    s = wc.configure(s['run'], stop_roles=[])
    check(s['confirm_before'] == s['stop_roles'] == [], '旧名空列表清空两个键')


def test_configure(tmp):
    c = client(REPLIES)
    s = wc.start(demo_copy(tmp, 'configure'), mode='auto', confirm_before=['ARCHITECT'], client=c)
    check(s['pending']['step'] == 1, '运行先在 ARCHITECT 停')
    s = wc.configure(s['run'], confirm_before=['QA_ENGINEER'])
    s = wc.resume(s['run'], client=c)
    check(s['pending']['step'] == 8 and len(c.calls) == 7, '中途 configure 后按新规则在 QA 前停')
    s = wc.configure(s['run'], confirm_before=[])
    s = wc.resume(s['run'], client=c)
    check(s['status'] == 'done' and len(c.calls) == 10, '清空确认规则后跑到底')


def task_events(run):
    return [e for e in wc._load(ROOT / run)['events'] if e['type'] == 'task']


def test_execute_note(tmp):
    c = client(REPLIES)
    s = wc.start(demo_copy(tmp, 'note'), client=c)
    original = s['pending']['task']
    s = wc.execute(s['run'], note='注意分页从 1 开始', actor='viewer', client=c)
    prompt = c.calls[0]['prompt']
    check('补充说明（人工追加，和任务同等效力）：\n1. 注意分页从 1 开始\n' in prompt,
          'execute 追加说明传到模型提示词')
    e = task_events(s['run'])[0]
    check(e['task'] == original and e['attempt'] == 1, '任务原文不变，首次 attempt 为 1')
    check(e['notes'][0] == dict(kind='add', text='注意分页从 1 开始', attempt=1,
                               actor='viewer', at=e['notes'][0]['at']) and e['notes'][0]['at'],
          '说明记录 kind/text/attempt/actor/at')
    check(e['confirm'] == [dict(phase='before', action='note', actor='viewer', at=e['notes'][0]['at']),
                           dict(phase='before', action='run', role=None, model=None,
                                actor='viewer', at=e['notes'][0]['at'])], '确认记录保存操作人与时间')
    check(s['steps'][0]['attempt'] == 1 and s['steps'][0]['confirm'] == e['confirm'],
          'status 的任务摘要带 attempt/confirm')
    cfg = wc._load(wc._side(ROOT / s['run'], '.ctl'))
    check(cfg['go']['1']['attempt'] == 1 and cfg['go']['1']['actor'] == 'viewer'
          and cfg['history'][-1]['actor'] == 'viewer', 'go 和 history 保存授权信息')
    check([a['at'] for a in e['confirm']] == sorted(a['at'] for a in e['confirm'])
          and e['confirm'][-1]['at'] == cfg['go']['1']['at'], 'note 先于 run，时间与持久化授权一致')
    s = wc.execute(s['run'], client=c)
    check(len(c.calls) == 2 and task_events(s['run'])[0] == e, '回放仍核对原文，说明和确认不变')


def test_execute_without_note(tmp):
    c = client(REPLIES)
    s = wc.start(demo_copy(tmp, 'no-note'), client=c)
    s = wc.execute(s['run'], client=c)
    e = task_events(s['run'])[0]
    check('补充说明' not in c.calls[0]['prompt'] and 'notes' not in e,
          '未给 note 时不添加提示段和事件 notes')
    check(e['confirm'][0]['actor'] == 'workflow_ctl', '默认 actor 有值')
    check([a['action'] for a in e['confirm']] == ['run'], '无 note 执行只记录 run')


def test_execute_legacy_positional(tmp):
    from unittest.mock import patch
    c = client([REPLIES[0]])
    s = wc.start(demo_copy(tmp, 'legacy-positional'), client=c)
    run = s['run']
    original_task = s['pending']['task']
    with patch.object(wc, '_continue', wraps=wc._continue) as advance:
        s = wc.execute(run, None, None, 1, True, c)
        advance.assert_called_once_with(ROOT / run, True, c)
    check(len(c.calls) == 1 and s['status'] == 'waiting' and s['pending']['step'] == 2,
          '旧位置调用保留 step、wait 和 ScriptClient，只执行第 1 步')
    events = task_events(run)
    check([(e['step'], e['status']) for e in events] == [(1, 'ok'), (2, 'waiting')]
          and events[0]['result'] == REPLIES[0], '旧位置调用使用传入客户端的离线结果')
    check(events[0]['task'] == original_task and 'notes' not in events[0]
          and '补充说明' not in c.calls[0]['prompt']
          and not wc._load(wc._side(ROOT / run, '.ctl')).get('notes'),
          '旧位置调用不向任务、提示词或控制文件意外追加说明')


def test_execute_legacy_positional_with_keywords(tmp):
    from unittest.mock import patch
    c = client([REPLIES[0]])
    s = wc.start(demo_copy(tmp, 'legacy-positional-keywords'), client=c)
    run = s['run']
    original_task = s['pending']['task']
    with patch.object(wc, '_continue', wraps=wc._continue) as advance:
        s = wc.execute(run, None, None, 1, True, c, note='兼容旧位置调用', actor='mcp:test')
        advance.assert_called_once_with(ROOT / run, True, c)
    e = task_events(run)[0]
    check(len(c.calls) == 1 and s['pending']['step'] == 2 and e['task'] == original_task,
          '旧位置参数同时搭配 note/actor 关键字仍只执行第 1 步')
    check('1. 兼容旧位置调用' in c.calls[0]['prompt']
          and [n['text'] for n in e['notes']] == ['兼容旧位置调用']
          and e['notes'][0]['actor'] == e['confirm'][0]['actor'] == 'mcp:test',
          '兼容调用正确传递关键字说明和来源')


def test_note_retry_pending(tmp):
    c = client(['不是 JSON', '仍然不是 JSON', REPLIES[0]])
    s = wc.start(demo_copy(tmp, 'retry-note'), client=c)
    run = s['run']
    s = wc.execute(run, note='保留第一条说明', client=c)
    d = wc.status(run, detail=True)
    pend = d['pending']
    check(pend['phase'] == 'before' and pend['reason'] == 'error' and pend['attempt'] == 2,
          '失败后 pending 标记开始前、error 和下一次尝试数')
    check('补充说明' in pend['prompt'] and '保留第一条说明' in pend['prompt']
          and pend['notes'][0]['attempt'] == 1, '失败重停 describe 提示词仍带说明')
    first = task_events(run)[0]
    check(first['status'] == 'error' and first['attempt'] == 1 and first['notes']
          and first['confirm'][0]['actor'], '失败事件也带 attempt/notes/confirm')
    check(first['confirm'] == [
        dict(phase='before', action='note', actor='workflow_ctl', at=first['notes'][0]['at']),
        dict(phase='before', action='run', role=None, model=None,
             actor='workflow_ctl', at=first['notes'][0]['at'])], '失败尝试保留 note/run 及准确来源和时间')
    # 重新回放并按规则停下，过期的 execute 不应授权第二次尝试。
    wc.configure(run, confirm_before=['*'])
    s = wc.resume(run, client=c)
    check(len(c.calls) == 1 and s['pending']['attempt'] == 2
          and s['pending']['reason'] == 'rule:*', '旧 go 不会在 resume 时重复授权')
    check(task_events(run)[0] == first, '失败回放完整保留 note/run')
    s = wc.execute(run, note='追加第二条说明', actor='mcp:test', client=c)
    check(s['pending']['attempt'] == 3 and [n['attempt'] for n in s['pending']['notes']] == [1, 2],
          '多次 execute 累积说明，尝试数逐次增加')
    second = task_events(run)[1]
    check(second['confirm'] == [
        dict(phase='before', action='note', actor='mcp:test', at=second['notes'][1]['at']),
        dict(phase='before', action='run', role=None, model=None,
             actor='mcp:test', at=second['notes'][1]['at'])], '重试只记录本次新增 note 和 run，来源及时间准确')
    s = wc.execute(run, client=c)
    events = task_events(run)
    check([e['attempt'] for e in events[:3]] == [1, 2, 3]
          and [e['status'] for e in events[:3]] == ['error', 'error', 'ok']
          and events[0] == first, '失败记录原样保留，成功重试记正确 attempt')
    check(events[1] == second and [a['action'] for a in events[2]['confirm']] == ['run'],
          '重试回放保留此前确认，只有历史说明时不新增 note 动作')
    check('1. 保留第一条说明\n2. 追加第二条说明' in c.calls[2]['prompt'],
          '不追加新说明的重试仍收到全部历史说明')


def test_rewind_notes(tmp):
    c = client(REPLIES)
    s = wc.start(demo_copy(tmp, 'rewind-note'), client=c)
    s = wc.execute(s['run'], note='第一步', client=c)
    s = wc.execute(s['run'], note='第二步', client=c)
    s = wc.rewind(s['run'], 2, client=c)
    cfg = wc._load(wc._side(ROOT / s['run'], '.ctl'))
    check(set(cfg['notes']) == {'1'} and set(cfg['go']) == {'1'}, 'rewind 清当前及后续说明，保留前序说明')
    d = wc.status(s['run'], detail=True)
    check(d['pending']['notes'] == [] and d['pending']['attempt'] == 1
          and '补充说明' not in d['pending']['prompt'], 'rewind 后提示词和尝试次数重置')


def test_note_validation(tmp):
    c = client(REPLIES)
    s = wc.start(demo_copy(tmp, 'invalid-note'), client=c)
    p = ROOT / s['run']
    cf = wc._side(p, '.ctl')
    for bad, message in [('', '说明必须是非空字符串'), (' \n', '说明必须是非空字符串'),
                         (3, '说明必须是非空字符串'), ([], '说明必须是非空字符串'),
                         ('字' * 4001, '说明最多 4000 字'), ('\ud800', '说明必须是有效的 UTF-8 字符串')]:
        before = (p.read_bytes(), cf.read_bytes())
        raises(lambda: wc.execute(s['run'], note=bad, client=c), message)
        check(before == (p.read_bytes(), cf.read_bytes()) and not c.calls, '非法说明无写入、无模型调用')
    raises(lambda: wc.execute(s['run'], model='bad', note='', client=c), '模型名无效')
    raises(lambda: wc.execute(s['run'], role='../bad', note='', client=c), '角色卡名无效')
    check(True, '沿用模型、角色优先于说明的校验顺序')
    s = wc.execute(s['run'], note='字' * 4000, client=c)
    check('字' * 4000 in c.calls[0]['prompt'], '实际执行 4000 字边界，按字符而非字节计数')


def test_execute_string_encoding(tmp):
    c = client([])
    s = wc.start(demo_copy(tmp, 'invalid-encoding'), client=c)
    p = ROOT / s['run']
    cf = wc._side(p, '.ctl')
    for kw, message in [({'model': 'cli:claude/\ud800'}, '模型名无效'),
                        ({'role': '\ud800'}, '角色卡名无效')]:
        before = (p.read_bytes(), cf.read_bytes())
        raises(lambda: wc.execute(s['run'], client=c, **kw), message)
        check(before == (p.read_bytes(), cf.read_bytes()) and not c.calls,
              'execute 模型名、角色名的孤立代理字符在写入前拒绝')


def test_external_actor(tmp):
    c = client([])
    s = wc.start(demo_copy(tmp, 'external-actor'), client=c)
    s = wc.submit(s['run'], REPLIES[0], actor='mcp:test', client=c)
    e = task_events(s['run'])[0]
    check(e['actor'] == 'mcp:test' and e['attempt'] == 1 and e['source'] == 'external'
          and e['confirm'][0]['phase'] == 'before' and e['confirm'][0]['action'] == 'submit'
          and e['confirm'][0]['actor'] == 'mcp:test' and e['confirm'][0]['at'],
          '外部 submit 事件保存 actor 和开始前 submit 确认')
    check(s['steps'][0]['actor'] == 'mcp:test' and not c.calls, '外部提交摘要带 actor，不调用模型')


def test_prune_notes_numeric_steps(tmp):
    cfg = {key: {step: [step] for step in ['10', '1', '3', '2']}
           for key in ['notes', 'go', 'submitted']}
    wc._prune(cfg, 3)
    check(all(set(cfg[key]) == {'1', '2'} for key in cfg),
          '清理按数字步号处理无序键，同时清 notes/go/submitted 当前及后续步')


def test_actor_validation(tmp):
    c = client([])
    s = wc.start(demo_copy(tmp, 'invalid-actor'), client=c)
    p = ROOT / s['run']
    cf = wc._side(p, '.ctl')
    for bad in ['乱写 的', '', None, 3, 'viewer\n', '\ud800', 'mcp:', 'mcp:' + 'a' * 65]:
        before = (p.read_bytes(), cf.read_bytes())
        raises(lambda: wc.execute(s['run'], actor=bad, client=c), '来源无效：')
        raises(lambda: wc.submit(s['run'], REPLIES[0], actor=bad, client=c), '来源无效：')
        check(before == (p.read_bytes(), cf.read_bytes()), '非法 actor 在 execute/submit 写入前拒绝')


def test_attempt_compatibility(tmp):
    req = dict(step=1, role='ENGINEER', name='任务实现')
    notes = [dict(kind='add', text='历史说明', attempt=1, actor='viewer', at='then')]
    for attempt, expected in [(None, 'run'), (1, 'wait'), (2, 'run'), (3, 'wait')]:
        go = {} if attempt is None else dict(attempt=attempt)
        ctl = wc._Control(dict(mode='step', go={'1': go}, notes={'1': notes}))
        ctl.failed[1] = [dict(status='error')]
        d = ctl.decide(req)
        check(d['action'] == expected and d['attempt'] == 2 and d['notes'] == notes
              and d['failed'] == ctl.failed[1], 'go 缺省兼容，显式 attempt 只匹配当前次')
    s = wc.start(demo_copy(tmp, 'old-status'), client=client([]))
    p = ROOT / s['run']
    t = wc._load(p)
    for key in ['phase', 'reason', 'attempt', 'notes']:
        t['pending'].pop(key, None)
    for e in t['events']:
        e.pop('attempt', None)
    wc._dump(p, t)
    before = p.read_bytes()
    d = wc.status(s['run'])
    check(d['pending']['phase'] == 'before' and d['pending']['reason'] == 'step'
          and d['pending']['attempt'] == 1 and d['steps'][0]['attempt'] == 1,
          '旧记录 status 为新增字段提供缺省值')
    check(p.read_bytes() == before, '读取旧记录不改文件')


def test_prompt_layout(tmp):
    from verbs.workflow._agents import _prompt
    notes = [dict(text='第一条'), dict(text='第二条')]
    for fmt, submit in [(None, False), (('result', {'type': 'object'}), False),
                        (('result', {'type': 'object'}), True)]:
        prompt = _prompt('原任务', '参考内容', '节点', fmt, submit, notes=notes, previous={'ignored': True})
        check(prompt.index('参考文本') < prompt.index('补充说明') < prompt.index('1. 第一条'),
              '追加说明位于参考文本之后，保持列表顺序')
        check('2. 第二条' in prompt and 'ignored' not in prompt, 'previous 参数本阶段不使用')
        if not submit:
            check(prompt.index('2. 第二条') < prompt.index('只返回一个 JSON 对象'), '追加说明位于格式说明之前')


def test_settle_preserves_notes(tmp):
    c = client(['不是 JSON', REPLIES[0]])
    s = wc.start(demo_copy(tmp, 'settle-note'), client=c)
    s = wc.execute(s['run'], note='恢复时不能丢失', client=c)
    p = ROOT / s['run']
    t = wc._load(p)
    t.update(status='error')
    t.pop('pending')
    wc._dump(p, t)
    before = p.read_bytes()
    raises(lambda: wc.execute(s['run'], note='\ud800', client=c), '说明必须是有效的 UTF-8 字符串')
    check(p.read_bytes() == before, '非法说明在 settle 回放之前拒绝')
    cfg = wc._load(wc._side(p, '.ctl'))
    settled = wc._settle(p, cfg, t, c)
    check(settled['pending']['attempt'] == 2 and settled['pending']['reason'] == 'error'
          and '恢复时不能丢失' in settled['pending']['prompt'] and len(c.calls) == 1,
          'error 恢复仅回放，pending 的说明、原因、次数保留')
    s = wc.execute(s['run'], client=c)
    check(task_events(s['run'])[1]['attempt'] == 2 and '恢复时不能丢失' in c.calls[1]['prompt'],
          '恢复后只授权当前尝试并继续传历史说明')


def test_legacy_agent_signature(tmp):
    from tools.dsl import DSLEngine
    from verbs.workflow import _workflow
    calls = []

    def fake(engine, role, task, context):
        calls.append(task)
        return {'ok': True}

    script = '任务实现\n    任务 原文\n    角色 ENGINEER\n    记录 result\n'
    for controlled in [False, True]:
        wd = tmp / ('legacy-agent-' + str(controlled))
        wd.mkdir()
        engine = DSLEngine(client=client([]), workdir=wd, verbose=False)
        if controlled:
            engine._wf_control = wc._Control(dict(mode='auto'))
        _workflow.run(engine, script, fake)
        e = wc._load(engine.vars['workflow_trace'])['events'][0]
        check(e['status'] == 'ok' and 'notes' not in e and 'confirm' not in e,
              '无说明时兼容不接受 notes 的旧假 call_agent')
        check(('attempt' in e) == controlled, '不受控事件不增加 attempt 等控制字段')
    check(calls == ['原文', '原文'], '受控和不受控均只调用一次假模型')


def test_note_with_override(tmp):
    c = client([REPLIES[0]])
    s = wc.start(demo_copy(tmp, 'override-note'), client=c)
    s = wc.execute(s['run'], role='ARCHITECT_GLM', model='cli:goose/glm-5.3',
                   note='换卡仍保留任务', actor='mcp:' + 'a' * 64, client=c)
    e = task_events(s['run'])[0]
    check(e['role'] == 'ARCHITECT_GLM' and e['default_role'] == 'ARCHITECT'
          and e['model_override'] == 'cli:goose/glm-5.3', '追加说明兼容换卡换模型')
    check(e['confirm'][1]['role'] == 'ARCHITECT_GLM'
          and e['confirm'][1]['model'] == 'cli:goose/glm-5.3'
          and '换卡仍保留任务' in c.calls[0]['prompt'], '确认记录准确保留角色、模型及 actor 长度边界')


def test_configure_during_execute(tmp):
    from concurrent.futures import ThreadPoolExecutor
    entered, release = threading.Event(), threading.Event()
    c = client(REPLIES)
    original = c.chat_messages

    def blocked(messages, **kw):
        entered.set()
        assert release.wait(10), '没有释放假模型'
        return original(messages, **kw)

    c.chat_messages = blocked
    s = wc.start(demo_copy(tmp, 'concurrent-note'), client=c)
    wc.configure(s['run'], confirm_before=['*'])
    wc.resume(s['run'], client=c)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(wc.execute, s['run'], note='只用于当前步', client=c)
        try:
            assert entered.wait(10), '假模型没有进入调用'
            wc.configure(s['run'], confirm_before=['ARCHITECT_GLM'])
        finally:
            release.set()
        out = future.result(timeout=10)
    check(out['pending']['step'] == 2 and out['pending']['reason'] == 'rule:ARCHITECT_GLM'
          and len(c.calls) == 1, 'Event 控制交错：执行中改规则，当前步只跑一次，下一步用新规则')
    e = task_events(s['run'])[0]
    check(len(e['notes']) == 1 and [a['action'] for a in e['confirm']] == ['note', 'run'] and e['attempt'] == 1,
          '并发 configure 不丢失或重复当前尝试的说明和确认')


def test_all_write_actors(tmp):
    # 设计第 8 节第 21 条：八个写接口均记录显式来源和缺省来源。
    for actor in ['viewer', 'mcp:test', 'workflow_ctl']:
        kw = {} if actor == 'workflow_ctl' else {'actor': actor}
        c = client(REPLIES)
        s = wc.start(demo_copy(tmp, 'all-actors-' + actor.replace(':', '-')), client=c, **kw)
        run = s['run']
        wc.configure(run, confirm_before=['*'], **kw)
        s = wc.execute(run, client=c, **kw)
        first = task_events(run)[0]
        check(first['confirm'][0]['actor'] == actor and first['result'] == REPLIES[0],
              'execute 确认来源正确，结果不掺入 actor：' + actor)
        s = wc.submit(run, REPLIES[1], client=c, **kw)
        second = task_events(run)[1]
        check(second['actor'] == second['confirm'][0]['actor'] == actor
              and s['steps'][1]['actor'] == actor and second['result'] == REPLIES[1],
              'submit 事件、确认和 status 保留来源：' + actor)
        check('actor' not in s['steps'][0] and actor not in c.calls[0]['prompt'],
              '事件没有顶层 actor 时 status 不补写，来源不进入提示词')
        wc.pause(run, **kw)
        wc.resume(run, client=c, **kw)
        wc.rewind(run, 2, client=c, **kw)
        s = wc.abort(run, **kw)
        cfg = wc._load(wc._side(ROOT / run, '.ctl'))
        check([h['op'] for h in cfg['history']] ==
              ['start', 'configure', 'execute', 'submit', 'pause', 'resume', 'rewind', 'abort']
              and all(h['actor'] == actor for h in cfg['history']),
              '全部写操作 history 保留来源且不增加操作条目：' + actor)
        check(cfg['history'][1]['confirm_before'] == ['*']
              and s['status'] == 'aborted' and s['error'] == '外部中止（' + actor + '）',
              'configure 记录 confirm_before，abort 顶层 error 保持外部中止格式')


def test_all_write_actor_validation(tmp):
    demo = demo_copy(tmp, 'all-invalid-actors')
    s = wc.start(demo, client=client([]))
    run = s['run']
    # 同时给错误业务参数，确认 actor 校验先于路径、模型、规则和步号校验。
    calls = [lambda bad: wc.start(None, actor=bad),
             lambda bad: wc.configure(run, confirm_before=['a b'], actor=bad),
             lambda bad: wc.execute(run, model='invalid', actor=bad),
             lambda bad: wc.submit(run, 'not json', actor=bad),
             lambda bad: wc.abort(run, actor=bad),
             lambda bad: wc.pause(run, actor=bad),
             lambda bad: wc.resume(run, actor=bad),
             lambda bad: wc.rewind(run, 'invalid', actor=bad)]
    def snapshot():
        return {str(p.relative_to(demo)): p.read_bytes() for p in demo.rglob('*') if p.is_file()}
    before = snapshot()
    for bad in ['乱写 的', '', None, 3, 'viewer\n', '\ud800', 'mcp:\ud800',
                'mcp:', 'mcp:' + 'a' * 65]:
        for call in calls:
            raises(lambda: call(bad), '来源无效：')
            assert snapshot() == before, '非法来源不能修改或新增任何文件'
    for fn in [wc.configure, wc.execute, wc.submit, wc.abort, wc.pause, wc.resume, wc.rewind]:
        args = ('missing', {}) if fn is wc.submit else ('missing', 0) if fn is wc.rewind else ('missing',)
        raises(lambda: fn(*args, actor='乱写 的'), '来源无效：')
    check(True, '八个写接口优先拒绝非法、空、超长及不可编码来源，所有文件不变')


def test_deferred_actor(tmp):
    from unittest.mock import patch
    for actor in ['viewer', 'mcp:test']:
        for op in ['execute', 'submit']:
            c = client([REPLIES[0]])
            s = wc.start(demo_copy(tmp, 'deferred-' + op + actor.replace(':', '-')), client=c)
            run = s['run']
            with patch.object(wc, '_spawn') as spawn:
                if op == 'execute':
                    wc.execute(run, actor=actor)
                else:
                    wc.submit(run, REPLIES[0], wait=False, actor=actor)
                spawn.assert_called_once_with(ROOT / run)
            # 模拟后台稍后读取持久化控制文件；不依赖调用入口的内存参数。
            p = ROOT / run
            wc._advance(p, wc._load(wc._side(p, '.ctl')), client=c)
            e = task_events(run)[0]
            check(e['confirm'][0]['actor'] == actor and
                  (op != 'submit' or e['actor'] == actor), '延迟推进保留来源：' + op + '/' + actor)


def run():
    (ROOT / 'data/tmp').mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix='wfconfirm-', dir=ROOT / 'data/tmp'))
    try:
        for test in [test_legacy, test_matching, test_roles, test_validation, test_configure,
                     test_execute_note, test_execute_without_note, test_note_retry_pending,
                     test_execute_legacy_positional, test_execute_legacy_positional_with_keywords,
                     test_rewind_notes, test_note_validation, test_external_actor,
                     test_prune_notes_numeric_steps,
                     test_execute_string_encoding,
                     test_actor_validation, test_attempt_compatibility, test_prompt_layout,
                     test_settle_preserves_notes, test_legacy_agent_signature,
                     test_note_with_override, test_configure_during_execute,
                     test_all_write_actors, test_all_write_actor_validation, test_deferred_actor]:
            test(tmp)
        print('workflow confirm passed')
    finally:
        shutil.rmtree(tmp)


if __name__ == '__main__':
    run()
