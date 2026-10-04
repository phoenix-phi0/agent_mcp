# -*- coding: utf-8 -*-
"""对账：库里有、数据文件里已经没有的条目和对照，清掉。

    cd /home/ysc/mcp && .venv/bin/python kg/prune.py        # 只看
    cd /home/ysc/mcp && .venv/bin/python kg/prune.py --删    # 真删

为什么需要这个：导入器（routes/kg_import2.zs）只增只改、不删。它按编号
认记录，所以重复导入安全——但只对「改」和「增」安全。把文件里一条拆成
三条、给条目换了 code、删掉一对对照，旧的那些就留在库里不动，页面上同时
看到新旧两套，而导入那一步一声不响、数字还都对。

对两张表：

  contrast  对照。文件里没有的那对就删。**先做这张**：条目被对照引用着
            时不能删，而那条对照本身可能也是该删的旧数据——先清掉它，
            条目才自由。
  item      条目。文件里没有的删，但被引用着的不删、只报告：
              attempt / mastery 引用着（学习记录，删了就指向空处）
              别的条目 after 指着（学习顺序链会断）
              文件里还在的对照引用着（对照两端不带外键，库拦不住，删了
                就悬空）。早先漏了这一条：拆条目时删掉 ga-kedo、node-kara，
                contrast.jsonl 里那一对还指着它们，导入时被拒、测试才发现

还会报「文件里有、库里没有」：条目那边多半是还没导入；对照那边多半是
文件里有一头写错了或者已经不存在——导入器会拒掉那对，但只在返回值里
提一个数字，很容易看漏。

删是反复删到不动为止的：挡住会级联（旧的 he-to 指着旧的 ni-de，头一轮
ni-de 删不掉，he-to 删掉之后它才自由）。只删一轮会留下看着莫名其妙的残渣。

返回 0 表示库和文件一致；还有没处理掉的就返回 1。
"""

import json
import sqlite3
import sys
from pathlib import Path

PROJ = Path(__file__).resolve().parent


def read_codes(path: Path) -> set:
    out = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            code = (json.loads(line).get("code") or "").strip()
            if code:
                out.add(code)
    return out


def read_pairs(path: Path) -> set:
    """对照在库里是「小的放 a、大的放 b」存的（kg_contrast_add.sql），
    文件里写反了也是同一对，所以这里也排一下序再比。"""
    out = set()
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            x, y = (d.get("a") or "").strip(), (d.get("b") or "").strip()
            if x and y and x != y:
                out.add((min(x, y), max(x, y)))
    return out


def exists(con, code: str) -> bool:
    return bool(con.execute("SELECT 1 FROM node WHERE code = ?", (code,)).fetchone()
                or con.execute("SELECT 1 FROM item WHERE code = ?", (code,)).fetchone())


def item_held(con, code: str) -> str:
    """这个条目被什么引用着；没有引用返回空串。"""
    why = []
    for tbl in ("attempt", "mastery"):
        n, = con.execute(
            f"SELECT COUNT(*) FROM {tbl} WHERE point = ?", (code,)).fetchone()
        if n:
            why.append(f"{tbl} {n} 行")
    refs = [r for r, in con.execute(
        "SELECT code FROM item WHERE after = ?", (code,))]
    if refs:
        tail = "…" if len(refs) > 3 else ""
        why.append(f"被 {'、'.join(refs[:3])}{tail} 的 after 指着")
    pairs = [f"{a}↔{b}" for a, b in con.execute(
        "SELECT a, b FROM contrast WHERE a = ? OR b = ?", (code, code))]
    if pairs:
        why.append(f"对照 {'、'.join(pairs[:3])} 引用着")
    return "；".join(why)


def item_orphans(con, want: set) -> list:
    return sorted({c for c, in con.execute("SELECT code FROM item")} - want)


