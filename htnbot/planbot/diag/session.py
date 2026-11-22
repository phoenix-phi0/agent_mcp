"""Diagnosis session: wraps the injected command runner, tracks per-file progress, builds findings."""

import ast
import json
import os
import re

from planbot.core import PlanbotError, load_domain, parse_task
from planbot.executor import dry_run_task, execute_task
from planbot.planner import allowed_actions
from planbot.diag.parse import (clean_text, norm_path, parse_locate, parse_probe, parse_report,
                                parse_run_test, safe_expr)
from planbot.diag.rank import needs_probe, probe_plan, rank, sample_plan

LOCATE_LIMIT = 50
_COMMANDS = ('run_test', 'test_report', 'locate', 'probe')
_NEWLINE = re.compile(r'\r\n|\r|\n')
_CONTEXT = 2
_SNIPPET_MAX = 160
_MESSAGE_MAX = 300
_MAX_CANDIDATES = 5
_PLAN_MAX = 8
_EMPTY_REPORT = {'unrunnable': False, 'location': None, 'failures': []}
_SKIPPED = 'skipped: test cannot run'
_BAD_RESULT = 'invalid runner result'
_SURROGATES = re.compile('[\ud800-\udfff]')
_SENSOR_CMD = 'diag_state'
_SUMMARY_MAX = 2500
_HINTS = {
    'passed': 'hint: test passes, nothing to fix.',
    'unrunnable': 'hint: the test cannot run; fix the reported location first.',
    'found': ('hint: candidates are ranked most suspicious first; lines marked >> are the suspects, '
              'check the top one against the exception before editing.'),
    'not_found': ('hint: no cause located; read the exception and failing test, '
                  'candidates (if any) are stack frames only.'),
}


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _valid(result):
    return (isinstance(result, dict) and isinstance(result.get('status'), str)
            and _is_int(result.get('exit_code')) and isinstance(result.get('output'), str))


def _yes(flag):
    return 'yes' if flag else 'no'


def _snippet(text, line):
    if text is None:
        return []
    lines = _NEWLINE.split(text)
    if lines and lines[-1] == '':
        lines.pop()
    first, last = max(1, line - _CONTEXT), min(len(lines), line + _CONTEXT)
    return [{'line': n, 'text': clean_text(lines[n - 1], _SNIPPET_MAX)}
            for n in range(first, last + 1)]


# ---- assert-variable rule ---------------------------------------------------

_FUNCS = (ast.FunctionDef, ast.AsyncFunctionDef)
_SCOPES = _FUNCS + (ast.ClassDef, ast.Lambda)
_ASSERT_VAR_MAX = 2
_CLAUSES = (ast.excepthandler,) + ((ast.match_case,) if hasattr(ast, 'match_case') else ())


def _test_func_name(test):
    """Last segment of a failure's test id, without a trailing ' (…)' or '[…]' part."""
    text = test if isinstance(test, str) else ''
    cuts = [i for i in (text.find(' ('), text.find('[')) if i >= 0]
    if cuts:
        text = text[:min(cuts)]
    parts = [p for p in re.split(r'::|\.', text.strip()) if p]
    return parts[-1] if parts else ''


def _end(node):
    return getattr(node, 'end_lineno', None) or node.lineno


def _inner_stmts(stmt):
    """Statements directly nested in a statement (blocks, handlers, match cases)."""
    for child in ast.iter_child_nodes(stmt):
        if isinstance(child, ast.stmt):
            yield child
        elif isinstance(child, _CLAUSES):
            yield from _inner_stmts(child)


def _own_exprs(stmt):
    """Expression children of a statement itself, not those of statements nested in it."""
    for child in ast.iter_child_nodes(stmt):
        if not isinstance(child, (ast.stmt,) + _CLAUSES):
            yield child


def _innermost_stmt(body, line):
    for stmt in body:
        if stmt.lineno <= line <= _end(stmt):
            if isinstance(stmt, _SCOPES):
                return None
            return _innermost_stmt(list(_inner_stmts(stmt)), line) or stmt
    return None


def _target_names(target):
    return [n.id for n in ast.walk(target) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)]


def _walk_expr(node):
    """Nodes of an expression, not entering lambdas."""
    stack = [node]
    while stack:
        cur = stack.pop()
        yield cur
        for child in ast.iter_child_nodes(cur):
            if not isinstance(child, ast.Lambda):
                stack.append(child)


