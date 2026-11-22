# -*- coding: utf-8 -*-
"""确定性的调试指令：test_report / locate / probe / blame_change。

只用标准库和经典算法（栈解析、Ochiai 覆盖差异、行探针、ddmin），不调用任何语言模型。
以当前目录为仓库根；由 tools/cmd_table.json 的 steps 调用：
    .venv/bin/python -B tools/dbg.py <子命令> <测试文件> [--case X] [--limit N] [--paths ...] [--at ...] [--exprs ...] [--runs N]
退出码：0 = 给出了报告（测试有失败也是 0）；2 = 测试跑不起来或参数不对，输出里说明原因。
时限：读环境变量 CMD_TIMEOUT（执行器给的剩余秒数，没有按 170），留出余量，快到时输出已得到的部分结果。
"""
import os
import sys

DBG = os.path.realpath(__file__)
if __name__ == '__main__' and sys.path and os.path.realpath(sys.path[0] or '.') == os.path.dirname(DBG):
    del sys.path[0]  # 不让 tools/ 下的 cmd.py 等遮住标准库同名模块

import ast
import importlib.util
import json
import math
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import unittest

OUT_MAX = 7900          # 执行器只留末尾 8000 字符，这里自己控制总长
BAD = ('fail', 'error')
WORD = {'pass': '通过', 'fail': '失败', 'error': '出错', 'skip': '跳过', None: '用例之外'}


# ───────────────────────── 公共小工具 ─────────────────────────

class Stop(Exception):
    """提前收场：code 是退出码，text 是要输出的全部内容。"""
    def __init__(self, text, code=0):
        super().__init__(text)
        self.text, self.code = text, code


class Budget:
    def __init__(self, seconds=None):
        if seconds is None:
            raw = os.environ.get('CMD_TIMEOUT', '')
            total = float(raw) if re.fullmatch(r'\d+(\.\d+)?', raw) else 170.0
            seconds = total - max(12.0, total * 0.08)
        self.end = time.monotonic() + max(1.0, seconds)

    def left(self):
        return self.end - time.monotonic()


def _cut(text, n):
    text = str(text)
    return text if len(text) <= n else text[:n - 1] + '…'


def _rel(root, filename):
    """仓库内代码文件的相对路径；不在仓库内（或是 .venv、本文件）返回 None。"""
    if not filename or filename.startswith('<'):
        return None
    p = os.path.realpath(filename if os.path.isabs(filename) else os.path.join(root, filename))
    if p == DBG or not p.startswith(root + os.sep):
        return None
    rel = p[len(root) + 1:].replace(os.sep, '/')
    parts = rel.split('/')
    if '.venv' in parts or 'site-packages' in parts or 'node_modules' in parts:
        return None
    return rel


def _context(root, rel, line, indent='    '):
    """该行前后各 2 行代码。"""
    try:
        with open(os.path.join(root, rel), encoding='utf-8', errors='replace') as f:
            lines = f.read().split('\n')
    except OSError:
        return []
    if lines and lines[-1] == '':
        lines.pop()
    return ['%s%s %5d  %s' % (indent, '>' if n == line else ' ', n, _cut(lines[n - 1].rstrip(), 160))
            for n in range(max(1, line - 2), min(len(lines), line + 2) + 1)]


def _source_line(root, rel, line):
    try:
        with open(os.path.join(root, rel), encoding='utf-8', errors='replace') as f:
            lines = f.read().split('\n')
        return _cut(lines[line - 1].strip(), 120) if 1 <= line <= len(lines) else ''
    except OSError:
        return ''


def _style(path):
    """'unittest'：文件引入了 unittest 且有带 test* 方法的类；否则 'script'（脚本式）。"""
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            tree = ast.parse(f.read())
    except (SyntaxError, ValueError, OSError):
        return 'script'
    imported = has_case = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported = imported or any(a.name.split('.')[0] == 'unittest' for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported = imported or (node.module or '').split('.')[0] == 'unittest'
        elif isinstance(node, ast.ClassDef):
            has_case = has_case or any(isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef)) and
                                       b.name.startswith('test') for b in node.body)
    return 'unittest' if imported and has_case else 'script'


def _env(root):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    modules = os.path.join(root, 'tests/e2e/node_modules')
    if os.path.isdir(modules):
        env['NODE_PATH'] = modules
    return env


def _spawn(argv, cwd, log, timeout, env):
    """跑子进程，输出进 log；返回 (退出码或 None, 是否超时)。"""
    with open(log, 'wb') as f:
        p = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.DEVNULL, stdout=f, stderr=subprocess.STDOUT, env=env)
        try:
            return p.wait(timeout=max(1.0, timeout)), False
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()
            return None, True


def _tail(log, n=12):
    try:
        with open(log, encoding='utf-8', errors='replace') as f:
            return [_cut(x.rstrip(), 200) for x in f.read().splitlines()[-n:]]
    except OSError:
        return []


# ───────────────────────── 子进程：按 unittest 跑并逐用例写结果 ─────────────────────────

def _exc_info(root, etype, value, tb):
    frames = []
    while tb is not None:
        rel = _rel(root, tb.tb_frame.f_code.co_filename)
        if rel:
            frames.append([rel, tb.tb_lineno, tb.tb_frame.f_code.co_name])
        tb = tb.tb_next
    if isinstance(value, SyntaxError) and value.filename and value.lineno:
        rel = _rel(root, value.filename)
        if rel:
            frames.append([rel, value.lineno, '语法错'])
    try:
        msg = str(value)
    except Exception:
        msg = '<异常信息取不出>'
    return dict(type=getattr(etype, '__name__', str(etype)), msg=_cut(msg, 1500), frames=frames[-12:])


class _Cover:
    """记录每个用例执行过的行（只记统计范围内的文件）。"""
    def __init__(self, root, scope, test_rel):
        self.root, self.scope, self.test_rel = root, scope, test_rel
        self.known, self.cur = {}, None

    def _want(self, filename):
        rel = _rel(self.root, filename)
        if rel is None or not rel.endswith('.py'):
            return None
        if self.scope:
            return rel if any(s in ('', '.') or rel == s or rel.startswith(s + '/') for s in self.scope) else None
        if rel == self.test_rel or os.path.basename(rel).startswith('test'):
            return None
        same_dir = os.path.dirname(rel) == os.path.dirname(self.test_rel)
        return rel if same_dir or 'tests' not in rel.split('/')[:-1] else None

    def _global(self, frame, event, arg):
        if self.cur is None:
            return None
        filename = frame.f_code.co_filename
        rel = self.known.get(filename, 0)
        if rel == 0:
            rel = self.known[filename] = self._want(filename)
        if rel is None:
            return None
        add = self.cur.setdefault(rel, set()).add

        def local(frame, event, arg):
            if event == 'line':
                add(frame.f_lineno)
            return local
        return local

    def begin(self):
        self.cur = {}

    def end(self):
        cov, self.cur = self.cur or {}, None
        return {'cov': {f: sorted(cov[f]) for f in sorted(cov)}}

    def install(self):
        threading.settrace(self._global)
        sys.settrace(self._global)

    def finish(self):
        return None


_FUNCS = {'len': len, 'type': type}