def main(argv: list, root: Path = None) -> int:
    do_delete = "--删" in argv
    root = Path(root) if root else PROJ
    db = root / "app.db"
    items_src = root / "content" / "items.jsonl"
    pairs_src = root / "content" / "contrast.jsonl"
    if not db.is_file():
        print(f"没有这个库：{db}")
        return 1
    if not items_src.is_file():
        print(f"没有这个文件：{items_src}")
        return 1

    con = sqlite3.connect(db)
    left = 0          # 处理完之后还剩几件事没解决

    # —— 对照 ——————————————————————————————————————————————
    want_p = read_pairs(pairs_src)
    have_p = {(a, b) for a, b in con.execute("SELECT a, b FROM contrast")}
    orphan_p = sorted(have_p - want_p)
    missing_p = sorted(want_p - have_p)
    print(f"对照：文件 {len(want_p)} 对，库里 {len(have_p)} 对")

    if missing_p:
        left += len(missing_p)
        print(f"\n  文件里有、库里没有的 {len(missing_p)} 对（导入时被拒了）：")
        for a, b in missing_p:
            gone = [x for x in (a, b) if not exists(con, x)]
            why = f"   ← {'、'.join(gone)} 不存在" if gone else "   ← 两头都在，重新导入一次"
            print(f"    {a} ↔ {b}{why}")

    if orphan_p:
        print(f"\n  库里有、文件里没有的 {len(orphan_p)} 对：")
        for a, b in orphan_p:
            print(f"    {a} ↔ {b}")
        if do_delete:
            con.executemany("DELETE FROM contrast WHERE a = ? AND b = ?", orphan_p)
            con.commit()
            print(f"  删了 {len(orphan_p)} 对。")
        else:
            left += len(orphan_p)

    # —— 条目 ——————————————————————————————————————————————
    want = read_codes(items_src)
    have = {c for c, in con.execute("SELECT code FROM item")}
    missing = sorted(want - have)
    print(f"\n条目：文件 {len(want)} 条，库里 {len(have)} 条")

    if missing:
        left += len(missing)
        print(f"\n  文件里有、库里没有的 {len(missing)} 条（还没导入？）：")
        for c in missing[:20]:
            print("    " + c)
        if len(missing) > 20:
            print(f"    …还有 {len(missing) - 20} 条")

    first = item_orphans(con, want)
    if first:
        held = {c: w for c in first if (w := item_held(con, c))}
        print(f"\n  库里有、文件里没有的 {len(first)} 条：")
        _show(con, first, held)

        if do_delete:
            gone, rounds = 0, 0
            while True:
                rounds += 1
                free = [c for c in item_orphans(con, want) if not item_held(con, c)]
                if not free:
                    break
                # 课文挂接是内容（导入时整表重灌），不算「挡住」：跟着条目
                # 一起删掉，不然留下指向空处的行。表可能还没建（老库）。
                # 题目同理（每次 py -m kg 都整表重灌），留着的话出到这道题时
                # 找不到条目，判不了
                for tbl in ("item_lesson", "question"):
                    if con.execute("SELECT 1 FROM sqlite_master WHERE type='table'"
                                   " AND name=?", (tbl,)).fetchone():
                        con.executemany(f"DELETE FROM {tbl} WHERE item = ?",
                                        [(c,) for c in free])
                con.executemany("DELETE FROM item WHERE code = ?", [(c,) for c in free])
                con.commit()
                gone += len(free)
            print(f"  删了 {gone} 条（{rounds - 1} 轮）。")
            rest = item_orphans(con, want)
            if rest:
                left += len(rest)
                held = {c: w for c in rest if (w := item_held(con, c))}
                print(f"\n  还剩 {len(rest)} 条删不掉，先把引用处理掉：")
                _show(con, rest, held)
        else:
            left += len(first)
            if held:
                print(f"  （{len(held)} 条现在被挡着，但挡住会级联——删完别的，它们多半也就自由了）")

    con.close()
    print()
    if left:
        print(f"还有 {left} 处没对上。" + ("" if do_delete else "确认要删就加 --删。"))
        return 1
    print("库和文件一致。")
    return 0


def _show(con, codes: list, held: dict) -> None:
    for c in codes:
        row = con.execute("SELECT label FROM item WHERE code = ?", (c,)).fetchone()
        label = row[0] if row else "―"
        mark = f"   ← 挡住：{held[c]}" if c in held else ""
        print(f"    {c:24} | {label}{mark}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
