"""kfinish：K 任务收尾机器人（第 1 批：打包 → 隔离验证 → 上线 → 线上探测）。

模型一次调用传结构化参数，机器人用 planbot（htnbot/planbot，HTN 规划执行）按 tools/kfinish_domain 领域跑完各步，
只回一行 JSON。规格见 data/tmp/kfinish_spec.md。

用法：
  .venv/bin/python -m tools.kfinish <config.json>     # 或 - 从 stdin 读
  退出码：0 全部成功；1 某步失败（也输出正常 JSON）；2 参数错误。
Python：tools.kfinish.run(config: dict) -> dict（多一个键 exit_code 不会出现，用 exit_code_of(result) 取）。

可替换（测试注入）：systemctl_show(unit) -> dict、http_get(url, timeout) -> int|None、PROBE_PYTHON、
以及等待时长 VERIFY_START_WAIT / STOP_WAIT / PROD_GET_WAIT。

安全：子进程一律列表参数、shell=False、独立进程组、有超时，超时按进程组杀；不用 pkill/killall；
init_data 的输出不落盘、口令不进任何输出；只读 git；allow 不是 true 绝不调用真上线（代码里硬检查）。
"""
import glob
import hashlib
import json
import os
import re
import secrets
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT / 'htnbot') not in sys.path:
    sys.path.insert(0, str(_ROOT / 'htnbot'))
from planbot import core, executor, planner  # noqa: E402

DOMAIN = str(_ROOT / 'tools/kfinish_domain/domain.json')
CALLBACKS = str(_ROOT / 'tools/kfinish_domain/callbacks.py')

DEFAULT_PYTHON = '/root/.local/share/uv/python/cpython-3.13.18-linux-x86_64-gnu/bin/python3.13'
PROBE_PYTHON = str(_ROOT / '.venv/bin/python')
PYPI_INDEX = 'https://pypi.org/simple'
PROD_PORT = 8119
STEPS = ('pack', 'verify', 'deploy')
LANGS = ('zh', 'ja')
GIT_PATHS = ('kg_v4', 'gen', 'tools', 'verbs', 'templates', 'scripts', 'content')

VERIFY_START_WAIT = 90
STOP_WAIT = 10
PROD_GET_WAIT = 60
REPORT_MAX_LINES = 15


class BadConfig(Exception):
    pass


# ---------------------------------------------------------------- 子进程

def _killpg(pid, sig=signal.SIGTERM):
    try:
        os.killpg(pid, sig)
    except (ProcessLookupError, PermissionError):
        pass


def _stop_group(proc):
    _killpg(proc.pid, signal.SIGTERM)
    try:
        proc.wait(5)
    except subprocess.TimeoutExpired:
        _killpg(proc.pid, signal.SIGKILL)
        proc.wait()


def _run(argv, cwd, env=None, timeout=60, log=None):
    """跑一条命令，输出写到 log（None 则丢到 DEVNULL）。返回退出码；超时返回 124（整个进程组已杀）。"""
    out = open(log, 'ab') if log else subprocess.DEVNULL
    try:
        try:
            proc = subprocess.Popen(list(argv), cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=out,
                                    stderr=subprocess.STDOUT, start_new_session=True, shell=False)
        except OSError as exc:
            if log:
                out.write(f'\n[kfinish] 启动失败：{exc}\n'.encode())
            return 127
        try:
            return proc.wait(timeout)
        except subprocess.TimeoutExpired:
            _stop_group(proc)
            if log:
                out.write(f'\n[kfinish] 超时 {timeout} 秒，已按进程组杀掉\n'.encode())
            return 124
    finally:
        if log:
            out.close()


def _capture(argv, cwd=None, timeout=60, env=None):
    """跑一条只读命令取 stdout。返回 (退出码, stdout)。"""
    try:
        proc = subprocess.Popen(list(argv), cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, start_new_session=True, shell=False)
    except OSError as exc:
        return 127, str(exc)
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _stop_group(proc)
        return 124, ''
    return proc.returncode, out.decode('utf-8', 'replace')


def _tail(path, n):
    try:
        lines = Path(path).read_text(encoding='utf-8', errors='replace').splitlines()
    except OSError:
        return ''
    return '\n'.join(lines[-n:])


def _base_env():
    env = dict(os.environ)
    env.pop('KG_PASSWORD', None)
    return env


# ---------------------------------------------------------------- 可替换的外部探测

def http_get(url, timeout=5):
    """GET，返回状态码；连不上返回 None。不走代理。"""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url, timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except Exception:
        return None


