import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))  # 项目根，run_all 不设 PYTHONPATH
"""整项目流程 workflow_demo/project_workflow.wf：离线假模型从头跑到尾，受控运行逐步执行（每步从头回放）。

剧本（18 次调用）：架构 v1 → 审查需修改 → 架构 v2 → 审查通过
→ 模块 core：分配两项 → 实现两项 → 模块验收需修改 → 返工 → 模块验收通过（交实际接口）
→ 模块 web：分配用了清单外的卡 → 分配调整 → 实现 → 模块验收通过
→ 集成测试（场景写成 tests/test_integration.py）→ 集成验收需修改 → 返工 → 集成验收通过。
核对：步骤顺序、每个模块各自返工、清空让模块验收只看本模块的实现记录、后面的模块分配时看得到前面模块的实际接口、
工程师拿到整个架构、跳转按模块分开算。所有假回复都过各自的格式校验。
"""
import json
import shutil
import tempfile
from pathlib import Path

from dsl.client import ScriptClient
from tools import workflow_ctl as wc

ROOT = Path(__file__).resolve().parents[2]


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print('  ✓', msg)


def arch(version, changes=False):
    a = {
        'summary': f'待办网站 {version}', 'stack': 'Python3 Flask SQLite pytest',
        'layout': [{'path': 'app/', 'purpose': '应用代码'}, {'path': 'tests/', 'purpose': '测试'}],
        'data_model': [{'name': 'todo', 'fields': ['id INTEGER 主键', 'title TEXT 非空'], 'notes': ''}],
        'modules': [
            {'name': 'core', 'title': '骨架和数据层', 'responsibility': '建表、待办的增删改查；不管网页',
             'files': ['app/db.py', 'tests/test_db.py'], 'depends_on': [],
             'provides': [{'name': 'create_todo', 'kind': '函数', 'signature': 'create_todo(title: str) -> int',
                           'behavior': '新建待办', 'errors': ['ValueError：标题为空']}],
             'uses': [], 'acceptance': ['pytest 通过', 'create_todo 返回新 id'], 'tests': ['tests/test_db.py']},
            {'name': 'web', 'title': '网页和接口', 'responsibility': '路由和页面；不直接写 SQL',
             'files': ['app/web.py', 'tests/test_web.py'], 'depends_on': ['core'],
             'provides': [{'name': 'POST /todos', 'kind': 'HTTP接口', 'signature': 'POST /todos {"title": str} -> {"id": int}',
                           'behavior': '新建', 'errors': ['400 标题为空']}],
             'uses': [{'ref': 'core.create_todo', 'signature': 'create_todo(title: str) -> int', 'behavior': '新建待办',
                       'errors': ['ValueError：标题为空']}], 'acceptance': ['POST /todos 返回 id'], 'tests': ['tests/test_web.py']},
        ],
        'integration': [{'name': '新建待办', 'steps': ['POST /todos', 'GET /todos'], 'expected': '列表里有它'}],
        'conventions': ['错误用 ValueError'], 'risks': [], 'open_questions': []}
    if changes:
        a['changes'] = [{'issue': '缺错误约定', 'action': '已修改', 'detail': '补了 400'}]
    return a


def review(decide):
    return {'decide': decide, 'summary': decide,
            'issues': [] if decide == '通过' else [{'location': 'web', 'problem': '缺错误', 'suggestion': '补',
                                                   'severity': '一般'}]}


def assign(*pairs):
    return {'tasks': [{'content': c, 'agent': a, 'reason': '按难度'} for c, a in pairs]}


def impl(what, need=None):
    return {'status': '完成', 'summary': f'做了{what}', 'changes': [{'target': f'{what}.py', 'action': '新增', 'detail': what}],
            'error_handling': [], 'verification': {'executed': True, 'method': 'pytest', 'result': '通过'},
            'open_issues': [], 'need_architect': need or []}


