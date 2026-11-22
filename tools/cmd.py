# -*- coding: utf-8 -*-
"""固定指令执行器；指令及权限由只读配置表定义。"""
import builtins
import ast
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
    result = dict(status=status, exit_code=exit_code, output=output[-8000:], job=job, reason=reason)
    if len(output) > 8000:
        result['truncated'] = True
    return result


_SECRET_VALUE = r'[A-Za-z0-9_+/=.-]'
_SENSITIVE_PART = r'(?:key|token|secret|authorization|credential|password|passwd|pwd)'
_SENSITIVE_NAME = (r'(?:[\w.-]*' + _SENSITIVE_PART + r'[\w.-]*|'
                   r'"[^"\r\n]*' + _SENSITIVE_PART + r'[^"\r\n]*"|'
                   r"'[^'\r\n]*" + _SENSITIVE_PART + r"[^'\r\n]*')")
_ASSIGN = re.compile(
    r"(?i)(?<![\w.])(?P<name>" + _SENSITIVE_NAME + r")[\"']?\s*[:=]\s*"
    r"(?:(?P<quote>[\"'])(?P<quoted>(?:\\.|(?!(?P=quote))[^\\\r\n])*)(?P=quote)|"
    r"(?P<plain>" + _SECRET_VALUE + r"{12,})(?!" + _SECRET_VALUE + r"|[([]))")
_BEARER = re.compile(r'(?i)(\bbearer\s+)(' + _SECRET_VALUE + r'{12,})')
_PREFIX = re.compile(r'(?i)(?:\b(?:sk-|ghp_|gho_|AKIA|xox[bap]-)' + _SECRET_VALUE + r'{12,}|\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)')
_PEM = re.compile(r'-----BEGIN ([^-\r\n]*PRIVATE KEY)-----')
_LOCATION = re.compile(r'^(?:.*?:[0-9]+:|\s*[0-9]+\t)')


def _redact(output):
    pem_end = None
    result = []
    for line in output.splitlines(keepends=True):
        prefix = _LOCATION.match(line)
        location = prefix.group() if prefix else ''
        body = line[len(location):]
        ending = body[len(body.rstrip('\r\n')):]
        body = body.rstrip('\r\n')
        begin = _PEM.search(body)
        if pem_end is None and begin:
            pem_end = '-----END ' + begin.group(1) + '-----'
        if pem_end is not None:
            if pem_end in body:
                pem_end = None
            result.append(location + '[已隐藏：私钥]' + ending)
            continue

        def assignment(match):
            value = match.group('quoted')
            if value is not None:
                password = re.search(r'(?i)password|passwd|pwd', match.group('name'))
                hide = bool(value) if password else len(value) >= 6
                start, end = match.span('quoted')
            else:
                value = match.group('plain')
                hide = bool(re.search(r'[A-Za-z]', value) and re.search(r'[0-9]', value))
                start, end = match.span('plain')
            if not hide:
                return match.group()
            start -= match.start()
            end -= match.start()
            return match.group()[:start] + '[已隐藏]' + match.group()[end:]

        body = _ASSIGN.sub(assignment, body)
        body = _BEARER.sub(lambda m: m.group(1) + '[已隐藏]', body)
        body = _PREFIX.sub('[已隐藏]', body)
        result.append(location + body + ending)
    return ''.join(result)


def _truncate(output, command, values):
    maximum = max(1, command.get('max_output', 8000))
    if len(output) <= maximum:
        return output, False
    lines = output.splitlines(keepends=True)
    head = command.get('truncate', 'tail') == 'head'

    def annotation(shown):
        note = '共 %d 行，显示 %d 行' % (len(lines), len(shown.splitlines()))
        if head and command.get('name') == 'show':
            paths = values.get('paths', [])
            current = os.path.relpath(paths[0], command['cwd']) if paths else ''
            line_no = values.get('start', 1)
            for line in shown.splitlines():
                header = re.match(r'^== (.*?)（共 \d+ 行）==', line)
                numbered = re.match(r'^\s*(\d+)\t', line)
                if header: current, line_no = header.group(1), values.get('start', 1)
                if numbered: line_no = int(numbered.group(1)) + 1
            remaining = output[len(shown):]
            header = re.match(r'^== (.*?)（共 \d+ 行）==', remaining)
            if header: current, line_no = header.group(1), values.get('start', 1)
            note += '；从 %s 第 %d 行继续读' % (current, line_no)
        return '[' + note + '，输出已截断]\n'

    # Recompute as the displayed line count changes; never split a head line.
    reserve = len(annotation(''))
    for _ in range(5):
        available = max(0, maximum - reserve)
        if head:
            used = 0
            selected = []
            for line in lines:
                if used + len(line) > available: break
                selected.append(line)
                used += len(line)
            shown = ''.join(selected)
        else:
            shown = output[-available:] if available else ''
        note = annotation(shown)
        if len(note) <= reserve: break
        reserve = len(note)
    if len(note) > maximum:
        return note[:maximum], True
    return (shown + note if head else note + shown), True