def _bound_names(stmt):
    """Names a statement binds by itself (not through the statements nested in it)."""
    names = []
    if isinstance(stmt, ast.Assign):
        for target in stmt.targets:
            names += _target_names(target)
    elif isinstance(stmt, ast.AugAssign):
        names += _target_names(stmt.target)
    elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
        names += _target_names(stmt.target)
    elif isinstance(stmt, (ast.For, ast.AsyncFor)):
        names += _target_names(stmt.target)
    elif isinstance(stmt, (ast.With, ast.AsyncWith)):
        for item in stmt.items:
            if item.optional_vars is not None:
                names += _target_names(item.optional_vars)
    for expr in _own_exprs(stmt):
        for node in _walk_expr(expr):
            if isinstance(node, ast.NamedExpr):
                names.append(node.target.id)
    return names


def _assignments(body, before):
    """{name: greatest start line < before of a statement binding it}, nested blocks included."""
    best = {}
    for stmt in body:
        if isinstance(stmt, _SCOPES):
            continue
        if stmt.lineno < before:
            for name in _bound_names(stmt):
                best[name] = max(best.get(name, 0), stmt.lineno)
        for name, line in _assignments(list(_inner_stmts(stmt)), before).items():
            best[name] = max(best.get(name, 0), line)
    return best


def _assert_var_lines(rep, sources, test_file):
    """[(test_file, line)]: where the variables used by the failing assertion were last assigned."""
    failures = rep.get('failures') if isinstance(rep, dict) else None
    if not failures:
        return []
    first = failures[0]
    at = first.get('assert_line')
    text = sources.get(test_file)
    if not at or text is None:
        return []
    try:
        tree = ast.parse(text)
        line = at['line']
        name = _test_func_name(first.get('test'))
        funcs = [n for n in ast.walk(tree)
                 if isinstance(n, _FUNCS) and n.name == name and n.lineno <= line <= _end(n)]
        if not funcs:
            return []
        func = max(funcs, key=lambda n: n.lineno)
        stmt = _innermost_stmt(func.body, line)
        if stmt is None:
            return []
        used = []
        for expr in _own_exprs(stmt):
            for node in _walk_expr(expr):
                if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id not in used:
                    used.append(node.id)
        assigned = _assignments(func.body, stmt.lineno)
        rows = sorted({assigned[n] for n in used if n in assigned}, reverse=True)
    except Exception:
        return []
    return [(test_file, row) for row in rows[:_ASSERT_VAR_MAX]]


def _merge_assert_vars(R, A, rep, sources, test_file, probe_vals):
    """R with the assert-variable lines A folded in (see the session rules)."""
    if not A:
        return R
    R = [dict(c, reasons=list(c['reasons'])) for c in R]
    known = {(c['file'], c['line']): c for c in R}
    fresh = []
    for key in A:
        if key in known:
            if 'assert_var' not in known[key]['reasons']:
                known[key]['reasons'].append('assert_var')
        elif key not in fresh:
            fresh.append(key)
    if not fresh:
        return R
    failures = rep.get('failures') or []
    frames = failures[0]['frames'] if failures else []
    in_test = not any(fr['file'] in sources and fr['file'] != test_file for fr in frames)
    items = []
    for file, line in fresh:
        at = '%s:%d' % (file, line)
        items.append({'file': file, 'line': line, 'score': 0.0, 'reasons': ['assert_var'],
                      'snippet': _snippet(sources.get(file), line),
                      'probe': [{'expr': v['expr'], 'value': v['value']}
                                for v in probe_vals if v['at'] == at]})
    if in_test:
        result = items + R
        for item in items:
            item['score'] = R[0]['score'] if R else 0.0
    else:
        head = R[:_MAX_CANDIDATES - len(items)]
        result = head + items
        for i, item in enumerate(items):
            prev = len(head) + i - 1
            item['score'] = result[prev]['score'] if prev >= 0 else 0.0
    return result[:_MAX_CANDIDATES]


