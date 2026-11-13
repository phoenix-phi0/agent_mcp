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
        prompt = _prompt('原任务', '参考内容', '节点', fmt, submit, notes=notes, previous=None)
        check(prompt.index('参考文本') < prompt.index('补充说明') < prompt.index('1. 第一条'),
              '追加说明位于参考文本之后，保持列表顺序')
        check('2. 第二条' in prompt and 'ignored' not in prompt, 'previous 参数本阶段不使用')
        if not submit:
            check(prompt.index('2. 第二条') < prompt.index('只返回一个 JSON 对象'), '追加说明位于格式说明之前')


def test_p1_previous_layout(tmp):
    from verbs.workflow._agents import _prompt
    notes = [dict(text='第一条'), dict(text='第二条')]
    for fmt, submit in [(None, False), (('result', {'type': 'object'}), False),
                        (('result', {'type': 'object'}), True)]:
        prompt = _prompt('原任务', '参考内容', '节点', fmt, submit,
                         notes=notes, previous={'ignored': True})
        previous_block = ('上一次交的结果被打回，要按意见重做：\n'
                          '上一次的结果：{"ignored": true}\n')
        check(prompt.count(previous_block) == 1
              and prompt.index('2. 第二条') < prompt.index(previous_block),
              'previous 按设计 3.2 完整展示，位于追加说明之后')
        without_previous = _prompt('原任务', '参考内容', '节点', fmt, submit, notes=notes)
        check(without_previous == prompt.replace(previous_block, '')
              and '上一次交的结果被打回' not in without_previous
              and '上一次的结果：' not in without_previous,
              '没有 previous 时不出现上一次结果段落')
        actor_notes = [dict(note, actor='mcp:test') for note in notes]
        check(_prompt('原任务', '参考内容', '节点', fmt, submit,
                      notes=actor_notes, previous={'ignored': True}) == prompt,
              'actor 不进入提示词')
        if not submit:
            check(prompt.index(previous_block) < prompt.index('只返回一个 JSON 对象'),
                  '上一次结果位于格式说明之前')


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


def test_after_attempt_settings(tmp):
    demo = demo_copy(tmp, 'after-settings')
    s = wc.start(demo, confirm_after=['ARCHITECT'], max_attempts=3, client=client([]))
    run = s['run']
    check(s['confirm_after'] == ['ARCHITECT'] and s['max_attempts'] == 3,
          'start/status 保存结束后规则和尝试上限')
    cfg = wc._load(wc._side(ROOT / run, '.ctl'))
    check(cfg['confirm_after'] == ['ARCHITECT'] and cfg['max_attempts'] == 3
          and cfg['history'][0]['confirm_after'] == ['ARCHITECT']
          and cfg['history'][0]['max_attempts'] == 3, 'start 控制文件及 history 带新参数')
    s = wc.configure(run, confirm_after=['任务实现', 'ENGINEER*'], max_attempts=50)
    check(s['confirm_after'] == ['任务实现', 'ENGINEER*'] and s['max_attempts'] == 50,
          'configure 更新规则并接受上限 50')
    s = wc.configure(run, confirm_after=None, max_attempts=None)
    check(s['confirm_after'] == ['任务实现', 'ENGINEER*'] and s['max_attempts'] == 50,
          '两个新参数 None 均保持设置')
    s = wc.configure(run, confirm_after=[], max_attempts=1)
    check(s['confirm_after'] == [] and s['max_attempts'] == 1, '空列表清空规则并接受下限 1')
    cfg = wc._load(wc._side(ROOT / run, '.ctl'))
    check(cfg['history'][-1]['confirm_after'] == [] and cfg['history'][-1]['max_attempts'] == 1,
          'configure history 带新参数')
    s = wc.start(demo_copy(tmp, 'after-default'), client=client([]))
    check(s['confirm_after'] == [] and s['max_attempts'] == 4, '旧 start 调用写入缺省设置')
    cf = wc._side(ROOT / s['run'], '.ctl')
    cfg = wc._load(cf)
    check(cfg['confirm_after'] == [] and cfg['max_attempts'] == 4, '缺省值持久化')
    del cfg['confirm_after'], cfg['max_attempts']
    wc._dump(cf, cfg)
    before = cf.read_bytes()
    s = wc.status(s['run'])
    check(s['confirm_after'] == [] and s['max_attempts'] == 4 and cf.read_bytes() == before,
          '旧控制文件读取缺省值且不迁移')
    check(wc._rules({'confirm_after': ['QA']}, 'confirm_after') == ['QA']
          and wc._rules({}, 'confirm_after') == [], '_rules 支持完整字段名和旧文件')


def test_after_attempt_validation(tmp):
    demo = demo_copy(tmp, 'after-invalid')
    s = wc.start(demo, client=client([]))
    cf = wc._side(ROOT / s['run'], '.ctl')
    before = cf.read_bytes()
    for bad in [[''], ['a*b'], ['**'], ['a b'], ['../x'], ['x\n'], ['\ud800'],
                ['a' * 81], [3], [None], 'ARCHITECT', 3, {}]:
        raises(lambda: wc.start(demo, confirm_after=bad, client=client([])), '确认规则无效：')
        raises(lambda: wc.configure(s['run'], confirm_after=bad), '确认规则无效：')
        assert cf.read_bytes() == before
    for bad in [0, 'x', True, 99, False, -1, 1.0, '\ud800']:
        raises(lambda: wc.start(demo, max_attempts=bad, client=client([])), 'max_attempts 无效：')
        raises(lambda: wc.configure(s['run'], max_attempts=bad), 'max_attempts 无效：')
        assert cf.read_bytes() == before
    check(True, '新参数非法规则、类型、范围和代理字符均转为 ControlError，控制文件不变')
    valid = ['*', '任务·实现.一-*', 'a' * 80 + '*']
    check(wc.configure(s['run'], confirm_after=valid)['confirm_after'] == valid,
          '结束后规则沿用中文、通配和最长规则边界')


def test_rewind_confirm_state(tmp):
    c = client(REPLIES)
    s = wc.start(demo_copy(tmp, 'rewind-confirm-state'), client=c)
    s = wc.execute(s['run'], client=c)
    s = wc.execute(s['run'], client=c)
    cf = wc._side(ROOT / s['run'], '.ctl')
    cfg = wc._load(cf)
    for key in ['notes', 'after', 'revisions']:
        cfg[key] = {step: [dict(marker=step)] for step in ['10', '1', '3', '2']}
    cfg['item_controls'] = {'assignment': {'step': 3}}
    wc._dump(cf, cfg)
    wc.rewind(s['run'], 2, client=c)
    cfg = wc._load(cf)
    check(all(cfg[key] == {'1': [dict(marker='1')]} for key in ['notes', 'after', 'revisions']),
          'rewind 按数字清除 notes/after/revisions 当前及后续步，保留前序')
    check(cfg['item_controls'] == {}, 'rewind 到来源步之前清除该 record 的逐项设置')


def test_ctl_lock_l1(tmp):
    from concurrent.futures import ThreadPoolExecutor
    s = wc.start(demo_copy(tmp, 'lock-l1'), client=client([]))
    run = s['run']
    p = ROOT / run
    barrier = threading.Barrier(2)

    def update(card):
        barrier.wait(timeout=10)
        for i in range(20):
            # models 仍是整张替换；调用方的读改写与 configure 共用可重入锁。
            with wc._ctl_lock(run):
                models = wc._load(wc._side(p, '.ctl'))['models']
                models[card] = 'cli:claude/model-' + str(i)
                wc.configure(run, models=models)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(update, card) for card in ['ENGINEER', 'ARCHITECT']]
        for future in futures:
            future.result(timeout=20)
    cfg = wc._load(wc._side(p, '.ctl'))
    check(cfg['models'] == dict(ENGINEER='cli:claude/model-19', ARCHITECT='cli:claude/model-19')
          and sum(h['op'] == 'configure' for h in cfg['history']) == 40,
          'L1 两线程各 20 次 configure 不丢模型键和 history，锁内 configure 可重入')
    check(wc._side(p, '.ctl.lock').is_file(), 'L1 独立 .ctl.lock 文件不随控制文件替换')


def test_ctl_lock_process(tmp):
    import subprocess
    s = wc.start(demo_copy(tmp, 'lock-process'), client=client([]))
    p = ROOT / s['run']
    code = """
import fcntl
import sys
from tools import workflow_ctl as wc
p = sys.argv[1]
with wc._side(p, '.ctl.lock').open('a') as lock:
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print('blocked', flush=True)
    else:
        raise AssertionError('跨进程没有互斥')
wc.configure(p, max_attempts=7)
"""
    with wc._ctl_lock(p):
        proc = subprocess.Popen([sys.executable, '-c', code, str(p)], cwd=ROOT,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            import select
            assert select.select([proc.stdout], [], [], 10)[0], '子进程没有启动'
            assert proc.stdout.readline().strip() == 'blocked', '子进程未检测到父进程锁'
            wc.configure(s['run'], confirm_after=['QA'])
        except BaseException:
            proc.kill()
            proc.communicate()
            raise
    try:
        out, err = proc.communicate(timeout=10)
        assert proc.returncode == 0, out + err
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate()
    s = wc.status(p)
    check(s['confirm_after'] == ['QA'] and s['max_attempts'] == 7,
          '独立进程被锁阻塞，释放后 configure 读取最新设置，不丢更新')


def test_configure_entry_lock(tmp):
    from concurrent.futures import ThreadPoolExecutor
    s = wc.start(demo_copy(tmp, 'lock-entry'), client=client([]))
    barrier = threading.Barrier(2)

    def update(kw):
        barrier.wait(timeout=10)
        for _ in range(20):
            wc.configure(s['run'], **kw)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(update, kw) for kw in
                   [dict(confirm_after=['QA']), dict(max_attempts=7)]]
        for future in futures:
            future.result(timeout=20)
    cfg = wc._load(wc._side(ROOT / s['run'], '.ctl'))
    check(cfg['confirm_after'] == ['QA'] and cfg['max_attempts'] == 7 and len(cfg['history']) == 41,
          'configure 入口自行加锁，两线程独立设置各 20 次不丢字段或 history')


def test_p1_previous_absent(tmp):
    from verbs.workflow._agents import _prompt
    fmt = ('result', {'type': 'object'})
    check(_prompt('任务', '参考', '节点', fmt, False, previous=None) ==
          _prompt('任务', '参考', '节点', fmt, False), 'P1 缺省输出不变')


def test_p1_rejected_result(tmp):
    from verbs.workflow._agents import _prompt
    notes = [dict(kind='reject', text='旧意见'), dict(kind='add', text='补充'),
             dict(kind='reject', text='缺409错误码')]
    prompt = _prompt('任务', None, '节点', ('result', {}), False, notes, {'a': 1})
    check('1. 旧意见' in prompt and '3. 缺409错误码' in prompt, 'P1 保留全部说明')
    check('上一次交的结果被打回' in prompt and '打回意见：缺409错误码' in prompt
          and '上一次的结果：{"a": 1}' in prompt, 'P1 包含最新打回意见及结果')
    check(prompt.index('补充说明') < prompt.index('上一次交的结果') <
          prompt.index('按下面的 JSON Schema'), 'P1 段落顺序')
    no_reject = _prompt('任务', None, previous={'a': 1}, notes=[dict(kind='add', text='补充')])
    check('打回意见：' not in no_reject, 'P1 无打回意见时省略该行')