def _validate_out(out):
    if not isinstance(out, builtins.list):
        raise ValueError('out: 必须是列表')
    if len(out) > 8:
        raise ValueError('out: 第 9 步超过 8 步上限')
    steps = []
    for i, item in enumerate(out, 1):
        def invalid(message):
            raise ValueError(f'out: 第 {i} 步 {message}')
        if isinstance(item, str):
            if item not in ('sort', 'uniq', 'count'):
                invalid('未知步骤')
            op, value, sep = item, None, None
        elif isinstance(item, dict):
            keys = set(item) - {'sep'}
            if len(keys) != 1:
                invalid('必须指定一个步骤')
            op = next(iter(keys))
            value, sep = item[op], item.get('sep')
            if 'sep' in item and (op != 'field' or not isinstance(sep, str) or not sep or len(sep) > 200):
                invalid('sep 必须是非空且不超过 200 字符的分隔符')
            if op in ('filter', 'exclude'):
                if not isinstance(value, str) or len(value) > 200:
                    invalid('需要不超过 200 字符的字符串')
            elif op in ('head', 'tail', 'field'):
                if type(value) is not int or value < 1 or (op != 'field' and value > 100000):
                    invalid('需要正整数；head/tail 上限为 100000')
            elif op == 'sort':
                if value not in ('asc', 'desc', 'num', 'num_desc'):
                    invalid('排序方式无效')
            elif op == 'uniq':
                if value not in ('plain', 'count'):
                    invalid('去重方式无效')
            else:
                invalid('未知步骤')
        else:
            invalid('格式无效')
        if op == 'count' and i != len(out):
            invalid('count 必须是最后一步')
        steps.append((op, value, sep))
    return steps


def _postprocess(output, steps, limit_mode=None, limit=None):
    lines = output.splitlines()
    for op, value, sep in steps:
        if op == 'filter': lines = [x for x in lines if value in x]
        elif op == 'exclude': lines = [x for x in lines if value not in x]
        elif op == 'head': lines = lines[:value]
        elif op == 'tail': lines = lines[-value:]
        elif op == 'sort':
            if value in ('num', 'num_desc'):
                def number(line):
                    match = re.match(r'^[+-]?\d+', line)
                    return int(match.group()) if match else 0
                lines.sort(key=number, reverse=value == 'num_desc')
            else:
                lines.sort(reverse=value == 'desc')
        elif op == 'uniq':
            counts = {}
            for line in lines: counts[line] = counts.get(line, 0) + 1
            lines = [f'{n}\t{x}' for x, n in counts.items()] if value == 'count' else builtins.list(counts)
        elif op == 'field':
            fields = [line.split(sep) for line in lines]
            lines = [parts[value - 1] for parts in fields if len(parts) >= value]
        elif op == 'count': lines = [str(len(lines))]
    if limit_mode and not (steps and steps[-1][0] == 'count'):
        lines = lines[:limit] if limit_mode == 'head' else lines[-limit:]
    return '\n'.join(lines) + ('\n' if lines else '')


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
    if any(fnmatch.fnmatchcase(str(resolved), pattern) or fnmatch.fnmatchcase(resolved.name, pattern)
           for pattern in spec.get('deny', [])):
        raise ValueError(f'{name}: path 不允许读取这类文件')
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


