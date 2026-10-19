# -*- coding: utf-8 -*-
"""模板集管理：python -m gen tpl <子命令>

    list                          所有套、说明、继承关系
    show <套>                     清单、模板文件（继承/覆盖）、产物路径规则、项目级文件、参数
    diff <套A> <套B>              两套对同一个样例实体渲染结果的差异
    where <产物路径>              某个生成文件来自哪套哪个模板
    check [套]                    清单合法、继承无环、都能渲染、路径不撞、要求字段/参数齐全
    render <套> <实体文件> [--project] [--out 目录] [--参数 键=JSON]
                                  渲染到 stdout 或目录（不写项目）
    new <套> --from <基础套>      建新套的骨架（清单 + 空覆盖）
    doc                           按清单生成 gen/templates/README.md
"""

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

from .templates_ import (LAYOUT, MANIFEST, TEMPLATE_ROOT, TemplateError, _target, chain,
                         describe, products, project_params, render, render_project, sets)

README = "README.md"


def _sample(set_name: str, root: Path):
    """用于 diff / check 的样例实体：标题、正文、默认 now 的字段，加上这套要求的字段。"""
    from tools.entity import parse
    try:
        need = describe(set_name, root)["要求字段"]
    except TemplateError:
        need = []
    extra = "".join(f"  字段 {n} 文本 必填 索引 {n}\n" for n in need)
    text = ("实体 note 笔记\n  字段 title 文本 必填 标题\n  字段 body 长文本 正文\n" + extra
            + "  字段 created_at 文本 必填 默认 now 记于\n结束\n")
    return parse(text)[0]


def _pattern(tpl_name: str):
    """模板文件名 → 能匹配产物路径的正则（实体名当通配）。"""
    path = _target(tpl_name, "\0")
    return re.compile("^" + re.escape(path).replace("\0", r"(?P<e>[^/]+?)") + "$")


def _origin(set_name: str, root: Path) -> dict:
    """{模板文件: (来自哪套, 状态)}；状态：本套 / 继承 / 覆盖。"""
    ch = chain(set_name, root)
    out = {}
    for tpl, owner in products(set_name, root).items():
        if owner != set_name:
            state = "继承"
        elif any((Path(root) / n / tpl).is_file() for n in ch[1:]):
            state = "覆盖"
        else:
            state = "本套"
        out[tpl] = (owner, state)
    return out


def _extends_of(owner: str, tpl: str, root: Path) -> list:
    f = Path(root) / owner / tpl
    return re.findall(r'\{%-?\s*extends\s+"([^"]+)"', f.read_text(encoding="utf-8")) if f.is_file() else []


# ---------------------------------------------------------------- 子命令

def cmd_list(a, root) -> int:
    for n in sets(root, abstract=True):
        try:
            d = describe(n, root)
        except TemplateError as ex:
            print(f"{n}\t[坏] {ex}")
            continue
        tag = "（抽象，不能直接用）" if d["抽象"] else ""
        print(f"{n}{tag}\n    {d['说明'] or '（无说明）'}\n    继承：{' → '.join(d['继承链'][1:]) or '无'}")
    return 0


def cmd_show(a, root) -> int:
    d = describe(a.set, root)
    print(f"套：{d['名']}{'（抽象）' if d['抽象'] else ''}")
    print(f"说明：{d['说明'] or '—'}")
    print(f"继承：{' → '.join(d['继承链'][1:]) or '无'}")
    print(f"要求字段：{'、'.join(d['要求字段']) or '无'}")
    print("\n模板文件（产物路径规则里 <实体> 是实体名）：")
    for tpl, (owner, state) in _origin(a.set, root).items():
        ext = _extends_of(owner, tpl, root)
        extra = f"  extends {', '.join(ext)}" if ext else ""
        print(f"  {tpl:<18} {state}（{owner}）  →  {_target(tpl, '<实体>')}{extra}")
    print("\n项目级文件（每个项目一次）：")
    if not d["项目级文件"]:
        print("  无")
    for pf in d["项目级文件"]:
        gate = f"  当 {pf['当']} 非空" if pf.get("当") else ""
        print(f"  {pf.get('路径')}  ←  {pf.get('模板')}（{pf.get('来自')}）{gate}")
    print("\n参数：")
    if not d["参数"]:
        print("  无")
    for k, v in d["参数"].items():
        print(f"  {k} = {json.dumps(v.get('默认'), ensure_ascii=False)}    {v.get('说明', '')}")
    return 0


