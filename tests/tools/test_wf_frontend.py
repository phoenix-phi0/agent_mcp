import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))  # 项目根，run_all 不设 PYTHONPATH
"""前端流程 workflow_demo/frontend_workflow.wf：离线假模型从头跑到尾，不调真模型。

剧本（18 次调用）：界面设计 v1 → 评审会（DESIGNER 发言、REVIEWER_GPT 发言并点名追问 DESIGNER、DESIGNER 回答）
→ 主持人判断可以结论 → 结论有修改项 → 设计修改 v2
→ 骨架页：实现 → 页面验收需修改 → 返工 → 验收通过
→ 列表页：实现（报告设计和后端对不上）→ 设计师裁决 → 验收通过
→ 端到端测试 → 整体验收需修改 → 返工 → 整体验收通过。
核对：步骤顺序和角色；评审的人看得到设计、被追问的人看得到问题；设计修改拿到结论；页面循环用的是修改后的设计；
工程师只拿本页设计和全前端约定（拿不到别的页、场景）；裁决只往后传；页面验收只看本页的实现记录；跳转按页面分开算。
另外：评审结论没有修改项就不改设计；HUMAN 进了评审名单就停下等人发言（全自动之外的人工介入）。
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


def page(name, title, states, acceptance):
    return {'name': name, 'title': title, 'files': [f'web/{name}.html', f'web/js/{name}.js'],
            'purpose': f'{title}；不管别的页', 'apis': [{'method': 'GET', 'path': '/api/surveys', 'request': '',
                                                     'response': '{"surveys": [...]}', 'errors': ['401 未登录']}],
            'elements': [f'#{name}-root'], 'actions': [{'do': '打开页面', 'expect': f'看到{title}'}],
            'states': states, 'acceptance': acceptance, 'tests': [f'web/tests/{name}.test.js']}


def design(version, changes=False):
    d = {'summary': f'问卷前端 {version}', 'stack': '纯 HTML/JS', 'layout': [{'path': 'web/', 'purpose': '前端'}],
         'serve': 'node web/serve.js，/api 转发给后端', 'test_harness': 'web/run_tests.sh 起临时后端和开发服务，jsdom 跑 web/tests',
         'shared': [{'name': 'api', 'file': 'web/js/api.js', 'provides': 'api(method, path, body) -> Promise<json>'}],
         'pages': [page('skeleton', '前端骨架', [], ['冒烟测试通过']),
                   page('surveys', '我的问卷列表', ['没有问卷时显示 #empty'] if version == 'v2' else [], ['列出自己的问卷'])],
         'flows': [{'name': '建问卷再填写', 'steps': [{'page': 'surveys', 'do': '新建', 'expect': '列表里出现它'}]}],
         'conventions': ['错误显示在 #error'], 'open_questions': []}
    if changes:
        d['changes'] = [{'issue': '列表页缺空数据状态', 'action': '已修改', 'detail': '加了 #empty'}]
    return d


def speech(text, agree=False, ask='', question=''):
    return {'speech': text, 'agree': agree, 'ask': ask, 'question': question}


def impl(what, need=None):
    return {'status': '完成', 'summary': f'做了{what}', 'changes': [{'target': f'web/{what}.js', 'action': '新增', 'detail': what}],
            'error_handling': [], 'verification': {'executed': True, 'method': './web/run_tests.sh', 'result': '3 passed'},
            'open_issues': [], 'need_architect': need or []}


def pcheck(decide, task=None):
    r = {'decide': decide, 'summary': f'页面验收{decide}',
         'checked': [{'item': '页面测试', 'result': '满足' if decide == '通过' else '不满足', 'evidence': 'web/tests 跑了'}],
         'not_verified': [], 'deviations': [] if decide == '通过' else ['设计要 #error，代码里没有，web/js/api.js']}
    if task:
        r['task'] = task
    return r


def final(decide, task=None):
    r = {'decide': decide, 'summary': f'整体{decide}',
         'checked': [{'item': '建问卷再填写', 'result': '满足' if decide == '通过' else '不满足', 'evidence': '走了一遍'}],
         'not_verified': []}
    if task:
        r['task'] = task
    return r


def decision(todo):
    return {'decision': '列表页补空数据状态' if todo else '设计不用改', 'reasons': ['REVIEWER_GPT 指出列表页缺空状态'],
            'dissent': [], 'todo': todo, 'summary': '评审结束'}


CHECK_DONE = {'done': '是', 'disagreements': [], 'summary': '大家都同意'}
REPLIES = [
    design('v1'),
    speech('设计覆盖了需求'), speech('列表页缺空数据状态', ask='DESIGNER', question='没有问卷时显示什么？'),
    speech('确实漏了，同意补', agree=True), CHECK_DONE,
    decision([{'who': 'DESIGNER', 'what': '列表页补空数据状态'}]), design('v2', changes=True),
    impl('skeleton'), pcheck('需修改', task='api.js 出错时要显示在 #error'), impl('skeleton_fix'), pcheck('通过'),
    impl('surveys', need=['后端列表接口的字段叫 items 不叫 surveys']),
    {'decisions': [{'issue': '列表字段名', 'verdict': '修改约定', 'detail': '列表接口以后端为准用字段ITEMS_FIELD',
                    'affected_modules': ['surveys']}]},
    pcheck('通过'),
    impl('e2e'), final('需修改', task='新建问卷后列表没刷新'), impl('e2e_fix'), final('通过'),
]
ROLES = ['DESIGNER', 'DESIGNER', 'REVIEWER_GPT', 'DESIGNER', 'MODERATOR', 'MODERATOR', 'DESIGNER',
         'FRONTEND_ENGINEER', 'FRONTEND_QA', 'FRONTEND_ENGINEER', 'FRONTEND_QA',
         'FRONTEND_ENGINEER', 'DESIGNER', 'FRONTEND_QA',
         'FRONTEND_ENGINEER', 'FRONTEND_QA', 'FRONTEND_ENGINEER', 'FRONTEND_QA']
NAMES = ['界面设计', '评审发言', '评审发言', '评审追问', '评审判断', '评审结论', '设计修改',
         '页面实现', '页面验收', '页面返工', '页面验收', '页面实现', '设计确认', '页面验收',
         '端到端测试', '整体验收', '整体返工', '整体验收']


def entry(attendees='DESIGNER,REVIEWER_GPT'):
    return ('用包 workflow\n设 content = 给问卷网站做前端\n设 backend = Flask的JSON接口在/api下\n设 stack = 纯HTML和JS\n'
            '设 goal = 不改后端\n设 project = fe_test\n设 web_dir = web\n设 test_cmd = ./web/run_tests.sh\n'
            f'设 review_attendees = {attendees}\n编排执行 frontend_workflow.wf\n')


def copy(tmp):
    demo = tmp / 'f'
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
    (demo / 'run_fe.zs').write_text(entry(), encoding='utf-8')
    c = client(REPLIES)
    s = wc.start(demo, entry='run_fe.zs', mode='auto', wait=True, client=c)
    check(s['status'] == 'done', f'全自动跑完，中间不停（{s.get("error")}）')
    check(len(c.calls) == 18, '一共 18 次调用')
    check([x['role'] for x in s['steps']] == ROLES, '角色顺序：设计 → 评审（含追问）→ 改设计 → 骨架返工一次 → 列表页裁决一次 → 端到端 → 整体返工一次')
    check([x['name'] for x in s['steps']] == NAMES, '步骤名顺序')
    p = [x.get('prompt', '') for x in c.calls]
    check('survey_app' not in p[0] and 'Flask的JSON接口在/api下' in p[0] and './web/run_tests.sh' in p[0], '界面设计拿到后端说明和测试命令')
    check('问卷前端 v1' in p[1] and '问卷前端 v1' in p[2], '评审的人看得到设计')
    check('设计覆盖了需求' in p[2], '后发言的人看得到前面的发言')
    check('没有问卷时显示什么？' in p[3] and '列表页缺空数据状态' in p[3], '被点名的设计师看得到问题')
    check('确实漏了' in p[4], '主持人看得到追问的回答')
    check('列表页补空数据状态' in p[6] and '问卷前端 v1' in p[6], '设计修改拿到评审结论和原设计')
    check('没有问卷时显示 #empty' in p[11], '页面循环用的是修改后的设计（v2）')
    check('"current_page"' in p[7] and '前端骨架' in p[7] and '我的问卷列表' not in p[7] and '建问卷再填写' not in p[7]
          and 'node web/serve.js' in p[7] and 'web/js/api.js' in p[7] and '错误显示在 #error' in p[7],
          '工程师只拿本页设计和全前端约定（serve、test_harness、shared、conventions），不拿别的页和端到端场景')
    check('api.js 出错时要显示在 #error' in p[9] and '不要改 web 以外的文件' in p[9], '返工按验收的 task 来，带着不改后端的规矩')
    check('做了skeleton_fix' in p[10], '返工后的验收看得到返工记录')
    check('后端列表接口的字段叫 items' in p[12] and '设计确认' in p[12], '工程师报告设计和后端对不上：先交设计师裁决')
    check('ITEMS_FIELD' in p[13] and 'ITEMS_FIELD' in p[14] and 'ITEMS_FIELD' not in p[11],
          '裁决记进 design_notes：后面的页面验收和端到端测试都看得到')
    check('做了surveys' in p[13] and '做了skeleton' not in p[13], '页面验收只看本页的实现记录（换页时清空）')
    check('建问卷再填写' in p[14] and '列表里出现它' in p[14] and '"acceptance"' not in p[14], '端到端测试拿到场景和各页元素，不拿验收条件')
    check('做了e2e' in p[15] and '建问卷再填写' in p[15], '整体验收看得到端到端测试的记录和场景')
    check('新建问卷后列表没刷新' in p[16], '整体返工按整体验收的 task 来')
    t = trace(s['run'])
    jumps = [(e['target'], e['count'], (e.get('item') or {}).get('index')) for e in t['events'] if e['type'] == 'jump']
    check(jumps == [('m', 1, 1), ('b', 1, None)], '跳转：骨架页返工一次（按页记）、整体返工一次；评审一轮就结论，没跳回')


def test_no_change(tmp):
    demo = copy(tmp)
    (demo / 'run_fe.zs').write_text(entry('REVIEWER_GPT'), encoding='utf-8')
    one = design('v1')
    one['pages'] = one['pages'][:1]
    c = client([one, speech('没问题', agree=True), CHECK_DONE, decision([]),
                impl('skeleton'), pcheck('通过'), impl('e2e'), final('通过')])
    s = wc.start(demo, entry='run_fe.zs', mode='auto', wait=True, client=c)
    check(s['status'] == 'done' and '设计修改' not in [x['name'] for x in s['steps']], '评审结论没有修改项：不改设计，直接做页面')


def test_human_reviewer(tmp):
    demo = copy(tmp)
    (demo / 'run_fe.zs').write_text(entry('REVIEWER_GPT,HUMAN'), encoding='utf-8')
    c = client([design('v1'), speech('没问题', agree=True)])
    s = wc.start(demo, entry='run_fe.zs', mode='auto', wait=True, client=c)
    check(s['status'] == 'waiting' and s['pending']['role'] == 'HUMAN' and s['pending']['name'] == '评审发言',
          '人进了评审名单：轮到人发言时停下等（别的步骤照常自动）')


def test_cards():
    from verbs.workflow import _agents as ag
    from tools.dsl import DSLEngine
    e = DSLEngine(workdir=ROOT / 'workflow_demo', verbs_root=ROOT / 'verbs', verbose=False)
    e.vars['project'] = 'survey1'
    for name in ('DESIGNER', 'FRONTEND_ENGINEER', 'FRONTEND_QA'):
        prof = ag.load_agent(e, name)
        check(prof['model'].startswith('cli:claude/'), f'{name} 卡能加载')
    tools = json.loads((ROOT / 'workflow_demo/agents/DESIGNER/agent.json').read_text(encoding='utf-8'))['agentic']['allowed_tools']
    check(not {'Write', 'Edit'} & set(tools), '设计师只读：没有 Write / Edit')
    qa = json.loads((ROOT / 'workflow_demo/agents/FRONTEND_QA/agent.json').read_text(encoding='utf-8'))['agentic']['allowed_tools']
    check(not {'Write', 'Edit'} & set(qa), '前端 QA 只读：没有 Write / Edit')


def run():
    (ROOT / 'data/tmp').mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='wffe-', dir=ROOT / 'data/tmp') as folder:
        for case in (test_full, test_no_change, test_human_reviewer):
            tmp = Path(folder) / case.__name__
            tmp.mkdir()
            print(case.__name__)
            case(tmp)
    print('test_cards')
    test_cards()
    print('前端流程：全部通过')


if __name__ == '__main__':
    run()
