"""加载检查：服务启动后「接口出错」那一类（条件看不懂、变量名非法、遍历写法不对……）在生成时就挡掉。

服务端的接口表只切块（dsl_http.scan_routes / split_endpoints），脚本要到请求时才由 DSLEngine 解析，
解析错误以 DSLError 抛出，路由器打印「[接口出错] 文件: 原话」并回 500。这里复用同一套：

- 切接口块：dsl_http.split_endpoints（与启动同一个函数；块不配对、端口反了同样报）。
- 脚本解析：DSLEngine 自己的 _take_sections / _check_loops / _scan_block / parse_cond_expr / _parse_each /
  _split_assign（check_name），逐行走一遍和 _exec_block 一样的解析点，但不执行任何动词（不碰库、不调模型）。

没有另写解析器：引擎改了写法规则，这里自动跟着变。只查「解析点」，运行期才知道的值（变量内容、sql 结果）不查。
"""
from pathlib import Path

from tools.dsl import DSLEngine
from tools.dsl_core import DSLError, normalize, parse_cond_expr, split_head, split_raw_cmp
from tools.dsl_http import scan_routes, split_endpoints


class _ParseOnly(DSLEngine):
    """只解析：把运行时才有值的部分（遍历的列表）换成空。"""

    def _resolve_items(self, raw):
        return []


def parse_cond(cond, lineno):
    """条件：结构（parse_cond_expr）+ 每个比较能不能拆出 左 运算符 右（求值时 eval_cond_expr 才拆，拆不出报「看不懂的条件」，这里提前拆一遍）。"""
    def leaves(t):
        if t[0] in ("and", "or"):
            for x in t[1]:
                yield from leaves(x)
        elif t[0] == "not":
            yield from leaves(t[1])
        else:
            yield t[1]
    for raw in leaves(parse_cond_expr(cond, lineno)):
        if split_raw_cmp(raw) is None:
            raise DSLError(
                f"第 {lineno + 1} 行：看不懂的条件「{raw}」。可用："
                f"包含 / 不包含 / 等于 / 不等于 / 为空 / 不为空 / "
                f"大于 / 小于 / 不小于 / 不大于 / 开头是 / 结尾是，组合用 且 / 或 / 非 / 括号")


def parse_script(script):
    """走一遍引擎的解析点。通过返回 None，否则返回报错原话（DSLError 的文字）。"""
    eng = _ParseOnly(client=None, workdir=Path("."), verbose=False)
    try:
        script = eng._take_sections(script)
        lines = [normalize(ln).rstrip() for ln in script.splitlines()]
        eng._check_loops(lines)
        for i, raw in enumerate(lines):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            head, rest = split_head(line)
            if head == "if":
                if not rest:
                    raise DSLError(f"第 {i + 1} 行：「如果」后面要跟条件")
                marks, _end = eng._scan_block(lines, i, len(lines))
                parse_cond(rest, i)
                for kind, at, cond in marks:
                    if kind == "elif":
                        parse_cond(cond, at)
            elif head in ("each", "foreach"):
                eng._parse_each(rest, i)
                else_at, _end = eng._find_block(lines, i, len(lines))
                if else_at is not None:
                    raise DSLError(f"第 {else_at + 1} 行：循环里不能直接写「否则」")
            elif head == "while":
                cond, _ = eng._parse_while(rest, i)
                parse_cond(cond, i)
            elif head == "set":
                eng._split_assign(rest, "设")
            elif head in ("else", "elif", "end") and not _opened(lines, i):
                raise DSLError(f"第 {i + 1} 行：多余的「{head_word(head)}」")
    except DSLError as e:
        return str(e)
    except Exception as e:  # noqa: BLE001
        return f"{type(e).__name__}: {e}"
    return None


def head_word(head):
    return {"else": "否则", "elif": "否则如果", "end": "结束"}[head]


def _opened(lines, at):
    """第 at 行之前是否有还没关的块（游离的 否则 / 结束 引擎运行到才报，这里提前报）。"""
    from tools.dsl_core import BLOCK_OPENERS
    depth = 0
    for j in range(at):
        h, _ = split_head(lines[j].strip())
        if h in BLOCK_OPENERS:
            depth += 1
        elif h == "end":
            depth -= 1
    return depth > 0


def check_text(text, rel, route):
    """一份文本按服务的方式加载。route=True：接口文件（切接口块逐块解析）；False：scripts 下的流程（整个当脚本）。
    返回问题列表，每条形如「[接口出错] 文件: 报错原话」，与服务打印的一致。"""
    if not route:
        e = parse_script(text)
        return [f"[接口出错] {rel}: {e}"] if e else []
    try:
        eps, _ports = split_endpoints(text, Path(rel))
    except DSLError as e:
        return [f"[接口出错] {rel}: {e}"]
    probs = []
    for ep in eps:
        e = parse_script(ep.script)
        if e:
            probs.append(f"[接口出错] {rel} 接口 {ep.method} {ep.path}（文件第 {ep.line} 行起）: {e}")
    return probs


def check_file(path, rel=None):
    """磁盘上的一个 .zs：scripts/ 下整个当脚本，其余（routes/）切接口块。"""
    path = Path(path)
    rel = rel or path.name
    return check_text(path.read_text(encoding="utf-8"), rel, not (path.parent.name == "scripts" or "/scripts/" in str(rel)))


def check_project(root):
    """全项目加载：scan_routes（接口重复、块不配对）+ 每个接口块 + scripts/*.zs 逐个解析。返回问题列表。"""
    root = Path(root)
    probs = []
    routes = root / "routes"
    try:
        scan_routes(routes)
    except DSLError as e:
        probs.append(f"[接口出错] routes: {e}")
    for f in sorted(routes.rglob("*.zs")) if routes.is_dir() else []:
        probs += check_file(f, str(f.relative_to(root)))
    sdir = root / "scripts"
    for f in sorted(sdir.rglob("*.zs")) if sdir.is_dir() else []:
        probs += check_file(f, str(f.relative_to(root)))
    return probs