def test_p1_previous_truncated(tmp):
    from verbs.workflow._agents import _prompt
    serialized = json.dumps({'值': '中' * 20000}, ensure_ascii=False)
    prompt = _prompt('任务', None, previous={'值': '中' * 20000})
    result = prompt.split('上一次的结果：', 1)[1].split('\n', 1)[0]
    check(result == serialized[:20000] + '…（已截断）', 'P1 序列化结果截断到 20000 字')


def test_p1_describe(tmp):
    from unittest.mock import patch
    from verbs.workflow import _agents
    profile = dict(model='test', system='system')
    with patch.object(_agents, 'load_agent', return_value=profile):
        prompt = _agents.describe(None, 'role', '任务', fmt=('result', {}),
                                  notes=[dict(kind='reject', text='缺409错误码')],
                                  previous={'a': 1})['prompt']
    check('打回意见：缺409错误码' in prompt and '上一次的结果：{"a": 1}' in prompt,
          'P1 describe 透传说明和结果')


def write_verdict(run, action, attempt=1, note='缺 409 错误码', result=None, **overrides):
    """第 4 项接口尚未实现：按设计直接持久化裁决。"""
    p = ROOT / run
    with wc._ctl_lock(p):
        cf = wc._side(p, '.ctl')
        cfg = wc._load(cf)
        verdict = dict(action=action, attempt=attempt, actor='viewer', at='2026-11-13T12:00:00',
                       role=None, model=None)
        verdict.update(overrides)
        cfg.setdefault('after', {})['1'] = verdict
        if action == 'reject':
            cfg.setdefault('notes', {}).setdefault('1', []).append(
                dict(kind='reject', text=note, attempt=attempt,
                     actor=verdict['actor'], at=verdict['at']))
        if result is not None:
            revisions = cfg.setdefault('revisions', {}).setdefault('1', [])
            revisions.append(dict(rev=len(revisions) + 1, kind='approve', attempt=attempt,
                                  result=result, actor=verdict['actor'], at=verdict['at']))
        wc._dump(cf, cfg)
    return verdict


def start_review(tmp, name, replies=None, **kw):
    c = client([REPLIES[0]] if replies is None else replies)
    s = wc.start(demo_copy(tmp, name), mode='auto', confirm_after=['ARCHITECT'], client=c, **kw)
    return s, c


def advance_only(run, c, **kw):
    p = ROOT / run
    wc._advance(p, wc._load(wc._side(p, '.ctl')), client=c, **kw)
    return wc.status(run, detail=True)


def test_after_review_hold(tmp):
    s, c = start_review(tmp, 'review-hold', max_attempts=7)
    p = wc.status(s['run'], detail=True)['pending']
    check(s['status'] == 'waiting' and p['phase'] == 'after' and p['result'] == REPLIES[0]
          and p['attempt'] == 1 and p['max_attempts'] == 7 and p['reason'] == 'rule:ARCHITECT'
          and p['notes'] == [] and p['format'] == 'contract' and p['schema'],
          '结束后 pending 带结果、次数、上限、规则、说明和格式')
    events = task_events(s['run'])
    check(len(c.calls) == 1 and len(events) == 1 and events[0]['status'] == 'review'
          and events[0]['result'] == REPLIES[0] and events[0]['attempt'] == 1,
          '只调用一次，只记录 review，不添加 waiting 事件')
    s = wc.resume(s['run'], client=c)
    check(task_events(s['run']) == events and len(c.calls) == 1 and s['pending']['phase'] == 'after',
          '无裁决 hold 原样保留事件，不重调模型')


def test_after_approve_release(tmp):
    s, c = start_review(tmp, 'approve-release')
    run = s['run']
    before = task_events(run)[0]
    wc.configure(run, confirm_before=['ARCHITECT_GLM'])
    verdict = write_verdict(run, 'approve')
    s = wc.resume(run, client=c)
    e = task_events(run)[0]
    check(s['pending']['step'] == 2 and s['pending']['phase'] == 'before' and len(c.calls) == 1,
          'approve 放行后在下游开始前停，不多调模型')
    check(e['status'] == 'ok' and e['result'] == before['result']
          and e['confirm'][-1] == dict(phase='after', action='approve', revised=False,
                                      actor=verdict['actor'], at=verdict['at']),
          'release 写 ok 并追加精确的 after/approve 确认')
    wc.resume(run, client=c)
    check(task_events(run)[0] == e and len(c.calls) == 1, '重复回放不重复确认')


def test_after_revised_approve(tmp):
    from wf_fixtures import contract
    changed = contract('人工修订后的接口约定')
    s, c = start_review(tmp, 'revised-approve', [REPLIES[0], REPLIES[1]])
    run = s['run']
    wc.configure(run, confirm_before=['接口修改'])
    write_verdict(run, 'approve', result=changed)
    s = wc.resume(run, client=c)
    e = task_events(run)[0]
    check(len(c.calls) == 2 and '人工修订后的接口约定' in c.calls[1]['prompt']
          and e['status'] == 'ok' and e['result'] == changed and e['result_model'] == REPLIES[0]
          and len(e['revisions']) == 1 and e['confirm'][-1]['revised'] is True,
          '改后放行：下游实际提示词用修订结果，事件保留模型原结果')
    wc.configure(run, confirm_before=['*'])
    wc.resume(run, client=c)
    check(task_events(run)[0] == e and len(c.calls) == 2, '已应用的修订不会再次追加')


def test_after_reject_retry(tmp):
    s, c = start_review(tmp, 'reject-retry', [REPLIES[0], REPLIES[0]])
    run = s['run']
    original = task_events(run)[0]
    verdict = write_verdict(run, 'reject')
    s = wc.resume(run, client=c)
    events = task_events(run)
    check([e['status'] for e in events] == ['rejected', 'review']
          and [e['attempt'] for e in events] == [1, 2] and s['pending']['attempt'] == 2,
          '打回保留原尝试，第二次结束后等待确认')
    check(events[0]['result'] == original['result'] and events[0]['reject'] ==
          dict(text='缺 409 错误码', actor='viewer', at=verdict['at'], next_role=None, next_model=None)
          and events[0]['confirm'][-1]['action'] == 'reject', 'rejected 保留结果、意见和裁决来源')
    check(len(c.calls) == 2 and '打回意见：缺 409 错误码' in c.calls[1]['prompt']
          and '上一次的结果：' + json.dumps(REPLIES[0], ensure_ascii=False) in c.calls[1]['prompt']
          and events[1]['task'] == original['task'] and events[1]['notes'][0]['kind'] == 'reject',
          '打回重跑带意见和上次结果，任务原文不变，事件记说明')
    all_events = wc._load(ROOT / run)['events']
    check([e['seq'] for e in all_events] == list(range(1, len(all_events) + 1)), '打回回放 seq 连续')
    wc.configure(run, confirm_before=['ARCHITECT_GLM'])
    write_verdict(run, 'approve', attempt=2)
    s = wc.resume(run, client=c)
    check([e['status'] for e in task_events(run)] == ['rejected', 'ok', 'waiting']
          and len(c.calls) == 2 and s['pending']['step'] == 2, '重试通过不丢 rejected，也不多调模型')


def test_after_reject_error_retry(tmp):
    s, c = start_review(tmp, 'reject-error', [REPLIES[0], '不是 JSON', REPLIES[0]])
    run = s['run']
    write_verdict(run, 'reject')
    s = wc.resume(run, client=c)
    check(s['pending']['phase'] == 'before' and s['pending']['attempt'] == 3
          and s['pending']['reason'] == 'error' and '没有返回 JSON' in s['pending']['last_error']
          and [e['status'] for e in task_events(run)] == ['rejected', 'error', 'waiting'],
          '用例16：打回重跑失败，回到开始前并保留 rejected/error')
    s = wc.execute(run, client=c)
    events = task_events(run)
    check(s['pending']['phase'] == 'after' and s['pending']['attempt'] == 3
          and [e['attempt'] for e in events] == [1, 2, 3]
          and [e['status'] for e in events] == ['rejected', 'error', 'review']
          and len(c.calls) == 3 and '缺 409 错误码' in c.calls[2]['prompt'],
          '用例16：execute 重试次数包含 error 和 rejected，说明继续保留')


def test_after_abort_resume(tmp):
    s, c = start_review(tmp, 'review-abort')
    before = task_events(s['run'])
    s = wc.abort(s['run'])
    check(s['status'] == 'aborted' and task_events(s['run']) == before, '用例17：abort 不动 review')
    s = wc.resume(s['run'], client=c)
    check(s['pending']['phase'] == 'after' and s['pending']['result'] == REPLIES[0]
          and task_events(s['run']) == before and len(c.calls) == 1, '用例17：resume 回到原确认，不重调模型')


def test_after_cost_spent(tmp):
    s, c = start_review(tmp, 'review-cost', [REPLIES[0], REPLIES[0]])
    run = s['run']
    cost = task_events(run)[0]['cost']
    check(cost > 0 and wc._load(ROOT / run)['cost_spent'] == cost, '用例20：review 计入成本')
    write_verdict(run, 'reject')
    wc.resume(run, client=c)
    check(wc._load(ROOT / run)['cost_spent'] == 2 * cost, '用例20：rejected 和新 review 均计入成本')
    wc.configure(run, confirm_before=['ARCHITECT_GLM'])
    write_verdict(run, 'approve', attempt=2)
    wc.resume(run, client=c)
    wc.resume(run, client=c)
    check(wc._load(ROOT / run)['cost_spent'] == 2 * cost and len(c.calls) == 2,
          '用例20：通过及再次回放不重复计算成本')


def test_after_decision_order(tmp):
    req = dict(step=1, line=1, name='任务实现', role='ENGINEER', task='原文')
    event = dict(type='task', **req, status='review', attempt=1, result={'ok': True})
    cfg = dict(mode='auto', confirm_before=['*'], confirm_after=['*'], max_attempts=3,
               submitted={'1': {'external': True}}, go={'1': {'attempt': 1}},
               after={'1': dict(action='approve', attempt=1, actor='viewer', at='now')})
    ctl = wc._Control(cfg, orders=False)
    ctl.held[1] = event
    d = ctl.decide(req)
    check(d['action'] == 'hold' and d['attempt'] == 1 and d['max_attempts'] == 3,
          'held 优先于 orders=False、submitted、go 和规则；恢复不消费裁决')
    ctl.orders = True
    cfg['after']['1']['attempt'] = 2
    check(ctl.decide(req)['action'] == 'hold', '过期或提前的裁决不放行')
    cfg['after']['1']['attempt'] = 1
    check(ctl.decide(req)['action'] == 'release', '匹配的 approve 优先于 submitted/go')
    ctl.replay[1] = dict(event, status='ok')
    check(ctl.decide(req)['action'] == 'replay', 'ok 回放优先于 held')
    for field, value in [('line', 2), ('name', '改名'), ('role', 'OTHER'), ('task', '修改原文')]:
        raises(lambda: ctl.decide({**req, field: value}), '回放对不上')
    check(ctl.replay[1]['result'] == {'ok': True} and ctl.held[1] == event,
          '四元组核对失败时原事件不变')
    ctl.replay.clear()
    ctl.held.clear()
    ctl.orders = False
    check(ctl.decide(req)['action'] == 'wait', '无 held 时 orders=False 优先于提交')
    ctl.orders = True
    d = ctl.decide(req)
    check(d['action'] == 'result' and not d['after'] and d['carry'] == d['failed'] == [],
          '外部结果优先于 go 和规则且不带结束后确认')