def check_expr(src):
    """探针表达式白名单：变量名、属性（不含双下划线名）、下标（常量或变量名）、常量、len(x) / type(x)。
    合法返回 AST 节点，否则抛 ValueError（原因）。只做语法检查，不执行任何东西。"""
    if not isinstance(src, str) or not src.strip() or len(src) > 200:
        raise ValueError('表达式为空或超过 200 字符')
    try:
        tree = ast.parse(src.strip(), mode='eval')
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        raise ValueError('不是合法的表达式') from None

    def dunder(name):
        return name.startswith('__') or name.endswith('__')

    def number(n):
        return (isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.USub) and isinstance(n.operand, ast.Constant)
                and type(n.operand.value) in (int, float))

    def walk(n, depth):
        if depth > 20:
            raise ValueError('嵌套过深')
        if isinstance(n, ast.Constant):
            if not isinstance(n.value, (int, float, str, bytes, bool, type(None))):
                raise ValueError('不允许的常量')
        elif isinstance(n, ast.Name):
            if dunder(n.id):
                raise ValueError('不允许双下划线名 ' + n.id)
        elif isinstance(n, ast.Attribute):
            if dunder(n.attr):
                raise ValueError('不允许双下划线属性 ' + n.attr)
            walk(n.value, depth + 1)
        elif isinstance(n, ast.Subscript):
            if not (isinstance(n.slice, (ast.Constant, ast.Name)) or number(n.slice)):
                raise ValueError('下标只能是常量或变量名')
            walk(n.slice, depth + 1)
            walk(n.value, depth + 1)
        elif number(n):
            pass
        elif isinstance(n, ast.Call):
            if not (isinstance(n.func, ast.Name) and n.func.id in _FUNCS and len(n.args) == 1
                    and not n.keywords and not isinstance(n.args[0], ast.Starred)):
                raise ValueError('只允许调用 len(x) 或 type(x)')
            walk(n.args[0], depth + 1)
        else:
            raise ValueError('不允许的语法 ' + type(n).__name__)
    walk(tree.body, 0)
    return tree.body


def _eval(n, frame):
    """只解释白名单里的节点，不用 eval / exec。"""
    if isinstance(n, ast.Constant):
        return n.value
    if isinstance(n, ast.Name):
        for scope in (frame.f_locals, frame.f_globals, frame.f_builtins):
            if n.id in scope:
                return scope[n.id]
        raise NameError(n.id)
    if isinstance(n, ast.Attribute):
        return getattr(_eval(n.value, frame), n.attr)
    if isinstance(n, ast.Subscript):
        return _eval(n.value, frame)[_eval(n.slice, frame)]
    if isinstance(n, ast.UnaryOp):
        return -n.operand.value
    if isinstance(n, ast.Call):
        return _FUNCS[n.func.id](_eval(n.args[0], frame))
    raise TypeError(type(n).__name__)


def _show(node, frame):
    try:
        value = _eval(node, frame)
    except Exception as e:
        return '!' + type(e).__name__
    try:
        text = repr(value)
    except Exception as e:
        return '<repr 出错 %s>' % type(e).__name__
    return _cut(re.sub(r' at 0x[0-9a-fA-F]+', ' at 0x…', text), 160)


class _Probe:
    """执行到指定行（该行执行之前）时，在当时的帧里取表达式的值。"""
    CAP = 4000

    def __init__(self, root, at, exprs, limit):
        self.targets = {}
        for i, (rel, line) in enumerate(at):
            self.targets.setdefault(os.path.realpath(os.path.join(root, rel)), {})[line] = i
        self.nodes = [check_expr(e) for e in exprs]
        self.limit, self.known, self.total = limit, {}, 0
        self.inside = False
        self.hits, self.count = [], {}
        self.out_hits, self.out_count = [], {}

    def _global(self, frame, event, arg):
        code = frame.f_code
        lines = self.known.get(code.co_filename, 0)
        if lines == 0:
            name = code.co_filename
            lines = self.known[name] = None if name.startswith('<') else self.targets.get(os.path.realpath(name))
        if lines is None or all(n < code.co_firstlineno for n in lines):
            return None

        def local(frame, event, arg):
            if event == 'line':
                i = lines.get(frame.f_lineno)
                if i is not None:
                    self._hit(i, frame)
            return local
        return local

    def _hit(self, i, frame):
        hits, count = (self.hits, self.count) if self.inside else (self.out_hits, self.out_count)
        key = str(i)
        count[key] = count.get(key, 0) + 1
        if count[key] > self.limit or self.total >= self.CAP:
            return
        self.total += 1
        hits.append([i, [_show(node, frame) for node in self.nodes]])

    def begin(self):
        self.inside, self.hits, self.count = True, [], {}

    def end(self):
        self.inside = False
        return {'hits': self.hits, 'nhit': self.count}

    def install(self):
        threading.settrace(self._global)
        sys.settrace(self._global)

    def finish(self):
        return dict(k='outside', hits=self.out_hits, nhit=self.out_count)


class _Result(unittest.TestResult):
    def __init__(self, put, root, prefix, tracer, deadline):
        super().__init__()
        self.put, self.root, self.prefix, self.tracer, self.deadline = put, root, prefix, tracer, deadline
        self.cur = self.fails = None
        self.outcome = 'pass'
        self.early = False

    def _name(self, test):
        try:
            name = test.id()
        except Exception:
            name = str(test)
        return name[len(self.prefix):] if name.startswith(self.prefix) else name

    def startTest(self, test):
        super().startTest(test)
        self.cur, self.outcome, self.fails = self._name(test), 'pass', []
        if self.tracer:
            self.tracer.begin()

    def stopTest(self, test):
        super().stopTest(test)
        extra = self.tracer.end() if self.tracer else {}
        self.put(k='case', id=self.cur, outcome=self.outcome, fails=self.fails, **extra)
        self.cur = self.fails = None
        if time.monotonic() > self.deadline and not self.shouldStop:
            self.early = True
            self.stop()

    def _bad(self, kind, test, err=None, msg=''):
        info = _exc_info(self.root, *err) if err else dict(type='UnexpectedSuccess', msg=msg, frames=[])
        info.update(name=self._name(test), kind=kind)
        if self.fails is None:      # setUpClass / setUpModule 等用例之外的错
            self.put(k='case', id=info['name'], outcome=kind, fails=[info])
            return
        self.fails.append(info)
        if self.outcome != 'error':
            self.outcome = kind

    def addFailure(self, test, err):
        self._bad('fail', test, err)

    def addError(self, test, err):
        self._bad('error', test, err)

    def addSuccess(self, test):
        pass

    def addExpectedFailure(self, test, err):
        pass

    def addUnexpectedSuccess(self, test):
        self._bad('fail', test, msg='标了 expectedFailure 却通过了')

    def addSkip(self, test, reason):
        if self.fails is None:
            self.put(k='case', id=self._name(test), outcome='skip', fails=[])
        elif self.outcome == 'pass':
            self.outcome = 'skip'

    def addSubTest(self, test, subtest, err):
        if err is not None:
            self._bad('fail' if issubclass(err[0], test.failureException) else 'error', subtest, err)


