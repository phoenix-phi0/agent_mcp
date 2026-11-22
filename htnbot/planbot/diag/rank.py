"""Candidate re-ranking for the adapter layer: breaks ties between suspicious lines.

Pure and deterministic: no randomness, no set-iteration order, no file access.
Standard library plus planbot.diag.parse only. Every public function is total (never raises).
All weights and thresholds live in WEIGHTS; the rules only look at syntax shape (ast),
coverage counts and positions relative to the stack frames.
"""
import ast
import math
import re

from planbot.diag.parse import clean_text, norm_path, safe_expr

WEIGHTS = {
    'susp': 1.0,
    'fail_only': 0.3,
    'structural': -1.0,
    'compare': 0.5,
    'arith': 0.4,
    'slice': 0.4,
    'boolop': 0.3,
    'value_stmt': 0.2,
    'shape_cap': 0.8,
    'small_int': 2.0,
    'exc': 0.5,
    'flow': 0.4,
    'msg_name': 0.2,
    'near': 0.3,
    'near_scale': 5.0,
    'at_frame': 0.15,
    'after_frame': -0.3,
    'guard': 0.3,
    'ret_on_path': 0.2,
    'probe': 0.4,
    'probe_diff': 0.2,
    'probe_cap': 0.6,
    'probe_gap': 0.05,
    'small_diff': 2.0,
    'frame_func': 0.0,
    'dead_store': 0.6,
    'lit_match': 0.3,
}

_NEWLINE = re.compile(r'\r\n|\r|\n')
_ELSE_LIKE = re.compile(r'^\s*(?:else|finally)\s*:')
_CONTEXT = 2
_SNIPPET_MAX = 160
_TRY_TYPES = (ast.Try, getattr(ast, 'TryStar', ast.Try))
_BLOCK_TYPES = (ast.stmt, ast.excepthandler, getattr(ast, 'match_case', ast.stmt))
_PLAIN_STMTS = (ast.Import, ast.ImportFrom, ast.Global, ast.Nonlocal, ast.Pass, ast.Raise)
_TRIVIAL_VALUES = (ast.Name, ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.Call,
                   ast.Await, ast.Starred)
_SIZE_OPS = (ast.Lt, ast.LtE, ast.Gt, ast.GtE)
_EQ_OPS = (ast.Eq, ast.NotEq)


# ---------------------------------------------------------------------------
# input sanitising
# ---------------------------------------------------------------------------

def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _num(value, default=0.0):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    value = float(value)
    return value if math.isfinite(value) else default


def _frames(failure):
    """Valid frames of one failure as (file, line) pairs, outermost first."""
    out = []
    frames = failure.get('frames') if isinstance(failure, dict) else None
    for frame in frames if isinstance(frames, list) else []:
        if (isinstance(frame, dict) and isinstance(frame.get('file'), str)
                and _is_int(frame.get('line')) and frame['line'] > 0):
            out.append((frame['file'], frame['line']))
    return out


def _failures(report):
    failures = report.get('failures') if isinstance(report, dict) else None
    return [f for f in failures if isinstance(f, dict)] if isinstance(failures, list) else []


def _loc_rows(loc):
    """(file, line) -> merged row; duplicates keep the largest of each number."""
    rows = {}
    for row in loc if isinstance(loc, list) else []:
        if not (isinstance(row, dict) and isinstance(row.get('file'), str)
                and _is_int(row.get('line')) and row['line'] > 0):
            continue
        susp = max(_num(row.get('susp')), 0.0)
        fail = row['fail'] if _is_int(row.get('fail')) else 0
        passed = row['passed'] if _is_int(row.get('passed')) else 0
        key = (row['file'], row['line'])
        old = rows.get(key)
        if old is not None:
            susp, fail, passed = max(susp, old[0]), max(fail, old[1]), max(passed, old[2])
        rows[key] = (susp, fail, passed)
    return rows


# ---------------------------------------------------------------------------
# static source analysis
# ---------------------------------------------------------------------------

def _called_names(node):
    """Names (plain or attribute) called anywhere below `node`."""
    names = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            if isinstance(sub.func, ast.Name):
                names.add(sub.func.id)
            elif isinstance(sub.func, ast.Attribute):
                names.add(sub.func.attr)
    return names


def _dead_stores(func):
    """Lines of plain assignments inside `func` whose targets are never read in `func`."""
    used, stores = set(), []
    for node in ast.walk(func):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            used.add(node.id)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            used.update(node.names)
        elif isinstance(node, ast.Assign):
            stores.append((node.lineno, node.targets))
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            stores.append((node.lineno, [node.target]))
    return {line for line, targets in stores
            if all(isinstance(t, ast.Name) and t.id not in used and any(c.isalnum() for c in t.id)
                   for t in targets)}


def _body_starts(func):
    """Start lines of every statement inside `func`, nested blocks included.

    The header line, decorators and the headers of nested functions or classes are left out.
    """
    lines = set()
    stack = list(func.body)
    while stack:
        node = stack.pop()
        if isinstance(node, ast.stmt) and not isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            lines.add(node.lineno)
        for child in ast.iter_child_nodes(node):
            if isinstance(child, _BLOCK_TYPES):
                stack.append(child)
    return sorted(lines)