def test_after_replay_revisions(tmp):
    req = dict(step=1, line=1, name='任务实现', role='ENGINEER', task='原文')
    original = {'version': 0}
    r1 = dict(rev=1, result={'version': 1})
    r2 = dict(rev=2, result={'version': 2})
    ctl = wc._Control(dict(revisions={'1': [r1, r2]}))
    old = dict(req, status='ok', result=r1['result'], result_model=original, revisions=[r1])
    ctl.replay[1] = old
    d = ctl.decide(req)
    check(d['result'] == r2['result'] and d['revise'] == dict(result_model=original, revisions=[r1, r2])
          and old['result'] == r1['result'] and old['revisions'] == [r1],
          '只应用更高 rev，保留最初模型结果，决策不修改历史事件')
    ctl.replay[1] = {**old, 'result': d['result'], **d['revise']}
    check(ctl.decide(req)['revise'] is None, '所有修订已经应用时不重复写入')
    # 引擎 replay 必须 store 改后值，验证后继 describe 的真实参考文本。
    from wf_fixtures import contract
    c = client([REPLIES[0]])
    s = wc.start(demo_copy(tmp, 'replay-revision'), client=c)
    wc.execute(s['run'], client=c)
    write_verdict(s['run'], 'approve', result=contract('回放后新约定'))
    s = advance_only(s['run'], c, orders=False)
    check('回放后新约定' in s['pending']['prompt'] and len(c.calls) == 1
          and task_events(s['run'])[0]['result_model'] == REPLIES[0], 'replay store 使用修订后结果')


def test_after_interrupted_reject(tmp):
    s, c = start_review(tmp, 'interrupted-reject', [REPLIES[0], REPLIES[0]])
    run = s['run']
    write_verdict(run, 'reject', role='ARCHITECT_GLM', model='cli:goose/glm-5.3')
    p = ROOT / run
    cfg = wc._load(wc._side(p, '.ctl'))
    ctl = wc._Control(cfg, p)
    req = {k: task_events(run)[0][k] for k in ['step', 'line', 'name', 'role', 'task']}
    d = ctl.decide(req)
    # 模拟 rejected 已落盘、下一次调用尚未开始时进程终止。
    t = wc._load(p)
    t.update(status='running', events=d['carry'])
    t.pop('pending', None)
    wc._dump(p, t)
    wc.configure(run, confirm_before=['*'], confirm_after=['ARCHITECT_GLM'])
    s = wc.resume(run, client=c)
    e = task_events(run)[1]
    check(len(c.calls) == 2 and s['pending']['phase'] == 'after' and s['pending']['attempt'] == 2
          and e['source'] == 'reject' and e['role'] == 'ARCHITECT_GLM'
          and e['default_role'] == 'ARCHITECT' and e['model_override'] == 'cli:goose/glm-5.3'
          and '上一次的结果：' in c.calls[1]['prompt'],
          '未消耗 reject 优先于开始前规则，恢复换卡换模型及 previous，按换后卡结束确认')


def test_after_rules_and_external(tmp):
    check(not decision([], mode='step')['after'], 'step 不自动带结束后确认')
    for rule in ['ENGINEER', 'ENGINEER*', '任务实现', '*', 'ENGINEER_SENIOR']:
        d = decision([], confirm_after=[rule], roles={'ENGINEER': 'ENGINEER_SENIOR'})
        check(d['after'] and d['reason'] == 'rule:' + rule, 'after 匹配原卡、换后卡、节点和通配：' + rule)
    check(not decision([], confirm_after=['QA'])['after'], '未命中 after 时不确认')
    s = wc.start(demo_copy(tmp, 'external-no-after'), confirm_after=['*'], client=client([]))
    s = wc.submit(s['run'], REPLIES[0], client=client([]))
    check(s['pending']['phase'] == 'before' and s['pending']['step'] == 2
          and task_events(s['run'])[0]['status'] == 'ok', '外部 submit 结果不走结束后确认')


def test_after_before_and_step(tmp):
    c = client([REPLIES[0]])
    s = wc.start(demo_copy(tmp, 'both-confirm'), mode='auto', confirm_before=['ARCHITECT'],
                 confirm_after=['ARCHITECT'], client=c)
    check(s['pending']['phase'] == 'before' and not c.calls, '同一角色前后都开时先停开始前')
    s = wc.execute(s['run'], note='保留说明和授权', actor='viewer', client=c)
    before = task_events(s['run'])[0]
    check(s['pending']['phase'] == 'after' and before['notes'][0]['text'] == '保留说明和授权'
          and [a['action'] for a in before['confirm']] == ['note', 'run'], 'execute 后停结束后并保留前置确认')
    wc.configure(s['run'], confirm_before=['ARCHITECT_GLM'])
    write_verdict(s['run'], 'approve')
    wc.resume(s['run'], client=c)
    check(task_events(s['run'])[0]['confirm'][:-1] == before['confirm'], 'release 追加确认，保留 before 历史')
    c2 = client([REPLIES[0]])
    s2 = wc.start(demo_copy(tmp, 'step-no-after'), client=c2)
    s2 = wc.execute(s2['run'], client=c2)
    check(task_events(s2['run'])[0]['status'] == 'ok' and s2['pending']['step'] == 2
          and s2['pending']['phase'] == 'before', 'step 模式本身只带开始前确认')


def test_after_no_store_until_release(tmp):
    from tools.dsl import DSLEngine
    from verbs.workflow import _agents, _workflow
    demo = demo_copy(tmp, 'no-store')
    c = client([REPLIES[0]])
    engine = DSLEngine(client=c, workdir=demo, verbose=False)
    engine.vars.update(project='test', content='固定任务')
    engine._wf_control = wc._Control(dict(mode='auto', confirm_after=['ARCHITECT']))
    script = '接口约定\n    角色 ARCHITECT\n    任务 {content}\n    格式 contract\n    记录 result\n'
    try:
        _workflow.run(engine, script, _agents.call_agent, describe=_agents.describe,
                      load_format=_agents.load_format, check_format=_agents.check_format)
    except wc.WorkflowPause:
        pass
    else:
        raise AssertionError('应当停在结束后')
    trace = wc._load(engine.vars['workflow_trace'])
    check(engine.lookup('result') is None and trace['pending']['result'] == REPLIES[0]
          and len(c.calls) == 1, 'review 结果只留在 trace/pending，不写入引擎变量')


def test_after_sort_and_rewind(tmp):
    req = dict(step=1, line=1, name='任务实现', role='ENGINEER', task='原文')
    events = [dict(type='task', **req, status=status, attempt=i, result={'i': i})
              for i, status in enumerate(['error', 'rejected', 'review', 'review'], 1)]
    p = tmp / 'sorting.json'
    wc._dump(p, dict(events=events + [dict(type='cost', step=1, status='ok')]))
    ctl = wc._Control({}, p)
    check(ctl.carry[1] == events[:2] and ctl.held[1] == events[3] and not ctl.replay
          and ctl.failed is ctl.carry, '__init__ 按状态分拣，held 取最后一条，兼容 failed')
    d = ctl.decide(req)
    check(d['action'] == 'hold' and d['attempt'] == 4 and d['max_attempts'] == 4
          and d['carry'] == d['failed'] == events[:2], 'hold 使用 held 的 attempt 并返回全部 carry')
    ctl = wc._Control({}, p, rewind=1)
    check(not ctl.carry and not ctl.held and not ctl.replay, 'rewind 截断 review/rejected/error 全部状态')


def test_after_configure_during_run(tmp):
    from concurrent.futures import ThreadPoolExecutor
    entered, release = threading.Event(), threading.Event()
    c = client(REPLIES[:2])
    original = c.chat_messages

    def blocked(messages, **kw):
        if not c.calls:
            entered.set()
            assert release.wait(10), '没有释放模型'
        return original(messages, **kw)

    c.chat_messages = blocked
    s = wc.start(demo_copy(tmp, 'concurrent-after'), client=c)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(wc.resume, s['run'], client=c)
        try:
            assert entered.wait(10), '第一步未开始'
            wc.configure(s['run'], confirm_after=['ARCHITECT_GLM'])
        finally:
            release.set()
        s = future.result(timeout=10)
    events = task_events(s['run'])
    check(len(c.calls) == 2 and [e['status'] for e in events] == ['ok', 'review']
          and s['pending']['step'] == 2 and s['pending']['phase'] == 'after',
          'Event 确定交错：第一步执行中改 after，下一步读取新规则且各调一次')


def test_after_unsorted_revisions(tmp):
    req = dict(step=1, line=1, name='任务实现', role='ENGINEER', task='原文')
    original = {'version': 0}
    revisions = [dict(rev=i, result={'version': i}) for i in [3, 1, 2]]
    ctl = wc._Control(dict(revisions={'1': revisions}))
    ctl.replay[1] = dict(req, status='ok', result=original)
    d = ctl.decide(req)
    check(d['result'] == {'version': 3}
          and [r['rev'] for r in d['revise']['revisions']] == [1, 2, 3]
          and d['revise']['result_model'] == original,
          '控制文件修订无序时按 rev 应用，最终取最大修订号')
    check([r['rev'] for r in revisions] == [3, 1, 2], '修订排序不修改控制文件中的列表')


def test_after_attempt_limit_manual_retry(tmp):
    c = client(['不是 JSON', REPLIES[0]])
    s = wc.start(demo_copy(tmp, 'manual-over-limit'), mode='auto',
                 confirm_after=['ARCHITECT'], max_attempts=1, client=c)
    check(s['pending']['phase'] == 'before' and s['pending']['attempt'] == 2
          and s['pending']['max_attempts'] == 1, '失败后次数递增，上限仍在 pending 中')
    s = wc.execute(s['run'], client=c)
    check(s['pending']['phase'] == 'after' and s['pending']['attempt'] == 2
          and [e['status'] for e in task_events(s['run'])] == ['error', 'review']
          and len(c.calls) == 2, 'max_attempts 不阻止人工 execute 失败重试')



def test_api_phase(tmp):
    s, c = start_review(tmp, 'api-phase')
    run = s['run']
    for call in [lambda: wc.execute(run, model='bad', client=c),
                 lambda: wc.submit(run, 'bad', client=c)]:
        raises(call, '这一步在等结束后确认，用 approve / reject')
    raises(lambda: wc.approve(run, step=2, client=c), '现在停在第 1 步')
    wc.configure(run, confirm_before=['*'])
    s = wc.approve(run, actor='mcp:test', client=c)
    e = task_events(run)[0]
    check(e['status'] == 'ok' and e['confirm'][-1]['phase'] == 'after'
          and e['confirm'][-1]['action'] == 'approve' and e['confirm'][-1]['actor'] == 'mcp:test'
          and len(c.calls) == 1, '用例9：公共 approve 放行不多调模型')
    check(s['steps'][0]['revised'] is False and 'actor' in s['steps'][0], '摘要有 revised 和 actor')
    check(s['steps'][0]['actor'] == 'mcp:test', 'after 确认摘要来源与 approve 传入 actor 一致')
    for call in [lambda: wc.approve(run, result='bad', attempt=999, client=c),
                 lambda: wc.reject(run, '', attempt=999, client=c)]:
        raises(call, '这一步在等开始前确认，用 execute / submit')


