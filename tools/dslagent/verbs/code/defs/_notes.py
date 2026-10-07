"""笔记状态（下划线开头，不注册成动词）。存在状态目录（DSLAGENT_STATE）的 notes_state.json。

结构：
  head      文件清单 + 开局测试
  hist      历史动作记录 [{step, act, arg, res}]（读片段的结果不放这里，只放引用）
  snips     代码片段 [{file, a, b, body, step, funcs}]，step = 最近一次读到/刷新的步号
  refs      被收起的旧片段 [{key, funcs}]
  pins      钉住的区间 [{file, a, b}]，最多 MAX_PINS 段，和钉住区间重叠的片段永不收起
  latest    最近一次读片段读到的片段键
  step      已完成的步数（笔记追加更新），读片段按 step+1 给片段打步号
  recent    最近两步的 reason+arg 文本（收起时看点名）
  hint      给模型的提示（收起后又读回超过 2 次时写）
  test      当前测试结果摘要（跑测试动词写）
  stats     截断、重读、收起后重读、收起记录、压缩记录、钉住、运行、每次修改的处数
"""

import json
import re
from pathlib import Path

MAX_PINS = 3
REREAD_HINT_AT = 2


def path(ws):
    from _sandbox import state_dir
    return state_dir(ws) / "notes_state.json"


def load(ws):
    p = path(ws)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return new()


def new():
    return {"head": "", "hist": [], "snips": [], "refs": [], "pins": [], "latest": [],
            "step": 0, "recent": [], "hint": "", "test": "",
            "stats": {"trunc": 0, "reread": 0, "reread_ref": 0, "fold": [], "compress": [],
                      "edits": [], "pin": 0, "unpin": 0, "auto_unpin": 0, "runs": []}}


def save(ws, st):
    path(ws).write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def key(s):
    return f'{s["file"]}:{s["a"]}-{s["b"]}'


def parse_key(k):
    f, _, rng = str(k).rpartition(":")
    try:
        x, y = (int(v) for v in rng.split("-"))
    except ValueError:
        return None
    return f, x, y


def funcs_of(root, file, a, b):
    """片段涉及的函数/类：区间开头所在的那个函数 + 区间里定义的。"""
    try:
        lines = (Path(root) / file).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    names = []
    for i in range(min(a, len(lines)), 0, -1):
        m = re.match(r"\s*(?:async\s+)?def\s+(\w+)", lines[i - 1])
        if m:
            names.append(m.group(1))
            break
        if re.match(r"class\s+\w+", lines[i - 1]):
            break
    for i in range(a, min(b, len(lines)) + 1):
        m = re.match(r"\s*(?:async\s+)?(?:def|class)\s+(\w+)", lines[i - 1])
        if m and m.group(1) not in names:
            names.append(m.group(1))
    return names


def pinned(st, s):
    return any(p["file"] == s["file"] and p["a"] <= s["b"] and s["a"] <= p["b"]
               for p in st.get("pins", []))


def add_snip(st, file, a, b, body, step, trunc_note="", funcs=None):
    """新片段放最后；同文件、被新区间覆盖的旧片段删掉（替换而不是重复追加）。
    新区间整个落在已有片段里时不再加一段，把那段挪到最后并刷新步号。返回这段的键。"""
    for s in st["snips"]:
        if s["file"] == file and s["a"] <= a and b <= s["b"]:
            st["snips"].remove(s)
            st["snips"].append(s)
            s["step"] = step
            return key(s)
    keep = []
    for s in st["snips"]:
        if s["file"] == file and a <= s["a"] and s["b"] <= b:
            continue
        keep.append(s)
    st["snips"] = keep + [{"file": file, "a": a, "b": b, "body": body, "step": step,
                           "trunc": trunc_note, "funcs": funcs or []}]
    st["refs"] = [r for r in st["refs"] if not _covered(r["key"], file, a, b)]
    return key(st["snips"][-1])


def _covered(ref, file, a, b):
    k = parse_key(ref)
    return bool(k) and k[0] == file and a <= k[1] and k[2] <= b