def _text(value, spec, name):
    if not isinstance(value, str) or len(value) > spec.get('max_len', 8000) or '\x00' in value:
        raise ValueError(f'{name}: expected text max_len={spec.get("max_len", 8000)}')
    # 格式约束全写在指令表的 pattern 里，这里不认具体参数名
    if 'pattern' in spec and re.fullmatch(spec['pattern'], value) is None:
        raise ValueError(f'{name}: expected format {spec["pattern"]}')


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
        if typ in ('path_list', 'text_list') and isinstance(value, str):
            value = [value]
        if typ == 'path':
            value = _path(value, spec, cwd, name)
        elif typ == 'path_list':
            if not isinstance(value, builtins.list) or (spec.get('required') and not value):
                raise ValueError(f'{name}: expected {"nonempty " if spec.get("required") else ""}path list')
            if len(value) > spec.get('max_items', 100000):
                raise ValueError(f'{name}: too many paths')
            value = [_path(v, spec, cwd, name) for v in value]
        elif typ == 'int':
            if type(value) is not int or value < spec.get('min', -sys.maxsize) or value > spec.get('max', sys.maxsize):
                raise ValueError(f'{name}: expected integer in {spec.get("min", "-∞")}..{spec.get("max", "∞")}')
        elif typ == 'enum':
            if value not in spec['values'] or not isinstance(value, str):
                raise ValueError(f'{name}: expected one of {spec["values"]}')
        elif typ == 'text':
            _text(value, spec, name)
        elif typ == 'text_list':
            most = spec.get('max_items', 20)
            if not isinstance(value, builtins.list) or (spec.get('required') and not value) or len(value) > most:
                raise ValueError(f'{name}: expected {"nonempty " if spec.get("required") else ""}text list max_items={most}')
            for item in value:
                _text(item, spec, name)
        elif typ == 'bool':
            if type(value) is not bool:
                raise ValueError(f'{name}: expected bool')
        elif typ == 'object':
            if not isinstance(value, dict):
                raise ValueError(f'{name}: expected object')
        else:
            raise ValueError(f'{name}: unsupported type {typ}')
        values[name] = value
    if command['name'] == 'show':
        paths = ([values['path']] if values.get('path') else []) + values.get('paths', [])
        paths = builtins.list(dict.fromkeys(paths))
        if not paths or len(paths) > 12:
            raise ValueError('show: 需要 1 到 12 个文件')
        values['paths'] = paths
    if command['name'] == 'probe':
        resolved = []
        for item in values.get('at', []):
            filename, number = item.rsplit(':', 1)
            if '..' in Path(filename).parts:
                raise ValueError('at: .. 不允许')
            p = Path(filename)
            candidates = [p] if p.is_absolute() else [cwd / p, Path(values['path']).parent / p]
            tried = []
            for candidate in candidates:
                candidate = candidate.resolve()
                if candidate != cwd and cwd not in candidate.parents:
                    raise ValueError('at: 路径不在仓库内')
                tried.append(str(candidate))
                if candidate.is_file():
                    resolved.append(str(candidate.relative_to(cwd)) + ':' + number)
                    break
            else:
                raise ValueError('at: 找不到文件；试过 ' + ', '.join(tried) + '；例：tools/cmd.py:24')
        values['at'] = resolved
        case = values.get('case', '')
        if case.startswith('test') and '.' not in case:
            try:
                tree = ast.parse(Path(values['path']).read_text(encoding='utf-8'))
                candidates = [c.name + '.' + m.name for c in ast.walk(tree) if isinstance(c, ast.ClassDef)
                              for m in c.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and m.name == case]
            except (OSError, SyntaxError):
                candidates = []
            if len(candidates) > 1:
                raise ValueError('case: 多个候选：' + ', '.join(candidates))
            if candidates:
                values['case'] = candidates[0]
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
            value.pop('truncated', None)
        return value
    start = time.monotonic()
    chunks = []
    for step in steps:
        remaining = timeout - (time.monotonic() - start)
        if remaining <= 0:
            return result('failed', output=''.join(chunks), reason='timeout')
        # 把这一步还剩多少秒告诉它，长指令可以赶在被杀之前交出部分结果
        env = dict(os.environ, CMD_TIMEOUT=str(int(remaining)))
        try:
            if job_directory:
                with (job_directory / 'lock').open('a') as lock:
                    fcntl.flock(lock, fcntl.LOCK_EX)
                    p = subprocess.Popen(step, shell=True, cwd=command['cwd'], stdout=subprocess.PIPE,
                                         stderr=subprocess.STDOUT, start_new_session=True, env=env)
                    (job_directory / 'child_pid').write_text(str(p.pid))
            else:
                p = subprocess.Popen(step, shell=True, cwd=command['cwd'], stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, start_new_session=True, env=env)
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