def test_status_after_actor(tmp):
    for actor in ['viewer', 'mcp:test', 'workflow_ctl']:
        c = client([REPLIES[0]])
        s = wc.start(demo_copy(tmp, 'status-after-' + actor.replace(':', '-')),
                     confirm_after=['ARCHITECT'], client=c)
        run = s['run']
        s = wc.execute(run, actor='viewer', client=c)
        e = task_events(run)[0]
        check('actor' not in e and 'actor' not in s['steps'][0]
              and e['confirm'][-1]['phase'] == 'before',
              '普通 before 模型事件及摘要仍不补 actor：' + actor)
        s = wc.approve(run, actor=actor, client=c)
        e = task_events(run)[0]
        check('actor' not in e and e['confirm'][-1]['phase'] == 'after'
              and e['confirm'][-1]['actor'] == s['steps'][0]['actor'] == actor,
              '摘要只从 after 确认取准确来源，不取 before 来源：' + actor)
        p = ROOT / run
        before = p.read_bytes()
        check(wc.status(run, detail=True)['steps'][0]['actor'] == actor
              and p.read_bytes() == before, 'detail 摘要同样带来源，读取不改事件')


def test_api_revision(tmp):
    from wf_fixtures import contract
    s, c = start_review(tmp, 'api-revision', [REPLIES[0], REPLIES[1]])
    run = s['run']
    p = ROOT / run
    cf = wc._side(p, '.ctl')
    before = (p.read_bytes(), cf.read_bytes())
    for bad, message in [({'bad': True}, '结果不符合格式 contract：'),
                         ('bad', '结果不是 JSON'), ([], '结果必须是 JSON 对象'),
                         (contract('\ud800'), '有效的 UTF-8')]:
        raises(lambda: wc.approve(run, result=bad, client=c), message)
        check(before == (p.read_bytes(), cf.read_bytes()), '用例10：错误结果不写记录或控制文件')
    wc.configure(run, confirm_before=['接口修改'])
    changed = contract('公共接口改后的约定')
    s = wc.approve(run, result=json.dumps(changed), note='确认修订', actor='viewer', client=c)
    e = task_events(run)[0]
    r = e['revisions'][0]
    check(e['result'] == changed and e['result_model'] == REPLIES[0]
          and len(e['revisions']) == 1 and r['rev'] == 1 and r['kind'] == 'approve'
          and r['attempt'] == 1 and r['actor'] == 'viewer' and r['note'] == '确认修订'
          and r['at'] and s['steps'][0]['revised'] is True
          and '公共接口改后的约定' in c.calls[1]['prompt'], '用例10：修订保存全部字段并进入下游提示词')
    s = wc.rewind(run, 1, client=c)
    cfg = wc._load(cf)
    check(s['pending']['phase'] == 'before' and all(not cfg.get(k) for k in ['revisions', 'after', 'notes']),
          '用例19：rewind 清理修订、裁决、说明并停在开始前')


def _approve_json_type_boundary(tmp, name, original_value, changed_value, revised):
    from wf_fixtures import contract
    original = contract('JSON 类型边界')
    original['contract']['interfaces'][0]['input']['qa_type_boundary'] = original_value
    changed = json.loads(json.dumps(original))
    changed['contract']['interfaces'][0]['input']['qa_type_boundary'] = changed_value
    # 调换对象键顺序不构成修订。
    changed['contract'] = dict(reversed(list(changed['contract'].items())))
    s, c = start_review(tmp, name, [original, REPLIES[1]])
    run = s['run']
    wc.configure(run, confirm_before=['接口修改'])
    s = wc.approve(run, result=changed, actor='viewer', client=c)
    e = task_events(run)[0]

    def boundary(result):
        return result['contract']['interfaces'][0]['input']['qa_type_boundary']

    def leaf(value):
        return value[0]['nested'][0] if isinstance(value, list) else value

    final = leaf(boundary(e['result']))
    expected = leaf(changed_value)
    check(type(final) is type(expected) and final == expected and e['status'] == 'ok',
          name + '：放行结果保留修改值及 JSON 类型')
    check(e['confirm'][-1]['action'] == 'approve'
          and e['confirm'][-1]['revised'] is revised and s['steps'][0]['revised'] is revised,
          name + '：确认记录和摘要准确标记 revised')
    cfg = wc._load(wc._side(ROOT / run, '.ctl'))
    if revised:
        model_value = leaf(boundary(e['result_model']))
        check(type(model_value) is bool and model_value is leaf(original_value)
              and json.dumps(e['result_model'], sort_keys=True) == json.dumps(original, sort_keys=True),
              name + '：result_model 完整保留原布尔结果')
        revisions = e['revisions']
        check(len(revisions) == 1 and revisions[0]['kind'] == 'approve'
              and revisions[0]['rev'] == 1 and revisions[0]['attempt'] == 1
              and revisions[0]['actor'] == 'viewer'
              and type(leaf(boundary(revisions[0]['result']))) is int
              and leaf(boundary(revisions[0]['result'])) == expected
              and cfg['revisions']['1'] == revisions,
              name + '：事件和控制文件新增 approve 修订并保存数字值')
    else:
        check(not e.get('revisions') and 'result_model' not in e
              and not cfg.get('revisions', {}).get('1'),
              name + '：相同结果不生成修订或 result_model')
    context = c.calls[1]['prompt'].split('参考文本：', 1)[1].split('\n', 1)[0]
    downstream = leaf(boundary(json.loads(context)))
    check(len(c.calls) == 2 and s['pending']['step'] == 3
          and type(downstream) is type(expected) and downstream == expected,
          name + '：下游实际提示词使用放行值及其类型')


def test_api_approve_true_to_one(tmp):
    _approve_json_type_boundary(tmp, 'approve-true-to-one', True, 1, True)


def test_api_approve_nested_false_to_zero(tmp):
    _approve_json_type_boundary(tmp, 'approve-false-to-zero',
                                [{'nested': [False]}], [{'nested': [0]}], True)


def test_api_approve_identical_json(tmp):
    _approve_json_type_boundary(tmp, 'approve-identical-json',
                                [{'nested': [False]}], [{'nested': [False]}], False)


def test_api_reject(tmp):
    s, c = start_review(tmp, 'api-reject', [REPLIES[0], REPLIES[0]])
    run = s['run']
    s = wc.reject(run, '补充边界错误码', actor='viewer', client=c)
    events = task_events(run)
    check([e['status'] for e in events] == ['rejected', 'review']
          and events[0]['reject']['text'] == '补充边界错误码' and events[0]['reject']['actor'] == 'viewer'
          and s['pending']['attempt'] == 2 and '补充边界错误码' in c.calls[1]['prompt']
          and json.dumps(REPLIES[0], ensure_ascii=False) in c.calls[1]['prompt'],
          '用例11：公共 reject 保存打回并带意见和旧结果重跑')
    raises(lambda: wc.approve(run, attempt=1, result='bad', client=c),
           '结果已经换了（现在是第 2 次），刷新后再确认')
    raises(lambda: wc.reject(run, '', attempt=1, client=c), '结果已经换了（现在是第 2 次）')
    wc.configure(run, confirm_before=['*'])
    wc.approve(run, attempt=2, client=c)
    events = wc._load(ROOT / run)['events']
    check([e['seq'] for e in events] == list(range(1, len(events) + 1)) and len(c.calls) == 2,
          '用例11/14：第二次通过后 seq 连续且不多调模型')


def test_api_reject_override(tmp):
    s, c = start_review(tmp, 'api-override', [REPLIES[0], REPLIES[0]])
    wc.configure(s['run'], confirm_after=['*'])
    s = wc.reject(s['run'], '换卡重做', role='ARCHITECT_GLM', model='cli:goose/glm-5.3', client=c)
    e = task_events(s['run'])[-1]
    check(e['role'] == 'ARCHITECT_GLM' and e['default_role'] == 'ARCHITECT'
          and e['model_override'] == 'cli:goose/glm-5.3' and e['source'] == 'reject',
          '用例12：reject 换卡、默认角色和模型覆盖正确')


def test_api_limit(tmp):
    for increase in [False, True]:
        s, c = start_review(tmp, 'api-limit-' + str(increase), [REPLIES[0]] * 3, max_attempts=2)
        run = s['run']
        wc.reject(run, '再试', client=c)
        raises(lambda: wc.reject(run, '再试', client=c),
               '第 1 步已经跑了 2 次（上限 2），不能再打回：可以改了再通过，或者 configure(max_attempts=…) 调高')
        if increase:
            wc.configure(run, max_attempts=3)
            s = wc.reject(run, '第三次', client=c)
            check(s['pending']['attempt'] == 3, '用例13：调高上限后可再打回')
        else:
            wc.configure(run, confirm_before=['*'])
            s = wc.approve(run, result=REPLIES[0], client=c)
            check('revisions' not in task_events(run)[-2] and s['pending']['phase'] == 'before',
                  '用例13：到上限仍可 approve，相同结果不追加修订')


def test_api_validation(tmp):
    s, c = start_review(tmp, 'api-validation', [REPLIES[0]] * 2)
    run = s['run']
    for bad in [None, '', '  ', 3]:
        raises(lambda: wc.reject(run, bad, client=c), '打回要写意见')
    raises(lambda: wc.reject(run, '字' * 4001, client=c), '说明最多 4000 字')
    raises(lambda: wc.reject(run, '\ud800', client=c), '有效的 UTF-8')
    raises(lambda: wc.approve(run, note='\ud800', client=c), '有效的 UTF-8')
    raises(lambda: wc.reject(run, '意见', model='bad', client=c), '模型名无效')
    raises(lambda: wc.reject(run, '意见', role='../bad', client=c), '角色卡名无效')
    for call in [lambda: wc.approve(run, actor='乱写 的', client=c),
                 lambda: wc.reject(run, '意见', actor='乱写 的', client=c)]:
        raises(call, '来源无效')
    wc.reject(run, '字' * 4000, client=c)
    cfg = wc._load(wc._side(ROOT / run, '.ctl'))
    check(len(cfg['notes']['1'][0]['text']) == 4000 and cfg['history'][-1]['op'] == 'reject',
          '4000 字边界成功且 history 记录 reject')



def _reject_invalid_role(tmp, role, name):
    s, c = start_review(tmp, name, [REPLIES[0]])
    run = s['run']
    p = ROOT / run
    cf = wc._side(p, '.ctl')
    record_before, control_before = p.read_bytes(), cf.read_bytes()
    calls_before = len(c.calls)
    try:
        wc.reject(run, '请重做', role=role, client=c)
    except wc.ControlError as error:
        check(str(error) == f'角色卡名无效：{role}', '非法 role 统一为 ControlError 和指定文案')
    else:
        raise AssertionError('非法 role 必须拒绝')
    check(p.read_bytes() == record_before and cf.read_bytes() == control_before,
          '非法 role 不改记录、裁决、notes 或 history')
    check(len(c.calls) == calls_before, '非法 role 不调用模型')


def test_api_reject_role_integer(tmp):
    _reject_invalid_role(tmp, 3, 'reject-role-integer')


def test_api_reject_role_list(tmp):
    _reject_invalid_role(tmp, [], 'reject-role-list')


def test_api_reject_role_dict(tmp):
    _reject_invalid_role(tmp, {}, 'reject-role-dict')


def test_api_both_phases(tmp):
    c = client([REPLIES[0]])
    s = wc.start(demo_copy(tmp, 'api-both'), mode='auto', confirm_before=['*'],
                 confirm_after=['*'], client=c)
    run = s['run']
    raises(lambda: wc.approve(run, client=c), '这一步在等开始前确认，用 execute / submit')
    s = wc.execute(run, client=c)
    check(s['pending']['phase'] == 'after' and s['pending']['step'] == 1, '用例15：execute 后停结束后')
    s = wc.approve(run, client=c)
    check(s['pending']['phase'] == 'before' and s['pending']['step'] == 2, '用例15：approve 后才往下')