def systemctl_show(unit):
    """只读：systemctl show <unit> -p MainPID -p ActiveState -p NRestarts。"""
    rc, out = _capture(['systemctl', 'show', unit, '-p', 'MainPID', '-p', 'ActiveState', '-p', 'NRestarts'],
                       timeout=30)
    if rc != 0:
        return {'error': f'systemctl show 退出码 {rc}'}
    info = {}
    for line in out.splitlines():
        key, sep, value = line.partition('=')
        if sep:
            info[key.strip()] = value.strip()
    for key in ('MainPID', 'NRestarts'):
        if key in info:
            try:
                info[key] = int(info[key])
            except ValueError:
                pass
    return info


def _listening(port):
    try:
        with socket.create_connection(('127.0.0.1', int(port)), timeout=0.5):
            return True
    except OSError:
        return False


def _wait_not_listening(port, seconds):
    deadline = time.monotonic() + seconds
    while True:
        if not _listening(port):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.5)


# ---------------------------------------------------------------- 只杀工作目录下的进程

def _proc_cwd(pid):
    try:
        return os.readlink(f'/proc/{pid}/cwd')
    except OSError:
        return None


def _proc_pgid(pid):
    try:
        text = Path(f'/proc/{pid}/stat').read_text()
        return int(text[text.rindex(')') + 2:].split()[2])
    except (OSError, ValueError, IndexError):
        return None


def _all_pids():
    return [int(name) for name in os.listdir('/proc') if name.isdigit()]


def _pids_under(root):
    root = os.path.realpath(root)
    me = os.getpid()
    found = []
    for pid in _all_pids():
        if pid == me:
            continue
        cwd = _proc_cwd(pid)
        if cwd and (cwd == root or cwd.startswith(root + os.sep)):
            found.append(pid)
    return found


def _signal_under(root, sig):
    """给 cwd 在 root 之下的进程发信号：整个进程组都在 root 之下就按组发，否则只发给这些进程本身。"""
    pids = set(_pids_under(root))
    if not pids:
        return 0
    mine = os.getpgrp()
    groups = {}
    for pid in pids:
        pgid = _proc_pgid(pid)
        if pgid is not None:
            groups.setdefault(pgid, set()).add(pid)
    members = {}
    for pid in _all_pids():
        pgid = _proc_pgid(pid)
        if pgid in groups:
            members.setdefault(pgid, set()).add(pid)
    for pgid, inside in groups.items():
        try:
            if pgid != mine and members.get(pgid, set()) <= inside:
                os.killpg(pgid, sig)
            else:
                for pid in inside:
                    os.kill(pid, sig)
        except (ProcessLookupError, PermissionError):
            pass
    return len(pids)


def _kill_under(root):
    n = _signal_under(root, signal.SIGTERM)
    if not n:
        return 0
    deadline = time.monotonic() + 3
    while _pids_under(root) and time.monotonic() < deadline:
        time.sleep(0.2)
    if _pids_under(root):
        _signal_under(root, signal.SIGKILL)
        time.sleep(0.5)
    return n


# ---------------------------------------------------------------- 状态

def _state_path(state_dir):
    return os.path.join(state_dir, 'state.json')


def load_state(state_dir):
    with open(_state_path(state_dir), encoding='utf-8') as f:
        return json.load(f)


def save_state(state_dir, st):
    tmp = _state_path(state_dir) + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(st, f, ensure_ascii=False, indent=1)
    os.replace(tmp, _state_path(state_dir))


def state_facts(state_dir):
    st = load_state(state_dir)
    cfg = st['config']
    facts = [f'lang({lang})' for lang in cfg['langs']]
    for step in cfg['steps']:
        facts.append(f'want_{step}()')
    if 'deploy' in cfg['steps'] and cfg['deploy'].get('allow') is True:
        facts.append('deploy_allowed()')
    for lang, p in st['pack'].items():
        if p.get('ok'):
            facts.append(f'packed({lang})')
        if p.get('wheels_zero'):
            facts.append(f'wheels_zero({lang})')
        if p.get('index_retried'):
            facts.append(f'index_retried({lang})')
        if p.get('failed'):
            facts.append(f'pack_failed({lang})')
    for lang, v in st['verify'].items():
        if v.get('ok'):
            facts.append(f'verified({lang})')
        elif v.get('ok') is False:
            facts.append(f'verify_failed({lang})')
    d = st['deploy']
    if d.get('dry_run') == 0:
        facts.append('dryrun_ok()')
    if d.get('deployed'):
        facts.append('deployed()')
    if d.get('prod_ok'):
        facts.append('prod_checked()')
    return facts


