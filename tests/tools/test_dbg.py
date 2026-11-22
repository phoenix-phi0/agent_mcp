"""tools/dbg.py 四条调试指令的测试：全部在临时目录里造小项目、埋已知的错来验证。"""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import unittest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from tools import cmd, dbg

DBG = REPO / 'tools/dbg.py'

CALC_GOOD = '''def add(a, b):
    return a + b


def sub(a, b):
    return a - b


def mul(a, b):
    return a * b


def scale(xs, k):
    out = []
    for x in xs:
        if x < 0:
            out.append(x * k)
        else:
            out.append(x * k)
    return out


def half(n):
    return n // 2


def double(n):
    return n * 2


def check_pos(n):
    if n < 0:
        raise ValueError('negative: %d' % n)
    return n
'''
BUG_OLD, BUG_NEW = '        if x < 0:\n            out.append(x * k)\n', '        if x < 0:\n            out.append(x * k + 1)\n'
CALC_BAD = CALC_GOOD.replace(BUG_OLD, BUG_NEW)

UTIL = '''def first(xs):
    return xs[0]


def last(xs):
    return xs[-1]


def middle(xs):
    return xs[len(xs) // 2]


def count(xs):
    return len(xs)


def total(xs):
    return sum(xs)


def biggest(xs):
    return max(xs)
'''

HEADER = '''import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import calc
import util


'''
TEST_CALC = HEADER + '''class T(unittest.TestCase):
    def test_add(self):
        self.assertEqual(calc.add(1, 2), 3)

    def test_scale_pos(self):
        self.assertEqual(calc.scale([1, 3], 2), [2, 6])

    def test_scale_neg(self):
        got = calc.scale([-1, 2], 2)
        self.assertEqual(got, [-2, 4])  # MARK-ASSERT

    def test_check(self):
        self.assertEqual(calc.check_pos(-3), 0)

    def test_check_ok(self):
        self.assertEqual(calc.check_pos(3), 3)

    def test_util(self):
        self.assertEqual(util.total([1, 2]), 3)


if __name__ == '__main__':
    unittest.main()
'''
# 只有 scale 的用例：给 blame_change 用（在好的 calc 上全过）
TEST_SCALE = HEADER + '''class S(unittest.TestCase):
    def test_pos(self):
        self.assertEqual(calc.scale([1, 3], 2), [2, 6])

    def test_neg(self):
        self.assertEqual(calc.scale([-1, 2], 2), [-2, 4])

    def test_util(self):
        self.assertEqual(util.total([1, 2]), 3)


if __name__ == '__main__':
    unittest.main()
'''
TEST_OK = HEADER + '''class Ok(unittest.TestCase):
    def test_one(self):
        self.assertEqual(calc.add(1, 1), 2)

    def test_two(self):
        self.assertEqual(calc.check_pos(1), 1)

    @unittest.skip('demo')
    def test_three(self):
        pass


if __name__ == '__main__':
    unittest.main()
'''
TEST_ALLBAD = HEADER + '''class Bad(unittest.TestCase):
    def test_one(self):
        self.assertEqual(calc.scale([-1], 2), [-2])

    def test_two(self):
        calc.check_pos(-1)
'''
SCRIPT_BAD = '''import sys
print('  ✓ 第一项')
print('  ✗ 第二项：期望 3 实际 4')
print('      细节行 alpha')
print('  ✓ 第三项')
print('\\n通过 2，失败 1')
sys.exit(1)
'''
SCRIPT_OK = "print('  ✓ a')\nprint('  ✓ b')\nprint('通过 2，失败 0')\n"
SCRIPT_CRASH = '''import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import calc
print('  ✓ 开始')
calc.check_pos(-7)
'''
TEST_MARK = '''import unittest
from pathlib import Path
Path(__file__).resolve().parents[1].joinpath('ran.flag').write_text('x')


class M(unittest.TestCase):
    def test_m(self):
        value = [1, 2, 3]
        self.assertEqual(len(value), 3)  # MARK-M
'''
TEST_SLOW = '''import time
import unittest


class Slow(unittest.TestCase):
    def test_a_quick_fail(self):
        self.assertEqual(1, 2)

    def test_b_ok(self):
        pass

    def test_c_sleep(self):
        time.sleep(60)
'''


def line_of(text, needle):
    return next(i for i, x in enumerate(text.split('\n'), 1) if needle in x)


