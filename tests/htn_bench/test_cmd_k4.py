import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'data/tmp/hb/k4'))
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
        self.by_name('show')['params']['path']['roots'] = [str(self.root)]
        self.by_name('show')['params']['paths']['roots'] = [str(self.root)]
        for name in ('grep', 'find'):
            self.by_name(name)['params']['path'].update(roots=[str(self.root)], default=str(self.root))
        self.by_name('restart_check')['steps'] = ['printf service']
        self.by_name('batch_status')['steps'] = ['printf %s {job}']
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
        good = {'path': 'tests/ok.py'}
        for bad in ({}, {'path': 12}, {'path': 'tests/ok.py', 'limit': '4'}, {'path': 'tests/ok.py', 'limit': 201}, {'path': '../outside.py'}, {'path': '/etc/passwd'}, {'path': 'tests/ok.txt'}):
            self.check_pair('run_test', bad, good)
        (self.root / 'tests' / 'link.py').symlink_to('/etc/passwd')
        self.check_pair('run_test', {'path': 'tests/link.py'}, good)
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
            result = cmd.run('run_test', {'path': name})
            self.assertIn(result['status'], ('ok', 'rejected'))
            self.assertFalse(target.exists())
        (self.root / 'safe.txt').write_text('content')
        message = 'safe ' + ' '.join(variants)
        result = cmd.run('git_commit', {'paths': ['safe.txt'], 'text': message})
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
        self.assertEqual(cmd.run('tail_log', {'path': str(log)})['output'], log.read_text())
        self.assertEqual(cmd.run('tail_log', {'path': str(log), 'out': [{'filter': 'two'}]})['output'], 'normal two\n')
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
        for field, name, args in [('name', 'grep', {'text': 'needle'}), ('name', 'find', {})]:
            for bad in ['-x', '--output=/tmp/x', '; touch pwned', '$(touch pwned)', '`touch pwned`']:
                invalid = dict(args, **{field: bad})
                valid = dict(args, **{field: '*.txt'})
                self.check_pair(name, invalid, valid)
        for payload in [f'; touch {self.root}/pwned', f'$(touch {self.root}/pwned)', f'`touch {self.root}/pwned`']:
            self.assertEqual(cmd.run('grep', {'text': payload})['status'], 'ok')
            self.check_pair('find', {'name': payload}, {'name': '*.txt'})
        self.assertFalse((self.root / 'pwned').exists())
        found = cmd.run('grep', {'text': 'needle'})
        self.assertEqual(found['status'], 'ok', found)
        self.assertIn('needle visible', found['output'])
        self.assertIn('password=hidden', found['output'])
        self.assertEqual(cmd.run('grep', {'text': 'NO_SUCH_MATCH_4823'})['output'], '')
        self.assertIn('needle.txt', cmd.run('find', {'name': '*.txt'})['output'])
        # 不靠「本进程的命令行里有 test_cmd.py」：用 python -m unittest 跑时没有这段文字，断言会假失败
        marker = 'cmd_ps_marker_%d' % os.getpid()
        sleeper = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(20)', marker])
        try:
            self.assertIn(str(sleeper.pid), cmd.run('ps_check', {'text': marker})['output'])
        finally:
            sleeper.kill()
            sleeper.wait()
        subprocess.run(['git', 'add', 'needle.txt'], cwd=self.root, check=True)
        subprocess.run(['git', 'commit', '-qm', 'base'], cwd=self.root, check=True)
        (self.root / 'needle.txt').write_text('changed unique diff\n')
        self.assertIn('changed unique diff', cmd.run('git_diff')['output'])
        self.check_pair('batch_status', {'queue': 'gsbatch', 'job': '../../etc'}, {'queue': 'gsbatch', 'job': '20260101-123456-abcd'})

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
        allowed = cmd.run_as('small_model', 'job', {'action': 'start', 'command': 'run_test', 'args': {'path': 'tests/ok.py'}})
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
            'run_test': {'path': 'tests/tools/test_cmd.py'},
            'git_snapshot': {},
            'git_commit': {'paths': ['tools/cmd.py'], 'text': 'test'},
            'restart_check': {'unit': 'ali-trace.service'},
            'tail_log': {'path': '/tmp/example.log'},
            'git_diff': {}, 'git_push': {}, 'grep': {'text': 'test'},
            'find': {}, 'ps_check': {'text': 'test'},
            'batch_jobs': {'queue': 'gsbatch'},
            'batch_status': {'queue': 'gsbatch', 'job': '20260101-123456-abcd'},
            'run_all': {}, 'show': {'path': '/workspace/example.txt'},
            'git_log': {}, 'git_sync': {}, 'test_at_head': {'path': 'tests/tools/test_cmd.py'},
            'test_report': {'path': 'tests/tools/test_cmd.py', 'case': 'OutputTests.test_out_steps'},
            'locate': {'path': 'tests/tools/test_cmd.py', 'paths': ['tools/cmd.py']},
            'probe': {'path': 'tests/tools/test_cmd.py', 'at': ['tools/cmd.py:24', 'tools/cmd.py:28'],
                      'exprs': ['name', 'len(args)', "values['limit']", '-1']},
            'blame_change': {'path': 'tests/tools/test_cmd.py', 'paths': ['tools/dbg.py']},
            'exp_list': {}, 'exp_status': {'run': 'demo-0001'},
            'exp_wait': {'run': 'demo-0001'}, 'exp_results': {'run': 'demo-0001'},
            'exp_compare': {'run': 'demo-0001'}, 'exp_start': {'exp': 'demo'},
            'exp_cancel': {'run': 'demo-0001'},
            'exp_register': {'exp': 'demo', 'path': 'data/tmp/demo.py', 'result': 'data/tmp/result.json'},
        }
        self.assertEqual(set(args) | {'job'}, {c['name'] for c in table['commands']})
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
        probe = cmd._prepare(self.real('probe', table), cmd._validate(self.real('probe', table), args['probe']))[0]
        self.assertTrue(probe.endswith("--at tools/cmd.py:24 tools/cmd.py:28 --exprs name 'len(args)' 'values['\"'\"'limit'\"'\"']' -1"), probe)
        only_path = cmd._prepare(self.real('blame_change', table), cmd._validate(self.real('blame_change', table), {'path': 'tests/tools/test_cmd.py'}))[0]
        self.assertTrue(only_path.endswith("--case '' --runs 40 --paths "), only_path)
        for bad in ({'at': ['tools/cmd.py']}, {'at': []}, {'exprs': ['x'] * 9}, {'exprs': [1]}):
            with self.subTest(bad=bad):
                self.assertRaises(ValueError, cmd._validate, self.real('probe', table), dict(args['probe'], **bad))

    @staticmethod
    def real(name, table):
        return next(c for c in table['commands'] if c['name'] == name)


    def git(self, *args, cwd=None):
        return subprocess.check_output(['git', *args], cwd=cwd or self.root, text=True, stderr=subprocess.STDOUT).strip()

    def test_redact_and_multiple_show(self):
        safe = ["key = (period, source)", "sorted(rows, key=lambda r: r['rank'])",
                "token = next(tokens)", "for key, value in d.items():", "password = getpass()",
                '"key": "name"', "key = build_cache_key2(period, source)",
                "self._tokens[key] = value", "if key in self._resolved:",
                'secret = os.environ["APP_SECRET"]']
        pairs = {
            'api_key = "sk-abc123def456"': 'api_key = "[已隐藏]"',
            '"token": "a1b2c3d4"': '"token": "[已隐藏]"',
            '"access token": "abcdef"': '"access token": "[已隐藏]"',
            "password='x'": "password='[已隐藏]'",
            "passwd='x'": "passwd='[已隐藏]'",
            "pwd='x'": "pwd='[已隐藏]'",
            'OPENAI_API_KEY=sk-abc123def456ghi': 'OPENAI_API_KEY=[已隐藏]',
            'token: 9f8e7d6c5b4a3210': 'token: [已隐藏]',
            'Authorization: Bearer abcdef123456': 'Authorization: Bearer [已隐藏]',
            'sk-abcdefghijklmnop1234 ghp_abcdefghijklmnop1234 gho_abcdefghijklmnop1234': '[已隐藏] [已隐藏] [已隐藏]',
            'AKIAabcdefghijklmnop1234 xoxb-abcdefghijklmnop1234 eyJabc.def.ghi': '[已隐藏] [已隐藏] [已隐藏]',
            'credential="abcdef"; secret="123456"': 'credential="[已隐藏]"; secret="[已隐藏]"',
        }
        for original, expected in pairs.items():
            with self.subTest(original=original):
                self.assertEqual(cmd._redact(original), expected)
        for line in safe:
            with self.subTest(line=line):
                self.assertEqual(cmd._redact(line), line)
        pem = '  1\t-----BEGIN RSA PRIVATE KEY-----\n  2\tcontents\n  3\t-----END RSA PRIVATE KEY-----\n  4\tnormal\n'
        self.assertEqual(cmd._redact(pem), '  1\t[已隐藏：私钥]\n  2\t[已隐藏：私钥]\n  3\t[已隐藏：私钥]\n  4\tnormal\n')
        self.assertEqual(cmd._redact('f:1:-----BEGIN PRIVATE KEY-----\nf:2:contents\n'),
                         'f:1:[已隐藏：私钥]\nf:2:[已隐藏：私钥]\n')
        a, b = self.root / 'a.py', self.root / 'b.py'
        a.write_text('\n'.join(safe + list(pairs)) + '\n')
        b.write_text('one\ntwo\nthree\n')
        result = cmd.run('show', {'paths': [str(a), str(b)], 'start': 1, 'limit': 30})
        self.assertEqual(result['status'], 'ok', result)
        self.assertIn('== a.py（共 %d 行）==' % (len(safe) + len(pairs)), result['output'])
        self.assertIn('== b.py（共 3 行）==', result['output'])
        for line in safe: self.assertIn(line, result['output'])
        for number, expected in enumerate(pairs.values(), len(safe) + 1):
            self.assertIn(str(number) + '\t' + expected, result['output'])
        result = cmd.run('show', {'path': str(a), 'paths': str(b), 'start': 2, 'limit': 1})
        self.assertIn('2\t' + safe[1], result['output'])
        self.assertIn('2\ttwo', result['output'])
        self.assertNotIn('==', cmd.run('show', {'paths': str(b)})['output'])
        self.assertEqual(cmd.run('show', {'paths': [str(self.root / 'config.json')]})['status'], 'rejected')
        self.assertEqual(cmd.run('show', {'paths': [str(self.root / ('%d.py' % i)) for i in range(13)]})['status'], 'rejected')
        log = self.root / 's.log'; log.write_text('api_key = "abc123456789012345"\n')
        self.assertEqual(cmd.run('tail_log', {'path': str(log)})['output'], 'api_key = "[已隐藏]"\n')
        self.assertIn('s.log:1:api_key = "[已隐藏]"', cmd.run('grep', {'text': 'api_key', 'path': str(self.root)})['output'])
        self.add('redact_failure', 'read', ["printf 'token=abc123456789012345\n'; exit 1"])
        self.by_name('redact_failure')['redact'] = True
        self.save()
        failure = cmd.run('redact_failure')
        self.assertEqual(failure['status'], 'failed')
        self.assertEqual(failure['output'], 'token=[已隐藏]\n')

    def test_redact_table_and_head_truncation(self):
        for name in ('show', 'grep', 'tail_log', 'ps_check', 'batch_status'):
            command = self.by_name(name)
            self.assertTrue(command['redact'])
            self.assertNotIn('grep -viE', ' '.join(command['steps']))
        path = self.root / 'long.txt'
        path.write_text(''.join('%04d %s\n' % (i, 'a' * 100) for i in range(700)))
        command = self.by_name('show'); command['max_output'] = 800
        self.save()
        result = cmd.run('show', {'path': str(path), 'limit': 700})
        self.assertTrue(result['truncated'])
        self.assertLessEqual(len(result['output']), 800)
        self.assertIn('继续读', result['output'])
        self.assertIn('0000', result['output'])
        self.assertNotIn('0699', result['output'])
        job = cmd.run('job', {'action': 'start', 'command': 'show', 'args': {'path': str(path), 'limit': 700}})
        result = self.wait_job(job['job'])
        self.assertTrue(result['truncated'])
        self.assertIn('long.txt 第', result['output'])
        self.assertLessEqual(len(result['output']), 800)
        log = self.root / 'job.log'; log.write_text('token=abc123456789012345\n')
        job = cmd.run('job', {'action': 'start', 'command': 'tail_log', 'args': {'path': str(log)}})
        self.assertEqual(self.wait_job(job['job'])['output'], 'token=[已隐藏]\n')

    def test_show_audit_job_and_find(self):
        f = self.root / 'visible.txt'
        f.write_text("first\nsecond\npassword='hide'\nfourth\n")
        result = cmd.run_as('small_model', 'show', {'path': str(f), 'start': 2, 'limit': 3})
        self.assertEqual(result['status'], 'ok', result)
        self.assertRegex(result['output'], r'2\s+second')
        self.assertRegex(result['output'], r'4\s+fourth')
        self.assertIn("password='[已隐藏]'", result['output'])
        self.assertEqual(cmd.run('show', {'path': str(f), 'start': 50})['output'], '')
        for name in ('secret.env', 'config.json', '.git/config'):
            self.check_pair('show', {'path': str(self.root / name)}, {'path': str(f)})
        self.check_pair('show', {'path': '../escape'}, {'path': str(f)})
        self.assertNotIn('audit_error', result)
        (self.home / 'audit.jsonl').unlink()
        (self.home / 'audit.jsonl').mkdir()
        self.assertIn('audit_error', cmd.run('show', {'path': str(f)}))
        self.add('long_output', 'read', ["printf 'needle near beginning\n'; yes filler | head -n 2000; printf 'last line\n'"])
        self.save()
        jid = cmd.run('job', {'action': 'start', 'command': 'long_output'})['job']
        ordinary = self.wait_job(jid)
        self.assertLessEqual(len(ordinary['output']), 8000)
        self.assertIn('输出已截断', ordinary['output'])
        self.assertEqual(cmd.run('job', {'action': 'result', 'job': jid, 'out': [{'filter': 'needle'}]})['output'], 'needle near beginning\n')
        self.assertEqual(cmd.run('job', {'action': 'result', 'job': jid, 'out': [{'tail': 2}]})['output'], 'filler\nlast line\n')
        for i in range(3):
            path = self.root / ('order%d.txt' % i)
            path.touch()
            os.utime(path, (1700000000 + i * 120, 1700000000 + i * 120))
        out = cmd.run('find', {'name': 'order*.txt'})['output']
        self.assertLess(out.index('order2.txt'), out.index('order1.txt'))
        self.assertLess(out.index('order1.txt'), out.index('order0.txt'))

    def setup_remote(self):
        bare = self.root / 'remote.git'
        subprocess.run(['git', 'init', '--bare', '-q', str(bare)], check=True)
        (self.root / 'tracked').write_text('base\n')
        (self.root / 'other').write_text('other\n')
        self.git('add', 'tracked', 'other')
        self.git('commit', '-qm', 'base')
        self.git('remote', 'add', 'origin', str(bare))
        self.git('push', '-u', 'origin', 'HEAD')
        peer = self.root / 'peer'
        subprocess.run(['git', 'clone', '-q', str(bare), str(peer)], check=True)
        self.git('config', 'user.email', 'peer@example.org', cwd=peer)
        self.git('config', 'user.name', 'Peer', cwd=peer)
        return bare, peer

    def peer_commit(self, peer, name='tracked', text='upstream\n'):
        (peer / name).write_text(text)
        self.git('add', name, cwd=peer)
        self.git('commit', '-qm', 'upstream', cwd=peer)
        self.git('push', cwd=peer)

    def test_git_sync_log_push(self):
        bare, peer = self.setup_remote()
        self.assertIn('已是最新', cmd.run('git_sync')['output'])
        self.assertIn('没有要推', cmd.run('git_push')['output'])
        self.assertIn('base', cmd.run_as('small_model', 'git_log')['output'])
        (self.root / 'local').write_text('local')
        self.git('add', 'local'); self.git('commit', '-qm', 'local commit')
        self.peer_commit(peer)
        self.git('fetch', 'origin')
        self.assertIn('ahead=1 behind=1', cmd.run('git_log', {'range': 'ahead'})['output'])
        self.assertIn('local commit', cmd.run('git_log', {'range': 'ahead'})['output'])
        self.assertIn('upstream', cmd.run('git_log', {'range': 'behind'})['output'])
        old_remote = self.git('--git-dir', str(bare), 'rev-parse', 'HEAD')
        self.assertEqual(cmd.run('git_push')['exit_code'], 2)
        self.assertEqual(self.git('--git-dir', str(bare), 'rev-parse', 'HEAD'), old_remote)
        (self.root / 'other').write_text('local change\n')
        result = cmd.run('git_sync')
        self.assertEqual(result['status'], 'ok', result)
        self.assertEqual((self.root / 'other').read_text(), 'local change\n')
        self.assertEqual(self.git('log', '-1', '--format=%s'), 'local commit')
        self.assertEqual(cmd.run('git_push')['status'], 'ok')
        self.assertEqual(self.git('--git-dir', str(bare), 'rev-parse', 'HEAD'), self.git('rev-parse', 'HEAD'))
        for name in ('git_sync', 'git_push', 'test_at_head'):
            self.assertEqual(cmd.run_as('small_model', name, {'path': 'tests/ok.py'} if name == 'test_at_head' else {})['status'], 'rejected')

    def test_sync_clean_behind(self):
        bare, peer = self.setup_remote()
        self.peer_commit(peer)
        result = cmd.run('git_sync')
        self.assertEqual(result['status'], 'ok', result)
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.git('--git-dir', str(bare), 'rev-parse', 'HEAD'))
        self.assertEqual((self.root / 'tracked').read_text(), 'upstream\n')

    def test_sync_refusals_and_conflict(self):
        bare, peer = self.setup_remote()
        self.peer_commit(peer)
        (self.root / 'tracked').write_text('dirty\n')
        before = self.git('rev-parse', 'HEAD')
        result = cmd.run('git_sync')
        self.assertEqual(result['exit_code'], 2, result)
        self.assertEqual(self.git('rev-parse', 'HEAD'), before)
        self.assertEqual((self.root / 'tracked').read_text(), 'dirty\n')
        (self.root / 'tracked').write_text('base\n')
        (self.root / 'newfile').write_text('untracked\n')
        self.peer_commit(peer, 'newfile', 'remote file\n')
        result = cmd.run('git_sync')
        self.assertEqual(result['exit_code'], 2, result)
        self.assertEqual((self.root / 'newfile').read_text(), 'untracked\n')
        (self.root / 'newfile').unlink()
        (self.root / 'tracked').write_text('conflicting commit\n')
        self.git('add', 'tracked'); self.git('commit', '-qm', 'conflict')
        before = self.git('rev-parse', 'HEAD')
        result = cmd.run('git_sync')
        self.assertEqual(result['exit_code'], 3, result)
        self.assertEqual(self.git('rev-parse', 'HEAD'), before)
        self.assertFalse((self.root / '.git/rebase-merge').exists())
        self.assertEqual(self.git('status', '--porcelain', '--untracked-files=no'), '')

    def test_run_test_and_at_head(self):
        (self.root / '.venv/bin').mkdir(parents=True)
        (self.root / '.venv/bin/python').symlink_to(sys.executable)
        original = next(c for c in json.loads(cmd.TABLE.read_text())['commands'] if c['name'] == 'run_test')
        self.by_name('run_test')['steps'] = original['steps']
        self.save()
        (self.root / 'module.py').write_text('value = 1\n')
        test = self.root / 'tests/ok.py'
        test.write_text("import unittest\nclass T(unittest.TestCase):\n def test_one(self): self.assertTrue(True)\n def test_two(self): self.assertTrue(True)\nif __name__ == '__main__': unittest.main()\n")
        self.git('add', 'module.py', 'tests/ok.py'); self.git('commit', '-qm', 'base')
        result = cmd.run('run_test', {'path': 'tests/ok.py', 'case': 'T.test_one'})
        self.assertEqual(result['status'], 'ok', result)
        self.assertIn('Ran 1 test', result['output'])
        self.assertTrue(Path(result['output'].splitlines()[0][4:]).exists())
        self.assertIn('Ran 2 tests', cmd.run('run_test', {'path': 'tests/ok.py'})['output'])
        self.assertEqual(cmd.run('run_test', {'path': 'tests/ok.py', 'case': 'bad;'} )['status'], 'rejected')
        temp_parent = self.root / 'tempfiles'
        temp_parent.mkdir()
        previous_tmp = os.environ.get('TMPDIR')
        os.environ['TMPDIR'] = str(temp_parent)
        try:
            self.assertEqual(cmd.run('test_at_head', {'path': 'tests/ok.py'})['status'], 'ok')
            self.assertEqual(list(temp_parent.iterdir()), [])
        finally:
            if previous_tmp is None: os.environ.pop('TMPDIR', None)
            else: os.environ['TMPDIR'] = previous_tmp
        (self.root / 'module.py').write_text('value = 2\n')
        fresh = self.root / 'tests/new.py'
        fresh.write_text("import sys, pathlib\nsys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))\nimport module\nassert module.value == 2\n")
        self.assertEqual(cmd.run('run_test', {'path': 'tests/new.py'})['status'], 'ok')
        self.assertEqual(cmd.run('test_at_head', {'path': 'tests/new.py'})['exit_code'], 2)
        self.assertNotEqual(cmd.run('test_at_head', {'path': 'tests/new.py', 'paths': ['tests/new.py']})['exit_code'], 0)


class OutputTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.old = {k: os.environ.get(k) for k in ('CMD_TABLE', 'CMD_HOME')}
        self.addCleanup(self.restore)
        os.environ.update(CMD_TABLE=str(self.root / 'table.json'), CMD_HOME=str(self.root / 'state'))
        self.table = json.loads(cmd.TABLE.read_text())
        self.table['commands'].extend([
            dict(name='sample', level='read', doc='sample', params={}, cwd=str(self.root),
                 steps=["printf '2 b\n1 a\n2 b\n3 c\n'"], mode='sync', timeout=5),
            dict(name='large', level='read', doc='large', params={'limit': {'type': 'int', 'default': 2}},
                 cwd=str(self.root), steps=["yes '1234567890' | head -n 1000"],
                 limit_mode='head', mode='sync', timeout=5),
            dict(name='marker', level='read', doc='marker', params={}, cwd=str(self.root),
                 steps=['touch marker'], mode='sync', timeout=5),
            dict(name='fail_output', level='read', doc='failure', params={}, cwd=str(self.root),
                 steps=["printf 'error\n'; exit 3"], mode='sync', timeout=5)])
        Path(os.environ['CMD_TABLE']).write_text(json.dumps(self.table))

    def restore(self):
        for key, value in self.old.items():
            if value is None: os.environ.pop(key, None)
            else: os.environ[key] = value

    def test_out_steps(self):
        cases = [([{'filter': '2'}], '2 b\n2 b\n'), ([{'exclude': '2'}], '1 a\n3 c\n'),
                 ([{'head': 1}], '2 b\n'), ([{'tail': 1}], '3 c\n'),
                 (['sort'], '1 a\n2 b\n2 b\n3 c\n'), ([{'sort': 'desc'}], '3 c\n2 b\n2 b\n1 a\n'),
                 ([{'sort': 'num'}], '1 a\n2 b\n2 b\n3 c\n'),
                 (['uniq'], '2 b\n1 a\n3 c\n'), ([{'uniq': 'count'}], '2\t2 b\n1\t1 a\n1\t3 c\n'),
                 ([{'field': 2, 'sep': ' '}], 'b\na\nb\nc\n'), (['count'], '4\n'),
                 ([{'field': 2}, {'uniq': 'count'}, {'sort': 'num_desc'}], '2\tb\n1\ta\n1\tc\n')]
        for out, expected in cases:
            with self.subTest(out=out): self.assertEqual(cmd.run('sample', {'out': out})['output'], expected)

    def test_limits_and_truncation(self):
        self.assertEqual(cmd.run('large', {'out': ['count']})['output'], '1000\n')
        self.assertEqual(len(cmd.run('large')['output'].splitlines()), 2)
        self.assertTrue(cmd.run('sample', {'out': ['count']})['status'] == 'ok')
        command = next(c for c in self.table['commands'] if c['name'] == 'large')
        command.pop('limit_mode')
        Path(os.environ['CMD_TABLE']).write_text(json.dumps(self.table))
        result = cmd.run('large')
        self.assertTrue(result['truncated'])
        self.assertLessEqual(len(result['output']), 8000)
        self.assertIn('输出已截断', result['output'])
        self.assertEqual(cmd.run('large', {'out': ['count']})['output'], '1000\n')

    def test_rejection_and_failure(self):
        for out in [None, ['bad'], [{'head': 0}], ['count', 'sort'], ['sort'] * 9,
                    [{'field': 1, 'sep': ''}], [{'filter': 'x' * 201}]]:
            with self.subTest(out=out):
                self.assertEqual(cmd.run('marker', {'out': out})['status'], 'rejected')
                self.assertFalse((self.root / 'marker').exists())
        self.assertEqual(cmd.run('run_test', {'out': []})['status'], 'rejected')
        result = cmd.run('fail_output', {'out': [{'filter': 'missing'}]})
        self.assertEqual((result['status'], result['output']), ('failed', 'error\n'))
        for action in ('start', 'status'):
            self.assertEqual(cmd.run('job', {'action': action, 'out': []})['status'], 'rejected')
        result = cmd.run('job', {'action': 'start', 'command': 'marker', 'args': {'out': []}})
        self.assertIn('result', result['reason'])
        jid = cmd.run('job', {'action': 'start', 'command': 'sample'})['job']
        for _ in range(150):
            result = cmd.run('job', {'action': 'result', 'job': jid, 'out': ['count']})
            if result['status'] != 'running': break
            time.sleep(.02)
        self.assertEqual(result['output'], '4\n')

    def test_descriptions(self):
        listing = cmd.describe_as('small_model')
        for command in cmd.list_as('small_model'):
            self.assertEqual(sum(line.startswith(command['name'] + '(') for line in listing.splitlines()), 1)
        self.assertNotIn('git_commit(', listing)
        lines = listing.splitlines()
        for line in ('test_report(path, case?, limit?) [write] ', 'locate(path, paths?, limit?) [write] ',
                     'probe(path, at, exprs, case?, limit?) [write] ', 'blame_change(path, case?, paths?, runs?) [write] '):
            self.assertEqual(sum(x.startswith(line) for x in lines), 1, line)
        self.assertEqual(len(lines), len(set(lines)))
        self.assertIn('max_items=8', cmd.describe_as('small_model', 'probe'))
        self.assertEqual(cmd.describe_as('nobody'), '')
        self.assertIn('roots=', cmd.describe_as('small_model', 'show'))
        self.assertIn('pattern=', cmd.describe_as('small_model', 'grep'))


class ExperimentCommandsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.old = {key: os.environ.get(key) for key in ('CMD_TABLE', 'CMD_HOME', 'CMD_EXPROBOT_HOME')}
        self.addCleanup(self.restore)
        os.environ.pop('CMD_TABLE', None)
        os.environ['CMD_HOME'] = str(Path(self.tmp.name) / 'cmd')
        os.environ['CMD_EXPROBOT_HOME'] = str(Path(self.tmp.name) / 'exp')
        f = tempfile.NamedTemporaryFile(prefix='cmd_exp_test_', suffix='.py', dir=cmd.ROOT / 'data/tmp', delete=False, mode='w')
        self.script = Path(f.name)
        self.result = self.script.with_suffix('.json')
        self.addCleanup(self.script.unlink, missing_ok=True)
        self.addCleanup(self.result.unlink, missing_ok=True)
        f.write("import json, pathlib, sys, time\n"
                "p = pathlib.Path(sys.argv[1])\n"
                "if len(sys.argv) > 2: time.sleep(20)\n"
                "n = json.loads(p.read_text())['score'] + 1 if p.exists() else 1\n"
                "p.write_text(json.dumps({'score': n}))\n"
                "print('token=abc123456789012345')\n")
        f.close()
        self.relative_result = str(self.result.relative_to(cmd.ROOT))
        self.register_args = {'exp': 'demo', 'path': str(self.script), 'args': [self.relative_result], 'result': self.relative_result}

    def restore(self):
        for key, value in self.old.items():
            if value is None: os.environ.pop(key, None)
            else: os.environ[key] = value

    def call(self, name, args=None, caller='tool_call'):
        return cmd.run_as(caller, name, args or {})

    def ok(self, name, args=None, caller='tool_call'):
        result = self.call(name, args, caller)
        self.assertEqual(result['status'], 'ok', result)
        return result['output']

    def start(self):
        out = self.ok('exp_start', {'exp': 'demo'})
        match = re.search(r'^run: (demo-[0-9]+)$', out, re.M)
        self.assertIsNotNone(match, out)
        return match.group(1)

    def test_lifecycle_permissions_redaction_and_filter(self):
        self.ok('exp_register', self.register_args)
        one = self.start()
        self.assertIn('status: ok', self.ok('exp_wait', {'run': one, 'wait': 10}))
        output = self.ok('exp_results', {'run': one}, 'small_model')
        self.assertRegex(output, r'score\s+1')
        self.assertIn('token=[已隐藏]', output)
        self.assertNotIn('abc123456789012345', output)
        self.assertRegex(self.ok('exp_results', {'run': one, 'out': [{'filter': 'score'}]}), r'score\s+1')
        two = self.start()
        self.assertIn('status: ok', self.ok('exp_wait', {'run': two, 'wait': 10}, 'small_model'))
        comparison = self.ok('exp_compare', {'run': two, 'against': one}, 'small_model')
        self.assertRegex(comparison, r'score\s+1\s+2\s+\+1')
        self.assertIn(one, self.ok('exp_list', {}, 'small_model'))
        self.assertIn(two, self.ok('exp_list', {}, 'small_model'))
        self.assertIn('status: ok', self.ok('exp_status', {'run': two}, 'small_model'))
        for name, args in [('exp_start', {'exp': 'demo'}), ('exp_cancel', {'run': two}), ('exp_register', self.register_args)]:
            self.assertEqual(self.call(name, args, 'small_model')['status'], 'rejected')

    def test_start_returns_promptly_busy_and_cancel(self):
        args = dict(self.register_args, args=[self.relative_result, 'sleep'])
        self.ok('exp_register', args)
        start = time.monotonic()
        run = self.start()
        self.assertLess(time.monotonic() - start, 5)
        status = self.ok('exp_status', {'run': run})
        self.assertIn('status: running', status)
        self.assertIn('status: running', self.ok('exp_wait', {'run': run, 'wait': 1}))
        pid = int(re.search(r'^pid: (\d+)', status, re.M).group(1))
        busy = self.call('exp_start', {'exp': 'demo'})
        self.assertEqual(busy['status'], 'failed', busy)
        self.assertIn('EXPERIMENT_BUSY', busy['output'])
        self.assertIn('status: cancelled', self.ok('exp_cancel', {'run': run}))
        stat = Path(f'/proc/{pid}/stat')
        self.assertTrue(not stat.exists() or stat.read_text().split()[2] == 'Z')

    def test_register_rejects_invalid_inputs(self):
        for bad in [{'path': 'tools/cmd.py'}, {'args': ['bad arg']}, {'args': ['bad;arg']},
                    {'result': 'data/tmp/../outside.json'}, {'exp': 'Invalid'}]:
            with self.subTest(bad=bad):
                result = self.call('exp_register', dict(self.register_args, **bad))
                self.assertEqual(result['status'], 'rejected', result)
        self.assertNotIn('demo', self.ok('exp_list'))


if __name__ == '__main__':
    unittest.main()