class _Progress:
    """State of one test file in the current round."""

    def __init__(self):
        self.ran = False
        self.result = 'none'
        self.start_round()

    def start_round(self):
        self.report = False
        self.locate = False
        self.locate_valid = False  # locate output had a valid line
        self.probe = False
        self.cause = False
        self.unrunnable = False
        self.failed = []          # failed test ids from run_test
        self.rep = None           # parsed report
        self.cands = []           # candidates of the found cause
        self.stack = []           # stack-frame candidates of the first failing test
        self.source = None
        self.sources = {}         # canonical file -> text (only files that could be read)
        self.tried = set()        # canonical files already read this round


class Session:
    """Wraps `runner(name, args) -> {status, exit_code, output}`; `run` is the cmd executor for planbot."""

    def __init__(self, runner, repo_root='.', allow_probe=True):
        self._runner = runner
        self._root = repo_root
        self._allow_probe = bool(allow_probe)
        self._files = {}
        self.calls = []

    # ---- entry point -------------------------------------------------

    def run(self, name, args):
        try:
            if name == 'diag_state':
                return self._diag_state()
            if name not in _COMMANDS:
                return {'status': 'error', 'exit_code': 2, 'output': 'unknown command'}
            if not isinstance(args, dict) or not isinstance(args.get('path'), str):
                return {'status': 'error', 'exit_code': 2, 'output': 'bad args'}
            path = args['path']
            prog = self._files.get(path)
            if prog is None:
                prog = self._files[path] = _Progress()
            handler = getattr(self, '_do_' + name)
            return handler(path, prog, args)
        except Exception as exc:  # last resort: run never raises
            return {'status': 'error', 'exit_code': 1, 'output': clean_text(exc) or _BAD_RESULT}

    # ---- runner access -------------------------------------------------

    def _call(self, name, args):
        """Call the runner and record it. Returns (result, ok); a bad result is the canonical failure."""
        try:
            result = self._runner(name, args)
            text = None if _valid(result) else _BAD_RESULT
        except Exception as exc:
            result = None
            text = clean_text(exc) or exc.__class__.__name__
        if text is not None:
            self.calls.append({'name': name, 'args': dict(args), 'status': 'error',
                               'exit_code': None, 'output': text})
            return {'status': 'error', 'exit_code': 1, 'output': text}, False
        self.calls.append({'name': name, 'args': dict(args), 'status': result['status'],
                           'exit_code': result['exit_code'], 'output': clean_text(result['output'])})
        return result, True

    # ---- commands ------------------------------------------------------

    def _diag_state(self):
        rows = [{'file': path, 'ran': _yes(p.ran), 'result': p.result, 'report': _yes(p.report),
                 'locate': _yes(p.locate), 'probe': _yes(p.probe), 'cause': _yes(p.cause)}
                for path, p in sorted(self._files.items())]
        return {'status': 'ok', 'exit_code': 0, 'output': json.dumps({'files': rows})}

    def _do_run_test(self, path, prog, args):
        result, ok = self._call('run_test', args)
        if ok:
            prog.start_round()
            info = parse_run_test(result)
            prog.ran = True
            prog.result = 'green' if info['outcome'] == 'passed' else 'red'
            prog.failed = list(info['failed'])
            prog.unrunnable = info['outcome'] == 'unrunnable'
        return result

    def _do_test_report(self, path, prog, args):
        result, ok = self._call('test_report', args)
        if not ok:
            return result
        prog.report = True
        test_file = norm_path(path, self._root)
        rep = parse_report(result, path if test_file is None else test_file)
        prog.rep = rep
        prog.stack = self._stack_candidates(prog, rep)
        if prog.unrunnable or rep['unrunnable']:
            prog.unrunnable = True
            loc = rep['location']
            if loc:
                first = self._candidate(prog, loc['file'], loc['line'], 1.0, ['unrunnable'])
                rest = [c for c in prog.stack if (c['file'], c['line']) != (first['file'], first['line'])]
                prog.cands = ([first] + rest)[:_MAX_CANDIDATES]
                prog.source = 'unrunnable'
                prog.cause = True
        return result

    def _probe_allowed(self):
        return self._allow_probe

    def _report(self, prog):
        return prog.rep if prog.rep is not None else _EMPTY_REPORT

    def _test_file(self, path):
        norm = norm_path(path, self._root)
        return path if norm is None else norm

    def _norm_lines(self, prog, lines):
        """Normalise LocLine files; the same (file, line) merges into one row. Files in the root get read."""
        merged = {}
        for row in lines:
            name, readable = self._resolve(row['file'])
            if readable:
                self._source(prog, name)
            key = (name, row['line'])
            if key in merged:
                old = merged[key]
                for field in ('susp', 'fail', 'passed'):
                    old[field] = max(old[field], row[field])
            else:
                merged[key] = {'file': name, 'line': row['line'], 'susp': row['susp'],
                               'fail': row['fail'], 'passed': row['passed']}
        return list(merged.values())

    def _matched(self, values, at, exprs):
        """Probe values whose position (file normalised) and expression were both sent."""
        sent_at, sent_exprs = set(at), set(exprs)
        out = []
        for v in values:
            file, sep, line = v['at'].rpartition(':')
            if not sep or not line.isdigit():
                continue
            name, _ = self._resolve(file)
            at = '%s:%d' % (name, int(line))
            if at in sent_at and v['expr'] in sent_exprs:
                out.append(dict(v, at=at))
        return out

    def _do_locate(self, path, prog, args):
        if prog.unrunnable:
            prog.locate = True
            return {'status': 'ok', 'exit_code': 0, 'output': _SKIPPED}
        sent_args = dict(args)
        sent_args['limit'] = LOCATE_LIMIT
        result, ok = self._call('locate', sent_args)
        if not ok:
            return result
        prog.locate = True
        lines = self._norm_lines(prog, parse_locate(result))
        if not any(row['fail'] >= 1 or row['susp'] > 0 for row in lines):
            return result
        prog.locate_valid = True
        rep, test_file = self._canonical_report(self._report(prog)), self._test_file(path)
        cands = rank(rep, lines, prog.sources, test_file)
        if self._probe_allowed() and needs_probe(cands):
            plan = sample_plan(rep, lines, cands, prog.sources, test_file)
            if plan['at'] and plan['exprs']:
                sent = {'path': path, 'at': plan['at'], 'exprs': plan['exprs']}
                probed, pok = self._call('probe', sent)
                values = self._matched(parse_probe(probed), plan['at'], plan['exprs']) if pok else []
                if values:
                    cands = rank(rep, lines, prog.sources, test_file, probes=values)
        if cands:
            prog.cands, prog.source, prog.cause = cands, 'locate', True
        return result

    def _do_probe(self, path, prog, args):
        short = None
        if prog.unrunnable:
            short = _SKIPPED
        elif not self._probe_allowed():
            short = 'probe not allowed'
        else:
            rep, test_file = self._canonical_report(self._report(prog)), self._test_file(path)
            plan = probe_plan(rep, [], prog.sources, test_file)
            at = plan['at'][:_PLAN_MAX]
            exprs = [e for e in plan['exprs'] if safe_expr(e)][:_PLAN_MAX]
            if not at or not exprs:
                short = 'no probe points'
        if short is not None:
            prog.probe = True
            return {'status': 'error', 'exit_code': 1, 'output': short}
        result, ok = self._call('probe', {'path': path, 'at': at, 'exprs': exprs})
        if not ok:
            return result
        prog.probe = True
        values = self._matched(parse_probe(result), at, exprs)
        if values:
            cands = [c for c in rank(rep, [], prog.sources, test_file, probes=values) if c['probe']]
            if cands:
                cands = self._with_assert_vars(prog, path, cands, values)
                prog.cands, prog.source, prog.cause = cands, 'probe', True
        return result

    # ---- paths and sources ---------------------------------------------

    def _resolve(self, file):
        """(name, readable): canonical name if inside the root, else the raw string and not readable."""
        norm = norm_path(file, self._root)
        return (norm, True) if norm is not None else (clean_text(file), False)

    def _source(self, prog, name):
        """Text of a canonical file, read at most once per round; None when unreadable."""
        if name not in prog.tried:
            prog.tried.add(name)
            try:
                with open(os.path.join(self._root, name), encoding='utf-8', errors='replace') as fh:
                    prog.sources[name] = fh.read()
            except Exception:
                pass
        return prog.sources.get(name)

    def _snippet(self, text, line):
        return _snippet(text, line)

    def _with_assert_vars(self, prog, path, cands, probe_vals):
        """Fold the assert-variable lines into `cands` (only when locate gave no valid line)."""
        if prog.locate_valid or prog.unrunnable or prog.rep is None or not prog.rep['failures']:
            return cands
        rep, test_file = self._canonical_report(prog.rep), self._test_file(path)
        if norm_path(path, self._root) is not None:
            self._source(prog, test_file)
        return _merge_assert_vars(cands, _assert_var_lines(rep, prog.sources, test_file),
                                  rep, prog.sources, test_file, probe_vals)

    def _candidate(self, prog, file, line, score, reasons):
        name, readable = self._resolve(file)
        text = self._source(prog, name) if readable else None
        return {'file': name, 'line': line, 'score': score, 'reasons': list(reasons),
                'snippet': self._snippet(text, line), 'probe': []}

    def _stack_candidates(self, prog, rep):
        """Frames of the first failing test, innermost first, de-duplicated, as candidates."""
        failures = rep['failures']
        frames = failures[0]['frames'] if failures else []
        out, seen = [], set()
        for fr in reversed(frames):
            cand = self._candidate(prog, fr['file'], fr['line'], 0.0, ['stack'])
            key = (cand['file'], cand['line'])
            if key not in seen:
                seen.add(key)
                out.append(cand)
        return out

    def _canonical_report(self, rep):
        """Copy of a report whose frame files are canonical names (as the loaded sources are keyed)."""
        def fix(frame):
            return dict(frame, file=self._resolve(frame['file'])[0])
        failures = [dict(f, frames=[fix(fr) for fr in f['frames']],
                         assert_line=fix(f['assert_line']) if f['assert_line'] else None)
                    for f in rep['failures']]
        return dict(rep, failures=failures)

    # ---- finding ---------------------------------------------------------

    def finding(self, path):
        prog = self._files.get(path)
        if prog is None:
            return {'file': clean_text(path), 'status': 'not_found', 'source': None,
                    'failed_tests': [], 'exception': None, 'candidates': []}
        if prog.result == 'green':
            status = 'passed'
        else:
            status = 'found' if prog.cause else 'not_found'
        if status == 'passed':
            source = None
        elif prog.cause:
            source = prog.source
        elif not prog.report:
            source = None
        elif prog.unrunnable:
            source = 'unrunnable'
        else:
            source = 'report_only'
        if status == 'passed':
            cands = []
        elif status == 'found':
            cands = prog.cands
        else:
            cands = prog.stack if source in ('report_only', 'unrunnable') else []
            if source == 'report_only':  # no located lines: rank the report's own frames
                cands = rank(self._canonical_report(prog.rep), [], prog.sources,
                             self._test_file(path), limit=_MAX_CANDIDATES) or cands
                if prog.locate:
                    cands = self._with_assert_vars(prog, path, cands, [])
        failures = prog.rep['failures'] if prog.rep else []
        exception = None
        if failures:
            exception = {'type': clean_text(failures[0]['exc_type']),
                         'message': clean_text(failures[0]['message'], _MESSAGE_MAX)}
        return {'file': clean_text(path), 'status': status, 'source': source,
                'failed_tests': sorted(prog.failed), 'exception': exception,
                'candidates': json.loads(json.dumps(cands[:_MAX_CANDIDATES]))}