def _child(cfg_path):
    with open(cfg_path, encoding='utf-8') as f:
        cfg = json.load(f)
    root = os.path.realpath(os.getcwd())
    out = open(cfg['out'], 'a', encoding='utf-8')

    def put(**record):
        out.write(json.dumps(record, ensure_ascii=False) + '\n')
        out.flush()
    deadline = time.monotonic() + cfg['soft']
    test = cfg['test']
    tracer = None
    if cfg['mode'] == 'cover':
        tracer = _Cover(root, cfg.get('scope') or [], _rel(root, test))
    elif cfg['mode'] == 'probe':
        tracer = _Probe(root, cfg['at'], cfg['exprs'], cfg['limit'])
    name = os.path.splitext(os.path.basename(test))[0]
    sys.argv = [test]
    sys.path.insert(0, os.path.dirname(test))
    if tracer:
        tracer.install()
    loader = unittest.TestLoader()
    try:
        spec = importlib.util.spec_from_file_location(name, test)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        suite = loader.loadTestsFromName(cfg['case'], module) if cfg.get('case') else loader.loadTestsFromModule(module)
    except BaseException as e:
        sys.settrace(None)
        put(k='fatal', stage='导入测试文件时', **_exc_info(root, type(e), e, e.__traceback__))
        return 2
    total = suite.countTestCases()
    if loader.errors or not total:
        sys.settrace(None)
        why = '找不到用例 %s' % cfg['case'] if cfg.get('case') else '文件里没有可运行的用例'
        put(k='fatal', stage='装载用例时', type='LoadError', msg=why, frames=[])
        return 2
    put(k='start', total=total)
    result = _Result(put, root, name + '.', tracer, deadline)
    try:
        suite.run(result)
    finally:
        sys.settrace(None)
        threading.settrace(None)
    extra = tracer.finish() if tracer else None
    if extra:
        put(**extra)
    put(k='end', early=result.early)
    out.close()
    return 0


class Run:
    """一次按 unittest 跑的结果。"""
    def __init__(self, records, rc, timed_out, log):
        self.cases = [r for r in records if r.get('k') == 'case']
        self.fatal = next((r for r in records if r.get('k') == 'fatal'), None)
        self.total = next((r['total'] for r in records if r.get('k') == 'start'), None)
        self.outside = next((r for r in records if r.get('k') == 'outside'), None)
        end = next((r for r in records if r.get('k') == 'end'), None)
        self.done = end is not None and not end.get('early')
        self.timed_out, self.rc, self.log = timed_out, rc, log
        self.failed = [c for c in self.cases if c['outcome'] in BAD]
        self.passed = [c for c in self.cases if c['outcome'] == 'pass']
        if self.fatal is None and self.total is None:
            why = '超时，测试文件还没导入完' if timed_out else '测试进程异常退出（退出码 %s）' % rc
            self.fatal = dict(stage='', type='', msg=why, frames=[], tail=_tail(log))

    def partial(self):
        """没跑完时的一句说明；跑完了返回空串。"""
        if self.done:
            return ''
        ran = '只跑完 %d/%s 个用例' % (len(self.cases), self.total)
        if self.timed_out:
            return ran + '：到时限被中止（有用例卡住或太慢），可缩小 case 或用 job 启动'
        if self.rc not in (0, None):
            return ran + '：测试进程中途退出（退出码 %s）' % self.rc
        return ran + '：快到时限，提前停下，可缩小 case 或用 job 启动'


def _run_unittest(root, test, case, budget, work, mode='report', timeout=None, **extra):
    n = len(os.listdir(work))
    out, log, cfg_path = (os.path.join(work, '%d.%s' % (n, ext)) for ext in ('jsonl', 'log', 'json'))
    left = budget.left() if timeout is None else min(budget.left(), timeout + 3.0)
    with open(cfg_path, 'w', encoding='utf-8') as f:
        json.dump(dict(extra, mode=mode, test=test, case=case or '', out=out, soft=max(1.0, left - 8.0)), f)
    rc, timed_out = _spawn([sys.executable, '-B', DBG, '_child', cfg_path], root, log, left - 3.0, _env(root))
    records = []
    try:
        with open(out, encoding='utf-8') as f:
            for line in f:
                try:
                    records.append(json.loads(line))
                except ValueError:
                    break
    except OSError:
        pass
    return Run(records, rc, timed_out, log)


def _fatal_text(root, fatal):
    lines = ['%s%s%s' % (fatal.get('stage', ''), fatal['type'] + ': ' if fatal.get('type') else '', _cut(fatal['msg'], 600))]
    if fatal.get('frames'):
        rel, line, func = fatal['frames'][-1]
        lines.append('  位置 %s:%d (%s)' % (rel, line, func))
        lines.extend(_context(root, rel, line))
    lines.extend('  | ' + x for x in fatal.get('tail', []))
    return '\n'.join(lines)


# ───────────────────────── 脚本式测试 ─────────────────────────

_SUM = (re.compile(r'通过\s*(?P<p>\d+)\s*[，、,/;；\s]*失败\s*(?P<f>\d+)'),
        re.compile(r'(?P<p>\d+)\s*通过\s*[，、,/;；\s]*(?P<f>\d+)\s*失败'))
_FRAME = re.compile(r'\s*File "(.+?)", line (\d+)(?:, in (.+))?')
_EXC = re.compile(r'([A-Za-z_][\w.]*(?:Error|Exception|Exit|Interrupt|Warning))(?::\s*(.*))?$')


def _parse_traceback(root, lines):
    """输出里最后一个异常：类型、信息、仓库内的帧。没有返回 None。"""
    start = max((i for i, x in enumerate(lines) if x.strip() == 'Traceback (most recent call last):'), default=None)
    found = None
    for i in range(len(lines) - 1, (start if start is not None else 0) - 1, -1):
        m = _EXC.match(lines[i])
        if m:
            found = (i, m)
            break
    if found is None:
        return None
    end, m = found
    frames = []
    for x in lines[start if start is not None else 0:end]:
        fm = _FRAME.match(x)
        if fm:
            rel = _rel(root, fm.group(1))
            if rel:
                frames.append([rel, int(fm.group(2)), fm.group(3) or '语法错'])
    return dict(type=m.group(1).split('.')[-1], msg=_cut(m.group(2) or '', 600), frames=frames)


def _run_script(root, rel, budget, work, timeout=None):
    log = os.path.join(work, '%d.log' % len(os.listdir(work)))
    left = budget.left() - 3.0 if timeout is None else min(budget.left() - 3.0, timeout)
    rc, timed_out = _spawn([sys.executable, '-B', rel], root, log, left, _env(root))
    with open(log, encoding='utf-8', errors='replace') as f:
        lines = f.read().splitlines()
    summary = None
    for x in reversed(lines):
        summary = _SUM[0].search(x) or _SUM[1].search(x)
        if summary:
            break
    marks = [i for i, x in enumerate(lines) if '✗' in x]
    ticks = sum('✓' in x for x in lines)
    passed, failed = (int(summary.group('p')), int(summary.group('f'))) if summary else (ticks, len(marks))
    return dict(lines=lines, rc=rc, timed_out=timed_out, summary=bool(summary), marks=marks, passed=passed,
                failed=failed, exc=_parse_traceback(root, lines) if rc != 0 else None)


# ───────────────────────── 命令行公共部分 ─────────────────────────

