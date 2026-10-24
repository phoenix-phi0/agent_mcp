# -*- coding: utf-8 -*-
"""页面实体（「页面 实体 …」，K28a）：只进字段表给 .ui 绑定，不建表。

    cd /workspace/agent_mcp && .venv/bin/python tests/gen/test_page_entity.py

一、解析与校验：新写法解析、旧实体文件不受影响、表行为的旗标写了报错
二、field_table / options_map：页面字段进表（.ui 绑定靠它过 unknown_field）
三、建库路径全跳过：render_sql / ensure_db / 迁移 只加 / models / gen generate
四、被 queries 引用报错（loadcheck.check_page_entities）；唯一旗标检查不误报
五、v3 链路：约定「## 页面字段」→ 骨架生成「页面 实体」→ 比对约定
六、界面编译：页面字段能过 unknown_field，gen build 整条走得通
"""

import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from gen.project import build, ensure_db, generate, init            # noqa: E402
from tools.dslagent import loadcheck                                # noqa: E402
from tools.dslagent.packs.dslproj import contract as C              # noqa: E402
from tools.dslagent.packs.dslproj import project as P               # noqa: E402
from tools.dslagent.v3 import scaffold                              # noqa: E402
from tools.entity import field_table, options_map, parse, render_sql, validate  # noqa: E402
from tools.migrate import migrate_additive                          # noqa: E402

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


ENTITIES = """\
实体 account_student 学生账号
  字段 username 文本 必填 唯一 用户名
  字段 display_name 文本 显示名
结束
"""

PAGE_BLOCK = """
页面 实体 account_view 账号页面
  字段 account_state 文本 状态
  字段 attempt_n 整数 作答数
  字段 pick_kind 枚举 选择,填空 题型
结束
"""

# 全套（真表 + 页面实体）
ALL_ENTITIES = ENTITIES + PAGE_BLOCK


def sect(title):
    print(title)


def t_parse():
    sect("一、解析与校验")
    ents = parse(ALL_ENTITIES)
    check([(e.name, e.page) for e in ents] ==
          [("account_student", False), ("account_view", True)],
          "解析：普通实体 page=False，页面实体 page=True")
    v = ents[1]
    check(v.label == "账号页面" and [f.name for f in v.fields] ==
          ["account_state", "attempt_n", "pick_kind"],
          "页面实体带中文名，字段行照旧解析（含枚举选项）")

    old = parse(Path(ROOT / "kg/entities/user.entity").read_text(encoding="utf-8"))
    check(all(not e.page for e in old) and [e.name for e in old] == ["user", "account_view"],
          "旧实体文件不受影响：kg user.entity 照旧解析，account_view 还是普通实体")
    check("校验没过" not in render_sql(Path(ROOT / "kg/entities/user.entity").read_text(encoding="utf-8"), strict=True),
          "旧实体文件照常建表（两张）")

    bad = """\
实体 account_student 学生账号
  字段 username 文本 必填 用户名
结束

页面 实体 pv 页面
  字段 a 文本 必填 索引 唯一 系统 级联删除 默认 1 关联 account_student 标签
结束
"""
    probs = validate(parse(bad))
    check(len(probs) == 1 and "没有意义" in probs[0] and "必填" in probs[0],
          f"页面实体字段行写表行为的旗标 → 一条报错点齐所有无用旗标：{probs}")

    bad2 = """\
页面 实体 pv 页面
  字段 a 文本 状态
  字段 b 文本 状态
  主键 a
  唯一 a b
结束
"""
    probs2 = validate(parse(bad2))
    check(sum("不用写「主键」" in p for p in probs2) == 1
          and sum("不用写「唯一" in p for p in probs2) == 1,
          f"页面实体写 主键 / 多列唯一 → 报错：{probs2}")

    bad3 = """\
页面 实体 pv 页面
  字段 x 文本 状态
结束

实体 r 记录
  字段 pv 文本 关联 pv
结束
"""
    probs3 = validate(parse(bad3))
    check(any("指向页面实体" in p for p in probs3),
          f"普通实体的「关联」指向页面实体 → 报错：{probs3}")

    ok = parse("""\
页面 实体 pv 页面
  字段 kind 枚举 甲,乙 题型
结束
""")
    check(not validate(ok), "页面实体枚举带选项合法（下拉靠它）")

    try:
        parse("页面 pv 页面\n结束\n")
        check(False, "「页面」后面不写「实体」要报错")
    except Exception as e:
        check("「页面」后面要写「实体」" in str(e), f"「页面」后面不写「实体」要报错：{e}")