class Project(unittest.TestCase):
    """临时小项目：calc.py（埋了错）、util.py、几个测试文件；.venv 和 tools/dbg.py 用软链接指回真文件。"""
    calc = CALC_BAD

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve() / 'proj'
        for d in ('tests', '.venv/bin', 'tools'):
            (self.root / d).mkdir(parents=True)
        (self.root / '.venv/bin/python').symlink_to(sys.executable)
        (self.root / 'tools/dbg.py').symlink_to(DBG)
        self.write('calc.py', self.calc)
        self.write('util.py', UTIL)
        for name, text in [('test_calc', TEST_CALC), ('test_scale', TEST_SCALE), ('test_ok', TEST_OK),
                           ('test_allbad', TEST_ALLBAD), ('script_bad', SCRIPT_BAD), ('script_ok', SCRIPT_OK),
                           ('script_crash', SCRIPT_CRASH), ('test_mark', TEST_MARK), ('test_slow', TEST_SLOW)]:
            self.write('tests/%s.py' % name, text)

    def write(self, rel, text):
        (self.root / rel).write_text(text, encoding='utf-8')

    def dbg(self, *args, code=0):
        p = subprocess.run([sys.executable, '-B', str(DBG), *map(str, args)], cwd=self.root, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, text=True, encoding='utf-8')
        self.assertEqual(p.returncode, code, p.stdout)
        self.assertLessEqual(len(p.stdout), 8000)
        return p.stdout

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.root, text=True, stderr=subprocess.STDOUT)

    def git_init(self):
        self.git('init', '-q')
        self.git('config', 'user.email', 'test@example.org')
        self.git('config', 'user.name', 'Test')
        (self.root / '.gitignore').write_text('.venv\ntools\n__pycache__\n*.flag\n')
        self.git('add', '.gitignore', 'calc.py', 'util.py', 'tests')
        self.git('commit', '-qm', 'base')


class ReportTests(Project):
    def test_failures(self):
        out = self.dbg('test_report', 'tests/test_calc.py')
        self.assertIn('跑了 6/6 个用例：通过 4，失败 1，出错 1，跳过 0', out)
        neg = out[out.index('T.test_scale_neg'):]
        self.assertIn('失败 T.test_scale_neg', out)
        self.assertIn('AssertionError: Lists differ: [-1, 4] != [-2, 4]', neg)
        line = line_of(TEST_CALC, 'MARK-ASSERT')
        self.assertIn('最内层仓库内帧 tests/test_calc.py:%d (test_scale_neg)' % line, neg)
        self.assertRegex(neg, r'>\s+%d  \s*self\.assertEqual\(got' % line)
        self.assertRegex(neg, r'\n\s+%d  \s*got = calc\.scale' % (line - 1))
        # 异常从被测代码里抛出：最内层帧在 calc.py，而不是测试文件
        chk = out[out.index('出错 T.test_check'):]
        raise_line = line_of(CALC_BAD, 'raise ValueError')
        self.assertIn('ValueError: negative: -3', chk)
        self.assertIn('最内层仓库内帧 calc.py:%d (check_pos)' % raise_line, chk)
        self.assertIn('调用链 tests/test_calc.py:%d → calc.py:%d' % (line_of(TEST_CALC, 'check_pos(-3)'), raise_line), chk)
        chk = chk.split('\n[')[0]      # 只看这一个失败块
        context = re.findall(r'^    [> ] +(\d+)  ', chk, re.M)
        self.assertEqual(context, [str(n) for n in range(raise_line - 2, raise_line + 2)], '前后各 2 行，文件到 34 行为止')
        self.assertRegex(chk, r'    > +%d  \s*raise ValueError' % raise_line)
        self.assertNotIn('unittest/case.py', out)
        self.assertEqual(out, self.dbg('test_report', 'tests/test_calc.py'), '同样的输入输出要一样')

    def test_limit_and_case(self):
        out = self.dbg('test_report', 'tests/test_calc.py', '--limit', 1)
        self.assertIn('[1] ', out)
        self.assertNotIn('[2] ', out)
        self.assertIn('其余 1 个失败未展开：T.test_scale_neg', out)
        out = self.dbg('test_report', 'tests/test_calc.py', '--case', 'T.test_add')
        self.assertEqual(out.strip(), 'test_report tests/test_calc.py：全部通过（unittest，1 个用例）')
        out = self.dbg('test_report', 'tests/test_calc.py', '--case', 'T.test_missing', code=2)
        self.assertIn('测试跑不起来', out)
        self.assertIn('找不到用例 T.test_missing', out)

    def test_all_pass_is_one_line(self):
        out = self.dbg('test_report', 'tests/test_ok.py')
        self.assertEqual(out, 'test_report tests/test_ok.py：全部通过（unittest，3 个用例，其中跳过 1）\n')

    def test_script_style(self):
        out = self.dbg('test_report', 'tests/script_bad.py')
        self.assertIn('脚本式测试（没有独立用例），通过 2，失败 1，退出码 1', out)
        self.assertIn('✗ 第二项：期望 3 实际 4', out)
        self.assertIn('细节行 alpha', out)
        self.assertNotIn('第三项', out)
        self.assertEqual(self.dbg('test_report', 'tests/script_ok.py'),
                         'test_report tests/script_ok.py：全部通过（脚本式，通过 2，失败 0）\n')
        # ✗ 行全部列出：前 limit 处带详情行，其余只列该行
        self.write('tests/script_many.py', "for i in range(9):\n    print('  ✗ 项%d' % i)\n    print('    详情%d' % i)\nprint('通过 0，失败 9')\nraise SystemExit(1)\n")
        out = self.dbg('test_report', 'tests/script_many.py', '--limit', 2)
        self.assertIn('✗ 行共 9 处', out)
        self.assertEqual([('项%d' % i in out, '详情%d' % i in out) for i in range(9)], [(True, True)] * 2 + [(True, False)] * 7)
        out = self.dbg('test_report', 'tests/script_crash.py')
        self.assertIn('按 ✓/✗ 行计数', out)
        self.assertIn('脚本以异常结束：ValueError: negative: -7', out)
        self.assertIn('最内层仓库内帧 calc.py:%d (check_pos)' % line_of(CALC_BAD, 'raise ValueError'), out)

    def test_cannot_run(self):
        self.write('tests/test_broken.py', 'import unittest\nimport no_such_module_xyz\n\nclass B(unittest.TestCase):\n    def test_x(self): pass\n')
        out = self.dbg('test_report', 'tests/test_broken.py', code=2)
        self.assertIn('测试跑不起来', out)
        self.assertIn("ModuleNotFoundError: No module named 'no_such_module_xyz'", out)
        self.assertIn('tests/test_broken.py:2', out)
        self.assertIn('测试跑不起来', self.dbg('test_report', 'tests/nope.py', code=2))
        # 被测模块语法错：指到语法错的那一行
        self.write('calc.py', CALC_BAD + 'def broken(:\n')
        out = self.dbg('test_report', 'tests/test_calc.py', code=2)
        self.assertIn('SyntaxError', out)
        self.assertIn('calc.py:%d' % (CALC_BAD.count('\n') + 1), out)

    def test_partial_result_near_deadline(self):
        started = time.monotonic()
        out = self.dbg('test_report', 'tests/test_slow.py', '--budget', 6)
        self.assertLess(time.monotonic() - started, 30)
        self.assertIn('跑了 2/3 个用例：通过 1，失败 1', out)
        self.assertIn('只跑完 2/3 个用例：到时限被中止', out)
        self.assertIn('失败 Slow.test_a_quick_fail', out)


