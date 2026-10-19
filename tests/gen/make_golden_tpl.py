# -*- coding: utf-8 -*-
"""生成/比对 gen 模板的 golden：三套 × 样例实体的渲染结果 + private 账号文件。

    .venv/bin/python tests/gen/make_golden_tpl.py          # 重写 golden（只在有意改变产物时）
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.entity import parse                                  # noqa: E402
from gen.templates_ import render                               # noqa: E402

FIX = ROOT / "tests" / "gen" / "fixtures"
GOLDEN = ROOT / "tests" / "gen" / "golden_tpl"
SETS = ("default", "full", "private")


def entities():
    out = []
    for f in sorted(FIX.glob("*.entity")):
        out += parse(f.read_text(encoding="utf-8"))
    return out


def snapshot_sets() -> dict:
    snap = {}
    for s in SETS:
        for e in entities():
            try:
                files = render(e, s)
            except Exception as ex:                      # 要求字段不满足等
                files = {"__error__": type(ex).__name__}
            for rel, text in files.items():
                snap[f"{s}/{e.name}/{rel}"] = text
    return snap


def snapshot_auth() -> dict:
    """private 项目级账号文件：add_auth（必须/可选）+ apply_roles（有/无角色）。"""
    from gen import project as P
    sys.path.insert(0, str(ROOT / "tools" / "dslagent" / "verbs" / "newproj" / "defs"))
    import _gencore as G
    snap = {}
    for tag, optional, roles in (("must", False, ["teacher", "student"]),
                                 ("opt", True, ["admin", "custom"]),
                                 ("plain", False, [])):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "entities").mkdir()
            P.add_auth(root, optional)
            if roles:
                G.apply_roles(root, roles)
            for f in sorted(root.rglob("*")):
                if f.is_file():
                    snap[f"auth/{tag}/{f.relative_to(root).as_posix()}"] = f.read_bytes().decode("utf-8")
    return snap


def snapshot() -> dict:
    return {**snapshot_sets(), **snapshot_auth()}


if __name__ == "__main__":
    snap = snapshot()
    GOLDEN.mkdir(parents=True, exist_ok=True)
    (GOLDEN / "golden.json").write_text(
        json.dumps(snap, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8", newline="\n")
    print(f"{len(snap)} 个产物写入 {GOLDEN / 'golden.json'}")
