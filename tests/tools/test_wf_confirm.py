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
    check(cfg['item_controls'] == {'assignment': {'step': 3}}, '本项不清 item_controls')


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


def run():
    (ROOT / 'data/tmp').mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix='wfconfirm-', dir=ROOT / 'data/tmp'))
    try:
        for test in [test_api_phase, test_status_after_actor, test_api_revision, test_api_reject, test_api_reject_override,
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
        print('workflow confirm passed')
    finally:
        shutil.rmtree(tmp)


if __name__ == '__main__':
    run()
