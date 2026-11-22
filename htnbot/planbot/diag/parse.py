"""Parsing helpers for the adapter layer: text cleaning, expression whitelist, path normalisation.

Standard library only. Every function here is total: it never raises.
"""
import ast
import math
import os
import posixpath
import re

_SURROGATES = re.compile('[\ud800-\udfff]')
_EXPR_MAX_LEN = 80
_CALL_NAMES = ('len', 'type')


def clean_text(text, limit=None):
    """str(text) with lone surrogates replaced by '?', optionally truncated to `limit` chars."""
    try:
        out = _SURROGATES.sub('?', str(text))
    except Exception:
        return ''
    if isinstance(limit, int) and not isinstance(limit, bool) and len(out) > limit:
        out = out[:limit - 3] + '...' if limit > 3 else '...'[:max(limit, 0)]
    return out


def _is_int_const(node):
    return isinstance(node, ast.Constant) and type(node.value) is int


def _is_index(node):
    if hasattr(ast, 'Index') and isinstance(node, ast.Index):  # Python 3.8 wrapper
        node = node.value
    if isinstance(node, ast.Constant):
        return type(node.value) in (int, str)
    return (isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub)
            and _is_int_const(node.operand))


def _ok(node):
    if isinstance(node, ast.Name):
        return True
    if isinstance(node, ast.Attribute):
        return _ok(node.value)
    if isinstance(node, ast.Subscript):
        return _is_index(node.slice) and _ok(node.value)
    if isinstance(node, ast.Call):
        return (isinstance(node.func, ast.Name) and node.func.id in _CALL_NAMES
                and len(node.args) == 1 and not node.keywords
                and not isinstance(node.args[0], ast.Starred) and _ok(node.args[0]))
    return False


def safe_expr(text):
    """True if `text` is a whitelisted expression: names, attributes, constant subscripts, len(x), type(x)."""
    try:
        if not isinstance(text, str) or not text or len(text) > _EXPR_MAX_LEN:
            return False
        if _SURROGATES.search(text):
            return False
        return _ok(ast.parse(text, mode='eval').body)
    except Exception:
        return False


def norm_path(path, root=None):
    """Canonical root-relative POSIX path, or None if it cannot be normalised or leaves the root."""
    try:
        if not isinstance(path, str) or not path or '\0' in path or _SURROGATES.search(path):
            return None
        path = path.replace('\\', '/')
        if root is None:
            if path.startswith('/'):
                return None
            norm = posixpath.normpath(path)
            if norm in ('.', '..') or norm.startswith('../'):
                return None
            return norm
        if not isinstance(root, str) or '\0' in root or _SURROGATES.search(root):
            return None
        full = path if os.path.isabs(path) else os.path.join(root, path)
        real = os.path.realpath(full)
        real_root = os.path.realpath(root)
        prefix = real_root if real_root.endswith(os.sep) else real_root + os.sep
        if not real.startswith(prefix):
            return None
        rel = real[len(prefix):]
        return rel.replace(os.sep, '/') if rel else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# test-run result / failure report parsing
# ---------------------------------------------------------------------------

_SUMMARY_MAX = 200
_UNITTEST_HEAD = re.compile(r'^(?:FAIL|ERROR): (\S+) \(([\w.]+)\)', re.M)
_PYTEST_HEAD = re.compile(r'^(?:FAILED|ERROR) (\S+::\S+)', re.M)
_SUMMARY_LINE = re.compile(
    r'^(?:FAILED \(.*\)|OK(?: \(.*\))?|=+ .* in [\d.]+s.* =+|\d+ (?:passed|failed|error).* in [\d.]+s.*)\s*$')