def test_api_interrupted(tmp):
    s, c = start_review(tmp, 'api-interrupted')
    run = s['run']
    p = ROOT / run
    cf = wc._side(p, '.ctl')
    t, cfg = wc._load(p), wc._load(cf)
    t['status'], cfg['worker'] = 'running', 999999999
    wc._dump(p, t)
    wc._dump(cf, cfg)
    check(wc.status(run)['status'] == 'interrupted', '用例18：失效 worker 显示 interrupted')
    wc.configure(run, confirm_before=['*'])
    s = wc.approve(run, client=c)
    check(task_events(run)[0]['status'] == 'ok' and len(c.calls) == 1, '用例18：恢复后 approve 不重跑')


def test_cost_summary(tmp):
    from tools.wf_plan import cost_summary

    costs = {'ENGINEER_LITE': 1, 'ENGINEER': 3, 'ENGINEER_SENIOR': 8, 'TEST_ENGINEER': 2}
    items = [{'agent': role, 'content': f'【第{i}项】做第{i}件事'}
             for i, role in enumerate(('ENGINEER_LITE', 'ENGINEER', 'ENGINEER'), 1)]
    rows = [{'index': i, 'agent': item['agent'], 'cost': costs[item['agent']], 'content': item['content']}
            for i, item in enumerate(items, 1)]
    allowed = ['ENGINEER_LITE', 'ENGINEER', 'ENGINEER_SENIOR']
    check(cost_summary(items, 7, allowed, costs.__getitem__) ==
          {'total': 7, 'budget': 7, 'tasks': rows, 'status': '未超出'}, '成本合计等于预算未超出')
    over = [{'agent': 'ENGINEER_SENIOR', 'content': items[0]['content']}, *items[1:]]
    over_rows = [{'index': 1, 'agent': 'ENGINEER_SENIOR', 'cost': 8, 'content': items[0]['content']}, *rows[1:]]
    check(cost_summary(over, 7, allowed, costs.__getitem__) ==
          {'total': 14, 'budget': 7, 'tasks': over_rows, 'status': '超出'}, '成本合计超预算')
    outside = [{'agent': 'TEST_ENGINEER', 'content': '甲'}, {'agent': 'ENGINEER_LITE', 'content': '乙'}]
    check(cost_summary(outside, 7, allowed, costs.__getitem__) ==
          {'total': 3, 'budget': 7, 'tasks': [{'index': 1, 'agent': 'TEST_ENGINEER', 'cost': 2, 'content': '甲'},
                                              {'index': 2, 'agent': 'ENGINEER_LITE', 'cost': 1, 'content': '乙'}],
           'status': '超出', 'not_in_roster': ['TEST_ENGINEER']}, '清单外角色判超出')


def _scan_cost_trace(tmp, name):
    from test_wf_cost import demo_copy as cost_demo, run_demo, plan
    from wf_fixtures import contract, review, impl, acceptance
    folder = tmp / name
    folder.mkdir()
    _, _, trace, error = run_demo(cost_demo(folder), [contract('v1'), review('通过'),
                                  plan('ENGINEER_LITE', 'ENGINEER', 'ENGINEER'),
                                  impl('甲'), impl('乙'), impl('丙'), acceptance('通过')])
    check(error is None and trace['status'] == 'done', '补充：成本流程跑完')
    return trace


def test_scan_each_source(tmp):
    trace = _scan_cost_trace(tmp, 'scan-source')
    source = next(e for e in trace['events'] if e.get('name') == '任务分配')
    each = next(e for e in trace['events'] if e['type'] == 'each')
    check(each['record'] == 'assignment' and each['path'] == 'tasks'
          and each['source_step'] == source['step'], '补充a：遍历带清单来源和产生步号')


def test_scan_task_items(tmp):
    trace = _scan_cost_trace(tmp, 'scan-items')
    tasks = [e for e in trace['events'] if e.get('name') == '任务实现']
    each = next(e for e in trace['events'] if e['type'] == 'each')
    check([e['item'] for e in tasks] ==
          [dict(index=i, total=3, each_line=each['line'], record='assignment',
                source_step=each['source_step']) for i in range(1, 4)],
          '补充b：任务 item 从1递增、总数和来源正确，事件不带 key')


def test_scan_outside_item(tmp):
    trace = _scan_cost_trace(tmp, 'scan-outside')
    check(all('item' not in e for e in trace['events']
              if e['type'] == 'task' and e['name'] != '任务实现'),
          '补充c：遍历前后的任务事件没有 item')


def test_scan_unrevised_cost(tmp):
    trace = _scan_cost_trace(tmp, 'scan-unrevised')
    costs = [e for e in trace['events'] if e['type'] == 'cost']
    check(costs and all('list_rev' not in e for e in costs), '补充d：未修订成本事件没有 list_rev')


def test_scan_plans(tmp):
    from verbs.workflow._workflow import _plans, parse
    entry = (ROOT / 'workflow_demo/run_cost.zs').read_text(encoding='utf-8')
    workflow = next(line.split()[1] for line in entry.splitlines() if line.startswith('编排执行 '))
    script = (ROOT / 'workflow_demo' / workflow).read_text(encoding='utf-8')
    info = _plans(parse(script))['assignment']
    check(info == dict(path='tasks', each_line=next(i for i, line in enumerate(script.splitlines(), 1)
                                                   if line.startswith('遍历 ')),
                       var='task', nodes=['任务实现'], agent_field='agent', content_field='content',
                       cost_target='spent', budget_expr='{budget}'), '补充e：静态扫描成本入口引用的流程')
    nested = _plans(parse('如果 yes\n    遍历 x 于 data.rows\n        工作\n            角色 ENGINEER\n            任务 固定文本\n            记录 result'))
    check(nested['data']['agent_field'] is None and nested['data']['content_field'] is None,
          '补充：递归扫描，非逐项字段留空')
    check(_plans(parse('')) == {}, '补充：空流程没有清单')


def test_scan_item_key(tmp):
    import hashlib
    from verbs.workflow._workflow import _item_key
    info = dict(content_field='content')
    key = _item_key(dict(content='相同内容', agent='A'), info)
    check(key == hashlib.sha1('相同内容'.encode()).hexdigest()[:12]
          and key == _item_key(dict(content='相同内容', agent='B'), info)
          and key != _item_key(dict(content='不同内容'), info) and len(key) == 12,
          '补充f：内容指纹稳定、区分内容且长度12')
    check(_item_key(dict(b=2, a=1), None) == _item_key(dict(a=1, b=2), {})
          and len(_item_key({}, None)) == 12, '补充：无内容字段按整项排序序列化，支持空项')


def test_scan_controlled_replay(tmp):
    from test_wf_cost import demo_copy as cost_demo, plan
    from wf_fixtures import contract, review, impl, acceptance
    folder = tmp / 'scan-controlled'
    folder.mkdir()
    c = client([contract('v1'), review('通过'), plan('ENGINEER_LITE', 'ENGINEER'),
                impl('甲'), impl('乙'), acceptance('通过')])
    s = wc.start(cost_demo(folder), entry='run_cost.zs', mode='auto',
                 confirm_after=['任务分配'], client=c)
    run = s['run']
    s = wc.approve(run, result=plan('ENGINEER', 'ENGINEER_LITE'), client=c)
    trace = wc._load(ROOT / run)
    cost = next(e for e in trace['events'] if e['type'] == 'cost')
    check(s['status'] == 'done' and cost['list_rev'] == 1 and cost['total'] == 4,
          '补充：放行修订清单后成本带 list_rev')
    # 模拟旧版本记录：去掉任务 item，回放核对仍只认原有四个字段。
    for event in trace['events']:
        if event['type'] == 'task':
            event.pop('item', None)
    wc._dump(ROOT / run, trace)
    before = len(c.calls)
    s = wc.resume(run, client=c)
    trace = wc._load(ROOT / run)
    check(s['status'] == 'done' and len(c.calls) == before
          and next(e for e in trace['events'] if e['type'] == 'cost')['list_rev'] == 1,
          '补充：旧任务事件无 item 仍回放，已应用的修订号保留')


def test_scan_request_item(tmp):
    from tools.dsl import DSLEngine
    from verbs.workflow import _workflow
    class RecordingControl(wc._Control):
        def decide(self, request):
            requests.append(request)
            return super().decide(request)
    requests = []
    wd = tmp / 'scan-request'
    wd.mkdir()
    engine = DSLEngine(client=client([]), workdir=wd, verbose=False)
    engine.vars['rows'] = [{'content': '甲'}, {'content': '乙'}]
    engine._wf_control = RecordingControl(dict(mode='auto'))
    script = ('遍历 x 于 rows\n    实施\n        角色 ENGINEER\n        任务 x.content\n'
              '        记录 result\n结束\n    角色 ENGINEER\n    记录 final')
    _workflow.run(engine, script, lambda *args: {'ok': True})
    check([r['item']['index'] for r in requests[:2]] == [1, 2]
          and requests[0]['item'] is not requests[1]['item']
          and requests[0]['item']['key'] == _workflow._item_key({'content': '甲'}, dict(content_field='content'))
          and 'item' not in requests[2], '补充：控制器收到独立 item 副本及 key，遍历结束后弹栈')
    trace = wc._load(engine.vars['workflow_trace'])
    each = next(e for e in trace['events'] if e['type'] == 'each')
    check(each['path'] is None and 'source_step' not in each,
          '补充：无任务来源的列表不写 each.source_step')


def test_item_fingerprints(tmp):
    rows = [dict(key='a', agent='ENGINEER', model='cli:fake/first', confirm_before=True),
            dict(key='b', agent='ENGINEER', model='cli:fake/second', confirm_after=False),
            dict(key='a', agent='ENGINEER', model='cli:fake/duplicate'), None]
    cfg = dict(item_controls={'assignment': dict(step=3, rows=rows)})
    item = dict(record='assignment', index=1, key='a', agent='ENGINEER')
    assert wc._item_control(cfg, item)['model'] == 'cli:fake/first'
    assert wc._item_control(cfg, dict(item, index=3))['model'] == 'cli:fake/duplicate'
    assert wc._item_control(cfg, dict(item, index=4, key='b'))['confirm_after'] is False
    assert wc._item_control(cfg, dict(item, key='missing')) == {}
    assert wc._item_control({}, item) == {} and wc._item_control(cfg, None) == {}
    changed = wc._item_control(cfg, dict(item, agent='ENGINEER_LITE'))
    assert changed.get('model') is None and changed['confirm_before'] is True
    req = dict(step=4, name='任务实现', role='ENGINEER', item=item)
    for override in [dict(roles={'ENGINEER': 'ENGINEER_LITE'}),
                     dict(go={'4': dict(role='ENGINEER_LITE')})]:
        d = wc._Control(dict(cfg, mode='auto', models={'ENGINEER': 'cli:fake/global'}, **override)).decide(req)
        assert d['model'] == 'cli:fake/global'
    for extra, expected in [({}, 'cli:fake/first'),
                            (dict(go={'4': dict(model='cli:fake/go')}), 'cli:fake/go')]:
        d = wc._Control(dict(cfg, mode='auto', models={'ENGINEER': 'cli:fake/global'}, **extra)).decide(req)
        assert d['model'] == expected
    for role, model, expected in [('ENGINEER', None, 'cli:fake/first'),
                                  ('ENGINEER_LITE', None, 'cli:fake/global'),
                                  ('ENGINEER_LITE', 'cli:fake/reject', 'cli:fake/reject')]:
        ctl = wc._Control(dict(cfg, mode='auto', models={'ENGINEER': 'cli:fake/global'},
                              after={'4': dict(action='reject', attempt=1, role=role, model=model)}))
        ctl.carry[4] = [dict(status='rejected', result={})]
        assert ctl.decide(req)['model'] == expected
    for key in ['confirm_before', 'confirm_after']:
        config = dict(mode='step', confirm_after=['任务实现'], item_controls={
            'assignment': dict(rows=[dict(rows[0], **{key: False})])})
        d = wc._Control(config).decide(req)
        assert (d['action'] == 'run') if key == 'confirm_before' else not d['after']
    check(True, '逐项指纹同下标优先、换序查找、缺失兼容、换卡模型作废、false 覆盖规则')


