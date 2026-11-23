import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))  # 项目根，run_all 不设 PYTHONPATH
"""项目接口约定 CONTRACT.json（verbs/workflow/_contract.py 和三个动词：读约定、存约定、合并约定）。

1. 存约定：写出 architecture + 裁决 + history；去掉修改版才有的 changes；再写一次 history 接着记；uses 对不上记进 warnings。
2. 合并约定：按 order 排；改动的模块整份替换（去掉 status、change）、新增的加进来、删除的去掉；没在方案里的模块原样保留；
   方案给了数据模型 / 集成场景等就换掉；history 记改了哪些；合并后 uses 对不上进 warnings。
3. 方案和约定对不上的硬伤（新增的模块已存在、修改的模块不存在、order 漏了改动的模块、删了又在 order 里）：报错，不写文件。
4. DSL 里用：读约定（文件不在是空对象）、存约定、合并约定，后面写变量名；写了花括号报错；路径越出工作目录报错。
"""
import importlib.util
import json
import shutil
import tempfile
from pathlib import Path

from dsl.client import ScriptClient
from tools.dsl import DSLEngine
from tools.dsl_core import DSLError

ROOT = Path(__file__).resolve().parents[2]
sys_path = str(Path(__file__).resolve().parent)
if sys_path not in _sys.path:
    _sys.path.insert(0, sys_path)
from test_wf_project import arch  # noqa: E402  复用整项目流程测试的两模块架构（core、web）

spec = importlib.util.spec_from_file_location('_contract_t', ROOT / 'verbs/workflow/_contract.py')
C = importlib.util.module_from_spec(spec)
spec.loader.exec_module(C)


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print('  ✓', msg)


def raises(fn, words, msg):
    try:
        fn()
    except DSLError as e:
        check(all(w in str(e) for w in words), f'{msg}（{e}）')
        return
    raise AssertionError(msg + '：没有报错')


def mod(name, deps=(), provides=None, uses=None, status=None, change=None):
    m = {'name': name, 'title': name, 'responsibility': f'{name} 的职责', 'files': [f'app/{name}.py'],
         'depends_on': list(deps), 'provides': provides or [], 'uses': uses or [],
         'acceptance': ['pytest 通过'], 'tests': [f'tests/test_{name}.py']}
    if status:
        m['status'], m['change'] = status, change or '改了'
    return m


def prov(name, sig):
    return {'name': name, 'kind': '函数', 'signature': sig, 'behavior': 'x', 'errors': []}


def use(ref, sig):
    return {'ref': ref, 'signature': sig, 'behavior': 'x', 'errors': []}


def test_save(tmp):
    p = tmp / 'p/CONTRACT.json'
    a = arch('v2', changes=True)
    notes = [{'module': 'web', 'decisions': [{'issue': 'x', 'verdict': '修改约定', 'detail': 'GET / 302', 'affected_modules': ['web']}]}]
    d = C.save(p, a, notes, '整项目流程', run='runs/r1.json')
    on_disk = json.loads(p.read_text(encoding='utf-8'))
    check(on_disk == d and on_disk['architecture']['modules'][1]['name'] == 'web' and on_disk['contract_notes'] == notes,
          '存约定：architecture 和裁决原样写进文件')
    check('changes' not in on_disk['architecture'] and 'changes' in a, '修改版才有的 changes 不写进约定（原对象不动）')
    check(on_disk['warnings'] == [] and len(on_disk['history']) == 1 and on_disk['run'] == 'runs/r1.json', 'uses 都对得上；记了一条 history 和运行')
    a2 = arch('v1')
    a2['modules'][1]['uses'][0]['signature'] = 'create_todo(title)'
    d = C.save(p, a2, [], '重构流程')
    check(len(d['history']) == 2 and d['history'][-1]['source'] == '重构流程', '再写一次：history 接着记')
    check(any('签名' in w for w in d['warnings']), 'uses 和对方 provides 签名不一致：记进 warnings')
    a3 = arch('v1')
    a3['modules'][1]['uses'] = ['core.create_todo']
    d = C.save(tmp / 'old/CONTRACT.json', a3, [], '从运行记录补')
    check(any('旧格式' in w for w in d['warnings']), '早期格式的 uses 只写名字：不报错，记一条要补全的提醒')
    check(C.read(tmp / 'nope/CONTRACT.json') == {}, '文件不在：读出空对象')
    (tmp / 'bad.json').write_text('{"x": 1}', encoding='utf-8')
    raises(lambda: C.read(tmp / 'bad.json'), ['architecture'], '没有 architecture 的文件：报错')