def _job(table, caller, values, full_output=False):
    action = values['action']
    if action == 'start':
        name = values.get('command')
        command = _command(table, name)
        if not command or name == 'job':
            raise ValueError('command: unknown or invalid command')
        if not _allowed(table, caller, command):
            raise ValueError('command: caller is not permitted')
        inner = values.get('args', {})
        if isinstance(inner, dict) and 'out' in inner:
            raise ValueError('后台任务在 result 时用 out')
        args = _validate(command, inner)
        steps = _prepare(command, args)
        jid = uuid.uuid4().hex
        directory = _home() / 'jobs' / jid
        directory.mkdir(parents=True)
        (directory / 'meta.json').write_text(json.dumps({'caller': caller, 'command': name, 'definition': command, 'values': args, 'steps': steps, 'timeout': command.get('job_timeout', 3600), 'started': datetime.now(timezone.utc).isoformat()}), encoding='utf-8')
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
    answer = _result(status, result['exit_code'], output, jid, result['reason'])
    if full_output:
        answer['output'] = output
        answer.pop('truncated', None)
    return answer


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
        raw_args = {} if args is None else args
        if not isinstance(raw_args, dict):
            raise ValueError('args: expected object')
        has_out = 'out' in raw_args
        out = raw_args.get('out')
        if has_out and command['level'] != 'read':
            raise ValueError('out 只能用于只读指令')
        if has_out and name == 'job' and raw_args.get('action') != 'result':
            raise ValueError('job 只能在 result 时使用 out')
        out_steps = _validate_out(out) if has_out else []
        values = _validate(command, {k: v for k, v in raw_args.items() if k != 'out'})
        _home().mkdir(parents=True, exist_ok=True)
        if name == 'job':
            result = _job(table, caller, values, full_output=True)
        else:
            steps = _prepare(command, values)
            result = _execute(command, steps, command.get('timeout', 60), full_output=True)
        effective = command
        if name == 'job' and values.get('action') == 'result' and values.get('job'):
            meta_path = _home() / 'jobs' / values['job'] / 'meta.json'
            meta = json.loads(meta_path.read_text(encoding='utf-8'))
            effective = meta.get('definition', command)
            values = meta.get('values', values)
        output = result['output']
        if effective.get('redact'):
            output = _redact(output)
        if result['status'] == 'ok' and (has_out or (name != 'job' and effective.get('limit_mode'))):
            output = _postprocess(output, out_steps, effective.get('limit_mode') if name != 'job' else None, values.get('limit'))
        result['output'], truncated = _truncate(output, effective, values)
        if truncated:
            result['truncated'] = True
        else:
            result.pop('truncated', None)
    except (ValueError, TypeError, KeyError, OSError) as e:
        result = _result('rejected', reason=str(e))
    try:
        _home().mkdir(parents=True, exist_ok=True)
        row = dict(time=datetime.now(timezone.utc).isoformat(), caller=caller, name=name, args=args, status=result['status'], exit_code=result['exit_code'], seconds=round(time.monotonic() - started, 3))
        with (_home() / 'audit.jsonl').open('a', encoding='utf-8') as f:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + '\n')
    except OSError as e:
        result['audit_error'] = str(e)
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


def describe_as(caller, name=None) -> str:
    table = _table()
    if caller not in table.get('callers', {}):
        return ''
    commands = list_as(caller)
    if name is not None:
        command = next((c for c in commands if c['name'] == name), None)
        if command is None:
            return '指令不存在或无权限。'
        definition = _command(table, name)
        lines = [f"{name} [{command['level']}] {command['doc']}"]
        for key, spec in command['params'].items():
            details = [f"类型={spec['type']}", '必填' if spec.get('required') else '可选']
            details.extend(f'{field}={json.dumps(spec[field], ensure_ascii=False)}' for field in
                           ('default', 'min', 'max', 'values', 'max_len', 'max_items', 'pattern', 'glob', 'roots', 'deny') if field in spec)
            lines.append(f"{key}: " + ', '.join(details))
        if definition.get('limit_mode'):
            lines.append('limit 在 out 之后生效；count 不受 limit 限制。')
        if command['level'] == 'read':
            lines.append('可带 out；job 仅 result 可用。' if name == 'job' else '可带 out。')
        return '\n'.join(lines)
    lines = ['用 cmd_run 的 name 和 args 执行固定指令。']
    lines.extend(f'{key}: {value}' for key, value in table.get('common', {}).items())
    lines.extend(['out 按顺序执行 filter、exclude、head、tail、sort、uniq、field、count（最后一步）。',
                  '例：out=[{"filter":"error"},{"tail":10}]；sort 可选 asc/desc/num/num_desc，uniq 可选 plain/count。',
                  'field 支持 sep；最多 8 步。某条指令的参数细节：再调一次并给出 name。'])
    for command in commands:
        params = []
        for key, spec in command['params'].items():
            label = key + ('' if spec.get('required') else '?')
            if spec['type'] == 'enum':
                label += '=' + '|'.join(spec['values'])
            params.append(label)
        lines.append(f"{command['name']}({', '.join(params)}) [{command['level']}] {command['doc']}")
    return '\n'.join(lines)


def describe(name=None) -> str:
    return describe_as('tool_call', name)


if __name__ == '__main__' and len(sys.argv) == 3 and sys.argv[1] == '_worker':
    _worker(sys.argv[2])
