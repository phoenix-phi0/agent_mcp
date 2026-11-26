import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))  # 项目根，run_all 不设 PYTHONPATH
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))
"""改代码验收流程（workflow_demo/code_accept.wf）：在临时仓库上真跑指令节点（开工作树、记起点、我的改动、
在工作树里跑测试、HEAD 副本里跑基线、对照失败、抽查依据、暂存），模型步骤用假回复；
假回复「交上来」时顺手改工作树里的文件，模拟工程师干活。核对步骤顺序、角色、跳转、停下的位置，
以及指令节点不消耗模型回复。"""
import json
import shutil
import subprocess
import uuid
from pathlib import Path

from dsl.client import ScriptClient
from tools import workflow_ctl as wc
from wf_fixtures import impl

ROOT = Path(__file__).resolve().parents[2]
TEST = 'tests/tools/test_v.py'


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print('  ✓', msg)


def git(repo, *a):
    return subprocess.run(['git', '-C', str(repo), '-c', 'user.name=t', '-c', 'user.email=t@t', *a],
                          capture_output=True, text=True, check=True).stdout


class Client(ScriptClient):
    """第 i 次回复之前先跑 effects[i]（模拟工程师在工作树里改文件）。"""

    def __init__(self, replies, effects):
        super().__init__(replies)
        self.effects = effects
        self.offline = True

    def chat_messages(self, messages, temperature=None, **kw):
        fn = self.effects.get(self._i)
        if fn:
            fn()
        return super().chat_messages(messages, temperature=temperature, **kw)


def accept(decide, grip='高', ev=None, task=None):
    ev = ev if ev is not None else [{'出处': 'v.txt:1', '原文': '1 改过'}]
    r = {'decide': decide, 'summary': f'验收：{decide}', '把握': grip,
         'checked': [{'item': '改对了 v.txt', 'result': '满足' if decide == '通过' else '不满足', '依据': ev, '把握': grip}]}
    if task:
        r['task'] = task
    return r


def setup(tmp):
    repo = tmp / 'repo'
    (repo / 'tests/tools').mkdir(parents=True)
    (repo / TEST).write_text('import pathlib\nassert pathlib.Path("v.txt").read_text().startswith("1")\nprint("ok")\n',
                             encoding='utf-8')
    (repo / 'v.txt').write_text('1\n', encoding='utf-8')
    git(repo, 'init', '-q', '-b', 'main')
    git(repo, 'add', '.')
    git(repo, 'commit', '-q', '-m', 'init')
    demo = tmp / 'workflow_demo'
    shutil.copytree(ROOT / 'workflow_demo', demo, ignore=shutil.ignore_patterns('runs', 'work', '*.bak-*', '__pycache__'))
    (demo / 'work').mkdir()
    return repo, demo


def start(demo, repo, client, wt='wt1'):
    return wc.start(demo, entry='run_code_accept.zs', mode='auto', wait=True, client=client,
                    vars={'task': '把 v.txt 改成「1 改过」', 'repo': str(repo), 'allow': '["v.txt"]', 'test': TEST,
                          'checklist': '1 v.txt 第一行是「1 改过」', 'wt': wt, 'wt_root': str(demo / 'work'),
                          'engineer': 'ENGINEER'})


def trace(s):
    p = Path(s['run'])
    return json.loads(p.read_text(encoding='utf-8'))


