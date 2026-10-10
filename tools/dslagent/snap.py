"""项目快照（v2 的核心和验收共用，与任务类型无关；「哪些文件算项目内容」由当前资料包的 files(project) 决定）。

snapshot(project) → {相对路径: 文本}；changed(before, after) → 变了的相对路径（排序）；code_hash(snap) → 哈希；
diff_text(before, after, limit) → 新建 / 删除 / unified diff 文本；restore(project, base, files) → 把 files 恢复成 base 里的样子。
"""
import difflib
import hashlib
from pathlib import Path

DIFF_CAP = 12000


def snapshot(project, pack=None):
    from . import packs
    pack = pack or packs.current()
    out = {}
    for rel, f in pack.files(project):
        try:
            out[rel] = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            pass
    return out


def changed(before, after):
    return sorted(r for r in set(before) | set(after) if before.get(r) != after.get(r))


def code_hash(snap):
    h = hashlib.sha256()
    for k in sorted(snap):
        h.update(k.encode() + b"\0" + snap[k].encode("utf-8", "replace") + b"\1")
    return h.hexdigest()


def diff_text(before, after, limit=DIFF_CAP):
    parts = []
    for rel in changed(before, after):
        a, b = before.get(rel), after.get(rel)
        if a is None:
            parts.append(f"--- 新建 {rel}\n" + b)
            continue
        if b is None:
            parts.append(f"--- 删除 {rel}")
            continue
        parts.append("\n".join(difflib.unified_diff(a.splitlines(), b.splitlines(), rel, rel, lineterm="", n=2)))
    return "\n".join(parts)[:limit]


def restore(project, base, files):
    """把 files 恢复成 base 里的样子（base 里没有的删掉）。"""
    for rel in files:
        p = Path(project) / rel
        t = base.get(rel)
        if t is None:
            if p.is_file():
                p.unlink()
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(t, encoding="utf-8")