def test_item_controls_storage_validation(tmp):
    s = wc.start(demo_copy(tmp, 'item-storage'), client=client([]))
    run = s['run']
    cf = wc._side(ROOT / run, '.ctl')
    before = cf.read_bytes()
    raises(lambda: wc._set_item_controls(run, 'assignment', 3, [], '\ud800'), '来源无效')
    for record, rows in [('\ud800', []), ('assignment', [dict(key='\ud800')]),
                         ('assignment', [dict(agent='\ud800')]),
                         ('assignment', [dict(model='cli:claude/\ud800')])]:
        raises(lambda: wc._set_item_controls(run, record, 3, rows, 'viewer'), '有效的 UTF-8 JSON')
        assert cf.read_bytes() == before
    wc._set_item_controls(run, 'assignment', 3, [None], 'viewer')
    stored = wc._load(cf)['item_controls']['assignment']
    assert stored['rows'] == [None] and stored['at'] and stored['actor'] == 'viewer' and stored['step'] == 3
    cfg = dict(item_controls={'later': dict(step=10), 'earlier': dict(step=1), 'current': dict(step=3)})
    wc._prune(cfg, 3)
    assert cfg['item_controls'] == {'earlier': dict(step=1)}
    check(True, '逐项存储支持 null，拒绝不可编码输入且不写文件；按来源步数清除')


def _item_setup(tmp, name, after):
    from test_wf_cost import demo_copy as cost_demo, plan
    from wf_fixtures import contract, review, impl, acceptance
    folder = tmp / name
    folder.mkdir()
    assigned = plan('ENGINEER_LITE', 'ENGINEER', 'ENGINEER')
    c = client([contract('v1'), review('通过'), assigned, impl('甲'), impl('乙'), impl('丙'), acceptance('通过')])
    s = wc.start(cost_demo(folder), entry='run_cost.zs', mode='auto',
                 confirm_after=['任务分配'] + after, client=c)
    assert s['pending']['phase'] == 'after' and 'item' not in s['pending']
    assert s['pending']['plan']['record'] == 'assignment'
    assert s['pending']['plan']['budget'] == 7
    assert 'ENGINEER' in s['pending']['plan']['roster']
    return s, c, assigned


def _control_rows(assigned):
    from verbs.workflow._workflow import _item_key
    return [dict(key=_item_key(row, dict(content_field='content')), agent=row['agent'])
            for row in assigned['tasks']]


def test_item_controls_25(tmp):
    s, c, assigned = _item_setup(tmp, 'items-25', [])
    rows = _control_rows(assigned)
    rows[0]['model'] = 'cli:claude/item-model'
    rows[1]['confirm_before'] = True
    rows[2]['confirm_after'] = True
    run = s['run']
    wc._set_item_controls(run, 'assignment', s['pending']['step'], rows, 'viewer')
    cfg = wc._load(wc._side(ROOT / run, '.ctl'))
    assert cfg['item_controls']['assignment']['rows'] == rows
    assert cfg['history'][-1]['op'] == 'item_controls' and cfg['history'][-1]['actor'] == 'viewer'
    s = wc.approve(run, client=c)
    p = s['pending']
    assert p['phase'] == 'before' and p['reason'] == 'item' and p['item']['index'] == 2
    assert p['item']['total'] == 3 and 'key' not in p['item']
    assert p['plan']['record'] == 'assignment' and p['plan']['budget'] == 7
    first = next(e for e in task_events(run) if e['name'] == '任务实现' and e['status'] == 'ok')
    assert first['model_override'] == rows[0]['model']
    s = wc.execute(run, client=c)
    assert s['pending']['phase'] == 'after' and s['pending']['reason'] == 'item'
    assert s['pending']['item']['index'] == 3 and s['pending']['item']['total'] == 3
    assert 'key' not in s['pending']['item']
    for call in c.calls:
        assert all(token not in call['prompt'] for token in ['cli:claude/item-model', 'confirm_before', 'confirm_after'])
    assert next(e for e in task_events(run) if e['name'] == '任务分配')['result'] == assigned
    s = wc.approve(run, client=c)
    assert s['status'] == 'done'
    s = wc.rewind(run, cfg['item_controls']['assignment']['step'], client=c)
    assert wc._load(wc._side(ROOT / run, '.ctl'))['item_controls'] == {}
    check(True, '25：逐项模型、前停后停、item/plan、提示词和结果隔离、rewind 清除')


def test_item_controls_26(tmp):
    s, c, assigned = _item_setup(tmp, 'items-26', ['任务实现'])
    rows = _control_rows(assigned)
    rows[0]['confirm_after'] = False
    wc._set_item_controls(s['run'], 'assignment', s['pending']['step'], rows, 'workflow_ctl')
    s = wc.approve(s['run'], client=c)
    assert s['pending']['item']['index'] == 2 and s['pending']['phase'] == 'after'
    s = wc.approve(s['run'], client=c)
    assert s['pending']['item']['index'] == 3 and s['pending']['phase'] == 'after'
    s = wc.approve(s['run'], client=c)
    assert s['status'] == 'done'
    check(True, '26：第1项 false 覆盖后确认规则，其余项逐一后停')


def test_pending_plan_before_and_missing_budget(tmp):
    from tools.dsl import DSLEngine
    from verbs.workflow import _workflow
    wd = tmp / 'pending-plan-before'
    wd.mkdir()
    engine = DSLEngine(client=client([]), workdir=wd, verbose=False)
    engine._wf_control = wc._Control(dict(mode='step'))
    script = ('分配\n    角色 ARCHITECT\n    记录 assignment\n'
              '成本合计 spent assignment.tasks 预算 {missing}\n'
              '遍历 x 于 assignment.tasks\n    实施\n        角色 x.agent\n'
              '        任务 x.content\n        记录 result')
    try:
        _workflow.run(engine, script, lambda *args: {})
    except wc.WorkflowPause:
        pass
    pending = wc._load(engine.vars['workflow_trace'])['pending']
    assert pending['plan']['budget'] is None and pending['plan']['roster'] == []
    assert pending['plan']['cost_target'] == 'spent' and 'item' not in pending
    check(True, '清单来源开始前停带 plan；预算尚未定义时为 None')


def test_plan_approve_22(tmp):
    from wf_fixtures import impl
    s, c, assigned = _item_setup(tmp, 'plan-22', [])
    changed = {'tasks': [dict(assigned['tasks'][1], agent='ENGINEER_LITE'),
                         dict(assigned['tasks'][0], agent='ENGINEER'),
                         dict(assigned['tasks'][2], content='新加的一项', agent='ENGINEER_LITE')]}
    out = wc.approve(s['run'], result=changed, item_controls=[None, {'confirm_before': True}, None], client=c)
    assert out['cost_preview'] == dict(total=5, budget=7, status='未超出', not_in_roster=[])
    event = next(e for e in task_events(s['run']) if e['name'] == '任务分配')
    assert event['result_model'] == assigned and event['result'] == changed
    costs = [e for e in wc._load(ROOT / s['run'])['events'] if e['type'] == 'cost']
    assert costs[-1]['total'] == 5
    out = wc.execute(s['run'], client=c)
    executed = [e for e in task_events(s['run']) if e['name'] == '任务实现']
    assert [(e['task'], e['role']) for e in executed] == [(x['content'], x['agent']) for x in changed['tasks']]
    assert out['status'] == 'done'
    check(True, '22：改卡、换序、增删后的清单和原结果都保留，成本和遍历用新清单')


def test_plan_approve_23_28(tmp):
    from test_wf_cost import demo_copy as cost_demo, plan
    from wf_fixtures import contract, review, impl, acceptance
    for name, role, outside in [('over', 'ENGINEER_SENIOR', []), ('outside', 'ENGINEER_GPT', ['ENGINEER_GPT'])]:
        folder = tmp / ('plan-23-' + name)
        folder.mkdir()
        assigned = plan('ENGINEER')
        adjusted = plan('ENGINEER_LITE')
        c = client([contract('v1'), review('通过'), assigned, adjusted, impl('甲'), acceptance('通过')])
        s = wc.start(cost_demo(folder), entry='run_cost.zs', mode='auto', confirm_after=['任务分配'], client=c)
        changed = plan(role)
        s = wc.approve(s['run'], result=changed,
                       item_controls=[dict(model='cli:claude/old-card', confirm_before=True, confirm_after=True)], client=c)
        assert s['cost_preview']['status'] == '超出' and s['cost_preview']['not_in_roster'] == outside
        assert s['pending']['phase'] == 'before' and s['pending']['role'] == 'ENGINEER_LITE'
        listing = wc.plan(s['run'])
        assert listing['rows'][0]['control']['model'] is None
        assert listing['rows'][0]['confirm_before'] and listing['rows'][0]['confirm_after']
        s = wc.execute(s['run'], client=c)
        assert s['pending']['phase'] == 'after'
        execution = next(e for e in task_events(s['run']) if e['name'] == '任务实现')
        assert execution.get('model_override') != 'cli:claude/old-card'
        check(True, '23/28：超预算和清单外卡触发调整；换卡后保留确认、原模型作废')


def test_plan_approve_validation_24(tmp):
    s, c, assigned = _item_setup(tmp, 'plan-validation', [])
    p = ROOT / s['run']
    cf = wc._side(p, '.ctl')
    before = (p.read_bytes(), cf.read_bytes())
    bad_result = {'tasks': [dict(assigned['tasks'][0], agent='UNKNOWN')]}
    raises(lambda: wc.approve(s['run'], result=bad_result, item_controls='bad', client=c), '不符合格式')
    for controls in ['bad', [], [None], [None, None, None, None],
                     [{'unknown': 1}, None, None], [True, None, None],
                     [{'confirm_before': 1}, None, None], [{'confirm_after': 'yes'}, None, None],
                     [{'model': 'bad'}, None, None], [{'model': 'cli:claude/\ud800'}, None, None]]:
        raises(lambda: wc.approve(s['run'], item_controls=controls, client=c), '逐项设置第')
        assert (p.read_bytes(), cf.read_bytes()) == before
    raises(lambda: wc.approve(s['run'], result={'tasks': [dict(assigned['tasks'][0], content='\ud800')]}, client=c), 'UTF-8')
    assert (p.read_bytes(), cf.read_bytes()) == before
    plain = wc.start(demo_copy(tmp, 'no-plan-controls'), mode='auto', confirm_after=['接口约定'], client=client(REPLIES))
    raises(lambda: wc.approve(plain['run'], item_controls=[], client=c), '逐项设置只能用在分配清单上')
    check(True, '24：格式先于逐项设置校验；错误字段、长度、类型、模型和编码全部拒绝且文件不动')


