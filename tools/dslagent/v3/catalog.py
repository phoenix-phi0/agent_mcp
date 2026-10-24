"""plan/catalog.md：全项目「接口目录」，程序生成（不调模型），给写约定 / 复核约定 / 做模块 / 补改当只读参考。

每个已有约定（通过检查）的模块一节，按模块名排序：说明（plan/top.zs 里这个模块的注释）、依赖、表（学习记录的标注）、
公开函数（函数头 + 返回 + 报错，不含伪代码，复用 contract.public_heads）、接口（方法 路径 -> 函数，带 角色 / 公开 / 上传）。

build(project, top_text) -> 全文；refresh(project) -> 读 plan/top.zs + 全部 contracts/*.md 重新生成并存盘，
内容没变不重写（约定通过 / 重写 / 清理删掉的模块 / 同步顶层依赖时调，见 planning.save / 清理删掉的模块 / 同步顶层依赖）；
brief_index(project, top_text, exclude) -> 除 exclude 外每个模块一行概要（说明 + 公开函数名），给写约定时非直接依赖的模块用。
"""
from pathlib import Path

from ..packs.dslproj import contract as C
from . import top as T


def path_of(project):
    return Path(project) / "plan" / "catalog.md"


def top_comments(text):
    """plan/top.zs 原文 -> {模块名: 说明}：模块行末尾的 # 注释；没有就用紧挨着上一行的单独注释（中间不能隔空行）。"""
    out, pending = {}, []
    for raw in (text or "").replace("\r\n", "\n").split("\n"):
        line = raw.rstrip()
        if not line.strip():
            pending = []
            continue
        idx = T._comment_idx(line)
        code = (line if idx < 0 else line[:idx]).strip()
        comment = "" if idx < 0 else line[idx:].lstrip("#").strip()
        if not code:                                   # 整行都是注释
            if comment:
                pending.append(comment)
            continue
        m = T.MODULE_RE.match(code)
        if m:
            out[m.group(1)] = comment or "；".join(pending)
        pending = []
    return out


def _parsed_modules(project):
    """项目里通过检查的全部约定 -> {模块名: contract}，按名排序。"""
    cdir = Path(project) / "contracts"
    out = {}
    for f in sorted(cdir.glob("*.md")) if cdir.is_dir() else []:
        c, probs = C.parse(f.read_text(encoding="utf-8"))
        if not probs:
            out[f.stem] = c
    return out


def _iface_line(i):
    tail = []
    if i.get("动作"):
        tail.append(f"动作 {i['动作']}")
    if i["公开"]:
        tail.append("公开")
    if i["角色"]:
        tail.append(f"角色 {i['角色']}")
    if i["上传"]:
        u = i["上传"]
        extra = [f"上传 {u['字段']}"]
        if u["类型"]:
            extra.append(f"类型 {u['类型']}")
        if u["上限"]:
            extra.append(f"上限 {u['上限']}")
        tail.append(" ".join(extra))
    if i.get("模板"):
        w = i["模板"]
        tail.append("模板 " + w["名"] + "".join(f" {k}={v}" for k, v in w["参数"].items()))
    if i.get("传"):
        tail.append("传 " + " ".join(f"{k}={v}" for k, v in i["传"].items()))
    if i.get("参数"):
        tail.append("参数 " + " ".join(f"{f}={p}" for f, p in i["参数"].items()))
    head = f"{i['方法']} {i['路径']} -> {i['函数']}"
    return head + ("  " + "  ".join(tail) if tail else "")


def _table_line(t):
    return f"表 {t['名']}" + "（学习记录）" if t["学习记录"] else f"表 {t['名']}"


def section(name, c, desc):
    lines = [f"## 模块 {name}", f"说明：{desc or '（没有写说明）'}", f"依赖：{'、'.join(c['依赖']) or '无'}", ""]
    lines.append("表：" + ("、".join(_table_line(t) for t in c["表"]) if c["表"] else "无"))
    lines.append("")
    lines.append("公开函数：")
    heads = C.public_heads(c)
    lines.append(heads if heads else "（无）")
    lines.append("")
    lines.append("接口：")
    lines += [_iface_line(i) for i in c["接口"]] if c["接口"] else ["（无）"]
    return "\n".join(lines).rstrip() + "\n"


def build(project, top_text):
    comments = top_comments(top_text)
    mods = _parsed_modules(project)
    header = "# 接口目录（程序生成，只读；约定通过 / 重写 / 清理删掉的模块 / 同步顶层依赖时自动刷新）\n\n"
    if not mods:
        return header + "（还没有通过检查的模块约定）\n"
    return header + "\n".join(section(name, mods[name], comments.get(name, "")) for name in sorted(mods))


def refresh(project):
    """重新生成 plan/catalog.md；内容没变不重写。没有 plan/top.zs 时不生成，返回 None。→ 写盘的文本。"""
    project = Path(project)
    top_file = project / "plan" / "top.zs"
    if not top_file.is_file():
        return None
    text = build(project, top_file.read_text(encoding="utf-8"))
    p = path_of(project)
    if not p.is_file() or p.read_text(encoding="utf-8") != text:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")
    return text


def one_liner(name, c, comments):
    heads = [f["名"] for f in c["函数"] if f["公开"]]
    return f"模块 {name}：{comments.get(name, '') or '（没有写说明）'}；公开函数：{'、'.join(heads) if heads else '无'}"


def brief_index(project, top_text, exclude):
    """给写约定用的「目录」：除 exclude（通常是自身 + 直接依赖）外，每个有约定的模块一行（说明 + 公开函数名）。"""
    comments = top_comments(top_text)
    mods = _parsed_modules(project)
    lines = [one_liner(name, mods[name], comments) for name in sorted(mods) if name not in exclude]
    return "\n".join(lines)