class LocateTests(Project):
    def test_ranks_bug_line(self):
        out = self.dbg('locate', 'tests/test_calc.py')
        self.assertIn('Ochiai', out)
        self.assertIn('用例 6（失败 2，通过 4）', out)
        self.assertIn('T.test_scale_neg (AssertionError)', out)
        rows = [x for x in out.splitlines() if re.match(r'\s*\d+\. ', x)]
        bug = line_of(CALC_BAD, 'x * k + 1')
        top3 = ' '.join(rows[:3])
        self.assertIn('calc.py:%d ' % bug, top3)
        row = next(x for x in rows if 'calc.py:%d ' % bug in x)
        self.assertIn('0.707  失败 1/2  通过 0/4  | out.append(x * k + 1)', row)
        self.assertTrue(all('tests/' not in x for x in rows), rows)
        scores = [float(re.search(r'  (\d\.\d{3})  失败', x).group(1)) for x in rows]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual(out, self.dbg('locate', 'tests/test_calc.py'))
        self.assertEqual(len([x for x in self.dbg('locate', 'tests/test_calc.py', '--limit', 2).splitlines()
                              if re.match(r'\s*\d+\. ', x)]), 2)

    def test_single_failure_ranks_first(self):
        out = self.dbg('locate', 'tests/test_scale.py', '--paths', 'calc.py')
        first = next(x for x in out.splitlines() if x.startswith(' 1. '))
        self.assertIn('calc.py:%d  1.000  失败 1/1  通过 0/2' % line_of(CALC_BAD, 'x * k + 1'), first)
        self.assertIn('范围：calc.py', out)
        self.assertIn(first, self.dbg('locate', 'tests/test_scale.py', '--paths', '.'))
        out = self.dbg('locate', 'tests/test_scale.py', '--paths', 'util.py')
        self.assertNotIn('calc.py:', out)

    def test_no_ranking_without_contrast(self):
        out = self.dbg('locate', 'tests/test_ok.py')
        self.assertIn('排不出可疑行', out)
        self.assertIn('没有失败的', out)
        self.assertNotRegex(out, r'\d\.\d{3}')
        out = self.dbg('locate', 'tests/test_allbad.py')
        self.assertIn('排不出可疑行', out)
        self.assertIn('没有通过用例做对比', out)
        self.assertNotRegex(out, r'\d\.\d{3}')
        out = self.dbg('locate', 'tests/script_bad.py')
        self.assertIn('不支持', out)
        self.assertIn('脚本式', out)


