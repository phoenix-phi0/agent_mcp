import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))  # 项目根，run_all 不设 PYTHONPATH
"""编排里的机械步骤：节点写「指令 命令名 键=值 …」，内置的机器人（ROBOT）跑命令表里的命令，不调模型、不建卡。
参数里的 {变量} 展开、整个是变量时保留列表、int/bool 照命令表转类型；退出码不是 0 记成「失败」由流程分支；
命令被拒、流程没权限的命令（推送）、写法不对、变量没值、结果不符合格式都报错；卡上写 model=cmd 加载报错。"""
import json
import shutil
import tempfile
from pathlib import Path

from dsl.client import ScriptClient
from tools.dsl import DSLEngine

ROOT = Path(__file__).resolve().parents[2]


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print('  ✓', msg)


def demo_copy(tmp):
    dst = tmp / 'workflow_demo'
    shutil.copytree(ROOT / 'workflow_demo', dst,
                    ignore=shutil.ignore_patterns('runs', 'work', '*.bak-*', '__pycache__'))
    return dst


def run_flow(demo, wf, zs_vars='', replies=()):
    shutil.rmtree(demo / 'runs', ignore_errors=True)     # 每次只留这一次的运行记录（同一秒里跑几次文件名会撞）
    (demo / 't.wf').write_text(wf, encoding='utf-8')
    (demo / 't.zs').write_text('用包 workflow\n' + zs_vars + '编排执行 t.wf\n', encoding='utf-8')
    client = ScriptClient(list(replies))
    client.offline = True
    engine = DSLEngine(client=client, workdir=demo, verbs_root=ROOT / 'verbs', verbose=False)
    error = None
    try:
        engine.run_file('t.zs')
    except Exception as e:      # noqa: BLE001
        error = e
    files = sorted((demo / 'runs').glob('*.json'))
    trace = json.loads(files[-1].read_text(encoding='utf-8')) if files else None
    return client, trace, error


def run():
    (ROOT / 'data/tmp').mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(dir=ROOT / 'data/tmp'))     # 受控运行要求工作目录在项目里
    try:
        demo = demo_copy(tmp)

        # 1. 正常：两步指令，按第一步的结果分支；不消耗假客户端的回复
        wf = ('看改动\n    指令 git_diff paths={files} limit={n}\n    记录 d\n'
              '如果 d.状态 == 成功\n    数行数\n        任务 数一下工具目录\n        指令 count_lines path=tools limit=3\n        记录 c\n')
        client, t, err = run_flow(demo, wf, '设 files = ["tools/cmd.py","tools/cmd_table.json"]\n设 n = 5\n')
        check(err is None and t['status'] == 'done' and client.calls == [], f'跑完、没调模型：{err}')
        tasks = [e for e in t['events'] if e['type'] == 'task']
        check([e['name'] for e in tasks] == ['看改动', '数行数'] and [e['role'] for e in tasks] == ['ROBOT', 'ROBOT'],
              '两步都由机器人跑，按结果分支')
        check(tasks[0]['command'] == {'name': 'git_diff', 'args': {'paths': '{files}', 'limit': '{n}'}},
              f'记录里留着节点写的指令：{tasks[0].get("command")}')
        d = tasks[0]['result']
        check(d['状态'] == '成功' and d['exit_code'] == 0 and d['command'] == 'git_diff'
              and d['args'] == {'paths': ['tools/cmd.py', 'tools/cmd_table.json'], 'limit': 5},
              f'整个值是 {{files}} 时传列表，limit 照命令表转成整数：{d["args"]}')
        c = tasks[1]['result']
        check(c['状态'] == '成功' and 'tools' in c['结果'] and tasks[1]['task'] == '数一下工具目录',
              '数行数：结果里有输出；写了任务就当说明')

        # 2. 各种该报错的
        cases = (
            ('步\n    指令 find path=/etc\n    记录 r\n', '', '被拒'),                     # 路径越出 /workspace
            ('步\n    指令 git_push\n    记录 r\n', '', '没有权限'),                       # 流程不能推送
            ('步\n    指令 git_diff paths = x\n    记录 r\n', '', '键=值'),                 # 带空格
            ('步\n    角色 ENGINEER\n    指令 git_diff\n    记录 r\n', '', '不写角色'),
            ('步\n    指令 git_diff limit=1 limit=2\n    记录 r\n', '', '两次'),
            ('步\n    角色 ROBOT\n    记录 r\n', '', '指令'),                              # 机器人没有指令
            ('看改动\n    指令 git_diff paths={files}\n    记录 d\n', '', '没有值'),          # 变量没值
        )
        for wf, zs, word in cases:
            client, t, err = run_flow(demo, wf, zs)
            check(err is not None and word in str(err), f'{wf.splitlines()[1].strip()}：报错（{str(err)[:70]}）')

        # 3. 带格式：结果按格式校验
        (demo / 'formats/cmd_need_x.json').write_text(json.dumps({'type': 'object', 'required': ['x']}), encoding='utf-8')
        client, t, err = run_flow(demo, '数\n    指令 count_lines path=tools limit=3\n    格式 cmd_need_x\n    记录 r\n')
        check(err is not None and '不符合格式' in str(err), f'结果不符合格式：报错（{str(err)[:80]}）')

        # 4. 卡上写 model=cmd：加载就报错，机械步骤只能写成节点的指令
        d = demo / 'agents/CMD_CARD'
        d.mkdir(parents=True)
        (d / 'agent.json').write_text(json.dumps({'model': 'cmd'}), encoding='utf-8')
        (d / 'SOUL.md').write_text('x', encoding='utf-8')
        client, t, err = run_flow(demo, '步\n    任务 x\n    角色 CMD_CARD\n    记录 r\n')
        check(err is not None and '不能写 cmd' in str(err), f'model=cmd 的卡：报错（{str(err)[:70]}）')
        # 5. 节点上的「确认」：受控运行在这里停；写错报错；不受控的运行照常跑完
        from tools import workflow_ctl as wc
        client, t, err = run_flow(demo, '数\n    指令 count_lines path=tools limit=3\n    确认 稍后\n    记录 r\n')
        check(err is not None and '确认只能写' in str(err), f'确认写错：报错（{str(err)[:60]}）')
        client, t, err = run_flow(demo, '数\n    指令 count_lines path=tools limit=3\n    确认 之后\n    记录 r\n')
        check(err is None and t['status'] == 'done', '不受控的运行：确认不起作用，照常跑完')
        shutil.rmtree(demo / 'runs', ignore_errors=True)
        (demo / 't.wf').write_text('数\n    指令 count_lines path=tools limit=3\n    确认 之前\n    记录 r\n'
                                   '再数\n    指令 count_lines path=tools limit=3\n    记录 r2\n', encoding='utf-8')
        c = ScriptClient([])
        c.offline = True
        s = wc.start(demo, entry='t.zs', mode='auto', wait=True, client=c)
        check(s['status'] == 'waiting' and s['pending']['name'] == '数' and s['pending']['phase'] == 'before'
              and s['pending']['reason'] == 'node', f'确认 之前：自动模式也停在开始前（{s.get("pending", {}).get("reason")}）')
        s = wc.execute(s['run'], client=c, wait=True)
        check(s['status'] == 'done' and [x['name'] for x in s['steps']] == ['数', '再数'], 'execute 以后接着跑完，下一个节点不停')
        print('wf cmd step passed')
    finally:
        shutil.rmtree(tmp)


if __name__ == '__main__':
    run()
