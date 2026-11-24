# -*- coding: utf-8 -*-
"""tools/kfinish.py：打包 → 隔离验证 → 上线 → 探测 机器人（离线）。

    cd /workspace/agent_mcp && .venv/bin/python tests/tools/test_kfinish.py

全部用临时目录里的假东西：假仓库（真 git init + 一次提交，scripts/build_bundle.sh 是假脚本）、
假包（install/init_data/start/stop 四个脚本，start 用 python -m http.server 起在随机空闲端口）、
假 deploy 目录（deploy.sh 记录参数）、假 systemctl（PATH 里的脚本或注入的函数）。
不碰 8119、不碰 /workspace/dslagent_exp、不联网。
"""
import contextlib
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools import kfinish  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix='kfinish_test_'))
WORK_TMP = TMP / 'worktmp'
WORK_TMP.mkdir()
tempfile.tempdir = str(WORK_TMP)

FLAGS = ('FAKE_PACK_FAIL', 'FAKE_ZERO_NO_INDEX', 'FAKE_ZERO_ALWAYS', 'FAKE_STOP_FAIL', 'FAKE_TRACEBACK',
         'FAKE_PW_SINK', 'FAKE_DEPLOY_RC', 'PIP_INDEX_URL', 'KG_PASSWORD')
for _k in FLAGS:
    os.environ.pop(_k, None)

BUILD = r'''#!/usr/bin/env bash
set -eu
L=ja
if [ "${1:-}" = "--lang" ]; then L=$2; shift 2; fi
OUT=${1%/}
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
echo "build lang=$L out=$OUT index=${PIP_INDEX_URL:-}"
if [ -n "${FAKE_PACK_FAIL:-}" ]; then echo "boom: 打包坏了"; exit 3; fi
rm -rf "$OUT" "$OUT.tar.gz"
mkdir -p "$OUT/wheels" "$OUT/scripts"
if [ -n "${FAKE_ZERO_ALWAYS:-}" ] || { [ -n "${FAKE_ZERO_NO_INDEX:-}" ] && [ -z "${PIP_INDEX_URL:-}" ]; }; then
  echo "no wheels"
else
  touch "$OUT/wheels/a-1.0-py3-none-any.whl" "$OUT/wheels/b-1.0-py3-none-any.whl"
fi
cp "$HERE"/pkg/*.sh "$OUT/scripts/"
echo "$L" > "$OUT/LANG"
tar -czf "$OUT.tar.gz" -C "$(dirname "$OUT")" "$(basename "$OUT")"
echo done
'''

PKG = {
    'install.sh': '''#!/usr/bin/env bash
cd "$(dirname "$0")/.."
"$PYTHON" -c 'print("install ok")'
''',
    'init_data.sh': '''#!/usr/bin/env bash
cd "$(dirname "$0")/.."
mkdir -p data run
echo "admin password: $KG_PASSWORD"
echo "pw=$KG_PASSWORD" >&2
[ -z "${FAKE_PW_SINK:-}" ] || printf '%s' "$KG_PASSWORD" > "$FAKE_PW_SINK"
echo topsecret > data/.auth_secret
"$PYTHON" -c "import sqlite3; c=sqlite3.connect('data/app.db'); c.execute('create table t(x)'); c.commit()"
''',
    'start.sh': '''#!/usr/bin/env bash
cd "$(dirname "$0")/.."
mkdir -p run data
nohup "${PYTHON:-python3}" -m http.server "$PORT" --bind 127.0.0.1 > run/server.log 2>&1 &
echo $! > run/server.pid
[ -z "${FAKE_TRACEBACK:-}" ] || echo "Traceback (most recent call last):" >> data/app.log
echo started
''',
    'stop.sh': '''#!/usr/bin/env bash
cd "$(dirname "$0")/.."
if [ -n "${FAKE_STOP_FAIL:-}" ]; then echo "假装停了"; exit 0; fi
kill "$(cat run/server.pid)" 2>/dev/null || true
echo stopped
''',
}

