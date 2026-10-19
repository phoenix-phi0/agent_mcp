# -*- coding: utf-8 -*-
"""gen 模板集清单、继承、golden、`python -m gen tpl` 子命令。

    .venv/bin/python tests/gen/test_tpl.py

一、清单解析（describe / sets / 要求字段 / 旧 requires.txt 兼容）
二、继承（覆盖、@套名/文件、成环、父不存在）
三、golden：三套 × 样例实体 + private 账号文件，逐字节
四、项目级文件渲染（参数、当、未声明参数报错）；关注册补丁 = 模板渲染
五、子命令 list / show / diff / where / render / new / doc / check
六、check 能抓到 坏继承 / 路径冲突 / 缺参数 / 缺要求字段
七、dslagent 的模板名单来自清单
"""

import io
import json
import shutil
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "gen"))

import make_golden_tpl as MG                                    # noqa: E402
from gen import tpl as TPL                                      # noqa: E402
from gen.templates_ import (TEMPLATE_ROOT, TemplateError, chain, describe, products,  # noqa: E402
                            render, render_project, required_fields, sets)
from tools.entity import parse                                  # noqa: E402

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


def run(*argv, root=None):
    """跑 gen tpl 子命令，返回 (退出码, 输出)。"""
    buf = io.StringIO()
    args = (["--root", str(root)] if root else []) + list(argv)
    with redirect_stdout(buf):
        rc = TPL.main(args)
    return rc, buf.getvalue()


def make_root(tmp: Path) -> Path:
    """复制真实模板库当工作台。"""
    dst = tmp / "templates"
    shutil.copytree(TEMPLATE_ROOT, dst)
    return dst


NOTE = parse("实体 note 笔记\n  字段 title 文本 必填 标题\n  字段 owner 文本 必填 索引 归属\n结束\n")[0]