def mcheck(decide, sig, task=None):
    r = {'decide': decide, 'summary': f'模块验收{decide}',
         'checked': [{'item': 'pytest', 'result': '满足' if decide == '通过' else '不满足', 'evidence': '跑了'}],
         'not_verified': [],
         'deviations': [] if decide == '通过' else [f'约定 create_todo(title: str) -> int，代码是 {sig}，app/db.py']}
    if task:
        r['task'] = task
    return r


def final(decide, task=None):
    r = {'decide': decide, 'summary': f'集成{decide}',
         'checked': [{'item': '新建待办', 'result': '满足' if decide == '通过' else '不满足', 'evidence': '走了一遍'}],
         'not_verified': []}
    if task:
        r['task'] = task
    return r


REPLIES = [
    arch('v1'), review('需修改'), arch('v2', changes=True), review('通过'),
    assign(('建表和数据层函数', 'ENGINEER_LITE'), ('数据层测试', 'ENGINEER')),
    impl('core_db'), impl('core_test'),
    mcheck('需修改', 'create_todo(title)', task='标题为空要报 ValueError'), impl('core_fix'),
    mcheck('通过', 'create_todo(title: str) -> int'),
    assign(('路由和页面', 'ENGINEER_SENIOR')), assign(('路由和页面', 'ENGINEER')),
    impl('web_routes', need=['首页约定和骨架测试冲突']),
    {'decisions': [{'issue': '首页约定和骨架测试冲突', 'verdict': '修改约定', 'detail': 'GET / 改为 302 到 /todos', 'affected_modules': ['core', 'web']}]},
    mcheck('通过', 'POST /todos'),
    impl('itest'),
    final('需修改', task='列表页没显示新建的待办'), impl('web_fix'), final('通过'),
]
ROLES = ['ARCHITECT', 'ARCHITECT_GLM', 'ARCHITECT', 'ARCHITECT_GLM',
         'ARCHITECT', 'ENGINEER_LITE', 'ENGINEER', 'QA_ENGINEER', 'ENGINEER', 'QA_ENGINEER',
         'ARCHITECT', 'ARCHITECT', 'ENGINEER', 'ARCHITECT', 'QA_ENGINEER',
         'TEST_ENGINEER', 'QA_ENGINEER', 'ENGINEER', 'QA_ENGINEER']
ENTRY = ('用包 workflow\n设 content = 做待办网站\n设 stack = Python3+Flask\n设 goal = 不要后台\n'
         '设 project = todo_test\n设 test_cmd = .venv/bin/python -m pytest -q\n设 budget = 4\n'
         '设 roles = ENGINEER_LITE,ENGINEER,TEST_ENGINEER\n编排执行 project_workflow.wf\n'
         '存约定 work/todo_test/CONTRACT.json arch contract_notes 整项目流程\n')