# ---- diagnose -----------------------------------------------------------

def _cmd_name(run):
    cmd = run.get('cmd') if isinstance(run, dict) else None
    return cmd.get('name') if isinstance(cmd, dict) else None


def _check_shape(domain):
    for sensor in domain.sensors:
        if _cmd_name(sensor.run) != _SENSOR_CMD:
            raise PlanbotError('DOMAIN_INVALID', 'sensor %r must be a %s command' % (sensor.name, _SENSOR_CMD))
    for name, action in domain.actions.items():
        if _cmd_name(action.run) not in _COMMANDS:
            raise PlanbotError('DOMAIN_INVALID', 'action %r must be one of the read-only commands' % name)


def diagnose(domain_path, test_file, runner, execute=False, allow=None, max_replans=3, repo_root='.'):
    """Observe and decompose (or execute) the diagnose task; returns {report, calls, finding}."""
    domain = load_domain(domain_path)
    _check_shape(domain)
    if not isinstance(test_file, str) or _SURROGATES.search(test_file):
        raise PlanbotError('GOAL_INVALID', 'invalid test file name')
    task = parse_task(domain, 'diagnose(' + test_file + ')')
    if not callable(runner):
        raise PlanbotError('USAGE', 'runner must be callable')
    allowed = allowed_actions(domain, allow, None)
    if isinstance(max_replans, int) and max_replans < 0:
        raise PlanbotError('USAGE', 'max_replans must not be negative')
    session = Session(runner, repo_root, allow_probe='probe' in allowed)
    domain.cmd_runner = session.run
    if execute:
        report = execute_task(domain, task, allowed, memory=None, max_replans=max_replans)
    else:
        report = dry_run_task(domain, task, allowed, memory=None)
    return {'report': report, 'calls': session.calls, 'finding': session.finding(test_file)}