class _Src:
    """Parsed source of one file: text lines plus per-line ast lookups."""

    def __init__(self, text):
        tree = ast.parse(text)
        lines = _NEWLINE.split(text)
        if lines and lines[-1] == '':
            lines.pop()
        self.lines = lines
        self.stmts = []
        self.exprs = {}
        self.funcs = []
        self.func_bodies = []  # (first line, last line, body statement start lines, name)
        self.dead_stores = set()
        self.func_names = {}   # function name -> [first line, ...]
        self.func_calls = {}   # first line of a function -> names it calls
        self.value_returns = set()
        self.loops = []
        self.ifs = []
        self.docs = set()
        for index, node in enumerate(ast.walk(tree)):
            if isinstance(node, (ast.stmt, ast.excepthandler)):
                start = node.lineno
                for deco in getattr(node, 'decorator_list', ()):
                    start = min(start, deco.lineno)
                end = node.end_lineno or node.lineno
                self.stmts.append((start, -end, index, node))
            if isinstance(node, ast.expr):
                self.exprs.setdefault(node.lineno, []).append(node)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.funcs.append((node.lineno, node.end_lineno or node.lineno))
                self.dead_stores |= _dead_stores(node)
                self.func_bodies.append((node.lineno, node.end_lineno or node.lineno,
                                         _body_starts(node), node.name))
                self.func_names.setdefault(node.name, []).append(node.lineno)
                self.func_calls[node.lineno] = _called_names(node)
                if any(isinstance(sub, ast.Return) and sub.value is not None
                       for sub in ast.walk(node)):
                    self.value_returns.add(node.lineno)
            if isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
                self.loops.append((node.lineno, node.end_lineno or node.lineno))
            if isinstance(node, ast.If):
                self.ifs.append((node.lineno, node.end_lineno or node.lineno))
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                first = node.body[0] if node.body else None
                if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                        and isinstance(first.value.value, str)):
                    self.docs.add(id(first))

    def usable(self, line):
        """True for a line that exists and is neither blank nor a pure comment."""
        if not 1 <= line <= len(self.lines):
            return False
        text = self.lines[line - 1].strip()
        return bool(text) and not text.startswith('#')

    def text(self, line):
        return self.lines[line - 1] if 1 <= line <= len(self.lines) else ''

    def innermost(self, line):
        """Innermost statement that starts at or covers `line` (None if there is none)."""
        best = None
        for start, neg_end, index, node in self.stmts:
            if start <= line <= -neg_end and (best is None or (start, neg_end, index) > best[0]):
                best = ((start, neg_end, index), node)
        return best[1] if best else None

    def func_body(self, line):
        """(name, statement start lines) of the innermost function containing `line`.

        ('', []) at module level.
        """
        best = None
        for start, end, body, name in self.func_bodies:
            if start <= line <= end and (best is None or start > best[0]):
                best = (start, name, body)
        return (best[1], best[2]) if best else ('', [])

    def func_start(self, line):
        """First line of the innermost function containing `line` (0 at module level)."""
        best = 0
        for start, end in self.funcs:
            if start <= line <= end and start > best:
                best = start
        return best

    def line_exprs(self, line):
        return self.exprs.get(line, [])

    def in_loop_with(self, anchor, line):
        """True when some loop covers both `anchor` and `line`."""
        return any(s <= anchor <= e and s <= line <= e for s, e in self.loops)

    def guard_line(self, anchor):
        """Condition line of the innermost `if` whose body holds a raise at `anchor`."""
        node = self.innermost(anchor)
        if not isinstance(node, ast.Raise):
            return None
        best = None
        for start, end in self.ifs:
            if start < anchor <= end and (best is None or start > best):
                best = start
        return best

    def snippet(self, line):
        first, last = max(1, line - _CONTEXT), min(len(self.lines), line + _CONTEXT)
        return [{'line': n, 'text': clean_text(self.lines[n - 1].rstrip('\r\n'), _SNIPPET_MAX)}
                for n in range(first, last + 1)]


def _load_source(text):
    try:
        return _Src(text) if isinstance(text, str) else None
    except Exception:  # syntax error, null bytes, absurd nesting: treat as no source
        return None


# ---------------------------------------------------------------------------
# features: each takes (ctx, cand) and returns (score, label); label None = no hit
# ---------------------------------------------------------------------------

_NO = (0.0, None)


def _f_susp(ctx, cand):
    value = cand['susp']
    return WEIGHTS['susp'] * value, 'susp=%.3f' % value


def _f_fail_only(ctx, cand):
    row = cand['row']
    if ctx['any_passed'] and row is not None and row[2] == 0 and row[1] > 0:
        return WEIGHTS['fail_only'], 'fail_only'
    return _NO


def _f_stack(ctx, cand):
    return (0.0, 'in_stack') if cand['in_stack'] else _NO


def _small_int(node):
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        node = node.operand
    return (isinstance(node, ast.Constant) and type(node.value) is int
            and abs(node.value) <= WEIGHTS['small_int'])


def _number(node):
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        node = node.operand
    return isinstance(node, ast.Constant) and type(node.value) in (int, float)


def _stmt(cand):
    src = cand['src']
    return src.innermost(cand['line']) if src is not None else None