def base_contract(tmp):
    p = tmp / 'm/CONTRACT.json'
    a = arch('v1')
    a['modules'] = [mod('core', provides=[prov('create', 'create(t) -> int')]),
                    mod('web', ['core'], provides=[prov('POST /todos', 'POST /todos')], uses=[use('core.create', 'create(t) -> int')]),
                    mod('report', ['core'])]
    C.save(p, a, [{'module': 'core', 'decisions': []}], '整项目流程')
    return p


def test_merge(tmp):
    p = base_contract(tmp)
    plan = {'summary': '加截止日期', 'project_summary': '带截止日期的待办网站',
            'order': ['core', 'due', 'web', 'report'],
            'modules': [mod('core', provides=[prov('create', 'create(t, due=None) -> int')], status='修改', change='create 加 due'),
                        mod('due', ['core'], provides=[prov('sort_by_due', 'sort_by_due(items) -> list')],
                            uses=[use('core.create', 'create(t, due=None) -> int')], status='新增', change='新模块'),
                        mod('web', ['core', 'due'], uses=[use('core.create', 'create(t, due=None) -> int'),
                                                          use('due.sort_by_due', 'sort_by_due(items) -> list')], status='修改')],
            'removed': [], 'integration': [{'name': '按截止日期排', 'steps': ['新建两条'], 'expected': '早的在前'}]}
    d = C.merge(p, plan, [{'module': 'web', 'decisions': ['新裁决']}], '改项目流程', run='runs/r2.json')
    names = [m['name'] for m in d['architecture']['modules']]
    check(names == ['core', 'due', 'web', 'report'], '按 order 排：改的替换、新的插进去、没动的原样')
    check(all('status' not in m and 'change' not in m for m in d['architecture']['modules']), '方案里的 status、change 不进约定')
    check(d['architecture']['modules'][0]['provides'][0]['signature'] == 'create(t, due=None) -> int'
          and d['architecture']['modules'][3]['responsibility'] == 'report 的职责', '改动的模块整份换成新版；没动的模块一字不差')
    check(d['architecture']['summary'] == '带截止日期的待办网站' and d['architecture']['integration'][0]['name'] == '按截止日期排'
          and d['architecture']['data_model'] == arch('v1')['data_model'], '方案给了的（概要、集成场景）换掉，没给的（数据模型）照旧')
    h = d['history'][-1]
    check(h['changed'] == ['core', 'web'] and h['added'] == ['due'] and h['removed'] == [] and h['summary'] == '加截止日期',
          'history 记下改了、加了哪些模块')
    check(d['contract_notes'] == [{'module': 'web', 'decisions': ['新裁决']}] and d['warnings'] == [], '裁决换成这次流程结束时的；uses 都对得上')
    # 没给裁决：沿用原来的
    p2 = base_contract(tmp / 'n')
    plan2 = {'summary': '删报表', 'order': ['core', 'web'], 'modules': [], 'removed': [{'name': 'report', 'reason': '不要了'}]}
    d = C.merge(p2, plan2, None, '改项目流程')
    check([m['name'] for m in d['architecture']['modules']] == ['core', 'web'] and d['history'][-1]['removed'] == ['report']
          and d['contract_notes'] == [{'module': 'core', 'decisions': []}], '删除模块；没给裁决就沿用原来的')
    # 改了 core 的签名却没改 web：uses 对不上，记进 warnings（不报错，人来看）
    p3 = base_contract(tmp / 'w')
    plan3 = {'summary': '改签名', 'order': ['core', 'web', 'report'],
             'modules': [mod('core', provides=[prov('create', 'create(title) -> int')], status='修改')]}
    d = C.merge(p3, plan3, None, '改项目流程')
    check(any('web 用到 core.create' in w for w in d['warnings']), '改了接口签名、调用方没跟着改：合并后查出来记进 warnings')
    # 方案漏写了没动的模块：放到最后保留，并提醒
    p4 = base_contract(tmp / 'k')
    d = C.merge(p4, {'summary': 's', 'order': ['core', 'web'], 'modules': []}, None, '改项目流程')
    check([m['name'] for m in d['architecture']['modules']][-1] == 'report' and any('report' in w for w in d['warnings']),
          '原约定的模块不在 order 里也没写删除：保留在最后并提醒')