# ---- summarize ----------------------------------------------------------

def _esc(value, limit=None):
    """clean_text, then CR/LF as the two characters \\r / \\n, then truncate (length counts escaped text)."""
    text = clean_text(value).replace('\r', '\\r').replace('\n', '\\n')
    return clean_text(text, limit)


def _failed_segment(tests):
    items = [_esc(t, 120) for t in tests if isinstance(t, str)]
    if not items:
        return '-'
    whole = ', '.join(items)
    if len(whole) <= 300:
        return whole
    for keep in range(len(items) - 1, -1, -1):
        text = ', '.join(items[:keep]) + ' (+%d more)' % (len(items) - keep)
        if len(text) <= 300:
            return text
    return ' (+%d more)' % len(items)


def _num(value, kind):
    return value if isinstance(value, kind) and not isinstance(value, bool) else kind(0)


def _candidate_lines(cand, index, snippets, probes):
    reasons = cand.get('reasons')
    reasons = ', '.join(_esc(r) for r in reasons if isinstance(r, str)) if isinstance(reasons, list) else ''
    line = _num(cand.get('line'), int)
    head = '  %d. %s:%d score=%.3f [%s]' % (index, _esc(cand.get('file')), line,
                                          _num(cand.get('score'), float), reasons)
    out = [clean_text(head, 160)]
    rows = cand.get('snippet') if snippets else None
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict):
            n = _num(row.get('line'), int)
            out.append('%s %d | %s' % ('  >>' if n == line else '    ', n, _esc(row.get('text'), 100)))
    values = cand.get('probe') if probes else None
    pairs = ['%s=%s' % (_esc(v.get('expr')), _esc(v.get('value'))) for v in values
             if isinstance(v, dict)] if isinstance(values, list) else []
    if pairs:
        out.append(clean_text('     probe: ' + '; '.join(pairs), 120))
    return out