def _f_structural(ctx, cand):
    src, line = cand['src'], cand['line']
    if src is None:
        return _NO
    hit = bool(_ELSE_LIKE.match(src.text(line)))
    node = _stmt(cand)
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, *_PLAIN_STMTS)):
        hit = True
    elif isinstance(node, _TRY_TYPES) and node.lineno == line:
        hit = True
    elif isinstance(node, ast.Expr) and id(node) in src.docs:
        hit = True
    return (WEIGHTS['structural'], 'structural') if hit else _NO


def _f_compare(ctx, cand):
    src = cand['src']
    if src is None:
        return _NO
    best = None
    for node in src.line_exprs(cand['line']):
        if not isinstance(node, ast.Compare):
            continue
        operands = [node.left, *node.comparators]
        if (any(isinstance(op, _SIZE_OPS) for op in node.ops)
                or (any(isinstance(op, _EQ_OPS) for op in node.ops)
                    and any(_number(o) for o in operands))):
            return WEIGHTS['compare'], 'compare'
        best = WEIGHTS['compare'] / 2
    return (best, 'compare_other') if best is not None else _NO


def _f_arith(ctx, cand):
    src = cand['src']
    if src is None:
        return _NO
    node = _stmt(cand)
    if isinstance(node, ast.AugAssign) and node.lineno == cand['line']:
        return WEIGHTS['arith'], 'arith'
    for node in src.line_exprs(cand['line']):
        if (isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub))
                and (_small_int(node.left) or _small_int(node.right))):
            return WEIGHTS['arith'], 'arith'
    return _NO


def _computed_index(node):
    if isinstance(node, ast.Slice):
        return True
    if isinstance(node, ast.Tuple):
        return any(isinstance(e, ast.Slice) for e in node.elts)
    if isinstance(node, ast.UnaryOp):
        return not isinstance(node.operand, ast.Constant)
    return isinstance(node, (ast.BinOp, ast.Call, ast.IfExp, ast.Subscript))


def _f_slice(ctx, cand):
    src = cand['src']
    if src is not None:
        for node in src.line_exprs(cand['line']):
            if isinstance(node, ast.Subscript) and _computed_index(node.slice):
                return WEIGHTS['slice'], 'slice'
    return _NO


def _f_boolop(ctx, cand):
    src = cand['src']
    if src is not None:
        for node in src.line_exprs(cand['line']):
            if isinstance(node, ast.BoolOp) or (isinstance(node, ast.UnaryOp)
                                                and isinstance(node.op, ast.Not)):
                return WEIGHTS['boolop'], 'boolop'
    return _NO


def _f_value_stmt(ctx, cand):
    node = _stmt(cand)
    if node is None or node.lineno != cand['line']:
        return _NO
    if isinstance(node, (ast.Return, ast.Assign, ast.AnnAssign)):
        value = node.value
        if value is not None and not isinstance(value, _TRIVIAL_VALUES):
            return WEIGHTS['value_stmt'], 'value_stmt'
    return _NO


def _f_dead_store(ctx, cand):
    """With a no-value exception: an assignment whose result is never read in its function."""
    src = cand['src']
    if ctx.get('exc_kind') == 'none' and src is not None and cand['line'] in src.dead_stores:
        return WEIGHTS['dead_store'], 'dead_store'
    return _NO


def _f_frame_func(ctx, cand):
    """Line that is in the pool only because it shares a function with a stack frame."""
    return (WEIGHTS['frame_func'], 'frame_func') if cand['frame_func'] else _NO


# --- (4) exception-class affinity -------------------------------------------

_INDEX_ERRORS = ('IndexError', 'KeyError')
_ZERO_ERRORS = ('ZeroDivisionError',)
_TYPE_ERRORS = ('TypeError', 'AttributeError')
_VALUE_ERRORS = ('ValueError',)
_CONVERSIONS = ('int', 'float', 'str', 'bool', 'bytes', 'complex', 'list', 'tuple', 'set', 'dict')
_STR_METHODS = ('split', 'rsplit', 'join', 'strip', 'lstrip', 'rstrip', 'replace', 'lower',
                'upper', 'title', 'capitalize', 'format', 'startswith', 'endswith', 'find',
                'rfind', 'index', 'center', 'ljust', 'rjust', 'zfill', 'splitlines', 'partition')
_GROW_METHODS = ('append', 'extend', 'insert')
_SEQUENCES = (list, tuple, set, frozenset, dict)
_COMPARE_OP = re.compile(r'^\s*(?:assert\s+)?(.+?)\s*(==|!=|<=|>=|<|>)\s*(.+?)\s*$')
_ERROR_PREFIX = re.compile(r'^\s*[A-Za-z_.]*(?:Error|Exception)\s*:\s*')
_IDENT = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')
try:
    _BUILTIN_NAMES = frozenset(dir(len.__self__))
except Exception:  # pragma: no cover - interpreter without a builtins module on functions
    _BUILTIN_NAMES = frozenset()


def _exc_name(failure):
    text = failure.get('exc_type') if isinstance(failure, dict) else None
    if not isinstance(text, str):
        return ''
    return re.split(r'[.:]', text.strip())[-1]


def _first_line(failure):
    message = failure.get('message') if isinstance(failure, dict) else None
    if not isinstance(message, str):
        return ''
    return _NEWLINE.split(_ERROR_PREFIX.sub('', message, count=1))[0]


