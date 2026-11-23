import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))  # 项目根，run_all 不设 PYTHONPATH
"""改项目流程 workflow_demo/change_workflow.wf（入口 run_change.zs）：离线假模型从头跑到尾，不调真模型。

项目 work/todo_chg 里有一份接口约定（core、web 两个模块，带一条老裁决），需求是加截止日期。剧本（21 次调用）：
基线核对（有一处 drift）→ 改动方案 v1 → 评审会（ARCHITECT_GLM 发言并点名追问 ARCHITECT、ARCHITECT 回答、REVIEWER_GPT 发言）
→ 主持人判断可以结论 → 结论有修改项 → 方案修改 v2
→ core（修改）：分配 → 实现（报告已有测试和新签名矛盾）→ 架构师裁决 → 模块验收需修改 → 返工 → 通过
→ web（修改）：分配 → 实现 → 通过 → 新场景测试 → 集成验收需修改 → 返工 → 通过 → 合并回约定。
核对：步骤和角色；基线拿到约定；方案拿到约定、老裁决和 drift；评审看得到方案和约定；方案修改拿到结论；
模块循环只走方案里改动的模块、用修改后的方案；工程师只拿本模块的新约定；裁决接在老裁决后面往下传；
模块验收和集成验收看得到基线；集成验收看得到没改的模块的原约定和 keep；跑完约定按方案合并写回。
另外：没有约定时入口直接停下不调模型；人进评审名单时停下等人；入口参数能传。
"""
import copy
import json
import shutil
import sys
import tempfile
from pathlib import Path

from dsl.client import ScriptClient
from tools import trace_server as ts
from tools import workflow_ctl as wc
from tools.dsl import DSLEngine

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_wf_project import arch, assign, impl, mcheck, final  # noqa: E402

NEW_SIG = 'create_todo(title: str, due: str | None = None) -> int'


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print('  ✓', msg)


def speech(text, agree=False, ask='', question=''):
    return {'speech': text, 'agree': agree, 'ask': ask, 'question': question}


def baseline():
    return {'summary_line': '42 passed in 3.1s', 'passed': 42, 'failed': 0, 'failing_tests': [],
            'drift': [{'module': 'web', 'item': 'GET /', 'contract': '302 到 /todos', 'code': '直接渲染首页', 'file': 'app/web.py'}],
            'summary': '待办网站，测试都过'}


def plan(v, changes=False, attendee_fix=False):
    base = arch('v2')
    core, web = copy.deepcopy(base['modules'])
    core['provides'][0]['signature'] = NEW_SIG
    core['status'], core['change'] = '修改', f'create_todo 加可选参数 due（{v}）'
    web['uses'][0]['signature'] = NEW_SIG
    web['status'], web['change'] = '修改', 'POST /todos 收 due，列表按 due 排序'
    p = {'summary': f'加截止日期 {v}', 'project_summary': '带截止日期的待办网站', 'order': ['core', 'web'],
         'modules': [core, web], 'removed': [], 'layout': base['layout'],
         'data_model': [{'name': 'todo', 'fields': ['id INTEGER 主键', 'title TEXT 非空', 'due TEXT 可空'], 'notes': '启动时给老库补 due 列'}],
         'integration': base['integration'] + [{'name': '按截止日期排序', 'steps': ['新建两条带 due 的', 'GET /todos?sort=due'], 'expected': '早的在前'}],
         'conventions': base['conventions'], 'keep': ['不带 due 的 POST /todos 照常能用', '老库启动时补列，不丢数据'],
         'risks': [], 'open_questions': []}
    if changes:
        p['changes'] = [{'issue': '老库迁移没写', 'action': '已修改', 'detail': '数据模型 notes 和 keep 写了补列'}]
    return p


def decision(todo):
    return {'decision': '补上老库迁移' if todo else '方案不用改', 'reasons': ['REVIEWER_GPT 指出老库没有 due 列'],
            'dissent': [], 'todo': todo, 'summary': '评审结束'}


CHECK_DONE = {'done': '是', 'disagreements': [], 'summary': '大家都同意'}
OLD_NOTES = [{'module': 'web', 'decisions': [{'issue': '首页', 'verdict': '修改约定', 'detail': '老裁决：GET / 302 到 /todos',
                                              'affected_modules': ['web']}]}]