def t_field_table():
    sect("二、field_table / options_map")
    ents = parse(ALL_ENTITIES)
    ft = field_table(parse(ALL_ENTITIES))
    for k in ("account_state", "account_view.account_state", "attempt_n", "username"):
        if k not in ft:
            check(False, f"字段表缺 {k}：{sorted(ft)}")
            return
    check(True, "字段表含页面字段（裸名 + 带实体名键）")
    check(options_map(parse(ALL_ENTITIES)).get("pick_kind") == ["选择", "填空"],
          "枚举选项照常进 options_map")


def _project(entity_text=ALL_ENTITIES, queries=None):
    tmp = Path(tempfile.mkdtemp(prefix="test_page_entity_"))
    init(tmp, sample=False)
    (tmp / "entities" / "account.entity").write_text(entity_text, encoding="utf-8")
    for name, sql in queries or []:
        (tmp / "queries" / f"{name}.sql").write_text(sql, encoding="utf-8")
    return tmp


def t_db_paths():
    sect("三、建库路径全跳过")
    sql = render_sql(ALL_ENTITIES, strict=True)
    check("CREATE TABLE account_student" in sql and "account_view" not in sql,
          "render_sql：建真表，页面实体不出现")

    tmp = _project()
    ensure_db(tmp)
    con = sqlite3.connect(tmp / "app.db")
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    con.close()
    check("account_student" in tables and "account_view" not in tables,
          f"ensure_db 建库：{sorted(tables)}")

    r = migrate_additive(tmp / "app.db", tmp / "entities")
    check(r["tables"] == [] and r["columns"] == [] and r["indexes"] == []
          and not any("account_view" in w for w in r["warnings"]),
          f"迁移 只加：不补页面实体的表/列/索引 {r}")

    from tools.entity import render_models
    m = render_models(ALL_ENTITIES)
    check("account_student" in m and "account_view" not in m, "models.py 同样跳过")

    out = "\n".join(generate(tmp))
    qdir = sorted(f.name for f in (tmp / "queries").glob("*.sql"))
    check("跳过实体 account_view" in out
          and not any(f.startswith("account_view") for f in qdir)
          and any(f.startswith("account_student") for f in qdir),
          f"gen generate：跳过页面实体，不产出它的增删改查（{qdir}）")


def t_loadcheck():
    sect("四、queries 引用报错 / 唯一检查不误报")
    tmp = _project(queries=[("account_view_list", "SELECT * FROM account_view")])
    probs = loadcheck.check_page_entities(tmp)
    check(len(probs) == 1 and "account_view_list" in probs[0]
          and "不建表" in probs[0],
          f"queries 引用页面实体 → 报：{probs}")
    (tmp / "queries" / "account_view_list.sql").unlink()
    check(loadcheck.check_page_entities(tmp) == [], "删掉引用后不再报")

    uni = ENTITIES + """
页面 实体 report_view 报表页面
  字段 学号 文本 学号，唯一
结束
""".replace("字段 学号 文本", "字段 stu_no 文本")
    tmp2 = _project(entity_text=uni)
    check(loadcheck.check_entity_uniques(tmp2) == [],
          "页面实体说明文字里的「唯一」不报缺旗标（没有索引可建，两头堵）")
    tmp3 = _project(entity_text=ENTITIES + """
实体 extra 其他
  字段 code 文本 编号，唯一
结束
""")
    check(any("code" in p for p in loadcheck.check_entity_uniques(tmp3)),
          "对照：普通实体说明文字里的「唯一」照样报（不是一刀切关掉）")


CONTRACT = """\
模块 account

## 表
表 account_student
  username 文本 用户名，唯一

## 页面字段
页面 account_view 账号页面
  account_state 文本 状态
  attempt_n 整数 作答数
  pick_kind 枚举 选择,填空 题型
"""


