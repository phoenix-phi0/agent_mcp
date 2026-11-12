import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))  # 项目根，run_all 不设 PYTHONPATH
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))
"""按成本分配的流程（workflow_demo/cost_workflow.wf）：角色卡的 cost、「角色清单」「成本合计」两条语句、
超预算时只改角色重分、过程记录里的每步成本和合计。用假模型回复跑真实的角色卡和格式，不调模型。"""
import json
import re
import shutil
import tempfile
from pathlib import Path

from dsl.client import ScriptClient
from tools.dsl import DSLEngine
from tools.dsl_core import DSLError
from wf_fixtures import acceptance, contract, impl, review

ROOT = Path(__file__).resolve().parents[2]
COST = {'ARCHITECT': 5, 'ARCHITECT_GLM': 1, 'QA_ENGINEER': 4, 'ENGINEER_LITE': 1, 'ENGINEER': 3,
        'ENGINEER_SENIOR': 8, 'TEST_ENGINEER': 2,
        # codex 的几档（ChatGPT 订阅）；QA_GPT 不在分配格式里，是给流程换 QA 用的
        'ENGINEER_GPT_LITE': 1, 'ENGINEER_GPT': 2, 'ENGINEER_GPT_SENIOR': 4, 'QA_GPT': 2,
        # Fable 5.2（cli:claude/fable，Claude Code 2.1.322 起指向 5.2）：同一小任务实测约 opus 的 1.9 倍
        'ENGINEER_FABLE': 15,
        # 架构师的 Fable 版（low 档）：不在分配格式里，用 roles={"ARCHITECT": "ARCHITECT_FABLE"} 换上；
        # 钱包需求实测两步约 $2.2，sonnet 架构师（cost 5）约 $0.39 → 约 28，取 30
        'ARCHITECT_FABLE': 30,
        # codex 审查员：ARCHITECT_GLM 审不完时换它（审得偏严，慎用）
        'REVIEWER_GPT': 2}


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print('  ✓', msg)


def plan(*agents):
    return {'tasks': [{'content': f'【第{i}项】做第{i}件事', 'agent': a, 'reason': f'第{i}项的难度判断'}
                      for i, a in enumerate(agents, 1)]}


def demo_copy(tmp, budget=None, edit=None):
    dst = tmp / 'workflow_demo'
    shutil.copytree(ROOT / 'workflow_demo', dst,
                    ignore=shutil.ignore_patterns('runs', 'work', '*.bak-*', '__pycache__'))
    if budget is not None:
        p = dst / 'run_cost.zs'
        p.write_text(re.sub(r'设 budget = \S+', f'设 budget = {budget}', p.read_text(encoding='utf-8')),
                     encoding='utf-8')
    if edit:
        edit(dst)
    return dst


def run_demo(demo, replies):
    client = ScriptClient(list(replies))
    client.offline = True
    engine = DSLEngine(client=client, workdir=demo, verbs_root=ROOT / 'verbs', verbose=False)
    error = None
    try:
        engine.run_file('run_cost.zs')
    except Exception as e:      # noqa: BLE001  出错的情况也要看过程记录
        error = e
    files = list((demo / 'runs').glob('*.json'))
    trace = json.loads(files[0].read_text(encoding='utf-8')) if files else None
    return engine, client, trace, error


def load_agent(tmp, data):
    import importlib.util
    spec = importlib.util.spec_from_file_location('ag_cost', ROOT / 'verbs/workflow/_agents.py')
    ag = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ag)
    card = tmp / 'agents' / 'X'
    card.mkdir(parents=True, exist_ok=True)
    (card / 'SOUL.md').write_text('# X', encoding='utf-8')
    (card / 'agent.json').write_text(json.dumps({'model': 'cli:claude/haiku', **data}), encoding='utf-8')
    return ag.load_agent(DSLEngine(workdir=tmp, verbose=False), 'X')


