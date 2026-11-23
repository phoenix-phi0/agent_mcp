import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))  # 项目根，run_all 不设 PYTHONPATH
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))
"""代码重构流程（workflow_demo/refactor_workflow.wf）：现状分析 → 重构方案 → 审查（最多改 2 轮）→ 按成本分配
→ 逐项实施 → 回归验收。用假模型回复跑真实的角色卡和格式，不调模型。"""
import json
import shutil
import tempfile
from pathlib import Path

from dsl.client import ScriptClient
from tools.dsl import DSLEngine
from wf_fixtures import acceptance, impl, review
from test_wf_project import arch as project_arch

ROOT = Path(__file__).resolve().parents[2]


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print('  ✓', msg)


def analysis():
    return {"analysis": {
        "summary": "单文件钱包服务，鉴权和金额校验在 deposit、transfer 里各写一遍",
        "files": [{"path": "wallet_service.py", "lines": 420, "role": "全部业务"},
                  {"path": "tests/test_transfer.py", "lines": 300, "role": "转账测试"}],
        "test_command": ".venv/bin/python -m pytest -p no:cacheprovider -q",
        "baseline": {"summary_line": "218 passed in 15.37s", "passed": 218, "failed": 0},
        "public_api": [{"name": "WalletService.transfer", "signature": "(token, to_username, amount, idempotency_key) -> dict",
                        "where": "wallet_service.py:WalletService.transfer"}],
        "smells": [{"location": "wallet_service.py:deposit/transfer", "problem": "重复 25 行金额校验",
                    "impact": "改规则要改两处", "suggestion": "抽 _check_amount", "risk": "中"}],
        "constraints": ["transfer 从令牌校验到提交在同一个 with self._tx() 里"]}}


def plan(v='v1'):
    return {"plan": {
        "goal": f"去掉重复校验 {v}", "keep": ["WalletService.transfer 签名不变", "已有测试断言不改"],
        "steps": [{"title": "抽 _check_amount", "smells": ["wallet_service.py:deposit/transfer"],
                   "change": "抽函数，两处调用", "files": ["wallet_service.py"], "verify": "全量 ≥218 全过"}],
        "acceptance": ["全量测试 ≥218 且全过"], "out_of_scope": [], "risks": [], "open_questions": []}}


def plan_rev(v):
    r = plan(v)
    r["changes"] = [{"issue": "keep 漏了错误码顺序", "action": "已修改", "detail": "补进 keep"}]
    return r


def assign(*agents):
    return {"tasks": [{"content": f"【第{i}项】重构第{i}步，行为不变", "agent": a, "reason": f"第{i}项：简单"}
                      for i, a in enumerate(agents, 1)]}


def contract_arch(v, changes=False):
    """重构后的接口约定（architecture 格式）：借用整项目流程测试的两模块架构，概要标上版本"""
    a = project_arch(v, changes=changes)
    a['summary'] = f'重构后的钱包服务 {v}'
    return a


def demo_copy(tmp):
    dst = tmp / 'workflow_demo'
    shutil.copytree(ROOT / 'workflow_demo', dst,
                    ignore=shutil.ignore_patterns('runs', 'work', '*.bak-*', '__pycache__'))
    return dst


def run_demo(demo, replies):
    client = ScriptClient(list(replies))
    client.offline = True
    engine = DSLEngine(client=client, workdir=demo, verbs_root=ROOT / 'verbs', verbose=False)
    error = None
    try:
        engine.run_file('run_refactor.zs')
    except Exception as e:      # noqa: BLE001  出错的情况也要看过程记录
        error = e
    files = list((demo / 'runs').glob('*.json'))
    trace = json.loads(files[0].read_text(encoding='utf-8')) if files else None
    return client, trace, error


