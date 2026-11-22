"""Offline and real integration checks for the HTN diagnostic wrapper (tools/htn_diag.py over htnbot/planbot/diag)."""
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools import htn_diag

FIXTURE = json.loads((ROOT / 'htnbot/tests/fixtures/diag_real.json').read_text(encoding='utf-8'))
CASES = {c['test']: c for c in FIXTURE['cases']}


def recorded(test):
    """按夹具录像回放指令机器人的输出；没录过的指令返回「未录制」。"""
    calls = CASES[test]['calls']
    seen = []

    def fake(caller, name, args):
        seen.append((caller, name))
        if name in calls:
            r = calls[name]
            return {'status': r['status'], 'exit_code': r['exit_code'], 'output': r['output']}
        return {'status': 'error', 'exit_code': 1, 'output': '未录制'}
    return fake, seen


class OfflineTests(unittest.TestCase):
    def setUp(self):
        # 缓存写进临时目录，别让回放出来的结果留在真缓存里被 --detail 读到
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patcher = patch.object(htn_diag, 'CACHE', Path(tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_brief_and_detail_param(self):
        test = 'tests/htn_bench/test_cmd_k2.py'
        fake, seen = recorded(test)
        with patch.object(htn_diag.cmd, 'run_as', fake):
            short = htn_diag.diagnose(test, execute=True, brief=True)
            first = len(seen)
            more = htn_diag.diagnose(test, detail=True)
        self.assertEqual(set(short), {'mode', 'status', 'summary', 'candidates', 'calls'})
        self.assertEqual(short['status'], 'found')
        self.assertIn({'file': 'data/tmp/hb/k2/tools/cmd.py', 'line': 196}, short['candidates'])
        self.assertTrue(all(isinstance(name, str) for name in short['calls']))
        self.assertLess(len(json.dumps(short, ensure_ascii=False)), 4000)
        self.assertEqual(len(seen), first)  # detail=True 读缓存，没有再调指令
        self.assertEqual(more['status'], 'found')
        self.assertIn('== test_report 原文', more['detail'])

    def run_case(self, test):
        fake, seen = recorded(test)
        with patch.object(htn_diag.cmd, 'run_as', fake):
            result = htn_diag.diagnose(test, execute=True)
        self.assertTrue(all(caller == 'small_model' for caller, _ in seen))
        self.assertTrue(all(type(c['exit_code']) is int for c in result['calls']))
        return result

    def test_pass(self):
        result = self.run_case('tests/htn_demo/test_demo_pass.py')
        self.assertEqual(result['finding']['status'], 'passed')
        self.assertEqual([c['name'] for c in result['calls']], ['run_test'])
        self.assertIn('测试通过', result['summary'])
        self.assertNotIn('--detail', result['summary'])

    def test_found_and_summary(self):
        result = self.run_case('tests/htn_demo/test_demo_fail.py')
        self.assertEqual(result['finding']['status'], 'found')
        top = [(c['file'], c['line']) for c in result['finding']['candidates'][:3]]
        self.assertIn(('data/tmp/htn_demo/buggy.py', 7), top)
        text = result['summary']
        self.assertIn('data/tmp/htn_demo/buggy.py:7', text)
        self.assertIn('失败用例', text)
        self.assertIn('--detail', text)
        self.assertLess(len(text), 2500)

    def test_fast_skips_run_test(self):
        # 用 test_report 代替 run_test 判红绿，整个排查只跑一遍 test_report，不再单独跑 run_test
        fake, seen = recorded('tests/htn_demo/test_demo_fail.py')
        with patch.object(htn_diag.cmd, 'run_as', fake):
            result = htn_diag.diagnose('tests/htn_demo/test_demo_fail.py', execute=True)
        self.assertEqual([name for _, name in seen], ['test_report', 'locate'])
        self.assertEqual([c['name'] for c in result['calls']], ['run_test', 'test_report', 'locate'])
        self.assertEqual(result['finding']['status'], 'found')
        fake, seen = recorded('tests/htn_demo/test_demo_pass.py')
        with patch.object(htn_diag.cmd, 'run_as', fake):
            result = htn_diag.diagnose('tests/htn_demo/test_demo_pass.py', execute=True)
        self.assertEqual([name for _, name in seen], ['test_report'])
        self.assertEqual(result['finding']['status'], 'passed')

    def test_fast_off_same_result(self):
        for test in CASES:
            with self.subTest(test=test):
                outs = []
                for fast in (False, True):
                    fake, _ = recorded(test)
                    orig = htn_diag.make_runner
                    with patch.object(htn_diag.cmd, 'run_as', fake), \
                            patch.object(htn_diag, 'make_runner', lambda *a, **k: orig(*a, **dict(k, fast=fast))):
                        f = htn_diag.diagnose(test, execute=True)['finding']
                    outs.append((f['status'], [(c['file'], c['line']) for c in f['candidates']]))
                self.assertEqual(outs[0], outs[1])

    def test_detail_has_report(self):
        result = self.run_case('tests/htn_bench/test_cmd_k2.py')
        text = htn_diag.detail(result)
        self.assertIn('== test_report 原文', text)
        self.assertIn('最内层仓库内帧', text)

    def test_runner_exit_code(self):
        runner = htn_diag.make_runner('custom', lambda caller, name, args: {'status': 'ok', 'exit_code': None, 'output': None})
        self.assertEqual(runner('run_test', {'path': 'x'}), {'status': 'ok', 'exit_code': 1, 'output': ''})

    def test_dry_run(self):
        with patch.object(htn_diag.cmd, 'run_as', lambda *a: self.fail('dry run must not call commands')):
            result = htn_diag.diagnose('tests/htn_demo/test_demo_fail.py')
        self.assertEqual(result['mode'], 'dry_run')
        self.assertIsNone(result['finding'])
        self.assertEqual(htn_diag.summarize(result).split('\n')[0], 'status: not_run（只空跑了计划，没有执行）')

    def test_cli_detail_uses_cache(self):
        test = 'tests/htn_demo/test_demo_fail.py'
        fake, seen = recorded(test)
        with patch.object(htn_diag.cmd, 'run_as', fake):
            with redirect_stdout(io.StringIO()) as out1:
                htn_diag.main([test])
            first = len(seen)
            with redirect_stdout(io.StringIO()) as out2:
                htn_diag.main([test, '--detail'])
        self.assertIn('buggy.py:7', out1.getvalue())
        self.assertEqual(len(seen), first)  # --detail 读缓存，没有再调指令
        self.assertIn('== test_report 原文', out2.getvalue())


class RealTests(unittest.TestCase):
    def test_import_failure(self):
        result = htn_diag.diagnose('tests/htn_demo/test_demo_import.py', execute=True)
        c = result['finding']['candidates'][0]
        self.assertEqual((c['file'], c['line']), ('tests/htn_demo/test_demo_import.py', 3))

    def test_real_k2(self):
        result = htn_diag.diagnose('tests/htn_bench/test_cmd_k2.py', execute=True)
        self.assertEqual(result['finding']['status'], 'found')
        self.assertIn(('data/tmp/hb/k2/tools/cmd.py', 196),
                      [(c['file'], c['line']) for c in result['finding']['candidates']])

    def test_examples(self):
        for filename, status in [('test_demo_pass.py', 'passed'), ('test_demo_fail.py', 'found'),
                                 ('test_demo_inline.py', 'found')]:
            with self.subTest(filename=filename):
                result = htn_diag.diagnose('tests/htn_demo/' + filename, execute=True)
                self.assertEqual(result['finding']['status'], status, result['summary'])
                self.assertTrue(all(type(call['exit_code']) is int for call in result['calls']))


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if result.wasSuccessful():
        print('全部通过')
    sys.exit(not result.wasSuccessful())
