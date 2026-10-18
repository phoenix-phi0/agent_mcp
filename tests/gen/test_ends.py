# -*- coding: utf-8 -*-
"""按界面的「端」拆页面：gen/project.py 的 split_pages、build、make_app。

    cd /home/ysc/mcp && .venv/bin/python tests/gen/test_ends.py

一、split_pages：主页面是入口界面的端，没写「端」的归主页面；别的端各一页，
    地址取「认证 角色」的代号，对不上的用 end1；账号页每页都有；只有一端不拆
二、page_options：每页知道别的端在哪个地址、别的页面上有哪些界面
三、build kg 的界面（临时目录）：index.html / teacher.html 各自的界面、标题、
    pages.json；不拆了 pages.json 删掉
四、make_app：/ 和 /teacher、/教师 都是 200，各是各的页面；/teacher/ 跳回
    /teacher；多人模式下页面本身也能打开（登录在页面里），教师接口照样 401
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from gen.project import (PAGES_FILE, build, ensure_db, make_app,  # noqa: E402
                         page_options, split_pages)
from tools.ui import parse                                                       # noqa: E402

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


UI = """\
界面 自定义 做题 端 学生
  文案 做题
结束
界面 表单 登录
  文案 登录
结束
界面 自定义 学情 端 教师
  文案 学情
结束
界面 自定义 关于
  文案 没写端
结束
界面 自定义 学生管理 端 教师
  文案 学生管理
结束
界面 自定义 账本 端 会计
  文案 账本