def ref_overlaps(st, file, a, b):
    for r in st["refs"]:
        k = parse_key(r["key"])
        if k and k[0] == file and k[1] <= b and a <= k[2]:
            return True
    return False


def note_reread_ref(st):
    st["stats"]["reread_ref"] = st["stats"].get("reread_ref", 0) + 1
    n = st["stats"]["reread_ref"]
    if n > REREAD_HINT_AT:
        st["hint"] = (f"你已多次重读同一片段（被收起后又读回 {n} 次），请钉住需要的片段（钉住的不会被收起）或换个思路"
                      "——例如用「运行」打印中间值，或顺着调用链去看还没读过的函数。")


_LINE_RE = re.compile(r"(?:([\w./]+\.py))?:(\d+)(?:\s*[-~–]\s*(\d+))?|第\s*(\d+)\s*行|(\d+)\s*行")


def mentioned(s, texts):
    """片段在最近两步的 reason/arg 里被点名：函数名（≥4 字）或落在区间里的行号。"""
    for t in texts:
        for fn in s.get("funcs", []):
            if len(fn) >= 4 and re.search(rf"(?<!\w){re.escape(fn)}(?!\w)", t):
                return True
        for m in _LINE_RE.finditer(t):
            f = m.group(1)
            if f and not (f == s["file"] or s["file"].endswith("/" + f)):
                continue
            x = int(m.group(2) or m.group(4) or m.group(5))
            y = int(m.group(3) or x)
            if x <= s["b"] and s["a"] <= y:
                return True
    return False


def fold(st, cur, keep_steps=3):
    """v6 收起：最近 keep_steps 步内读过的、钉住的、最近两步点名过的保留，其余收成引用。
    cur = 即将要做的步号（最近 3 步 = cur-3 … cur-1）。返回收起的片段键列表。"""
    keep, gone = [], []
    for s in st["snips"]:
        recent = isinstance(s.get("step"), int) and s["step"] >= cur - keep_steps
        if recent or pinned(st, s) or mentioned(s, st.get("recent", [])):
            keep.append(s)
        else:
            gone.append(s)
    st["snips"] = keep
    have = {r["key"] for r in st["refs"]}
    for s in gone:
        if key(s) not in have:
            st["refs"].append({"key": key(s), "funcs": s.get("funcs", [])})
    return [key(s) for s in gone]


def render(st):
    parts = [st["head"]]
    if st["hist"]:
        parts.append("【历史动作】\n" + "\n".join(
            f'第 {h["step"]} 步 {h["act"]} {h["arg"]}\n{h["res"]}'.strip() for h in st["hist"]))
    if st["snips"]:
        lat = set(st["latest"])
        body = []
        for s in st["snips"]:
            tag = "（最近一次读到）" if key(s) in lat else ""
            tag += "（已钉住）" if pinned(st, s) else ""
            body.append(f'{s["file"]} {s["a"]}-{s["b"]}{tag}：\n{s["body"]}{s["trunc"]}')
        parts.append("【代码】读过的原文，同一区间只留最新一次；修改成功后自动刷新为改后的内容，不必重读：\n"
                     + "\n\n".join(body))
    if st.get("pins"):
        parts.append("【钉住】" + "、".join(f'{p["file"]}:{p["a"]}-{p["b"]}' for p in st["pins"])
                     + f"（最多 {MAX_PINS} 段，不会被收起；不再需要时「取消钉住」）")
    if st["refs"]:
        parts.append("【已读但已收起的旧片段】" + "；".join(
            f'已读 {r["key"]}' + (f'（含函数 {",".join(r["funcs"])}）' if r.get("funcs") else "")
            for r in st["refs"]) + "（需要原文再读，或读时顺手钉住）")
    if st.get("hint"):
        parts.append("【提示】" + st["hint"])
    if st["test"]:
        parts.append("【当前测试】\n" + st["test"])
    return "\n\n".join(p for p in parts if p).strip()