class Ctx:
    def __init__(self, name, path, budget):
        self.name, self.budget = name, budget
        self.root = os.path.realpath(os.getcwd())
        self.test = os.path.realpath(path if os.path.isabs(path) else os.path.join(self.root, path))
        if not self.test.startswith(self.root + os.sep) or not os.path.isfile(self.test):
            raise Stop('%s：测试跑不起来——找不到仓库内的测试文件 %s' % (name, path), 2)
        self.rel = self.test[len(self.root) + 1:].replace(os.sep, '/')
        self.head = '%s %s：' % (name, self.rel)
        self.style = _style(self.test)
        self.work = tempfile.mkdtemp(prefix='dbg_')

    def inside(self, value, what):
        """把参数里的路径转成仓库内相对路径。"""
        p = os.path.realpath(value if os.path.isabs(value) else os.path.join(self.root, value))
        if p != self.root and not p.startswith(self.root + os.sep):
            raise Stop('%s%s 不在仓库内：%s' % (self.head, what, value), 2)
        return p[len(self.root) + 1:].replace(os.sep, '/')

    def cannot_run(self, fatal):
        raise Stop(self.head + '测试跑不起来——' + _fatal_text(self.root, fatal), 2)


def _counts(run):
    by = {}
    for c in run.cases:
        by[c['outcome']] = by.get(c['outcome'], 0) + 1
    return by


# ───────────────────────── 1. test_report ─────────────────────────

def _failure_block(root, index, fail, more):
    lines = ['[%d] %s %s' % (index, WORD[fail['kind']], fail['name'])]
    msg = [x for x in fail['msg'].split('\n')]
    shown = msg[:6]
    lines.append('    %s: %s' % (fail['type'], _cut(shown[0], 400)) if shown and shown[0] else '    ' + fail['type'])
    lines.extend('    ' + _cut(x, 200) for x in shown[1:])
    if len(msg) > 6:
        lines.append('    …（异常信息共 %d 行）' % len(msg))
    frames = fail['frames']
    if frames:
        rel, line, func = frames[-1]
        chain = ' → '.join('%s:%d' % (f[0], f[1]) for f in frames[-4:])
        lines.append('    最内层仓库内帧 %s:%d (%s)%s' % (rel, line, func, '；调用链 ' + chain if len(frames) > 1 else ''))
        lines.extend(_context(root, rel, line, '    '))
    else:
        lines.append('    栈里没有仓库内的帧')
    if more:
        lines.append('    （该用例另有 %d 个子失败）' % more)
    return '\n'.join(lines)


def test_report(ctx, case, limit):
    if ctx.style == 'script':
        return _script_report(ctx, case, limit)
    run = _run_unittest(ctx.root, ctx.test, case, ctx.budget, ctx.work)
    if run.fatal:
        ctx.cannot_run(run.fatal)
    by = _counts(run)
    note = run.partial()
    if not run.failed and not note:
        return '%s全部通过（unittest，%d 个用例%s）' % (ctx.head, len(run.cases), '，其中跳过 %d' % by['skip'] if by.get('skip') else '')
    out = ['%sunittest，跑了 %d/%s 个用例：通过 %d，失败 %d，出错 %d，跳过 %d' % (
        ctx.head, len(run.cases), run.total, by.get('pass', 0), by.get('fail', 0), by.get('error', 0), by.get('skip', 0))]
    if note:
        out.append('注意：' + note)
    size = sum(len(x) + 1 for x in out)
    shown = 0
    for c in run.failed[:limit]:
        block = _failure_block(ctx.root, shown + 1, c['fails'][0], len(c['fails']) - 1)
        if size + len(block) > OUT_MAX - 600:
            break
        out.append(block)
        size += len(block) + 1
        shown += 1
    rest = run.failed[shown:]
    if rest:
        out.append(_cut('其余 %d 个失败未展开：%s' % (len(rest), '，'.join(c['id'] for c in rest)), 500))
    return '\n'.join(out)


def _script_report(ctx, case, limit):
    r = _run_script(ctx.root, ctx.rel, ctx.budget, ctx.work)
    lines = r['lines']
    notes = []
    if case:
        notes.append('脚本式测试没有独立用例，case 被忽略')
    if r['timed_out']:
        notes.append('到时限被中止，下面是已输出的部分；可用 job 启动')
    if not lines and r['rc'] != 0 and not r['timed_out']:
        raise Stop('%s测试跑不起来——脚本没有任何输出，退出码 %s' % (ctx.head, r['rc']), 2)
    count = '通过 %d，失败 %d' % (r['passed'], r['failed']) + ('' if r['summary'] else '（按 ✓/✗ 行计数，脚本没有打印汇总）')
    if r['rc'] == 0 and not r['failed'] and not r['marks']:
        return '%s全部通过（脚本式，%s）' % (ctx.head, count) + ''.join('\n注意：' + x for x in notes)
    out = ['%s脚本式测试（没有独立用例），%s，退出码 %s' % (ctx.head, count, '无（超时）' if r['timed_out'] else r['rc'])]
    out.extend('注意：' + x for x in notes)
    marks = r['marks']
    if marks:
        # 所有 ✗ 行都列；前 limit 处连同其后最多 3 行详情，其余只列这一行；篇幅不够时说明还剩几处
        out.append('✗ 行共 %d 处（L 是输出里的行号；前 %d 处带其后的详情行）：' % (len(marks), min(limit, len(marks))))
        size = sum(len(x) + 1 for x in out)
        for n, i in enumerate(marks):
            rows = ['  L%d %s' % (i + 1, _cut(lines[i].strip(), 400 if n < limit else 160))]
            for j in range(i + 1, min(i + 4, len(lines)) if n < limit else 0):
                if '✗' in lines[j] or '✓' in lines[j] or _SUM[0].search(lines[j]) or _SUM[1].search(lines[j]):
                    break
                if lines[j].strip():
                    rows.append('       ' + _cut(lines[j].rstrip(), 300))
            size += sum(len(x) + 1 for x in rows)
            if size > OUT_MAX - 1500:
                out.append('  …篇幅所限，还有 %d 处 ✗ 未列出' % (len(marks) - n))
                break
            out.extend(rows)
    exc = r['exc']
    if exc:
        out.append('脚本以异常结束：%s%s' % (exc['type'], ': ' + exc['msg'] if exc['msg'] else ''))
        if exc['frames']:
            rel, line, func = exc['frames'][-1]
            out.append('    最内层仓库内帧 %s:%d (%s)' % (rel, line, func))
            out.extend(_context(ctx.root, rel, line))
    if not marks and not exc:
        out.append('没有 ✗ 行，输出末尾：')
        out.extend('  | ' + _cut(x.rstrip(), 200) for x in lines[-10:])
    return '\n'.join(out)


# ───────────────────────── 2. locate ─────────────────────────