def run():
    tmp = Path(tempfile.mkdtemp())
    try:
        # 0. 卡和格式：分析员是 codex 只读验收那种沙箱；两个架构师卡都带重构技能
        an = json.loads((ROOT / 'workflow_demo/agents/REFACTOR_ANALYST/agent.json').read_text(encoding='utf-8'))
        check(an['model'].startswith('cli:codex/') and an['agentic']['sandbox'] == 'project-read-only'
              and an.get('cost'), '分析员：codex、项目只读、有 cost')
        for name in ('ARCHITECT', 'ARCHITECT_FABLE'):
            d = json.loads((ROOT / f'workflow_demo/agents/{name}/agent.json').read_text(encoding='utf-8'))
            check('skills/refactor.md' in d['skills'] and (ROOT / f'workflow_demo/agents/{name}/skills/refactor.md').is_file()
                  and '重构方案' in (ROOT / f'workflow_demo/agents/{name}/SOUL.md').read_text(encoding='utf-8'),
                  f'{name}：带 refactor.md，SOUL 有重构方案一节')

        # 1. 正常路径：分析 → 方案 → 审查需修改 → 修改 → 审查通过 → 分配两项 → 实施两项 → QA 需修改 → 修改 → QA 通过
        demo = demo_copy(tmp / 'a')
        replies = [analysis(), plan('v1'), review('需修改'), plan_rev('v2'), review('通过'),
                   assign('ENGINEER_LITE', 'ENGINEER'), impl('抽函数'), impl('集中常量'),
                   acceptance('需修改', '测试数少了 2 个'), impl('补回测试', fix_for='测试数少了 2 个'),
                   acceptance('通过'), contract_arch('v1'), review('通过')]
        client, t, err = run_demo(demo, replies)
        check(err is None and t['status'] == 'done', f'跑完：{err}')
        check(len(client.calls) == 13, f'13 次调用（实际 {len(client.calls)}）')
        tasks = [e for e in t['events'] if e['type'] == 'task']
        names = [e['name'] for e in tasks]
        check(names == ['现状分析', '重构方案', '方案审查', '方案修改', '方案审查', '任务分配',
                        '任务实现', '任务实现', '测试', '代码修改', '测试', '约定更新', '约定核对'], f'节点顺序：{names}')
        cu, cc = tasks[11], tasks[12]
        ctx = cu['context']
        check(cu['role'] == 'ARCHITECT' and ctx.get('contract') == {} and ctx.get('analysis') == analysis()
              and ctx['plan']['plan']['goal'] == '去掉重复校验 v2' and len(ctx['task_results']) == 3,
              '约定更新：没有原约定（空对象），拿到现状分析、最终方案和实现记录（分析 + 两项实现；'
              f'重构流程的返工本来就不存记录）：{sorted(ctx)} {len(ctx.get("task_results") or [])}')
        check(cc['role'] == 'QA_ENGINEER' and cc['context']['arch']['summary'] == '重构后的钱包服务 v1'
              and cc['context']['public_api'] == analysis()['analysis']['public_api'] and '只核对' in cc['task'],
              '约定核对：QA 拿到新约定和重构前的公开接口，只核对不改')
        ct = json.loads((demo / 'work/wallet_refactor1/CONTRACT.json').read_text(encoding='utf-8'))
        check(ct['source'] == '重构流程' and ct['architecture']['summary'] == '重构后的钱包服务 v1' and ct['contract_notes'] == [],
              '跑完写了 CONTRACT.json（没有原约定：裁决为空）')
        check([e['role'] for e in tasks[:2]] == ['REFACTOR_ANALYST', 'ARCHITECT'], '分析员先看代码，架构师再写方案')
        check(tasks[1]['context'] == analysis(), '重构方案的参考文本是现状分析')
        check(tasks[3]['context']['plan']['goal'] == '去掉重复校验 v1', '方案修改拿到上一版方案')
        check(tasks[5]['context']['plan']['goal'] == '去掉重复校验 v2', '任务分配用修改后的方案')
        check([e['role'] for e in tasks[6:8]] == ['ENGINEER_LITE', 'ENGINEER'], '实施按分配的角色跑')
        qa = tasks[8]
        check(isinstance(qa['context'], list) and qa['context'][0] == analysis()
              and len(qa['context']) == 3, '回归验收的参考文本：第一条是现状分析（基线），后面是两项实现记录')
        check('baseline' in qa['task'] and 'public_api' in qa['task'], '验收提示要求对照基线和公开接口')
        check(tasks[9]['task'] == '测试数少了 2 个' and tasks[9]['role'] == 'ENGINEER', '返工把 QA 的 task 交给工程师')

        # 2. 审查一直判需修改：最多改 2 轮，第 3 次跳转报错停下（不让方案越改越大）
        demo = demo_copy(tmp / 'b')
        replies = [analysis(), plan('v1'), review('需修改'), plan_rev('v2'), review('需修改'), plan_rev('v3'),
                   review('需修改'), plan_rev('v4')]
        client, t, err = run_demo(demo, replies)
        check(err is not None and '跳转 a 超过最大 2 次' in str(err) and t['status'] == 'error',
              f'审查改满 2 轮还不过：报错停下（{str(err)[:60]}）')
        check(len(client.calls) == 8, '分析、方案、3 次审查、3 次修改')

        # 3. 项目已有约定：约定更新拿到原约定；核对判需修改 → 修正 → 再核对通过；原约定的裁决沿用，history 接着记
        demo = demo_copy(tmp / 'c')
        old = {'version': 1, 'source': '整项目流程', 'architecture': contract_arch('v0'),
               'contract_notes': [{'module': 'web', 'decisions': ['老裁决']}], 'history': [{'source': '整项目流程'}], 'warnings': []}
        (demo / 'work/wallet_refactor1').mkdir(parents=True)
        (demo / 'work/wallet_refactor1/CONTRACT.json').write_text(json.dumps(old, ensure_ascii=False), encoding='utf-8')
        bad = review('需修改')
        bad['issues'] = [{'location': 'core.create_todo', 'problem': '约定说在 app/db.py，代码搬到了 app/repo.py',
                          'suggestion': 'files 改成 app/repo.py', 'severity': '一般'}]
        replies = [analysis(), plan('v1'), review('通过'), assign('ENGINEER_LITE'), impl('抽函数'), acceptance('通过'),
                   contract_arch('v1'), bad, contract_arch('v2', changes=True), review('通过')]
        client, t, err = run_demo(demo, replies)
        check(err is None and t['status'] == 'done', f'跑完：{err}')
        tasks = [e for e in t['events'] if e['type'] == 'task']
        check([e['name'] for e in tasks][-4:] == ['约定更新', '约定核对', '约定修正', '约定核对'], '核对不过：修正一次再核对')
        check(tasks[-4]['context']['contract']['architecture']['summary'] == '重构后的钱包服务 v0', '约定更新拿到重构前的原约定')
        check('app/repo.py' in json.dumps(tasks[-2]['context'], ensure_ascii=False) and tasks[-2]['context']['contract'] == tasks[-4]['context']['contract'],
              '约定修正拿到核对意见和原约定')
        ct = json.loads((demo / 'work/wallet_refactor1/CONTRACT.json').read_text(encoding='utf-8'))
        check(ct['architecture']['summary'] == '重构后的钱包服务 v2' and 'changes' not in ct['architecture']
              and ct['contract_notes'] == [{'module': 'web', 'decisions': ['老裁决']}] and len(ct['history']) == 2,
              '写回修正后的约定；原约定的裁决沿用；history 接着记')
        print('wf refactor passed')
    finally:
        shutil.rmtree(tmp)


if __name__ == '__main__':
    run()