def run_step(state_dir, name, lang=None):
    """动作回调的入口：读状态 → 跑原语 → 存状态。原语出意外也记进状态再抛出（动作失败）。"""
    st = load_state(state_dir)
    key = f'{name}({lang or ""})'
    attempts = st.setdefault('attempts', {})
    attempts[key] = attempts.get(key, 0) + 1
    save_state(state_dir, st)
    try:
        if name == 'pack':
            _pack(st, state_dir, lang)
        elif name == 'repack_index':
            _pack(st, state_dir, lang, index=PYPI_INDEX, retry=True)
        elif name == 'verify':
            _verify(st, state_dir, lang)
        elif name == 'deploy_dryrun':
            if attempts[key] > 1:
                raise RuntimeError('deploy_dryrun 已经跑过一次，不重复')
            _deploy_dryrun(st, state_dir)
        elif name == 'deploy':
            if attempts[key] > 1:
                raise RuntimeError('真上线已经尝试过一次，绝不重复')
            _deploy(st, state_dir)
        elif name == 'prod_check':
            if attempts[key] > 1:
                raise RuntimeError('上线后检查已经跑过一次')
            _prod_check(st, state_dir)
        else:
            raise RuntimeError(f'未知动作 {name}')
    except Exception as exc:
        msg = f'{key} 出错：{exc}'
        if name in ('pack', 'repack_index'):
            st['pack'].setdefault(lang, {}).update(ok=False, failed=True, reason=msg)
        elif name == 'verify':
            entry = st['verify'].setdefault(lang, {})
            entry.update(ok=False, reason=entry.get('reason') or msg)
        else:
            d = st['deploy']
            if not d.get('failed_step'):
                d.update(status='failed', failed_step=name, reason=msg)
        save_state(state_dir, st)
        raise
    save_state(state_dir, st)
    return None


# ---------------------------------------------------------------- pack

def _sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def _pack(st, state_dir, lang, index=None, retry=False):
    cfg = st['config']
    out = cfg['out'][lang].rstrip('/')
    index = index or cfg.get('pip_index')
    log = os.path.join(state_dir, f'pack_{lang}_index.log' if retry else f'pack_{lang}.log')
    p = st['pack'].setdefault(lang, {})
    if retry:
        p['index_retried'] = True
    env = _base_env()
    if index:
        env['PIP_INDEX_URL'] = index
    repo = cfg['repo']
    rc = _run(['bash', os.path.join(repo, 'scripts/build_bundle.sh'), '--lang', lang, out],
              cwd=repo, env=env, timeout=1800, log=log)
    p.update(log=log, rc=rc)
    if rc != 0:
        p.update(ok=False, failed=True,
                 reason=f'pack({lang}) 打包脚本退出码 {rc}，日志 {log}，最后 5 行：{_tail(log, 5)}')
        return
    wheels = len(glob.glob(os.path.join(out, 'wheels', '*.whl')))
    tgz = out + '.tar.gz'
    p.update(wheels=wheels, tgz=tgz)
    if wheels == 0:
        if retry:
            p.update(ok=False, failed=True, wheels_zero=True,
                     reason=f'pack({lang}) wheels 为 0（已换 pypi.org 源重试），看 {log}；检查网络或换可用的 pip_index')
        elif cfg.get('pip_index'):
            p.update(ok=False, failed=True, wheels_zero=True,
                     reason=f'pack({lang}) wheels 为 0（pip_index={cfg["pip_index"]}），看 {log}；换个源再试')
        else:
            p.update(ok=False, wheels_zero=True)
        return
    if not os.path.isfile(tgz):
        p.update(ok=False, failed=True, reason=f'pack({lang}) 打包脚本成功但没有 {tgz}，看 {log}')
        return
    p.update(ok=True, failed=False, wheels_zero=False, sha256=_sha256(tgz))


# ---------------------------------------------------------------- verify

def _count_logs(base):
    tb = h500 = 0
    for pattern in ('run/*.log', 'data/*.log'):
        for path in glob.glob(os.path.join(base, pattern)):
            try:
                text = Path(path).read_text(encoding='utf-8', errors='replace')
            except OSError:
                continue
            tb += text.count('Traceback')
            h500 += text.count('" 500 ')
    return tb, h500


def _integrity(db):
    if not os.path.isfile(db):
        return None
    try:
        con = sqlite3.connect(f'file:{urllib.parse.quote(db)}?mode=ro', uri=True)
        try:
            return str(con.execute('pragma integrity_check').fetchone()[0])
        finally:
            con.close()
    except sqlite3.Error as exc:
        return f'error: {exc}'


def _remove_auth_secrets(root):
    n = 0
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            if name == '.auth_secret':
                try:
                    os.unlink(os.path.join(dirpath, name))
                    n += 1
                except OSError:
                    pass
    return n