DEPLOY = '''#!/usr/bin/env bash
echo "args=$* unit=$KG_SYSTEMD_UNIT" >> "$(dirname "$0")/calls.txt"
echo "deploy $*"
exit ${FAKE_DEPLOY_RC:-0}
'''

FAKE_SYSTEMCTL = '''#!/usr/bin/env bash
echo "$*" >> "$(dirname "$0")/systemctl_calls.txt"
case "$1" in show) echo "MainPID=4242"; echo "ActiveState=active"; echo "NRestarts=0";; *) exit 9;; esac
'''


def _write(path, text, mode=0o755):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    path.chmod(mode)
    return path


def _git(repo, *args):
    subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True,
                   env=dict(os.environ, GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@example.invalid',
                            GIT_COMMITTER_NAME='t', GIT_COMMITTER_EMAIL='t@example.invalid'))


def make_repo(name):
    repo = TMP / name
    _write(repo / 'scripts/build_bundle.sh', BUILD)
    for fname, text in PKG.items():
        _write(repo / 'scripts/pkg' / fname, text)
    _write(repo / 'tools/x.py', 'x = 1\n', 0o644)
    _write(repo / 'README.md', 'r\n', 0o644)
    _git(repo, 'init', '-q')
    _git(repo, 'add', '-A')
    _git(repo, 'commit', '-q', '-m', 'init')
    return repo


def make_deploy_dir(name):
    run_dir = TMP / name / 'run'
    data_dir = TMP / name / 'data'
    _write(run_dir / 'deploy.sh', DEPLOY)
    data_dir.mkdir(parents=True)
    con = sqlite3.connect(data_dir / 'app.db')
    con.execute('create table t(x)')
    con.execute('insert into t values (1)')
    con.commit()
    con.close()
    return run_dir, data_dir


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        port = s.getsockname()[1]
    assert port != 8119
    return port


@contextlib.contextmanager
def env(**values):
    old = {k: os.environ.get(k) for k in values}
    os.environ.update({k: str(v) for k, v in values.items()})
    try:
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


@contextlib.contextmanager
def patched(**attrs):
    old = {k: getattr(kfinish, k) for k in attrs}
    for k, v in attrs.items():
        setattr(kfinish, k, v)
    try:
        yield
    finally:
        for k, v in old.items():
            setattr(kfinish, k, v)


def fake_systemctl_fn(seq):
    calls = []

    def show(unit):
        calls.append(unit)
        return dict(seq[min(len(calls) - 1, len(seq) - 1)])
    show.calls = calls
    return show


def real_or(prod_url, code):
    real = kfinish.http_get

    def get(url, timeout=5):
        if url.startswith(prod_url):
            return code
        return real(url, timeout)
    return get


_counter = [0]


def config(repo, steps, **extra):
    _counter[0] += 1
    n = _counter[0]
    cfg = {'task': 'K900', 'repo': str(repo), 'steps': steps, 'langs': ['zh'],
           'out': {'zh': str(TMP / f'out{n}/kg_v4_bundle'), 'ja': str(TMP / f'out{n}/kg_v4_bundle_ja_K900')},
           'python': sys.executable, 'state_dir': str(TMP / f'state{n}')}
    if 'verify' in steps:
        cfg['port'] = free_port()
    cfg.update(extra)
    return cfg


def check_shape(tc, res):
    line = json.dumps(res, ensure_ascii=False)
    tc.assertNotIn('\n', line)
    tc.assertLessEqual(len(res['report_md'].split('\n')), 15)
    tc.assertTrue(res['report_md'].startswith('### 打包与上线（kfinish）'))


def leftover_workdirs():
    return [p for p in WORK_TMP.iterdir() if p.name.startswith('kfinish_')]


class KfinishTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo = make_repo('repo')
        kfinish.STOP_WAIT = 2

    def setUp(self):
        self.assertEqual(leftover_workdirs(), [])

    def tearDown(self):
        self.assertEqual(leftover_workdirs(), [], '隔离验证的工作目录没删掉')

    # ---------------- 正常全流程（命令行，一行 JSON）
    def test_full_flow_cli(self):
        run_dir, data_dir = make_deploy_dir('dep_cli')
        bin_dir = _write(TMP / 'bin/systemctl', FAKE_SYSTEMCTL).parent
        cfg = config(self.repo, ['pack', 'verify', 'deploy'], langs=['zh', 'ja'],
                     deploy={'commit': 'abc1234', 'allow': False, 'unit': 'fake-kg.service',
                             'run_dir': str(run_dir), 'data_dir': str(data_dir), 'url': 'http://127.0.0.1:1'})
        path = _write(TMP / 'cfg_cli.json', json.dumps(cfg), 0o644)
        e = dict(os.environ, PATH=f'{bin_dir}:{os.environ["PATH"]}', TMPDIR=str(WORK_TMP))
        done = subprocess.run([sys.executable, '-m', 'tools.kfinish', str(path)], cwd=str(ROOT), env=e,
                              capture_output=True, text=True, timeout=300)
        lines = done.stdout.strip('\n').split('\n')
        self.assertEqual(len(lines), 1, done.stdout + done.stderr)
        res = json.loads(lines[0])
        self.assertEqual(done.returncode, 0, lines[0])
        self.assertEqual(res['status'], 'ok', res['reason'])
        check_shape(self, res)
        self.assertRegex(res['head'], r'^[0-9a-f]{40}$')
        for lang in ('zh', 'ja'):
            self.assertTrue(res['pack'][lang]['ok'])
            self.assertEqual(res['pack'][lang]['wheels'], 2)
            self.assertRegex(res['pack'][lang]['sha256'], r'^[0-9a-f]{64}$')
            v = res['verify'][lang]
            self.assertTrue(v['ok'], v)
            self.assertEqual((v['install'], v['init'], v['start']), (0, 0, 0))
            self.assertEqual(v['get'], {'/': 200})
            self.assertEqual(v['integrity'], 'ok')
            self.assertEqual((v['traceback'], v['http500']), (0, 0))
            self.assertTrue(v['stopped'])
        self.assertFalse(kfinish._listening(cfg['port']))
        self.assertEqual(res['deploy']['status'], 'dry_run_only')
        self.assertEqual(res['deploy']['dry_run'], 0)
        calls = (run_dir / 'calls.txt').read_text().splitlines()
        self.assertEqual(calls, ['args=--dry-run abc1234 K900 unit=fake-kg.service'])
        sc = (bin_dir / 'systemctl_calls.txt').read_text().splitlines()
        self.assertTrue(all(c.startswith('show ') for c in sc), sc)
        self.assertTrue(os.path.isfile(os.path.join(res['state_dir'], 'counts_before.json')))

    # ---------------- 换源重打
    def test_wheels_zero_then_index_retry_ok(self):
        with env(FAKE_ZERO_NO_INDEX=1):
            res = kfinish.run(config(self.repo, ['pack']))
        check_shape(self, res)
        self.assertEqual(res['status'], 'ok', res['reason'])
        p = res['pack']['zh']
        self.assertTrue(p['ok'])
        self.assertTrue(p['index_retried'])
        self.assertEqual(p['wheels'], 2)
        log = Path(res['state_dir'], 'pack_zh_index.log').read_text()
        self.assertIn('index=https://pypi.org/simple', log)

    def test_wheels_zero_after_retry_fails(self):
        with env(FAKE_ZERO_ALWAYS=1):
            res = kfinish.run(config(self.repo, ['pack', 'verify']))
        check_shape(self, res)
        self.assertEqual(res['status'], 'failed')
        self.assertEqual(kfinish.exit_code_of(res), 1)
        self.assertEqual(res['failed_step'], 'pack(zh)')
        self.assertIn('wheels 为 0（已换 pypi.org 源重试）', res['reason'])
        self.assertIn('pack_zh_index.log', res['reason'])
        self.assertTrue(res['pack']['zh']['index_retried'])
        self.assertEqual(res['verify'], {})

    def test_wheels_zero_with_pip_index_no_retry(self):
        with env(FAKE_ZERO_ALWAYS=1):
            res = kfinish.run(config(self.repo, ['pack'], pip_index='http://mirror.invalid/simple'))
        self.assertEqual(res['status'], 'failed')
        self.assertFalse(res['pack']['zh']['index_retried'])
        self.assertIn('wheels 为 0', res['reason'])

    def test_pack_script_fails(self):
        with env(FAKE_PACK_FAIL=1):
            res = kfinish.run(config(self.repo, ['pack']))
        self.assertEqual(res['status'], 'failed')
        self.assertEqual(res['failed_step'], 'pack(zh)')
        self.assertIn('退出码 3', res['reason'])
        self.assertIn('boom: 打包坏了', res['reason'])

    # ---------------- 参数错误
    def test_port_in_use_bad_config(self):
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0))
            s.listen()
            cfg = config(self.repo, ['pack', 'verify'], port=s.getsockname()[1])
            res = kfinish.run(cfg)
        self.assertEqual(res['status'], 'bad_config')
        self.assertEqual(kfinish.exit_code_of(res), 2)
        self.assertIn('已被占用', res['reason'])
        self.assertFalse(os.path.exists(cfg['out']['zh']))
        self.assertFalse(os.path.exists(cfg['state_dir']))
        check_shape(self, res)

    def test_bad_configs(self):
        base = config(self.repo, ['pack', 'verify'])
        for patch in ({'port': 8119}, {'task': 'X1'}, {'steps': []}, {'steps': ['regress']},
                      {'python': '/nonexistent/python'}, {'repo': str(TMP)}, {'langs': ['en']}):
            res = kfinish.run(dict(base, **patch))
            self.assertEqual(res['status'], 'bad_config', patch)
        res = kfinish.run(config(self.repo, ['deploy'], deploy={'allow': False}))
        self.assertEqual(res['status'], 'bad_config')
        res = kfinish.run(config(self.repo, ['verify']))
        self.assertEqual(res['status'], 'bad_config')
        self.assertIn('tar.gz 不存在', res['reason'])

    def test_cli_bad_config_exit_2(self):
        done = subprocess.run([sys.executable, '-m', 'tools.kfinish', '-'], cwd=str(ROOT), input='{"task": "bad"}',
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 2)
        self.assertEqual(json.loads(done.stdout)['status'], 'bad_config')

    # ---------------- verify 失败仍收尾
    def test_get_fail_still_cleans_up(self):
        cfg = config(self.repo, ['pack', 'verify'], probes=['/', '/nope'])
        res = kfinish.run(cfg)
        check_shape(self, res)
        self.assertEqual(res['status'], 'failed')
        self.assertEqual(res['failed_step'], 'verify(zh)')
        v = res['verify']['zh']
        self.assertEqual(v['get'], {'/': 200, '/nope': 404})
        self.assertTrue(v['stopped'])
        self.assertIn('/nope=404', res['reason'])
        st = json.loads(Path(res['state_dir'], 'state.json').read_text())['verify']['zh']
        self.assertTrue(st['workdir_removed'])
        self.assertEqual(st['auth_secret_removed'], 1)
        self.assertFalse(os.path.exists(st['workdir']))
        self.assertFalse(kfinish._listening(cfg['port']))

    def test_traceback_in_log_fails(self):
        with env(FAKE_TRACEBACK=1):
            res = kfinish.run(config(self.repo, ['pack', 'verify']))
        self.assertEqual(res['status'], 'failed')
        self.assertEqual(res['verify']['zh']['traceback'], 1)
        self.assertTrue(res['verify']['zh']['stopped'])

    def test_stop_fails_kill_only_inside_workdir(self):
        outside_dir = TMP / 'outside'
        outside_dir.mkdir(exist_ok=True)
        outside = subprocess.Popen(['sleep', '120'], cwd=str(outside_dir), start_new_session=True)
        try:
            cfg = config(self.repo, ['pack', 'verify'])
            with env(FAKE_STOP_FAIL=1):
                res = kfinish.run(cfg)
            self.assertEqual(res['status'], 'ok', res['reason'])
            v = res['verify']['zh']
            self.assertTrue(v['stopped'])
            st = json.loads(Path(res['state_dir'], 'state.json').read_text())['verify']['zh']
            self.assertGreaterEqual(st['killed'], 1)
            self.assertFalse(kfinish._listening(cfg['port']))
            self.assertIsNone(outside.poll(), 'W 之外的进程被杀了')
        finally:
            outside.kill()
            outside.wait()

    def test_init_output_not_on_disk(self):
        sink = TMP / 'pw_sink.txt'
        with env(FAKE_PW_SINK=sink):
            res = kfinish.run(config(self.repo, ['pack', 'verify']))
        self.assertEqual(res['status'], 'ok', res['reason'])
        pw = sink.read_text()
        self.assertGreaterEqual(len(pw), 16)
        self.assertNotIn(pw, json.dumps(res, ensure_ascii=False))
        for path in Path(res['state_dir']).rglob('*'):
            if path.is_file():
                self.assertNotIn(pw, path.read_text(errors='replace'), str(path))
                self.assertNotIn('admin password', path.read_text(errors='replace'), str(path))
        sink.unlink()

    # ---------------- deploy
    def test_allow_false_never_deploys(self):
        run_dir, data_dir = make_deploy_dir('dep_false')
        show = fake_systemctl_fn([{'MainPID': 10, 'ActiveState': 'active', 'NRestarts': 0}])
        cfg = config(self.repo, ['deploy'], deploy={'commit': 'c0ffee1', 'allow': False, 'unit': 'u.service',
                                                     'run_dir': str(run_dir), 'data_dir': str(data_dir),
                                                     'url': 'http://prod.invalid'})
        with patched(systemctl_show=show, http_get=real_or('http://prod.invalid', 200)):
            res = kfinish.run(cfg)
        self.assertEqual(res['status'], 'ok', res['reason'])
        self.assertEqual(res['deploy']['status'], 'dry_run_only')
        self.assertEqual((run_dir / 'calls.txt').read_text().splitlines(),
                         ['args=--dry-run c0ffee1 K900 unit=u.service'])
        # 代码里的硬检查：直接调原语也不会真上线
        st = json.loads(Path(res['state_dir'], 'state.json').read_text())
        with self.assertRaises(RuntimeError):
            kfinish._deploy(st, res['state_dir'])
        self.assertEqual(len((run_dir / 'calls.txt').read_text().splitlines()), 1)
        self.assertEqual(json.loads(Path(res['state_dir'], 'counts_before.json').read_text()), {'t': 1})

    def test_allow_true_deploys_and_checks(self):
        run_dir, data_dir = make_deploy_dir('dep_true')
        probe = _write(TMP / 'probe.py', textwrap.dedent('''
            import sqlite3, sys
            c = sqlite3.connect(sys.argv[1] + '/app.db'); c.execute('insert into t values (2)'); c.commit()
            print('probe ok', sys.argv[2])
        '''), 0o644)
        show = fake_systemctl_fn([{'MainPID': 100, 'ActiveState': 'active', 'NRestarts': 0},
                                  {'MainPID': 200, 'ActiveState': 'active', 'NRestarts': 0}])
        cfg = config(self.repo, ['deploy'], deploy={'commit': 'c0ffee1', 'allow': True, 'unit': 'u.service',
                                                     'run_dir': str(run_dir), 'data_dir': str(data_dir),
                                                     'url': 'http://prod.invalid', 'probe': str(probe)})
        with patched(systemctl_show=show, http_get=real_or('http://prod.invalid', 200),
                     PROBE_PYTHON=sys.executable):
            res = kfinish.run(cfg)
        check_shape(self, res)
        self.assertEqual(res['status'], 'ok', res['reason'])
        d = res['deploy']
        self.assertEqual(d['status'], 'deployed')
        self.assertEqual(d['main_pid'], [100, 200])
        self.assertEqual(d['active'], 'active')
        self.assertEqual(d['get'], 200)
        self.assertEqual(d['probe']['rc'], 0)
        self.assertIn('probe ok http://prod.invalid', d['probe']['tail'])
        self.assertEqual(d['counts_diff'], {'rows': {'t': [1, 2]}})
        self.assertEqual((run_dir / 'calls.txt').read_text().splitlines(),
                         ['args=--dry-run c0ffee1 K900 unit=u.service', 'args=c0ffee1 K900 unit=u.service'])
        self.assertEqual(show.calls, ['u.service', 'u.service'])

    def test_allow_true_deploy_fails_not_retried(self):
        run_dir, data_dir = make_deploy_dir('dep_fail')
        show = fake_systemctl_fn([{'MainPID': 100, 'ActiveState': 'active'}])
        _write(run_dir / 'deploy.sh', DEPLOY.replace('exit ${FAKE_DEPLOY_RC:-0}',
                                                     '[ "$1" = "--dry-run" ] && exit 0; exit 5'))
        cfg = config(self.repo, ['deploy'], deploy={'commit': 'c0ffee1', 'allow': True, 'unit': 'u.service',
                                                     'run_dir': str(run_dir), 'data_dir': str(data_dir),
                                                     'url': 'http://prod.invalid'})
        with patched(systemctl_show=show, http_get=real_or('http://prod.invalid', 200)):
            res = kfinish.run(cfg)
        self.assertEqual(res['status'], 'failed')
        self.assertEqual(res['failed_step'], 'deploy')
        self.assertEqual(res['deploy']['status'], 'failed')
        self.assertIn('退出码 5', res['reason'])
        self.assertEqual(len((run_dir / 'calls.txt').read_text().splitlines()), 2)

    def test_prod_check_pid_unchanged_fails(self):
        run_dir, data_dir = make_deploy_dir('dep_pid')
        show = fake_systemctl_fn([{'MainPID': 100, 'ActiveState': 'active'}])
        cfg = config(self.repo, ['deploy'], deploy={'commit': 'c0ffee1', 'allow': True, 'unit': 'u.service',
                                                     'run_dir': str(run_dir), 'data_dir': str(data_dir),
                                                     'url': 'http://prod.invalid'})
        with patched(systemctl_show=show, http_get=real_or('http://prod.invalid', 200)):
            res = kfinish.run(cfg)
        self.assertEqual(res['status'], 'failed')
        self.assertEqual(res['failed_step'], 'prod_check')
        self.assertIn('MainPID 没变', res['reason'])

    # ---------------- not_in_bundle
    def test_not_in_bundle(self):
        repo = make_repo('repo_dirty')
        (repo / 'tools/x.py').write_text('x = 2\n')
        _write(repo / 'kg_v4/new.zs', 'new\n', 0o644)
        (repo / 'README.md').write_text('changed\n')
        res = kfinish.run(config(repo, ['pack']))
        self.assertEqual(res['status'], 'ok', res['reason'])
        self.assertIn('tools/x.py', res['not_in_bundle'])
        self.assertIn('kg_v4/', res['not_in_bundle'])   # 未跟踪目录 git status 折叠成目录名
        self.assertNotIn('README.md', res['not_in_bundle'])
        self.assertIn('未提交改动不进包', res['report_md'])
        check_shape(self, res)


if __name__ == '__main__':
    try:
        unittest.main(verbosity=2)
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