结束
"""

ROLES = {"teacher": "教师", "student": "学生"}


def names(page):
    return [s.name for s in page["screens"]]


def screen_names(js: str) -> list:
    line = next(x for x in js.splitlines() if x.startswith("const screens = "))
    rows, _ = json.JSONDecoder().raw_decode(line[len("const screens = "):])
    return [s["name"] for s in rows]


def main() -> int:
    print("一、split_pages")
    pages = split_pages(parse(UI), ROLES)
    check([(p["end"], p["slug"], p["main"]) for p in pages]
          == [("学生", "", True), ("教师", "teacher", False), ("会计", "end2", False)],
          f"主页面是入口的端（学生），教师 → teacher，没有代号的会计 → end2："
          f"{[(p['end'], p['slug']) for p in pages]}")
    check(names(pages[0]) == ["做题", "登录", "关于"], f"主页面：学生的 + 没写端的 + 登录：{names(pages[0])}")
    check(names(pages[1]) == ["学情", "学生管理", "登录"],
          f"教师页：自己的界面在前（第一个是落地页），登录在后：{names(pages[1])}")
    check(names(pages[2]) == ["账本", "登录"], f"会计页：{names(pages[2])}")
    one = split_pages(parse("界面 自定义 甲 端 学生\n  文案 a\n结束\n界面 自定义 乙\n  文案 b\n结束\n"), ROLES)
    check(len(one) == 1 and names(one[0]) == ["甲", "乙"], f"只有一端：不拆：{[names(p) for p in one]}")
    check(page_options(one, one[0], ROLES) == {}, "不拆时 page 是空的（前端按不分端的主页面）")
    nolabel = split_pages(parse("界面 自定义 甲\n  文案 a\n结束\n界面 自定义 乙 端 教师\n  文案 b\n结束\n"), ROLES)
    check([(p["end"], p["slug"], names(p)) for p in nolabel] == [("", "", ["甲"]), ("教师", "teacher", ["乙"])],
          f"入口没写端：主页面是没写端的那些，教师另一页：{[(p['end'], names(p)) for p in nolabel]}")

    print("二、page_options")
    t = page_options(pages, pages[1], ROLES)
    check(t["badge"] == "教师端" and t["role"] == "teacher" and not t["main"]
          and t["home"] == {"path": "/", "label": "打开学生端"}, f"教师页：标识、代号、打开学生端：{t}")
    check(t["ends"] == {"学生": "/", "student": "/", "教师": "/teacher", "teacher": "/teacher", "会计": "/end2"},
          f"别的端在哪：{t['ends']}")
    check(t["elsewhere"] == {"做题": "学生", "关于": "学生", "账本": "会计"}, f"教师页上没有的界面：{t['elsewhere']}")
    s = page_options(pages, pages[0], ROLES)
    check(s["main"] and s["badge"] == "" and s["home"] is None
          and set(s["elsewhere"]) == {"学情", "学生管理", "账本"}, f"主页面：{s}")

    tmp = Path(tempfile.mkdtemp(prefix="test_ends_"))
    try:
        print("三、build kg 的界面")
        proj = tmp / "kgcopy"
        proj.mkdir()
        for d in ("ui", "routes", "entities", "queries"):
            shutil.copytree(ROOT / "kg" / d, proj / d)
        ensure_db(proj)
        lines = build(proj, title="日语学习")
        web = proj / "web"
        check(any("教师端：/teacher" in x for x in lines), f"编译日志说了教师端的地址：{lines[-1]}")
        main_js = (web / "app.js").read_text(encoding="utf-8")
        t_js = (web / "teacher.js").read_text(encoding="utf-8")
        check(screen_names(main_js) == ["知识图谱", "登录", "改密码", "学习进度", "做题", "默写", "问老师", "教材"],
              f"学生页（/）：{screen_names(main_js)}")
        check(screen_names(t_js) == ["学情", "学生管理", "AI老师设定", "教材导入", "登录", "改密码"],
              f"教师页（/teacher）：学情在前：{screen_names(t_js)}")
        check("nav-side" not in main_js and "nav-side" not in t_js, "两边都没有「管理」那组（kg 的界面不再写「侧 管理」）")
        main_html = (web / "index.html").read_text(encoding="utf-8")
        t_html = (web / "teacher.html").read_text(encoding="utf-8")
        check("<title>日语学习</title>" in main_html and "<title>日语学习·教师端</title>" in t_html, "两页标题分得开")
        check('src="./teacher.js"' in t_html and 'href="./teacher.css"' in t_html and "./app.js" not in t_html,
              "教师页引自己的 js、css")
        check(json.loads((web / PAGES_FILE).read_text(encoding="utf-8")) == {"teacher": "teacher.html", "教师": "teacher.html"},
              "pages.json：/teacher 和 /教师")

        print("四、make_app")
        app, _ = make_app(proj)
        c = app.test_client()
        r = c.get("/")
        check(r.status_code == 200 and "<title>日语学习</title>" in r.get_data(as_text=True), f"/ 是学生页：{r.status_code}")
        for path in ("/teacher", "/教师"):
            r = c.get(path)
            check(r.status_code == 200 and "日语学习·教师端" in r.get_data(as_text=True), f"{path} 是教师页：{r.status_code}")
        r = c.get("/teacher/")
        check(r.status_code in (301, 302, 308) and r.headers["Location"].endswith("/teacher"),
              f"/teacher/ 跳回 /teacher（不然 ./teacher.js 解析错）：{r.status_code} {r.headers.get('Location')}")
        check(c.get("/teacher.js").status_code == 200 and c.get("/nobody").status_code == 404, "teacher.js 能取，乱打的 404")
        app2, _ = make_app(proj, login=True)
        c2 = app2.test_client()
        check(c2.get("/teacher").status_code == 200 and c2.get("/").status_code == 200,
              "多人模式：两个页面本身都能打开（登录在页面里）")
        r = c2.post("/report/home", json={"form": {}})
        check(r.status_code == 401, f"多人模式没登录调教师接口：401（认证照旧）：{r.status_code}")
        r = c.post("/report/home", json={"form": {}})
        check(r.status_code == 200, f"单人模式调教师接口不要登录：{r.status_code}")

        # 不拆了（都改成一端）：pages.json 删掉，/teacher 不再打开过时的页面
        for f in (proj / "ui").glob("*.ui"):
            f.write_text(f.read_text(encoding="utf-8").replace(" 端 教师", " 端 学生"), encoding="utf-8")
        build(proj)
        check(not (web / PAGES_FILE).exists(), "不拆了：pages.json 删了")
        check(c.get("/teacher").status_code == 404, "/teacher 404")

        # 所有 .ui 都解析失败：build 不抛，但返回里要带「<文件>：解析失败 …」（检查项目靠它判不过）
        for f in (proj / "ui").glob("*.ui"):
            f.unlink()
        (proj / "ui" / "bad.ui").write_text("界面 表单 坏页\n  字段 title 书名\n结束\n", encoding="utf-8")
        lines = build(proj)
        check(any("bad.ui：解析失败" in x and "分组" in x for x in lines), f"没有任何界面可编译时也带出解析失败：{lines}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
