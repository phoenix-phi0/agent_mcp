# -*- coding: utf-8 -*-
"""固定指令执行器；指令及权限由只读配置表定义。"""
import builtins
import fnmatch
import fcntl
import json
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
TABLE = ROOT / 'tools/cmd_table.json'
_WORKERS = []


def _table():
    return json.loads(Path(os.environ.get('CMD_TABLE', TABLE)).read_text(encoding='utf-8'))


def _home():
    return Path(os.environ.get('CMD_HOME', ROOT / 'data/tmp/cmd')).resolve()


def _result(status, exit_code=None, output='', job=None, reason=''):
    return dict(status=status, exit_code=exit_code, output=output[-8000:], job=job, reason=reason)


def _command(table, name):
    return next((c for c in table['commands'] if c['name'] == name), None)


def _allowed(table, caller, command):
    policy = table.get('callers', {}).get(caller, {})
    return command['level'] in policy.get('levels', []) or command['name'] in policy.get('allow', [])


def _path(value, spec, cwd, name):
    if not isinstance(value, str) or not value or '\x00' in value:
        raise ValueError(f'{name}: expected nonempty path')
    p = Path(value)
    if '..' in p.parts:
        raise ValueError(f'{name}: .. is forbidden')
    resolved = (cwd / p).resolve()
    roots = [Path(x).resolve() for x in spec.get('roots', [str(cwd)])]
    if not any(resolved == root or root in resolved.parents for root in roots):
        raise ValueError(f'{name}: path must be under an allowed root')
    patterns = spec.get('glob', '*')
    if isinstance(patterns, str):
        patterns = [patterns]
    # glob is relative to cwd or an explicit root; ** also matches zero directories.
    candidates = []
    for root in roots:
        if resolved == root or root in resolved.parents:
            candidates.append(resolved.relative_to(root).as_posix())
    if not any(fnmatch.fnmatchcase(s, pattern) or
               ('**/' in pattern and fnmatch.fnmatchcase(s, pattern.replace('**/', '')))
               for s in candidates for pattern in patterns):
        raise ValueError(f'{name}: path must match {patterns}')
    return str(resolved)


def _validate(command, args):
    if not isinstance(args, dict):
        raise ValueError('args: expected object')
    specs = command.get('params', {})
    unknown = set(args) - set(specs)
    if unknown:
        raise ValueError(f'{sorted(unknown)[0]}: unknown parameter')
    cwd = Path(command['cwd']).resolve()
    values = {}
    for name, spec in specs.items():
        if name not in args:
            if 'default' in spec:
                value = spec['default']
            elif spec.get('required'):
                raise ValueError(f'{name}: required')
            else:
                continue
        else:
            value = args[name]
        typ = spec['type']
        if typ == 'path':
            value = _path(value, spec, cwd, name)
        elif typ == 'path_list':
            if not isinstance(value, builtins.list) or (spec.get('required') and not value):
                raise ValueError(f'{name}: expected {"nonempty " if spec.get("required") else ""}path list')
            value = [_path(v, spec, cwd, name) for v in value]
        elif typ == 'int':
            if type(value) is not int or value < spec.get('min', -sys.maxsize) or value > spec.get('max', sys.maxsize):
                raise ValueError(f'{name}: expected integer in {spec.get("min", "-∞")}..{spec.get("max", "∞")}')
        elif typ == 'enum':
            if value not in spec['values'] or not isinstance(value, str):
                raise ValueError(f'{name}: expected one of {spec["values"]}')
        elif typ == 'text':
            if not isinstance(value, str) or len(value) > spec.get('max_len', 8000) or '\x00' in value:
                raise ValueError(f'{name}: expected text max_len={spec.get("max_len", 8000)}')
            # 格式约束全写在指令表的 pattern 里，这里不认具体参数名
            if 'pattern' in spec and re.fullmatch(spec['pattern'], value) is None:
                raise ValueError(f'{name}: expected format {spec["pattern"]}')
        elif typ == 'bool':
            if type(value) is not bool:
                raise ValueError(f'{name}: expected bool')
        elif typ == 'object':
            if not isinstance(value, dict):
                raise ValueError(f'{name}: expected object')
        else:
            raise ValueError(f'{name}: unsupported type {typ}')
        values[name] = value
    return values