def _verify(st, state_dir, lang):
    cfg = st['config']
    port = cfg['port']
    tgz = st['pack'][lang]['tgz']
    url = f'http://127.0.0.1:{port}'
    v = {'ok': False, 'install': None, 'init': None, 'start': None, 'get': {}, 'integrity': None,
         'traceback': None, 'http500': None, 'extra_check': None, 'stopped': None}
    st['verify'][lang] = v
    problems = []
    if port == PROD_PORT or _listening(port):
        v['reason'] = f'verify({lang}) 端口 {port} 已被占用或是正式端口，什么都没启动'
        v['stopped'] = True
        return
    work = tempfile.mkdtemp(prefix=f'kfinish_{cfg["task"]}_{lang}_')
    v['workdir'] = work
    save_state(state_dir, st)
    base = None
    env = _base_env()
    env.update(PYTHON=cfg['python'], PORT=str(port))
    try:
        rc = _run(['tar', '-xzf', tgz, '-C', work], cwd=work, timeout=600,
                  log=os.path.join(state_dir, f'verify_{lang}_install.log'))
        tops = [n for n in os.listdir(work) if os.path.isdir(os.path.join(work, n))]
        if rc != 0 or len(tops) != 1:
            problems.append(f'解压 {tgz} 失败或顶层目录不唯一（tar 退出码 {rc}，顶层 {tops[:3]}）')
            return
        base = os.path.join(work, tops[0])
        log = os.path.join(state_dir, f'verify_{lang}_install.log')
        v['install'] = _run(['bash', 'scripts/install.sh'], cwd=base, env=env, timeout=900, log=log)
        if v['install'] != 0:
            problems.append(f'install.sh 退出码 {v["install"]}，看 {log}：{_tail(log, 3)}')
            return
        init_env = dict(env, KG_PASSWORD=secrets.token_urlsafe(16))
        v['init'] = _run(['bash', 'scripts/init_data.sh'], cwd=base, env=init_env, timeout=600, log=None)
        del init_env
        if v['init'] != 0:
            problems.append(f'init_data.sh 退出码 {v["init"]}（输出不落盘）')
            return
        log = os.path.join(state_dir, f'verify_{lang}_start.log')
        v['start'] = _run(['bash', 'scripts/start.sh'], cwd=base, env=env, timeout=180, log=log)
        if v['start'] != 0:
            problems.append(f'start.sh 退出码 {v["start"]}，看 {log}')
            return
        deadline = time.monotonic() + VERIFY_START_WAIT
        code = None
        while True:
            code = http_get(url + '/', 3)
            if code == 200 or time.monotonic() >= deadline:
                break
            time.sleep(1)
        v['get']['/'] = code
        for probe in cfg['probes']:
            path = probe if probe.startswith('/') else '/' + probe
            if path != '/':
                v['get'][path] = http_get(url + path, 10)
        bad = {k: c for k, c in v['get'].items() if c != 200}
        if bad:
            problems.append('GET 不是 200：' + '，'.join(f'{k}={c}' for k, c in bad.items()))
        v['integrity'] = _integrity(os.path.join(base, 'data', 'app.db'))
        if v['integrity'] not in (None, 'ok'):
            problems.append(f'integrity_check={v["integrity"]}')
        v['traceback'], v['http500'] = _count_logs(base)
        if v['traceback'] or v['http500']:
            problems.append(f'日志里 Traceback {v["traceback"]} 次、" 500 " {v["http500"]} 次（包内 run/*.log、data/*.log）')
        if cfg.get('extra_check'):
            log = os.path.join(state_dir, f'verify_{lang}_extra.log')
            rc = _run([cfg['python'], '-I', cfg['extra_check'], base, url], cwd=base, env=env, timeout=300, log=log)
            v['extra_check'] = {'rc': rc, 'tail': _tail(log, 20)[-1500:]}
            if rc != 0:
                problems.append(f'extra_check 退出码 {rc}，看 {log}')
    except Exception as exc:
        problems.append(f'意外：{exc}')
    finally:
        if base and os.path.isfile(os.path.join(base, 'scripts', 'stop.sh')):
            _run(['bash', 'scripts/stop.sh'], cwd=base, env=env, timeout=60,
                 log=os.path.join(state_dir, f'verify_{lang}_stop.log'))
        stopped = _wait_not_listening(port, STOP_WAIT)
        if not stopped or _pids_under(work):
            v['killed'] = _kill_under(work)
            stopped = _wait_not_listening(port, 5)
        v['stopped'] = stopped
        if not stopped:
            problems.append(f'停服后端口 {port} 仍在监听')
        v['auth_secret_removed'] = _remove_auth_secrets(work)
        shutil.rmtree(work, ignore_errors=True)
        v['workdir_removed'] = not os.path.exists(work)
        v['ok'] = not problems
        if problems:
            v['reason'] = f'verify({lang}) 不通过：' + '；'.join(problems) + f'（日志在 {state_dir}）'


