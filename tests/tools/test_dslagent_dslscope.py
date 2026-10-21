# -*- coding: utf-8 -*-
"""v2 的两项补充：DSL 验收检查（verify/dsl.py + _gencore.dsl_verify）、改动范围闸（scope.py + v2 流程）。不调真模型。

    cd /home/ysc/mcp && .venv/bin/python tests/tools/test_dslagent_dslscope.py

  一、DSL：项目根识别；各失败点（坏实体 / 坏 sql 引用 / 重复接口 / 坏 ui）报缺口带文件行号；好项目通过且不碰工作区 app.db；无 DSL 改动跳过
  二、范围：参数 / 计划 #范围 块 / 无 的解析；越界回滚 + 缺口 + 补改；补改后仍越界判部分成功；参数优先于计划块
  三、DSL 检查并入验收流程（假模型）：坏 ui → 补改入参带报错 → 补改修好后成功
"""

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_dslagent_v2 as T            # noqa: E402  复用假模型 / 夹具（导入时设好临时目录环境变量）

from tools.dslagent import scope as SC            # noqa: E402
from tools.dslagent import v2 as V                # noqa: E402
from tools.dslagent.verify import dsl as DV       # noqa: E402

check, TMP = T.check, T.TMP
ENTITY = "实体 note 笔记\n  字段 title 文本 必填 标题\n结束\n"


def gen_proj(base, name="app"):
    root = Path(base) / name
    shutil.rmtree(root, ignore_errors=True)
    (root / "entities").mkdir(parents=True)
    (root / "entities" / "note.entity").write_text(ENTITY, encoding="utf-8")
    r = DV._gen().run_op("generate", {"root": str(root)})
    assert r["ok"] == "是", r
    return root


def edit(root, rel, fn):
    p = Path(root) / rel
    p.write_text(fn(p.read_text(encoding="utf-8")), encoding="utf-8")


def t_roots():
    print("一、项目根识别")
    base = TMP / "roots"
    shutil.rmtree(base, ignore_errors=True)
    gen_proj(base, "app")
    gen_proj(base / "deep", "kg")
    (base / "other").mkdir()
    (base / "other" / "x.zs").write_text("接口 GET /x\n", encoding="utf-8")
    ch = ["app/queries/note_list.sql", "app/ui/note.ui", "deep/kg/routes/note.zs", "other/x.zs", "README.md", "app/a.py"]
    check(DV.project_roots(base, ch) == ["app", "deep/kg"], "改动文件向上找像 gen 项目的目录（去重、多个）", DV.project_roots(base, ch))
    check(DV.project_roots(base, ["other/x.zs", "x.md", "app/a.py"]) == [], "不像项目的目录 / 非 DSL 文件不归任何项目")
    check(DV.check(base, ["app/a.py", "README.md"]) == {"跑了": False, "项目": [], "缺口": []}, "无 DSL 改动：完全跳过")
    check(DV.dsl_files(["a.py", "b.sql", "c.ui"]) == ["b.sql", "c.ui"], "DSL 后缀")


def t_dsl():
    print("一、DSL 检查各失败点")
    base = TMP / "dsl"
    shutil.rmtree(base, ignore_errors=True)
    root = gen_proj(base)
    db = root / "app.db"
    before = db.read_bytes()
    names = sorted(x.name for x in root.rglob("*"))
    r = DV.check(base, ["app/entities/note.entity", "app/ui/note.ui"])
    check(r["跑了"] and not r["缺口"] and r["项目"][0]["ok"], "好项目：通过", r)
    check(db.read_bytes() == before and sorted(x.name for x in root.rglob("*")) == names, "不碰工作区的 app.db，工作区文件不多不少")

    def broken(rel, fn, files=None):
        shutil.rmtree(base, ignore_errors=True)
        rt = gen_proj(base)
        edit(rt, rel, fn)
        return DV.check(base, files or ["app/" + rel])

    r = broken("entities/note.entity", lambda t: t + "垃圾 ???\n")
    g = r["缺口"]
    check(len(g) == 1 and "实体" in g[0]["说明"] and "垃圾" in g[0]["说明"] and g[0].get("行") == 4 and g[0].get("文件") == "app/entities/note.entity",
          "坏实体：报错文本、文件、行号", g)
    r = broken("queries/note_list.sql", lambda t: t)
    check(r["缺口"] == [] and r["跑了"], "（对照）sql 没改坏时没缺口")
    shutil.rmtree(base, ignore_errors=True)
    rt = gen_proj(base)
    (rt / "queries" / "note_list.sql").unlink()
    g = DV.check(base, ["app/queries/note_list.sql"])["缺口"]
    check(g and g[0]["文件"] == "app/routes/note.zs" and isinstance(g[0].get("行"), int) and "note_list" in g[0]["说明"],
          "坏 sql 引用（查询名没有对应 .sql）：指到路由文件和行", g)
    shutil.rmtree(base, ignore_errors=True)
    rt = gen_proj(base)
    shutil.copy(rt / "routes" / "note.zs", rt / "routes" / "note2.zs")
    g = DV.check(base, ["app/routes/note2.zs"])["缺口"]
    check(g and "重复" in g[0]["说明"] and g[0]["文件"].startswith("app/routes/note"), "重复接口", g)
    r = broken("ui/note.ui", lambda t: t + "界面 坏\n  乱七八糟 ???\n")
    g = r["缺口"]
    check(g and g[0]["文件"] == "app/ui/note.ui" and g[0].get("行") and "ui" in g[0]["说明"], "坏 ui：文件 + 行号", g)
    r = broken("routes/note.zs", lambda t: t.replace("接口 ", "接口口 ", 1))
    check(r["缺口"] and "app/routes" in (r["缺口"][0].get("文件") or "app/routes") or r["缺口"], "坏路由语法也报缺口", r["缺口"])


