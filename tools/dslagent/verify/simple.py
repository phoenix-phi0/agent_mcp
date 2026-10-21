"""简单验收：把资料包的 accept(project, ctx) -> {通过, 问题, 摘要} 包成 verify/__init__.py 里的完整验收接口（check / fix / prepare）。

- check：调 accept；有问题就组补改入参（任务原文 + 问题列表 + 范围内现有文件全文，包可用 fix_input 替换）；
  补改后的复核（stage=补改后）不再组补改入参。没有边界复核（boundary）——验收通过就算成功。
- fix：派 1 次补改（回复 {result:{edits}, status, reason}，edits 能套就套；套用同样过范围拦截）。补改 system 取包的 FIX_SYSTEM，缺省通用文本。
"""
import re
from pathlib import Path

from .. import scope as SC
from .code import dispatch_fix

FIX_SYSTEM_DEFAULT = """你是补改子任务执行者。一个任务已经做完，但验收发现了问题（用户消息里列出）。只根据用户消息给你的数据补改，不能读别的文件，不能运行任何东西。

## 要求
- 每个问题都要处理；只改允许改动范围内的文件，不要改测试文件
- 对外行为按任务原文保持

## 输出
只输出一个 JSON 对象，不要 markdown 围栏，不要别的文字：

{"result": {"edits": [{"file": "…", "old": "…", "new": "…"}], "说明": "…"}, "status": "成功|失败|超出预期", "reason": "…"}

- file：相对项目根的路径；old：要替换的原文，从给你的当前文件一字不差抄（不带行号前缀，含缩进，在文件里唯一）；new：替换后的文本
- 新建文件：old 写空串，new 是完整内容；整份重写已有文件：用一条 edit，old 取整个原文
- status：成功 / 失败 / 超出预期；reason：失败或超出预期时写"""
FILE_CAP, TOTAL_CAP = 12000, 40000
TEXT_SUF = {".py", ".zs", ".md", ".txt", ".json", ".ui", ".entity", ".sql", ".csv", ".yaml", ".yml", ".toml"}


def scope_files(project, scope, cap=TOTAL_CAP):
    """范围内现有文件的全文（带行号前缀；总长超 cap 的略）。"""
    root = Path(project)
    out, total = [], 0
    for f in sorted(root.rglob("*")):
        if not f.is_file() or f.suffix not in TEXT_SUF or any(p.startswith(".") or p == "__pycache__" for p in f.relative_to(root).parts):
            continue
        rel = str(f.relative_to(root))
        if scope and not SC.inside(rel, scope):
            continue
        try:
            txt = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        blk = f"### {rel}（共 {len(txt.splitlines())} 行）\n```\n" + "\n".join(
            f"{i:4d}| {l}" for i, l in enumerate(txt.splitlines(), 1))[:FILE_CAP] + "\n```"
        if total + len(blk) > cap:
            out.append(f"（{rel} 等后面的文件超出长度上限，略）")
            break
        total += len(blk)
        out.append(blk)
    return "\n\n".join(out)


class Simple:
    def __init__(self, pack):
        self.pack = pack
        self.NAME = pack.NAME
        self.FIX_SYS = getattr(pack, "FIX_SYSTEM", FIX_SYSTEM_DEFAULT)

    def prepare(self, project, given, out):
        return self.pack.NAME, ""

    def ctx(self, project, pr, checklist):
        base, cur = pr.get("base") or {}, pr.get("cur") or {}
        from ..snap import changed
        return {"task": pr["task"], "scope": pr.get("scope") or [], "stage": pr.get("stage") or "验收", "out": pr.get("out"),
                "changed": changed(base, cur) if base is not None and cur is not None else [], "base": base, "cur": cur,
                "main": pr.get("main"), "checklist": checklist}

    def check(self, project, pr, checklist):
        ctx = self.ctx(project, pr, checklist)
        r = self.pack.accept(project, ctx)
        probs = [str(x) for x in (r.get("问题") or [])]
        ok = bool(r.get("通过")) and not probs
        after_fix = ctx["stage"] == "补改后"
        summary = str(r.get("摘要") or "\n".join(probs))[:2000]
        acc = pr["accept"]
        acc.setdefault("验收记录", []).append({"阶段": ctx["stage"], "通过": ok, "问题": [p[:400] for p in probs[:12]]})
        gaps = [{"说明": p} for p in probs]
        user = None
        if not ok and not after_fix:
            if hasattr(self.pack, "fix_input"):
                user = self.pack.fix_input(project, ctx, probs)
            else:
                user = (f"【任务原文】\n{pr['task']}\n\n【验收发现的问题】\n" + "\n".join(f"{k}. {p}" for k, p in enumerate(probs, 1))
                        + "\n\n【允许改动范围内现有文件的完整当前内容】\n" + (scope_files(project, ctx["scope"]) or "（还没有文件）"))
        return {"通过": ok, "缺口列表": gaps, "补改系统": self.FIX_SYS, "补改入参": user,
                "原因": "" if ok else "验收没过（已派 1 次补改）：" + "；".join(p[:200] for p in probs[:4]), "测试摘要": summary}

    def fix(self, M, project, chk, tag="fix"):
        return dispatch_fix(M, project, chk["补改系统"], chk["补改入参"], tag)