def _prepare(command, values):
    log = _home() / (command['name'] + '-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '-' + uuid.uuid4().hex[:8] + '.log')
    def quote(v):
        if isinstance(v, builtins.list):
            return ' '.join(shlex.quote(str(x)) for x in v)
        if isinstance(v, bool):
            return 'true' if v else 'false'
        return shlex.quote(str(v))
    fields = {k: quote(v) for k, v in values.items()}
    for k, spec in command.get('params', {}).items():
        fields.setdefault(k, 'false' if spec['type'] == 'bool' else "''")
    fields['log'] = shlex.quote(str(log))
    return [s.format_map(fields) for s in command['steps']]


def _execute(command, steps, timeout, full_output=False, job_directory=None):
    def result(status, exit_code=None, output="", reason=""):
        value = _result(status, exit_code, output, reason=reason)
        if full_output:
            value["output"] = output
        return value
    start = time.monotonic()
    chunks = []
    for step in steps:
        remaining = timeout - (time.monotonic() - start)
        if remaining <= 0:
            return result('failed', output=''.join(chunks), reason='timeout')
        try:
            if job_directory:
                with (job_directory / 'lock').open('a') as lock:
                    fcntl.flock(lock, fcntl.LOCK_EX)
                    p = subprocess.Popen(step, shell=True, cwd=command['cwd'], stdout=subprocess.PIPE,
                                         stderr=subprocess.STDOUT, start_new_session=True)
                    (job_directory / 'child_pid').write_text(str(p.pid))
            else:
                p = subprocess.Popen(step, shell=True, cwd=command['cwd'], stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, start_new_session=True)
            try:
                out, _ = p.communicate(timeout=remaining)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGKILL)
                out, _ = p.communicate()
                chunks.append(out.decode('utf-8', 'replace'))
                return result('failed', p.returncode, ''.join(chunks), reason='timeout')
        except OSError as e:
            return result('failed', output=''.join(chunks), reason=str(e))
        chunks.append(out.decode('utf-8', 'replace'))
        if p.returncode:
            return result('failed', p.returncode, ''.join(chunks))
    return result('ok', 0, ''.join(chunks))


