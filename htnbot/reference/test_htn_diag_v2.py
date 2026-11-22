"""Offline and real integration checks for the HTN diagnostic adapter."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools import htn_diag

PATH = 'tests/htn_demo/test_demo_fail.py'


class OfflineTests(unittest.TestCase):
    def scenario(self, test_code=1, locate_output=' 1. data/tmp/htn_demo/buggy.py:7  1.000  失败 1/1  通过 0/1  | return total',
                 probe_status='ok', allow=None):
        seen = []

        def fake(caller, name, args):
            seen.append((caller, name, args.copy()))
            responses = {
                'run_test': {'status': 'ok' if test_code == 0 else 'failed', 'exit_code': test_code, 'output': ''},
                'test_report': {'status': 'ok', 'exit_code': 0,
                                'output': 'data/tmp/htn_demo/buggy.py:7\n> 7   return value + missing\n'},
                'locate': {'status': 'ok', 'exit_code': 0, 'output': locate_output},
                'probe': {'status': probe_status, 'exit_code': 0 if probe_status == 'ok' else 1, 'output': ''},
            }
            return responses[name]

        with patch.object(htn_diag.cmd, 'run_as', fake):
            result = htn_diag.diagnose(PATH, execute=True, allow=allow)
        self.assertTrue(all(type(call['exit_code']) is int for call in result['calls']))
        self.assertEqual([x[1] for x in seen], [x['name'] for x in result['calls']])
        return result, seen

    def test_pass(self):
        result, seen = self.scenario(test_code=0)
        self.assertEqual(result['report']['status'], 'done')
        self.assertEqual([x[1] for x in seen], ['run_test'])

    def test_locate(self):
        result, seen = self.scenario()
        self.assertEqual(result['report']['status'], 'done')
        self.assertEqual([x[1] for x in seen], ['run_test', 'test_report', 'locate'])

    def test_probe(self):
        result, seen = self.scenario(locate_output='')
        self.assertEqual(result['report']['status'], 'done')
        self.assertEqual([x[1] for x in seen], ['run_test', 'test_report', 'locate', 'probe'])
        self.assertEqual(seen[-1][2], {'path': PATH, 'at': ['data/tmp/htn_demo/buggy.py:7'],
                                      'exprs': ['total', 'xs']})

    def test_probe_failure_stuck(self):
        result, seen = self.scenario(locate_output='', probe_status='failed')
        self.assertEqual(result['report']['status'], 'stuck')
        self.assertEqual([x[1] for x in seen], ['run_test', 'test_report', 'locate', 'probe'])

    def test_allow_without_locate(self):
        result, seen = self.scenario(allow=['run_test', 'test_report', 'probe'])
        self.assertEqual(result['report']['status'], 'stuck')
        self.assertEqual(result['report']['stuck']['reason'], 'no_plan')
        self.assertEqual([x[1] for x in seen], ['run_test'])

    def test_exit_codes_and_isolation(self):
        runner = htn_diag.make_runner('custom', lambda caller, name, args: {
            'status': 'ok', 'exit_code': None, 'output': ''})
        self.assertEqual(runner('run_test', {'path': PATH})['exit_code'], 1)
        state = json.loads(runner('diag_state', {})['output'])
        self.assertEqual(state['files'][0]['result'], 'red')
        self.assertEqual(json.loads(htn_diag.make_runner()( 'diag_state', {})['output']), {'files': []})
        self.assertEqual(runner('probe', {'path': PATH})['exit_code'], 2)

    def test_dry_run(self):
        result = htn_diag.diagnose(PATH)
        self.assertEqual(result['mode'], 'dry_run')
        self.assertTrue(result['report']['plan']['found'])
        self.assertEqual(result['calls'], [])
        self.assertIsNone(result['finding'])

    def test_ties_and_summary(self):
        result, _ = self.scenario(locate_output=(
            ' 1. data/tmp/htn_demo/buggy.py:7  1.000  失败 1/1  通过 0/1  | x\n'
            ' 2. data/tmp/htn_demo/buggy.py:6  1.000  失败 1/1  通过 0/1  | y'))
        candidates = result['finding']['candidates']
        self.assertGreaterEqual(len(candidates), 2)
        self.assertTrue(all(c['code'] for c in candidates))
        text = htn_diag.summarize(result)
        self.assertLessEqual(len(text), 2500)
        self.assertIn('data/tmp/htn_demo/buggy.py:7', text)


class RealTests(unittest.TestCase):
    def test_import_failure(self):
        result = htn_diag.diagnose('tests/htn_demo/test_demo_import.py', execute=True)
        self.assertEqual(result['finding']['kind'], 'cannot_run')
        self.assertEqual(sum(c['name'] == 'test_report' for c in result['calls']), 1)
        candidate = result['finding']['candidates'][0]
        self.assertEqual((candidate['file'], candidate['line']), ('tests/htn_demo/test_demo_import.py', 3))

    def test_real_k2(self):
        result = htn_diag.diagnose('tests/htn_bench/test_cmd_k2.py', execute=True)
        self.assertEqual(result['finding']['status'], 'found')
        self.assertIn(('data/tmp/hb/k2/tools/cmd.py', 196),
                      [(c['file'], c['line']) for c in result['finding']['candidates']])

    def test_examples(self):
        for filename, expected in [
            ('test_demo_pass.py', ['run_test']),
            ('test_demo_fail.py', ['run_test', 'test_report', 'locate']),
            ('test_demo_inline.py', ['run_test', 'test_report', 'locate', 'probe']),
        ]:
            with self.subTest(filename=filename):
                result = htn_diag.diagnose('tests/htn_demo/' + filename, execute=True)
                self.assertEqual(result['report']['status'], 'done', result)
                self.assertEqual([call['name'] for call in result['calls']], expected)
                self.assertTrue(all(type(call['exit_code']) is int for call in result['calls']))


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if result.wasSuccessful():
        print('全部通过')
    sys.exit(not result.wasSuccessful())