def run():
    (ROOT / 'data/tmp').mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix='wfproj-', dir=ROOT / 'data/tmp'))
    try:
        demo = tmp / 'p'
        shutil.copytree(ROOT / 'workflow_demo', demo,
                        ignore=shutil.ignore_patterns('runs', 'work', '*.bak-*', '__pycache__'))
        (demo / 'run_test.zs').write_text(ENTRY, encoding='utf-8')
        c = ScriptClient(list(REPLIES))
        c.offline = True
        s = wc.start(demo, entry='run_test.zs', client=c)
        run_id = s['run']
        # 架构写完停下（结束后确认）再通过：被遍历的 arch.modules 不是按角色分配的清单，通过时不该去算成本
        wc.configure(run_id, confirm_after=['架构设计'])
        s = wc.execute(run_id, wait=True, client=c)
        check(s['pending']['step'] == 1 and s['pending']['phase'] == 'after', '架构设计停在结束后确认')
        s = wc.approve(run_id, attempt=1, wait=True, client=c)
        check(s['pending']['step'] == 2, '通过架构（遍历的模块清单没有角色，不算成本、不报错），往下到第 2 步')
        while s['status'] == 'waiting':          # 逐步：每一步都从头回放到停下的地方
            s = wc.execute(run_id, wait=True, client=c)
        check(s['status'] == 'done', f'跑完（{s.get("error")}）')
        check(len(c.calls) == 19, '一共 19 次调用')
        check([x['role'] for x in s['steps']] == ROLES,
              '步骤顺序：架构两轮 → core 返工一次 → web 调一次分配 → 集成测试 → 集成返工一次（返工后不重写集成测试）')

        prompt = [x.get('prompt', '') for x in c.calls]
        check('首页约定和骨架测试冲突' in prompt[13] and '约定确认' in prompt[13], '工程师报了 need_architect：先交架构师裁决')
        check('GET / 改为 302' in prompt[14] and 'GET / 改为 302' in prompt[16] and 'GET / 改为 302' not in prompt[12],
              '裁决记进 contract_notes：后面的模块验收、集成验收都看得到')
        check('"acceptance"' not in prompt[16] and '"provides"' in prompt[16], '集成验收只拿各模块的 provides，不拿验收条件')
        check('core.create_todo' in prompt[10] and 'create_todo(title: str) -> int' in prompt[10]
              and '骨架和数据层' not in prompt[10] and '代码是' not in prompt[10],
              '第二个模块分配时：从本模块的 uses 拿到要调的约定签名，不看别的模块的设计和验收记录')
        check('"current_module"' in prompt[4] and '网页和接口' not in prompt[4] and 'built' not in prompt[4],
              '第一个模块分配时：只给当前模块的约定，不给别的模块')
        check('create_todo(title: str) -> int' in prompt[5] and '待办网站' not in prompt[5] and '网页和接口' not in prompt[5]
              and '错误用 ValueError' in prompt[5], '工程师只拿本模块、约定这些，不拿整份架构（没有概要、别的模块、集成场景）')
        check('做了web_routes' in prompt[14] and '做了core_db' not in prompt[14],
              '模块验收只看本模块的实现记录（换模块时清空了）')
        check('做了core_fix' in prompt[9], '模块返工后的验收看得到返工记录')
        check(prompt[5].count('改测试的规矩') == 1 and '建表和数据层函数' in prompt[5] and '改测试的规矩' in prompt[8],
              '实现和返工的任务后面都接上改测试的规矩')
        check('integration 的每个场景' in prompt[15] and '列表里有它' in prompt[15] and '建表、待办的增删改查' in prompt[15] and '"acceptance"' not in prompt[15],
              '集成测试拿到集成场景和各模块的职责、接口（不拿验收条件）')
        check('POST /todos' in prompt[16] and 'create_todo(title: str) -> int' in prompt[16] and '做了itest' in prompt[16],
              '集成验收看得到各模块的约定和集成测试的记录')
        check('模块验收需修改' not in prompt[16] and '代码是' not in prompt[16], '模块验收的记录不往下传')

        t = json.loads((ROOT / run_id).read_text(encoding='utf-8'))
        jumps = [(e['target'], e['count'], (e.get('item') or {}).get('index')) for e in t['events'] if e['type'] == 'jump']
        check(jumps == [('a', 1, None), ('m', 1, 1), ('c', 1, 2), ('b', 1, None)],
              '跳转：架构修改一次、core 模块返工一次、web 分配调整一次（按模块记）、集成返工一次')
        clears = [e for e in t['events'] if e['type'] == 'clear']
        check([e['target'] for e in clears] == ['contract_notes', 'module_results', 'module_results'],
              '每个模块开头清空一次实现记录')
        spent = [e for e in t['events'] if e['type'] == 'cost']
        check(len(spent) == 3 and spent[1].get('status') == '超出', '成本合计三次：web 第一次分配用了清单外的卡')
        ct = json.loads((demo / 'work/todo_test/CONTRACT.json').read_text(encoding='utf-8'))
        check(ct['architecture']['summary'] == '待办网站 v2' and ct['source'] == '整项目流程'
              and ct['contract_notes'][0]['decisions'][0]['detail'] == 'GET / 改为 302 到 /todos',
              '跑完写了 CONTRACT.json：最终架构（v2）和架构师的裁决都在')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print('整项目流程：全部通过')


