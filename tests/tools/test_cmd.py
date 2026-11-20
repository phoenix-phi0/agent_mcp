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
    def test_list_as_permissions(self):
        names = {c['name'] for c in cmd.list_as('small_model')}
        self.assertTrue({'run_test', 'job', 'echo'} <= names)
        self.assertTrue({'restart_check', 'git_commit'}.isdisjoint(names))
        self.assertEqual(cmd.list_as('nobody'), [])
        self.assertEqual(cmd.list(), cmd.list_as('tool_call'))

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
        for name in ('grep', 'find'):
            self.by_name(name)['params']['path'].update(roots=[str(self.root)], default=str(self.root))
        self.by_name('restart_check')['steps'] = ['printf service']
        self.by_name('batch_status')['steps'] = ['printf %s {job_id}']
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

    def wait_job(self, jid):
        for _ in range(150):
            result = cmd.run('job', {'action': 'result', 'job': jid})
            if result['status'] != 'running':
                return result
            time.sleep(.02)
        self.fail('job did not finish')

    def test_new_validation_and_real_commands(self):
        (self.root / 'needle.txt').write_text('needle visible\nneedle password=hidden\n')
        for field, name, args in [('include', 'grep', {'pattern': 'needle'}), ('name', 'find', {})]:
            for bad in ['-x', '--output=/tmp/x', '; touch pwned', '$(touch pwned)', '`touch pwned`']:
                invalid = dict(args, **{field: bad})
                valid = dict(args, **{field: '*.txt'})
                self.check_pair(name, invalid, valid)
        for payload in [f'; touch {self.root}/pwned', f'$(touch {self.root}/pwned)', f'`touch {self.root}/pwned`']:
            self.assertEqual(cmd.run('grep', {'pattern': payload})['status'], 'ok')
            self.check_pair('find', {'name': payload}, {'name': '*.txt'})
        self.assertFalse((self.root / 'pwned').exists())
        found = cmd.run('grep', {'pattern': 'needle'})
        self.assertEqual(found['status'], 'ok', found)
        self.assertIn('needle visible', found['output'])
        self.assertNotIn('password=hidden', found['output'])
        self.assertEqual(cmd.run('grep', {'pattern': 'NO_SUCH_MATCH_4823'})['output'], '')
        self.assertIn('needle.txt', cmd.run('find', {'name': '*.txt'})['output'])
        self.assertIn(str(os.getpid()), cmd.run('ps_check', {'pattern': 'test_cmd.py'})['output'])
        subprocess.run(['git', 'add', 'needle.txt'], cwd=self.root, check=True)
        subprocess.run(['git', 'commit', '-qm', 'base'], cwd=self.root, check=True)
        (self.root / 'needle.txt').write_text('changed unique diff\n')
        self.assertIn('changed unique diff', cmd.run('git_diff')['output'])
        self.check_pair('batch_status', {'queue': 'gsbatch', 'job_id': '../../etc'}, {'queue': 'gsbatch', 'job_id': '20260101-123456-abcd'})

    def test_push_local_bare(self):
        bare = self.root / 'origin.git'
        subprocess.run(['git', 'init', '--bare', '-q', str(bare)], check=True)
        subprocess.run(['git', 'remote', 'add', 'origin', str(bare)], cwd=self.root, check=True)
        (self.root / 'tracked').write_text('content')
        subprocess.run(['git', 'add', 'tracked'], cwd=self.root, check=True)
        subprocess.run(['git', 'commit', '-qm', 'base'], cwd=self.root, check=True)
        self.assertEqual(cmd.run_as('small_model', 'git_push')['status'], 'rejected')
        pushed = cmd.run('git_push')
        self.assertEqual(pushed['status'], 'ok', pushed)
        head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=self.root, text=True).strip()
        subprocess.run(['git', '--git-dir', str(bare), 'cat-file', '-e', head + '^{commit}'], check=True)

    def test_job_only_cancel_and_permissions(self):
        self.add('only', 'write', ['touch side_effect; printf done'])
        self.by_name('only')['mode'] = 'job_only'
        self.add('long', 'service', ['sleep 30 & echo $! > child_job.pid; wait'])
        self.save()
        self.assertEqual(cmd.run('only')['status'], 'rejected')
        self.assertFalse((self.root / 'side_effect').exists())
        jid = cmd.run('job', {'action': 'start', 'command': 'only'})['job']
        self.assertEqual(self.wait_job(jid)['output'], 'done')
        self.assertTrue((self.root / 'side_effect').exists())
        self.assertIn('已经结束', cmd.run('job', {'action': 'cancel', 'job': jid})['reason'])
        for name, args in [('long', {}), ('only', {})]:
            self.assertEqual(cmd.run_as('small_model', 'job', {'action': 'start', 'command': name, 'args': args})['status'], 'rejected')
        allowed = cmd.run_as('small_model', 'job', {'action': 'start', 'command': 'run_test', 'args': {'file': 'tests/ok.py'}})
        self.assertEqual(self.wait_job(allowed['job'])['status'], 'ok')
        started = cmd.run('job', {'action': 'start', 'command': 'long'})
        jid = started['job']
        for _ in range(100):
            if (self.root / 'child_job.pid').exists(): break
            time.sleep(.02)
        pid = int((self.root / 'child_job.pid').read_text())
        listing = cmd.run('job', {'action': 'list'})
        self.assertIn(jid + ' long running ', listing['output'])
        self.assertNotIn(jid, cmd.run_as('small_model', 'job', {'action': 'list'})['output'])
        for action in ('status', 'result', 'cancel'):
            self.assertEqual(cmd.run_as('small_model', 'job', {'action': action, 'job': jid})['status'], 'rejected')
        result = cmd.run('job', {'action': 'cancel', 'job': jid})
        self.assertEqual((result['status'], result['reason']), ('failed', 'cancelled'))
        self.assertEqual(cmd.run('job', {'action': 'status', 'job': jid})['reason'], 'cancelled')
        time.sleep(1)
        stat = Path(f'/proc/{pid}/stat')
        self.assertTrue(not stat.exists() or stat.read_text().split()[2] == 'Z')
        result = json.loads((self.home / 'jobs' / jid / 'result.json').read_text())
        self.assertEqual(result['status'], 'cancelled')
        self.assertEqual(cmd.run('job', {'action': 'cancel', 'job': 'a' * 32})['status'], 'rejected')

    def test_real_table_templates_and_timeouts(self):
        table = json.loads(cmd.TABLE.read_text(encoding='utf-8'))
        args = {
            'run_test': {'file': 'tests/tools/test_cmd.py'},
            'git_snapshot': {},
            'git_commit': {'files': ['tools/cmd.py'], 'message': 'test'},
            'restart_check': {'unit': 'ali-trace.service'},
            'tail_log': {'path': '/tmp/example.log'},
            'git_diff': {}, 'git_push': {}, 'grep': {'pattern': 'test'},
            'find': {}, 'ps_check': {'pattern': 'test'},
            'batch_jobs': {'queue': 'gsbatch'},
            'batch_status': {'queue': 'gsbatch', 'job_id': '20260101-123456-abcd'},
            'run_all': {},
        }
        for command in table['commands']:
            with self.subTest(command=command['name']):
                if command['mode'] == 'sync':
                    self.assertLessEqual(command['timeout'], 170)
                if command['name'] == 'job':
                    continue
                for template in command['steps']:
                    stripped = re.sub(r'\{(?:log|' + '|'.join(map(re.escape, command['params'])) + r')\}', '', template)
                    self.assertNotRegex(stripped, r'[{}]')
                values = cmd._validate(command, args[command['name']])
                for step in cmd._prepare(command, values):
                    self.assertIsNone(re.search(r'\{[A-Za-z_][A-Za-z_0-9]*\}', step), step)


if __name__ == '__main__':
    unittest.main()