def test_plan_reject_27(tmp):
    from test_wf_cost import plan
    s, c, assigned = _item_setup(tmp, 'plan-27', [])
    rows = _control_rows(assigned)
    rows[0]['confirm_before'] = True
    wc._set_item_controls(s['run'], 'assignment', s['pending']['step'], rows)
    # 打回后模型重新分配，停在同一来源步的结束后。
    retry = client([assigned])
    s = wc.reject(s['run'], note='重新分配', client=retry)
    cfg = wc._load(wc._side(ROOT / s['run'], '.ctl'))
    assert 'assignment' not in cfg['item_controls']
    assert any(h['op'] == 'reject' and h.get('record') == 'assignment' for h in cfg['history'])
    assert all(r['control'] is None for r in wc.plan(s['run'])['rows'])
    check(True, '27：打回清单删除逐项设置并记录 history，重分清单没有旧设置')


def test_plan_states_33(tmp):
    s, c, assigned = _item_setup(tmp, 'plan-33', [])
    p, cf = ROOT / s['run'], wc._side(ROOT / s['run'], '.ctl')
    before = (p.read_bytes(), cf.read_bytes())
    listing = wc.plan(s['run'])
    assert listing['total'] == listing['budget'] == 7
    assert [r['state'] for r in listing['rows']] == ['todo'] * 3
    assert listing['source_step'] == 3 and listing['format'] == 'cost_assignment'
    assert listing['path'] == 'tasks' and listing['editable'] and listing['why_not'] is None
    assert listing['roster'][0].keys() == {'name', 'cost', 'description'}
    assert (p.read_bytes(), cf.read_bytes()) == before
    s = wc.approve(s['run'], item_controls=[None, {'confirm_after': True}, {'confirm_before': True}], client=c)
    listing = wc.plan(s['run'])
    assert [r['state'] for r in listing['rows']] == ['done', 'held', 'todo']
    assert listing['rows'][1]['step'] == s['pending']['step']
    s = wc.approve(s['run'], client=c)
    assert [r['state'] for r in wc.plan(s['run'])['rows']] == ['done', 'done', 'waiting']
    s = wc.execute(s['run'], client=client(['不是JSON']))
    assert wc.plan(s['run'])['rows'][2]['state'] == 'tried'
    s = wc.execute(s['run'], client=c)
    assert not wc.plan(s['run'])['editable'] and wc.plan(s['run'])['why_not']
    raises(lambda: wc.plan(s['run'], '\ud800'), '没有可改的分配清单')
    check(True, '33：只读 plan 返回成本、来源、规则开关以及 todo/done/held/waiting/tried 各状态')


def test_plan_legacy_34(tmp):
    from wf_fixtures import contract, review, impl, acceptance
    assigned = {'tasks': [{'content': '旧流程任务', 'agent': 'ENGINEER'}]}
    c = client([contract('v1'), review('通过'), assigned, impl('甲'), acceptance('通过')])
    demo = demo_copy(tmp, 'plan-34')
    s = wc.start(demo, mode='auto', confirm_after=['任务分配'], client=c)
    listing = wc.plan(s['run'])
    assert listing['budget'] is None and listing['status'] is None
    assert listing['rows'][0]['item'] == assigned['tasks'][0]
    s = wc.approve(s['run'], item_controls=[None], client=c)
    assert s['cost_preview']['budget'] is None and s['cost_preview']['status'] is None
    assert not any(e['name'] == '分配调整' for e in task_events(s['run']))
    empty = wc.start(demo_copy(tmp, 'plan-empty'), client=client([]))
    raises(lambda: wc.plan(empty['run']), '这次运行没有可改的分配清单')
    check(True, '34：旧流程可列清单，无预算不判断超出；没有清单时报 ControlError')


def _edit_setup(tmp, name, count=6, budget=12, edit=None):
    from test_wf_cost import demo_copy as cost_demo, plan
    from wf_fixtures import contract, review, impl, acceptance
    folder = tmp / name
    folder.mkdir()
    assigned = plan(*(['ENGINEER_LITE'] * count))
    c = client([contract('v1'), review('通过'), assigned]
               + [impl(str(i)) for i in range(count)] + [acceptance('通过')])
    s = wc.start(cost_demo(folder, budget=budget, edit=edit), entry='run_cost.zs', mode='auto',
                 confirm_before=['任务实现'], client=c)
    return s, c, assigned


def test_edit_plan_29(tmp):
    import copy
    s, c, assigned = _edit_setup(tmp, 'edit-29')
    run = s['run']
    wc.execute(run, client=c)
    s = wc.execute(run, client=c)
    assert s['pending']['item']['index'] == 3
    before = [e for e in task_events(run) if e.get('item') and e['status'] == 'ok']
    calls = len(c.calls)
    changed = copy.deepcopy(assigned['tasks'][:5])
    changed[2].update(agent='ENGINEER', content='新的第三项')
    changed[3].update(agent='ENGINEER', content='新的第四项')
    changed.append(dict(content='追加项', agent='ENGINEER_LITE', reason='追加'))
    s = wc.edit_plan(run, tasks=changed, client=c, actor='viewer')
    assert len(c.calls) == calls
    assert s['cost_preview']['total'] == 10
    assert s['pending']['task'] == '新的第三项' and s['pending']['role'] == 'ENGINEER'
    trace = wc._load(ROOT / run)
    cost = next(e for e in trace['events'] if e['type'] == 'cost')
    assert cost['total'] == 10 and cost['list_rev'] == 1
    assert [e for e in task_events(run) if e.get('item') and e['status'] == 'ok'] == before
    for _ in range(4):
        s = wc.execute(run, client=c)
    assert s['status'] == 'done'
    events = [e for e in task_events(run) if e.get('item') and e['status'] == 'ok']
    assert [(e['task'], e['role']) for e in events] == [(x['content'], x['agent']) for x in changed]
    cfg = wc._load(wc._side(ROOT / run, '.ctl'))
    assert cfg['history'][-1]['actor'] == 'workflow_ctl'
    revision = cfg['revisions']['3'][-1]
    assert revision['kind'] == 'plan_edit' and revision['actor'] == 'viewer' and 'attempt' not in revision
    check(True, '29：修改未跑项、增删清单，已跑项不重跑，成本和 pending 刷新')


def test_edit_plan_30(tmp):
    import copy
    s, c, assigned = _edit_setup(tmp, 'edit-30')
    run = s['run']
    s = wc.execute(run, client=c)
    p, cf = ROOT / run, wc._side(ROOT / run, '.ctl')
    before = (p.read_bytes(), cf.read_bytes())
    changed = copy.deepcopy(assigned['tasks'])
    changed[0]['content'] = '不能改'
    raises(lambda: wc.edit_plan(run, tasks=changed), '第 1 项已经跑过')
    raises(lambda: wc.edit_plan(run, tasks=[]), '第 1 项已经跑过')
    raises(lambda: wc.edit_plan(run, item_controls=[{}, None, None, None, None, None]), '第 1 项已经跑过')
    changed = copy.deepcopy(assigned['tasks'])
    changed[1]['agent'] = 'ENGINEER_SENIOR'
    raises(lambda: wc.edit_plan(run, tasks=changed), '改后合计 13，预算 12')
    changed[1]['agent'] = 'ENGINEER_GPT'
    raises(lambda: wc.edit_plan(run, tasks=changed), 'ENGINEER_GPT')
    assert (p.read_bytes(), cf.read_bytes()) == before
    fresh, c2, assigned2 = _edit_setup(tmp, 'edit-30-fresh')
    assigned2['tasks'][0]['agent'] = 'ENGINEER_SENIOR'
    out = wc.edit_plan(fresh['run'], tasks=assigned2['tasks'], client=c2)
    assert out['cost_preview']['status'] == '超出'
    assert out['pending']['name'] == '分配调整' and out['pending']['phase'] == 'before'
    check(True, '30：冻结前缀和超预算拒绝时文件不变；尚未执行时允许进入分配调整')


def test_edit_plan_31(tmp):
    import subprocess
    s, c, assigned = _edit_setup(tmp, 'edit-31')
    run = s['run']
    p, cf = ROOT / run, wc._side(ROOT / run, '.ctl')
    proc = subprocess.Popen(['bash', '-c', 'exec -a workflow_ctl sleep 60'])
    try:
        cfg = wc._load(cf)
        cfg['worker'] = proc.pid
        wc._dump(cf, cfg)
        before = (p.read_bytes(), cf.read_bytes())
        changed = [dict(row) for row in assigned['tasks']]
        changed[0]['content'] = '后台不能改'
        raises(lambda: wc.edit_plan(run, tasks=changed), '后台还在跑，先 pause 等当前这步跑完再改清单')
        assert (p.read_bytes(), cf.read_bytes()) == before
        out = wc.edit_plan(run, item_controls=[{'confirm_after': True}] + [None] * 5, client=c)
        assert out['worker_alive'] and len(c.calls) == 3
        assert wc._load(cf)['item_controls']['assignment']['rows'][0]['confirm_after'] is True
        assert p.read_bytes() == before[0]
    finally:
        proc.terminate()
        proc.wait()
    check(True, '31：后台运行时拒绝改内容，允许单改逐项设置且不覆盖运行记录')


def test_edit_plan_32(tmp):
    from tools.dsl import DSLEngine
    from wf_fixtures import impl, acceptance
    s, c, assigned = _edit_setup(tmp, 'edit-32', count=3)
    run = s['run']
    wc.execute(run, client=c)
    wc.configure(run, confirm_after=['任务实现'])
    s = wc.execute(run, client=c)
    assert s['pending']['item']['index'] == 2 and s['pending']['phase'] == 'after'
    first = next(e for e in task_events(run) if e.get('item') and e['item']['index'] == 1 and e['status'] == 'ok')
    retry = client([impl('最终通过'), impl('第三项'), acceptance('通过')])
    s = wc.reject(run, note='第二项重做', client=retry)
    assert len(retry.calls) == 1 and s['pending']['item']['index'] == 2
    snapshots = []
    original = DSLEngine.store
    def capture(engine, key, value):
        if key == 'task_results':
            snapshots.append(value)
        return original(engine, key, value)
    DSLEngine.store = capture
    try:
        s = wc.approve(run, client=retry)
        s = wc.execute(run, client=retry)
        s = wc.approve(run, client=retry)
    finally:
        DSLEngine.store = original
    assert s['status'] == 'done' and len(retry.calls) == 3
    events = task_events(run)
    assert next(e for e in events if e.get('item') and e['item']['index'] == 1 and e['status'] == 'ok') == first
    assert [e['status'] for e in events if e.get('item') and e['item']['index'] == 2] == ['rejected', 'ok']
    assert snapshots[-1] == [first['result'], impl('最终通过'), impl('第三项')]
    check(True, '32：仅被打回项重跑，其他事件不动，task_results 只存最终通过结果')