def _operands(failure):
    """(left, right) texts of the first comparison in the message, or None."""
    match = _COMPARE_OP.match(_first_line(failure))
    return (match.group(1), match.group(3)) if match else None


def _literal(text):
    try:
        return True, ast.literal_eval(text.strip())
    except Exception:
        return False, None


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _value_kind(left, right):
    """Shape family implied by the types of the two compared values (None if unclear)."""
    ok_l, a = _literal(left)
    ok_r, b = _literal(right)
    if not (ok_l and ok_r):
        return None
    if isinstance(a, bool) and isinstance(b, bool):
        return 'bool' if a != b else None
    if _is_number(a) and _is_number(b):
        try:
            return 'boundary' if abs(a - b) <= WEIGHTS['small_diff'] else None
        except Exception:
            return None
    if isinstance(a, str) and isinstance(b, str):
        return 'str'
    if isinstance(a, _SEQUENCES) and isinstance(b, _SEQUENCES):
        return 'seq'
    return None


def _exc_kind(failure):
    name = _exc_name(failure)
    if name in _INDEX_ERRORS:
        return 'subscript'
    if name in _ZERO_ERRORS:
        return 'div'
    if name in _TYPE_ERRORS:
        return 'none'
    if name in _VALUE_ERRORS:
        return 'value'
    if 'assert' in name.lower():
        pair = _operands(failure)
        return _value_kind(*pair) if pair else None
    return None


def _has_expr(src, line, test):
    return any(test(node) for node in src.line_exprs(line))


def _is_call_to(node, names):
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in names


def _is_method_call(node, names):
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr in names)


def _none_value(node):
    return node is None or (isinstance(node, ast.Constant) and node.value is None)


def _lacks_return(node, src):
    """An `if` header whose body never returns or raises, inside a function that returns a value."""
    if not isinstance(node, ast.If):
        return False
    if any(isinstance(n, (ast.Return, ast.Raise)) for stmt in node.body for n in ast.walk(stmt)):
        return False
    return src.func_start(node.lineno) in src.value_returns


def _shape_hit(ctx, cand, kind):
    src, line = cand['src'], cand['line']
    if src is None:
        return False
    node = _stmt(cand)
    own = node is not None and node.lineno == line
    if kind == 'subscript':
        return (_has_expr(src, line, lambda n: isinstance(n, ast.Subscript)
                          or _is_call_to(n, ('range', 'len'))))
    if kind == 'div':
        div = (ast.Div, ast.FloorDiv, ast.Mod)
        return (_has_expr(src, line, lambda n: isinstance(n, ast.BinOp) and isinstance(n.op, div))
                or (own and isinstance(node, ast.AugAssign) and isinstance(node.op, div)))
    if kind == 'none':
        if own and isinstance(node, ast.Return) and _none_value(node.value):
            return True
        if own and isinstance(node, (ast.Assign, ast.AnnAssign)) and _none_value(node.value):
            return True
        return (_has_expr(src, line, lambda n: isinstance(n, ast.Attribute))
                or (own and _lacks_return(node, src)))
    if kind == 'value':
        return (_has_expr(src, line, lambda n: isinstance(n, ast.Compare)
                          or _is_call_to(n, _CONVERSIONS)))
    if kind == 'boundary':
        return any(f(ctx, cand)[1] in ('compare', 'arith', 'slice')
                   for f in (_f_compare, _f_arith, _f_slice))
    if kind == 'bool':
        return (_f_boolop(ctx, cand)[1] is not None or _f_compare(ctx, cand)[1] is not None)
    if kind == 'seq':
        return (_f_slice(ctx, cand)[1] is not None
                or _has_expr(src, line, lambda n: isinstance(n, ast.Subscript)
                             or _is_call_to(n, ('range',)) or _is_method_call(n, _GROW_METHODS)))
    if kind == 'str':
        return (_f_slice(ctx, cand)[1] is not None
                or _has_expr(src, line, lambda n: isinstance(n, ast.JoinedStr)
                             or _is_method_call(n, _STR_METHODS)
                             or (isinstance(n, ast.BinOp) and isinstance(n.op, ast.Mod)
                                 and isinstance(n.left, ast.Constant)
                                 and isinstance(n.left.value, str))))
    return False


def _f_exc(ctx, cand):
    kind = ctx.get('exc_kind')
    if kind and _shape_hit(ctx, cand, kind):
        return WEIGHTS['exc'], 'exc~' + kind
    return _NO


# --- (5) data flow ------------------------------------------------------------

def _line_names(src, line):
    out = set()
    for node in src.line_exprs(line):
        if isinstance(node, ast.Name):
            out.add(node.id)
        elif isinstance(node, ast.Attribute):
            out.add(node.attr)
    return out


def _f_flow(ctx, cand):
    if cand['func'] and (cand['file'], cand['func']) in ctx['flow_funcs']:
        return WEIGHTS['flow'], 'flow'
    return _NO


_QUOTED = re.compile(r"'([^'\n]{1,40})'|\"([^\"\n]{1,40})\"")


