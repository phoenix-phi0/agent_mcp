import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))  # 项目根，run_all 不设 PYTHONPATH
"""AI 会议 workflow_demo/meeting_workflow.wf：离线假模型，不调真模型。

1. 全是 AI：两轮（第一轮有点名追问，主持人判断还要再来一轮），第二轮都同意，出结论；
   后发言的人看得到前面的发言，追问的回答也记进会议记录，结论节点拿到全部发言。
2. 人参会（HUMAN，model=human）：受控运行轮到人就停下（即使是自动模式、没有确认规则），
   不能「执行」（不调模型），只能交结果；人交的发言里点名追问，被点名的 AI 紧跟着回答。
3. 人当主持人：主持判断和结论都停下等人交。
4. 给 HUMAN 换了模型（长期覆盖）就让 AI 代答，不停；不受控的运行碰到人直接报错，说清要在查看器上交。
"""
import json
import shutil
import tempfile
from pathlib import Path

from dsl.client import ScriptClient
from tools import workflow_ctl as wc
from tools.dsl import DSLEngine
from tools.dsl_core import DSLError

ROOT = Path(__file__).resolve().parents[2]


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print('  ✓', msg)


def speech(text, agree=False, ask='', question=''):
    return {'speech': text, 'agree': agree, 'ask': ask, 'question': question}


def mcheck(done, *dis):
    return {'done': done, 'disagreements': list(dis), 'summary': f'讨论到第几轮 {done}'}


DECISION = {'decision': '前端用纯 HTML/JS，不打包', 'reasons': ['REVIEWER_GPT 说部署简单'], 'dissent': [],
            'todo': [{'who': 'ARCHITECT', 'what': '写页面清单'}], 'summary': '定了纯 HTML/JS'}


def entry(attendees, moderator=None):
    return ('用包 workflow\n设 topic = 问卷网站的前端用什么技术\n设 background = 后端已经有JSON接口\n'
            f'设 attendees = {attendees}\n' + (f'设 moderator = {moderator}\n' if moderator else '') +
            '编排执行 meeting_workflow.wf\n')


def copy(tmp):
    demo = tmp / 'm'
    shutil.copytree(ROOT / 'workflow_demo', demo, ignore=shutil.ignore_patterns('runs', 'work', '*.bak-*', '__pycache__'))
    return demo


def client(replies):
    c = ScriptClient(list(replies))
    c.offline = True
    return c


def prompts(c):
    return [x['prompt'] for x in c.calls]


def steps(run):
    t = json.loads(Path(run).read_text(encoding='utf-8'))
    return [(e['step'], e['name'], e.get('role')) for e in t['events'] if e.get('type') == 'task' and e.get('status') == 'ok']


def test_all_ai(tmp):
    demo = copy(tmp)
    (demo / 'run_m.zs').write_text(entry('ARCHITECT,REVIEWER_GPT'), encoding='utf-8')
    c = client([speech('我主张 React', ask='REVIEWER_GPT', question='你怎么看打包？'),
                speech('不要打包，纯 HTML/JS 部署最简单'),          # 追问的回答
                speech('同上，纯 HTML/JS'),                          # REVIEWER_GPT 第一轮发言
                mcheck('否', 'ARCHITECT 和 REVIEWER_GPT 在要不要打包上不一致'),
                speech('那就纯 HTML/JS', agree=True), speech('同意', agree=True),
                mcheck('是'), DECISION])
    e = DSLEngine(workdir=demo, verbs_root=ROOT / 'verbs', verbose=False, client=c)
    e.run_file('run_m.zs')
    check(e.vars['decision'] == DECISION, '两轮之后出结论')
    m = e.vars['minutes']
    check([x['who'] for x in m] == ['ARCHITECT', 'REVIEWER_GPT', 'REVIEWER_GPT', 'ARCHITECT', 'REVIEWER_GPT'],
          '会议记录按发言顺序，追问的回答紧跟在提问之后')
    p = prompts(c)
    check(len(p) == 8, '一共 8 次调用（两轮发言、一次追问、两次判断、一次结论）')
    check('我主张 React' in p[1] and '你怎么看打包？' in p[1], '被追问的角色看得到问题和前面的发言')
    check('不要打包' in p[2] and '我主张 React' in p[2], '后发言的人看得到前面所有发言（含追问的回答）')
    check('在要不要打包上不一致' not in p[0], '第一轮没有上一轮的分歧')
    check('那就纯 HTML/JS' in p[5] and '同意' in p[6], '主持人判断时看得到这一轮的全部发言')
    check('讨论到第几轮 是' in p[7] and '讨论到第几轮 否' not in p[7], '结论节点拿到主持人最后一轮的判断（不是上一轮的）')
    check('在要不要打包上不一致' in p[4], '第二轮发言的人看得到主持人上一轮指出的分歧')