class ProbeTests(Project):
    def test_values_at_bug(self):
        bug = line_of(CALC_BAD, 'x * k + 1')
        out = self.dbg('probe', 'tests/test_calc.py', '--at', 'calc.py:%d' % bug, '--exprs', 'x', 'k', 'len(out)', 'xs[0]', 'xs[-1]', 'nope', 'type(k)')
        self.assertIn('== calc.py:%d | out.append(x * k + 1)   命中 1 次' % bug, out)
        self.assertIn("#1 T.test_scale_neg [失败]  x=-1 ; k=2 ; len(out)=0 ; xs[0]=-1 ; xs[-1]=2 ; nope=!NameError ; type(k)=<class 'int'>", out)
        self.assertIn('只有失败用例命中这里', out)
        self.assertEqual(out, self.dbg('probe', 'tests/test_calc.py', '--at', 'calc.py:%d' % bug, '--exprs', 'x', 'k', 'len(out)', 'xs[0]', 'xs[-1]', 'nope', 'type(k)'))

    def test_pass_fail_difference(self):
        branch = line_of(CALC_BAD, 'if x < 0:')
        out = self.dbg('probe', 'tests/test_calc.py', '--at', 'calc.py:%d' % branch, 'calc.py:%d' % line_of(CALC_BAD, 'return a + b'),
                       '--exprs', 'x', 'k')
        self.assertIn('命中 4 次，记录 4 次，显示 4 次', out)
        self.assertIn('通过 / 失败两组取值不同的表达式（失败组 2 次命中，通过组 2 次）', out)
        self.assertIn('x：仅失败组 [-1, 2]；仅通过组 [1, 3]', out)
        self.assertNotIn('   k：', out)
        self.assertIn('T.test_scale_pos [通过]  x=1 ; k=2', out)
        self.assertIn('T.test_scale_neg [失败]  x=-1 ; k=2', out)
        self.assertIn('T.test_add [通过]  x=!NameError ; k=!NameError', out)
        # case 只跑一个用例；limit 限制记录次数
        out = self.dbg('probe', 'tests/test_calc.py', '--case', 'T.test_scale_pos', '--limit', 1, '--at', 'calc.py:%d' % branch, '--exprs', 'x')
        self.assertIn('命中 2 次，记录 1 次，显示 1 次', out)
        self.assertNotIn('x=3', out)

    def test_not_hit(self):
        out = self.dbg('probe', 'tests/test_ok.py', '--at', 'calc.py:%d' % line_of(CALC_BAD, 'x * k + 1'), 'calc.py:3', '--exprs', 'x')
        self.assertIn('未命中：测试没有执行到这一行', out)
        self.assertIn('未命中：这一行不是可执行语句的起始行', out)

    def test_whitelist_rejects_before_running(self):
        flag = self.root / 'ran.flag'
        at = 'tests/test_mark.py:%d' % line_of(TEST_MARK, 'MARK-M')
        bad = ['print(1)', 'value.append(9)', 'value.__class__', '__import__', "__import__('os').system('true')",
               '(lambda: 1)()', '[v for v in value]', 'value + [1]', 'value[0:1]', 'value[len(value)]', 'len(value, 1)',
               'len(*value)', 'type(value, (), {})', 'open', 'a if b else c', 'value[0].__dict__', 'x := 1', 'f"{value}"',
               'not value', 'value == 1', '1; 2', '']
        for expr in bad:
            with self.subTest(expr=expr):
                if expr not in ('open',):
                    self.assertRaises(ValueError, dbg.check_expr, expr)
        for expr in bad:
            if expr in ('open', ''):
                continue    # 'open' 只是个名字（取到的是 repr，不会被调用）；空串在命令行层就没了
            with self.subTest(run=expr):
                out = self.dbg('probe', 'tests/test_mark.py', '--at', at, '--exprs', 'value', expr, code=2)
                self.assertIn('拒绝执行', out)
                self.assertIn('测试没有运行', out)
                self.assertFalse(flag.exists(), expr)
        for expr in ['value', 'self.id', 'value[0]', 'value[-1]', 'd["k"]', 'a[i]', 'len(value)', 'type(value)', 'None', '3.5', 'a.b.c[0].d']:
            dbg.check_expr(expr)
        out = self.dbg('probe', 'tests/test_mark.py', '--at', at, '--exprs', 'value', 'len(value)', 'value[-1]')
        self.assertIn('M.test_m [通过]  value=[1, 2, 3] ; len(value)=3 ; value[-1]=3', out)
        self.assertTrue(flag.exists())
        for wrong in ('calc.py', 'calc.py:9999', 'nofile.py:3', '../x.py:1'):
            self.assertIn('参数不对', self.dbg('probe', 'tests/test_mark.py', '--at', wrong, '--exprs', 'value', code=2))


