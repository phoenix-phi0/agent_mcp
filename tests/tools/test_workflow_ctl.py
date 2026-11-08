import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))  # 项目根，run_all 不设 PYTHONPATH
"""编排的外部控制（tools/workflow_ctl.py）：逐步停、外部交结果、换模型换卡、自动跑、
按角色停、回退、回放核对、中止、进程丢了的判断。

全程用离线假模型（client 传进去就在本进程里同步推进），不起后台进程、不调真模型。
临时目录建在项目的 data/tmp 下：控制接口只认项目里的 runs/*.json。
"""
import json
import shutil
import tempfile
from pathlib import Path

from dsl.client import ScriptClient
from tools import workflow_ctl as wc

ROOT = Path(__file__).resolve().parents[2]
_sys.path.insert(0, str(Path(__file__).resolve().parent))
from wf_fixtures import REPLIES, acceptance, contract, review  # noqa: E402
ROLES = ['ARCHITECT', 'ARCHITECT_GLM', 'ARCHITECT', 'ARCHITECT_GLM', 'ARCHITECT',
         'ENGINEER', 'ENGINEER', 'QA_ENGINEER', 'ENGINEER', 'QA_ENGINEER']


def demo_copy(tmp, name):
    dst = tmp / name
    shutil.copytree(ROOT / 'workflow_demo', dst,
                    ignore=shutil.ignore_patterns('runs', 'work', '*.bak-*', '__pycache__'))
    return dst


def client(replies):
    c = ScriptClient(list(replies))
    c.offline = True
    return c


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print('  ✓', msg)


def raises(fn, text):
    try:
        fn()
    except wc.ControlError as e:
        if text not in str(e):
            raise AssertionError(f'报错内容不对：{e}')
        return True
    raise AssertionError('应当报错')


def ok_steps(s):
    return [x for x in s['steps'] if x['status'] == 'ok']


