# -*- coding: utf-8 -*-
"""命名约定：脚本里的变量名、脚本参数、SQL 参数用英文 snake_case。

    cd /home/ysc/mcp && .venv/bin/python tests/dsl/test_naming.py
    cd /home/ysc/mcp && .venv/bin/python tests/dsl/test_naming.py --全部   # 列出每一处

关键字（设、如果、遍历…）、动词名、动词参数名（拆选项 的 题干/题型）、界面名、
显示文本照旧中文。引擎本身继续支持中文变量名——这里只管仓库里的业务脚本
（.zs、生成 .zs 的 .j2 模板）和 SQL 文件（kg/queries、gen 的 .sql 模板）。

扫的位置：

  设 X = / 设 X.y =            X（问、问JSON、流式、对话、读取、读JSON、读JSONL、判定 同）
  遍历 X 于 … 序号 Y           X、Y（逐项 同）
  {X} {X.y} {X 或 …}           X（JSON 样子的 {"k":…} 不算）
  执行 a.zs k=v                k（脚本参数；后台执行 同）
  查询/查一行/查一值/写库 库 名 k=v   k（SQL 参数）
  .sql 里的 :k                 k

不扫：注释行、字典里点号后面的键（传给中文动词的参数字典，键就是中文的动词
参数名）、显示文本里不在 {} 里的字。verbs/（含 tools/dslagent/verbs/）下用 .zs 写的动词，开头「# 参数：」
声明的是动词参数名，照规矩中文，也不算。

另外查一条：变量名不能是关键字的英文别名（set、if、end、reset、verdict……，
见 tools/dsl_core.KEYWORDS）和循环分隔词 in。引擎眼下不拦，但「reset」这类
名字一旦写到行首就成了语句，读的人也会看岔。
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.dsl_core import KEYWORDS      # noqa: E402
from tools.verbs import parse_param_decl  # noqa: E402

# 变量名不许用的英文词：关键字的英文别名、循环分隔词
ASCII_RESERVED = {v for v in KEYWORDS.values()} | {"in"}

# 业务脚本所在的地方。data/ 下是旧副本，tests/ 里内联的片段有的专门测中文
# 变量名，都不扫。
ZS_DIRS = ["kg", "flows", "dsl", "routes", "learner", "gen", "tools", "verbs", "app2", "agents"]
SKIP_PARTS = {"data", ".venv", "node_modules", "__pycache__"}

ASSIGN_KW = ("设置", "设", "变量", "提问JSON", "问JSON", "提问", "问", "流式", "对话",
             "载入JSONL", "读JSONL", "载入JSON", "读JSON", "读取", "载入", "判定")
LOOP_KW = ("遍历", "循环", "每个", "逐项", "逐个")
CALL_KW = ("后台执行", "执行", "调用")
DB_VERBS = ("查询", "查一行", "查一值", "写库")
IN_WORDS = ("属于", "于", "在", "in")

VAR_RE = re.compile(r"\{([^{}]+)\}")
KV_RE = re.compile(r"(\S+?)=")
SQL_PARAM_RE = re.compile(r"(?<![:\w]):([^\W\d]\w*)")


def strip_jinja(text: str) -> str:
    """去掉 Jinja 的注释、语句块，{{ 表达式 }} 换成一个 ASCII 占位。"""
    text = re.sub(r"\{#.*?#\}", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
    text = re.sub(r"\{%.*?%\}", "", text, flags=re.S)
    return re.sub(r"\{\{.*?\}\}", "J", text, flags=re.S)


def head_of(expr: str) -> str:
    expr = expr.strip()
    expr = re.split(r"\s+或(\s|$)", expr)[0].strip()
    return expr.split(".")[0].strip()


def _after_kw(line: str, kws):
    for kw in kws:
        if line.startswith(kw + " ") or line.startswith(kw + "\t"):
            return kw, line[len(kw):].strip()
    return None, None


def scan_zs(text: str, allowed=()):
    """返回 [(行号, 位置说明, 标识符)]：非 ASCII 的，和撞了英文关键字的。

    allowed 是可以用中文的名字（.zs 动词声明的参数）。
    """
    hits = []
    for no, raw in enumerate(text.splitlines(), 1):
        line = raw.replace("＝", "=").replace("｛", "{").replace("｝", "}").strip()
        if not line or line.startswith("#"):
            continue
        names = []
        kw, rest = _after_kw(line, ASSIGN_KW)
        if kw and "=" in rest:
            names.append(("赋值", head_of(rest.split("=", 1)[0])))
        kw, rest = _after_kw(line, LOOP_KW)
        if kw:
            for w in IN_WORDS:
                m = re.match(rf"^(\S+?)\s*{re.escape(w)}\s", rest)
                if m:
                    names.append(("遍历", m.group(1)))
                    break
            m = re.search(r"\s序号\s+(\S+)\s*$", rest)
            if m:
                names.append(("序号", m.group(1)))
        m = re.match(r"^重复\s.*\s计数\s+(\S+)\s*$", line)
        if m:
            names.append(("计数", m.group(1)))
        # 「设 x = 执行 …」「执行 …」
        body = line
        if "=" in line:
            k2, r2 = _after_kw(line, ASSIGN_KW)
            if k2:
                body = r2.split("=", 1)[1].strip()
        kw, rest = _after_kw(body, CALL_KW)
        if kw:
            for k in KV_RE.findall(rest.split(None, 1)[1] if " " in rest else ""):
                names.append(("脚本参数", k))
        kw, rest = _after_kw(body, DB_VERBS)
        if kw:
            parts = rest.split(None, 2)
            if len(parts) == 3:
                for k in KV_RE.findall(parts[2]):
                    names.append(("SQL参数", k))
        for m in VAR_RE.finditer(line):
            inner = m.group(1)
            if any(c in inner for c in '":,'):
                continue    # JSON 字面量
            names.append(("引用", head_of(inner)))
        for where, name in names:
            if not name or name in allowed:
                continue
            if not name.isascii():
                hits.append((no, where, name))
            elif where in ("赋值", "遍历", "序号", "计数", "引用", "脚本参数") and name in ASCII_RESERVED:
                hits.append((no, where + "（关键字）", name))
    return hits


def scan_sql(text: str):
    hits = []
    for no, raw in enumerate(text.splitlines(), 1):
        line = raw.split("--", 1)[0]
        line = re.sub(r"'[^']*'", "''", line)
        for m in SQL_PARAM_RE.finditer(line):
            if not m.group(1).isascii():
                hits.append((no, "SQL参数", m.group(1)))
    return hits


def files():
    for d in ZS_DIRS:
        base = ROOT / d
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if not p.is_file() or SKIP_PARTS & set(p.relative_to(ROOT).parts):
                continue
            n = p.name
            if n.endswith(".zs") or n.endswith(".zs.j2"):
                yield p, "zs"
            elif n.endswith(".sql") or n.endswith(".sql.j2"):
                yield p, "sql"


def report():
    out = []
    for p, kind in files():
        text = p.read_text(encoding="utf-8")
        if p.name.endswith(".j2"):
            text = strip_jinja(text)
        # verbs/ 下的 .zs 动词（包顶层、defs/ 里的都算；dslagent 私有动词根 tools/dslagent/verbs/ 同）：声明的参数是动词参数名
        allowed = parse_param_decl(text) if (ROOT / "verbs" in p.parents or ROOT / "tools" / "dslagent" / "verbs" in p.parents) else ()
        hits = scan_zs(text, allowed) if kind == "zs" else scan_sql(text)
        for no, where, name in hits:
            out.append((str(p.relative_to(ROOT)), no, where, name))
    return out


def self_test():
    """扫描器自己的对照：该抓的抓得到，不该抓的不抓。"""
    sample = (
        "设 回答 = 1\n"
        "设 card.题干 = x\n"            # 点号后的键不算
        "遍历 项 于 {列表} 序号 号\n"
        "执行 scripts/a.zs 学习者={learner}\n"
        "后台执行 scripts/b.zs 块={chunk} on_error=scripts/c.zs\n"
        "设 r = 查询 app.db q 条数=5\n"
        "返回 {\"错误\":\"{原话 或}\"}\n"
        "# 设 注释 = 1\n"
        "设 ok = {ok}\n"
        "设 reset = 1\n"                # 关键字的英文别名
        "设 rec.reset = {new_round}\n"  # 点号后的键是英文关键字没关系
    )
    got = {(w, n) for _, w, n in scan_zs(sample)}
    want = {("赋值", "回答"), ("遍历", "项"), ("引用", "列表"), ("序号", "号"),
            ("脚本参数", "学习者"), ("脚本参数", "块"), ("SQL参数", "条数"), ("引用", "原话"),
            ("赋值（关键字）", "reset")}
    sql = {n for _, _, n in scan_sql("SELECT 1 WHERE a = :条数 AND b = :ok -- :注释\n"
                                      "AND c = '12:30' AND d::text = x")}
    return got == want, got ^ want, sql == {"条数"}, sql


def main():
    ok1, diff, ok2, sql = self_test()
    passed = failed = 0
    ok3 = scan_zs("# 参数：对象\n问 问候 = {对象}\n", allowed=["对象"]) == [(2, "赋值", "问候")]
    for ok, msg in ((ok1, f"扫描器对照：中文变量名、英文关键字当变量名都抓到，点号后的键和注释不抓 {diff or ''}"),
                    (ok3, "扫描器对照：.zs 动词声明的参数名放过，局部变量照抓"),
                    (ok2, f"扫描器对照：.sql 里的 :中文参数抓到、注释和字符串不抓 {sql}")):
        print(("  ✓ " if ok else "  ✗ ") + msg)
        passed += ok
        failed += not ok

    hits = report()
    scanned = sum(1 for _ in files())
    ok = not hits
    print(("  ✓ " if ok else "  ✗ ")
          + f"扫了 {scanned} 个 .zs/.sql（含 .j2 模板），中文的变量名/脚本参数/SQL 参数 {len(hits)} 处")
    passed += ok
    failed += not ok
    limit = None if "--全部" in sys.argv else 40
    for f, no, where, name in hits[:limit]:
        print(f"      {f}:{no}  {where}  {name}")
    if limit and len(hits) > limit:
        print(f"      …… 还有 {len(hits) - limit} 处，加 --全部 看")
    print(f"\n通过 {passed}，失败 {failed}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
