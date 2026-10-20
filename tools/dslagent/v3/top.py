"""顶层规划 plan/top.zs：只有「项目 名」和「模块 名 [依赖 甲 乙]」，说明写注释（# 开头，或语句后面空格 + #）。确定性，不调模型。

    项目 kgstudy
    模块 graph                 # 知识图谱：知识点和前置边
    模块 vocab 依赖 graph      # 单词库
    模块 progress 依赖 graph vocab

parse(text) -> (top, 问题)，top = {"项目", "模块": [{"名", "依赖", "行"}]}；check(text) -> 问题列表；layers(top) -> 依赖分层；
sync_deps(text, want) -> 按 {模块名: [依赖…]} 改写各「模块」行的依赖子句（保留注释、不改模块名），给「同步顶层依赖」动词用。
"""
import re

NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
SPLIT_RE = re.compile(r"[\s,，、]+")
MODULE_RE = re.compile(r"^模块\s+(\S+)(?:\s+依赖\s+(.+))?$")


def clean(text):
    """去掉代码围栏行，换行统一成 \\n。"""
    return "\n".join(l for l in (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
                     if not l.strip().startswith("```")).strip() + "\n"


def _strip_comment(s):
    i = s.find("#")
    while i >= 0:
        if i == 0 or s[i - 1] in " \t":
            return s[:i].rstrip()
        i = s.find("#", i + 1)
    return s.rstrip()


def parse(text):
    probs, top = [], {"项目": None, "模块": []}
    for no, raw in enumerate(clean(text).splitlines(), 1):
        s = _strip_comment(raw).strip()
        if not s:
            continue
        if s.startswith("项目"):
            parts = s.split()
            if len(parts) != 2 or parts[0] != "项目":
                probs.append(f"第 {no} 行：项目写法是「项目 <名>」，现在是「{s}」")
            elif top["项目"] is not None:
                probs.append(f"第 {no} 行：「项目」只能写一次")
            else:
                top["项目"] = parts[1]
            continue
        m = MODULE_RE.match(s)
        if not m:
            probs.append(f"第 {no} 行：只能写「项目 <名>」和「模块 <名> [依赖 甲 乙]」（说明写成 # 注释），现在是「{s[:40]}」")
            continue
        deps = [d for d in SPLIT_RE.split(m.group(2) or "") if d and d != "无"]
        top["模块"].append({"名": m.group(1), "依赖": list(dict.fromkeys(deps)), "行": no})
    return top, probs


def find_cycle(mods):
    """mods：{名: [依赖]}。有环返回环上的名字列表（首尾相同），没有返回 None。"""
    state, stack = {}, []

    def visit(n):
        state[n] = 1
        stack.append(n)
        for d in mods.get(n, []):
            if d not in mods:
                continue
            if state.get(d) == 1:
                return stack[stack.index(d):] + [d]
            if d not in state:
                got = visit(d)
                if got:
                    return got
        stack.pop()
        state[n] = 2
        return None
    for n in mods:
        if n not in state:
            got = visit(n)
            if got:
                return got
    return None


def check(text):
    """→ 问题列表（空 = 通过）。"""
    top, probs = parse(text)
    if top["项目"] is None:
        probs.append("缺「项目 <名>」")
    elif not NAME_RE.match(top["项目"]):
        probs.append(f"项目名「{top['项目']}」要用英文 snake（小写字母开头，只含小写字母 / 数字 / 下划线）")
    if not top["模块"]:
        probs.append("一个模块都没写（模块 <名> [依赖 …]）")
    names = {}
    for m in top["模块"]:
        if not NAME_RE.match(m["名"]):
            probs.append(f"第 {m['行']} 行：模块名「{m['名']}」要用英文 snake")
        if m["名"] in names:
            probs.append(f"第 {m['行']} 行：模块「{m['名']}」重复")
        names[m["名"]] = m["依赖"]
    for m in top["模块"]:
        for d in m["依赖"]:
            if d == m["名"]:
                probs.append(f"第 {m['行']} 行：模块「{d}」依赖了自己")
            elif d not in names:
                probs.append(f"第 {m['行']} 行：模块「{m['名']}」依赖的「{d}」没有写成模块")
    cyc = find_cycle(names)
    if cyc:
        probs.append("模块依赖成环：" + " → ".join(cyc))
    return probs


def _comment_idx(s):
    i = s.find("#")
    while i >= 0:
        if i == 0 or s[i - 1] in " \t":
            return i
        i = s.find("#", i + 1)
    return -1


def sync_deps(text, want):
    """按 want={模块名: [依赖…]} 改写「模块 <名> [依赖 …]」行里的依赖子句；不认识的行、want 里没有的模块原样保留，
    注释（# 之后的部分）保留，不改模块名。→ 新文本（以 \\n 结尾）。"""
    out = []
    for raw in clean(text).splitlines():
        idx = _comment_idx(raw)
        code = raw if idx < 0 else raw[:idx]
        comment = "" if idx < 0 else raw[idx:]
        m = MODULE_RE.match(code.strip())
        if not m or m.group(1) not in want:
            out.append(raw)
            continue
        new_code = f"模块 {m.group(1)}"
        deps = want[m.group(1)]
        if deps:
            new_code += " 依赖 " + " ".join(deps)
        out.append(new_code + ("  " + comment if comment else ""))
    return "\n".join(out) + "\n"


def load(text):
    """通过检查的文本 → top；不通过抛 ValueError（带问题清单）。"""
    probs = check(text)
    if probs:
        raise ValueError("top.zs 有问题：" + "；".join(probs[:6]))
    return parse(text)[0]


def layers(top):
    """依赖分层：第 0 层没有依赖，第 k 层的依赖都在更低层；层内按 top.zs 里的先后。→ [[模块名…], …]。"""
    deps = {m["名"]: m["依赖"] for m in top["模块"]}
    depth = {}

    def d(n):
        if n not in depth:
            depth[n] = 1 + max((d(x) for x in deps[n]), default=-1)
        return depth[n]
    for n in deps:
        d(n)
    out = []
    for n in deps:
        while len(out) <= depth[n]:
            out.append([])
        out[depth[n]].append(n)
    return out