def cmd_diff(a, root) -> int:
    # 样例要同时满足两套的要求字段
    need = sorted(set(describe(a.a, root)["要求字段"]) | set(describe(a.b, root)["要求字段"]))
    from tools.entity import parse
    extra = "".join(f"  字段 {n} 文本 必填 索引 {n}\n" for n in need)
    e = parse("实体 note 笔记\n  字段 title 文本 必填 标题\n  字段 body 长文本 正文\n" + extra
              + "  字段 created_at 文本 必填 默认 now 记于\n结束\n")[0]
    ra, rb = render(e, a.a, root=root), render(e, a.b, root=root)
    same = 0
    for path in sorted(set(ra) | set(rb)):
        if path not in rb:
            print(f"--- 只有 {a.a}：{path}")
        elif path not in ra:
            print(f"+++ 只有 {a.b}：{path}")
        elif ra[path] == rb[path]:
            same += 1
        else:
            print("".join(difflib.unified_diff(
                ra[path].splitlines(True), rb[path].splitlines(True),
                f"{a.a}/{path}", f"{a.b}/{path}")), end="")
    print(f"\n（样例实体 note；{same} 个产物完全相同）")
    return 0


def cmd_where(a, root) -> int:
    rel = a.path.replace("\\", "/").lstrip("./")
    found = 0
    for n in sets(root):
        d = describe(n, root)
        for pf in d["项目级文件"]:
            if pf.get("路径") == rel:
                found += 1
                print(f"{n}: 项目级文件 {pf['模板']}（{pf['来自']}）")
        for tpl, (owner, state) in _origin(n, root).items():
            m = _pattern(tpl).match(rel)
            if m:
                found += 1
                chain_txt = " → ".join(_extends_of(owner, tpl, root)) or "无 extends"
                print(f"{n}: {owner}/{tpl}（{state}；{chain_txt}），实体 {m.group('e')}")
    if not found:
        print(f"没有哪套模板会生成 {rel}（产物目录：{'、'.join(LAYOUT.values())}）")
        return 1
    return 0


def _check_one(name: str, root: Path) -> list:
    errs = []
    try:
        d = describe(name, root)
    except TemplateError as ex:
        return [str(ex)]
    man = Path(root) / name / MANIFEST
    if man.is_file():
        raw = json.loads(man.read_text(encoding="utf-8"))
        if raw.get("名") not in (None, name):
            errs.append(f"清单的名「{raw.get('名')}」和目录名「{name}」不一致")
        known = {"名", "说明", "提示", "继承", "要求字段", "参数", "项目级文件", "抽象"}
        errs += [f"清单里有不认识的键「{k}」" for k in raw if k not in known]
        if not d["说明"]:
            errs.append("清单缺「说明」")
    for k, v in d["参数"].items():
        if "默认" not in v:
            errs.append(f"参数「{k}」缺「默认」")
    seen = set()
    for pf in d["项目级文件"]:
        for key in ("路径", "模板"):
            if not pf.get(key):
                errs.append(f"项目级文件缺「{key}」：{pf}")
        if pf.get("路径") in seen:
            errs.append(f"项目级文件路径重复：{pf.get('路径')}")
        seen.add(pf.get("路径"))
        if pf.get("当") and pf["当"] not in d["参数"]:
            errs.append(f"项目级文件 {pf.get('路径')} 的「当」写了没声明的参数「{pf['当']}」")
    if d["抽象"]:
        return errs
    # 能渲染 + 产物路径不撞（render 会报）
    try:
        e = _sample(name, root)
        files = render(e, name, root=root)
        if not files:
            errs.append("没有任何可产出的模板")
    except TemplateError as ex:
        errs.append(f"渲染样例实体失败：{ex}")
    if d["项目级文件"]:
        try:
            # 默认参数能渲染；给了角色再渲染一次（带 当 的文件）
            render_project(name, root=root)
            extra = {k: ["a", "b"] for k, v in d["参数"].items() if v.get("默认") == []}
            if extra:
                render_project(name, extra, root=root)
        except TemplateError as ex:
            errs.append(f"项目级文件渲染失败：{ex}")
    return errs


def cmd_check(a, root) -> int:
    names = [a.set] if a.set else sets(root, abstract=True)
    bad = 0
    for n in names:
        errs = _check_one(n, root)
        print(f"{'✗' if errs else '✓'} {n}")
        for x in errs:
            print(f"    {x}")
        bad += bool(errs)
    return 1 if bad else 0


def cmd_render(a, root) -> int:
    from tools.entity import parse
    ents = parse(Path(a.entity_file).read_text(encoding="utf-8"))
    files = {}
    need = describe(a.set, root)["要求字段"]
    for e in ents:
        have = {f.name for f in e.fields}
        if [n for n in need if n not in have]:
            print(f"# 跳过实体 {e.name}（模板「{a.set}」要求字段 {'、'.join(need)}）", file=sys.stderr)
            continue
        files.update(render(e, a.set, db=a.db, root=root))
    if a.project:
        params = {}
        for kv in a.param or []:
            k, _, v = kv.partition("=")
            try:
                params[k] = json.loads(v)
            except ValueError:
                params[k] = v
        files.update(render_project(a.set, params, root=root))
    if a.out:
        out = Path(a.out)
        for rel, text in sorted(files.items()):
            p = out / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8", newline="")
        print(f"{len(files)} 个文件写到 {out}")
    else:
        for rel, text in sorted(files.items()):
            print(f"--- {rel} ---")
            print(text, end="" if text.endswith("\n") else "\n")
    return 0