_REPORT_HEAD = re.compile(r'^\[\d+\]\s+(?:失败|出错)\s+(.+?)\s*$')
_EXC_LINE = re.compile(r'^([A-Za-z_][\w.]*)(?::[ ]?(.*))?$')
_TRUNC_NOTE = re.compile(r'^\s*…（异常信息共 \d+ 行）\s*$')
_SUBFAIL_NOTE = re.compile(r'^\s*（该用例另有')
_FRAME_LINE = re.compile(r'^最内层仓库内帧 (\S+?):(\d+) \(([^)]*)\)(?:；调用链 (.*))?$')
_CODE_LINE = re.compile(r'^([> ])\s*(\d+)  (.*)$')
_CHAIN_TOKEN = re.compile(r'^(\S+?):(\d+)$')
_POS_LINE = re.compile(r'(?:最内层仓库内帧|位置)\s')
_POS_TOKEN = re.compile(r'([^\s:：；→()]+\.py):(\d+)')
_UNRUNNABLE_MARK = '测试跑不起来'


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _failed_ids(output):
    """Identifiers of failed test cases recognised in a runner's raw output."""
    ids = set()
    for name, paren in _UNITTEST_HEAD.findall(output):
        if '_FailedTest' in paren:
            continue  # a collection/import failure, not a test that ran
        ident = paren if paren.endswith('.' + name) else paren + '.' + name
        if ident.startswith('__main__.'):
            ident = ident[len('__main__.'):]
        ids.add(ident)
    ids.update(_PYTEST_HEAD.findall(output))
    return sorted(clean_text(i) for i in ids)


def _summary_line(output):
    lines = [ln.strip() for ln in output.splitlines() if ln.strip()]
    for ln in reversed(lines):
        if _SUMMARY_LINE.match(ln):
            return ln
    return lines[-1] if lines else ''


def parse_run_test(result):
    """RunInfo for a test-run result. Never raises."""
    try:
        if not isinstance(result, dict):
            return {'outcome': 'unrunnable', 'failed': [], 'summary': 'invalid result'}
        output = result.get('output')
        output = output if isinstance(output, str) else ''
        summary = clean_text(_summary_line(output), _SUMMARY_MAX)
        code = result.get('exit_code')
        if _is_int(code) and code == 0:
            return {'outcome': 'passed', 'failed': [], 'summary': summary}
        failed = _failed_ids(output)
        return {'outcome': 'failed' if failed else 'unrunnable', 'failed': failed, 'summary': summary}
    except Exception:
        return {'outcome': 'unrunnable', 'failed': [], 'summary': 'invalid result'}


def _frame(file, line, func='', code=''):
    try:
        n = int(line)
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    return {'file': clean_text(file), 'line': n, 'func': clean_text(func), 'code': clean_text(code)}


def _parse_block(test, body):
    """One failure from the indented lines following a '[n] 失败 name' header."""
    lines = [ln[4:] if ln.startswith('    ') else ln.lstrip() for ln in body]
    split = next((i for i, ln in enumerate(lines) if _FRAME_LINE.match(ln)), None)
    msg_lines = lines if split is None else lines[:split]
    msg_lines = [ln for ln in msg_lines if not _TRUNC_NOTE.match(ln) and not _SUBFAIL_NOTE.match(ln)]
    exc_type, message = '', '\n'.join(msg_lines).rstrip()
    if msg_lines:
        m = _EXC_LINE.match(msg_lines[0])
        if m:
            exc_type = m.group(1)
            message = '\n'.join([m.group(2) or ''] + msg_lines[1:]).rstrip()
    frames = []
    if split is not None:
        file, line, func, chain = _FRAME_LINE.match(lines[split]).groups()
        code = ''
        for ln in lines[split + 1:]:
            cm = _CODE_LINE.match(ln)
            if cm and cm.group(1) == '>':
                code = cm.group(3).strip()
                break
        for tok in (chain.split(' → ') if chain else []):
            cm = _CHAIN_TOKEN.match(tok.strip())
            if cm is None or cm.groups() == (file, line):
                continue  # the innermost frame is appended below with its func/code
            fr = _frame(cm.group(1), cm.group(2))
            if fr:
                frames.append(fr)
        inner = _frame(file, line, func, code)
        if inner:
            frames.append(inner)
    return {'test': clean_text(test), 'exc_type': clean_text(exc_type),
            'message': clean_text(message), 'frames': frames, 'assert_line': None}