def _f_lit_match(ctx, cand):
    """A string constant compared on this line also appears quoted in a failing case's name."""
    src = cand['src']
    if src is None or not ctx['lit_match']:
        return _NO
    for node in src.line_exprs(cand['line']):
        if isinstance(node, ast.Compare):
            for side in [node.left] + list(node.comparators):
                if (isinstance(side, ast.Constant) and isinstance(side.value, str)
                        and side.value in ctx['lit_match']):
                    return WEIGHTS['lit_match'], 'lit_match'
    return _NO


def _f_msg_name(ctx, cand):
    src = cand['src']
    if src is not None and ctx['ids'] and _line_names(src, cand['line']) & ctx['ids']:
        return WEIGHTS['msg_name'], 'msg_name'
    return _NO


# --- (6) position relative to the innermost non-test frame ----------------------

def _f_position(ctx, cand):
    frame = ctx['frame']
    if frame is None or cand['src'] is None or not cand['same_func']:
        return _NO
    line, anchor = cand['line'], frame[1]
    if line < anchor:
        gap = anchor - line
        return WEIGHTS['near'] / (1 + gap / WEIGHTS['near_scale']), 'near_frame:%d' % -gap
    if line == anchor:
        return WEIGHTS['at_frame'], 'at_frame'
    if not cand['src'].in_loop_with(anchor, line):
        return WEIGHTS['after_frame'], 'after_frame'
    return _NO


def _f_guard(ctx, cand):
    frame = ctx['frame']
    if frame is None or cand['src'] is None or cand['file'] != frame[0]:
        return _NO
    if cand['src'].guard_line(frame[1]) == cand['line']:
        return WEIGHTS['guard'], 'guard'
    return _NO


def _f_ret_on_path(ctx, cand):
    if ctx['frame'] is not None or cand['src'] is None:
        return _NO
    row = cand['row']
    node = _stmt(cand)
    if (row is not None and row[1] > 0 and isinstance(node, ast.Return)
            and node.lineno == cand['line'] and cand['func']
            and (cand['file'], cand['func']) in ctx['called_funcs']):
        return WEIGHTS['ret_on_path'], 'ret_on_path'
    return _NO


# --- (7) runtime probe values -----------------------------------------------------

def _f_probe(ctx, cand):
    values = [item['value'].strip() for item in cand['probe_items']]
    if not values:
        return _NO
    if (ctx['actual'] is not None and ctx['actual'] in values) or (
            ctx['type_class'] and 'None' in values):
        return WEIGHTS['probe'], 'probe'
    return _NO


def _values_differ(items):
    """True when some expr has fail values and pass values, both non-empty and disjoint."""
    groups = {}
    for item in items:
        if item['outcome'] in ('fail', 'pass'):
            groups.setdefault(item['expr'], {'fail': set(), 'pass': set()})[
                item['outcome']].add(item['value'].strip())
    return any(sides['fail'] and sides['pass'] and not (sides['fail'] & sides['pass'])
               for sides in groups.values())


def _f_probe_diff(ctx, cand):
    if _values_differ(cand['probe_items']):
        return WEIGHTS['probe_diff'], 'probe_diff'
    return _NO


_SHAPE_FEATURES = (_f_structural, _f_compare, _f_arith, _f_slice, _f_boolop, _f_value_stmt)
_HEAD_FEATURES = (_f_susp, _f_fail_only)
# Only used when the report has failures; they run after the shape group, in this order.
_EXTRA_FEATURES = (_f_exc, _f_stack, _f_flow, _f_position, _f_guard, _f_ret_on_path,
                   _f_msg_name, _f_lit_match, _f_dead_store, _f_frame_func)
_PROBE_FEATURES = (_f_probe, _f_probe_diff)


def _score(ctx, cand):
    total, reasons = 0.0, []

    def run(feature):
        score, label = feature(ctx, cand)
        if label is not None:
            reasons.append(label)
        return score if label is not None else 0.0

    for feature in _HEAD_FEATURES:
        total += run(feature)
    positive = negative = 0.0
    for feature in _SHAPE_FEATURES:
        score = run(feature)
        if score > 0:
            positive += score
        else:
            negative += score
    total += min(positive, WEIGHTS['shape_cap']) + negative
    if ctx['failures']:
        for feature in _EXTRA_FEATURES:
            total += run(feature)
        total += min(sum(run(feature) for feature in _PROBE_FEATURES), WEIGHTS['probe_cap'])
    return round(total, 3), reasons


# ---------------------------------------------------------------------------
# rank
# ---------------------------------------------------------------------------

def _pool(failures, rows, test_file):
    """Candidate (file, line) keys in the order they were found (order is irrelevant later)."""
    pool = {}
    failing = [key for key, row in rows.items() if row[1] >= 1]
    for key in failing or [key for key, row in rows.items() if row[0] > 0]:
        pool[key] = True
    for key in (fr for f in failures for fr in _frames(f)):
        if key[0] != test_file:
            pool[key] = True
    return pool


def _innermost_frame(failures, test_file):
    for failure in failures:
        inner = [fr for fr in _frames(failure) if fr[0] != test_file]
        if inner:
            return inner[-1]
    return None