def locate(ctx, paths, limit):
    if ctx.style == 'script':
        return ctx.head + '不支持——locate 要逐用例比较覆盖，只支持 unittest 风格；这是脚本式测试（没有独立用例），请用 test_report。'
    scope = sorted({ctx.inside(p, 'paths') for p in paths if p})
    run = _run_unittest(ctx.root, ctx.test, '', ctx.budget, ctx.work, mode='cover', scope=scope)
    if run.fatal:
        ctx.cannot_run(run.fatal)
    nf, np_ = len(run.failed), len(run.passed)
    note = run.partial()
    tail = '\n注意：' + note if note else ''
    if not nf:
        return '%s排不出可疑行——%d 个用例没有失败的（通过 %d）；可疑度要靠失败用例覆盖到的行来算。%s' % (ctx.head, len(run.cases), np_, tail)
    if not np_:
        return ('%s排不出可疑行——%d 个失败用例，没有通过用例做对比；这时失败用例走过的每一行得分都一样，排名没有意义。'
                '先用 test_report 看出错位置。%s' % (ctx.head, nf, tail))
    stat = {}
    for group, cases in ((0, run.failed), (1, run.passed)):
        for c in cases:
            for rel, lines in c.get('cov', {}).items():
                for line in lines:
                    stat.setdefault((rel, line), [0, 0])[group] += 1
    rows = sorted(((ef / math.sqrt(nf * (ef + ep)), ef, ep, rel, line) for (rel, line), (ef, ep) in stat.items() if ef),
                  key=lambda r: (-r[0], -r[1], r[2], r[3], r[4]))
    where = '、'.join(s or '.' for s in scope) if scope else '仓库内非 tests 的 .py'
    out = ['%sOchiai 可疑度 = 失败覆盖 / sqrt(失败用例数 × (失败覆盖 + 通过覆盖))；用例 %d（失败 %d，通过 %d）；范围：%s' % (
        ctx.head, len(run.cases), nf, np_, where)]
    if note:
        out.append('注意：' + note + '；排名只基于已跑完的用例')
    out.append(_cut('失败用例：' + '，'.join('%s (%s)' % (c['id'], c['fails'][0]['type'] if c['fails'] else '?') for c in run.failed[:6])
                    + (' 等 %d 个' % nf if nf > 6 else ''), 700))
    if not rows:
        out.append('排不出可疑行——失败用例没有执行到统计范围内的任何行（可能错在测试本身、子进程里，或要用 paths 换范围）。')
        return '\n'.join(out)
    for i, (score, ef, ep, rel, line) in enumerate(rows[:limit], 1):
        out.append('%2d. %s:%d  %.3f  失败 %d/%d  通过 %d/%d  | %s' % (i, rel, line, score, ef, nf, ep, np_, _source_line(ctx.root, rel, line)))
    if len(rows) > limit:
        same = sum(1 for r in rows[limit:] if abs(r[0] - rows[limit - 1][0]) < 1e-12)
        out.append('（共 %d 行被失败用例覆盖%s；同分的行按文件、行号排）' % (len(rows), '，其中 %d 行与第 %d 名同分未列出' % (same, limit) if same else ''))
    return '\n'.join(out)


# ───────────────────────── 3. probe ─────────────────────────

def _executable_lines(path):
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            code = compile(f.read(), path, 'exec')
    except (SyntaxError, ValueError, OSError):
        return None
    found, todo = set(), [code]
    while todo:
        c = todo.pop()
        found.update(line for _, _, line in c.co_lines() if line)
        todo.extend(k for k in c.co_consts if hasattr(k, 'co_lines'))
    return found


def _uniq(values):
    return list(dict.fromkeys(values))


def _values(values):
    return '[' + ', '.join(_cut(v, 60) for v in values[:4]) + (' …共 %d 个' % len(values) if len(values) > 4 else '') + ']'