def view(trace, wf, tmp):
    """查看页（jsdom）画得出两条新语句和成本；没有 node 或 jsdom 就跳过，同 test_trace_view。"""
    import os
    import subprocess
    node = shutil.which('node')
    paths = [p for p in (os.environ.get('NODE_PATH'), str(ROOT / 'node_modules'), '/tmp/wfjsdom/node_modules')
             if p and (Path(p) / 'jsdom').is_dir()]
    if not node or not paths:
        print('  - 跳过查看页渲染：没有 node 或 jsdom')
        return
    path = tmp / 'cost_trace.json'
    path.write_text(json.dumps(trace, ensure_ascii=False), encoding='utf-8')
    line = next(i for i, x in enumerate(wf.splitlines(), 1) if x.startswith('成本合计'))

    def render(sel=None):
        p = subprocess.run([node, str(ROOT / 'tests/e2e/trace_view_check.js'), str(ROOT / 'tools/trace_view.html'),
                            str(path)] + ([str(sel)] if sel else []), capture_output=True, text=True,
                           encoding='utf-8', env=dict(os.environ, NODE_PATH=paths[0]), timeout=60)
        if p.returncode:
            raise AssertionError(p.stderr[-800:])
        return json.loads(p.stdout)

    out = render()
    check(not out['errors'], f'查看页没有脚本错误：{out["errors"][:2]}')
    check('已花成本27' in out['summary'] and '实施分配 7 / 预算 7' in out['summary'], '概况里有已花成本和预算')
    check('角色清单 roster' in out['flow'] and '4 张卡' in out['flow'], '流程图画出角色清单')
    check('成本合计 spent' in out['flow'] and '7 / 7' in out['flow'], '流程图画出成本合计（最后一次 7 / 7）')
    check('成本 5' in out['flow'] and '工程师·便宜档' in out['flow'], '任务节点显示成本，新角色有中文名')
    out = render(line)
    check(not out['errors'], '点成本合计节点：没有脚本错误')