def _probe_items(probes):
    """Valid probe values grouped by their `at` text, input order kept."""
    out = {}
    for item in probes if isinstance(probes, list) else []:
        if not (isinstance(item, dict) and isinstance(item.get('at'), str)
                and isinstance(item.get('expr'), str) and isinstance(item.get('value'), str)):
            continue
        outcome = item.get('outcome')
        out.setdefault(item['at'], []).append(
            {'expr': clean_text(item['expr']), 'value': clean_text(item['value']),
             'outcome': outcome if outcome in ('fail', 'pass') else None})
    return out


def _test_func_name(failure):
    name = failure.get('test') if isinstance(failure, dict) else None
    if not isinstance(name, str):
        return ''
    return re.split(r'::|\.', name.split('[')[0].strip())[-1]


def _failed_test_names(failures):
    """Test function names of the failing cases.

    Last '::' (or dotted) part; a parametrisation suffix ('[...]' or ' (...)') is removed first.
    """
    names = set()
    for failure in failures:
        name = failure.get('test')
        if isinstance(name, str):
            name = re.split(r'::|\.', name.split(' (')[0].split('[')[0].strip())[-1].strip()
            if name:
                names.add(name)
    return names


def _norm_test_file(test_file):
    if not test_file:
        return None
    return norm_path(test_file) or test_file


def _call_roots(failures, test_file, srcs):
    """Names called by the failing assertion lines and the failing test bodies."""
    names = set()
    test_src = srcs.get(test_file)
    for failure in failures:
        texts = []
        assert_line = failure.get('assert_line')
        if isinstance(assert_line, dict) and isinstance(assert_line.get('code'), str):
            texts.append(assert_line['code'])
        frames = failure.get('frames')
        for fr in frames if isinstance(frames, list) else []:
            if (isinstance(fr, dict) and fr.get('file') == test_file
                    and isinstance(fr.get('code'), str)):
                texts.append(fr['code'])
        if test_src is not None:
            for start in test_src.func_names.get(_test_func_name(failure), []):
                end = max(e for s, e in test_src.funcs if s == start)
                texts.extend(test_src.lines[start - 1:end])
        for text in texts:
            names.update(re.findall(r'([A-Za-z_][A-Za-z0-9_]*)\s*\(', text))
    return names


def _called_funcs(roots, srcs):
    """(file, first line) of functions reached from `roots` by name, up to 3 call layers."""
    found, frontier = set(), set(roots)
    for _ in range(3):
        reached = set()
        for file in sorted(srcs):
            src = srcs[file]
            if src is None:
                continue
            for name in sorted(frontier):
                for start in src.func_names.get(name, []):
                    if (file, start) not in found:
                        found.add((file, start))
                        reached.add((file, start))
        frontier = set()
        for file, start in reached:
            frontier |= srcs[file].func_calls.get(start, set())
    return found


def _failure_context(failures, test_file, srcs, stack):
    first = failures[0]
    ids = set()
    ids.update(_IDENT.findall(first.get('message') if isinstance(first.get('message'), str) else ''))
    assert_line = first.get('assert_line')
    if isinstance(assert_line, dict) and isinstance(assert_line.get('code'), str):
        ids.update(_IDENT.findall(assert_line['code']))
    pair = _operands(first) if 'assert' in _exc_name(first).lower() else None
    stack_funcs = set()
    for file, line in stack:
        src = srcs.get(file)
        start = src.func_start(line) if src is not None else 0
        if start:
            stack_funcs.add((file, start))
    called = _called_funcs(_call_roots(failures, test_file, srcs), srcs)
    lits = set()
    for failure in failures:
        name = failure.get('test')
        if isinstance(name, str):
            lits.update(a or b for a, b in _QUOTED.findall(name))
    return {
        'lit_match': lits,
        'exc_kind': _exc_kind(first),
        'ids': ids - _BUILTIN_NAMES,
        'actual': pair[0].strip() if pair else None,
        'type_class': _exc_name(first) in _TYPE_ERRORS,
        'flow_funcs': stack_funcs | called,
        'called_funcs': called,
    }


def rank(report, loc, sources, test_file='', probes=None, limit=5):
    """Up to `limit` Candidate dicts, most suspicious first. Never raises."""
    try:
        return _rank(report, loc, sources, test_file, probes, limit)
    except Exception:
        return []