def _job(table, caller, values):
    action = values['action']
    if action == 'start':
        name = values.get('command')
        command = _command(table, name)
        if not command or name == 'job':
            raise ValueError('command: unknown or invalid command')
        if not _allowed(table, caller, command):
            raise ValueError('command: caller is not permitted')
        args = _validate(command, values.get('args', {}))
        steps = _prepare(command, args)
        jid = uuid.uuid4().hex
        directory = _home() / 'jobs' / jid
        directory.mkdir(parents=True)
        (directory / 'meta.json').write_text(json.dumps({'caller': caller, 'command': name, 'definition': command, 'steps': steps, 'timeout': command.get('job_timeout', 3600), 'started': datetime.now(timezone.utc).isoformat()}), encoding='utf-8')
        (directory / 'output.log').touch()
        _WORKERS[:] = [p for p in _WORKERS if p.poll() is None]
        worker = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '_worker', str(directory)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        _WORKERS.append(worker)
        pid_temp = directory / 'pid.parent.tmp'
        pid_temp.write_text(str(worker.pid))
        os.replace(pid_temp, directory / 'pid')
        return _result('running', job=jid)
    if action == 'list':
        jobs = _home() / 'jobs'
        rows = []
        for directory in jobs.iterdir() if jobs.exists() else []:
            try:
                meta = json.loads((directory / 'meta.json').read_text(encoding='utf-8'))
                command = _command(table, meta['command'])
                if not command or not _allowed(table, caller, command):
                    continue
                try:
                    status = json.loads((directory / 'result.json').read_text(encoding='utf-8'))['status']
                except FileNotFoundError:
                    status = 'running'
                rows.append((meta.get('started', ''), directory.name, meta['command'], status))
            except (OSError, ValueError, KeyError):
                continue
        rows.sort(reverse=True)
        return _result('ok', 0, ''.join(f'{jid} {name} {status} {started}\n' for started, jid, name, status in rows[:20]))
    jid = values.get('job')
    if not isinstance(jid, str) or not re.fullmatch(r'[0-9a-f]{32}', jid):
        raise ValueError('job: expected job id')
    directory = _home() / 'jobs' / jid
    try:
        meta = json.loads((directory / 'meta.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        raise ValueError('job: unknown job id') from None
    command = _command(table, meta['command'])
    if not command or not _allowed(table, caller, command):
        raise ValueError('job: caller is not permitted')
    with (directory / 'lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            result = json.loads((directory / 'result.json').read_text(encoding='utf-8'))
        except FileNotFoundError:
            result = None
        if action == 'cancel' and result is None:
            try:
                pid = int((directory / 'pid').read_text())
                os.kill(pid, 0)
                try:
                    child_pid = int((directory / 'child_pid').read_text())
                    os.killpg(child_pid, signal.SIGKILL)
                except (FileNotFoundError, ProcessLookupError):
                    pass
                os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError:
                # worker 已经不在、又没留下结果：把状态落盘，否则这个任务会永远显示 running
                result = dict(status='failed', exit_code=None, reason='worker 已不在，没有留下结果')
                (directory / 'result.json').write_text(json.dumps(result), encoding='utf-8')
                return _result('failed', job=jid, reason='已经结束')
            result = dict(status='cancelled', exit_code=None, reason='cancelled')
            (directory / 'result.json').write_text(json.dumps(result), encoding='utf-8')
        elif action == 'cancel':
            status = 'failed' if result['status'] == 'cancelled' else result['status']
            return _result(status, result['exit_code'], job=jid, reason='已经结束')
    if result is None:
        return _result('running', job=jid)
    output = (directory / 'output.log').read_text(encoding='utf-8', errors='replace') if action == 'result' else ''
    status = 'failed' if result['status'] == 'cancelled' else result['status']
    return _result(status, result['exit_code'], output, jid, result['reason'])


def _worker(directory):
    directory = Path(directory)
    pid_temp = directory / 'pid.worker.tmp'
    pid_temp.write_text(str(os.getpid()))
    os.replace(pid_temp, directory / 'pid')
    meta = json.loads((directory / 'meta.json').read_text(encoding='utf-8'))
    try:
        result = _execute(meta['definition'], meta['steps'], meta['timeout'], full_output=True, job_directory=directory)
    except Exception as e:
        result = _result('failed', reason=str(e))
    (directory / 'output.log').write_text(result['output'], encoding='utf-8')
    (directory / 'exit_code').write_text(str(result['exit_code']), encoding='utf-8')
    with (directory / 'lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            with (directory / 'result.json').open('x', encoding='utf-8') as f:
                json.dump({k: result[k] for k in ('status', 'exit_code', 'reason')}, f)
        except FileExistsError:
            pass


def run_as(caller, name, args=None):
    started = time.monotonic()
    result = None
    try:
        table = _table()
        command = _command(table, name)
        if not command:
            raise ValueError('name: unknown command')
        if name != 'job' and not _allowed(table, caller, command):
            raise ValueError('caller: not permitted for command')
        if name == 'job' and caller not in table.get('callers', {}):
            raise ValueError('caller: unknown caller')
        if command.get('mode') == 'job_only':
            raise ValueError(f'用 job 启动：{{"action":"start","command":"{name}"}}')
        values = _validate(command, {} if args is None else args)
        _home().mkdir(parents=True, exist_ok=True)
        if name == 'job':
            result = _job(table, caller, values)
        else:
            steps = _prepare(command, values)
            result = _execute(command, steps, command.get('timeout', 60))
    except (ValueError, TypeError, KeyError, OSError) as e:
        result = _result('rejected', reason=str(e))
    try:
        _home().mkdir(parents=True, exist_ok=True)
        row = dict(time=datetime.now(timezone.utc).isoformat(), caller=caller, name=name, args=args, status=result['status'], exit_code=result['exit_code'], seconds=round(time.monotonic() - started, 3))
        with (_home() / 'audit.jsonl').open('a', encoding='utf-8') as f:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + '\n')
    except OSError:
        pass
    return result


def run(name: str, args: dict = None) -> dict:
    return run_as('tool_call', name, args)


def list_as(caller) -> list:
    table = _table()
    if caller not in table.get('callers', {}):
        return []
    return [{k: c[k] for k in ('name', 'level', 'doc', 'params')} for c in table['commands'] if c['name'] == 'job' or _allowed(table, caller, c)]


def list() -> list:
    return list_as('tool_call')


def describe() -> str:
    return '固定指令执行器：run(name, args) 执行，list() 查看可用指令；job 指令支持 start、status、result、list、cancel。'


if __name__ == '__main__' and len(sys.argv) == 3 and sys.argv[1] == '_worker':
    _worker(sys.argv[2])