def run():
    tmp = Path(tempfile.mkdtemp())
    try:
        # 0. 真实的角色卡：每张都有 cost 和 description；格式里能挑的角色和流程里的角色清单一致
        agents = ROOT / 'workflow_demo/agents'
        for name, cost in COST.items():
            d = json.loads((agents / name / 'agent.json').read_text(encoding='utf-8'))
            check(d.get('cost') == cost and d.get('description'), f'{name} 卡：cost {cost}，有说明')
        wf = (ROOT / 'workflow_demo/cost_workflow.wf').read_text(encoding='utf-8')
        check(re.search(r'^角色清单 roster \{roles\}$', wf, re.M), '流程的角色清单取自入口脚本的 roles 变量')
        zs = (ROOT / 'workflow_demo/run_cost.zs').read_text(encoding='utf-8')
        roster = re.search(r'^设 roles = (\S+)$', zs, re.M)[1].split(',')
        enum = json.loads((ROOT / 'workflow_demo/formats/cost_assignment.json').read_text(encoding='utf-8'))
        enum = enum['properties']['tasks']['items']['properties']['agent']['enum']
        check(set(roster) <= set(enum) and set(enum) <= set(COST), '分配格式能挑的角色包含入口脚本的清单，且都是有成本的卡')

        # 1. cost 的取值检查
        check(load_agent(tmp / 'k', {'cost': 2.5})['cost'] == 2.5, 'cost 可以是小数')
        # 1a. 纯问答卡的 timeout（fable 架构师写约定超过默认 90 秒被杀过）：30–3600；agentic 卡写在 agentic.timeout
        check(load_agent(tmp / 'k', {'timeout': 600})['timeout'] == 600
              and load_agent(tmp / 'k', {})['timeout'] is None, '纯问答卡可写 timeout，不写是 None（用全局默认）')
        for bad in (10, 5000, '600', True):
            try:
                load_agent(tmp / 'k', {'timeout': bad})
                raise AssertionError(f'应当拒绝 timeout={bad!r}')
            except DSLError as e:
                check('timeout 必须是' in str(e), f'timeout={bad!r}：拒绝')
        try:
            load_agent(tmp / 'k', {'timeout': 600, 'agentic': {'cwd': '.', 'allowed_tools': ['Read']}})
            raise AssertionError('agentic 卡写顶层 timeout 应当拒绝')
        except DSLError as e:
            check('agentic.timeout' in str(e), 'agentic 卡写顶层 timeout：拒绝，提示写在 agentic.timeout')
        import inspect
        from tools import llm_router as _lr
        check('timeout' in inspect.signature(_lr.submit_call).parameters, 'submit_call 收 timeout 参数')
        # 三个后端（claude / codex / 本机 goose）的纯问答分支都先用传进来的 timeout，再退回全局设置
        src = inspect.getsource(_lr.submit_call)
        check(all(f'timeout = timeout or _setting("DSL_{b}_TIMEOUT"' in src for b in ('CLAUDE', 'CODEX', 'GOOSE')),
              'claude、codex、goose 的纯问答都认卡里的 timeout')
        check(json.loads((ROOT / 'workflow_demo/agents/ARCHITECT_GLM/agent.json').read_text(encoding='utf-8'))
              .get('timeout') == 300, 'ARCHITECT_GLM 审查卡 timeout 300（长约定 90 秒审不完）')
        # via：goose 卡可指定一律经 batchmgr；别的值、别的模型都拒
        check(load_agent(tmp / 'k', {'model': 'cli:goose/glm-5.3', 'via': 'batchmgr'})['via'] == 'batchmgr'
              and load_agent(tmp / 'k', {})['via'] is None, 'goose 卡可写 via batchmgr，不写是 None')
        for data in ({'via': 'batchmgr'}, {'model': 'cli:goose/glm-5.3', 'via': 'local'}):
            try:
                load_agent(tmp / 'k', data)
                raise AssertionError(f'应当拒绝 {data}')
            except DSLError as e:
                check('via 只能是' in str(e), f'via 拒绝：{data}')
        check('via' in inspect.signature(_lr.submit_call).parameters
              and 'if via == "batchmgr" or not gsbatch._zai_key():' in src, 'submit_call 收 via，batchmgr 优先于本机 goose')
        check(json.loads((ROOT / 'workflow_demo/agents/ARCHITECT_GLM/agent.json').read_text(encoding='utf-8'))
              .get('via') == 'batchmgr', 'ARCHITECT_GLM 审查卡经 batchmgr')
        # claude 的提示词走标准输入：133KB 的重构分析当命令行参数会 E2BIG（单个参数上限 128KB）
        check('"-p", prompt' not in src and 'ch.run(cmd, cwd, env, prompt + ask, timeout, "claude"' in src,
              'submit_call 的 claude 提示词从标准输入给，不放命令行参数')

        # 1b. codex 卡：effort 拼进模型名；agentic 用 sandbox 管权限，不写 allowed_tools / mcp_tools
        def bad_card(data):
            try:
                load_agent(tmp / 'cx', data)
            except DSLError as e:
                return str(e)
            return ''
        cx = load_agent(tmp / 'cx', {'model': 'cli:codex/gpt-6.1-terra', 'effort': 'high',
                                     'agentic': {'cwd': '.', 'sandbox': 'read-only'}})
        check(cx['model'] == 'cli:codex/gpt-6.1-terra@high' and cx['agentic']['sandbox'] == 'read-only',
              'codex 卡：effort 拼成 @high，sandbox 照写')
        check(load_agent(tmp / 'cx', {'model': 'cli:codex/gpt-reserve', 'agentic': {'cwd': '.'}})
              ['agentic']['sandbox'] == 'workspace-write', 'codex 卡不写 sandbox 默认 workspace-write')
        check('sandbox' in bad_card({'model': 'cli:codex/gpt-6.1-terra',
                                     'agentic': {'cwd': '.', 'allowed_tools': ['Read']}}),
              'codex 卡写 allowed_tools 被拒')
        check('sandbox' in bad_card({'model': 'cli:codex/gpt-6.1-terra',
                                     'agentic': {'cwd': '.', 'sandbox': 'danger-full-access'}}),
              'codex 卡 sandbox 不能是 danger-full-access')
        check('sandbox' in bad_card({'agentic': {'cwd': '.', 'allowed_tools': ['Read'], 'sandbox': 'read-only'}}),
              'claude 卡写 sandbox 被拒')
        import os
        from tools import llm_router
        os.environ['GSB_CODEX_BIN'] = shutil.which('true') or '/bin/true'
        cmd = llm_router._codex_cmd('gpt-6-astra@high', 'read-only', tmp, tmp / 'r.txt', mcp_env={'WF_OUT': '/x'})
        joined = ' '.join(cmd)
        check('model_reasoning_effort=high' in joined and '-m gpt-6-astra ' in joined + ' ',
              'codex 命令：模型名里的 @high 拆成 model_reasoning_effort')
        check('mcp_servers.wf.default_tools_approval_mode="approve"' in cmd and 'network_access' not in joined,
              'codex 命令：只给 wf 服务放开审批；只读沙箱不放开网络')
        cmd = llm_router._codex_cmd('gpt-reserve', 'workspace-write', tmp, tmp / 'r.txt')
        check('sandbox_workspace_write.network_access=true' in cmd
              and not any(x.startswith('mcp_servers.wf.') for x in cmd),
              'codex 命令：workspace-write 放开网络（装依赖）；不挂提交工具时没有 wf 配置')
        # 不读 ~/.codex/config.toml（全局挂的 gsb_tools 的 run_wait 能在沙箱外跑命令）：配置全由这次的参数给
        cmd = llm_router._codex_cmd('gpt-reserve', 'workspace-write', tmp, tmp / 'r.txt', mcp_env={'WF_OUT': '/x'})
        check(cmd[1:3] == ['exec', '--ignore-user-config'] and any(x.startswith('mcp_servers.wf.command') for x in cmd),
              'codex 命令：--ignore-user-config 不带全局配置，只挂这次给的 wf')

        # 1b'. codex 事件流打时间戳：ts_tee 原样转发标准输出和标准输入，另存「秒数<TAB>原行」，退出码照传
        import subprocess
        import sys as _s
        log = tmp / 'ev.log'
        p = subprocess.run([_s.executable, str(ROOT / 'tools/ts_tee.py'), str(log), '--', _s.executable, '-c',
                            'import sys; d=sys.stdin.read(); print("{\\"type\\":\\"a\\"}"); print(d.upper()); sys.exit(3)'],
                           input='hi', capture_output=True, text=True, timeout=30)
        lines = log.read_text(encoding='utf-8').splitlines()
        check(p.returncode == 3 and p.stdout == '{"type":"a"}\nHI\n',
              'ts_tee：标准输出原样转发、标准输入传给子进程、退出码照传')
        check(len(lines) == 4 and lines[1].split('\t', 1)[1] == '{"type":"a"}' and '退出码 3' in lines[-1],
              'ts_tee：日志每行带开始后的秒数，首尾有开始和结束标记')
        # GLM 经 batchmgr：每次尝试带上较短的超时（卡住时早点重试），每次尝试都记进用量
        sent = []

        class _Resp:
            def __init__(self, body):
                self.body = json.dumps(body).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return self.body

        def fake_urlopen(req, timeout=None):
            if req.get_method() == 'POST':
                sent.append(json.loads(req.data.decode()))
                return _Resp({'ok': True, 'job_id': f'j{len(sent)}'})
            out = '' if len(sent) == 1 else '{"answer": 3}'      # 第一次卡住没输出，第二次正常
            return _Resp({'job': {'status': 'done', 'tasks': [{'status': 'timeout' if not out else 'done',
                                                               'output': out, 'seconds': 120 if not out else 5}]}})
        import urllib.request
        real, real_sleep = urllib.request.urlopen, llm_router.__dict__.get('_time')
        urllib.request.urlopen = fake_urlopen
        import time as _t
        real_t_sleep = _t.sleep
        _t.sleep = lambda s: None
        try:
            res, use = llm_router._batchmgr_goose_json('q', 's', 'glm-5.3',
                                                       {'type': 'object', 'required': ['answer'],
                                                        'properties': {'answer': {'type': 'integer'}}})
        finally:
            urllib.request.urlopen = real
            _t.sleep = real_t_sleep
        check(res == {'answer': 3} and all(b.get('timeout') == llm_router.BATCHMGR_TRY_TIMEOUT for b in sent)
              and len(sent) == 2 and [a['status'] for a in use['attempts']] == ['timeout', 'done'],
              f'batchmgr：每次尝试带超时 {llm_router.BATCHMGR_TRY_TIMEOUT} 秒，卡住的那次重试后成功，尝试都记下')

        # 1c. 验收用的 project-read-only：卡能写；命令行不直接收它（先换算成 workspace-write + 空临时目录）；
        #     换算后不放开网络；项目文件被改能比对出来
        qa = load_agent(tmp / 'cx', {'model': 'cli:codex/gpt-6.1-sol', 'agentic': {'cwd': '.', 'sandbox': 'project-read-only'}})
        check(qa['agentic']['sandbox'] == 'project-read-only', 'codex 卡可以写 sandbox project-read-only')
        try:
            llm_router._codex_cmd('gpt-6.1-sol', 'project-read-only', tmp, tmp / 'r.txt')
            check(False, 'project-read-only 不能直接传给 codex')
        except llm_router.BackendError:
            check(True, 'project-read-only 不能直接传给 codex（要先换算）')
        cmd = llm_router._codex_cmd('gpt-6.1-sol', 'workspace-write', tmp, tmp / 'r.txt', network=False)
        check('workspace-write' in cmd and not any('network_access' in x for x in cmd),
              '验收换算后的 workspace-write 不放开网络')
        proj = tmp / 'snap'
        (proj / '.venv').mkdir(parents=True)
        (proj / 'a.py').write_text('x = 1', encoding='utf-8')
        before = llm_router._tree_snapshot(proj)
        (proj / '.venv' / 'junk').write_text('cache', encoding='utf-8')
        check(llm_router._snapshot_diff(before, llm_router._tree_snapshot(proj)) == {},
              '快照跳过 .venv：虚拟环境里的变化不算改动项目')
        (proj / 'a.py').write_text('x = 22', encoding='utf-8')
        (proj / 'conftest.py').write_text('', encoding='utf-8')
        diff = llm_router._snapshot_diff(before, llm_router._tree_snapshot(proj))
        check(diff == {'新增': ['conftest.py'], '改动': ['a.py']}, f'快照比对出新增和改动的文件：{diff}')
        check(load_agent(tmp / 'k', {})['cost'] is None, '不写 cost：None（旧卡照常能用）')
        for bad in (0, -1, True, '3', 5000):
            try:
                load_agent(tmp / 'k', {'cost': bad})
                raise AssertionError(f'应当拒绝 cost={bad!r}')
            except DSLError as e:
                check('cost 必须是' in str(e), f'cost={bad!r}：拒绝')

        # 2. 第一次分配超预算（8+3+3=14 > 7）→ 分配调整只改角色（1+3+3=7）→ 实施三项 → QA 通过
        demo = demo_copy(tmp / 'a')
        replies = [contract('v1'), review('通过'), plan('ENGINEER_SENIOR', 'ENGINEER', 'ENGINEER'),
                   plan('ENGINEER_LITE', 'ENGINEER', 'ENGINEER'),
                   impl('骨架'), impl('登录'), impl('会话'), acceptance('通过')]
        engine, client, t, err = run_demo(demo, replies)
        check(err is None and t['status'] == 'done', f'跑完：{err}')
        check(len(client.calls) == 8, '8 次调用：约定、审查、分配、调整、实施三项、QA')
        ev = {k: [e for e in t['events'] if e['type'] == k] for k in ('roster', 'cost', 'task', 'jump')}
        r = ev['roster'][0]['roles']
        check([x['name'] for x in r] == roster and [x['cost'] for x in r] == [1, 3, 8, 2]
              and all(x['description'] and 'model' not in x for x in r), '角色清单：名字、成本、说明（不带模型）')
        tasks = ev['task']
        check(tasks[2]['name'] == '任务分配' and '实施预算：7' in tasks[2]['task']
              and 'ENGINEER_SENIOR' in tasks[2]['task'] and 'cost' in tasks[2]['task'],
              '任务分配的提示里有预算和角色清单（带 cost）')
        check([(c['total'], c['budget'], c['status']) for c in ev['cost']] == [(14, 7, '超出'), (7, 7, '未超出')],
              '成本合计两次：14 超出，调整后 7 未超出（等于预算算没超）')
        check(ev['cost'][0]['by_role'] == {'ENGINEER_SENIOR': 8, 'ENGINEER': 6}, '按角色分的小计')
        adj = tasks[3]
        check(adj['name'] == '分配调整' and adj['context']['total'] == 14 and adj['context']['budget'] == 7
              and [x['agent'] for x in adj['context']['tasks']] == ['ENGINEER_SENIOR', 'ENGINEER', 'ENGINEER']
              and adj['context']['tasks'][0]['content'] == '【第1项】做第1件事',
              '分配调整的参考文本：合计、预算、每项的角色成本和原文')
        check([e['target'] for e in ev['jump']] == ['c'], '超预算跳回一次')
        check([e['role'] for e in tasks[4:7]] == ['ENGINEER_LITE', 'ENGINEER', 'ENGINEER'],
              '实施按调整后的角色跑')
        check([e.get('cost') for e in tasks] == [5, 1, 5, 5, 1, 3, 3, 4], '每个任务节点记下这张卡的 cost')
        check(t['cost_spent'] == 27, '过程记录里的已花成本 = 各节点之和 27')
        view(t, wf, tmp)

        # 3. 一直超预算：调整两次还超 → 第三次跳转报错，流程停下
        demo = demo_copy(tmp / 'b')
        over = plan('ENGINEER_SENIOR', 'ENGINEER_SENIOR')
        _, client, t, err = run_demo(demo, [contract('v1'), review('通过'), over, over, over, over])
        check(err is not None and '跳转 c 超过最大 2 次' in str(err) and t['status'] == 'error',
              f'一直超预算：调整两次后报错停下（{str(err)[:60]}）')
        check(len(client.calls) == 6, '分配一次 + 调整三次')

        # 4. 预算不是数字
        demo = demo_copy(tmp / 'c', budget='很多')
        _, _, t, err = run_demo(demo, [contract('v1'), review('通过'), plan('ENGINEER_LITE')])
        check(err is not None and '预算不是数字' in str(err), '预算不是数字：报错')

        # 5. 清单里的卡没配 cost：在角色清单那一行就报错，一次模型都不调
        def drop_cost(dst):
            p = dst / 'agents/TEST_ENGINEER/agent.json'
            d = json.loads(p.read_text(encoding='utf-8'))
            d.pop('cost')
            p.write_text(json.dumps(d), encoding='utf-8')
        demo = demo_copy(tmp / 'd', edit=drop_cost)
        _, client, _, err = run_demo(demo, [])
        check(err is not None and 'TEST_ENGINEER 没有配置 cost' in str(err) and not client.calls,
              '卡没配 cost：角色清单那一行报错，不调模型')

        # 6. 分配里挑了格式外的角色：格式就不收
        demo = demo_copy(tmp / 'e')
        _, _, _, err = run_demo(demo, [contract('v1'), review('通过'), plan('ARCHITECT')])
        check(err is not None and '不符合格式 cost_assignment' in str(err), '挑了格式外的角色：格式拒收')

        # 7. 挑了格式里有、但这次清单里没有的卡（入口脚本的清单去掉 TEST_ENGINEER）：算超出，分配调整换掉后照常往下走
        def no_tester(dst):
            p = dst / 'run_cost.zs'
            p.write_text(p.read_text(encoding='utf-8').replace(',TEST_ENGINEER', ''), encoding='utf-8')
        demo = demo_copy(tmp / 'f', edit=no_tester)
        _, client, t, err = run_demo(demo, [contract('v1'), review('通过'), plan('TEST_ENGINEER', 'ENGINEER_LITE'),
                                            plan('ENGINEER_LITE', 'ENGINEER_LITE'), impl('甲'), impl('乙'),
                                            acceptance('通过')])
        costs = [e for e in t['events'] if e['type'] == 'cost']
        check(err is None and [c['status'] for c in costs] == ['超出', '未超出']
              and costs[0].get('not_in_roster') == ['TEST_ENGINEER'], '清单外的卡：判超出，调整后通过')

        # 8. 入口脚本没设 roles：角色清单那一行就报错
        def no_roles(dst):
            p = dst / 'run_cost.zs'
            p.write_text(re.sub(r'^设 roles = .*\n', '', p.read_text(encoding='utf-8'), flags=re.M), encoding='utf-8')
        demo = demo_copy(tmp / 'g', edit=no_roles)
        _, client, _, err = run_demo(demo, [])
        check(err is not None and '角色清单无效' in str(err) and not client.calls, '没设 roles：报错，不调模型')
        print('wf cost passed')
    finally:
        shutil.rmtree(tmp)


if __name__ == '__main__':
    run()