def probe(ctx, case, at, exprs, limit):
    if ctx.style == 'script':
        return ctx.head + '不支持——probe 只支持 unittest 风格；这是脚本式测试（没有独立用例）。'
    at, exprs = _uniq(x for x in at if x), _uniq(x.strip() for x in exprs if x.strip())
    if not at or not exprs:
        raise Stop(ctx.head + '参数不对——at 和 exprs 都至少要一个', 2)
    if len(at) > 8 or len(exprs) > 8:
        raise Stop(ctx.head + '参数不对——at、exprs 各最多 8 个', 2)
    for e in exprs:     # 先全部过白名单，任何一个不合格就不运行测试
        try:
            check_expr(e)
        except ValueError as err:
            raise Stop('%s拒绝执行——表达式 %r 不在白名单内：%s。只允许变量名、属性（不含双下划线名）、常量或变量名下标、常量、len(x)、type(x)。测试没有运行。'
                       % (ctx.head, _cut(e, 80), err), 2) from None
    if case.startswith('test') and '.' not in case:
        try:
            with open(ctx.test, encoding='utf-8') as source:
                tree = ast.parse(source.read())
            choices = [c.name + '.' + m.name for c in ast.walk(tree) if isinstance(c, ast.ClassDef)
                       for m in c.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and m.name == case]
        except (OSError, SyntaxError):
            choices = []
        if len(choices) > 1:
            raise Stop(ctx.head + 'case 有多个候选：' + ', '.join(choices), 2)
        if choices:
            case = choices[0]
    places = []
    for item in at:
        m = re.fullmatch(r'(.+):(\d+)', item)
        if not m or '..' in m.group(1).split('/'):
            raise Stop('%s参数不对——at 要写成 相对路径:行号，收到 %r' % (ctx.head, _cut(item, 80)), 2)
        value, line = m.group(1), int(m.group(2))
        candidates = [value] if os.path.isabs(value) else [os.path.join(ctx.root, value), os.path.join(os.path.dirname(ctx.test), value)]
        tried = []
        for candidate in candidates:
            rel = ctx.inside(candidate, 'at')
            full = os.path.join(ctx.root, rel)
            tried.append(full)
            if os.path.isfile(full):
                break
        else:
            raise Stop('%s参数不对——at 的文件不存在，试过：%s；例如 tools/cmd.py:24' % (ctx.head, ', '.join(tried)), 2)
        with open(full, encoding='utf-8', errors='replace') as f:
            total = len(f.read().split('\n'))
        if not 1 <= line <= total:
            raise Stop('%s参数不对——%s 只有 %d 行，没有第 %d 行' % (ctx.head, rel, total, line), 2)
        places.append((rel, line))
    run = _run_unittest(ctx.root, ctx.test, case, ctx.budget, ctx.work, mode='probe', at=places, exprs=exprs, limit=limit)
    if run.fatal:
        ctx.cannot_run(run.fatal)
    out = ['%s用例 %d（失败 %d，通过 %d）；取的是该行执行之前的值；!X 表示求值时抛 X' % (ctx.head, len(run.cases), len(run.failed), len(run.passed))]
    if run.partial():
        out.append('注意：' + run.partial())
    sources = [dict(id=None, outcome=None, hits=(run.outside or {}).get('hits', []), nhit=(run.outside or {}).get('nhit', {}))] + run.cases
    room = (OUT_MAX - 400) // len(places)
    for i, (rel, line) in enumerate(places):
        hits = [(c['id'], c['outcome'], vals) for c in sources for k, vals in c.get('hits', []) if k == i]
        total = sum(c.get('nhit', {}).get(str(i), 0) for c in sources)
        title = '== %s:%d | %s' % (rel, line, _source_line(ctx.root, rel, line))
        if not hits:
            lines = _executable_lines(os.path.join(ctx.root, rel))
            hint = '测试没有执行到这一行'
            if lines is not None and line not in lines:
                near = sorted(lines, key=lambda n: (abs(n - line), n))[:2]
                hint = '这一行不是可执行语句的起始行' + ('，附近的可执行行：' + '、'.join(str(n) for n in sorted(near)) if near else '')
            out.append('%s\n   未命中：%s' % (title, hint))
            continue
        bad = [h for h in hits if h[1] in BAD]
        good = [h for h in hits if h[1] == 'pass']
        chosen = set(range(len(hits)))
        if len(hits) > limit:       # 显示名额先在失败 / 通过两组间平分，再按命中次序补满
            picked_bad = [n for n, h in enumerate(hits) if h[1] in BAD][:limit // 2]
            picked_good = [n for n, h in enumerate(hits) if h[1] == 'pass'][:limit - len(picked_bad)]
            chosen = set(picked_bad + picked_good)
            for n in range(len(hits)):
                if len(chosen) >= limit:
                    break
                chosen.add(n)
        block = ['%s   命中 %d 次，记录 %d 次，显示 %d 次' % (title, total, len(hits), len(chosen))]
        diff = []
        if bad and good:
            for j, e in enumerate(exprs):
                fv, pv = _uniq(h[2][j] for h in bad), _uniq(h[2][j] for h in good)
                if set(fv) != set(pv):
                    only_f, only_p = [v for v in fv if v not in pv], [v for v in pv if v not in fv]
                    both = [v for v in fv if v in pv]
                    diff.append(_cut('   %s：仅失败组 %s；仅通过组 %s%s' % (
                        _cut(e, 60), _values(only_f), _values(only_p), '；两组都有 ' + _values(both) if both else ''), max(120, room // 3 // len(exprs))))
            block.append('   通过 / 失败两组取值不同的表达式（失败组 %d 次命中，通过组 %d 次）：' % (len(bad), len(good)) if diff
                         else '   通过 / 失败两组都命中了这里，各表达式的取值集合相同')
            block.extend(diff)
        elif bad or good:
            block.append('   只有%s用例命中这里，没有另一组可比' % ('失败' if bad else '通过'))
        used = sum(len(x) + 1 for x in block)
        dropped = 0
        for n, (cid, outcome, vals) in enumerate(hits):
            if n not in chosen:
                continue
            who = '%s [%s]' % (cid, WORD[outcome]) if cid else '（导入时或用例之外）'
            row = _cut(' #%d %s  %s' % (n + 1, who, ' ; '.join('%s=%s' % p for p in zip(exprs, vals))), 420)
            if used + len(row) > room:
                dropped += 1
                continue
            block.append(row)
            used += len(row) + 1
        if dropped:
            block.append('   （另有 %d 次命中因篇幅未显示，可减少 at / exprs 或调小 limit）' % dropped)
        out.append('\n'.join(block))
    return '\n'.join(out)


# ───────────────────────── 4. blame_change ─────────────────────────

def _git(root, *args, text=True):
    """只做读操作；GIT_OPTIONAL_LOCKS=0 保证连索引刷新都不写。"""
    p = subprocess.run(['git', '-c', 'core.quotepath=false', *args], cwd=root, stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, env=dict(os.environ, GIT_OPTIONAL_LOCKS='0'))
    out = p.stdout.decode('utf-8', 'surrogateescape') if text else p.stdout
    return p.returncode, out


def _sides(body):
    old, new, last = [], [], ()
    for b in body:
        if b.startswith('\\'):       # “\ No newline at end of file”
            for side in last:
                side[-1] = side[-1][:-1]
            continue
        line = b[1:] + '\n'
        if b[:1] == '-':
            old.append(line)
            last = (old,)
        elif b[:1] == '+':
            new.append(line)
            last = (new,)
        else:
            old.append(line)
            new.append(line)
            last = (old, new)
    return old, new


def parse_diff(text):
    """把 git diff 拆成文件和 hunk。返回 [{file, new, deleted, binary, hunks:[{header, os, ol, ns, nl, body, old, new}]}]。"""
    files, cur = [], None
    lines = text.split('\n')
    i = 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith('diff --git '):
            rest = ln[len('diff --git a/'):]
            cur = dict(file=rest[:(len(rest) - 3) // 2], new=False, deleted=False, binary=False, hunks=[])
            files.append(cur)
        elif cur is None:
            pass
        elif ln.startswith('new file mode'):
            cur['new'] = True
        elif ln.startswith('deleted file mode'):
            cur['deleted'] = True
        elif ln.startswith('Binary files ') or ln.startswith('GIT binary patch'):
            cur['binary'] = True
        elif ln.startswith('@@ '):
            m = re.match(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@', ln)
            if m:
                o_start, n_start = int(m.group(1)), int(m.group(3))
                o_len = 1 if m.group(2) is None else int(m.group(2))
                n_len = 1 if m.group(4) is None else int(m.group(4))
                body, co, cn = [], 0, 0
                i += 1
                while i < len(lines) and (co < o_len or cn < n_len or lines[i].startswith('\\')):
                    b = lines[i]
                    if not b.startswith('\\'):
                        co += b[:1] != '+'
                        cn += b[:1] != '-'
                    body.append(b)
                    i += 1
                old, new = _sides(body)
                cur['hunks'].append(dict(header=ln, os=o_start, ol=o_len, ns=n_start, nl=n_len, body=body, old=old, new=new))
                continue
        i += 1
    return files


def apply_hunks(base, hunks):
    """在 HEAD 版本的文本上套用选中的若干 hunk（各 hunk 的旧行范围互不重叠，从后往前换）。"""
    lines = re.findall(r'[^\n]*\n|[^\n]+', base)
    for h in sorted(hunks, key=lambda h: -h['os']):
        at = h['os'] - 1 if h['ol'] else h['os']
        if lines[at:at + len(h['old'])] != h['old']:
            raise ValueError('hunk 与 HEAD 内容对不上：' + h['header'])
        lines[at:at + len(h['old'])] = h['new']
    return ''.join(lines)


def ddmin(items, test):
    """Zeller 的 ddmin：test(子集) 返回 'fail' 才算复现。是生成器：每轮先交出当前集合，最后一个是 1-最小的子集；
    test 中途抛异常时，调用方手里留着的就是已缩小到的集合。"""
    cur, n = list(items), 2
    while len(cur) >= 2:
        size = len(cur)
        bounds = [size * k // n for k in range(n + 1)]
        subsets = [cur[bounds[k]:bounds[k + 1]] for k in range(n)]
        yield cur
        reduced = False
        for s in subsets:
            if test(s) == 'fail':
                cur, n, reduced = s, 2, True
                break
        if not reduced and n > 2:
            for s in subsets:
                rest = [x for x in cur if x not in s]
                if test(rest) == 'fail':
                    cur, n, reduced = rest, max(n - 1, 2), True
                    break
        if not reduced:
            if n >= size:
                break
            n = min(size, n * 2)
    yield cur


class _Limit(Exception):
    pass


def _signature(ctx, root, test, rel, case, timeout=None):
    """跑一次测试，返回 (失败特征, 一句描述)。特征：{} = 通过；None = 未判定；否则 {用例或标记: 异常类型}。"""
    if ctx.style == 'script':
        r = _run_script(root, rel, ctx.budget, ctx.work, timeout)
        if r['timed_out']:
            return None, '超时'
        if r['marks'] or r['failed']:
            return {'(✗)': '✗'}, '%d 处 ✗' % (len(r['marks']) or r['failed'])
        if r['rc'] == 0:
            return {}, '通过'
        if r['exc']:
            return {'(脚本)': r['exc']['type']}, '%s: %s' % (r['exc']['type'], _cut(r['exc']['msg'], 200))
        return {'(退出码)': str(r['rc'])}, '退出码 %s' % r['rc']
    run = _run_unittest(root, test, case, ctx.budget, ctx.work, timeout=timeout)
    if run.fatal:
        if not run.fatal.get('type'):
            return None, run.fatal['msg']
        return {'(导入)': run.fatal['type']}, '%s%s: %s' % (run.fatal.get('stage', ''), run.fatal['type'], _cut(run.fatal['msg'], 200))
    sig = {c['id']: (c['fails'][0]['type'] if c['fails'] else '?') for c in run.failed}
    if not sig:
        return ({}, '通过') if run.done else (None, run.partial())
    return sig, _cut('，'.join('%s (%s)' % kv for kv in list(sig.items())[:4]) + (' 等 %d 个' % len(sig) if len(sig) > 4 else ''), 400)


def _chunk_text(chunk, max_lines):
    if chunk['kind'] == 'file':
        body = ['+' + x for x in chunk['preview']]
        head = '%s（%s）' % (chunk['file'], chunk['what'])
    else:
        h = chunk['hunk']
        body = h['body']
        old = '行 %d-%d' % (h['os'], h['os'] + h['ol'] - 1) if h['ol'] else '第 %d 行之后' % h['os']
        new = '行 %d-%d' % (h['ns'], h['ns'] + h['nl'] - 1) if h['nl'] else '（删除）'
        head = '%s HEAD %s → 工作区 %s%s' % (chunk['file'], old, new, '（%s）' % chunk['what'] if chunk['what'] else '')
    lines = [head] + ['    ' + _cut(x, 160) for x in body[:max_lines]]
    if len(body) > max_lines:
        lines.append('    …（共 %d 行）' % len(body))
    return lines


def blame_change(ctx, case, paths, max_runs):
    root = ctx.root
    rc, top = _git(root, 'rev-parse', '--show-toplevel')
    if rc or os.path.realpath(top.strip()) != root:
        raise Stop(ctx.head + '做不了——当前目录不是 Git 仓库的根目录', 2)
    if _git(root, 'rev-parse', '--verify', '-q', 'HEAD')[0]:
        raise Stop(ctx.head + '做不了——仓库还没有任何提交', 2)

    def in_head(rel):
        return _git(root, 'cat-file', '-e', 'HEAD:' + rel)[0] == 0

    counts = {'pass': 0, 'fail': 0, 'unres': 0}
    state = dict(runs=0, slowest=0.0)

    def measured(*args, **kwargs):
        started = time.monotonic()
        state['runs'] += 1
        result = _signature(ctx, *args, **kwargs)
        state['slowest'] = max(state['slowest'], time.monotonic() - started)
        return result

    def ran():
        return '跑了 %d 次测试' % state['runs']

    # 前提一：工作区失败
    orig, orig_text = measured(root, ctx.test, ctx.rel, case)
    if orig is None:
        raise Stop('%s测试跑不起来——在工作区：%s' % (ctx.head, orig_text), 2)
    if not orig:
        return '%s前提不成立——测试在工作区是通过的，没有要归因的失败。（%s）' % (ctx.head, ran())

    rc, diff = _git(root, '-c', 'diff.noprefix=false', '-c', 'diff.mnemonicprefix=false', 'diff', '--no-color',
                    '--no-ext-diff', '--no-renames', 'HEAD')
    if rc:
        raise Stop(ctx.head + '做不了——git diff 失败', 2)
    files, chunks, base_files, notes = {}, [], [], []

    def whole_file(rel, what):
        full = os.path.join(root, rel)
        data = None
        if os.path.isfile(full):
            with open(full, 'rb') as f:
                data = f.read()
        preview = [] if data is None or b'\0' in data[:4096] else data.decode('utf-8', 'replace').split('\n')[:400]
        files[rel] = dict(kind='file', work=data)
        chunks.append(dict(file=rel, kind='file', what=what, preview=preview))

    for f in parse_diff(diff):
        rel = f['file']
        if f['binary']:
            whole_file(rel, '二进制文件，整个算一块')
        elif f['hunks']:
            if rel == ctx.rel and f['new']:
                base_files.append(rel)      # 测试文件本身是新加的：算基线，不参与缩小
                continue
            files[rel] = dict(kind='text', deleted=f['deleted'], new=f['new'])
            what = '新文件' if f['new'] else '删除文件' if f['deleted'] else ''
            chunks.extend(dict(file=rel, kind='hunk', what=what, hunk=h) for h in f['hunks'])
    extras = []
    for p in paths:
        if not p:
            continue
        rel = ctx.inside(p, 'paths')
        if not os.path.isfile(os.path.join(root, rel)):
            raise Stop('%s参数不对——paths 里要给文件：%s' % (ctx.head, rel), 2)
        if rel == ctx.rel or rel in files or rel in base_files or in_head(rel):
            continue        # 已入库的文件，其改动已经在 diff 里
        extras.append(rel)
    extras = sorted(set(extras))
    if not in_head(ctx.rel) and ctx.rel not in base_files:
        base_files.append(ctx.rel)
    if base_files:
        notes.append('测试文件 %s 未入库，已作为基线带入副本' % ctx.rel)
    rc, others = _git(root, 'ls-files', '--others', '--exclude-standard')
    carried = set(extras) | set(base_files)
    ignored = 0 if rc else sum(1 for x in others.split('\n') if x and x not in carried)
    if ignored:
        notes.append('另有 %d 个未入库文件没有带入副本（只带 paths 里给的），结论不包含它们的影响' % ignored)
    if not chunks and not extras:
        return '%s前提不成立——工作区相对 HEAD 没有未提交改动（未入库文件要用 paths 带入）。（%s）' % (ctx.head, ran())

    copy = os.path.realpath(tempfile.mkdtemp(prefix='dbg_head_'))
    try:
        archive = subprocess.Popen(['git', 'archive', '--format=tar', 'HEAD'], cwd=root, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, env=dict(os.environ, GIT_OPTIONAL_LOCKS='0'))
        untar = subprocess.run(['tar', '-x', '-C', copy], stdin=archive.stdout, stderr=subprocess.DEVNULL)
        archive.stdout.close()
        if archive.wait() or untar.returncode:
            raise Stop(ctx.head + '做不了——无法导出 HEAD', 2)

        def put_file(rel, data):
            target = os.path.join(copy, rel)
            if data is None:
                if os.path.lexists(target):
                    os.remove(target)
                return
            os.makedirs(os.path.dirname(target), exist_ok=True)
            fresh = not os.path.exists(target)
            with open(target, 'wb') as f:
                f.write(data)
            if fresh and os.path.exists(os.path.join(root, rel)):
                shutil.copymode(os.path.join(root, rel), target)

        def carry(rel):
            with open(os.path.join(root, rel), 'rb') as f:
                put_file(rel, f.read())

        for rel in base_files:
            carry(rel)
        copy_test = os.path.join(copy, ctx.rel)

        # 前提二：HEAD 上通过
        head_sig, head_text = measured(copy, copy_test, ctx.rel, case)
        if head_sig != {} and extras:
            # 退一步：照 test_at_head 的做法把 paths 的未入库文件都当基线再试
            for rel in extras:
                carry(rel)
            second, second_text = measured(copy, copy_test, ctx.rel, case)
            if second == {}:
                notes.append('不带 paths 的文件时 HEAD 上不通过（%s），所以这些文件算基线、不参与缩小：%s' % (head_text, '，'.join(extras)))
                head_sig, extras = second, []
            else:
                head_text = second_text
        if head_sig is None:
            return '%s做不了——测试在已提交版本（HEAD）上没能跑出结果：%s。（%s）' % (ctx.head, head_text, ran())
        if head_sig != {}:
            return ('%s前提不成立——测试在已提交版本（HEAD）上不通过：%s。失败不是未提交改动引起的，或者测试还依赖没带上的未入库文件（用 paths 带入）。（%s）'
                    % (ctx.head, head_text, ran()))
        for rel in extras:
            whole_file(rel, '未入库文件，整个算一块')
        if not chunks:
            return '%s前提不成立——除了当作基线的未入库文件，工作区相对 HEAD 没有别的改动。（%s）' % (ctx.head, ran())
        for n, c in enumerate(chunks):
            c['id'] = n
        for rel, info in files.items():
            target = os.path.join(copy, rel)
            info['orig'] = None
            if os.path.isfile(target):
                with open(target, 'rb') as f:
                    info['orig'] = f.read()
            info['chunks'] = [c for c in chunks if c['file'] == rel]

        def materialize(selected):
            for rel, info in files.items():
                chosen = [c for c in info['chunks'] if c['id'] in selected]
                if not chosen:
                    data = info['orig']
                elif info['kind'] == 'file':
                    data = info['work']
                elif info['deleted']:
                    data = None
                else:
                    base = (info['orig'] or b'').decode('utf-8', 'surrogateescape')
                    data = apply_hunks(base, [c['hunk'] for c in chosen]).encode('utf-8', 'surrogateescape')
                put_file(rel, data)

        cache = {}
        per_run = max(20.0, state['slowest'] * 3)

        def test(subset):
            key = frozenset(subset)
            if key in cache:
                return cache[key]
            if state['runs'] >= max_runs:
                raise _Limit('到运行次数上限 %d 次' % max_runs)
            if ctx.budget.left() < state['slowest'] + 8:
                raise _Limit('快到时限')
            try:
                materialize(key)
            except ValueError:
                verdict = 'unres'
            else:
                sig, _ = measured(copy, copy_test, ctx.rel, case, timeout=per_run)
                verdict = 'unres' if sig is None else 'pass' if not sig else \
                    'fail' if any(orig.get(k) == v for k, v in sig.items()) else 'unres'
            counts[verdict] += 1
            cache[key] = verdict
            return verdict

        ids = [c['id'] for c in chunks]
        current, why = ids, ''
        try:
            if test(ids) != 'fail':
                return ('%s做不了——在 HEAD 副本里套用全部 %d 块改动后没有复现工作区的失败（%s）。失败多半还依赖没带上的未入库文件，用 paths 带入。（%s）'
                        % (ctx.head, len(ids), orig_text, ran()))
            for current in ddmin(ids, test):
                pass
        except _Limit as e:
            why = str(e)
        tally = '%s（缩小过程中：通过 %d，复现失败 %d，未判定 %d）' % (ran(), counts['pass'], counts['fail'], counts['unres'])
        if why:
            out = ['%s未收敛——%s就停了，目前缩小到 %d 块（共 %d 块改动），真正的最小集合在这些块之内；%s。可调大 runs 或用 job 启动继续。'
                   % (ctx.head, why, len(current), len(ids), tally)]
        else:
            out = ['%s最小改动集合 %d 块（共 %d 块改动）%s；%s' % (
                ctx.head, len(current), len(ids), '，去掉其中任何一块都不再复现' if len(current) > 1 else '，只套用它就能复现失败', tally)]
        out.append('失败特征：' + orig_text)
        out.extend('注意：' + x for x in notes)
        picked = [c for c in chunks if c['id'] in set(current)]
        room = OUT_MAX - sum(len(x) + 1 for x in out) - 200
        per = max(6, min(40, 160 // max(1, len(picked))))
        for n, c in enumerate(picked, 1):
            lines = _chunk_text(c, per)
            lines[0] = '[%d] %s' % (n, lines[0])
            text = '\n'.join(lines)
            if len(text) > room:
                text = lines[0]
                if len(text) > room:
                    out.append('…其余 %d 块未列出' % (len(picked) - n + 1))
                    break
            out.append(text)
            room -= len(text) + 1
        return '\n'.join(out)
    finally:
        shutil.rmtree(copy, ignore_errors=True)


# ───────────────────────── 命令行入口 ─────────────────────────

OPTIONS = {'--case': 'one', '--limit': 'one', '--runs': 'one', '--budget': 'one',
           '--paths': 'many', '--at': 'many', '--exprs': 'many'}
USAGE = '用法：dbg.py test_report|locate|probe|blame_change <测试文件> [--case X] [--limit N] [--paths ...] [--at 文件:行 ...] [--exprs ...] [--runs N]'


def _parse(argv):
    """自己拆参数：many 型选项一直收到下一个选项名为止（表达式可以以 - 开头，不能交给 argparse）。"""
    positional, options, cur = [], {}, None
    for token in argv:
        if token in OPTIONS:
            cur = token
            options.setdefault(token, [])
        elif cur is None:
            positional.append(token)
        else:
            options[cur].append(token)
            if OPTIONS[cur] == 'one':
                cur = None
    return positional, options


def _int(options, key, default, low, high):
    raw = (options.get(key) or [''])[0]
    if raw == '':
        return default
    if not re.fullmatch(r'\d+', raw) or not low <= int(raw) <= high:
        raise Stop('参数不对——%s 要是 %d..%d 的整数' % (key, low, high), 2)
    return int(raw)


def main(argv):
    if len(argv) == 2 and argv[0] == '_child':
        return _child(argv[1])
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    ctx = None
    try:
        positional, options = _parse(argv[1:])
        if not argv or argv[0] not in ('test_report', 'locate', 'probe', 'blame_change') or len(positional) != 1:
            raise Stop(USAGE, 2)
        name = argv[0]
        case = (options.get('--case') or [''])[0]
        if case and not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.]*', case):
            raise Stop('参数不对——case 要写成 类名 或 类名.方法名', 2)
        seconds = _int(options, '--budget', 0, 1, 86400)
        ctx = Ctx(name, positional[0], Budget(seconds or None))
        paths = options.get('--paths', [])
        if name == 'test_report':
            text = test_report(ctx, case, _int(options, '--limit', 5, 1, 50))
        elif name == 'locate':
            text = locate(ctx, paths, _int(options, '--limit', 10, 1, 100))
        elif name == 'probe':
            text = probe(ctx, case, options.get('--at', []), options.get('--exprs', []), _int(options, '--limit', 20, 1, 200))
        else:
            text = blame_change(ctx, case, paths, _int(options, '--runs', 40, 4, 500))
        code = 0
    except Stop as e:
        text, code = e.text, e.code
    finally:
        if ctx is not None:
            shutil.rmtree(ctx.work, ignore_errors=True)
    if len(text) > OUT_MAX:
        text = text[:OUT_MAX] + '\n…（输出过长，已截断）'
    sys.stdout.write(text.rstrip('\n') + '\n')
    sys.stdout.flush()
    return code


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