# ---------------------------------------------------------------- deploy

def _table_counts(db):
    if not os.path.isfile(db):
        return None
    con = sqlite3.connect(f'file:{urllib.parse.quote(db)}?mode=ro', uri=True)
    try:
        names = [r[0] for r in con.execute(
            "select name from sqlite_master where type='table' and name not like 'sqlite_%' order by name")]
        return {n: con.execute('select count(*) from "%s"' % n.replace('"', '""')).fetchone()[0] for n in names}
    finally:
        con.close()


def _counts_diff(before, after):
    before, after = before or {}, after or {}
    diff = {}
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    rows = {t: [before[t], after[t]] for t in sorted(set(before) & set(after)) if before[t] != after[t]}
    if added:
        diff['tables_added'] = added
    if removed:
        diff['tables_removed'] = removed
    if rows:
        diff['rows'] = rows
    return diff


def _deploy_env(dep):
    env = _base_env()
    env['KG_SYSTEMD_UNIT'] = dep['unit']
    return env


def _deploy_dryrun(st, state_dir):
    cfg, d = st['config'], st['deploy']
    dep = cfg['deploy']
    d['before'] = systemctl_show(dep['unit'])
    db = os.path.join(dep['data_dir'], 'app.db')
    try:
        d['counts_before'] = _table_counts(db)
    except sqlite3.Error as exc:
        d['counts_before'] = None
        d['counts_error'] = str(exc)
    with open(os.path.join(state_dir, 'counts_before.json'), 'w', encoding='utf-8') as f:
        json.dump(d['counts_before'], f, ensure_ascii=False, indent=1)
    log = os.path.join(state_dir, 'deploy_dryrun.log')
    rc = _run(['bash', 'deploy.sh', '--dry-run', dep['commit'], cfg['task']], cwd=dep['run_dir'],
              env=_deploy_env(dep), timeout=600, log=log)
    d['dry_run'] = rc
    if rc != 0:
        d.update(status='failed', failed_step='deploy_dryrun',
                 reason=f'deploy.sh --dry-run 退出码 {rc}，看 {log}：{_tail(log, 5)}')
    else:
        d['status'] = 'dry_run_only'


def _deploy(st, state_dir):
    cfg, d = st['config'], st['deploy']
    dep = cfg['deploy']
    if dep.get('allow') is not True:
        raise RuntimeError('deploy.allow 不是 true，拒绝真上线')
    if d.get('dry_run') != 0:
        raise RuntimeError('dry-run 没通过，拒绝真上线')
    log = os.path.join(state_dir, 'deploy.log')
    d['deploy_started'] = True
    save_state(state_dir, st)
    rc = _run(['bash', 'deploy.sh', dep['commit'], cfg['task']], cwd=dep['run_dir'],
              env=_deploy_env(dep), timeout=900, log=log)
    d['deploy_rc'] = rc
    if rc != 0:
        d.update(status='failed', failed_step='deploy',
                 reason=f'deploy.sh 退出码 {rc}，看 {log}：{_tail(log, 5)}；先看线上服务状态再决定是否回滚')
        return
    d['deployed'] = True


def _prod_check(st, state_dir):
    cfg, d = st['config'], st['deploy']
    dep = cfg['deploy']
    after = systemctl_show(dep['unit'])
    d['after'] = after
    before_pid = (d.get('before') or {}).get('MainPID')
    d['main_pid'] = [before_pid, after.get('MainPID')]
    d['active'] = after.get('ActiveState')
    problems = []
    if not after.get('MainPID') or after.get('MainPID') == before_pid:
        problems.append(f'MainPID 没变（{before_pid} → {after.get("MainPID")}）')
    if d['active'] != 'active':
        problems.append(f'ActiveState={d["active"]}')
    url = dep['url'].rstrip('/')
    deadline = time.monotonic() + PROD_GET_WAIT
    while True:
        code = http_get(url + '/', 5)
        if code == 200 or time.monotonic() >= deadline:
            break
        time.sleep(2)
    d['get'] = code
    if code != 200:
        problems.append(f'GET {url}/ = {code}')
    if dep.get('probe'):
        log = os.path.join(state_dir, 'prod_probe.log')
        rc = _run([PROBE_PYTHON, '-I', dep['probe'], dep['data_dir'], dep['url']], cwd=state_dir,
                  timeout=600, log=log)
        d['probe'] = {'rc': rc, 'tail': _tail(log, 20)[-1500:]}
        if rc != 0:
            problems.append(f'探测脚本退出码 {rc}，看 {log}')
    try:
        d['counts_after'] = _table_counts(os.path.join(dep['data_dir'], 'app.db'))
    except sqlite3.Error as exc:
        d['counts_after'] = None
        problems.append(f'上线后读行数失败：{exc}')
    with open(os.path.join(state_dir, 'counts_after.json'), 'w', encoding='utf-8') as f:
        json.dump(d['counts_after'], f, ensure_ascii=False, indent=1)
    d['counts_diff'] = _counts_diff(d.get('counts_before'), d['counts_after'])
    if problems:
        d.update(status='failed', failed_step='prod_check',
                 reason='已上线，但上线后检查不通过：' + '；'.join(problems) + '；先看服务日志，必要时回滚')
        return
    d.update(status='deployed', prod_ok=True)