def t_v3_chain():
    sect("五、v3 链路：约定 → 骨架 → 比对")
    c, probs = C.parse(CONTRACT)
    check(not probs, f"约定「## 页面字段」解析通过：{probs}")
    check([pg["名"] for pg in c["页面字段"]] == ["account_view"]
          and [f["名"] for f in c["页面字段"][0]["字段"]] ==
          ["account_state", "attempt_n", "pick_kind"],
          "页面字段的行进 c[\"页面字段\"]")
    check(C.unique_decls(c)["单列"] == [("account_student", "username", CONTRACT.splitlines().index("  username 文本 用户名，唯一") + 1)],
          "唯一声明只认「## 表」，页面字段里的不掺进来")

    text = scaffold.entity_text(c)
    check("页面 实体 account_view 账号页面" in text
          and "  字段 account_state 文本 状态" in text
          and "必填" not in text.split("页面 实体")[1],
          f"骨架按约定生成「页面 实体」，字段不带必填：{text!r}")
    ents = parse(text)
    check(not validate(ents), "骨架产物过实体校验")

    bad_c, _ = C.parse("模块 account\n\n## 页面字段\n页面 Bad-Name\n  x 文本 状态\n页面 account_view 页\n页面 account_view 页\n")
    probs2 = C.check(bad_c, "account", {}, ["account"])
    check(sum("要用英文 snake" in p for p in probs2) == 1
          and sum("重复" in p for p in probs2) == 1,
          f"约定检查：页面实体名要 snake、重复要报：{probs2}")
    both, _ = C.parse("模块 account\n\n## 表\n表 thing\n  a 文本 甲\n\n## 页面字段\n页面 thing 页\n  x 文本 状态\n")
    probs3 = C.check(both, "account", {}, ["account"])
    check(any("一个名字只能是一样" in p for p in probs3),
          f"约定检查：表名和页面实体名撞车要报：{probs3}")

    tmp = _project()
    (tmp / "contracts").mkdir(exist_ok=True)
    (tmp / "contracts" / "account.md").write_text(CONTRACT, encoding="utf-8")
    c2, _ = C.parse(CONTRACT)

    def page_diffs(prj):
        return [d for d in P.compare(prj, "account", c2, ["account"])["差异"]
                if "页面" in d or "account_view" in d]

    check(page_diffs(tmp) == [], f"页面实体写对了 → 比对不报：{page_diffs(tmp)}")

    tmp2 = _project(entity_text=ENTITIES)
    d2 = page_diffs(tmp2)
    check(len(d2) == 1 and "没有对应的" in d2[0],
          f"实体文件里没写页面实体 → 报：{d2}")

    tmp3 = _project(entity_text=ENTITIES.replace("实体 account_student 学生账号", "实体 account_view 账号页面"))
    d3 = page_diffs(tmp3)
    check(any("普通实体" in x and "不要为页面专用字段建真表" in x for x in d3),
          f"页面实体写成了普通实体（会建表）→ 报：{d3}")

    tmp4 = _project(entity_text=ALL_ENTITIES.replace("  字段 attempt_n 整数 作答数\n", ""))
    d4 = page_diffs(tmp4)
    check(any("缺字段" in x and "attempt_n" in x for x in d4),
          f"页面实体缺约定的字段 → 报：{d4}")

    tmp5 = _project(entity_text=ALL_ENTITIES + """
页面 实体 account_view 账号页面
  字段 extra_col 文本 私加的
结束
""")
    d5 = page_diffs(tmp5)
    check(any("多了约定" in x and "extra_col" in x for x in d5),
          f"页面实体私加约定里没有的字段 → 报：{d5}")

    tmp6 = _project(entity_text=ALL_ENTITIES.replace(
        "  字段 attempt_n 整数 作答数", "  字段 attempt_n 文本 作答数"))
    d6 = page_diffs(tmp6)
    check(any("attempt_n" in x and "类型" in x for x in d6),
          f"页面实体字段类型和约定不一致 → 报：{d6}")


UI = """\
界面 自定义 账号
  分组 筛选
    字段 pick_kind 控件 下拉 宽 160px 题型
  结束
  列表 学生表 绑 students
    列 username 用户名
    列 account_state 状态
    列 attempt_n 作答数
  结束
结束
"""


def t_ui_build():
    sect("六、界面编译：页面字段过 unknown_field")
    tmp = _project()
    (tmp / "ui" / "student.ui").write_text(UI, encoding="utf-8")
    try:
        lines = build(tmp)
        check(not any("unknown_field" in x for x in lines),
              f"页面字段过字段表，无 unknown_field：{lines}")
    except Exception as e:
        check(False, f"gen build 抛错：{e}")

    tmp2 = _project(entity_text=ENTITIES)
    (tmp2 / "ui" / "student.ui").write_text(UI, encoding="utf-8")
    try:
        build(tmp2)
        check(False, "对照：没有页面实体时 account_state 应挡编译")
    except Exception as e:
        check("unknown_field" in str(e) or "不在字段表里" in str(e),
              f"对照：没有页面实体时 account_state 挡编译：{str(e)[:120]}")


def main():
    t_parse()
    t_field_table()
    t_db_paths()
    t_loadcheck()
    t_v3_chain()
    t_ui_build()
    print(f"\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
