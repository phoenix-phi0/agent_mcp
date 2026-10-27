# -*- coding: utf-8 -*-
"""界面「序 n」：项目级的导航顺序和入口（tools/ui_site.py 的 merge、gen/project.py 的 build）。

    cd /home/ysc/mcp && .venv/bin/python tests/gen/test_order.py

一、merge：写了序的按序在前，没写的在后、照文件名序；一个都没写跟原来一样；
    「序 1000」也排在没写的前面；--入口 仍优先；同一端里同序提示、按文件名排；
    两端各从序 1 排不提示，但主页面（/）归哪端是文件名在选时提示
二、build（临时项目）：不带 --入口 时学生页落在序 1 的界面、教师页按序排；
    「侧」跟「序」一起用：右边那组也按序、组的先后跟着序走；带 --入口 时入口优先
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from gen.project import build, ensure_db  # noqa: E402
from tools import ui_site                  # noqa: E402

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


def ui(name, extra=""):
    return f"界面 自定义 {name}{(' ' + extra) if extra else ''}\n  文案 {name}\n结束\n"


def names(screens):
    return [s.name for s in screens]


def screen_names(js: str) -> list:
    line = next(x for x in js.splitlines() if x.startswith("const screens = "))
    rows, _ = json.JSONDecoder().raw_decode(line[len("const screens = "):])
    return [s["name"] for s in rows]


def main() -> int:
    print("一、merge")
    files = {"a_node.ui": ui("知识图谱"), "b_quiz.ui": ui("做题", "序 2"),
             "c_more.ui": ui("学习进度") + ui("教材", "序 3"), "t_chat.ui": ui("问老师", "序 1")}
    ss, notes = ui_site.merge(files)
    check(names(ss) == ["问老师", "做题", "教材", "知识图谱", "学习进度"],
          f"写了序的按序在前，没写的在后、照文件名（和文件内）先后：{names(ss)}")
    check(notes == [], f"不同序、没写序：没有提示：{notes}")

    plain = {"b.ui": ui("乙"), "a.ui": ui("甲") + ui("丙")}
    check(names(ui_site.merge(plain)[0]) == ["甲", "丙", "乙"], "一个都没写序：跟原来一样按文件名")

    big = {"a.ui": ui("甲"), "z.ui": ui("乙", "序 1000")}
    check(names(ui_site.merge(big)[0]) == ["乙", "甲"], "「序 1000」也排在没写序的前面（不是拿 999 充数）")

    ss, _ = ui_site.merge(files, entry="知识图谱")
    check(names(ss)[:2] == ["知识图谱", "问老师"], f"--入口 优先于序：{names(ss)}")

    dup = {"x.ui": ui("甲", "端 学生 序 1"), "a.ui": ui("乙", "端 学生 序 1"), "m.ui": ui("丙", "端 学生 序 0")}
    ss, notes = ui_site.merge(dup)
    check(names(ss) == ["丙", "乙", "甲"], f"同一端同序：按文件名排（a.ui 在 x.ui 前）：{names(ss)}")
    check(len(notes) == 1 and "「序 1」重复" in notes[0] and "乙（a.ui）" in notes[0] and "甲（x.ui）" in notes[0],
          f"同一端同序：提示一声、说清哪两个：{notes}")

    ends = {"report.ui": ui("学情", "端 教师 序 1"), "teacher.ui": ui("问老师", "端 学生 序 1"),
            "assist.ui": ui("教师助手", "端 教师 序 2")}
    ss, notes = ui_site.merge(ends)
    check(not any("重复" in x for x in notes), f"两端各自从序 1 排：不算重复：{notes}")
    check(names(ss)[0] == "学情" and any("主页面" in x and "学情（report.ui）" in x for x in notes),
          f"但主页面归哪端成了文件名在选：提示：{notes}")
    _, notes = ui_site.merge(ends, entry="问老师")
    check(notes == [], f"给了 --入口 就不提示：{notes}")

    tmp = Path(tempfile.mkdtemp(prefix="test_order_"))
    try:
        print("二、build")
        proj = tmp / "proj"
        proj.mkdir()
        for d in ("routes", "entities", "queries"):
            shutil.copytree(ROOT / "kg" / d, proj / d)
        (proj / "ui").mkdir()
        (proj / "ui" / "auth.ui").write_text("界面 表单 登录\n  文案 登录\n结束\n", encoding="utf-8")
        (proj / "ui" / "node.ui").write_text(ui("知识图谱", "端 学生 侧 看看"), encoding="utf-8")
        (proj / "ui" / "progress.ui").write_text(ui("学习进度", "端 学生 侧 看看 序 6"), encoding="utf-8")
        (proj / "ui" / "quiz.ui").write_text(ui("做题", "端 学生 序 2"), encoding="utf-8")
        (proj / "ui" / "report.ui").write_text(ui("学情", "端 教师 序 1"), encoding="utf-8")
        (proj / "ui" / "teacher.ui").write_text(ui("问老师", "端 学生 序 0"), encoding="utf-8")
        (proj / "ui" / "assist.ui").write_text(ui("教师助手", "端 教师 序 2"), encoding="utf-8")
        (proj / "ui" / "import.ui").write_text(ui("教材导入", "端 教师 侧 管理"), encoding="utf-8")
        ensure_db(proj)
        lines = build(proj, title="t")
        web = proj / "web"
        main_js = (web / "app.js").read_text(encoding="utf-8")
        t_js = (web / "teacher.js").read_text(encoding="utf-8")
        check(screen_names(main_js) == ["问老师", "做题", "学习进度", "登录", "知识图谱"],
              f"学生页（/）：序 0 的问老师是入口，有序的在前、没写的（auth.ui、node.ui）照文件名在后：{screen_names(main_js)}")
        check(screen_names(t_js) == ["学情", "教师助手", "教材导入", "登录"],
              f"教师页：学情（序 1）是入口、助手第二、没写序的在后：{screen_names(t_js)}")
        check(not any("重复" in x or "主页面" in x for x in lines), f"这组写法没有提示：{lines}")
        check('<span class="nav-side-h">看看</span>' in main_js and '<span class="nav-side-h">管理</span>' in t_js,
              "「侧」照常生成右边那组")

        lines = build(proj, entry="知识图谱", title="t")
        check(screen_names((web / "app.js").read_text(encoding="utf-8"))[0] == "知识图谱",
              "--入口 优先于序")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