def cmd_new(a, root) -> int:
    if not re.match(r"^[A-Za-z][A-Za-z0-9_]*$", a.set):
        print(f"套名「{a.set}」只能用字母、数字、下划线，字母开头")
        return 1
    d = Path(root) / a.set
    if d.exists():
        print(f"{d} 已存在")
        return 1
    chain(a.base, root)       # 基础套必须存在且继承链没问题
    d.mkdir(parents=True)
    man = {"名": a.set, "说明": f"（写一句话说明）基于 {a.base}", "继承": a.base}
    (d / MANIFEST).write_text(json.dumps(man, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="")
    print(f"建了 {d}\n  {MANIFEST}（继承 {a.base}）\n同名文件放进来就覆盖基础套的；"
          f"想在基础套上改一点，写 {{% extends \"@{a.base}/文件名\" %}} 再覆盖变量/块。")
    return 0


def render_doc(root: Path = TEMPLATE_ROOT) -> str:
    L = ["# gen 模板集", "",
         "<!-- 由 `python -m gen tpl doc` 按各套的 set.json 生成，不要手改 -->", "",
         "> 区别：仓库根的 `templates/`（db/、frontend/）是建库和前端页面模板；"
         "这里的 `gen/templates/` 是 `gen` 按实体生成 SQL / 接口 / 界面用的模板集。", "",
         "每套一个目录，目录里 `set.json` 是清单（名、说明、继承、要求字段、参数、项目级文件）。"
         "继承的套只写与基础套的差异；`python -m gen tpl show <套>` 看细节。", ""]
    for n in sets(root, abstract=True):
        d = describe(n, root)
        L += [f"## {n}{'（抽象基础套）' if d['抽象'] else ''}", "", d["说明"] or "（无说明）", ""]
        L.append(f"- 继承：{' → '.join(d['继承链'][1:]) or '无'}")
        L.append(f"- 要求字段：{'、'.join(d['要求字段']) or '无'}")
        org = _origin(n, root)
        own = [f"`{t}`（{s}）" for t, (o, s) in org.items() if o == n]
        inh = [f"`{t}`（来自 {o}）" for t, (o, s) in org.items() if o != n]
        L.append(f"- 本套文件：{'、'.join(own) or '无'}")
        if inh:
            L.append(f"- 继承来的文件：{'、'.join(inh)}")
        if d["项目级文件"]:
            L += ["", "项目级文件（每个项目一次）：", ""]
            for pf in d["项目级文件"]:
                gate = f"，当参数「{pf['当']}」非空" if pf.get("当") else ""
                L.append(f"- `{pf.get('路径')}` ← `{pf.get('模板')}`{gate}")
        if d["参数"]:
            L += ["", "| 参数 | 默认 | 说明 |", "|---|---|---|"]
            for k, v in d["参数"].items():
                val = json.dumps(v.get("默认"), ensure_ascii=False).replace("|", "\\|")
                L.append(f"| {k} | `{val}` | {v.get('说明', '')} |")
        L.append("")
    return "\n".join(L).rstrip("\n") + "\n"


def cmd_doc(a, root) -> int:
    p = Path(root) / README
    p.write_text(render_doc(root), encoding="utf-8", newline="\n")
    print(f"写了 {p}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="gen tpl", description="模板集管理")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    s = sub.add_parser("show"); s.add_argument("set"); s.set_defaults(fn=cmd_show)
    s = sub.add_parser("diff"); s.add_argument("a"); s.add_argument("b"); s.set_defaults(fn=cmd_diff)
    s = sub.add_parser("where"); s.add_argument("path"); s.set_defaults(fn=cmd_where)
    s = sub.add_parser("check"); s.add_argument("set", nargs="?", default=""); s.set_defaults(fn=cmd_check)
    s = sub.add_parser("render")
    s.add_argument("set"); s.add_argument("entity_file")
    s.add_argument("--project", action="store_true", help="同时渲染项目级文件")
    s.add_argument("--out", default="", help="写到这个目录（不给就打印）")
    s.add_argument("--db", default="app.db")
    s.add_argument("--参数", dest="param", action="append", metavar="键=JSON", help="项目级参数，可重复")
    s.set_defaults(fn=cmd_render)
    s = sub.add_parser("new"); s.add_argument("set"); s.add_argument("--from", dest="base", required=True)
    s.set_defaults(fn=cmd_new)
    sub.add_parser("doc").set_defaults(fn=cmd_doc)
    p.add_argument("--root", default=str(TEMPLATE_ROOT), help=argparse.SUPPRESS)
    a = p.parse_args(argv)
    try:
        return a.fn(a, Path(a.root))
    except TemplateError as ex:
        print(f"[模板] {ex}")
        return 1
