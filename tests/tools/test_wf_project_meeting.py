import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))  # 项目根，run_all 不设 PYTHONPATH
"""整项目流程开会版 workflow_demo/project_meeting_workflow.wf：离线假模型从头跑到尾，不调真模型。

剧本（18 次调用）：架构 v1 → 架构评审会第一轮（ARCHITECT 发言、ARCHITECT_GLM 发言并点名追问 ARCHITECT、ARCHITECT 回答）
→ 主持人判断还要再议（有分歧）→ 第二轮两人都认可 → 主持人判断可以结论 → 结论有修改项、有保留意见 → 架构修改 v2
→ core：分配 → 实现 → 验收通过 → web：分配 → 实现 → 验收通过 → 集成测试 → 集成验收通过。
核对：步骤顺序和角色；评审的人看得到架构和前面的发言；第二轮看得到上一轮的分歧；被追问的人看得到问题；
架构修改拿到结论；后面用的是修改后的架构；会议纪要不传给工程师；集成验收看得到保留意见。
另外：结论没有修改项就不改架构；HUMAN 参会 / 主持时轮到人就停下；入口参数能传；后半段和整项目流程一字不差。
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

from dsl.client import ScriptClient
from tools import trace_server as ts
from tools import workflow_ctl as wc

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_wf_project import arch, assign, impl, mcheck, final  # noqa: E402  复用整项目流程测试的假回复


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print('  ✓', msg)


def speech(text, agree=False, ask='', question=''):
    return {'speech': text, 'agree': agree, 'ask': ask, 'question': question}


def decision(todo, dissent=()):
    return {'decision': 'web 补上标题为空的 400' if todo else '架构不用改', 'reasons': ['ARCHITECT_GLM 指出缺错误约定'],
            'dissent': list(dissent), 'todo': todo, 'summary': '评审结束'}


CHECK_DONE = {'done': '是', 'disagreements': [], 'summary': '大家都同意'}
CHECK_MORE = {'done': '否', 'disagreements': ['web 的错误约定没定'], 'summary': '错误约定还有分歧'}
REPLIES = [
    arch('v1'),
    speech('架构如上，core 先搭骨架'), speech('web 缺错误约定', ask='ARCHITECT', question='标题为空时 POST /todos 返回什么？'),
    speech('应该返回 400，同意补', agree=True), CHECK_MORE,
    speech('第二轮：按 400 补', agree=True), speech('可以了', agree=True), CHECK_DONE,
    decision([{'who': 'ARCHITECT', 'what': 'web 的 POST /todos 补标题为空返回 400'}],
             dissent=['ARCHITECT_GLM：担心 core 和 web 拆得太细，接口改动要两边一起改']),
    arch('v2', changes=True),
    assign(('建表和数据层函数', 'ENGINEER_LITE')), impl('core_db'), mcheck('通过', 'create_todo(title: str) -> int'),
    assign(('路由和页面', 'ENGINEER')), impl('web_routes'), mcheck('通过', 'POST /todos'),
    impl('itest'), final('通过'),
]
ROLES = ['ARCHITECT', 'ARCHITECT', 'ARCHITECT_GLM', 'ARCHITECT', 'MODERATOR',
         'ARCHITECT', 'ARCHITECT_GLM', 'MODERATOR', 'MODERATOR', 'ARCHITECT',
         'ARCHITECT', 'ENGINEER_LITE', 'QA_ENGINEER', 'ARCHITECT', 'ENGINEER', 'QA_ENGINEER',
         'TEST_ENGINEER', 'QA_ENGINEER']
NAMES = ['架构设计', '评审发言', '评审发言', '评审追问', '评审判断',
         '评审发言', '评审发言', '评审判断', '评审结论', '架构修改',
         '模块任务分配', '任务实现', '模块验收', '模块任务分配', '任务实现', '模块验收',
         '集成测试', '集成验收']


def entry(attendees='ARCHITECT,ARCHITECT_GLM', moderator=None):
    return ('用包 workflow\n设 content = 做待办网站\n设 stack = Python3+Flask\n设 goal = 不要后台\n'
            '设 project = todo_meet_test\n设 test_cmd = .venv/bin/python -m pytest -q\n设 budget = 4\n'
            '设 roles = ENGINEER_LITE,ENGINEER,TEST_ENGINEER\n'
            f'设 review_attendees = {attendees}\n' + (f'设 moderator = {moderator}\n' if moderator else '')
            + '编排执行 project_meeting_workflow.wf\n存约定 work/todo_meet_test/CONTRACT.json arch contract_notes 测试\n')


def copy(tmp):
    demo = tmp / 'p'
    shutil.copytree(ROOT / 'workflow_demo', demo, ignore=shutil.ignore_patterns('runs', 'work', '*.bak-*', '__pycache__'))
    return demo


def client(replies):
    c = ScriptClient(list(replies))
    c.offline = True
    return c


def trace(run):
    p = Path(run) if Path(run).is_absolute() else ROOT / run
    return json.loads(p.read_text(encoding='utf-8'))


def test_full(tmp):
    demo = copy(tmp)
    (demo / 'run_pm.zs').write_text(entry(), encoding='utf-8')
    c = client(REPLIES)
    s = wc.start(demo, entry='run_pm.zs', mode='auto', wait=True, client=c)
    check(s['status'] == 'done', f'全自动跑完，中间不停（{s.get("error")}）')
    check(len(c.calls) == 18, '一共 18 次调用')
    check([x['role'] for x in s['steps']] == ROLES, '角色顺序：架构 → 评审两轮（第一轮有追问）→ 结论 → 改架构 → 两个模块 → 集成')
    check([x['name'] for x in s['steps']] == NAMES, '步骤名顺序')
    p = [x.get('prompt', '') for x in c.calls]
    check('待办网站 v1' in p[1] and '待办网站 v1' in p[2] and '架构评审会' in p[1], '评审的人看得到待评审的架构')
    check('架构如上' in p[2], '后发言的人看得到前面的发言')
    check('标题为空时 POST /todos 返回什么？' in p[3], '被点名的架构师看得到问题')
    check('同意补' in p[4], '主持人看得到追问的回答')
    check('web 的错误约定没定' in p[5] and 'web 的错误约定没定' in p[6], '第二轮看得到主持人上一轮指出的分歧')
    check('web 的 POST /todos 补标题为空返回 400' in p[9] and '待办网站 v1' in p[9], '架构修改拿到评审结论和原架构')
    check('待办网站 v2' in p[17], '后面用的是修改后的架构（v2）')
    check(all('架构如上' not in x and '拆得太细' not in x for x in p[10:17]),
          '会议纪要和保留意见不传给分配、工程师、模块验收和集成测试（只拿本模块的约定）')
    check('拆得太细' in p[17] and 'dissent' in p[17] and '"todo"' not in p[17],
          '集成验收看得到评审结论的保留意见（只给 decision 和 dissent）')
    t = trace(s['run'])
    jumps = [(e['target'], e['count']) for e in t['events'] if e['type'] == 'jump']
    check(jumps == [('r', 1)], '跳转：评审会第一轮没结论，跳回再议一次')
    ct = json.loads((demo / 'work/todo_meet_test/CONTRACT.json').read_text(encoding='utf-8'))
    check(ct['architecture']['summary'] == '待办网站 v2' and [m['name'] for m in ct['architecture']['modules']] == ['core', 'web']
          and 'changes' not in ct['architecture'] and ct['warnings'] == [],
          '跑完写了 CONTRACT.json：是修改后的架构（v2），去掉了 changes，uses 都对得上')


def test_no_change(tmp):
    demo = copy(tmp)
    (demo / 'run_pm.zs').write_text(entry('REVIEWER_GPT'), encoding='utf-8')
    c = client([arch('v1'), speech('没问题', agree=True), CHECK_DONE, decision([]),
                assign(('建表', 'ENGINEER_LITE')), impl('core'), mcheck('通过', 'x'),
                assign(('路由', 'ENGINEER')), impl('web'), mcheck('通过', 'y'), impl('itest'), final('通过')])
    s = wc.start(demo, entry='run_pm.zs', mode='auto', wait=True, client=c)
    check(s['status'] == 'done' and '架构修改' not in [x['name'] for x in s['steps']],
          f'评审结论没有修改项：不改架构，直接做模块（{s.get("error")}）')


def test_human(tmp):
    demo = copy(tmp)
    (demo / 'run_pm.zs').write_text(entry('ARCHITECT,HUMAN'), encoding='utf-8')
    c = client([arch('v1'), speech('架构如上')])
    s = wc.start(demo, entry='run_pm.zs', mode='auto', wait=True, client=c)
    check(s['status'] == 'waiting' and s['pending']['role'] == 'HUMAN' and s['pending']['name'] == '评审发言',
          '人进了评审名单：轮到人发言时停下等')
    check('待办网站 v1' in json.dumps(s['pending'], ensure_ascii=False), '人看得到待评审的架构')
    (demo / 'run_pm2.zs').write_text(entry('REVIEWER_GPT', moderator='HUMAN'), encoding='utf-8')
    c = client([arch('v1'), speech('没问题', agree=True)])
    s = wc.start(demo, entry='run_pm2.zs', mode='auto', wait=True, client=c)
    check(s['status'] == 'waiting' and s['pending']['role'] == 'HUMAN' and s['pending']['name'] == '评审判断',
          '人当主持人：判断这一步停下等人')
    rows = {r['name']: r for r in ts.list_runs(demo / 'runs')}
    check(rows[Path(s['run']).name]['meeting'] == 'embedded', '运行清单标成「流程里有会」，会议页列得出来')


def test_entry(tmp):
    demo = copy(tmp)
    params = {p['name']: p for p in {e['entry']: e for e in ts.list_entries(demo)}['run_project_meeting.zs']['params']}
    check(set(params) == {'content', 'project', 'review_attendees', 'moderator'} and not any(p['required'] for p in params.values()),
          '入口声明了 content、project、review_attendees、moderator，都可选')
    check(params['review_attendees']['default'] == 'ARCHITECT,ARCHITECT_GLM,REVIEWER_GPT' and params['project']['default'],
          '评审名单和项目名有默认值（会议页「交给流程」时预先填上）')
    c = client([arch('v1')])
    s = wc.start(demo, entry='run_project_meeting.zs', mode='auto', wait=True, client=c,
                 vars={'content': '会议结论：做一个记账网站', 'project': 'ledger_meet1', 'review_attendees': 'HUMAN'})
    check('会议结论：做一个记账网站' in c.calls[0]['prompt'] and 'ledger_meet1' in c.calls[0]['prompt'], '传的需求和项目名进了架构设计')
    check(s['status'] == 'waiting' and s['pending']['role'] == 'HUMAN', '传的评审名单生效：架构出来后轮到人')


def test_same_tail():
    """模块开发以后的步骤和 project_workflow.wf 一字不差（只在集成验收多给评审结论）：改那边忘了改这边就报。"""
    a = (ROOT / 'workflow_demo/project_workflow.wf').read_text(encoding='utf-8')
    b = (ROOT / 'workflow_demo/project_meeting_workflow.wf').read_text(encoding='utf-8')
    anchor = '遍历 module 于 arch.modules\n'
    ta, tb = a[a.index(anchor):], b[b.index(anchor):]
    tb = tb.replace(' arch_review=arch_review[decision,dissent]', '').replace(
        '参考文本的 arch_review 是架构评审会的结论：dissent 里有人保留意见的地方逐条看实现有没有出问题，出了问题算不满足。', '')
    check(ta == tb, '模块开发、集成测试、集成验收和整项目流程一致')
    check('\n架构审查\n' not in b and '\n    角色 ARCHITECT_GLM\n' not in b, '没有单人架构审查这一步了（由评审会代替）')


def test_astra_architect(tmp):
    """ARCHITECT_GPT：Codex gpt-6.2-astra 的架构师，技能照 ARCHITECT 复制；用 roles 换掉流程里的 ARCHITECT。"""
    from verbs.workflow import _agents as ag
    from tools.dsl import DSLEngine
    agents = ROOT / 'workflow_demo/agents'
    e = DSLEngine(client=ScriptClient([]), workdir=ROOT / 'workflow_demo', verbose=False)
    prof = ag.load_agent(e, 'ARCHITECT_GPT')
    check(prof['model'].startswith('cli:codex/gpt-6.2-astra') and not prof['tools'] and prof['agentic'] is None,
          f'ARCHITECT_GPT 能加载：Astra（{prof["model"]}）、不带工具（只交 JSON）')
    a = json.loads((agents / 'ARCHITECT/agent.json').read_text(encoding='utf-8'))
    g = json.loads((agents / 'ARCHITECT_GPT/agent.json').read_text(encoding='utf-8'))
    same = g['skills'] == a['skills'] and all(
        (agents / 'ARCHITECT' / f).read_text(encoding='utf-8') == (agents / 'ARCHITECT_GPT' / f).read_text(encoding='utf-8')
        for f in ['SOUL.md'] + a['skills'])
    check(same, 'SOUL.md 和技能跟 ARCHITECT 一字不差（改那边忘了改这边就报）')
    demo = copy(tmp)
    (demo / 'run_pm.zs').write_text(entry('ARCHITECT_GPT,ARCHITECT_GLM'), encoding='utf-8')
    c = client([arch('v1'), speech('这是我的架构', agree=True)])
    s = wc.start(demo, entry='run_pm.zs', mode='step', client=c, roles={'ARCHITECT': 'ARCHITECT_GPT'})
    pd = s['pending']
    check(pd['name'] == '架构设计' and pd.get('card') == 'ARCHITECT_GPT' and str(pd.get('model', '')).startswith('cli:codex/gpt-6.2-astra'),
          f'roles={{"ARCHITECT": "ARCHITECT_GPT"}}：架构设计交给 Astra 架构师（card={pd.get("card")} model={pd.get("model")}）')


def run():
    (ROOT / 'data/tmp').mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='wfpm-', dir=ROOT / 'data/tmp') as folder:
        for case in (test_full, test_no_change, test_human, test_entry, test_astra_architect):
            tmp = Path(folder) / case.__name__
            tmp.mkdir()
            print(case.__name__)
            case(tmp)
    print('test_same_tail')
    test_same_tail()
    print('整项目流程开会版：全部通过')


if __name__ == '__main__':
    run()