def test_human_seat(tmp):
    demo = copy(tmp)
    (demo / 'run_m.zs').write_text(entry('ARCHITECT,HUMAN'), encoding='utf-8')
    c = client([speech('我主张纯 HTML/JS'),
                speech('不支持 IE，只管现代浏览器', agree=True),   # 人追问后 ARCHITECT 的回答
                mcheck('是'), DECISION])
    s = wc.start(demo, entry='run_m.zs', mode='auto', wait=True, client=c)
    run = s['run']
    check(s['status'] == 'waiting' and s['pending']['role'] == 'HUMAN' and s['pending']['reason'] == 'human',
          '自动模式、没有确认规则，轮到人也停下等')
    check(len(c.calls) == 1, '停下之前只调了 ARCHITECT 一次，没给人调模型')
    try:
        wc.execute(run, wait=True, client=c)
        raise AssertionError('人的那一步不该能执行')
    except wc.ControlError as err:
        check('用 submit 交结果' in str(err), '人的那一步不能「执行」，提示用 submit 交')
    s = wc.submit(run, speech('要不要兼容旧浏览器？', ask='ARCHITECT', question='兼容 IE 吗？'), wait=True, client=c)
    check(s['status'] == 'done', '人交了发言后跑到底')
    check([x[1:] for x in steps(ROOT / run if not Path(run).is_absolute() else run)] ==
          [('发言', 'ARCHITECT'), ('发言', 'HUMAN'), ('追问', 'ARCHITECT'), ('主持判断', 'MODERATOR'), ('会议结论', 'MODERATOR')],
          '人发言后，被点名的 ARCHITECT 紧跟着回答，再由主持人判断、出结论')
    p = prompts(c)
    check('兼容 IE 吗？' in p[1] and '要不要兼容旧浏览器？' in p[1], 'AI 看得到人的发言和追问')
    t = json.loads((ROOT / run if not Path(run).is_absolute() else Path(run)).read_text(encoding='utf-8'))
    human = next(e for e in t['events'] if e.get('type') == 'task' and e.get('role') == 'HUMAN' and e.get('status') == 'ok')
    check(any(c.get('action') == 'submit' for c in human.get('confirm', [])), '人的发言在记录里标着是交上来的')


def test_human_moderator(tmp):
    demo = copy(tmp)
    (demo / 'run_m.zs').write_text(entry('ARCHITECT,REVIEWER_GPT', moderator='HUMAN'), encoding='utf-8')
    c = client([speech('纯 HTML/JS', agree=True), speech('同意', agree=True)])
    s = wc.start(demo, entry='run_m.zs', mode='auto', wait=True, client=c)
    run = s['run']
    check(s['pending']['name'] == '主持判断' and s['pending']['role'] == 'HUMAN', '人当主持人：判断这一步停下等人')
    s = wc.submit(run, mcheck('是'), wait=True, client=c)
    check(s['pending']['name'] == '会议结论' and s['pending']['role'] == 'HUMAN', '结论也停下等人')
    s = wc.submit(run, DECISION, wait=True, client=c)
    check(s['status'] == 'done' and len(c.calls) == 2, '人拍板后结束；模型只调了两个 AI 的发言')