def main():
    tmp = Path(tempfile.mkdtemp(prefix="tpl_"))

    print("一、清单解析")
    check(sets() == ["default", "full", "private"], f"sets()={sets()}（不含 _base）")
    check("_base" in sets(abstract=True), "abstract=True 含 _base")
    d = describe("private")
    check(d["继承"] == "full" and d["继承链"] == ["private", "full", "_base"], f"private 继承链 {d['继承链']}")
    check(d["要求字段"] == ["owner"] and required_fields("private") == ["owner"], "private 要求字段 owner")
    check(required_fields("default") == [], "default 无要求字段")
    check(set(d["参数"]) >= {"认证", "开放注册", "角色", "角色名"}, "private 参数齐")
    check(len(d["项目级文件"]) == 7 and d["项目级文件"][0]["路径"] == "entities/user.entity", "private 项目级文件 7 个")
    check(describe("full")["项目级文件"] == [] and describe("full")["参数"] == {}, "full 无项目级文件 / 参数")
    check(describe("_base")["抽象"] is True, "_base 抽象")
    # 旧 requires.txt 兼容读
    troot = tmp / "t1"
    (troot / "old").mkdir(parents=True)
    (troot / "old" / "requires.txt").write_text("# 注释\nowner\nteam\n", encoding="utf-8")
    check(required_fields("old", troot) == ["owner", "team"], "无清单时读 requires.txt")
    (troot / "old" / "set.json").write_text(json.dumps({"要求字段": ["x"]}), encoding="utf-8")
    check(required_fields("old", troot) == ["x"], "清单优先于 requires.txt")

    print("二、继承")
    r = make_root(tmp)
    check(products("private", r)["list.sql.j2"] == "private" and products("full", r)["list.sql.j2"] == "_base",
          "private 覆盖 list.sql，full 用 _base 的")
    check(products("default", r)["delete.sql.j2"] == "_base", "default 的 delete.sql 继承自 _base")
    # 新套只覆盖一个文件
    (r / "mine").mkdir()
    (r / "mine" / "set.json").write_text(json.dumps({"说明": "x", "继承": "full"}), encoding="utf-8")
    (r / "mine" / "delete.sql.j2").write_text('{% extends "@full/delete.sql.j2" %}{% set 删注 = "（软删）" %}', encoding="utf-8")
    out = render(NOTE, "mine", root=r)
    check("-- 删一条笔记（软删）。" in out["queries/note_delete.sql"], "子套 extends @full/ 并改变量")
    check(out["queries/note_list.sql"] == render(NOTE, "full", root=r)["queries/note_list.sql"], "其余文件同 full")
    # 成环 / 父不存在
    (r / "ca").mkdir(); (r / "cb").mkdir()
    (r / "ca" / "set.json").write_text(json.dumps({"继承": "cb"}), encoding="utf-8")
    (r / "cb" / "set.json").write_text(json.dumps({"继承": "ca"}), encoding="utf-8")
    try:
        chain("ca", r)
        check(False, "成环应报错")
    except TemplateError as ex:
        check("成环" in str(ex), f"成环：{ex}")
    (r / "orphan").mkdir()
    (r / "orphan" / "set.json").write_text(json.dumps({"继承": "nope"}), encoding="utf-8")
    try:
        render(NOTE, "orphan", root=r)
        check(False, "父不存在应报错")
    except TemplateError as ex:
        check("nope" in str(ex) and "不存在" in str(ex), f"父不存在：{ex}")

    print("三、golden 逐字节")
    golden = json.loads((ROOT / "tests" / "gen" / "golden_tpl" / "golden.json").read_text(encoding="utf-8"))
    snap = MG.snapshot()
    check(set(snap) == set(golden), f"产物集合一致（{len(golden)} 个）")
    diff = [k for k in golden if snap.get(k) != golden[k]]
    check(not diff, f"逐字节一致{'' if not diff else '，不一致：' + str(diff[:5])}")
    check(sum(k.startswith("auth/") for k in golden) == 19, "含账号文件 19 个")
    check(any(k.startswith("private/") for k in golden) and any(k.startswith("default/") for k in golden)
          and any(k.startswith("full/") for k in golden), "三套都在 golden 里")

    print("四、项目级文件")
    files = render_project("private")
    check(list(files) == ["entities/user.entity", "queries/user_insert.sql", "queries/user_by_name.sql",
                          "routes/auth.zs", "ui/auth.ui"], "默认参数：5 个文件（角色空 → 不出 user_auth / auth_roles）")
    f2 = render_project("private", {"角色": ["teacher", "student"]})
    check("queries/user_auth.sql" in f2 and "认证 角色 teacher 教师" in f2["routes/auth_roles.zs"], "给角色 → 多 2 个文件")
    check("默认 student 角色" in f2["entities/user.entity"], "user 表 role 列默认最后一个角色")
    check("认证 可选" in render_project("private", {"认证": "可选"})["routes/auth.zs"], "参数 认证=可选")
    try:
        render_project("private", {"没有这个参数": 1})
        check(False, "未声明参数应报错")
    except TemplateError as ex:
        check("没有参数" in str(ex), f"未声明参数：{ex}")
    # 关注册：对已有项目的补丁 与 模板渲染 一致
    from gen import project as P
    pa, pb = tmp / "pa", tmp / "pb"
    for p_ in (pa, pb):
        (p_ / "entities").mkdir(parents=True)
    P.add_auth(pa)
    P.close_register(pa)
    P.add_auth(pb, no_register=True)
    check((pa / "routes/auth.zs").read_bytes() == (pb / "routes/auth.zs").read_bytes(), "close_register 补丁 == 开放注册=false 模板")
    check(P.close_register(pa) == [], "close_register 可重复调用")
    check(b"403" in (pb / "routes/auth.zs").read_bytes(), "关注册后 register 回 403")

    print("五、子命令")
    rc, out = run("list")
    check(rc == 0 and "private" in out and "继承：full → _base" in out, "list")
    rc, out = run("show", "private")
    check(rc == 0 and "覆盖（private）" in out and "继承" in run("show", "default")[1] and "关注册标记" in out, "show（继承/覆盖/参数）")
    check(run("show", "nope")[0] == 1, "show 不存在的套 → 1")
    rc, out = run("diff", "full", "private")
    check(rc == 0 and "AND owner = :current_user" in out, "diff full private")
    rc, out = run("where", "queries/abc_update.sql")
    check(rc == 0 and "private/update.sql.j2" in out and "_base/update.sql.j2" in out, "where 查询路径")
    rc, out = run("where", "routes/auth.zs")
    check(rc == 0 and "项目级文件" in out, "where 项目级文件")
    check(run("where", "queries/zzz.txt")[0] == 1, "where 找不到 → 1")
    ef = tmp / "e.entity"
    ef.write_text("实体 note 笔记\n  字段 title 文本 必填 标题\n  字段 owner 文本 必填 索引 归属\n结束\n"
                  "实体 tag 标签\n  字段 name 文本 必填 名称\n结束\n", encoding="utf-8")
    rc, out = run("render", "private", str(ef))
    check(rc == 0 and "--- queries/note_list.sql ---" in out and "tag_list" not in out, "render 到 stdout（跳过缺 owner 的实体）")
    od = tmp / "outdir"
    rc, out = run("render", "full", str(ef), "--project", "--out", str(tmp / "o2"))
    check(rc == 0, "render --project 对没有项目级文件的套不报错")
    rc, out = run("render", "private", str(ef), "--project", "--out", str(od), "--参数", '角色=["a","b"]')
    check(rc == 0 and (od / "routes/auth_roles.zs").is_file() and (od / "queries/note_list.sql").is_file(), "render --project --out 写到目录")
    check(not (ROOT / "gen" / "out" / "queries" / "note_list.sql").exists(), "render 不写项目")
    r2 = make_root(tmp / "n")
    rc, out = run("new", "mine2", "--from", "full", root=r2)
    check(rc == 0 and (r2 / "mine2" / "set.json").is_file() and describe("mine2", r2)["继承"] == "full", "new 建骨架")
    check(render(NOTE, "mine2", root=r2) == render(NOTE, "full", root=r2), "新套空覆盖 == 基础套")
    check(run("new", "mine2", "--from", "full", root=r2)[0] == 1, "new 已存在 → 1")
    check(run("new", "x1", "--from", "nope", root=r2)[0] == 1, "new 基础套不存在 → 1")
    rc, out = run("doc", root=r2)
    doc = (r2 / "README.md").read_text(encoding="utf-8")
    check(rc == 0 and "## private" in doc and "templates/" in doc and "| 开放注册 |" in doc and "## mine2" in doc, "doc 生成 README")
    real = (TEMPLATE_ROOT / "README.md")
    check(real.is_file() and real.read_text(encoding="utf-8") == TPL.render_doc(), "gen/templates/README.md 与清单同步")

    print("六、check 抓错")
    check(run("check")[0] == 0, "真实模板库 check 全过")
    r3 = make_root(tmp / "c")
    (r3 / "badp").mkdir()
    (r3 / "badp" / "set.json").write_text(json.dumps({"说明": "x", "继承": "nope"}), encoding="utf-8")
    rc, out = run("check", "badp", root=r3)
    check(rc == 1 and "nope" in out, "坏继承")
    (r3 / "cyc1").mkdir(); (r3 / "cyc2").mkdir()
    (r3 / "cyc1" / "set.json").write_text(json.dumps({"说明": "x", "继承": "cyc2"}), encoding="utf-8")
    (r3 / "cyc2" / "set.json").write_text(json.dumps({"说明": "x", "继承": "cyc1"}), encoding="utf-8")
    rc, out = run("check", "cyc1", root=r3)
    check(rc == 1 and "成环" in out, "继承成环")
    (r3 / "clash").mkdir()
    (r3 / "clash" / "set.json").write_text(json.dumps({"说明": "x"}), encoding="utf-8")
    (r3 / "clash" / "routes.zs.j2").write_text("# a\n", encoding="utf-8")
    (r3 / "clash" / "list.sql.j2").write_text("select 1\n", encoding="utf-8")
    check(run("check", "clash", root=r3)[0] == 0, "好的最小套 check 通过")
    # 路径冲突：文件名规则下单实体内很难自然撞车，这里让两个模板算出同一路径来验证检测
    (r3 / "clash2").mkdir()
    (r3 / "clash2" / "set.json").write_text(json.dumps({"说明": "x"}), encoding="utf-8")
    (r3 / "clash2" / "screens.ui.j2").write_text("# a\n", encoding="utf-8")
    import gen.templates_ as TT
    orig = TT._target
    try:
        TT._target = lambda name, ent: "ui/same.ui"          # 所有模板都算到同一路径
        (r3 / "clash2" / "extra.ui.j2").write_text("# b\n", encoding="utf-8")
        rc, out = run("check", "clash2", root=r3)
    finally:
        TT._target = orig
    check(rc == 1 and "覆盖" in out, "产物路径冲突")
    # 缺参数
    (r3 / "noparam").mkdir()
    (r3 / "noparam" / "project").mkdir()
    (r3 / "noparam" / "list.sql.j2").write_text("select 1\n", encoding="utf-8")
    (r3 / "noparam" / "project" / "a.j2").write_text("hi {{ 没声明 }}\n", encoding="utf-8")
    (r3 / "noparam" / "set.json").write_text(json.dumps({
        "说明": "x", "项目级文件": [{"路径": "a.txt", "模板": "project/a.j2", "当": "未知参数"}],
        "参数": {"p": {"说明": "没默认"}}}), encoding="utf-8")
    rc, out = run("check", "noparam", root=r3)
    check(rc == 1 and "未知参数" in out and "缺「默认」" in out, "缺参数声明 / 缺默认")
    (r3 / "noparam" / "set.json").write_text(json.dumps({
        "说明": "x", "项目级文件": [{"路径": "a.txt", "模板": "project/a.j2"}]}), encoding="utf-8")
    rc, out = run("check", "noparam", root=r3)
    check(rc == 1 and "项目级文件渲染失败" in out, "模板用了没声明的参数 → 渲染失败")
    # 缺要求字段：要求字段不在 describe 的样例里补齐则 where; 这里造一套要求 x 但模板引用 e.y
    (r3 / "needf").mkdir()
    (r3 / "needf" / "set.json").write_text(json.dumps({"说明": "x", "要求字段": ["owner"]}), encoding="utf-8")
    (r3 / "needf" / "list.sql.j2").write_text("select {{ e.fields | map(attribute='name') | join(',') }} where {{ e.team }}\n", encoding="utf-8")
    rc, out = run("check", "needf", root=r3)
    check(rc == 1 and "渲染样例实体失败" in out, "模板用了清单没要求的字段 → check 报错")
    # 要求字段缺失时项目生成会跳过实体
    tdir = tmp / "proj"
    (tdir / "entities").mkdir(parents=True)
    (tdir / "entities" / "a.entity").write_text("实体 tag 标签\n  字段 name 文本 必填 名称\n结束\n", encoding="utf-8")
    log = P.generate(tdir, "private")
    check(any("要求字段 owner" in x for x in log), "项目生成：缺 owner 的实体被跳过并说明")

    print("七、dslagent 模板名单来自清单")
    sys.path.insert(0, str(ROOT / "tools" / "dslagent" / "verbs" / "newproj" / "defs"))
    import _tplset
    import _layer
    check(_tplset.names() == tuple(sets()) == _layer.TEMPLATES, "names() == sets() == _layer.TEMPLATES")
    check(_tplset.fill("《模板清单》") == "default / full / private", "提示词标记《模板清单》")
    check("private（每人只看自己的" in _tplset.fill("《模板清单:提示》"), "提示词标记《模板清单:提示》")

    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
