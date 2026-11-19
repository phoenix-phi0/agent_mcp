import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools import cmd


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / 'state'
        self.table_path = self.root / 'table.json'
        self.old = {k: os.environ.get(k) for k in ('CMD_TABLE', 'CMD_HOME')}
        self.addCleanup(self.restore)
        os.environ.update(CMD_TABLE=str(self.table_path), CMD_HOME=str(self.home))
        self.table = json.loads((cmd.TABLE).read_text())
        for c in self.table['commands']:
            c['cwd'] = str(self.root)
        self.by_name('tail_log')['params']['path']['roots'] = [str(self.root)]
        self.by_name('restart_check')['steps'] = ['printf service']
        self.by_name('run_test')['steps'] = ['printf test']
        self.add('sleep', 'read', ['sleep 0.4; printf done'])
        self.add('bad', 'read', ['exit 7'])
        self.add('timeout', 'read', ["sleep 30 & echo $! > child.pid; wait"], timeout=0.25)
        self.add('echo', 'read', ['printf %s {value}'], {'value': {'type': 'text', 'required': True, 'max_len': 1000}})
        self.save()
        (self.root / 'tests').mkdir()
        (self.root / 'tests' / 'ok.py').write_text('pass')
        subprocess.run(['git', 'init', '-q'], cwd=self.root, check=True)
        subprocess.run(['git', 'config', 'user.email', 'test@example.org'], cwd=self.root, check=True)
        subprocess.run(['git', 'config', 'user.name', 'Test'], cwd=self.root, check=True)

    def restore(self):
        for k, v in self.old.items():
            if v is None: os.environ.pop(k, None)
            else: os.environ[k] = v

    def by_name(self, name):
        return next(c for c in self.table['commands'] if c['name'] == name)

    def add(self, name, level, steps, params=None, timeout=2):
        self.table['commands'].append(dict(name=name, level=level, doc=name, params=params or {}, cwd=str(self.root), steps=steps, mode='sync', timeout=timeout))

    def save(self):
        self.table_path.write_text(json.dumps(self.table))

    def check_pair(self, name, invalid, valid, caller='tool_call'):
        bad = cmd.run_as(caller, name, invalid)
        self.assertEqual(bad['status'], 'rejected', bad)
        self.assertTrue(bad['reason'])
        good = cmd.run_as(caller, name, valid)
        self.assertEqual(good['status'], 'ok', good)

    def test_validation_permissions_and_paths(self):
        self.assertEqual(cmd.run('missing')['status'], 'rejected')
        self.assertEqual(cmd.run('echo', {'value': 'ok'})['status'], 'ok')
        good = {'file': 'tests/ok.py'}
        for bad in ({}, {'file': 12}, {'file': 'tests/ok.py', 'tail': '4'}, {'file': 'tests/ok.py', 'tail': 201}, {'file': '../outside.py'}, {'file': '/etc/passwd'}, {'file': 'tests/ok.txt'}):
            self.check_pair('run_test', bad, good)
        (self.root / 'tests' / 'link.py').symlink_to('/etc/passwd')
        self.check_pair('run_test', {'file': 'tests/link.py'}, good)
        self.check_pair('restart_check', {'unit': 'other'}, {'unit': 'ali-trace.service'})
        self.assertEqual(cmd.run_as('small_model', 'restart_check', {'unit': 'ali-trace.service'})['status'], 'rejected')
        self.assertEqual(cmd.run('restart_check', {'unit': 'ali-trace.service'})['status'], 'ok')
        self.assertEqual(cmd.run_as('small_model', 'run_test', good)['status'], 'ok')

    def test_injection_commit_and_path(self):
        target = self.root / 'pwned'
        variants = [f'; touch {target}', f'$(touch {target})', f'`touch {target}`', f'\ntouch {target}']
        for text in variants:
            self.assertEqual(cmd.run('echo', {'value': text})['output'], text)
            name = 'tests/' + text + '.py'
            result = cmd.run('run_test', {'file': name})
            self.assertIn(result['status'], ('ok', 'rejected'))
            self.assertFalse(target.exists())
        (self.root / 'safe.txt').write_text('content')
        message = 'safe ' + ' '.join(variants)
        result = cmd.run('git_commit', {'files': ['safe.txt'], 'message': message})
        self.assertEqual(result['status'], 'ok', result)
        actual = subprocess.check_output(['git', 'log', '-1', '--format=%B'], cwd=self.root, text=True).rstrip('\n')
        self.assertEqual(actual, message)
        self.assertFalse(target.exists())

    def test_timeout_and_job(self):
        result = cmd.run('timeout')
        self.assertEqual(result['reason'], 'timeout')
        pid = int((self.root / 'child.pid').read_text())
        time.sleep(.05)
        stat = Path(f'/proc/{pid}/stat')
        self.assertTrue(not stat.exists() or stat.read_text().split()[2] == 'Z')
        started = cmd.run('job', {'action': 'start', 'command': 'sleep'})
        self.assertEqual(started['status'], 'running')
        jid = started['job']
        self.assertEqual(cmd.run('job', {'action': 'status', 'job': jid})['status'], 'running')
        for _ in range(100):
            result = cmd.run('job', {'action': 'result', 'job': jid})
            if result['status'] != 'running': break
            time.sleep(.03)
        self.assertEqual(result['status'], 'ok', result)
        self.assertEqual(result['output'], 'done')
        started = cmd.run('job', {'action': 'start', 'command': 'bad'})
        for _ in range(100):
            result = cmd.run('job', {'action': 'status', 'job': started['job']})
            if result['status'] != 'running': break
            time.sleep(.03)
        self.assertEqual((result['status'], result['exit_code']), ('failed', 7))

    def test_audit_and_filter(self):
        log = self.root / 'a.log'
        log.write_text('normal\nkey=abc\ntoken=abc\napi_key=abc\nsecret: abc\n"access_token": "abc"\nAuthorization: Bearer abc\npassword = x\nused 120 tokens total\nnormal two\n')
        self.assertEqual(cmd.run('tail_log', {'path': str(log)})['output'], 'normal\nused 120 tokens total\nnormal two\n')
        self.assertEqual(cmd.run('tail_log', {'path': str(log), 'grep': 'two'})['output'], 'normal two\n')
        self.check_pair('tail_log', {'path': 'a.bin'}, {'path': 'a.log'})
        rows = [json.loads(x) for x in (self.home / 'audit.jsonl').read_text().splitlines()]
        self.assertTrue({'ok', 'rejected'} <= {r['status'] for r in rows})
        for row in rows:
            self.assertEqual(set(row), {'time', 'caller', 'name', 'args', 'status', 'exit_code', 'seconds'})

    def test_real_table_templates_and_timeouts(self):
        table = json.loads(cmd.TABLE.read_text(encoding='utf-8'))
        args = {
            'run_test': {'file': 'tests/tools/test_cmd.py'},
            'git_snapshot': {},
            'git_commit': {'files': ['tools/cmd.py'], 'message': 'test'},
            'restart_check': {'unit': 'ali-trace.service'},
            'tail_log': {'path': '/tmp/example.log'},
        }
        for command in table['commands']:
            with self.subTest(command=command['name']):
                if command['mode'] == 'sync':
                    self.assertLessEqual(command['timeout'], 170)
                if command['name'] == 'job':
                    continue
                values = cmd._validate(command, args[command['name']])
                for step in cmd._prepare(command, values):
                    self.assertIsNone(re.search(r'\{[A-Za-z_][A-Za-z_0-9]*\}', step), step)


if __name__ == '__main__':
    unittest.main()