class BlameTests(Project):
    calc = CALC_GOOD

    def change(self):
        """6 块互不相关的改动，其中只有 calc.py 中间那块引入错误。"""
        self.write('calc.py', ('import extra_mod  # TOPMARK\n' + CALC_BAD).replace("'negative: %d'", "'negative number: %d'"))
        self.write('util.py', '# 顶部注释 UTILMARK\n' + UTIL + '\n\ndef smallest(xs):\n    return min(xs)  # TAILMARK\n')
        self.write('extra_mod.py', 'VALUE = 1  # EXTRAMARK\n')

    def test_parse_and_apply(self):
        self.git_init()
        self.change()
        self.write('util.py', (self.root / 'util.py').read_text().rstrip('\n'))     # 末尾没有换行
        files = dbg.parse_diff(self.git('diff', 'HEAD'))
        self.assertEqual([(f['file'], len(f['hunks'])) for f in files], [('calc.py', 3), ('util.py', 2)])
        for f in files:
            base = self.git('show', 'HEAD:' + f['file'])
            self.assertEqual(dbg.apply_hunks(base, f['hunks']), (self.root / f['file']).read_text())
            self.assertEqual(dbg.apply_hunks(base, []), base)
        only_bug = dbg.apply_hunks(CALC_GOOD, [files[0]['hunks'][1]])
        self.assertEqual(only_bug, CALC_BAD)

    def test_ddmin(self):
        calls = []

        def test(subset):
            calls.append(tuple(subset))
            if 5 in subset and 6 not in subset:
                return 'unres'
            return 'fail' if {3, 7} <= set(subset) else 'pass'
        self.assertEqual(list(dbg.ddmin(list(range(10)), test))[-1], [3, 7])
        self.assertEqual(list(dbg.ddmin([1], test))[-1], [1])
        self.assertEqual(list(dbg.ddmin(list(range(8)), lambda s: 'fail' if 2 in s else 'pass'))[-1], [2])

    def test_isolates_the_bad_hunk(self):
        self.git_init()
        self.change()
        before = self.git('status', '--porcelain')
        out = self.dbg('blame_change', 'tests/test_scale.py', '--paths', 'extra_mod.py')
        self.assertIn('最小改动集合 1 块（共 6 块改动），只套用它就能复现失败', out)
        self.assertIn('失败特征：S.test_neg (AssertionError)', out)
        bug = line_of(CALC_GOOD, 'out.append(x * k)')
        self.assertRegex(out, r'\[1\] calc\.py HEAD 行 (\d+)-(\d+) → 工作区 行 (\d+)-(\d+)')
        lo, hi = map(int, re.search(r'\[1\] calc\.py HEAD 行 (\d+)-(\d+)', out).groups())
        self.assertTrue(lo <= bug <= hi)
        self.assertIn('-            out.append(x * k)', out)
        self.assertIn('+            out.append(x * k + 1)', out)
        for other in ('TOPMARK', 'UTILMARK', 'TAILMARK', 'EXTRAMARK', 'negative number', 'extra_mod', '[2]'):
            self.assertNotIn(other, out)
        m = re.search(r'跑了 (\d+) 次测试（缩小过程中：通过 (\d+)，复现失败 (\d+)，未判定 (\d+)）', out)
        runs, passed, failed, unres = map(int, m.groups())
        self.assertEqual(runs, 2 + passed + failed + unres)
        self.assertLessEqual(runs, 40)
        self.assertGreater(unres, 0, '「import extra_mod」那块单独套用会导入失败，应记为未判定')
        self.assertEqual(self.git('status', '--porcelain'), before)
        self.assertEqual(out, self.dbg('blame_change', 'tests/test_scale.py', '--paths', 'extra_mod.py'))
        # 只跑一个用例也一样
        self.assertIn('最小改动集合 1 块', self.dbg('blame_change', 'tests/test_scale.py', '--case', 'S.test_neg', '--paths', 'extra_mod.py'))

    def test_two_hunks_needed(self):
        self.git_init()
        # 两处改动合起来才出错：double(sub(5, 1)) 原本是 8；只改 sub 得 2，只改 double 得 64，两处都改才得 16
        self.write('tests/test_pair.py', HEADER + 'class P(unittest.TestCase):\n    def test_p(self):\n'
                   '        self.assertNotEqual(calc.double(calc.sub(5, 1)), 16)\n')
        self.git('add', 'tests/test_pair.py')
        self.git('commit', '-qm', 'pair')
        self.write('calc.py', CALC_GOOD.replace('return a - b', 'return a - b - 3').replace('return n * 2', 'return n * 16'))
        self.write('util.py', '# UTILMARK\n' + UTIL + '\n\ndef smallest(xs):\n    return min(xs)  # TAILMARK\n')
        self.assertEqual([len(f['hunks']) for f in dbg.parse_diff(self.git('diff', 'HEAD'))], [2, 2])
        out = self.dbg('blame_change', 'tests/test_pair.py')
        self.assertIn('最小改动集合 2 块（共 4 块改动），去掉其中任何一块都不再复现', out)
        self.assertIn('+    return a - b - 3', out)
        self.assertIn('+    return n * 16', out)
        self.assertNotIn('UTILMARK', out)
        self.assertNotIn('TAILMARK', out)

    def test_untracked_file_as_chunk(self):
        self.git_init()
        self.write('tests/test_plug.py', HEADER + 'import importlib.util\n\n\nclass G(unittest.TestCase):\n    def test_g(self):\n'
                   '        self.assertIsNone(importlib.util.find_spec("plugin_new"))\n')
        self.git('add', 'tests/test_plug.py')
        self.git('commit', '-qm', 'plug')
        self.write('plugin_new.py', 'NAME = "plugin"  # PLUGMARK\n')
        self.write('calc.py', '# TOPMARK\n' + CALC_GOOD)
        self.write('util.py', UTIL + '\n\ndef smallest(xs):\n    return min(xs)  # TAILMARK\n')
        out = self.dbg('blame_change', 'tests/test_plug.py', '--paths', 'plugin_new.py')
        self.assertIn('最小改动集合 1 块（共 3 块改动）', out)
        self.assertIn('[1] plugin_new.py（未入库文件，整个算一块）', out)
        self.assertIn('PLUGMARK', out)
        self.assertNotIn('TOPMARK', out)
        # 没带上这个未入库文件：副本里复现不了，要说清楚
        out = self.dbg('blame_change', 'tests/test_plug.py')
        self.assertIn('没有复现工作区的失败', out)
        self.assertIn('paths', out)

    def test_untracked_test_file_is_baseline(self):
        self.git_init()
        self.change()
        self.write('tests/test_fresh.py', TEST_SCALE)
        out = self.dbg('blame_change', 'tests/test_fresh.py', '--paths', 'extra_mod.py')
        self.assertIn('最小改动集合 1 块（共 6 块改动）', out)
        self.assertIn('测试文件 tests/test_fresh.py 未入库，已作为基线带入副本', out)
        self.assertIn('+            out.append(x * k + 1)', out)

    def test_preconditions(self):
        self.assertIn('不是 Git 仓库', self.dbg('blame_change', 'tests/test_scale.py', code=2))
        self.git_init()
        out = self.dbg('blame_change', 'tests/test_scale.py')
        self.assertIn('前提不成立——测试在工作区是通过的', out)
        self.write('util.py', UTIL + '# 无关改动\n')
        self.assertIn('前提不成立——测试在工作区是通过的', self.dbg('blame_change', 'tests/test_scale.py'))
        # HEAD 上本来就失败
        self.write('calc.py', CALC_BAD)
        self.git('commit', '-qam', 'bug committed')
        out = self.dbg('blame_change', 'tests/test_scale.py')
        self.assertIn('前提不成立——工作区相对 HEAD 没有未提交改动', out)
        self.write('util.py', UTIL + '# 又一处无关改动\n')
        out = self.dbg('blame_change', 'tests/test_scale.py')
        self.assertIn('前提不成立——测试在已提交版本（HEAD）上不通过：S.test_neg (AssertionError)', out)
        self.assertNotIn('最小改动集合', out)

    def test_run_limit_reports_not_converged(self):
        self.git_init()
        self.change()
        out = self.dbg('blame_change', 'tests/test_scale.py', '--paths', 'extra_mod.py', '--runs', 5)
        self.assertIn('未收敛——到运行次数上限 5 次就停了', out)
        self.assertIn('跑了 5 次测试', out)
        self.assertNotIn('最小改动集合', out)
        self.assertRegex(out, r'目前缩小到 \d 块（共 6 块改动）')
        self.assertIn('+            out.append(x * k + 1)', out, '还没排除的块里应包含真正的那块')
        # 时限太短同样报未收敛而不是什么都不给
        out = self.dbg('blame_change', 'tests/test_scale.py', '--paths', 'extra_mod.py', '--budget', 2)
        self.assertTrue('未收敛——快到时限就停了' in out or '最小改动集合' in out, out)


