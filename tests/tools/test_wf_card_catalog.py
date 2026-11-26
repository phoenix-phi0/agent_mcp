import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))  # 项目根，run_all 不设 PYTHONPATH
"""角色卡分类：workflow_demo/agents 下每张卡都有合法的 category、都能加载、都写进了 agents/CATALOG.md；
agents 工具（trace_server.read_agents）带出 category；写错的 category 加载时报错。"""
import json
import shutil
import tempfile
from pathlib import Path

from tools import trace_server
from tools.dsl import DSLEngine
from tools.dsl_core import DSLError
from verbs.workflow import _agents

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / 'workflow_demo'


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print('  ✓', msg)


def run():
    cards = sorted(p.name for p in (DEMO / 'agents').iterdir() if (p / 'agent.json').is_file())
    catalog = (DEMO / 'agents/CATALOG.md').read_text(encoding='utf-8')
    engine = DSLEngine(workdir=DEMO, verbs_root=ROOT / 'verbs', verbose=False)
    engine.vars['project'] = 'catalog_check'
    bad, unlisted, broken = [], [], []
    for name in cards:
        data = json.loads((DEMO / 'agents' / name / 'agent.json').read_text(encoding='utf-8'))
        if data.get('category') not in _agents.CATEGORIES:
            bad.append(name)
        if name not in catalog:
            unlisted.append(name)
        try:
            _agents.load_agent(engine, name)
        except DSLError as e:
            broken.append(f'{name}: {e}')
    check(not bad, f'{len(cards)} 张卡都有合法的 category：{bad}')
    check(not unlisted, f'都写进了 CATALOG.md：{unlisted}')
    check(not broken, f'都能加载：{broken}')
    rows = trace_server.read_agents({'workdir': str(DEMO)})
    check(len(rows) == len(cards) and all(r.get('category') for r in rows), 'agents 工具带出 category')

    # 验收、失败分析、记录三种格式：依据 / 把握
    from tools import wf_submit
    fmt = lambda n: wf_submit.load_format(DEMO, n)
    ev = [{'出处': 'app/orders.py:88-90', '原文': "if qty <= 0:\n    raise OrderError('BAD_QTY')"}]
    item = {'item': '数量校验', 'result': '满足', '依据': ev, '把握': '高'}
    ok_acc = {'decide': '通过', 'summary': '逻辑对', '把握': '高', 'checked': [item]}
    check(not wf_submit.validate(fmt('accept_check'), ok_acc), 'accept_check：合格的能过')
    check(wf_submit.validate(fmt('accept_check'), dict(ok_acc, checked=[dict(item, result='不满足')])),
          'accept_check：有不满足却判通过，不收')
    check(wf_submit.validate(fmt('accept_check'), dict(ok_acc, checked=[dict(item, result='未验证', 依据=[])])),
          'accept_check：有未验证却判通过，不收')
    check(wf_submit.validate(fmt('accept_check'), dict(ok_acc, decide='需修改')), 'accept_check：需修改没写 task，不收')
    check(wf_submit.validate(fmt('accept_check'), dict(ok_acc, checked=[dict(item, 依据=[])])), 'accept_check：判满足没给依据，不收')
    check(wf_submit.validate(fmt('accept_check'), dict(ok_acc, checked=[dict(item, 把握='低')])),
          'accept_check：有一条把握低、总把握却写高，不收')
    check(not wf_submit.validate(fmt('accept_check'), dict(ok_acc, 把握='低', checked=[dict(item, 把握='低')])),
          'accept_check：有一条把握低、总把握写低，能过')
    check(not wf_submit.validate(fmt('accept_check'), dict(ok_acc, checked=[dict(item, 依据=[{'出处': 'run_test 输出', '原文': 'EXIT=0'}])])),
          'accept_check：依据可以是命令输出原文')
    check(not (DEMO / 'formats/code_review.json').exists(), '旧的 code_review 格式删了（换成 accept_check）')
    check(json.loads((DEMO / 'formats/acceptance.json').read_text(encoding='utf-8'))['required'][0] == 'decide'
          and '把握' not in (DEMO / 'formats/acceptance.json').read_text(encoding='utf-8'),
          '已有的 acceptance 格式没动（重构、前端、整项目流程在用）')
    fa = {'状态': '已归因', '结果': '一条新挂', '依据': ev, '把握': '中',
          'failures': [{'test': 'test_qty', '归因': '我的改动', '原因': '>= 写成 >', '依据': ev, '把握': '中', '建议': '改回'}]}
    check(not wf_submit.validate(fmt('failure_analysis'), fa), 'failure_analysis：合格的能过')
    bad = dict(fa, failures=[dict(fa['failures'][0], 归因='不明')])
    check(wf_submit.validate(fmt('failure_analysis'), bad), 'failure_analysis：有不明却说已归因，不收')
    bad = dict(fa, failures=[dict(fa['failures'][0], 把握='低')])
    check(wf_submit.validate(fmt('failure_analysis'), bad), 'failure_analysis：有把握低的却说已归因，不收')
    rn = {'状态': '完成', '结果': '写了提交说明', '种类': '提交说明', '标题': '订单：数量为 0 时报 BAD_QTY',
          '正文': '- app/orders.py：先校验数量', '依据': [{'出处': 'task_results[0]', '原文': '先校验数量'}], '把握': '高'}
    check(not wf_submit.validate(fmt('record_note'), rn), 'record_note：合格的能过')
    check(wf_submit.validate(fmt('record_note'), dict(rn, 标题='x' * 80)), 'record_note：标题超过 72 字，不收')
    hints = [wf_submit.shape_hint(fmt(n)) for n in ('accept_check', 'failure_analysis', 'record_note')]
    check(all(h and '依据' in h for h in hints), '三个格式都能生成交结果的提示（提交工具要用）')
    rows = {r['name']: r for r in trace_server.read_agents({'workdir': str(DEMO)})}
    check(rows['ACCEPTOR']['model'].startswith('cli:codex/') and rows['ACCEPTOR']['category'] == '验收'
          and rows['ACCEPTOR_SENIOR']['model'].startswith('cli:codex/') and rows['ACCEPTOR_SENIOR']['cost'] > rows['ACCEPTOR']['cost']
          and rows['TRIAGE']['category'] == '分析' and rows['SCRIBE']['category'] == '记录'
          and rows['REPO_ENGINEER']['model'] == 'muse' and rows['REPO_ENGINEER']['model'] != rows['ACCEPTOR']['model'],
          '验收员是 Codex（和工程师 Muse 不同模型），高档验收员更贵，几张新卡的分类对')
    check(all(n not in rows for n in ('CODE_REVIEWER', 'FAILURE_ANALYST', 'RECORDER')), '改名前的三张卡不在了')

    tmp = Path(tempfile.mkdtemp())
    try:
        d = tmp / 'agents/BAD_CAT'
        d.mkdir(parents=True)
        (d / 'agent.json').write_text(json.dumps({'model': 'human', 'category': '杂项'}), encoding='utf-8')
        (d / 'SOUL.md').write_text('x', encoding='utf-8')
        e2 = DSLEngine(workdir=tmp, verbs_root=ROOT / 'verbs', verbose=False)
        try:
            _agents.load_agent(e2, 'BAD_CAT')
            err = None
        except DSLError as e:
            err = e
        check(err is not None and 'category' in str(err), f'category 写错：加载报错（{err}）')
    finally:
        shutil.rmtree(tmp)
    (DEMO / 'work/catalog_check').exists() and shutil.rmtree(DEMO / 'work/catalog_check')
    print('wf card catalog passed')


if __name__ == '__main__':
    run()