def _same_file(frame_file, test_file):
    want = norm_path(test_file)
    if want is None:  # absolute test_file: only an identical absolute frame path matches
        return frame_file.replace('\\', '/') == test_file.replace('\\', '/')
    got = norm_path(frame_file)
    if got is not None:
        return got == want
    return frame_file.replace('\\', '/').endswith('/' + want)  # absolute path


def _location(output):
    """Last reported 'file:line' on a position line (innermost / last one), or None."""
    found = None
    for ln in output.splitlines():
        if _POS_LINE.search(ln):
            for file, line in reversed(_POS_TOKEN.findall(ln)):
                if int(line) > 0:
                    found = {'file': clean_text(file), 'line': int(line)}
                    break
    return found


def parse_report(result, test_file=''):
    """Report for a failure-report result. Never raises."""
    empty = {'unrunnable': False, 'location': None, 'failures': []}
    try:
        if not isinstance(result, dict) or not isinstance(result.get('output'), str):
            return empty
        output = result['output']
        blocks, current = [], None
        for ln in output.splitlines():
            m = _REPORT_HEAD.match(ln)
            if m:
                current = (m.group(1), [])
                blocks.append(current)
            elif current is not None and (ln.startswith(' ') or not ln.strip()):
                current[1].append(ln)
            else:
                current = None
        failures = [_parse_block(test, body) for test, body in blocks]
        if isinstance(test_file, str) and test_file:
            for f in failures:
                inside = [fr for fr in f['frames'] if _same_file(fr['file'], test_file)]
                f['assert_line'] = inside[-1] if inside else None
        if _UNRUNNABLE_MARK in output:
            return {'unrunnable': True, 'location': _location(output), 'failures': failures}
        return {'unrunnable': False, 'location': None, 'failures': failures}
    except Exception:
        return empty


# ---------------------------------------------------------------------------
# suspicious-line ranking / value-sampling result parsing
# ---------------------------------------------------------------------------

_LOC_ROW = re.compile(r'^\s*\d+\.\s+(\S+?):(\d+)(?=\s|\||$)(.*)$')
_LOC_SCORE = re.compile(r'^\s+(\d+(?:\.\d+)?)(?=\s|\||$)')
_LOC_FAIL = re.compile(r'失败\s*(\d+)')
_LOC_PASS = re.compile(r'通过\s*(\d+)')
_PROBE_HEAD = re.compile(r'^==\s+(\S+?:\d+)(?=\s|\||$)')
_PROBE_VAL = re.compile(r'^\s*#\d+\s+(.*)$')
_PROBE_FAILED_MARK = re.compile(r'求值(?:出错|失败|错误)|eval(?:uation)?\s+(?:error|failed)', re.I)
_PROBE_ERR_VALUE = re.compile(
    r'^(?:<[^>]*(?:error|exception|出错|失败|异常)[^>]*>|[A-Za-z_][\w.]*(?:Error|Exception)\b.*)$', re.I | re.S)
_PROBE_CASE = re.compile(
    r'[（(\[]\s*(?:用例|test)[ :：=]\s*(\S+?)\s+(失败|通过|fail(?:ed)?|pass(?:ed)?)\s*[)）\]]', re.I)
_PROBE_SPLIT = re.compile(r'^(.+?)\s*(?<![=!<>])=(?!=)\s*(.*)$', re.S)
_PROBE_MARK = re.compile(r' \[(失败|通过|出错)\](?=\s|$)')
_PROBE_OUTCOME = {'失败': 'fail', '出错': 'fail', '通过': 'pass'}


def _split_item(item):
    """(expr, value) cut at the first '=' that is not part of == != <= >=; None if there is none."""
    i = 0
    while i < len(item):
        if item[i] == '=':
            if item[i + 1:i + 2] == '=':
                i += 2
                continue
            if i > 0 and item[i - 1] in '!<>':
                i += 1
                continue
            return item[:i].strip(), item[i + 1:].strip()
        i += 1
    return None