def test_merge_errors(tmp):
    p = base_contract(tmp)
    before = p.read_text(encoding='utf-8')
    cases = [
        ({'order': ['core', 'web', 'report'], 'modules': [mod('core', status='新增')]}, ['core', '新增'], '新增的模块原约定里已有'),
        ({'order': ['core', 'x', 'web', 'report'], 'modules': [mod('x', status='修改')]}, ['x', '修改'], '修改的模块原约定里没有'),
        ({'order': ['core', 'web', 'report'], 'modules': [mod('due', status='新增')]}, ['due', 'order'], '改动的模块不在 order 里'),
        ({'order': ['core', 'web', 'report'], 'modules': [], 'removed': [{'name': 'report'}]}, ['report', '删除'], '删了又在 order 里'),
        ({'order': ['core', 'web', 'ghost'], 'modules': []}, ['ghost'], 'order 里有不存在的模块'),
    ]
    for plan, words, msg in cases:
        raises(lambda plan=plan: C.merge(p, plan, None, 't'), words, '合并约定报错：' + msg)
    check(p.read_text(encoding='utf-8') == before, '报错时约定文件没被改')
    raises(lambda: C.merge(tmp / 'none/CONTRACT.json', {'order': []}, None, 't'), ['不存在'], '没有约定可合并：报错')
    raises(lambda: C.safe_path(tmp, '../x.json'), ['工作目录'], '路径越出工作目录：报错')
    raises(lambda: C.safe_path(tmp, 'x.txt'), ['.json'], '不是 .json：报错')


def test_dsl(tmp):
    wd = tmp / 'wd'
    wd.mkdir()
    e = DSLEngine(client=ScriptClient([]), workdir=wd, verbs_root=ROOT / 'verbs', verbose=False)
    e.vars['a'] = arch('v1')
    e.run('用包 workflow\n设 c0 = 读约定 work/p1/CONTRACT.json\n存约定 work/p1/CONTRACT.json a 来源=测试\n'
          '设 c1 = 读约定 work/p1/CONTRACT.json\n')
    check(e.vars['c0'] == {}, 'DSL：读约定 文件不在是空对象')
    check(isinstance(e.vars['c1'], dict) and e.vars['c1']['architecture']['modules'][0]['name'] == 'core'
          and e.vars['c1']['source'] == '测试', 'DSL：存约定后 读约定 拿到的是结构（不是文本）')
    e.vars['plan'] = {'summary': '加报表', 'order': ['core', 'web', 'report'], 'modules': [mod('report', ['core'], status='新增')]}
    e.run('用包 workflow\n合并约定 work/p1/CONTRACT.json plan\n设 c2 = 读约定 work/p1/CONTRACT.json\n')
    check([m['name'] for m in e.vars['c2']['architecture']['modules']] == ['core', 'web', 'report'], 'DSL：合并约定 写回')
    try:
        e.run('用包 workflow\n存约定 work/p1/CONTRACT.json {a}\n')
    except DSLError as err:
        check('花括号' in str(err) or '变量' in str(err), f'DSL：变量名写成花括号报错（{err}）')
    else:
        raise AssertionError('写了花括号应报错')


def run():
    (ROOT / 'data/tmp').mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix='wfct-', dir=ROOT / 'data/tmp'))
    try:
        for case in (test_save, test_merge, test_merge_errors, test_dsl):
            tmp = folder / case.__name__
            tmp.mkdir()
            print(case.__name__)
            case(tmp)
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    print('项目接口约定：全部通过')


if __name__ == '__main__':
    run()