# ---------------------------------------------------------------- 配置

def _git_head(repo):
    rc, out = _capture(['git', '-C', repo, 'rev-parse', 'HEAD'], timeout=30)
    head = out.strip()
    return head if rc == 0 and re.fullmatch(r'[0-9a-f]{40}', head) else None


def _not_in_bundle(repo):
    rc, out = _capture(['git', '-C', repo, 'status', '--porcelain', '--', *GIT_PATHS], timeout=60)
    if rc != 0:
        return []
    paths = []
    for line in out.splitlines():
        if len(line) > 3:
            path = line[3:]
            if ' -> ' in path:
                path = path.split(' -> ', 1)[1]
            paths.append(path.strip('"'))
    return paths


def normalize(config):
    if not isinstance(config, dict):
        raise BadConfig('配置必须是 JSON 对象')
    task = config.get('task')
    if not isinstance(task, str) or not re.fullmatch(r'K\d+[A-Za-z0-9_]*', task):
        raise BadConfig('task 必填，形如 K197')
    steps = config.get('steps')
    if not isinstance(steps, list) or not steps or any(s not in STEPS for s in steps):
        raise BadConfig('steps 必填，是 pack/verify/deploy 的非空子集')
    steps = [s for s in STEPS if s in steps]
    langs = config.get('langs', list(LANGS))
    if not isinstance(langs, list) or not langs or any(lang not in LANGS for lang in langs):
        raise BadConfig('langs 只能是 zh/ja 的非空子集')
    langs = list(dict.fromkeys(langs))
    repo = config.get('repo')
    if not isinstance(repo, str) or not os.path.isdir(repo):
        raise BadConfig('repo 必填，且要是存在的目录')
    repo = os.path.abspath(repo)
    head = _git_head(repo)
    if head is None:
        raise BadConfig(f'repo 不是 git 仓库或取不到 HEAD：{repo}')
    python = config.get('python') or DEFAULT_PYTHON
    if not os.path.isfile(python):
        raise BadConfig(f'python 不存在：{python}')
    out = {'zh': '/workspace/dslagent_exp/kg_v4_bundle', 'ja': f'/workspace/dslagent_exp/kg_v4_bundle_ja_{task}'}
    given = config.get('out') or {}
    if not isinstance(given, dict):
        raise BadConfig('out 必须是 {语言: 目录}')
    for lang, path in given.items():
        if lang in LANGS:
            if not isinstance(path, str) or not path:
                raise BadConfig(f'out.{lang} 必须是目录路径')
            out[lang] = os.path.abspath(path)
    probes = config.get('probes', ['/'])
    if not isinstance(probes, list) or any(not isinstance(p, str) for p in probes):
        raise BadConfig('probes 必须是路径列表')
    port = config.get('port')
    if 'verify' in steps:
        if type(port) is not int or not 0 < port < 65536:
            raise BadConfig('verify 需要 port（整数）')
        if port == PROD_PORT:
            raise BadConfig(f'port 不能是正式端口 {PROD_PORT}')
        if _listening(port):
            raise BadConfig(f'端口 {port} 已被占用，没有启动任何东西')
        if 'pack' not in steps:
            for lang in langs:
                if not os.path.isfile(out[lang].rstrip('/') + '.tar.gz'):
                    raise BadConfig(f'verify 需要先打好包：{out[lang]}.tar.gz 不存在（steps 里加 pack）')
    extra = config.get('extra_check')
    if extra is not None and (not isinstance(extra, str) or not os.path.isfile(extra)):
        raise BadConfig(f'extra_check 脚本不存在：{extra}')
    dep_in = config.get('deploy') or {}
    if not isinstance(dep_in, dict):
        raise BadConfig('deploy 必须是对象')
    dep = {'commit': dep_in.get('commit'), 'allow': dep_in.get('allow') is True,
           'unit': dep_in.get('unit') or 'ali-kg_v4.service',
           'run_dir': dep_in.get('run_dir') or '/workspace/dslagent_exp/kg_v4_run',
           'data_dir': dep_in.get('data_dir') or '/workspace/dslagent_exp/kg_v4_data',
           'url': dep_in.get('url') or f'http://127.0.0.1:{PROD_PORT}', 'probe': dep_in.get('probe')}
    if 'deploy' in steps:
        if not isinstance(dep['commit'], str) or not re.fullmatch(r'[0-9A-Za-z._/-]+', dep['commit']):
            raise BadConfig('deploy.commit 必填')
        if not os.path.isfile(os.path.join(dep['run_dir'], 'deploy.sh')):
            raise BadConfig(f'deploy.run_dir 下没有 deploy.sh：{dep["run_dir"]}')
        if dep['probe'] is not None and (not isinstance(dep['probe'], str) or not os.path.isfile(dep['probe'])):
            raise BadConfig(f'deploy.probe 脚本不存在：{dep["probe"]}')
    pip_index = config.get('pip_index')
    if pip_index is not None and not isinstance(pip_index, str):
        raise BadConfig('pip_index 必须是字符串或 null')
    state_dir = config.get('state_dir') or str(
        _ROOT / 'data/tmp/kfinish' / f'{task}-{time.strftime("%Y%m%d-%H%M%S")}')
    return {'task': task, 'repo': repo, 'head': head, 'steps': steps, 'langs': langs, 'out': out,
            'port': port, 'python': python, 'pip_index': pip_index, 'probes': probes, 'extra_check': extra,
            'deploy': dep, 'state_dir': os.path.abspath(state_dir)}