def _probe_marked_entries(at, rest):
    """ProbeValues of a '<test> [失败|通过|出错]  e=v ; e=v' line; None if the line has no such mark."""
    m = _PROBE_MARK.search(rest)
    if not m:
        return None
    test = clean_text(rest[:m.start()].strip())
    outcome = _PROBE_OUTCOME[m.group(1)]
    out = []
    for item in rest[m.end():].strip().split(' ; '):
        pair = _split_item(item.strip())
        if pair is None or not pair[0]:
            continue
        out.append({'at': clean_text(at), 'expr': clean_text(pair[0]), 'value': clean_text(pair[1]),
                    'test': test, 'outcome': outcome})
    return out


def _output_of(result):
    if not isinstance(result, dict):
        return None
    output = result.get('output')
    return output if isinstance(output, str) else None


def parse_locate(result):
    """LocLine list for a suspicious-line ranking result (output order, first (file, line) wins). Never raises."""
    try:
        output = _output_of(result)
        if not output:
            return []
        rows, seen = [], set()
        for ln in output.splitlines():
            m = _LOC_ROW.match(ln)
            if not m:
                continue
            file, line, rest = m.group(1), int(m.group(2)), m.group(3)
            if line <= 0 or (file, line) in seen:
                continue
            seen.add((file, line))
            rest = rest.split('|', 1)[0]
            sm = _LOC_SCORE.match(rest)
            fm, pm = _LOC_FAIL.search(rest), _LOC_PASS.search(rest)
            rows.append({'file': clean_text(file), 'line': line,
                         'susp': float(sm.group(1)) if sm else None,
                         'fail': int(fm.group(1)) if fm else 0,
                         'passed': int(pm.group(1)) if pm else 0})
        peak = {}
        for r in rows:
            peak[r['file']] = max(peak.get(r['file'], 0), r['fail'])
        for r in rows:
            if r['susp'] is None:
                denom = peak[r['file']] * (r['fail'] + r['passed'])
                r['susp'] = r['fail'] / math.sqrt(denom) if denom > 0 else 0.0
        return rows
    except Exception:
        return []


def _probe_entry(at, rest):
    """ProbeValue for one '#n ...' line, or None if it is not a successful 'expr = value'."""
    if _PROBE_FAILED_MARK.search(rest):
        return None
    test = outcome = None
    cm = _PROBE_CASE.search(rest)
    if cm:
        test = clean_text(cm.group(1))
        outcome = 'fail' if cm.group(2).lower() in ('失败', 'fail', 'failed') else 'pass'
        rest = (rest[:cm.start()] + rest[cm.end():]).strip()
    sm = _PROBE_SPLIT.match(rest)
    if not sm:
        return None
    expr, value = sm.group(1).strip(), sm.group(2).strip()
    if not expr or _PROBE_ERR_VALUE.match(value):
        return None
    return {'at': clean_text(at), 'expr': clean_text(expr), 'value': clean_text(value),
            'test': test, 'outcome': outcome}


def parse_probe(result):
    """ProbeValue list for a value-sampling result (output order); failed evaluations dropped. Never raises."""
    try:
        output = _output_of(result)
        code = result.get('exit_code') if isinstance(result, dict) else None
        if not output or not _is_int(code) or code != 0:
            return []
        values, at = [], None
        for ln in output.splitlines():
            hm = _PROBE_HEAD.match(ln)
            if hm:
                at = hm.group(1)
                continue
            vm = _PROBE_VAL.match(ln)
            if vm and at is not None:
                marked = _probe_marked_entries(at, vm.group(1))
                if marked is not None:
                    values.extend(marked)
                    continue
                entry = _probe_entry(at, vm.group(1))
                if entry:
                    values.append(entry)
        return values
    except Exception:
        return []