def test_override_and_plain(tmp):
    demo = copy(tmp)
    (demo / 'run_m.zs').write_text(entry('ARCHITECT,HUMAN'), encoding='utf-8')
    c = client([speech('A'), speech('AI 代人说', agree=True), mcheck('是'), DECISION])
    s = wc.start(demo, entry='run_m.zs', mode='auto', wait=True, client=c, models={'HUMAN': 'cli:claude/haiku'})
    check(s['status'] == 'done' and len(c.calls) == 4, '给 HUMAN 换了模型就由 AI 代答，不停')
    e = DSLEngine(workdir=demo, verbs_root=ROOT / 'verbs', verbose=False, client=client([speech('A')]))
    try:
        e.run_file('run_m.zs')
        raise AssertionError('不受控的运行碰到人应当报错')
    except DSLError as err:
        check('是人' in str(err) and '查看器' in str(err), '不受控的运行碰到人：报错说清要在查看器上交')
    bad = demo / 'agents/HUMAN/agent.json'
    bad.write_text(json.dumps({'model': 'human', 'effort': 'high'}), encoding='utf-8')
    from verbs.workflow._agents import load_agent
    try:
        load_agent(e, 'HUMAN')
        raise AssertionError('人的卡写了 effort 应当报错')
    except DSLError as err:
        check('不写 effort' in str(err), '人的卡写了模型参数：报错')


def test_page(tmp):
    """运行页：轮到人时按发言格式出表单，没有「按默认执行」；页面交的结果再交给 workflow_ctl，会议接着走。"""
    import subprocess
    sys_path = str(Path(__file__).resolve().parent)
    if sys_path not in _sys.path:
        _sys.path.insert(0, sys_path)
    from test_trace_view import jsdom_env
    from tools import trace_server
    node, env = jsdom_env()
    if not node:
        print('  - 跳过页面：没有 node 或 jsdom')
        return
    demo = copy(tmp)
    (demo / 'run_m.zs').write_text(entry('ARCHITECT,HUMAN'), encoding='utf-8')
    c = client([speech('我主张纯 HTML/JS'), speech('不支持 IE', agree=True), mcheck('是'), DECISION])
    s = wc.start(demo, entry='run_m.zs', mode='auto', wait=True, client=c)
    run = Path(s['run']) if Path(s['run']).is_absolute() else ROOT / s['run']
    data, req = tmp / 'trace.json', tmp / 'req.json'
    data.write_text(json.dumps(trace_server.read_trace(run), ensure_ascii=False, default=str), encoding='utf-8')
    r = subprocess.run([node, str(ROOT / 'tests/e2e/trace_human_check.js'), str(ROOT / 'tools/trace_view.html'),
                        str(data), str(req)], env=env, capture_output=True, text=True, timeout=60)
    check(r.returncode == 0, '页面：轮到人时是「轮到你」，没有按默认执行，按发言格式填表交（' + (r.stderr + r.stdout).strip()[-300:] + '）')
    body = json.loads(req.read_text(encoding='utf-8'))
    s = wc.submit(run, body['result'], wait=True, client=c)
    check(s['status'] == 'done' and '兼容 IE 吗？' in prompts(c)[1], '页面交的发言让会议接着走，被点名的 AI 看到了问题')


def run():
    (ROOT / 'data/tmp').mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='wfmeet-', dir=ROOT / 'data/tmp') as folder:
        for case in (test_all_ai, test_human_seat, test_human_moderator, test_override_and_plain, test_page):
            tmp = Path(folder) / case.__name__
            tmp.mkdir()
            print(case.__name__)
            case(tmp)
    print('AI 会议：全部通过')


if __name__ == '__main__':
    run()