def test_edit_plan_validation_rollback(tmp):
    from unittest.mock import patch
    s, c, assigned = _edit_setup(tmp, 'edit-validation')
    run = s['run']
    p, cf = ROOT / run, wc._side(ROOT / run, '.ctl')
    before = (p.read_bytes(), cf.read_bytes())
    raises(lambda: wc.edit_plan(run, actor='\ud800'), '来源无效')
    raises(lambda: wc.edit_plan(run, record='\ud800'), '没有可改的分配清单')
    raises(lambda: wc.edit_plan(run, tasks=[dict(assigned['tasks'][0], content='\ud800')]), 'UTF-8')
    raises(lambda: wc.edit_plan(run, tasks=[{'content': '缺卡'}]), '结果不符合格式')
    raises(lambda: wc.edit_plan(run, item_controls=[]), '逐项设置第')
    raises(lambda: wc.edit_plan(run, item_controls=[{'model': 'cli:x/\ud800'}] + [None] * 5), '逐项设置第')
    assert (p.read_bytes(), cf.read_bytes()) == before
    failure = wc.ControlError('第 1 步回放对不上（测试）')
    advance = wc._advance
    def broken(*args, **kwargs):
        advance(*args, **kwargs)
        raise failure
    with patch.object(wc, '_advance', broken):
        try:
            wc.edit_plan(run, tasks=assigned['tasks'], client=c)
        except wc.ControlError as exc:
            assert exc is failure
        else:
            raise AssertionError('回放错误应原样抛出')
    assert (p.read_bytes(), cf.read_bytes()) == before
    held, _, _ = _item_setup(tmp, 'edit-review', [])
    raises(lambda: wc.edit_plan(held['run']), '这份清单还在等确认，用 approve 带上改后的结果')
    empty = wc.start(demo_copy(tmp, 'edit-empty'), client=client([]))
    raises(lambda: wc.edit_plan(empty['run']), '没有可改的分配清单')
    check(True, 'edit_plan：入口校验、孤立代理字符、格式、设置和回放失败均不留下写入')


def test_edit_plan_alignment(tmp):
    from verbs.workflow._workflow import _item_key
    s, c, assigned = _edit_setup(tmp, 'edit-align')
    run = s['run']
    controls = [dict(model='cli:claude/original', confirm_before=True)] + [None] * 5
    wc.edit_plan(run, item_controls=controls, client=c)
    tasks = [dict(x) for x in assigned['tasks']]
    tasks[0], tasks[1] = tasks[1], tasks[0]
    tasks[1]['agent'] = 'ENGINEER'
    out = wc.edit_plan(run, tasks=tasks, client=c)
    cfg = wc._load(wc._side(ROOT / run, '.ctl'))
    rows = cfg['item_controls']['assignment']['rows']
    assert rows[0] is None and rows[1]['agent'] == 'ENGINEER_LITE'
    setting = wc._item_control(cfg, dict(record='assignment', index=2, agent='ENGINEER',
                                        key=_item_key(tasks[1], dict(content_field='content'))))
    assert setting['model'] is None and setting['confirm_before'] is True
    source = next(e for e in task_events(run) if e['step'] == 3)
    assert [r['rev'] for r in source['revisions']] == [1, 2]
    assert source['result_model'] == assigned and source['result']['tasks'] == tasks
    assert len(c.calls) == 3 and out['cost_preview']['total'] == 8
    check(True, 'edit_plan：重复修订递增，指纹随重排对齐，换卡使原模型失效且保留确认开关')


def test_edit_plan_replay_mismatch(tmp):
    def edit(demo):
        path = demo / 'cost_workflow.wf'
        script = path.read_text()
        script = script.replace('遍历 task 于 assignment.tasks',
                                '如果 spent.total == 5\n    插入节点\n        角色 ENGINEER_LITE\n'
                                '        任务 新插入\n        格式 implementation\n        记录 inserted\n'
                                '遍历 task 于 assignment.tasks')
        path.write_text(script)
    s, c, assigned = _edit_setup(tmp, 'edit-mismatch', edit=edit)
    run = s['run']
    wc.execute(run, client=c)
    p, cf = ROOT / run, wc._side(ROOT / run, '.ctl')
    before = (p.read_bytes(), cf.read_bytes())
    calls = len(c.calls)
    raises(lambda: wc.edit_plan(run, tasks=assigned['tasks'][:5], client=c), '第 4 步回放对不上')
    assert (p.read_bytes(), cf.read_bytes()) == before and len(c.calls) == calls
    check(True, 'edit_plan：实际分支变化导致回放错位，原错误抛出且记录和控制文件逐字节恢复')


def run():
    (ROOT / 'data/tmp').mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix='wfconfirm-', dir=ROOT / 'data/tmp'))
    try:
        for test in [test_edit_plan_29, test_edit_plan_30, test_edit_plan_31, test_edit_plan_32,
                     test_edit_plan_validation_rollback, test_edit_plan_alignment, test_edit_plan_replay_mismatch,
                     test_plan_approve_22, test_plan_approve_23_28, test_plan_approve_validation_24,
                     test_plan_reject_27, test_plan_states_33, test_plan_legacy_34, test_item_controls_storage_validation, test_item_fingerprints, test_item_controls_25, test_item_controls_26,
                     test_pending_plan_before_and_missing_budget, test_cost_summary, test_api_phase, test_status_after_actor, test_api_revision, test_api_reject, test_api_reject_override,
                     test_api_approve_true_to_one, test_api_approve_nested_false_to_zero,
                     test_api_approve_identical_json,
                     test_api_limit, test_api_validation, test_api_both_phases, test_api_interrupted,
                     test_api_reject_role_integer, test_api_reject_role_list, test_api_reject_role_dict,
                     test_after_unsorted_revisions, test_after_attempt_limit_manual_retry,
                     test_after_review_hold, test_after_approve_release, test_after_revised_approve,
                     test_after_reject_retry, test_after_reject_error_retry, test_after_abort_resume,
                     test_after_cost_spent, test_after_decision_order, test_after_replay_revisions,
                     test_after_interrupted_reject, test_after_rules_and_external,
                     test_after_before_and_step, test_after_no_store_until_release,
                     test_after_sort_and_rewind, test_after_configure_during_run,
                     test_p1_previous_absent, test_p1_previous_layout, test_p1_rejected_result, test_p1_previous_truncated,
                     test_p1_describe, test_after_attempt_settings, test_after_attempt_validation,
                     test_rewind_confirm_state, test_ctl_lock_l1, test_ctl_lock_process,
                     test_configure_entry_lock, test_legacy, test_matching, test_roles, test_validation, test_configure,
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
        for test in [test_scan_each_source, test_scan_task_items, test_scan_outside_item,
                     test_scan_unrevised_cost, test_scan_plans, test_scan_item_key,
                     test_scan_controlled_replay, test_scan_request_item]:
            test(tmp)
        print('workflow confirm passed')
    finally:
        shutil.rmtree(tmp)


if __name__ == '__main__':
    run()


def test_approve_legacy_positional_note(tmp):
    c = client(REPLIES)
    s = wc.start(demo_copy(tmp, 'approve-positional-note'), mode='auto',
                 confirm_after=['接口约定'], client=c)
    run = s['run']
    out = wc.approve(run, None, '人工说明', client=c)
    cfg = wc._load(wc._side(ROOT / run, '.ctl'))
    assert out['status'] == 'done' and len(c.calls) == len(REPLIES)
    assert cfg['after']['1']['action'] == 'approve'
    assert cfg.get('revisions', {}) == {} and cfg.get('item_controls', {}) == {}
    check(True, '旧 approve(run, None, note, client=...) 普通节点照常通过')


def test_approve_legacy_all_positional_revised(tmp):
    from unittest.mock import patch
    from wf_fixtures import contract
    c = client(REPLIES)
    s = wc.start(demo_copy(tmp, 'approve-positional-revised'), mode='auto',
                 confirm_after=['接口约定'], client=c)
    run = s['run']
    changed = contract('人工修订')
    with patch.object(wc, '_continue', wraps=wc._continue) as continued:
        out = wc.approve(run, changed, '人工说明', 1, 1, True, c, 'viewer')
    continued.assert_called_once_with(ROOT / run, True, c)
    cfg = wc._load(wc._side(ROOT / run, '.ctl'))
    revision = cfg['revisions']['1'][0]
    assert revision['result'] == changed and revision['note'] == '人工说明'
    assert revision['attempt'] == 1 and revision['actor'] == 'viewer'
    assert cfg['after']['1']['attempt'] == 1 and cfg['after']['1']['actor'] == 'viewer'
    approval = next(h for h in cfg['history'] if h['op'] == 'approve')
    assert approval['step'] == 1 and approval['attempt'] == 1 and approval['actor'] == 'viewer'
    event = task_events(run)[0]
    assert event['result'] == changed and event['result_model'] == REPLIES[0]
    assert out['status'] == 'done' and len(c.calls) == len(REPLIES)
    check(True, '改后通过的全部旧位置参数保持 result/note/step/attempt/wait/client/actor 绑定')


def test_approve_legacy_positional_guards_and_item_controls(tmp):
    from test_wf_cost import plan
    s, c, assigned = _item_setup(tmp, 'approve-positional-controls', [])
    run = s['run']
    p, cf = ROOT / run, wc._side(ROOT / run, '.ctl')
    step, attempt = s['pending']['step'], s['pending']['attempt']
    before = (p.read_bytes(), cf.read_bytes(), len(c.calls))
    raises(lambda: wc.approve(run, None, '人工说明', step + 1, attempt, True, c, 'viewer'),
           f'不是第 {step + 1} 步')
    raises(lambda: wc.approve(run, None, '人工说明', step, attempt + 1, True, c, 'viewer'),
           '结果已经换了')
    assert (p.read_bytes(), cf.read_bytes(), len(c.calls)) == before
    changed = plan('ENGINEER_LITE', 'ENGINEER_LITE', 'ENGINEER_LITE')
    out = wc.approve(run, changed, '修改清单', step, attempt, True, c, 'viewer',
                     item_controls=[{'confirm_before': True}, None, None])
    cfg = wc._load(cf)
    revision = cfg['revisions'][str(step)][0]
    assert revision['note'] == '修改清单' and revision['result'] == changed
    assert revision['attempt'] == attempt and revision['actor'] == 'viewer'
    control = cfg['item_controls']['assignment']
    assert control['step'] == step and control['actor'] == 'viewer'
    assert control['rows'][0]['confirm_before'] is True and len(control['rows']) == 3
    assert out['pending']['phase'] == 'before' and out['pending']['item']['index'] == 1
    assert len(c.calls) == 3
    check(True, '旧 step/attempt 防呆拒绝且文件不变；旧位置参数可同时使用关键字 item_controls')


def test_rewind_retains_item_controls_before_target(tmp):
    s, c, assigned = _item_setup(tmp, 'rewind-retain-item-controls', [])
    run, source_step = s['run'], s['pending']['step']
    rows = _control_rows(assigned)
    rows[0]['confirm_before'] = True
    wc._set_item_controls(run, 'assignment', source_step, rows, 'viewer')
    cf = wc._side(ROOT / run, '.ctl')
    stored = wc._load(cf)['item_controls']['assignment']
    out = wc.approve(run, client=c)
    assert out['pending']['step'] > source_step
    out = wc.rewind(run, out['pending']['step'], client=c)
    assert wc._load(cf)['item_controls'] == {'assignment': stored}
    assert out['pending']['step'] > source_step and len(c.calls) == 3
    check(True, 'rewind 到来源步之后严格保留该 record 的真实 rows 和完整设置')


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='wfconfirm-regression-', dir=ROOT / 'data/tmp') as folder:
        for test in [test_approve_legacy_positional_note, test_approve_legacy_all_positional_revised,
                     test_approve_legacy_positional_guards_and_item_controls,
                     test_rewind_retains_item_controls_before_target]:
            test(Path(folder))