REPLIES = [
    baseline(), plan('v1'),
    speech('core 的签名要兼容老调用', ask='ARCHITECT', question='不带 due 的老调用还能用吗？'),
    speech('due 有默认值 None，老调用照常', agree=True), speech('老库没有 due 列，要迁移'), CHECK_DONE,
    decision([{'who': 'ARCHITECT', 'what': '写清老库启动时补 due 列'}]), plan('v2', changes=True),
    assign(('create_todo 加 due', 'ENGINEER_LITE')),
    impl('core_due', need=['tests/test_db.py 断言 create_todo 只收 title，和新签名矛盾']),
    {'decisions': [{'issue': '老测试和新签名', 'verdict': '修改约定', 'detail': 'DUE_RULING：老测试保留，新增带 due 的测试',
                    'affected_modules': ['core']}]},
    mcheck('需修改', 'create_todo(title, due)', task='due 要校验日期格式'), impl('core_fix'), mcheck('通过', NEW_SIG),
    assign(('POST /todos 收 due', 'ENGINEER')), impl('web_due'), mcheck('通过', 'POST /todos'),
    impl('itest'), final('需修改', task='按截止日期排序时没有 due 的没排在最后'), impl('web_fix'), final('通过'),
]
ROLES = ['QA_ENGINEER', 'ARCHITECT', 'ARCHITECT_GLM', 'ARCHITECT', 'REVIEWER_GPT', 'MODERATOR', 'MODERATOR', 'ARCHITECT',
         'ARCHITECT', 'ENGINEER_LITE', 'ARCHITECT', 'QA_ENGINEER', 'ENGINEER', 'QA_ENGINEER',
         'ARCHITECT', 'ENGINEER', 'QA_ENGINEER', 'TEST_ENGINEER', 'QA_ENGINEER', 'ENGINEER', 'QA_ENGINEER']
NAMES = ['基线核对', '改动方案', '评审发言', '评审追问', '评审发言', '评审判断', '评审结论', '方案修改',
         '模块任务分配', '任务实现', '约定确认', '模块验收', '模块返工', '模块验收',
         '模块任务分配', '任务实现', '模块验收', '新场景测试', '集成验收', '集成返工', '集成验收']


def load_contract_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location('_contract_c', ROOT / 'verbs/workflow/_contract.py')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def copy_demo(tmp, with_contract=True, project='todo_chg'):
    demo = tmp / 'c'
    shutil.copytree(ROOT / 'workflow_demo', demo, ignore=shutil.ignore_patterns('runs', 'work', '*.bak-*', '__pycache__'))
    if with_contract:
        load_contract_module().save(demo / f'work/{project}/CONTRACT.json', arch('v2'), OLD_NOTES, '整项目流程')
    return demo


def client(replies):
    c = ScriptClient(list(replies))
    c.offline = True
    return c


def test_full(tmp):
    demo = copy_demo(tmp)
    c = client(REPLIES)
    s = wc.start(demo, entry='run_change.zs', mode='auto', wait=True, client=c,
                 vars={'project': 'todo_chg', 'review_attendees': 'ARCHITECT_GLM,REVIEWER_GPT'})
    check(s['status'] == 'done', f'全自动跑完（{s.get("error")}）')
    check(len(c.calls) == 21, f'一共 21 次调用（{len(c.calls)}）')
    check([x['role'] for x in s['steps']] == ROLES, '角色顺序')
    check([x['name'] for x in s['steps']] == NAMES, '步骤名顺序：基线 → 方案 → 评审会 → 改方案 → 两个改动模块 → 新场景测试 → 集成')
    p = [x.get('prompt', '') for x in c.calls]
    check('待办网站 v2' in p[0] and '不改任何文件' in p[0] and '加截止日期' in p[0], '基线核对拿到约定和需求，只看不改')
    check('待办网站 v2' in p[1] and '老裁决' in p[1] and '直接渲染首页' in p[1], '改动方案拿到约定、老裁决和基线里的 drift')
    check('加截止日期 v1' in p[2] and '待办网站 v2' in p[2], '评审的人看得到方案和现在的约定')
    check('不带 due 的老调用还能用吗？' in p[3], '被点名的架构师看得到问题')
    check('写清老库启动时补 due 列' in p[7] and '加截止日期 v1' in p[7], '方案修改拿到评审结论和上一版方案')
    check('"current_module"' in p[8] and 'create_todo 加可选参数 due（v2）' in p[8] and 'POST /todos 收 due，列表按 due 排序' not in p[8],
          '模块循环用修改后的方案（v2），分配只拿本模块的新约定（status、change）')
    check(NEW_SIG in p[9] and '在已有项目上改' in p[9] and '待办网站 v2' not in p[9], '工程师拿到本模块的新签名，不拿整份约定')
    check('和新签名矛盾' in p[10] and '约定确认' in p[10] and '老裁决' in p[10], '工程师报告约定问题：交架构师裁决，看得到老裁决')
    check('DUE_RULING' in p[11] and '老裁决' in p[11] and '42 passed' in p[11], '模块验收看得到新裁决、老裁决和基线')
    check('DUE_RULING' in p[15] and 'DUE_RULING' not in p[9], '裁决只往后传：后面的模块看得到')
    check('做了web_due' in p[16] and '做了core_due' not in p[16], '模块验收只看本模块的实现记录（换模块时清空）')
    check('按截止日期排序' in p[17] and '早的在前' in p[17] and '文件已有的测试保留' in p[17], '新场景测试拿到新场景，已有测试不删不改')
    check('42 passed' in p[18] and '不带 due 的 POST /todos 照常能用' in p[18] and '"changed"' in p[18] and '"modules"' in p[18]
          and '做了itest' in p[18], '集成验收看得到基线、keep、改动的模块和原约定的模块、新场景测试记录')
    check('没有 due 的没排在最后' in p[19], '集成返工按验收的 task 来')
    t = json.loads((Path(s['run']) if Path(s['run']).is_absolute() else ROOT / s['run']).read_text(encoding='utf-8'))
    jumps = [(e['target'], e['count']) for e in t['events'] if e['type'] == 'jump']
    check(jumps == [('m', 1), ('b', 1)], '跳转：core 返工一次、集成返工一次；评审一轮就结论')
    ct = json.loads((demo / 'work/todo_chg/CONTRACT.json').read_text(encoding='utf-8'))
    a = ct['architecture']
    check(a['summary'] == '带截止日期的待办网站' and a['modules'][0]['provides'][0]['signature'] == NEW_SIG
          and a['modules'][1]['uses'][0]['signature'] == NEW_SIG and 'status' not in a['modules'][0], '约定按方案合并：两个模块换成新版')
    check(a['data_model'][0]['fields'][-1] == 'due TEXT 可空' and a['integration'][-1]['name'] == '按截止日期排序', '数据模型和集成场景换成新版')
    check([n['module'] for n in ct['contract_notes']] == ['web', 'core'] and 'DUE_RULING' in json.dumps(ct['contract_notes'], ensure_ascii=False),
          '裁决：老裁决在前，这次的接在后面')
    h = ct['history'][-1]
    check(h['source'] == '改项目流程' and h['changed'] == ['core', 'web'] and h['summary'] == '加截止日期 v2' and ct['warnings'] == [],
          'history 记了这次改动；uses 都对得上')


