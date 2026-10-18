# -*- coding: utf-8 -*-
"""tools/dslagent 的 newproj 包：7 个新动词单测（含失败 / 越界路径）、pack 白名单与空跑、固定模板 check、
v2.run_newproj 假模型全流程（成功 / private 误选重写 / custom.zs 坏了撤回重写 / 两次都坏失败）。不调真模型。

    .venv/bin/python tests/tools/test_dslagent_newproj.py
"""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
TMP = Path(tempfile.mkdtemp(prefix="dslagent_np_"))
os.environ["DSLAGENT_STATE"] = str(TMP / "state")
os.environ.pop("NEWPROJ_FORCE_SUBPROCESS", None)

from tools.dslagent import packs, plan as DP, v2 as V      # noqa: E402

DEFS = ROOT / "tools/dslagent/verbs/newproj/defs"
PASS = FAIL = 0
ENT = "实体 book 图书\n  字段 title 文本 必填 书名\n  字段 stock 整数 必填 默认 1 库存\n结束\n"


def check(cond, msg, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✓ " + msg)
    else:
        FAIL += 1
        print("  ✗ " + msg + (f"\n      {str(extra)[:1200]}" if extra != "" else ""))


def verb(name, ws):
    sys.path.insert(0, str(DEFS))
    spec = importlib.util.spec_from_file_location("_t_" + name, DEFS / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.WORKSPACE = Path(ws)
    return getattr(m, name)


def proj(name, ent=ENT):
    p = TMP / name
    (p / "entities").mkdir(parents=True)
    if ent:
        (p / "entities/app.entity").write_text(ent, encoding="utf-8")
    return p


def t_read():
    print("读原文")
    p = proj("rd")
    (p / "a.txt").write_text("l1\nl2\n", encoding="utf-8")
    f = verb("读原文", p)
    r = f("a.txt")
    check(r["ok"] == "是" and r["text"] == "l1\nl2\n", "读原文：无行号原样", r)
    r = f("pack:sys_ent.md")
    check(r["ok"] == "是" and "实体" in r["text"], "pack:sys_ent.md 读到模板自带提示词", r)
    check(f("../x")["ok"] == "否" and "越界" in f("../x")["msg"], "越界拒绝")
    check(f("pack:../newproj.zs")["ok"] == "否", "pack: 也不许越界")
    check(f("nope.txt")["ok"] == "否", "不存在")
    check(f("")["ok"] == "否", "没给路径")
    (p / "big.txt").write_text("x" * 200001, encoding="utf-8")
    check(f("big.txt")["ok"] == "否", "超过 200000 字拒绝")
    (p / "bin.dat").write_bytes(b"\xff\xfe\x00")
    check(f("bin.dat")["ok"] == "否", "非 utf-8 不抛")


def t_validate():
    print("校验实体")
    f = verb("校验实体", TMP)
    r = f(ENT)
    check(r["ok"] == "是" and r["实体数"] == 1, "合法实体", r)
    r = f("实体 a A\n  字段 x 乱写 必填 x\n结束\n")
    check(r["ok"] == "否" and "乱写" in r["errors"], "未知类型 → errors", r)
    check(f("")["ok"] == "否", "空文本")
    check(f("随便一段话")["ok"] == "否", "解析不出实体")
    r = f(ENT, "private", "做个图书管理")
    check(r["ok"] == "否" and "private" in r["errors"], "需求没提登录却选 private → 不过", r)
    check(f(ENT, "private", "要登录，每人只看自己的书")["ok"] == "是", "需求提了登录 → private 放行")
    check(f(ENT, "weird", "x")["ok"] == "否", "模板名不对")


def t_split():
    print("拆分隔块")
    f = verb("拆分隔块", TMP)
    r = f("=== queries/a.sql ===\n```sql\nSELECT 1\n```\n=== queries/b.sql ===\nSELECT 2\n=== routes/x.zs ===\nx\n", "queries/")
    check(r["n"] == 2 and r["files"][0] == {"file": "queries/a.sql", "content": "SELECT 1\n"}, "去围栏、按前缀留", r)
    check(r["rejected"] == ["routes/x.zs"], "前缀外的记入 rejected", r)
    r = f("=== queries/../evil.sql ===\nx\n=== queries/ok.sql ===\ny\n", "queries/")
    check(r["n"] == 1 and "queries/../evil.sql" in r["rejected"], "含 .. 拒绝", r)
    check(f("=== /etc/x ===\nx\n", "/")["n"] == 0, "绝对路径拒绝")
    check(f("没有分隔块", "queries/")["n"] == 0, "无分隔块 n=0")
    check(f("=== a ===\nx", "")["n"] == 0, "没给前缀 n=0")
    check(f("=== routes/custom.zs ===\nx\n=== routes/custom.zsx ===\ny\n", "routes/custom.zs")["n"] == 2, "前缀是纯字符串前缀")


def t_gen():
    print("生成增删改查 / 检查项目 / 项目摘要 / 预编译sql")
    p = proj("gen")
    gen, chk, summ, pre = (verb(n, p) for n in ("生成增删改查", "检查项目", "项目摘要", "预编译sql"))
    r = gen({"项目目录": ".", "模板": "full"})
    check(r["ok"] == "是" and (p / "routes/book.zs").is_file() and (p / "app.db").is_file(), "gen 成功：写出 routes/ 并建库", r)
    r2 = gen(json.dumps({"模板": "full"}))
    check(r2["ok"] == "是", "JSON 字符串参数、重复生成幂等", r2)
    check(chk({})["ok"] == "是", "检查项目：通过", chk({}))
    s = summ({})
    check("book_list" in s["queries"] and any(x["path"] == "/book/list" and x["action"] for x in s["routes"]) and s["uis"], "项目摘要：语句名 / 接口 / 界面", s)
    check("routes/book.zs: POST /book/list" in s["text"], "摘要 text 带所在文件")
    ok = pre({"files": [{"file": "queries/a.sql", "content": "-- c\nSELECT * FROM book WHERE stock < :n;\n"}]}, ENT)
    check(ok["ok"] == "是", "预编译sql：合法", ok)
    bad = pre({"files": [{"file": "queries/a.sql", "content": "SELECT nope FROM book"}, {"file": "queries/b.sql", "content": "SELECT 1"}]}, ENT)
    check(bad["ok"] == "否" and "a.sql" in bad["msg"] and "b.sql" not in bad["msg"], "预编译sql：只报坏的那条", bad)
    check(pre({"files": []}, ENT)["ok"] == "是", "没有 sql 算通过")
    check(pre({"files": [{"file": "q.sql", "content": " "}]}, ENT)["ok"] == "否", "空内容不过")
    check(pre("queries", ENT)["ok"] == "是", "给目录：读其中 *.sql")
    check(pre("../x", ENT)["ok"] == "否", "目录越界")
    check(pre("{bad", ENT)["ok"] == "否", "坏 JSON 不抛")
    check(pre({"files": []}, "")["ok"] == "否", "没给实体文本")
    (p / "routes/custom.zs").write_text("接口 POST /book/list 动作 dup\n  用包 db http\n  返回 {}\n结束\n", encoding="utf-8")
    r = chk({})
    check(r["ok"] == "否" and "重复" in r["msg"], "检查项目：接口重复", r)
    (p / "routes/custom.zs").write_text("接口 POST /book/x 动作 x\n  用包 db http\n", encoding="utf-8")
    r = chk({})
    check(r["ok"] == "否" and "结束" in r["msg"], "检查项目：路由语法错 → msg 带原因", r)
    (p / "routes/custom.zs").unlink()
    # 失败 / 越界
    check(gen({"项目目录": "../out"})["ok"] == "否", "生成：项目目录越界")
    check(chk({"项目目录": "../out"})["ok"] == "否", "检查：项目目录越界")
    check(summ({"项目目录": "../out"})["text"].startswith("[项目摘要]"), "摘要：项目目录越界")
    check(gen("{bad")["ok"] == "否", "生成：坏 JSON")
    r = gen({"模板": "不存在的"})
    check(r["ok"] == "否" and r["msg"], "生成：模板不存在 → msg", r)
    q = proj("gen_badent", "实体 a A\n  字段 x 乱写 必填 x\n结束\n")
    r = verb("生成增删改查", q)({})
    check(r["ok"] == "否" and "乱写" in r["msg"], "生成：实体有错 → ProjectError 转 msg", r)
    check(verb("检查项目", TMP / "nothere")({})["ok"] == "否", "检查：不是项目目录")
    # private
    pv = proj("gen_priv", "实体 note 笔记\n  字段 owner 文本 必填 索引 所有者\n  字段 body 文本 必填 内容\n结束\n")
    r = verb("生成增删改查", pv)({"模板": "private"})
    check(r["ok"] == "是" and (pv / "routes/auth.zs").is_file(), "private：加登录注册", r)
    check(verb("检查项目", pv)({})["ok"] == "是", "private 项目检查通过", verb("检查项目", pv)({}))
    # 解释器：没有 jinja2/flask 时走 .venv 子进程
    os.environ["NEWPROJ_FORCE_SUBPROCESS"] = "1"
    try:
        sp = proj("gen_sub")
        r = verb("生成增删改查", sp)({"模板": "full"})
        c = verb("检查项目", sp)({})
        check(r["ok"] == "是" and (sp / "routes/book.zs").is_file() and c["ok"] == "是", "强制子进程路径：生成 + 检查同样可用", (r, c))
        sp2 = proj("gen_sub2", "实体 a A\n  字段 x 乱写 必填 x\n结束\n")
        check(verb("生成增删改查", sp2)({})["ok"] == "否", "子进程路径：错误也转 msg")
    finally:
        os.environ.pop("NEWPROJ_FORCE_SUBPROCESS")


def t_dry():
    print("空跑占位")
    from tools.dsl import _CURRENT

    class E:
        dry_run = True
    _CURRENT.engine = E()
    try:
        p = proj("dry", None)
        check(verb("校验实体", p)("随便")["ok"] == "是", "校验实体 空跑占位")
        check(verb("生成增删改查", p)({})["ok"] == "是" and not (p / "routes").exists(), "生成增删改查 空跑不写盘")
        check(verb("检查项目", p)({})["ok"] == "是", "检查项目 空跑占位")
        check(verb("预编译sql", p)({"files": []}, "")["ok"] == "是", "预编译sql 空跑占位")
        check(verb("项目摘要", p)({})["queries"], "项目摘要 空跑占位")
    finally:
        _CURRENT.engine = None


def t_pack():
    print("pack 白名单 / 固定模板 check")
    code, np_ = packs.pick("code"), packs.pick("newproj")
    check("newproj" in packs.available() and np_.NAME == "newproj", "newproj 已登记")
    s = "用包 common text code newproj\n预算 调用 3 秒 60\n设 u = 撤回 x\n设 v = 校验实体 x\n"
    kw = dict(verbs=np_.EXTRA_VERBS, packs=np_.EXTRA_PACKS)
    check(DP.whitelist_check(s, {}, libs=(), **kw) == [], "newproj 包：新动词、撤回 / 留底、用包 newproj 都放行", DP.whitelist_check(s, {}, libs=(), **kw))
    pr = DP.whitelist_check(s, {}, libs=(), verbs=code_extra(code), packs=getattr(code, "EXTRA_PACKS", ()))
    check(any("撤回" in x for x in pr) and any("校验实体" in x for x in pr) and any("newproj" in x for x in pr), "code 包行为不变：撤回 / 新动词 / 用包 newproj 仍被拒", pr)
    check(not hasattr(code, "EXTRA_VERBS"), "code 包没有额外放开")
    check(np_.plan_problems("", "", None, ["缺预算"]) == ["缺预算"] and not any("清单" in x for x in np_.plan_problems("", "", None, [])), "newproj 不强制 #清单")
    check(code.plan_problems("", "", None, []) != [], "code 包仍要求 #清单")
    work = TMP / "chk"
    pj = proj("chkproj", None)
    problem, main, subs, rec = V.check(pj, work, np_.TEMPLATE.read_text(encoding="utf-8"), "做个图书管理", np_)
    check(problem == "" and rec.get("空跑假调用") == 4, "固定模板 v2.check 空跑通过（假模型 4 次）", (problem, rec))
    bad, *_ = V.check(pj, TMP / "chk2", np_.TEMPLATE.read_text(encoding="utf-8"), "x", code)
    check("白名单" in bad, "同一模板按 code 包检查会被白名单拒绝", bad)


def code_extra(code):
    return getattr(code, "EXTRA_VERBS", ())


class Fake:
    def __init__(self, ent_tpl=("full",), zs=None, ui=None, sql=None):
        self.tags, self.ent_tpl, self.zs, self.ui, self.n_ent = [], list(ent_tpl), list(zs or [GOOD_ZS]), list(ui or [GOOD_UI]), 0
        self.sql = list(sql or [GOOD_SQL])
        self.prompts, self.systems, self.kws = [], [], []

    def __call__(self, system, user, tag, timeout, model=None, **kw):
        self.tags.append(tag)
        self.prompts.append(user)
        self.systems.append(system)
        self.kws.append(dict(kw, model=model))
        if "JSON 对象" in user:
            tpl = self.ent_tpl[min(self.n_ent, len(self.ent_tpl) - 1)]
            self.n_ent += 1
            ent = ENT if tpl != "private" else ENT + "实体 n 笔记\n  字段 owner 文本 必填 索引 所有者\n结束\n"
            return json.dumps({"模板": tpl, "实体文本": ent}, ensure_ascii=False)
        if "SQLite 语句助手" in user:
            return self.sql.pop(0) if len(self.sql) > 1 else self.sql[0]
        if ".zs 接口助手" in user:
            return self.zs.pop(0) if len(self.zs) > 1 else self.zs[0]
        if ".ui 界面助手" in user:
            return self.ui.pop(0) if len(self.ui) > 1 else self.ui[0]
        return "?"


GOOD_SQL = "=== queries/book_low.sql ===\nSELECT * FROM book WHERE stock < :n\n"
GOOD_ZS = ("=== routes/custom.zs ===\n接口 POST /book/low 动作 book_low\n  用包 db http\n  设 rows = 查询 app.db book_low n={n}\n"
           "  设 group.low = {rows}\n  响应 lists {group}\n结束\n")
BAD_ZS = "=== routes/custom.zs ===\n接口 POST /book/low 动作 book_low\n  用包 db http\n"
GOOD_UI = "=== ui/custom.ui ===\n界面 列表 低库存\n  列表 low 占满\n    列 title 书名\n    列 stock 库存\n  结束\n结束\n"


def go(name, fake, req="做一个图书管理，有书和库存，要查低库存"):
    d = TMP / name
    return V.run_newproj(req, d / "proj", d / "out", model=fake), d / "proj"


def t_flow():
    print("v2.run_newproj 全流程（假模型）")
    f = Fake()
    r, p = go("ok", f)
    check(r["fixed"] and r["calls"] == 4 and (p / "routes/custom.zs").is_file() and (p / "ui/custom.ui").is_file() and (p / "queries/book_low.sql").is_file(),
          "成功：4 次模型调用，custom 三件套落盘", (r["stop"], r["calls"]))
    check("entities/app.entity" in r["changed_files"] and (TMP / "ok/out/result.json").is_file() and (TMP / "ok/out/calls.json").is_file(), "changed_files / 日志文件")
    check(any("提示词" not in x and "SQLite" in x for x in f.prompts), "sql 步骤用了提示词正文")
    ui_prompt = next(x for x in f.prompts if ".ui 界面助手" in x)
    check("不含 id" in ui_prompt and "book_low" in ui_prompt, "ui 提示词：列键必须是实体字段名、不含 id；带 gen/zs 摘要")
    f = Fake(ent_tpl=("private", "full"))
    r, p = go("priv", f)
    check(r["fixed"] and f.n_ent == 2 and r["calls"] == 5 and not (p / "routes/auth.zs").exists(), "需求没提登录却选 private → 带报错重写 1 次后选 full", (r["stop"], f.n_ent))
    check("不许选 private" in [x for x in f.prompts if "JSON 对象" in x][1], "重写提示词里带着报错")
    f = Fake(ent_tpl=("private", "private"))
    r, _ = go("priv2", f)
    check(not r["fixed"] and "实体两次都没过" in r["stop"], "private 两次都选 → 失败", r["stop"])
    f = Fake(zs=[BAD_ZS, GOOD_ZS])
    r, p = go("zsfix", f)
    second = [x for x in f.prompts if ".zs 接口助手" in x][1]
    check(r["fixed"] and r["calls"] == 5 and "上次的报错：" in second and "结束" in second.split("上次的报错：")[1][:200],
          "custom.zs 坏了 → 撤回 → 带报错重写 1 次后通过", (r["stop"], second[-300:]))
    f = Fake(zs=[BAD_ZS])
    r, p = go("zsbad", f)
    check(not r["fixed"] and "custom.zs 两次都没过" in r["stop"] and not (p / "routes/custom.zs").exists(), "两次都坏 → 失败，且坏文件已撤回", (r["stop"], list((p / "routes").glob("*"))))
    r, _ = go("empty", Fake(), req="")
    check(not r["fixed"] and "需求为空" in r["stop"], "需求为空 → 失败")
    rf = TMP / "req.txt"
    rf.write_text("图书管理", encoding="utf-8")
    r, _ = go("reqfile", Fake(), req=str(rf))
    check(r["fixed"], "需求给文件路径也行")


def t_fix3():
    print("newproj 三处修复：系统提示 / 0 文件不放行 / routes")
    f = verb("拆分隔块", TMP)
    r = f(json.dumps({"edits": [{"file": "queries/a.sql", "old": "", "new": "SELECT 1"}]}), "queries/")
    check(r["ok"] == "是" and r["n"] == 1 and r["files"][0] == {"file": "queries/a.sql", "content": "SELECT 1\n"} and r["from_json"] == "是" and r["note"] == "由 JSON 转换",
          "JSON edits（new）→ files，标注由 JSON 转换", r)
    r = f('```json\n{"edits":[{"file":"routes/custom.zs","old":"接口 X","new":""}]}\n```', "routes/custom.zs")
    check(r["n"] == 1 and r["files"][0]["content"] == "接口 X\n", "new 为空取 old；带围栏", r)
    r = f(json.dumps([{"file": "queries/a.sql", "content": "S1"}, {"file": "other/b.sql", "content": "S2"}]), "queries/")
    check(r["n"] == 1 and r["rejected"] == ["other/b.sql"] and r["ok"] == "是", "{file, content} 列表也转；前缀外丢掉", r)
    r = f("=== queries/a.sql ===\nS\n", "queries/")
    check(r["ok"] == "是" and not r.get("from_json"), "分隔块不标 JSON 转换", r)
    for txt in ("", "我觉得不需要", '{"edits": []}'):
        r = f(txt, "queries/")
        check(r["ok"] == "否" and "没有解析到 === 路径 === 分隔块，按格式重写" in r["msg"], f"0 文件不放行：{txt!r}", r)
    for mark in ("无", "（无）", " (无)\n"):
        r = f(mark, "queries/")
        check(r["ok"] == "是" and r["n"] == 0 and r["none"] == "是", f"无标记允许 0 文件：{mark!r}", r)

    from tools.dslagent import agents as AG
    np_sys, SUB_SYS = packs.pick("newproj").model_system(), AG.SUB_JSON.system_text()
    fk = Fake()
    r, _ = go("sys", fk)
    check(r["fixed"] and all(x == np_sys and x != SUB_SYS for x in fk.systems), "newproj 模型调用不带子任务 JSON edits 系统提示", [x[:80] for x in fk.systems])
    check(all("=== 路径 ===" in x for x in fk.systems), "专用系统提示写明分隔块格式")

    fk = Fake(sql=["随便说几句，没有分隔块", GOOD_SQL])
    r, p = go("sql0", fk)
    second = [x for x in fk.prompts if "SQLite 语句助手" in x][1]
    check(r["fixed"] and r["calls"] == 5 and "没有解析到 === 路径 === 分隔块，按格式重写" in second.split("上次的报错：")[1] and (p / "queries/book_low.sql").is_file(),
          "sql 步回散文 → 带报错重写 1 次", (r["stop"], second[-200:]))
    fk = Fake(sql=["随便说几句"])
    r, _ = go("sql0b", fk)
    check(not r["fixed"] and "定制 sql 两次都没过" in r["stop"] and "分隔块" in r["stop"], "sql 两次 0 文件 → 失败", r["stop"])
    fk = Fake(zs=["我来写一下接口……", GOOD_ZS])
    r, p = go("zs0", fk)
    check(r["fixed"] and r["calls"] == 5 and (p / "routes/custom.zs").is_file(), "zs 步 0 文件 → 重写后通过", r["stop"])
    fk = Fake(zs=["没有分隔块的话", "还是没有"])
    r, p = go("zs0b", fk)
    check(not r["fixed"] and "custom.zs 两次都没过" in r["stop"], "zs 空回复两次 → 失败", r["stop"])
    fk = Fake(ui=["随便"])
    r, _ = go("ui0", fk)
    check(not r["fixed"] and "custom.ui 两次都没过" in r["stop"], "ui 两次 0 文件 → 失败", r["stop"])
    fk = Fake(sql=["无"], zs=["（无）"], ui=["无"])
    r, p = go("none", fk)
    check(r["fixed"] and r["calls"] == 4 and not (p / "routes/custom.zs").exists() and not (p / "ui/custom.ui").exists(),
          "三步都回「无」→ 允许 0 文件，4 次调用成功", (r["stop"], r["calls"]))
    fk = Fake(sql=[json.dumps({"edits": [{"file": "queries/book_low.sql", "old": "", "new": "SELECT * FROM book WHERE stock < :n"}]})])
    r, p = go("jsonconv", fk)
    check(r["fixed"] and r["calls"] == 4 and (p / "queries/book_low.sql").is_file(), "模型回 JSON edits 也能落盘（不用重写）", r["stop"])

    old = os.environ.get("DSLAGENT_MODELS")
    os.environ["DSLAGENT_MODELS"] = json.dumps({"sub": "codex:gpt-6-luna:medium"})
    try:
        fk = Fake()
        r, _ = go("routes", fk)
        calls = json.loads((TMP / "routes/out/calls.json").read_text(encoding="utf-8"))
        rows = calls if isinstance(calls, list) else calls.get("calls", calls)
        check(r["fixed"] and rows and all(c.get("engine") == "codex" and c.get("effort") == "medium" and c.get("model") == "gpt-6-luna" for c in rows),
              "DSLAGENT_MODELS.sub 对 newproj 生效（calls.json 记 codex / medium）", rows[:1])
        check(all(k.get("model") == "codex:gpt-6-luna:medium" for k in fk.kws) and r["v2"]["模型"]["sub"] == "codex:gpt-6-luna:medium", "传给 backend 的模型串 / 记录里有实际路由")
        os.environ["DSLAGENT_MODELS"] = "{坏"
        r, _ = go("routes_bad", Fake())
        check(not r["fixed"] and "DSLAGENT_MODELS" in r["stop"], "DSLAGENT_MODELS 不合格 → 明确失败", r["stop"])
        os.environ.pop("DSLAGENT_MODELS")
        fk = Fake()
        r, _ = go("routes_def", fk)
        rows = json.loads((TMP / "routes_def/out/calls.json").read_text(encoding="utf-8"))
        rows = rows if isinstance(rows, list) else rows.get("calls", rows)
        check(r["fixed"] and all(c.get("engine") == "claude" for c in rows), "没设 → 默认 claude(sonnet)", rows[:1])
    finally:
        if old is None:
            os.environ.pop("DSLAGENT_MODELS", None)
        else:
            os.environ["DSLAGENT_MODELS"] = old


def main():
    try:
        t_read()
        t_validate()
        t_split()
        t_gen()
        t_dry()
        t_pack()
        t_flow()
        t_fix3()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{'=' * 50}\n通过 {PASS}，失败 {FAIL}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