def run():
    tmp = ROOT / 'data/tmp' / f'wf_code_accept_{uuid.uuid4().hex[:6]}'
    tmp.mkdir(parents=True)
    try:
        # 1. 先越界（多建了 x.txt）→ 范围返工 → 测试过 → 验收把握低 → 升档重判通过 → 暂存 → 停在人确认
        repo, demo = setup(tmp / 'a')
        wt = demo / 'work/wt1'
        effects = {0: lambda: ((wt / 'v.txt').write_text('1 改过\n', encoding='utf-8'),
                               (wt / 'x.txt').write_text('越界\n', encoding='utf-8')),
                   1: lambda: (wt / 'x.txt').unlink()}
        c = Client([impl('改 v.txt'), impl('删掉 x.txt'), accept('通过', '低'), accept('通过', '高')], effects)
        s = start(demo, repo, c)
        pd = s.get('pending', {})
        check(s['status'] == 'waiting' and pd.get('name') == '暂存' and pd.get('phase') == 'after' and pd.get('reason') == 'node'
              and pd.get('result', {}).get('状态') == '成功',
              f'暂存节点写了「确认 之后」：跑完停下等人确认，带着暂存结果（{s["status"]} {pd.get("name")} {pd.get("phase")} {s.get("error")}）')
        names = [x['name'] for x in s['steps']]
        check(names == ['开工作树', '记起点', '改代码', '我的改动', '范围返工', '我的改动', '跑测试', '基线测试', '对照失败',
                        '验收', '升档验收', '抽查依据', '暂存'], f'步骤顺序：{names}')
        roles = [x['role'] for x in s['steps']]
        check(roles[:3] == ['ROBOT', 'ROBOT', 'ENGINEER'] and roles[9:11] == ['ACCEPTOR', 'ACCEPTOR_SENIOR']
              and roles[4] == 'ENGINEER' and roles[-1] == 'ROBOT', f'角色：{roles}')
        check(len(c.calls) == 4, f'只有 4 次模型调用（工程师 2 次、验收 2 次），指令节点不消耗回复（实际 {len(c.calls)}）')
        t = trace(s)
        jumps = [(e['target'], e['count']) for e in t['events'] if e['type'] == 'jump']
        check(jumps == [('c', 1)], f'越界跳回一次：{jumps}')
        tasks = {e['name']: e for e in t['events'] if e['type'] == 'task' and e.get('status') == 'ok'}
        check('x.txt' in c.calls[1]['prompt'] and 'v.txt' in c.calls[1]['prompt'], '范围返工的任务里写了范围外的文件和允许清单')
        check(tasks['对照失败']['result']['data']['new'] == [] and tasks['跑测试']['result']['状态'] == '成功',
              '测试过，没有新挂')
        check('previous' in c.calls[3]['prompt'] and '"把握": "低"' in c.calls[3]['prompt'], '升档验收看得到上一位的结果')
        check(tasks['抽查依据']['result']['状态'] == '成功', '依据抽查对得上')
        check(git(wt, 'diff', '--cached', '--name-only').split() == ['v.txt'] and git(repo, 'status', '--porcelain') == '',
              '工作树里只暂存了 v.txt；主仓库没被动过')
        s2 = wc.approve(s['run'], attempt=pd['attempt'], client=c)
        s2 = wc.status(s['run']) if s2.get('status') == 'running' else s2
        check(s2['status'] == 'done' and len(c.calls) == 4, f'人确认（approve）后流程结束，不再调模型：{s2["status"]}')

        # 2. 改坏了 → 新挂 → 验收需修改但依据写错行 → 依据重判 → 返工改好 → 验收通过 → 暂存
        repo, demo = setup(tmp / 'b')
        wt = demo / 'work/wt1'
        effects = {0: lambda: (wt / 'v.txt').write_text('2\n', encoding='utf-8'),
                   3: lambda: (wt / 'v.txt').write_text('1 改过\n', encoding='utf-8')}
        bad_ev = [{'出处': 'v.txt:9', '原文': '2'}]
        good_ev = [{'出处': 'v.txt:1', '原文': '2'}]
        c = Client([impl('改 v.txt'), accept('需修改', ev=bad_ev, task='v.txt 要以 1 开头'),
                    accept('需修改', ev=good_ev, task='v.txt 要以 1 开头'), impl('改回'), accept('通过')], effects)
        s = start(demo, repo, c)
        names = [x['name'] for x in s['steps']]
        check(s['status'] == 'waiting' and s['pending']['name'] == '暂存' and s['pending']['phase'] == 'after',
              f'最后停在暂存之后等人确认：{s.get("error")}')
        check(names == ['开工作树', '记起点', '改代码', '我的改动', '跑测试', '基线测试', '对照失败', '验收', '抽查依据', '依据重判',
                        '返工', '我的改动', '跑测试', '基线测试', '对照失败', '验收', '抽查依据', '暂存'], f'步骤顺序：{names}')
        t = trace(s)
        oks = [e for e in t['events'] if e['type'] == 'task' and e.get('status') == 'ok']
        f1 = next(e for e in oks if e['name'] == '对照失败')
        check(f1['result']['data']['new'] == [TEST], f'第一轮：测试新挂，按测试路径记：{f1["result"]["data"]}')
        check(TEST in c.calls[1]['prompt'] and '"new"' in c.calls[1]['prompt'], '验收员看得到对照失败的新挂')
        ev = next(e for e in oks if e['name'] == '抽查依据')
        check(ev['result']['状态'] == '失败' and 'evidence' in c.calls[2]['prompt'], '依据写错行：抽查失败，交高档重判，看得到哪条对不上')
        check(c.calls[3]['prompt'].startswith('任务：v.txt 要以 1 开头') or 'v.txt 要以 1 开头' in c.calls[3]['prompt'],
              '返工拿到验收的 task')
        check([(e['target'], e['count']) for e in t['events'] if e['type'] == 'jump'] == [('c', 1)] and len(c.calls) == 5,
              '返工跳回一次，5 次模型调用')

        # 3. 两位验收员都把握低：停下交给人判
        repo, demo = setup(tmp / 'c')
        wt = demo / 'work/wt1'
        c = Client([impl('改 v.txt'), accept('通过', '低'), accept('通过', '低')],
                   {0: lambda: (wt / 'v.txt').write_text('1 改过\n', encoding='utf-8')})
        s = start(demo, repo, c)
        check(s['status'] == 'waiting' and s['pending']['name'] == '人判验收' and s['pending']['card'] == 'HUMAN'
              and len(c.calls) == 3, f'都拿不准：停在人判验收，不往下暂存（{s.get("pending", {}).get("name")}）')
        check(git(wt, 'diff', '--cached', '--name-only') == '', '还没暂存')
        print('wf code accept passed')
    finally:
        for wt in tmp.glob('*/workflow_demo/work/*'):
            subprocess.run(['git', '-C', str(wt), 'worktree', 'remove', '--force', str(wt)], capture_output=True)
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    run()