class CmdTests(Project):
    """经执行器、以 small_model 身份调用：用临时 CMD_TABLE / CMD_HOME，指令表的 steps 原样不动。"""
    def setUp(self):
        super().setUp()
        self.old = {k: os.environ.get(k) for k in ('CMD_TABLE', 'CMD_HOME')}
        self.addCleanup(self.restore)
        table = json.loads(cmd.TABLE.read_text(encoding='utf-8'))
        for c in table['commands']:
            c['cwd'] = str(self.root)
        (self.root / 'table.json').write_text(json.dumps(table), encoding='utf-8')
        os.environ.update(CMD_TABLE=str(self.root / 'table.json'), CMD_HOME=str(self.root / 'state'))

    def restore(self):
        for k, v in self.old.items():
            if v is None: os.environ.pop(k, None)
            else: os.environ[k] = v

    def run_small(self, name, args):
        return cmd.run_as('small_model', name, args)

    def test_four_commands_as_small_model(self):
        names = {c['name'] for c in cmd.list_as('small_model')}
        self.assertTrue({'test_report', 'locate', 'probe', 'blame_change'} <= names)
        self.assertEqual(cmd.run_as('nobody', 'test_report', {'path': 'tests/test_calc.py'})['status'], 'rejected')
        bug = line_of(CALC_BAD, 'x * k + 1')

        r = self.run_small('test_report', {'path': 'tests/test_calc.py'})
        self.assertEqual((r['status'], r['exit_code']), ('ok', 0), r)
        self.assertIn('失败 T.test_scale_neg', r['output'])
        self.assertNotIn('truncated', r)
        r = self.run_small('test_report', {'path': 'tests/test_calc.py', 'case': 'T.test_add', 'limit': 3})
        self.assertIn('全部通过', r['output'])
        r = self.run_small('test_report', {'path': 'tests/script_bad.py'})
        self.assertEqual(r['status'], 'ok', r)
        self.assertIn('通过 2，失败 1', r['output'])

        r = self.run_small('locate', {'path': 'tests/test_scale.py', 'paths': ['calc.py'], 'limit': 3})
        self.assertEqual(r['status'], 'ok', r)
        self.assertIn(' 1. calc.py:%d  1.000' % bug, r['output'])
        self.assertIn('Ochiai', self.run_small('locate', {'path': 'tests/test_calc.py'})['output'])

        r = self.run_small('probe', {'path': 'tests/test_calc.py', 'case': 'T.test_scale_neg', 'at': ['calc.py:%d' % bug],
                                     'exprs': ['x', 'xs[-1]', "len(out)"], 'limit': 5})
        self.assertEqual(r['status'], 'ok', r)
        self.assertIn('T.test_scale_neg [失败]  x=-1 ; xs[-1]=2 ; len(out)=0', r['output'])

    def test_flexible_probe_paths_and_cases(self):
        bug = line_of(CALC_BAD, 'x * k + 1')
        base = {'path': 'tests/test_calc.py', 'exprs': 'x', 'case': 'test_scale_neg'}
        for at in ('calc.py:%d' % bug, str(self.root / 'calc.py') + ':' + str(bug)):
            result = self.run_small('probe', dict(base, at=at))
            self.assertEqual(result['status'], 'ok', result)
            self.assertIn('T.test_scale_neg', result['output'])
        self.write('tests/local.py', 'def get():\n    return 42\n')
        self.write('tests/test_local.py', 'import unittest\nimport local\nclass A(unittest.TestCase):\n def test_one(self): self.assertEqual(local.get(), 42)\n')
        result = self.run_small('probe', {'path': 'tests/test_local.py', 'at': 'local.py:2', 'exprs': '42', 'case': 'test_one'})
        self.assertEqual(result['status'], 'ok', result)
        self.assertIn('A.test_one', result['output'])
        missing = self.run_small('probe', dict(base, at='missing.py:1'))
        self.assertEqual(missing['status'], 'rejected')
        self.assertIn('试过', missing['reason'])
        self.assertEqual(self.run_small('probe', dict(base, at='/etc/passwd:1'))['status'], 'rejected')
        self.write('tests/test_local.py', 'import unittest\nimport local\nclass A(unittest.TestCase):\n def test_one(self): local.get()\nclass B(unittest.TestCase):\n def test_one(self): local.get()\n')
        result = self.run_small('probe', {'path': 'tests/test_local.py', 'at': 'local.py:2', 'exprs': '42', 'case': 'test_one'})
        self.assertEqual(result['status'], 'rejected')
        self.assertIn('A.test_one', result['reason'])
        self.assertIn('B.test_one', result['reason'])

    def test_locate_default_local_fixture(self):
        self.write('tests/local.py', 'def get(x):\n    return x + 1\n')
        self.write('tests/test_local.py', 'import unittest\nimport local\nclass A(unittest.TestCase):\n def test_pass(self): self.assertEqual(local.get(1), 2)\n def test_fail(self): self.assertEqual(local.get(2), 2)\n')
        result = self.run_small('locate', {'path': 'tests/test_local.py'})
        self.assertEqual(result['status'], 'ok', result)
        self.assertIn('tests/local.py:2', result['output'])

    def test_blame_sync_and_job(self):
        self.write('calc.py', CALC_GOOD)
        self.git_init()
        self.write('calc.py', ('# TOPMARK\n' + CALC_BAD).replace("'negative: %d'", "'negative number: %d'"))
        self.write('util.py', UTIL + '\n\ndef smallest(xs):\n    return min(xs)\n')
        self.write('extra_mod.py', 'VALUE = 1\n')
        r = self.run_small('blame_change', {'path': 'tests/test_scale.py', 'paths': ['extra_mod.py']})
        self.assertEqual(r['status'], 'ok', r)
        self.assertIn('最小改动集合 1 块（共 5 块改动）', r['output'])
        self.assertIn('+            out.append(x * k + 1)', r['output'])
        r = self.run_small('blame_change', {'path': 'tests/test_scale.py', 'runs': 4})
        self.assertIn('未收敛', r['output'])
        started = self.run_small('job', {'action': 'start', 'command': 'blame_change', 'args': {'path': 'tests/test_scale.py', 'case': 'S.test_neg'}})
        self.assertEqual(started['status'], 'running', started)
        for _ in range(600):
            r = self.run_small('job', {'action': 'result', 'job': started['job']})
            if r['status'] != 'running': break
            time.sleep(.1)
        self.assertEqual(r['status'], 'ok', r)
        self.assertIn('最小改动集合 1 块（共 4 块改动）', r['output'])

    def test_invalid_arguments_rejected(self):
        flag = self.root / 'ran.flag'
        at = 'tests/test_mark.py:%d' % line_of(TEST_MARK, 'MARK-M')
        good = {'path': 'tests/test_mark.py', 'at': [at], 'exprs': ['value']}
        rejected = [
            ('test_report', {}), ('test_report', {'path': 'calc.py'}), ('test_report', {'path': '../x/tests/a.py'}),
            ('test_report', {'path': 'tests/test_mark.py', 'case': 'M; touch pwned'}),
            ('test_report', {'path': 'tests/test_mark.py', 'limit': 0}),
            ('test_report', {'path': 'tests/test_mark.py', 'out': ['count']}),
            ('test_report', {'path': 'tests/test_mark.py', 'tail': 3}),
            ('locate', {'path': 'tests/test_mark.py', 'paths': ['../outside.py']}),
            ('locate', {'path': 'tests/test_mark.py', 'limit': 51}),
            ('probe', {'path': 'tests/test_mark.py'}),
            ('probe', dict(good, at=[])), ('probe', dict(good, exprs=[])),
            ('probe', dict(good, at=['tests/test_mark.py'])), ('probe', dict(good, at=[at + '; touch pwned'])),
            ('probe', dict(good, at=['$(touch pwned):3'])), ('probe', dict(good, exprs=['x'] * 9)),
            ('probe', dict(good, exprs=['x' * 201])), ('probe', dict(good, exprs=[3])),
            ('blame_change', {'path': 'tests/test_mark.py', 'runs': 3}),
            ('blame_change', {'path': 'tests/test_mark.py', 'paths': ['/etc/passwd']}),
        ]
        for name, args in rejected:
            with self.subTest(name=name, args=args):
                r = self.run_small(name, args)
                self.assertEqual(r['status'], 'rejected', r)
                self.assertTrue(r['reason'])
        self.assertFalse(flag.exists(), '被拒的调用不应运行测试')
        # 白名单外的表达式能通过执行器的格式检查，但 dbg.py 在运行测试之前拒绝；带 shell 元字符的也只是一段文字
        for expr in ('value.append(1)', 'value.__class__', '$(touch pwned)', '`touch pwned`; x', "x'; touch pwned; '"):
            with self.subTest(expr=expr):
                r = self.run_small('probe', dict(good, exprs=[expr]))
                self.assertEqual((r['status'], r['exit_code']), ('failed', 2), r)
                self.assertIn('拒绝执行', r['output'])
        self.assertFalse(flag.exists())
        self.assertFalse((self.root / 'pwned').exists())
        # 字符串常量是合法表达式，里面的 shell 写法只是文字；以 - 开头的表达式也能传进去
        r = self.run_small('probe', dict(good, exprs=['value', '-1', "'; touch pwned; '"]))
        self.assertEqual(r['status'], 'ok', r)
        self.assertIn("value=[1, 2, 3] ; -1=-1 ; '; touch pwned; '='; touch pwned; '", r['output'])
        self.assertTrue(flag.exists())
        self.assertFalse((self.root / 'pwned').exists())

    def test_cannot_run_is_failed_with_reason(self):
        self.write('tests/test_broken.py', 'import unittest\nimport no_such_module_xyz\n\nclass B(unittest.TestCase):\n    def test_x(self): pass\n')
        for name, args in [('test_report', {}), ('locate', {}), ('probe', {'at': ['calc.py:2'], 'exprs': ['a']})]:
            with self.subTest(name=name):
                r = self.run_small(name, dict(args, path='tests/test_broken.py'))
                self.assertEqual((r['status'], r['exit_code']), ('failed', 2), r)
                self.assertIn('测试跑不起来', r['output'])
                self.assertIn('no_such_module_xyz', r['output'])

    def test_real_table_entries(self):
        table = json.loads(cmd.TABLE.read_text(encoding='utf-8'))
        for name in ('test_report', 'locate', 'probe', 'blame_change'):
            with self.subTest(name=name):
                c = next(x for x in table['commands'] if x['name'] == name)
                self.assertEqual((c['level'], c['mode'], c['cwd']), ('write', 'sync', '/workspace/agent_mcp'))
                self.assertLessEqual(c['timeout'], 170)
                self.assertIn(name, table['callers']['small_model']['allow'])
                self.assertEqual(len(c['steps']), 1)
                self.assertTrue(c['steps'][0].startswith('.venv/bin/python -B tools/dbg.py %s {path} ' % name))
                self.assertNotIn('\n', c['doc'])
                self.assertLessEqual(len(c['doc']), 40)
                self.assertEqual(sum(x.startswith(name + '(') for x in cmd.describe_as('small_model').splitlines()), 1)
        self.assertIn('max_items=', cmd.describe_as('small_model', 'probe'))


if __name__ == '__main__':
    unittest.main()
