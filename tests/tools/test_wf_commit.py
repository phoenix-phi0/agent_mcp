import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))  # 项目根，run_all 不设 PYTHONPATH
"""提交流程（workflow_demo/commit.wf）：在临时仓库上真跑指令节点（我的改动、查密钥、暂存、暂存版和 HEAD 副本里跑测试、
对照失败），模型步骤（失败分析、写提交说明）用假回复。核对每种情况停在哪、谁上场、指令节点不消耗模型回复、
流程本身不提交。"""
import json
import shutil
import subprocess
import uuid
from pathlib import Path

from dsl.client import ScriptClient
from tools import cmd
from tools import workflow_ctl as wc

ROOT = Path(__file__).resolve().parents[2]
TEST = 'tests/tools/test_v.py'
FAKE_KEY = 'sk-' + 'Zq7' * 10          # 测试用的假密钥（拼出来，源码里不放整串）


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print('  ✓', msg)


def git(repo, *a):
    return subprocess.run(['git', '-C', str(repo), '-c', 'user.name=t', '-c', 'user.email=t@t', *a],
                          capture_output=True, text=True, check=True).stdout


def client(replies):
    c = ScriptClient(list(replies))
    c.offline = True
    return c


NOTE = {'状态': '完成', '结果': '写了提交说明', '种类': '提交说明', '标题': 'v.txt：改成 1 ok',
        '正文': '- v.txt：改成 1 ok\n- 验证：ok', '依据': [{'出处': 'staged', '原文': 'v.txt'}], '把握': '高'}
TRI = {'状态': '已归因', '结果': '一条新挂', '依据': [{'出处': 'v.txt:1', '原文': '2'}], '把握': '高',
       'failures': [{'test': TEST, '归因': '我的改动', '原因': 'v.txt 不以 1 开头', '依据': [{'出处': 'v.txt:1', '原文': '2'}],
                     '把握': '高', '建议': '交给这次的工程师改回'}]}


def setup(tmp):
    demo = tmp / 'workflow_demo'
    shutil.copytree(ROOT / 'workflow_demo', demo, ignore=shutil.ignore_patterns('runs', 'work', '*.bak-*', '__pycache__'))
    repo = demo / 'work/proj'
    (repo / 'tests/tools').mkdir(parents=True)
    (repo / TEST).write_text('import pathlib\nassert pathlib.Path("v.txt").read_text().startswith("1")\nprint("ok")\n',
                             encoding='utf-8')
    (repo / 'v.txt').write_text('1\n', encoding='utf-8')
    git(repo, 'init', '-q', '-b', 'main')
    git(repo, 'add', '.')
    git(repo, 'commit', '-q', '-m', 'init')
    r = cmd.run_as('workflow', 'git_mark', {'repo': str(repo)})
    mark = json.loads(r['output'].strip().splitlines()[-1])['id']
    return demo, repo, mark


def start(demo, repo, mark, c, allow='["v.txt"]'):
    return wc.start(demo, entry='run_commit.zs', mode='auto', wait=True, client=c,
                    vars={'repo': str(repo), 'mark': mark, 'allow': allow, 'test': TEST, 'wt': 'proj'})


def names(s):
    return [x['name'] for x in s['steps']]


def run():
    tmp = ROOT / 'data/tmp' / f'wf_commit_{uuid.uuid4().hex[:6]}'
    tmp.mkdir(parents=True)
    try:
        # 1. 正常：暂存 → 暂存版测试过 → 写提交说明 → 停下等人提交（流程不提交）
        demo, repo, mark = setup(tmp / 'a')
        head = git(repo, 'rev-parse', 'HEAD')
        (repo / 'v.txt').write_text('1 ok\n', encoding='utf-8')
        c = client([NOTE])
        s = start(demo, repo, mark, c)
        pd = s.get('pending', {})
        check(s['status'] == 'waiting' and pd.get('name') == '写提交说明' and pd.get('phase') == 'after'
              and pd.get('result', {}).get('标题') == NOTE['标题'],
              f'写提交说明的节点写了「确认 之后」：写完停下，人看得到说明（{s["status"]} {pd.get("name")} {s.get("error")}）')
        check(names(s) == ['我的改动', '查密钥', '暂存', '暂存版测试', '基线测试', '对照失败', '写提交说明'], f'步骤：{names(s)}')
        check([x['role'] for x in s['steps']][-1] == 'SCRIBE' and len(c.calls) == 1,
              '只有记录员调了一次模型，指令节点不消耗回复')
        check('v.txt' in c.calls[0]['prompt'] and 'ok' in c.calls[0]['prompt'], '记录员看得到暂存的文件和测试输出')
        check(git(repo, 'diff', '--cached', '--name-only').split() == ['v.txt'] and git(repo, 'rev-parse', 'HEAD') == head,
              '暂存了 v.txt，没有提交')
        s2 = wc.approve(s['run'], attempt=pd['attempt'], client=c)
        s2 = wc.status(s['run']) if s2.get('status') == 'running' else s2
        check(s2['status'] == 'done' and git(repo, 'rev-parse', 'HEAD') == head and len(c.calls) == 1,
              '人确认后流程结束；暂存没有重做，也没有提交')

        # 2. 暂存版测试新挂：失败分析，然后停下交给人，不写提交说明
        demo, repo, mark = setup(tmp / 'b')
        (repo / 'v.txt').write_text('2\n', encoding='utf-8')
        c = client([TRI])
        s = start(demo, repo, mark, c)
        check(s['status'] == 'waiting' and s['pending']['name'] == '新挂了', f'停在新挂了：{s.get("pending", {}).get("name")}')
        check(names(s)[-3:] == ['对照失败', '失败分析', '新挂了'] and '写提交说明' not in names(s)
              and s['steps'][-2]['role'] == 'TRIAGE' and len(c.calls) == 1, f'交给失败分析员，不写提交说明：{names(s)}')
        check(TEST in c.calls[0]['prompt'] and '"new"' in c.calls[0]['prompt'], '失败分析员看得到新挂的测试')

        # 3. 查到密钥：停下，不暂存
        demo, repo, mark = setup(tmp / 'c')
        (repo / 'v.txt').write_text('1 ok\n', encoding='utf-8')
        (repo / 'conf.py').write_text(f'api_key = "{FAKE_KEY}"\n', encoding='utf-8')
        c = client([])
        s = start(demo, repo, mark, c, allow='["v.txt","conf.py"]')
        check(s['status'] == 'waiting' and s['pending']['name'] == '查到密钥' and names(s) == ['我的改动', '查密钥', '查到密钥']
              and c.calls == [], f'查到密钥：停下，没调模型：{names(s)}')
        check(git(repo, 'diff', '--cached', '--name-only') == '' and FAKE_KEY not in json.dumps(s, ensure_ascii=False),
              '什么都没暂存；状态里没有密钥原文')

        # 4. 有范围外的改动：停下
        demo, repo, mark = setup(tmp / 'd')
        (repo / 'v.txt').write_text('1 ok\n', encoding='utf-8')
        (repo / 'x.txt').write_text('别的\n', encoding='utf-8')
        s = start(demo, repo, mark, client([]))
        check(s['pending']['name'] == '范围不对' and names(s) == ['我的改动', '范围不对'], f'范围外：停在范围不对：{names(s)}')

        # 5. 起点以来没有改动：停下
        demo, repo, mark = setup(tmp / 'e')
        s = start(demo, repo, mark, client([]))
        check(s['pending']['name'] == '没有改动' and names(s) == ['我的改动', '没有改动'], f'没有改动：停下：{names(s)}')
        print('wf commit passed')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    run()