def run_rules():
    """真跑后补的两条规矩：模块验收有一项没满足就不能判通过；用 venv 的卡自动放行 .venv/bin/ 下的测试命令。"""
    from tools.wf_submit import validate
    from tools.dsl import DSLEngine
    from verbs.workflow import _agents as ag
    schema = json.loads((ROOT / 'workflow_demo/formats/module_acceptance.json').read_text(encoding='utf-8'))
    r = mcheck('通过', 'f()')
    r['checked'].append({'item': '场景', 'result': '未验证', 'evidence': '沙箱不让跑'})
    check(validate(schema, r) != [], '模块验收：有一项未验证还判通过，格式不收')
    r['decide'], r['task'] = '需修改', '补测试'
    check(validate(schema, r) == [], '同样的内容判需修改并给返工要求：收')
    r = mcheck('通过', 'f()')
    r['deviations'] = ['约定 f(x)，代码是 f()']
    check(validate(schema, r) != [], '模块验收：实现和约定有出入还判通过，格式不收')
    # survey1 真跑里漏过的两种：not_verified 不空还判通过；证据说只看到函数名还判满足
    r = mcheck('通过', 'f()')
    r['not_verified'] = ['git 报 dubious ownership，没能核对已有测试有没有被改']
    check(validate(schema, r) != [], '模块验收：not_verified 不为空还判通过，格式不收')
    r = mcheck('通过', 'f()')
    r['checked'][0]['evidence'] = 'accounts.py 用了 generate_password_hash；tests/test_accounts.py::test_hash 通过。我只看到该测试的函数名，没有读它的断言内容'
    check(validate(schema, r) != [], '模块验收：证据说只看到函数名还判满足，格式不收')
    r['checked'][0]['result'], r['decide'], r['task'] = '未验证', '需修改', '补看断言'
    check(validate(schema, r) == [], '同样的证据判未验证、需修改：收')
    r = mcheck('通过', 'f()')
    r['checked'][0]['evidence'] = 'db.py:12 `raise ValueError`；tests/test_db.py::test_empty 断言 `pytest.raises(ValueError)`，没有发现 skip'
    check(validate(schema, r) == [], '正常的证据（含「没有发现」）不误伤')
    r['checked'][0]['evidence'] = 'api/notifications.py:30 unread==\'1\' 才只看未读；test_unread_count 断言未读数为 3'
    check(validate(schema, r) == [], '证据里的「未读」（未读消息）不误伤')
    arch_schema = json.loads((ROOT / 'workflow_demo/formats/architecture.json').read_text(encoding='utf-8'))
    a = arch('v1')
    check(validate(arch_schema, a) == [], '架构：uses 写全约定，格式收')
    a['modules'][1]['uses'] = ['core.create_todo']
    check(validate(arch_schema, a) != [], '架构：uses 只写名字不写签名，格式不收')
    engine = DSLEngine(client=ScriptClient([]), workdir=ROOT / 'workflow_demo', verbose=False)
    engine.vars['project'] = 'rules_check'
    try:
        for card in ('TEST_ENGINEER', 'QA_ENGINEER', 'ENGINEER'):
            tools = ag.load_agent(engine, card)['agentic']['allowed_tools']
            check('Bash(.venv/bin/python -m pytest:*)' in tools and 'Bash(python -m pytest:*)' in tools,
                  f'{card}：venv 卡同时放行 python -m pytest 和 .venv/bin/python -m pytest')
    finally:
        shutil.rmtree(ROOT / 'workflow_demo/work/rules_check', ignore_errors=True)


if __name__ == '__main__':
    run_rules()
    run()