def test_no_contract(tmp):
    demo = copy_demo(tmp, with_contract=False)
    c = client([])
    e = DSLEngine(client=c, workdir=demo, verbs_root=ROOT / 'verbs', verbose=False)
    e.vars['project'] = 'nothing_here'
    e.run_file('run_change.zs')
    check(e.halted and e.halted['status'] == '失败' and 'CONTRACT.json' in e.halted['reason'] and not c.calls,
          f'项目里没有约定：入口直接停下，说清要先生成约定，不调模型（{e.halted}）')


def test_human(tmp):
    demo = copy_demo(tmp)
    c = client([baseline(), plan('v1')])
    s = wc.start(demo, entry='run_change.zs', mode='auto', wait=True, client=c,
                 vars={'project': 'todo_chg', 'review_attendees': 'HUMAN,REVIEWER_GPT'})
    check(s['status'] == 'waiting' and s['pending']['role'] == 'HUMAN' and s['pending']['name'] == '评审发言',
          '人进了方案评审名单：轮到人发言时停下等')
    check('加截止日期 v1' in json.dumps(s['pending'], ensure_ascii=False), '人看得到改动方案')
    rows = {r['name']: r for r in ts.list_runs(demo / 'runs')}
    check(rows[Path(s['run']).name]['meeting'] == 'embedded', '运行清单标成「流程里有会」，会议页列得出来')


def test_entry(tmp):
    demo = copy_demo(tmp)
    params = {p['name']: p for p in {e['entry']: e for e in ts.list_entries(demo)}['run_change.zs']['params']}
    check(set(params) == {'content', 'project', 'review_attendees', 'moderator'} and not any(p['required'] for p in params.values())
          and params['content']['default'] and params['review_attendees']['default'] == 'ARCHITECT_GLM,REVIEWER_GPT',
          '入口声明了 content、project、review_attendees、moderator，都可选，有默认值（会议页「交给流程」能用）')
    c = client([baseline()])
    s = wc.start(demo, entry='run_change.zs', mode='step', client=c,
                 vars={'project': 'todo_chg', 'content': '会议结论：加一个导出 CSV 的接口'})
    check(s['pending']['name'] == '基线核对' and '会议结论：加一个导出 CSV 的接口' in json.dumps(s['pending'], ensure_ascii=False),
          '传的需求进了第一步')


def test_cards():
    from verbs.workflow import _agents as ag
    e = DSLEngine(client=ScriptClient([]), workdir=ROOT / 'workflow_demo', verbose=False)
    for name in ('ARCHITECT', 'ARCHITECT_GPT'):
        prof = ag.load_agent(e, name)
        check('改已有项目的改动方案' in prof['system'], f'{name} 带改动方案的技能（change.md）')
    for fmt in ('change_plan', 'baseline'):
        check((ROOT / f'workflow_demo/formats/{fmt}.json').is_file(), f'格式 {fmt} 在')
    from tools.wf_submit import validate
    schema = json.loads((ROOT / 'workflow_demo/formats/change_plan.json').read_text(encoding='utf-8'))
    check(validate(schema, plan('v1')) == [], '剧本里的改动方案过 change_plan 格式校验')
    bad = plan('v1')
    del bad['modules'][0]['status']
    check(validate(schema, bad) != [], '改动的模块没写 status：格式不收')


def run():
    (ROOT / 'data/tmp').mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='wfchg-', dir=ROOT / 'data/tmp') as folder:
        for case in (test_full, test_no_contract, test_human, test_entry):
            tmp = Path(folder) / case.__name__
            tmp.mkdir()
            print(case.__name__)
            case(tmp)
    print('test_cards')
    test_cards()
    print('改项目流程：全部通过')


if __name__ == '__main__':
    run()