def _rank(report, loc, sources, test_file, probes, limit):
    if not _is_int(limit) or limit <= 0:
        return []
    test_file = test_file if isinstance(test_file, str) else ''
    sources = sources if isinstance(sources, dict) else {}
    failures = _failures(report)
    rows = _loc_rows(loc)
    keys = _pool(failures, rows, test_file)
    stack = {fr for f in failures for fr in _frames(f)}
    if not keys and not stack:
        return []

    wanted = {key[0] for key in keys} | {file for file, _ in stack}
    if failures:
        wanted |= {file for file in sources if isinstance(file, str)}
        wanted |= {file for file, _ in stack} | {test_file}
    srcs = {}
    for file in sorted(wanted):
        srcs[file] = _load_source(sources.get(file))
    only_func = set()
    test_norm = _norm_test_file(test_file)
    test_names = _failed_test_names(failures)

    def expand(origins, spare_tests):
        for file, line in sorted(origins):
            src = srcs.get(file)
            if src is None:
                continue
            name, body = src.func_body(line)
            if spare_tests and test_norm is not None and file == test_norm and name in test_names:
                continue  # the failing test function itself is not expanded
            for start in body:
                if (file, start) not in keys:
                    keys[(file, start)] = True
                    only_func.add((file, start))

    expand(stack | {key for key in keys if key in rows}, True)
    if not keys:  # last resort: the test's own frames, with their functions (test function too)
        for key in stack:
            keys[key] = True
        expand(stack, False)
    keys = [key for key in keys if srcs[key[0]] is None or srcs[key[0]].usable(key[1])]

    top = max((rows[key][0] for key in keys if key in rows), default=0.0)
    ctx = {
        'any_passed': any(row[2] > 0 for row in rows.values()),
        'frame': _innermost_frame(failures, test_file),
        'failures': bool(failures),
        'exc_kind': None, 'ids': set(), 'actual': None, 'type_class': False,
        'flow_funcs': set(), 'called_funcs': set(), 'lit_match': set(),
    }
    probe_items = {}
    if failures:
        ctx.update(_failure_context(failures, test_file, srcs, stack))
        probe_items = _probe_items(probes)
    frame = ctx['frame']
    frame_src = srcs.get(frame[0]) if frame is not None else None
    frame_func = frame_src.func_start(frame[1]) if frame_src is not None else None

    # "sampled": some pool row carries a value tagged fail or pass -> sample ordering
    sampled = any(item['outcome'] is not None
                  for key in keys
                  for item in probe_items.get('%s:%d' % key, []))
    scored = []
    for key in keys:
        file, line = key
        src = srcs[file]
        row = rows.get(key)
        norm = min(row[0] / top, 1.0) if row is not None and top > 0 else 0.0
        func = src.func_start(line) if src is not None else 0
        same_func = (frame is not None and src is not None and file == frame[0]
                     and frame_func is not None and func == frame_func)
        cand = {'file': file, 'line': line, 'src': src, 'row': row, 'susp': norm,
                'in_stack': key in stack, 'func': func, 'same_func': same_func,
                'frame_func': key in only_func,
                'probe_items': probe_items.get('%s:%d' % (file, line), [])}
        score, reasons = _score(ctx, cand)
        dist = abs(line - frame[1]) if same_func else math.inf
        if sampled:
            sort_key = (0 if _values_differ(cand['probe_items']) else 1, -round(norm, 3),
                        -score, 0 if cand['in_stack'] else 1, dist, file, line)
        else:
            sort_key = (-score, 0 if cand['in_stack'] else 1, dist, file, line)
        scored.append((sort_key, cand, score, reasons))
    scored.sort(key=lambda item: item[0])

    out = []
    for _, cand, score, reasons in scored[:limit]:
        src = cand['src']
        out.append({
            'file': cand['file'],
            'line': cand['line'],
            'score': score,
            'reasons': reasons,
            'snippet': src.snippet(cand['line']) if src is not None else [],
            'probe': [{'expr': item['expr'], 'value': item['value']}
                      for item in cand['probe_items']],
        })
    return out


# ---------------------------------------------------------------------------
# probe_plan
# ---------------------------------------------------------------------------

_PLAN_MAX = 8


def _plan_at(report, candidates, test_file):
    """Up to 8 'file:line' texts: the leading candidates, else the report's stack frames."""
    keys = []
    for cand in candidates if isinstance(candidates, (list, tuple)) else []:
        if (isinstance(cand, dict) and isinstance(cand.get('file'), str)
                and _is_int(cand.get('line')) and cand['line'] > 0):
            keys.append((cand['file'], cand['line']))
    keys = keys[:_PLAN_MAX]
    if not keys:
        for failure in _failures(report):
            keys.extend(reversed(_frames(failure)))
        keys = [k for k in keys if k[0] != test_file] + [k for k in keys if k[0] == test_file]
    out = []
    for file, line in keys:
        if (file, line) not in out:
            out.append((file, line))
    return out[:_PLAN_MAX]


def _line_exprs_of(tree, line):
    """Expression texts taken from one source line, in order of appearance (may repeat)."""
    called = {id(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
    items = []

    def add(node, rank_, text):
        items.append((node.col_offset, rank_, -(node.end_col_offset or 0), len(items), text))

    for node in ast.walk(tree):
        if isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)) and node.iter.lineno == line:
            add(node.iter, 1, 'len(%s)' % ast.unparse(node.iter))
        if not (isinstance(node, ast.expr) and node.lineno == line):
            continue
        if isinstance(node, ast.Subscript):
            add(node, 1, 'len(%s)' % ast.unparse(node.value))
        if id(node) in called:
            continue
        if isinstance(node, (ast.Name, ast.Attribute, ast.Subscript)):
            if not (isinstance(node, ast.Name) and node.id in _BUILTIN_NAMES):
                add(node, 0, ast.unparse(node))
    return [item[-1] for item in sorted(items)]


def probe_plan(report, candidates, sources, test_file=''):
    """{'at': [...], 'exprs': [...]}: where to take probe values and which expressions. Never raises."""
    at, exprs = [], []
    try:
        test_file = test_file if isinstance(test_file, str) else ''
        keys = _plan_at(report, candidates, test_file)
        at = ['%s:%d' % key for key in keys]
        trees = {}
        for file, line in keys:
            if file not in trees:
                text = sources.get(file) if isinstance(sources, dict) else None
                try:
                    trees[file] = ast.parse(text) if isinstance(text, str) else None
                except Exception:  # syntax error and the like: no source
                    trees[file] = None
            try:
                found = _line_exprs_of(trees[file], line) if trees[file] is not None else []
            except Exception:
                found = []
            for text in found:
                if text not in exprs and safe_expr(text):
                    exprs.append(text)
        exprs = exprs[:_PLAN_MAX]
    except Exception:
        pass
    return {'at': at, 'exprs': exprs}