# ---------------------------------------------------------------- 入口

def _bad(config, msg):
    task = config.get('task') if isinstance(config, dict) else None
    return {'status': 'bad_config', 'task': task, 'head': None, 'failed_step': None, 'reason': msg,
            'not_in_bundle': [], 'pack': {}, 'verify': {}, 'deploy': None, 'state_dir': None,
            'report_md': f'### 打包与上线（kfinish）\n- 参数错误：{msg}'}


def exit_code_of(result):
    return {'ok': 0, 'failed': 1}.get(result.get('status'), 2)


def run(config):
    try:
        cfg = normalize(config)
    except BadConfig as exc:
        return _bad(config, str(exc))
    state_dir = cfg['state_dir']
    os.makedirs(state_dir, exist_ok=True)
    st = {'config': cfg, 'pack': {}, 'verify': {}, 'deploy': {}, 'attempts': {},
          'not_in_bundle': _not_in_bundle(cfg['repo']) if 'pack' in cfg['steps'] else []}
    if 'pack' not in cfg['steps']:
        for lang in cfg['langs']:
            tgz = cfg['out'][lang].rstrip('/') + '.tar.gz'
            if os.path.isfile(tgz):
                st['pack'][lang] = {'ok': True, 'prebuilt': True, 'tgz': tgz}
    save_state(state_dir, st)

    plan_status, plan_note = None, None
    try:
        mod = core.load_python(CALLBACKS)
        mod.bind(sys.modules[__name__])
        domain = core.load_domain(DOMAIN)
        allowed = planner.allowed_actions(domain, None, ['deploy'] if cfg['deploy']['allow'] is True else [])
        res = executor.execute_task(domain, ('finish',), allowed, memory=None, max_replans=12, cwd=state_dir)
        plan_status = res['status']
        stuck = res.get('stuck') or {}
        plan_note = stuck.get('step') or stuck.get('node')
        if stuck:
            plan_note = f'{plan_note}（{stuck.get("reason")}）'
    except Exception as exc:
        plan_status, plan_note = 'error', f'{type(exc).__name__}: {exc}'
    result = _result(load_state(state_dir), plan_status, plan_note)
    try:
        with open(os.path.join(state_dir, 'result.json'), 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=1)
    except OSError:
        pass
    return result


_PACK_KEYS = ('ok', 'wheels', 'tgz', 'sha256', 'index_retried')
_VERIFY_KEYS = ('ok', 'install', 'init', 'start', 'get', 'integrity', 'traceback', 'http500', 'extra_check',
                'stopped')
_DEPLOY_KEYS = ('status', 'dry_run', 'main_pid', 'active', 'get', 'probe', 'counts_diff')