def t_scope_unit():
    print("二、范围解析")
    check(SC.parse("kg/,tests/kg/") == ["kg/", "tests/kg/"] and SC.parse(["./a", "b/"]) == ["a/", "b/"], "参数：逗号 / 列表，规范成目录前缀")
    check(SC.parse(None) == [] and SC.parse("") == [] and SC.parse(" , ") == [], "没有 → 空")
    raw = "用包 x\n终止 成功 好\n#清单\n改 a.py\n#范围\n- kg/\ntests/kg/\n#期望表\n[]\n"
    r, sc = SC.split(raw)
    check(sc == ["kg/", "tests/kg/"] and "#范围" not in r and "#清单\n改 a.py\n#期望表" in r, "计划 #范围 块：切出并保留其余", (r, sc))
    check(SC.split("没有块\n") == ("没有块\n", None), "无块 → None")
    check(SC.outside(["kg/a.py", "kgx/b.py", "tests/kg/t.py", "verbs/db/x.py"], ["kg/", "tests/kg/"]) == ["kgx/b.py", "verbs/db/x.py"]
          and SC.outside(["a"], []) == [], "目录边界匹配；空范围不拦")


EDIT_OLD = '''#改法 e2
@@ 改 docs/old.py
<<<<<<< 原文
def legacy(x):
    return x * 2
=======
def legacy(x):
    return x + x
>>>>>>> 新文
'''
BOTH = T.plan("设 a = 改文件 {e1}\n设 b = 改文件 {e2}\n终止 成功 改了两处", edits=T.EDIT_DOUBLE + "\n" + EDIT_OLD)
OLD_SRC = "def legacy(x):\n    return x * 2\n"


def fixrep(edits):
    return {"result": {"edits": edits, "说明": "x"}, "status": "成功", "reason": ""}