def run():
    (ROOT / 'data/tmp').mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix='wfctl-', dir=ROOT / 'data/tmp'))
    try:
        # ---- 1. 逐步：开始停在第 1 步，不调模型
        demo = demo_copy(tmp, 'a')
        c = client(REPLIES[1:])
        s = wc.start(demo, client=c)
        run_id = s['run']
        check(s['status'] == 'waiting' and s['pending']['step'] == 1
              and s['pending']['role'] == 'ARCHITECT', '开始后停在第 1 步 ARCHITECT')
        check(len(c.calls) == 0 and s['steps'][0]['status'] == 'waiting', '没调模型，第 1 步标 waiting')
        d = wc.status(run_id, detail=True)
        check(d['pending']['system'] and '只返回一个 JSON 对象' in d['pending']['prompt']
              and d['pending']['model'], 'detail 带系统提示、提示词、默认模型，外部能自己执行')
        check('system' not in s['pending'], '摘要里不带大段提示词')
        check((demo / 'runs' / (Path(run_id).name[:-5] + '.ctl')).is_file(), '控制文件在记录旁边')

        # ---- 2. 外部交结果
        raises(lambda: wc.submit(run_id, {'x': 1}, step=2), '停在第 1 步')
        raises(lambda: wc.submit(run_id, '不是json'), '不是 JSON')
        # 外部交的结果也按格式校验：形状不对直接拒，不进记录
        raises(lambda: wc.submit(run_id, {'tasks': [{'content': 'x', 'agent': 'ENGINEER'}]}),
               '不符合格式 contract')
        check(d['pending']['format'] == 'contract' and d['pending']['schema']['required'] == ['contract']
              and '本次调用：接口约定（提交格式 contract）' in d['pending']['prompt'],
              'pending 带格式名、Schema，提示词写明本次调用和格式')
        s = wc.submit(run_id, REPLIES[0], client=c)
        check(s['status'] == 'waiting' and s['pending']['step'] == 2, '交了第 1 步，停在第 2 步')
        check(s['steps'][0]['source'] == 'external' and s['steps'][0]['model'] == 'external',
              '第 1 步记成外部结果')

        # ---- 3. 内置执行器跑一步；再换卡换模型跑一步
        s = wc.execute(run_id, wait=True, client=c)
        check(len(c.calls) == 1 and s['pending']['step'] == 3, '执行第 2 步，停在第 3 步')
        raises(lambda: wc.execute(run_id, role='../x', client=c), '角色卡名无效')
        raises(lambda: wc.execute(run_id, model='乱写', client=c), '模型名无效')
        s = wc.execute(run_id, model='cli:goose/glm-5.3', role='ARCHITECT_GLM', wait=True, client=c)
        st3 = s['steps'][2]
        check(st3['role'] == 'ARCHITECT_GLM' and st3['default_role'] == 'ARCHITECT'
              and st3['model'] == 'cli:goose/glm-5.3' and st3['model_override'] == 'cli:goose/glm-5.3'
              and st3['source'] == 'execute', '第 3 步换了卡和模型，记录里看得出原来是谁')

        # ---- 4. 长期覆盖 + 自动跑到底
        raises(lambda: wc.configure(run_id, models={'ENGINEER': 'x'}), '模型名无效')
        wc.configure(run_id, models={'ENGINEER': 'cli:claude/haiku'})
        s = wc.resume(run_id, wait=True, client=c)
        check(s['status'] == 'done' and len(c.calls) == 9 and 'pending' not in s, '自动跑完，共调 9 次')
        check([x['default_role'] if x.get('default_role') else x['role'] for x in s['steps']] == ROLES,
              '十步角色顺序和不受控时一样')
        eng = [x for x in s['steps'] if x['role'] == 'ENGINEER']
        check(len(eng) == 3 and all(x['model'] == 'cli:claude/haiku' for x in eng),
              'ENGINEER 三步都用了覆盖的模型')
        trace = json.loads((ROOT / run_id).read_text(encoding='utf-8'))
        check(trace['resumes'] == 4 and [e['seq'] for e in trace['events']]
              == list(range(1, len(trace['events']) + 1)), '每次继续都回放重写，seq 连续')
        check([e['result'] for e in trace['events'] if e['type'] == 'task'] == REPLIES,
              '十步结果和直接跑一样')

        # ---- 5. 回退到第 8 步（QA），外部改判通过
        s = wc.rewind(run_id, 8, client=c)
        check(s['status'] == 'waiting' and s['pending']['step'] == 8
              and s['pending']['role'] == 'QA_ENGINEER' and len(ok_steps(s)) == 7, '回退后停在第 8 步，前 7 步还在')
        s = wc.submit(run_id, acceptance('通过'), client=c)
        check(s['status'] == 'done' and len(s['steps']) == 8 and len(c.calls) == 9,
              '第 8 步改判通过，不再返工，直接结束')
        cfg = json.loads((demo / 'runs' / (Path(run_id).name[:-5] + '.ctl')).read_text(encoding='utf-8'))
        check([h['op'] for h in cfg['history']] == ['start', 'submit', 'execute', 'execute', 'configure',
                                                    'resume', 'rewind', 'submit'], '控制文件记下每次操作')

        # ---- 6. 输入改了，回放对不上就报错
        rz = demo / 'run.zs'
        rz.write_text(rz.read_text(encoding='utf-8').replace('实现用户接口', '实现订单接口'), encoding='utf-8')
        s = wc.rewind(run_id, 3, client=c)
        check(s['status'] == 'error' and '对不上' in (s['error'] or ''), '入口脚本改过：回放报错，不悄悄走偏')

        # ---- 7. 自动跑，碰到 QA 停下；中止
        demo2 = demo_copy(tmp, 'b')
        c2 = client(REPLIES)
        s = wc.start(demo2, mode='auto', stop_roles=['QA_ENGINEER'], client=c2)
        check(s['status'] == 'waiting' and s['pending']['step'] == 8 and len(c2.calls) == 7,
              'auto + stop_roles：前 7 步自动跑，QA 前停下')
        s = wc.pause(s['run'])
        check(s['mode'] == 'step', 'pause 改成逐步')
        s = wc.abort(s['run'])
        check(s['status'] == 'aborted' and 'pending' not in s, '中止')
        check(wc.list_runs(demo2)[0]['status'] == 'aborted', 'list_runs 看得到')

        # ---- 8. 记录说在跑、进程却没了 → interrupted
        r = s['run']
        t = json.loads((ROOT / r).read_text(encoding='utf-8'))
        t['status'] = 'running'
        (ROOT / r).write_text(json.dumps(t, ensure_ascii=False), encoding='utf-8')
        cf = ROOT / r[:-5]
        cf = cf.with_name(cf.name + '.ctl')
        cfg = json.loads(cf.read_text(encoding='utf-8'))
        cfg['worker'] = 999999
        cf.write_text(json.dumps(cfg), encoding='utf-8')
        check(wc.status(r)['status'] == 'interrupted', '进程没了显示 interrupted')

        # ---- 9. 节点失败：停在这一步，原始回复留在记录里；重试成功后失败那次还在
        demo3 = demo_copy(tmp, 'c')
        c3 = client(['这不是 JSON，是一段话', review('通过')])
        r3 = wc.start(demo3, client=c3)['run']
        wc.submit(r3, contract('v1'), client=c3)
        s = wc.execute(r3, wait=True, client=c3)
        check(s['status'] == 'waiting' and s['pending']['step'] == 2
              and '没有返回 JSON' in s['pending'].get('last_error', ''), '第 2 步失败：停在第 2 步，带上失败原因')
        t3 = json.loads((ROOT / r3).read_text(encoding='utf-8'))
        bad = [e for e in t3['events'] if e['type'] == 'task' and e['status'] == 'error']
        check(len(bad) == 1 and bad[0]['raw'] == '这不是 JSON，是一段话', '原始回复记进失败那条事件')
        # 记录停在 error（老版本、或进程中途挂掉）且控制文件里还留着上次的 execute：
        # 先回放到停下时不能把旧指令再执行一遍，只有这次 execute 调一次模型
        t3['status'] = 'error'
        t3.pop('pending', None)
        (ROOT / r3).write_text(json.dumps(t3, ensure_ascii=False), encoding='utf-8')
        s = wc.execute(r3, wait=True, client=c3)
        check(len(c3.calls) == 2, '从 error 状态接着 execute：旧指令不重放，只调一次模型')
        check(s['status'] == 'waiting' and s['pending']['step'] == 3, '重试成功，往下走到第 3 步')
        rows = [(x['step'], x['status']) for x in s['steps']]
        check(rows[:3] == [(1, 'ok'), (2, 'error'), (2, 'ok')], '失败那次尝试保留在记录里，回放不丢')

        # ---- 10. 不是受控记录、越出项目的路径都拒
        raises(lambda: wc.status('/etc/passwd'), '不是编排记录')
        print('workflow ctl passed')
    finally:
        shutil.rmtree(tmp)


if __name__ == '__main__':
    run()