def _result(st, plan_status, plan_note):
    cfg = st['config']
    state_dir = cfg['state_dir']
    failed_step = reason = None
    for lang in cfg['langs']:
        p = st['pack'].get(lang) or {}
        if p.get('failed') or (p.get('wheels_zero') and not p.get('ok')):
            failed_step, reason = f'pack({lang})', p.get('reason') or f'pack({lang}) wheels 为 0，看 {p.get("log")}'
            break
    if failed_step is None:
        for lang in cfg['langs']:
            v = st['verify'].get(lang) or {}
            if v.get('ok') is False:
                failed_step, reason = f'verify({lang})', v.get('reason')
                break
    d = st['deploy']
    if failed_step is None and d.get('status') == 'failed':
        failed_step, reason = d.get('failed_step') or 'deploy', d.get('reason')
    if failed_step is None and plan_status not in ('done', 'already_satisfied'):
        failed_step = plan_note or 'finish'
        reason = f'规划执行结果 {plan_status}：{plan_note}；看 {state_dir}/state.json'
    status = 'failed' if failed_step else 'ok'

    pack = {lang: {k: p.get(k, False if k in ('ok', 'index_retried') else None) for k in _PACK_KEYS}
            for lang, p in st['pack'].items()}
    verify = {lang: {k: v.get(k) for k in _VERIFY_KEYS} for lang, v in st['verify'].items()}
    deploy = None
    if 'deploy' in cfg['steps']:
        deploy = {k: d.get(k) for k in _DEPLOY_KEYS}
        if deploy['status'] is None:
            deploy['status'] = 'failed' if status == 'failed' else None
    # 主工作区脏的时候可能有几十个，给模型看的输出只留前 10 个，全量在 state.json
    nib = st.get('not_in_bundle') or []
    out = {'status': status, 'task': cfg['task'], 'head': cfg['head'], 'failed_step': failed_step,
           'reason': reason, 'not_in_bundle': nib[:10], 'not_in_bundle_count': len(nib),
           'pack': pack, 'verify': verify, 'deploy': deploy, 'state_dir': state_dir}
    out['report_md'] = _report_md(out)
    return out


def _report_md(r):
    lines = ['### 打包与上线（kfinish）',
             f'- {r["task"]} HEAD `{(r["head"] or "")[:12]}`，结果 **{r["status"]}**']
    nib = r['not_in_bundle']
    if nib:
        n = r.get('not_in_bundle_count', len(nib))
        lines.append(f'- 未提交改动不进包（{n} 个）：' + '、'.join(nib[:5]) + ('…' if n > 5 else ''))
    for lang, p in r['pack'].items():
        if p['ok']:
            lines.append(f'- 打包 {lang}：wheels {p["wheels"]}，`{p["tgz"]}` sha256 `{(p["sha256"] or "")[:16]}`'
                         + ('（换 pypi.org 源重打）' if p['index_retried'] else ''))
        else:
            lines.append(f'- 打包 {lang}：失败')
    for lang, v in r['verify'].items():
        gets = '，'.join(f'{k} {c}' for k, c in (v['get'] or {}).items())
        extra = f'，extra_check {v["extra_check"]["rc"]}' if v['extra_check'] else ''
        lines.append(f'- 隔离验证 {lang}：{"通过" if v["ok"] else "不通过"}（install/init/start '
                     f'{v["install"]}/{v["init"]}/{v["start"]}，GET {gets or "-"}，integrity {v["integrity"]}，'
                     f'Traceback {v["traceback"]}，500 {v["http500"]}{extra}，已停服 {v["stopped"]}）')
    d = r['deploy']
    if d:
        text = f'- 上线：{d["status"]}（dry-run 退出码 {d["dry_run"]}'
        if d.get('main_pid'):
            text += f'，MainPID {d["main_pid"][0]}→{d["main_pid"][1]}，{d["active"]}，GET / {d["get"]}'
        if d.get('probe'):
            text += f'，探测 {d["probe"]["rc"]}'
        if d.get('counts_diff'):
            text += f'，行数变化 {json.dumps(d["counts_diff"], ensure_ascii=False)[:200]}'
        lines.append(text + '）')
    if r['reason']:
        lines.append(f'- 失败于 {r["failed_step"]}：{r["reason"][:400]}')
    lines.append(f'- 日志：`{r["state_dir"]}`')
    lines = [' '.join(line.split('\n')) for line in lines]
    return '\n'.join(lines[:REPORT_MAX_LINES])


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(json.dumps(_bad({}, '用法：python -m tools.kfinish <config.json>|-'), ensure_ascii=False))
        return 2
    try:
        text = sys.stdin.read() if argv[0] == '-' else Path(argv[0]).read_text(encoding='utf-8')
        config = json.loads(text)
    except (OSError, ValueError) as exc:
        print(json.dumps(_bad({}, f'读不了配置：{exc}'), ensure_ascii=False))
        return 2
    result = run(config)
    print(json.dumps(result, ensure_ascii=False))
    return exit_code_of(result)


if __name__ == '__main__':
    sys.exit(main())