# ---------------------------------------------------------------------------
# needs_probe
# ---------------------------------------------------------------------------

def _score_of(candidate):
    return _num(candidate.get('score')) if isinstance(candidate, dict) else 0.0


def needs_probe(candidates):
    """True when some runner-up is within WEIGHTS['probe_gap'] of the first candidate."""
    try:
        if not isinstance(candidates, (list, tuple)) or len(candidates) < 2:
            return False
        scores = [_score_of(c) for c in candidates]
        gap = WEIGHTS['probe_gap']
        return any(round(scores[0] - s, 3) <= gap for s in scores[1:])
    except Exception:
        return False


# ---------------------------------------------------------------------------
# sample_plan
# ---------------------------------------------------------------------------

_SAMPLE_LOC_MAX = 5


_LINE_NAME = re.compile(r'(?<![\w.])[A-Za-z_]\w*')
_KEYWORD_CACHE = {}


def _is_keyword(name):
    """True when `name` cannot be assigned to (a Python keyword); decided by the parser itself."""
    hit = _KEYWORD_CACHE.get(name)
    if hit is None:
        try:
            ast.parse('%s = 0' % name)
            hit = False
        except Exception:
            hit = True
        _KEYWORD_CACHE[name] = hit
    return hit


def _method_first_params(tree, line):
    """First positional parameter names of the methods (defined directly in a class body) around `line`."""
    names = set()
    if tree is None:
        return names
    for cls in ast.walk(tree):
        if not isinstance(cls, ast.ClassDef):
            continue
        for fn in cls.body:
            if (isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and fn.lineno <= line <= (fn.end_lineno or fn.lineno)):
                params = list(fn.args.posonlyargs) + list(fn.args.args)
                if params:
                    names.add(params[0].arg)
    return names


def _plan_line_names(text, line, tree):
    """Identifiers in the whole source text of one line, left to right (may repeat).

    Words inside strings, keyword-argument names and called function names are included;
    Python keywords, builtin names and the first parameter of methods are dropped.
    """
    rows = _NEWLINE.split(text) if isinstance(text, str) else []
    if not 1 <= line <= len(rows):
        return []
    skip = _method_first_params(tree, line)
    return [m for m in _LINE_NAME.findall(rows[line - 1])
            if not _is_keyword(m) and m not in _BUILTIN_NAMES and m not in skip]


def _sample_points(report, loc, candidates, sources, test_file):
    """(primary, fill): (file, line) keys from loc and the failures' innermost frames, then the filler keys."""
    primary = []
    for row in loc if isinstance(loc, (list, tuple)) else []:
        if len(primary) >= _SAMPLE_LOC_MAX:
            break
        if not (isinstance(row, dict) and isinstance(row.get('file'), str)
                and _is_int(row.get('line')) and row['line'] > 0):
            continue
        if not (_is_int(row.get('fail')) and row['fail'] >= 1) and not _num(row.get('susp')) > 0:
            continue
        if row['file'] == test_file:
            continue
        key = (row['file'], row['line'])
        if key not in primary:
            primary.append(key)
    if isinstance(sources, dict):
        for failure in _failures(report):
            if len(primary) >= _PLAN_MAX:
                break
            for file, line in reversed(_frames(failure)):
                if file in sources:
                    if (file, line) not in primary:
                        primary.append((file, line))
                    break
    fill = []
    for cand in candidates if isinstance(candidates, (list, tuple)) else []:
        if (isinstance(cand, dict) and isinstance(cand.get('file'), str)
                and _is_int(cand.get('line')) and cand['line'] > 0):
            key = (cand['file'], cand['line'])
            if key not in primary and key not in fill:
                fill.append(key)
    return primary, fill


def sample_plan(report, loc, candidates, sources, test_file=''):
    """{'at': [...], 'exprs': [...]}: where to take failing and passing samples, and which expressions.

    Depends on the order of `loc` on purpose. Never raises.
    """
    at, exprs = [], []
    try:
        test_file = test_file if isinstance(test_file, str) else ''
        primary, fill = _sample_points(report, loc, candidates, sources, test_file)
        keys = (primary + fill)[:_PLAN_MAX]
        at = ['%s:%d' % key for key in keys]
        trees = {}
        for file, line in primary:
            text = sources.get(file) if isinstance(sources, dict) else None
            if not isinstance(text, str):
                continue
            if file not in trees:
                try:
                    trees[file] = ast.parse(text)
                except Exception:  # syntax error and the like: no static exclusions
                    trees[file] = None
            try:
                found = _plan_line_names(text, line, trees[file])
            except Exception:
                found = []
            for name in found:
                if name not in exprs and safe_expr(name):
                    exprs.append(name)
        exprs = exprs[:_PLAN_MAX]
    except Exception:
        at, exprs = [], []
    return {'at': at, 'exprs': exprs}
