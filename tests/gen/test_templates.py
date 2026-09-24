# -*- coding: utf-8 -*-
"""模板集的产物命名。

    cd /home/ysc/mcp && .venv/bin/python tests/gen/test_templates.py

一、一套里放多个 .zs / .ui 模板，各自生成，不再互相覆盖
二、现有的「默认」「完整」两套，产物名跟改之前一样（已生成的项目不受影响）
三、跨实体撞车：报错，而且一个文件都不写
四、不认识的后缀照旧报错
"""

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import gen.core                                          # noqa: E402
from gen.project import ProjectError, generate, init     # noqa: E402
from gen.templates_ import TemplateError, render         # noqa: E402
from tools.entity import parse                           # noqa: E402

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


ENTITY = """\
实体 note 笔记
  字段 title 文本 必填 标题
结束
"""


def make_set(root: Path, name: str, files: dict) -> None:
    d = root / name
    d.mkdir(parents=True)
    for fname, text in files.items():
        (d / fname).write_text(text, encoding="utf-8")


def main():
    tmp = Path(tempfile.mkdtemp(prefix="tpl_"))
    troot = tmp / "templates"
    note = parse(ENTITY)[0]

    print("一、一套里多个 .zs / .ui 模板")
    make_set(troot, "multi", {
        "routes.zs.j2": "# 主接口 {{ e.name }}\n",
        "admin.zs.j2": "# 管理接口 {{ e.name }}\n",
        "screens.ui.j2": "# 主界面\n",
        "extra.ui.j2": "# 附加界面\n",
        "list.sql.j2": "-- 列表\n",
    })
    out = render(note, "multi", root=troot)
    check(sorted(out) == ["queries/note_list.sql", "routes/note.zs",
                          "routes/note_admin.zs", "ui/note.ui", "ui/note_extra.ui"],
          f"五个模板五个产物：{sorted(out)}")
    check("主接口" in out["routes/note.zs"] and "管理接口" in out["routes/note_admin.zs"],
          "两个 .zs 各是各的内容，没有互相覆盖")

    print("二、现有两套的产物名不变")
    for s in ("default", "full"):
        names = sorted(render(note, s))
        check(names == ["queries/note_delete.sql", "queries/note_insert.sql",
                        "queries/note_list.sql", "queries/note_one.sql",
                        "queries/note_update.sql", "routes/note.zs", "ui/note.ui"],
              f"「{s}」：{names}")

    print("三、跨实体撞车")
    make_set(troot, "clash", {
        "routes.zs.j2": "# {{ e.name }}\n",
        "admin.zs.j2": "# admin {{ e.name }}\n",
    })
    proj = tmp / "proj"
    init(proj, sample=False)
    (proj / "entities" / "a.entity").write_text(
        "实体 note 笔记\n  字段 t 文本 标题\n结束\n\n"
        "实体 note_admin 管理\n  字段 t 文本 标题\n结束\n", encoding="utf-8")
    # 项目生成走的是 gen/templates/，这里临时指到测试用的模板目录
    original = gen.core.render
    gen.core.render = lambda e, s, db, only=None: original(e, s, db, root=troot, only=only)
    try:
        try:
            generate(proj, "clash")
            check(False, "应该报撞车")
        except ProjectError as ex:
            check("note_admin.zs" in str(ex) and "note" in str(ex), f"报错：{ex}")
        written = [p.name for p in (proj / "routes").glob("*")]
        check(written == [], f"一个文件都没写：{written}")
    finally:
        gen.core.render = original

    print("四、不认识的后缀")
    make_set(troot, "bad", {"readme.md.j2": "x"})
    try:
        render(note, "bad", root=troot)
        check(False, "应该报错")
    except TemplateError as ex:
        check("不认识的产物类型" in str(ex), f"报错：{ex}")

    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