def _render(data, message_max, probes, with_snippets, with_heads):
    """Summary text; the first `with_snippets` candidates keep snippets, the first `with_heads` appear."""
    status, source = _esc(data.get('status'), 40), data.get('source')
    source = _esc(source, 40) if isinstance(source, str) and source else '-'
    exc = data.get('exception')
    if isinstance(exc, dict):
        exc_line = 'exception: %s: %s' % (_esc(exc.get('type'), 80), _esc(exc.get('message'), message_max))
    else:
        exc_line = 'exception: -'
    failed = data.get('failed_tests')
    lines = ['status: %s (source: %s)' % (status, source), 'file: ' + _esc(data.get('file'), 200),
             'failed: ' + _failed_segment(failed if isinstance(failed, list) else []), exc_line, 'candidates:']
    cands = data.get('candidates')
    cands = [c for c in cands if isinstance(c, dict)][:_MAX_CANDIDATES] if isinstance(cands, list) else []
    for i, cand in enumerate(cands[:max(with_heads, 1)], 1):
        lines.extend(_candidate_lines(cand, i, i <= with_snippets, probes))
    if not cands:
        lines.append('  (none)')
    kind = status if status == 'passed' else 'not_found'
    if status == 'found':
        kind = 'unrunnable' if source == 'unrunnable' else 'found'
    lines.append(_HINTS[kind])
    return '\n'.join(lines)


def summarize(finding):
    """Compact, deterministic text for a model: at most 2500 characters, always UTF-8 encodable."""
    data = finding if isinstance(finding, dict) else {}
    n = _MAX_CANDIDATES
    text = _render(data, 300, True, n, n)
    steps = [(200, True, n, n), (200, False, n, n)]
    steps += [(200, False, k, n) for k in range(n - 1, -1, -1)]
    steps += [(200, False, 0, k) for k in range(n - 1, 0, -1)]
    for args in steps:
        if len(text) <= _SUMMARY_MAX:
            break
        text = _render(data, *args)
    return text