def t_scope_flow():
    print("二、范围闸（假模型流程）")
    f = T.Fake(plan=BOTH)
    r, p, out = T.go("sc_none", f)
    check(r["reply"]["status"] == "成功" and "x + x" in (p / "docs" / "old.py").read_text(encoding="utf-8") and "fix" not in f.tags(),
          "没有范围：不启用闸，行为照旧", r["reply"])

    f = T.Fake(plan=BOTH, fix=fixrep([]))
    r, p, out = T.go("sc_fix", f, scope="pkg/,tests/")
    acc = r["v2"]["验收"]
    fx = next(u for t, _, u in f.log if t == "fix")
    check((p / "docs" / "old.py").read_text(encoding="utf-8") == OLD_SRC, "越界改动恢复成改前内容")
    check("越界改动：docs/old.py" in fx and "只能改 pkg/、tests/ 内的文件" in fx and "【任务原文】" in fx, "缺口交补改，提示只能改范围内的文件", fx[-400:])
    check(r["reply"]["status"] == "成功" and acc["越界"] == [{"阶段": "验收", "文件": ["docs/old.py"], "范围": ["pkg/", "tests/"]}],
          "补改后不再越界 → 成功，越界记进验收记录", (r["reply"], acc.get("越界")))

    f = T.Fake(plan=BOTH, fix=fixrep([{"file": "docs/old.py", "old": OLD_SRC, "new": "def legacy(x):\n    return x + 1\n"}]))
    r, p, out = T.go("sc_still", f, scope=["pkg/", "tests/"])
    check(r["reply"]["status"] == "部分成功" and not r["fixed"] and "补改后仍越界" in r["reply"]["reason"] and "docs/old.py" in r["reply"]["reason"],
          "补改后仍越界 → 部分成功并写原因", r["reply"])
    check((p / "docs" / "old.py").read_text(encoding="utf-8") == OLD_SRC and "x + x" in T.util(p), "仍越界的改动也已恢复，范围内的改动保留")
    check(len(r["v2"]["验收"]["越界"]) == 2 and "bound" not in f.tags(), "两次越界都记录；不再跑边界复核", f.tags())

    f = T.Fake(plan=T.PLAN_OK.replace("终止 成功", "设 z = 1\n终止 成功", 1) + "#范围\npkg/\ntests/\n", fix=fixrep([]))
    r, p, out = T.go("sc_planblock", f)
    check(r["reply"]["status"] == "成功" and "x + x" in T.util(p) and r["v2"]["验收"].get("越界") is None and "fix" not in f.tags(),
          "计划 #范围 块生效（块不影响 .zs 检查）；范围内改动不拦", r["reply"])
    plan2 = BOTH + "#范围\ndocs/\n"
    f = T.Fake(plan=plan2, fix=fixrep([]))
    r, p, out = T.go("sc_planblock2", f)
    check("x + x" not in T.util(p) or r["reply"]["status"] != "成功" or r["v2"]["验收"].get("越界"), "计划块限定 docs/：pkg 的改动越界")
    f = T.Fake(plan=plan2, fix=fixrep([]))
    r, p, out = T.go("sc_argwin", f, scope="pkg/")
    check(r["v2"]["验收"]["越界"][0]["范围"] == ["pkg/"] and r["v2"]["验收"]["越界"][0]["文件"] == ["docs/old.py"], "参数范围优先于计划块")


def t_dsl_flow():
    print("三、DSL 检查并入验收（假模型）")
    p = T.make_proj("dsl_flow")
    gen_proj(p, "app")
    ui = (p / "app" / "ui" / "note.ui").read_text(encoding="utf-8")
    bad = "#改法 e1\n@@ 改 app/ui/note.ui\n<<<<<<< 原文\n" + ui.rstrip("\n").splitlines()[0] + "\n=======\n" + \
          ui.rstrip("\n").splitlines()[0] + "\n# 备注\n界面 坏\n  乱七八糟 ???\n>>>>>>> 新文\n"
    head = "用包 common text code\n预算 调用 4 秒 300\n"
    plan = head + "设 res = 改文件 {e1}\n终止 成功 改 ui\n\n" + bad + "\n#清单\n改 app/ui/note.ui\n"
    good = ui
    f = T.Fake(plan=plan, fix=fixrep([{"file": "app/ui/note.ui", "old": "界面 坏\n  乱七八糟 ???\n", "new": ""}]))
    out = TMP / "out_dsl_flow"
    shutil.rmtree(out, ignore_errors=True)
    r = V.run(p, "改 ui", out, test_cmd=T.TEST_CMD, model=f, boundary=False)
    fx = next((u for t, _, u in f.log if t == "fix"), "")
    acc = r["v2"]["验收"]
    check("fix" in f.tags() and "DSL 检查" in fx and "app/ui/note.ui" in fx and "乱七八糟" in fx, "坏 ui：缺口（带报错、文件）进补改入参", fx[-500:])
    check(r["reply"]["status"] == "成功" and acc["DSL检查"]["缺口"] and not acc["补改后DSL检查"]["缺口"], "补改修好后成功；两次检查都记进验收记录",
          (r["reply"], acc.get("DSL检查")))
    f = T.Fake(plan=plan, fix=fixrep([]))
    shutil.rmtree(out, ignore_errors=True)
    p = T.make_proj("dsl_flow2")
    gen_proj(p, "app")
    r = V.run(p, "改 ui", out, test_cmd=T.TEST_CMD, model=f, boundary=False)
    check(r["reply"]["status"] == "失败" and "DSL 检查没过" in r["reply"]["reason"], "补改没修好 → 失败，原因写 DSL 检查", r["reply"])
    f = T.Fake()
    r, p, _ = T.go("nodsl", f)
    check(r["reply"]["status"] == "成功" and "DSL检查" not in r["v2"]["验收"], "只改 .py：验收里没有 DSL 检查")


def main():
    try:
        t_roots()
        t_dsl()
        t_scope_unit()
        t_scope_flow()
        t_dsl_flow()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{'=' * 50}\n通过 {T.PASS}，失败 {T.FAIL}")
    return 0 if T.FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
