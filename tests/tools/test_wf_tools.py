import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))  # 项目根，run_all 不设 PYTHONPATH
"""编排的机械命令（scripts/cmd/wf_tools.py，经命令表、以 workflow 调用方身份跑）：
抽查依据、对照失败、记起点 / 我的改动 / 暂存我的改动、查密钥；最后在流程里用指令节点串一遍。"""
import json
import shutil
import subprocess
import uuid
from pathlib import Path

from tools import cmd
from dsl.client import ScriptClient
from tools.dsl import DSLEngine

ROOT = Path(__file__).resolve().parents[2]
FAKE_KEY = 'sk-' + 'Ab3' * 10          # 测试用的假密钥（拼出来，源码里不放整串）


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print('  ✓', msg)


def run(_cmd_name, **args):
    r = cmd.run_as('workflow', _cmd_name, args)
    last = (r.get('output') or '').strip().splitlines()[-1:] or ['{}']
    try:
        data = json.loads(last[0])
    except ValueError:
        data = {}
    return r, data


def git(repo, *a):
    return subprocess.run(['git', '-C', str(repo), '-c', 'user.name=t', '-c', 'user.email=t@t', *a],
                          capture_output=True, text=True, check=True).stdout


def main():
    tmp = ROOT / 'data/tmp' / f'wftools_test_{uuid.uuid4().hex[:6]}'
    tmp.mkdir(parents=True)
    try:
        # 1. 抽查依据
        proj = tmp / 'proj'
        (proj / 'app').mkdir(parents=True)
        (proj / 'app/orders.py').write_text('def create(qty):\n    if qty <= 0:\n        raise OrderError("BAD_QTY")\n    return qty\n',
                                            encoding='utf-8')
        (proj / '.env').write_text('X=1\n', encoding='utf-8')
        record = {'状态': '通过', '依据': [{'出处': 'app/orders.py:2-3', '原文': 'if qty <= 0:\n raise OrderError("BAD_QTY")'}],
                  'checked': [{'item': 'a', '依据': [{'出处': 'app/orders.py:9', '原文': 'x'},
                                                    {'出处': 'app/orders.py:4', '原文': 'return qty * 2'},
                                                    {'出处': 'app/nope.py:1', '原文': 'x'},
                                                    {'出处': '.env:1', '原文': 'X=1'},
                                                    {'出处': 'task_results[0]', '原文': '不抽查'}]}]}
        r, d = run('check_evidence', dir=str(proj), record=json.dumps(record, ensure_ascii=False))
        probs = {b['出处']: b['问题'] for b in d.get('bad', [])}
        check(r['exit_code'] == 1 and d['ok'] == 1 and d['skipped'] == 1 and len(probs) == 4,
              f'抽查依据：1 条对得上，4 条对不上，1 条不是文件:行没抽：{d}')
        check('超出' in probs['app/orders.py:9'] and '对不上' in probs['app/orders.py:4'] and '不存在' in probs['app/nope.py:1']
              and '敏感' in probs['.env:1'], f'各自的原因：{probs}')
        r, d = run('check_evidence', dir=str(proj), record=json.dumps({'依据': record['依据']}, ensure_ascii=False))
        check(r['exit_code'] == 0 and d['状态'] == '成功', '全对得上：成功')

        # 2. 对照失败
        out = ('..F\nFAILED tests/test_a.py::test_x - assert 1 == 2\nERROR tests/test_b.py::test_y\n'
               '1 failed, 1 error, 5 passed in 0.3s\n')
        r, d = run('compare_failures', base=json.dumps({'failing_tests': ['tests/test_b.py::test_y', 'tests/test_c.py::test_z']}),
                   now=out)
        check(r['exit_code'] == 1 and d['new'] == ['tests/test_a.py::test_x'] and d['still'] == ['tests/test_b.py::test_y']
              and d['fixed'] == ['tests/test_c.py::test_z'], f'对照失败：新挂 / 原来就挂 / 修好了：{d}')
        r, d = run('compare_failures', base='["FAIL: test_q (m.T)"]', now='FAIL: test_q (m.T)\nRan 3 tests\nFAILED (failures=1)\n')
        check(r['exit_code'] == 0 and d['new'] == [] and d['still'] == ['test_q (m.T)'], f'unittest 输出：只有原来就挂的，成功：{d}')

        # 3. 记起点 / 我的改动 / 暂存
        repo = tmp / 'repo'
        repo.mkdir()
        git(repo, 'init', '-q', '-b', 'main')
        (repo / 'a.txt').write_text('a1\n', encoding='utf-8')
        (repo / 'b.txt').write_text(''.join(f'b{i}\n' for i in range(1, 21)), encoding='utf-8')
        git(repo, 'add', '.')
        git(repo, 'commit', '-q', '-m', 'init')
        # 开工前别人已经改了 b.txt 第 1 行、留了一个未跟踪文件
        (repo / 'b.txt').write_text('别人改的\n' + ''.join(f'b{i}\n' for i in range(2, 21)), encoding='utf-8')
        (repo / 'other.txt').write_text('别人的\n', encoding='utf-8')
        r, d = run('git_mark', repo=str(repo))
        mid = d.get('id')
        check(r['exit_code'] == 0 and mid and d['dirty_at_mark'] == 1 and d['untracked_at_mark'] == 1,
              f'记起点：开工前已有改动 1 个、未跟踪 1 个：{d}')
        check((repo / 'b.txt').read_text(encoding='utf-8').startswith('别人改的'), '记起点不动工作区')
        # 开工后：我改 a.txt、b.txt 第 20 行，新建 c.txt；别人改了 other.txt、新建 x.txt
        (repo / 'a.txt').write_text('a2\n', encoding='utf-8')
        (repo / 'b.txt').write_text('别人改的\n' + ''.join(f'b{i}\n' for i in range(2, 20)) + '我改的\n', encoding='utf-8')
        (repo / 'c.txt').write_text('新文件\n', encoding='utf-8')
        (repo / 'other.txt').write_text('别人又改了\n', encoding='utf-8')
        (repo / 'x.txt').write_text('别人新建\n', encoding='utf-8')
        r, d = run('git_mine', repo=str(repo), mark=mid, allow=['a.txt', 'b.txt', 'c.txt'])
        check(r['exit_code'] == 1 and d['mine'] == ['a.txt', 'b.txt', 'c.txt'] and d['outside'] == ['other.txt', 'x.txt']
              and d['unclear'] == [] and d['before'] == 1, f'我的改动：我的 3 个，范围外 2 个（别人开工后改的、新建的）：{d}')
        r, d = run('git_mine', repo=str(repo), mark=mid, allow=['a.txt', 'b.txt', 'c.txt', 'other.txt', 'x.txt'])
        check(r['exit_code'] == 1 and d['unclear'] == ['other.txt'], f'开工前就有、开工后又改的未跟踪文件：归属不明：{d}')

        r, d = run('git_stage_mine', repo=str(repo), mark=mid, allow=['a.txt', 'b.txt', 'c.txt'])
        cached = git(repo, 'diff', '--cached', '--name-only').split()
        bdiff = git(repo, 'diff', '--cached', '--', 'b.txt')
        check(r['exit_code'] == 0 and d['staged'] == ['a.txt', 'b.txt', 'c.txt'] and cached == ['a.txt', 'b.txt', 'c.txt'],
              f'暂存：只放了清单里的 3 个：{d} {cached}')
        check('+我改的' in bdiff and '别人改的' not in bdiff,
              '同一个文件里，开工前别人的改动没被带进暂存区，只放了我的那一处')
        check(git(repo, 'status', '--porcelain', '--', 'x.txt').startswith('??'), '范围外的文件没动')

        # 4. 查密钥：新文件里有像密钥的内容，一个都不放
        git(repo, 'reset', '-q')
        r, d = run('git_mark', repo=str(repo))
        mid2 = d['id']
        (repo / 'conf.py').write_text(f'api_key = "{FAKE_KEY}"\n', encoding='utf-8')
        (repo / 'a.txt').write_text('a3\n', encoding='utf-8')
        r, d = run('git_stage_mine', repo=str(repo), mark=mid2, allow=['a.txt', 'conf.py'])
        check(r['exit_code'] == 1 and d['reason'] == '查到像密钥的内容' and git(repo, 'diff', '--cached', '--name-only') == '',
              f'查到密钥：一个都没放：{d.get("hits")}')
        check(FAKE_KEY not in r['output'], '输出里不打印命中的内容')
        r, d = run('secret_scan', repo=str(repo), paths=['conf.py', 'a.txt'])
        check(r['exit_code'] == 1 and d['hits'] == [{'文件': 'conf.py', '行': 1, '类别': 'API 密钥（sk-）'}]
              and FAKE_KEY not in r['output'], f'查密钥：报文件和行号：{d}')

        # 5. 补丁和暂存区对不上（我改的那一行紧挨着开工前别人的改动、暂存区里又已经有别的版本）：一个都不放
        (repo / 'conf.py').unlink()
        git(repo, 'checkout', '-q', '--', 'a.txt')
        git(repo, 'add', 'a.txt')                        # 暂存区：a.txt 已经是另一个版本
        (repo / 'a.txt').write_text('a1\n', encoding='utf-8')
        r, d = run('git_mark', repo=str(repo))
        mid3 = d['id']
        git(repo, 'reset', '-q', '--', 'a.txt')
        (repo / 'a.txt').write_text('a9\n', encoding='utf-8')
        git(repo, 'add', 'a.txt')
        (repo / 'a.txt').write_text('a10\n', encoding='utf-8')
        r, d = run('git_stage_mine', repo=str(repo), mark=mid3, allow=['a.txt'])
        check(r['exit_code'] == 1 and d['reason'] == '补丁和暂存区对不上', f'补丁放不进：报错不硬塞：{d.get("reason")}')

        # 6. 在流程里串起来：记起点 → （这里模拟工程师改文件）→ 我的改动 → 按结果分支
        demo = tmp / 'demo'
        shutil.copytree(ROOT / 'workflow_demo', demo, ignore=shutil.ignore_patterns('runs', 'work', '*.bak-*', '__pycache__'))
        repo2 = tmp / 'repo2'
        repo2.mkdir()
        git(repo2, 'init', '-q', '-b', 'main')
        (repo2 / 'a.txt').write_text('a\n', encoding='utf-8')
        git(repo2, 'add', '.')
        git(repo2, 'commit', '-q', '-m', 'init')
        (demo / 't.wf').write_text(
            '记起点\n    指令 git_mark repo={repo}\n    记录 m\n'
            '我的改动\n    指令 git_mine repo={repo} mark={m.data.id} allow={allow}\n    记录 mine\n'
            '如果 mine.状态 == 成功\n    暂存\n        指令 git_stage_mine repo={repo} mark={m.data.id} allow={allow}\n        记录 st\n',
            encoding='utf-8')
        (demo / 't.zs').write_text(f'用包 workflow\n设 repo = {repo2}\n设 allow = ["a.txt"]\n编排执行 t.wf\n', encoding='utf-8')
        engine = DSLEngine(client=ScriptClient([]), workdir=demo, verbs_root=ROOT / 'verbs', verbose=False)
        engine.client.offline = True
        orig = cmd.run_as

        def run_as(caller, name, args):          # 模拟：记完起点，工程师改了 a.txt
            r = orig(caller, name, args)
            if name == 'git_mark':
                (repo2 / 'a.txt').write_text('a 改过\n', encoding='utf-8')
            return r
        cmd.run_as = run_as
        try:
            engine.run_file('t.zs')
        finally:
            cmd.run_as = orig
        t = json.loads(sorted((demo / 'runs').glob('*.json'))[-1].read_text(encoding='utf-8'))
        tasks = [e for e in t['events'] if e['type'] == 'task']
        check([e['name'] for e in tasks] == ['记起点', '我的改动', '暂存'] and tasks[1]['result']['data']['mine'] == ['a.txt']
              and git(repo2, 'diff', '--cached', '--name-only').split() == ['a.txt'],
              '流程里：记起点 → 我的改动（只有 a.txt）→ 暂存，都不调模型')
        # 7. 小检查：输出对正则、文件大小；对照失败认不出用例名时按测试路径记
        r, d = run('expect_text', text='a\nEXIT=0\n', pattern='^EXIT=0$')
        check(r['exit_code'] == 0 and d['match'] == 'EXIT=0', f'expect_text 匹配：{d}')
        r, d = run('expect_text', text='EXIT=1', pattern='^EXIT=0$')
        check(r['exit_code'] == 1 and d['match'] is None, 'expect_text 不匹配：退出码 1')
        r, d = run('file_size', path=str(proj / 'app/orders.py'), max_bytes=10)
        check(r['exit_code'] == 1 and d['bytes'] > 10, f'file_size 超上限：{d}')
        script_fail = '  ✓ 第一条\nTraceback (most recent call last):\n  AssertionError: x\nEXIT=1\n'
        r, d = run('compare_failures', base='LOG=x\n  ✓ 全过\nEXIT=0\n', now=script_fail, name='tests/tools/test_x.py')
        check(r['exit_code'] == 1 and d['new'] == ['tests/tools/test_x.py'],
              f'脚本式测试（只有 Traceback、没有 FAILED 行）挂了：按测试路径记成新挂：{d}')
        r, d = run('compare_failures', base=script_fail, now=script_fail, name='tests/tools/test_x.py')
        check(r['exit_code'] == 0 and d['still'] == ['tests/tools/test_x.py'], '改前改后都挂：原来就挂')

        # 8. 工作树、在工作树里跑测试、在暂存区 / HEAD 的副本里跑测试
        repo3 = tmp / 'repo3'
        (repo3 / 'tests/tools').mkdir(parents=True)
        (repo3 / 'tests/tools/test_ok.py').write_text('import pathlib\nprint("值", pathlib.Path("v.txt").read_text().strip())\n'
                                                     'assert pathlib.Path("v.txt").read_text().strip() == "1"\n', encoding='utf-8')
        (repo3 / 'v.txt').write_text('1\n', encoding='utf-8')
        git(repo3, 'init', '-q', '-b', 'main')
        git(repo3, 'add', '.')
        git(repo3, 'commit', '-q', '-m', 'init')
        wt = tmp / 'wt1'
        r, d = run('wt_add', repo=str(repo3), path=str(wt))
        check(r['exit_code'] == 0 and d['branch'] == 'wf/wt1' and not d['reused'] and (wt / 'v.txt').is_file(),
              f'开工作树：分支 wf/wt1，文件都在：{d}')
        r, d = run('wt_add', repo=str(repo3), path=str(wt))
        check(r['exit_code'] == 0 and d['reused'], '再开一次：接着用')
        r, d = run('wt_add', repo=str(repo3), path=str(proj))
        check(r['exit_code'] == 2 and '不是' in d.get('error', ''), '目录已存在但不是这个仓库的工作树：报错')
        r, _ = run('wt_add', repo=str(repo3), path='/workspace/agent_mcp/tools/x')
        check(r['status'] == 'rejected', '工作树只能开在 workflow_demo/work 或 data/tmp 下')
        r, _ = run('dir_test', dir=str(wt), path='tests/tools/test_ok.py')
        check(r['exit_code'] == 0 and 'EXIT=0' in r['output'] and '值 1' in r['output'], '在工作树里跑测试：过')
        (wt / 'v.txt').write_text('2\n', encoding='utf-8')
        r, _ = run('dir_test', dir=str(wt), path='tests/tools/test_ok.py')
        check(r['exit_code'] != 0 and r['output'].strip().endswith('EXIT=1'), '工作树里改坏了：不过，最后一行 EXIT=1')
        git(wt, 'add', 'v.txt')
        r, _ = run('staged_test', repo=str(wt), path='tests/tools/test_ok.py', **{'from': 'staged'})
        check(r['exit_code'] != 0 and 'EXIT=1' in r['output'], '暂存区的版本：不过')
        r, _ = run('staged_test', repo=str(wt), path='tests/tools/test_ok.py', **{'from': 'head'})
        check(r['exit_code'] == 0 and 'EXIT=0' in r['output'], 'HEAD 的版本：过（当基线用）')
        check(not list((ROOT / 'data/tmp').glob('staged_test_*')), '临时目录跑完都删了')
        r, _ = run('dir_test', dir=str(wt), path='../x.py')
        check(r['status'] == 'rejected', '测试路径只能是 tests/… 下的 .py')
        git(repo3, 'worktree', 'remove', '--force', str(wt))
        print('wf tools passed')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    main()
