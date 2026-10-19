# -*- coding: utf-8 -*-
"""防漂移：shared/verbs.md 列出的动词集合 == plan.py 的白名单 ALLOWED_VERBS。不调模型。

    .venv/bin/python tests/tools/test_dslagent_verbs_table.py

有出入时报出「白名单有、表里没有」和「表里有、白名单没有」的动词名。
表里不单列的两个动词（规划里基本用不上）写在 NOT_LISTED，白名单去掉它们时这里会提醒删掉。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.dslagent import plan as P  # noqa: E402

VERBS_MD = P.PKG / "agents" / "shared" / "verbs.md"
NOT_LISTED = {"归一化"}
IN_PROSE = {"列表加项"}      # 只在 并行派任务 的说明文字里点名（「用 列表加项 拼」）

PASS = FAIL = 0


def check(cond, msg, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✓ " + msg)
    else:
        FAIL += 1
        print("  ✗ " + msg + (f"\n    {extra}" if extra else ""))


def listed_verbs(text):
    """顶层「- 」行：每个「；」分段的首词（首段一律算；后段只认已知动词名，免得把说明文字当动词）。
    IN_PROSE 里的动词只要正文点名也算已列出。"""
    known = P.ALLOWED_VERBS | P.ALL_VERBS
    got = set()
    for line in text.splitlines():
        if not line.startswith("- "):
            continue
        for i, seg in enumerate(line[2:].split("；")):
            w = seg.split()[0] if seg.split() else ""
            if i == 0 or w in known:
                got.add(w)
    return got | {v for v in IN_PROSE if v in text}


def t_table():
    print("一、verbs.md 的动词 == 白名单")
    text = VERBS_MD.read_text(encoding="utf-8")
    listed = listed_verbs(text)
    expect = P.ALLOWED_VERBS - NOT_LISTED
    check(NOT_LISTED <= P.ALLOWED_VERBS, "NOT_LISTED 都还在白名单里", f"已不在白名单：{sorted(NOT_LISTED - P.ALLOWED_VERBS)}")
    missing = sorted(expect - listed)
    extra = sorted(listed - P.ALLOWED_VERBS)
    check(not missing, "白名单里的动词表里都有", f"表里缺：{missing}")
    check(not extra, "表里没有白名单外的动词", f"表里多：{extra}")


def main():
    t_table()
    print(f"\n通过 {PASS}，失败 {FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
