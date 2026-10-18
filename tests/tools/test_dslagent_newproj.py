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


# ------------------------------------------------------------------ split 模板（按功能分次生成）

def feat(name, path=None, act=None, sql=None, ui=True, ifaces=True):
    sql = [name + "_list"] if sql is None else sql
    f = {"名": name, "说明": name, "实体": ["book"], "sql": [{"名": q, "参数": ["n"], "说明": ""} for q in sql],
         "接口": [{"路径": path or f"/book/{name}", "动作": act or f"{name}_act", "说明": ""}] if ifaces else [],
         "界面": [f"{name}页"] if ui else []}
    return f


def inv(*feats, tpl="full"):
    return json.dumps({"模板": tpl, "功能": list(feats)}, ensure_ascii=False)


class FakeS:
    """split 模板假模型：按功能名从提示词里认出是哪个功能；bad={(功能,步骤):[回复…]} 覆盖默认回复（用完回最后一个）。"""

    def __init__(self, invs, bad=None, ent_tpl="full"):
        self.invs, self.bad, self.ent_tpl, self.prompts, self.tags, self.n = list(invs), bad or {}, ent_tpl, [], [], {}
        self.used = {}

    def _pick(self, key, default):
        if key in self.bad:
            seq = self.bad[key]
            i = self.used.get(key, 0)
            self.used[key] = i + 1
            return seq[min(i, len(seq) - 1)]
        return default

    def __call__(self, system, user, tag, timeout, model=None, **kw):
        self.prompts.append(user)
        self.tags.append(tag)
        if "项目拆解助手" in user:
            return self.invs.pop(0) if len(self.invs) > 1 else self.invs[0]
        if "应用建模助手" in user:
            return json.dumps({"模板": self.ent_tpl, "实体文本": ENT}, ensure_ascii=False)
        import re as _re
        if "需求核对员" in user:
            names = _re.findall(r"=== routes/([a-z0-9]+?)(?:_\w+)?\.zs ===", user)
            n = names[0] if names else "?"
            rules = json.loads(_re.search(r"规则：(\[.*?\]) 本功能sql", user, _re.S).group(1))
            ok = json.dumps([{"序号": i, "规则": r, "实现": "是", "依据": "x"} for i, r in enumerate(rules, 1)], ensure_ascii=False)
            return self._pick((n, "chk"), ok)
        m = _re.search(r"本功能：(\{.*?\}) (?:本功能规则|本功能sql|全项目|上次)", user, _re.S) or _re.search(r"本功能：(\{.*\})", user, _re.S)
        f = json.loads(m.group(1)) if m else {"名": "?", "sql": [], "接口": [{"路径": "/x", "动作": "x"}]}
        n = f["名"]
        if "SQLite 语句助手" in user:
            body = "".join(f"=== queries/{q['名']}.sql ===\nSELECT * FROM book WHERE stock < :n\n" for q in f["sql"])
            return self._pick((n, "sql"), body)
        if ".zs 接口助手" in user:
            a = f["接口"][0]
            q = f["sql"][0]["名"] if f["sql"] else "book_list"
            body = (f"=== routes/{n}.zs ===\n接口 POST {a['路径']} 动作 {a['动作']}\n  用包 db http\n  设 rows = 查询 app.db {q} n={{n}}\n"
                    f"  设 group.low = {{rows}}\n  响应 lists {{group}}\n结束\n")
            return self._pick((n, "zs"), body)
        if ".ui 界面助手" in user:
            body = (f"=== ui/{n}.ui ===\n界面 列表 {f['界面'][0]}\n  列表 low 占满\n    列 title 书名\n    列 stock 库存\n  结束\n结束\n")
            return self._pick((n, "ui"), body)
        return "?"


def gos(name, fake, req="做一个图书管理，有低库存等功能", **kw):
    d = TMP / name
    return V.run_newproj(req, d / "proj", d / "out", model=fake, split=True, **kw), d / "proj"


def recs(r):
    return {f["名"]: f for f in r["v2"].get("功能", [])}


def t_split_verbs():
    print("split：校验清单 / 拆分隔块 不覆盖 / 项目摘要 含参数")
    f = verb("校验清单", TMP)
    r = f(inv(feat("a"), feat("b")))
    check(r["ok"] == "是" and r["数量"] == 2 and r["模板"] == "full" and r["调用上限"] == 24, "合法清单：数量 / 模板 / 调用上限 4+10n", r)
    r = f("```json\n" + inv(feat("a")) + "\n```")
    check(r["ok"] == "是", "带围栏也行", r)
    r = f(json.dumps({"模板": "full", "功能": []}))
    check(r["ok"] == "是" and r["数量"] == 0 and r["调用上限"] == 4, "功能为空（纯增删改查）放行", r)
    r = f(json.dumps({"模板": "full", "功能": [{"名": "a", "sql": [], "接口": [], "界面": []}]}))
    check(r["ok"] == "是" and r["功能"][0]["实体"] == [], "缺的列表补 []", r)
    bad = [
        ("", "清单为空"), ("不是json", "合法 JSON"), ("[1]", "JSON 对象"),
        (inv(feat("a"), tpl="x"), "模板"),
        (inv(feat("Bad Name")), "snake"),
        (inv(feat("中文")), "snake"),
        (inv(feat("a"), feat("a", path="/z", act="z")), "功能名「a」重复"),
        (inv(feat("a", sql=["b_x"])), "要以功能名「a_」开头"),
        (inv(feat("a", sql=["a_x", "a_x"])), "sql 名「a_x」重复"),
        (inv(feat("a", sql=["a_x"]), feat("ab", sql=["a_x"], path="/z", act="z")), "sql 名「a_x」重复"),
        (inv(feat("a", path="/p"), feat("b", path="/p", act="bb")), "接口路径「/p」重复"),
        (inv(feat("a", act="same"), feat("b", act="same", path="/q")), "动作名「same」重复"),
        (inv(feat("a", path="nolead")), "要以 / 开头"),
        (inv(feat("a", act="Bad-Act")), "动作名"),
        (json.dumps({"模板": "full", "功能": "x"}), "对象列表"),
    ]
    for txt, want in bad:
        r = f(txt)
        check(r["ok"] == "否" and want in r["errors"], f"清单不过：{want}", r)
    os.environ["NEWPROJ_SPLIT_MAX_FEATURES"] = "2"
    try:
        r = f(inv(feat("a"), feat("b", path="/b", act="b"), feat("c", path="/c", act="c")))
        check(r["ok"] == "否" and "功能太多" in r["errors"], "功能数超过上限（NEWPROJ_SPLIT_MAX_FEATURES）→ 不过", r)
    finally:
        os.environ.pop("NEWPROJ_SPLIT_MAX_FEATURES")

    p = proj("sp_verbs")
    (p / "routes").mkdir()
    (p / "routes/book.zs").write_text("gen\n", encoding="utf-8")
    sp = verb("拆分隔块", p)
    r = sp("=== routes/book.zs ===\n接口\n", "routes/book.zs", "是")
    check(r["ok"] == "否" and "routes/book.zs" in r["msg"] and "不能覆盖" in r["msg"], "不覆盖：已存在的文件被拒", r)
    r = sp("=== routes/book.zs ===\n接口\n", "routes/book.zs")
    check(r["ok"] == "是", "不带不覆盖旧行为不变", r)
    r = sp("=== routes/other.zs ===\nx\n", "routes/book.zs", "是")
    check(r["ok"] == "否" and r["rejected"] == ["routes/other.zs"], "前缀是完整路径：只收这一个文件", r)
    r = sp("=== routes/new.zs ===\nx\n", "routes/new.zs", "是")
    check(r["ok"] == "是" and r["n"] == 1, "不覆盖：新文件放行", r)
    (p / "queries").mkdir()
    (p / "queries/a_x.sql").write_text("SELECT :id, :n, :id\n", encoding="utf-8")
    sm = verb("项目摘要", p)
    check("a_x," not in sm({})["text"] and "a_x" in sm({})["text"], "项目摘要：默认不带参数（旧格式）", sm({})["text"])
    r = sm({"含参数": "是"})
    check("a_x(id,n)" in r["text"] and r["queries"] == ["a_x"], "项目摘要 含参数=是：名(参数,…)", r)


def t_split_flow():
    print("split：v2.run_newproj(split=True) 假模型全流程")
    fk = FakeS([inv(feat("low_stock", path="/book/low", act="book_low"), feat("hot", path="/book/hot", act="book_hot"))])
    r, p = gos("s_ok", fk)
    fs = recs(r)
    check(r["fixed"] and r["v2"]["结论"] == "成功" and r["v2"]["split"] is True, "两个功能全过 = 成功", (r["stop"], r["v2"].get("结论")))
    check(r["calls"] == 8, "调用数 = 清单 1 + 实体 1 + 每功能 3×2", r["calls"])
    check(all((p / x).is_file() for x in ("routes/low_stock.zs", "routes/hot.zs", "ui/low_stock.ui", "ui/hot.ui", "queries/low_stock_list.sql", "queries/hot_list.sql")),
          "每个功能的 sql / zs / ui 按功能名落盘", sorted(str(x.relative_to(p)) for x in p.rglob("*") if x.is_file())[:30])
    check(not (p / "routes/custom.zs").exists(), "不写 custom.zs")
    check(fs["hot"]["步骤"]["zs"] == {"结果": "通过", "尝试": 1, "重写": 0} and set(fs) == {"low_stock", "hot"}, "result.json v2.功能 记每步通过 / 重写次数", fs)
    check(r["v2"]["预算"]["max_calls"] == 24, "预算 调用按功能数放宽 = 4+10×2", r["v2"]["预算"])
    rj = json.loads((TMP / "s_ok/out/result.json").read_text(encoding="utf-8"))
    check(rj["v2"]["功能"] and rj["v2"]["结论"] == "成功", "写进 result.json")
    zs_prompt = next(x for x in fk.prompts if ".zs 接口助手" in x and "hot" in x)
    sql_hot_prompt = next(x for x in fk.prompts if "SQLite 语句助手" in x and '"名":"hot"' in x)
    check("low_stock_list(n)" in sql_hot_prompt and "/book/low" in sql_hot_prompt.split("全项目名字摘要")[1], "第 2 个功能的输入带全项目名字摘要（前一功能的 sql 名+参数、接口路径+动作名）", sql_hot_prompt[-400:])
    check("SELECT * FROM book" not in sql_hot_prompt.split("全项目名字摘要")[1] and "接口 POST /book/low" not in sql_hot_prompt, "摘要只有名字，不给前一功能全文")
    check("hot_list" in zs_prompt and "本功能sql" in zs_prompt, "zs 输入带本功能刚写的 sql")

    fk = FakeS([inv(feat("a", path="/book/a", act="a_x", ui=False), feat("b", path="/book/b", act="b_x", sql=[], ifaces=False, ui=False))])
    r, p = gos("s_skip", fk)
    fs = recs(r)
    check(r["fixed"] and fs["b"]["步骤"]["sql"]["结果"] == "跳过" and fs["a"]["步骤"]["ui"]["结果"] == "跳过", "清单里为空的步骤跳过不调模型", fs)
    check(r["calls"] == 4, "跳过空步骤：清单 + 实体 + a 的 sql、zs = 4 次", r["calls"])

    r, _ = gos("s_none", FakeS([json.dumps({"模板": "full", "功能": []})]))
    check(r["fixed"] and r["calls"] == 2 and r["v2"]["功能"] == [], "功能清单为空 → 只剩实体 + gen，2 次调用成功", (r["stop"], r["calls"]))


def t_split_fail():
    print("split：清单重写 / 单个文件重写 / 单功能失败继续 / 整体结论")
    A, B, C = feat("a", path="/book/a", act="a_x"), feat("b", path="/book/b", act="b_x"), feat("c", path="/book/c", act="c_x")
    fk = FakeS([inv(feat("a", sql=["zz"])), inv(A)])
    r, _ = gos("s_inv_rw", fk)
    second = [x for x in fk.prompts if "项目拆解助手" in x][1]
    check(r["fixed"] and "要以功能名「a_」开头" in second.split("上次的报错：")[1], "清单不过 → 带校验报错重写 1 次后通过", (r["stop"], second[-200:]))
    r, _ = gos("s_inv_bad", FakeS([inv(feat("a", sql=["zz"]))]))
    check(not r["fixed"] and "功能清单两次都没过" in r["stop"] and r["v2"]["结论"] == "失败", "清单两次都不过 → 失败", r["stop"])

    BAD_ZS = "=== routes/a.zs ===\n接口 POST /book/a 动作 a_x\n  用包 db http\n"
    fk = FakeS([inv(A)], bad={("a", "zs"): [BAD_ZS]})
    r, p = gos("s_zs_rw", fk)
    check(not r["fixed"] and "部分成功" in r["stop"] and "a" in r["stop"], "唯一功能 zs 两次坏 → 部分成功（失败列表含 a）", r["stop"])
    check(not (p / "routes/a.zs").exists() and not (p / "queries/a_list.sql").exists(), "失败功能已写的 sql 和坏 zs 全部撤回", sorted(str(x.relative_to(p)) for x in p.rglob("*") if x.is_file()))

    class RW(FakeS):
        """a 的 zs 第 1 次坏、第 2 次好。"""
        def __call__(self, system, user, tag, timeout, model=None, **kw):
            out = super().__call__(system, user, tag, timeout, model, **kw)
            if ".zs 接口助手" in user and '"名":"a"' in user and "上次的报错：无" in user:
                return BAD_ZS
            return out
    fk = RW([inv(A, B)])
    r, p = gos("s_zs_ok2", fk)
    fs = recs(r)
    check(r["fixed"] and fs["a"]["步骤"]["zs"] == {"结果": "通过", "尝试": 2, "重写": 1} and fs["b"]["步骤"]["zs"]["重写"] == 0 and r["calls"] == 9,
          "单个文件第 1 次不过 → 撤回重写 1 次通过；记重写次数 = 1，总 9 次调用", (r["stop"], fs, r["calls"]))
    second = [x for x in fk.prompts if ".zs 接口助手" in x and '"名":"a"' in x][1]
    check("上次的报错：" in second and "上次的报错：无" not in second, "重写提示词带上次报错")

    fk = FakeS([inv(A, B, C)], bad={("b", "zs"): [BAD_ZS.replace("a.zs", "b.zs")], ("c", "ui"): ["随便说几句"]})
    r, p = gos("s_partial", fk)
    fs = recs(r)
    files = sorted(str(x.relative_to(p)) for x in p.rglob("*") if x.is_file() and x.parts[-2] in ("routes", "ui", "queries"))
    check(not r["fixed"] and r["status"] == "失败" and r["v2"]["结论"] == "部分成功" and r["stop"].startswith("部分成功") and "b" in r["stop"] and "c" in r["stop"],
          "b、c 失败 → 部分成功并列出失败功能；不终止整个模板", (r["stop"], r["v2"]["结论"]))
    check(fs["a"]["步骤"]["ui"]["结果"] == "通过" and fs["b"]["步骤"]["zs"]["结果"] == "失败" and fs["b"]["步骤"]["zs"]["尝试"] == 2 and fs["c"]["步骤"]["ui"]["结果"] == "失败"
          and "ui" not in fs["b"]["步骤"], "记录：a 全过，b 在 zs 失败（后面步骤不再跑），c 在 ui 失败", fs)
    check("失败原因" in fs["b"] and fs["b"]["失败步骤"] == "zs", "失败功能带失败步骤 / 原因", fs["b"])
    mine = [x for x in files if "book" not in x]
    check(mine == ["queries/a_list.sql", "routes/a.zs", "ui/a.ui"], "只剩成功功能 a 的文件（b、c 已撤回，gen 的 book 文件还在）", files)

    fk = FakeS([inv(A, B)], bad={("a", "sql"): ["=== queries/a_list.sql ===\nSELECT nope FROM book\n"]})
    r, p = gos("s_sqlbad", fk)
    fs = recs(r)
    check(fs["a"]["步骤"]["sql"] == {"结果": "失败", "尝试": 2, "重写": 1} and "预编译失败" in fs["a"]["失败原因"] and fs["b"]["步骤"]["ui"]["结果"] == "通过",
          "sql 预编译两次不过 → a 失败（未写盘），b 继续", fs)
    check(not (p / "queries/a_list.sql").exists(), "坏 sql 没写盘")

    fk = FakeS([inv(feat("book", path="/book/z", act="z_x", sql=["book_zz"]))], bad={})
    r, p = gos("s_collide", fk)
    check(not r["fixed"] and recs(r)["book"]["步骤"]["zs"]["结果"] == "失败" and "不能覆盖" in recs(r)["book"]["失败原因"],
          "功能名与 gen 路由文件同名 → 不覆盖，该功能失败（gen 的 routes/book.zs 仍在）", (r["stop"], recs(r)))
    check((p / "routes/book.zs").is_file() and "book_list" in (p / "routes/book.zs").read_text(encoding="utf-8"), "gen 的 routes/book.zs 没被动")

    r, _ = gos("s_budget", FakeS([inv(A)]), max_calls=3)
    check(not r["fixed"] and "调用" in r["stop"], "总调用上限仍生效（max_calls=3）", r["stop"])


def t_split_dry_cli():
    print("split：空跑 / 包登记 / CLI 参数 / 旧模板不变")
    np_ = packs.pick("newproj")
    check(np_.SPLIT_TEMPLATE.is_file() and np_.SPLIT_TEMPLATE != np_.TEMPLATE and "校验清单" in np_.EXTRA_VERBS, "SPLIT_TEMPLATE 登记，旧 TEMPLATE 不动")
    pj = proj("sp_dry", None)
    problem, main, subs, rec = V.check(pj, TMP / "sp_dry_work", np_.SPLIT_TEMPLATE.read_text(encoding="utf-8"), "做个图书管理", np_)
    check(problem == "" and rec.get("空跑假调用") == 5, "split 模板 v2.check 空跑走通（占位功能 1 个：清单 + 实体 + sql/zs/ui = 5 次假调用）", (problem, rec))
    for n in ("sys_plan", "sys_fsql", "sys_fzs", "sys_fui"):
        t = (np_.TEMPLATE.parent / "prompts" / f"{n}.md").read_text(encoding="utf-8")
        check("=== " in t or "JSON" in t, f"提示词 {n}.md 存在")
    check("<功能名>" in (np_.TEMPLATE.parent / "prompts/sys_fzs.md").read_text(encoding="utf-8") and "custom" not in (np_.TEMPLATE.parent / "prompts/sys_fui.md").read_text(encoding="utf-8").split("## .ui")[0],
          "zs / ui 提示词按功能名写文件，不再叫 custom")
    r, p = go("old_still", Fake())
    check(r["fixed"] and r["calls"] == 4 and "split" in r["v2"] and r["v2"]["split"] is False and (p / "routes/custom.zs").is_file(), "默认仍是旧模板（4 次调用，custom.zs）")

    from tools.dslagent import __main__ as M
    seen = {}
    real = V.run_newproj
    V.run_newproj = lambda req, project, out, wall=None, split=False, **kw: seen.update(split=split, wall=wall, req=req) or {
        "fixed": True, "calls": 0, "cost": 0, "seconds": 0, "stop": "", "changed_files": []}
    try:
        rq = TMP / "cli_req.txt"
        rq.write_text("需求", encoding="utf-8")
        M.main(["newproj", "--split", str(rq), str(TMP / "cli_p"), "--out", str(TMP / "cli_o")])
        check(seen["split"] is True and seen["wall"] is None, "CLI newproj --split → run_newproj(split=True)，--wall 缺省交给 run_newproj", seen)
        M.main(["newproj", str(rq), str(TMP / "cli_p"), "--out", str(TMP / "cli_o"), "--wall", "100"])
        check(seen["split"] is False and seen["wall"] == 100, "CLI 不带 --split 仍旧模板", seen)
    finally:
        V.run_newproj = real
    old = os.environ.get("DSLAGENT_MODELS")
    os.environ["DSLAGENT_MODELS"] = json.dumps({"sub": "codex:gpt-6-luna:medium"})
    try:
        fk = FakeS([inv(feat("a", path="/book/a", act="a_x"))])
        r, _ = gos("s_routes", fk)
        rows = json.loads((TMP / "s_routes/out/calls.json").read_text(encoding="utf-8"))
        rows = rows if isinstance(rows, list) else rows.get("calls", rows)
        check(r["fixed"] and len(rows) == 5 and all(c.get("engine") == "codex" and c.get("effort") == "medium" for c in rows), "DSLAGENT_MODELS.sub 对 split 全部步骤（含清单）生效", rows[:1])
    finally:
        if old is None:
            os.environ.pop("DSLAGENT_MODELS", None)
        else:
            os.environ["DSLAGENT_MODELS"] = old


# ------------------------------------------------------------------ split：规则核对 / ui 解析失败 / 多文件 / 角色

def rfeat(name, rules, **kw):
    f = feat(name, path=kw.pop("path", f"/book/{name}"), act=kw.pop("act", f"{name}_act"), **kw)
    f["规则"] = rules
    return f


def zs_body(n, path, act, role="", extra_sql=""):
    tail = f" 角色 {role}" if role else ""
    sql = f"=== queries/{extra_sql}.sql ===\nSELECT * FROM book WHERE stock < :n\n" if extra_sql else ""
    return (f"=== routes/{n}.zs ===\n接口 POST {path} 动作 {act}{tail}\n  用包 db http\n  设 rows = 查询 app.db {n}_list n={{n}}\n"
            f"  设 group.low = {{rows}}\n  响应 lists {{group}}\n结束\n" + sql)


def chk_reply(rules, no=()):
    return json.dumps([{"序号": i, "规则": r, "实现": "否" if i in no else "是", "依据": "缺少" if i in no else "x"}
                       for i, r in enumerate(rules, 1)], ensure_ascii=False)


def t_split_rules():
    print("split：规则字段校验 / 拆分隔块多文件 / 检查项目的 ui 解析失败 / 核对规则 / 角色")
    f = verb("校验清单", TMP)
    r = f(inv(rfeat("a", ["规则一", "规则二"])))
    check(r["ok"] == "是" and r["功能"][0]["规则"] == ["规则一", "规则二"], "清单：规则字段是文本列表放行", r)
    r = f(inv(feat("a")))
    check(r["ok"] == "是" and r["功能"][0]["规则"] == [], "清单：没写规则补 []", r)
    for bad, want in ((["x", 1], "规则 要是文本列表"), ("一条文本", "规则 要是文本列表"), (["ok", " "], "规则里有空字符串")):
        r = f(inv(rfeat("a", bad)))
        check(r["ok"] == "否" and want in r["errors"], f"清单：规则 {bad!r} 不过", r)
    # 角色
    def rinv(roles, tpl="private", role="teacher", **kw):
        fe = feat("a")
        if role is not None:
            fe["接口"][0]["角色"] = role
        d = {"模板": tpl, "功能": [fe]}
        if roles is not None:
            d["角色"] = roles
        return json.dumps(d, ensure_ascii=False)
    r = f(rinv(["teacher", "student"]))
    check(r["ok"] == "是" and r["角色"] == ["teacher", "student"] and r["角色模板"] == "private", "清单：角色 + private 放行，返回角色", r)
    check(f(rinv(["teacher"], tpl="full"))["ok"] == "否" and "必须是 private" in f(rinv(["teacher"], tpl="full"))["errors"], "清单：有角色模板不是 private → 不过")
    r = f(rinv(["teacher"], role="boss"))
    check(r["ok"] == "否" and "不在顶层" in r["errors"], "清单：接口角色不在顶层角色里 → 不过", r)
    r = f(rinv(["Teacher"], role=None))
    check(r["ok"] == "否" and "snake" in r["errors"], "清单：角色名要 snake", r)
    r = f(rinv(None, tpl="private", role=None), "老师登录后可以导入题目")
    check(r["ok"] == "否" and "必须给「角色」" in r["errors"], "清单：需求提到登录/老师 却没给角色 → 不过", r)
    check(f(rinv(None, tpl="full", role=None), "做一个图书管理，管库存")["ok"] == "是", "清单：需求没提登录 → 不要求角色")
    check(f(rinv(["teacher", "student"]), "老师登录后可以导入题目")["ok"] == "是", "清单：给了角色 + 需求提登录 → 放行")
    ev = verb("校验实体", TMP)
    r = ev(ENT, "full", "要登录", "private")
    check(r["ok"] == "否" and "private" in r["errors"], "校验实体：清单定了 private 实体步选 full → 不过", r)
    check(ev(ENT, "private", "要登录", "private")["ok"] == "是" and ev(ENT, "full", "x")["ok"] == "是", "校验实体：清单模板一致 / 没给 → 放行")

    # 拆分隔块：多文件命名
    p = proj("sp_multi")
    sp = verb("拆分隔块", p)
    pat = "routes/q.zs|routes/q_*.zs"
    r = sp("=== routes/q.zs ===\na\n=== routes/q_ext.zs ===\nb\n=== routes/other.zs ===\nc\n=== routes/q_a/b.zs ===\nd\n", pat, "是")
    check(r["ok"] == "是" and [x["file"] for x in r["files"]] == ["routes/q.zs", "routes/q_ext.zs"] and len(r["rejected"]) == 2, "多文件命名：q.zs 与 q_*.zs 放行，别的（含子目录）丢掉", r)
    r = sp("=== routes/other.zs ===\nc\n", pat, "是")
    check(r["ok"] == "否" and "routes/q.zs" in r["msg"] and "routes/q_*.zs" in r["msg"] and "routes/other.zs" in r["msg"],
          "全被丢掉时报错说清允许的命名，而不是只说没解析到", r)
    r = sp("=== routes/q.zs ===\na\n=== queries/q_x.sql ===\nSELECT 1\n", "queries/q_*.sql", "是", "是")
    check(r["ok"] == "是" and [x["file"] for x in r["files"]] == ["queries/q_x.sql"], "只取回复里附带的 sql 块", r)
    r = sp("=== routes/q.zs ===\na\n", "queries/q_*.sql", "是", "是")
    check(r["ok"] == "是" and r["n"] == 0, "可空：没有 sql 块也算通过（n=0）", r)
    check(sp("没有块的散文", "queries/q_*.sql", "是", "是")["ok"] == "是", "可空：散文也算没有 sql")

    # 核对规则 / 校验角色 动词
    cr = verb("核对规则", TMP)
    rules = ["判题用库里的题", "写作答记录"]
    r = cr(chk_reply(rules), {"规则": rules})
    check(r["ok"] == "是" and r["未实现列表"] == [], "核对规则：全是 → ok", r)
    r = cr("```json\n" + chk_reply(rules, no=(2,)) + "\n```", {"规则": rules})
    check(r["ok"] == "否" and r["未实现列表"] == ["写作答记录"] and "缺少" in r["未实现"], "核对规则：有『否』→ 未实现带依据（带围栏也行）", r)
    r = cr(json.dumps([{"序号": 1, "实现": "是"}]), {"规则": rules})
    check(r["ok"] == "否" and r["未实现列表"] == ["写作答记录"], "核对规则：回复漏了的规则算否", r)
    r = cr("我觉得都实现了", {"规则": rules})
    check(r["ok"] == "是" and r["解析"] == "否", "核对规则：回复不是 JSON → 核对不了，不拿它当重写理由", r)
    check(cr("x", {"规则": []})["ok"] == "是" and cr("x", {"规则": []})["数量"] == 0, "核对规则：规则为空直接过")
    pr = proj("role_v")
    (pr / "routes").mkdir()
    rv = verb("校验角色", pr)
    fe = {"名": "q", "接口": [{"路径": "/q/a", "动作": "q_a", "角色": "teacher"}, {"路径": "/q/b", "动作": "q_b"}]}
    check(rv(fe)["ok"] == "否" and "没找到" in rv(fe)["msg"], "校验角色：zs 里找不到接口 → 不过", rv(fe))
    (pr / "routes/q.zs").write_text("接口 POST /q/a 动作 q_a\n  返回 {}\n结束\n", encoding="utf-8")
    r = rv(fe)
    check(r["ok"] == "否" and "角色 teacher" in r["msg"] and "/q/a" in r["msg"], "校验角色：接口行没写角色 → 点名接口和写法", r)
    (pr / "routes/q.zs").write_text("接口 POST /q/a 动作 q_a\n  返回 {}\n结束\n", encoding="utf-8")
    (pr / "routes/q_ext.zs").write_text("接口 POST /q/c 动作 q_c 角色 student\n  返回 {}\n结束\n", encoding="utf-8")
    fe2 = {"名": "q", "接口": [{"路径": "/q/c", "动作": "q_c", "角色": "student"}]}
    check(rv(fe2)["ok"] == "是", "校验角色：在 routes/<功能>_*.zs 里也认", rv(fe2))
    (pr / "routes/q.zs").write_text("接口 POST /q/a 动作 q_a 只许 教师\n  返回 {}\n结束\n", encoding="utf-8")
    check(rv(fe)["ok"] == "是", "校验角色：『只许 教师』等同 角色 teacher；没标角色的接口不查", rv(fe))

    # 检查项目：ui 解析失败 = 检查不过
    pg = proj("ui_fail")
    verb("生成增删改查", pg)({"模板": "full"})
    ck = verb("检查项目", pg)
    check(ck({})["ok"] == "是", "gen 的项目检查通过")
    (pg / "ui/badf.ui").write_text("界面 表单 坏页\n  字段 title 书名\n结束\n", encoding="utf-8")
    r = ck({})
    check(r["ok"] == "否" and "ui/badf.ui" in r["msg"] and "字段" in r["msg"] and "分组" in r["msg"], "ui 解析失败 → 检查不过，报错带文件名和 gen 原话", r)
    (pg / "ui/badf.ui").write_text("界面 表单 坏页\n  分组 主体 竖排\n    字段 title 书名\n  结束\n结束\n", encoding="utf-8")
    check(ck({})["ok"] == "是", "改成字段在分组里 → 通过", ck({}))
    pg2 = proj("ui_fail_all")
    verb("生成增删改查", pg2)({"模板": "full"})
    for x in (pg2 / "ui").glob("*.ui"):
        x.unlink()
    (pg2 / "ui/only.ui").write_text("界面 表单 坏页\n  字段 title 书名\n结束\n", encoding="utf-8")
    r = verb("检查项目", pg2)({})
    check(r["ok"] == "否" and "ui/only.ui" in r["msg"], "所有 .ui 都解析失败（没有任何界面）也报出来", r)

    # 流程：规则核对
    R = ["判题用库里的题", "写作答记录"]
    fk = FakeS([inv(rfeat("a", R))])
    r, p = gos("r_ok", fk)
    check(r["fixed"] and r["calls"] == 6 and recs(r)["a"]["步骤"]["核对"] == {"结果": "通过", "尝试": 1, "重写": 0}, "规则核对全是 → 通过，多 1 次调用（共 6 次）", (r["stop"], r["calls"], recs(r)))
    chk_prompt = next(x for x in fk.prompts if "需求核对员" in x)
    check("判题用库里的题" in chk_prompt and "routes/a.zs" in chk_prompt and "SELECT * FROM book" in chk_prompt, "核对输入：规则 + 本功能 sql + zs 全文", chk_prompt[-300:])
    zs_prompt = next(x for x in fk.prompts if ".zs 接口助手" in x)
    check("本功能规则：" in zs_prompt and "写作答记录" in zs_prompt and "逐条实现" in zs_prompt, "zs 输入带规则列表，提示词要求逐条实现")

    fk = FakeS([inv(feat("a"))])
    r, _ = gos("r_empty", fk)
    check(r["fixed"] and r["calls"] == 5 and not any("需求核对员" in x for x in fk.prompts) and recs(r)["a"]["步骤"]["核对"]["结果"] == "跳过", "规则为空 → 跳过核对，不调模型（共 5 次）", (r["calls"], recs(r)))

    bad1 = chk_reply(R, no=(2,))
    fk = FakeS([inv(rfeat("a", R))], bad={("a", "chk"): [bad1, chk_reply(R)]})
    r, p = gos("r_rewrite", fk)
    zs_prompts = [x for x in fk.prompts if ".zs 接口助手" in x]
    check(r["fixed"] and len(zs_prompts) == 2 and "以下业务规则没有实现" in zs_prompts[1].split("上次的报错：")[1] and "写作答记录" in zs_prompts[1].split("上次的报错：")[1],
          "核对有『否』→ 撤回 zs 重写 1 次，报错带未实现规则", (r["stop"], len(zs_prompts)))
    check(r["calls"] == 8 and recs(r)["a"]["步骤"]["zs"]["尝试"] == 2 and "未实现规则" not in recs(r)["a"] and (p / "routes/a.zs").is_file(), "重写后核对通过：8 次调用，无未实现规则", (r["calls"], recs(r)))

    fk = FakeS([inv(rfeat("a", R))], bad={("a", "chk"): [bad1]})
    r, p = gos("r_unimpl", fk)
    fa = recs(r)["a"]
    check(r["v2"]["结论"] == "部分成功" and r["stop"].startswith("部分成功") and not r["fixed"], "重写后仍有未实现 → 部分成功（不判功能失败）", (r["stop"], r["v2"].get("结论")))
    check(fa["未实现规则"] == ["写作答记录"] and fa["步骤"]["核对"]["结果"] == "失败" and "失败原因" not in fa and (p / "routes/a.zs").is_file(), "记入 v2.功能[*].未实现规则，zs 仍保留", fa)
    check(r["calls"] == 8, "规则重写最多 1 次：8 次调用", r["calls"])

    # 规则重写那一轮语法两次都不过 → 放回第一版，仍记未实现
    broken = "=== routes/a.zs ===\n接口 POST /book/a 动作 a_act\n  用包 db http\n"
    good = zs_body("a", "/book/a", "a_act")
    fk = FakeS([inv(rfeat("a", R))], bad={("a", "chk"): [bad1], ("a", "zs"): [good, broken]})
    r, p = gos("r_restore", fk)
    fa = recs(r)["a"]
    check(r["v2"]["结论"] == "部分成功" and fa["未实现规则"] == ["写作答记录"] and "失败原因" not in fa and (p / "routes/a.zs").read_text(encoding="utf-8") == good.split("\n", 1)[1],
          "规则重写的语法重写不过 → 放回第一版（它过了检查），不判失败", (r["stop"], fa))

    # 语法重写与规则重写分开计
    fk = FakeS([inv(rfeat("a", R))], bad={("a", "zs"): [broken, good, good], ("a", "chk"): [bad1, chk_reply(R)]})
    r, _ = gos("r_split_count", fk)
    check(r["fixed"] and recs(r)["a"]["步骤"]["zs"]["尝试"] == 3 and r["calls"] == 9, "语法重写 1 次 + 规则重写 1 次分开计：zs 3 次，共 9 次调用", (r["stop"], r["calls"], recs(r)))

    # zs 回复追加 sql
    extra = zs_body("a", "/book/a", "a_act", extra_sql="a_extra")
    fk = FakeS([inv(rfeat("a", R))], bad={("a", "zs"): [extra]})
    r, p = gos("r_extra_sql", fk)
    check(r["fixed"] and (p / "queries/a_extra.sql").is_file() and (p / "routes/a.zs").is_file(), "zs 回复追加的 queries/<功能>_*.sql 一并写盘", (r["stop"], sorted(x.name for x in (p / "queries").iterdir())))
    bad_sql = zs_body("a", "/book/a", "a_act").replace("=== routes", "=== queries/a_bad.sql ===\nSELECT nope FROM book\n=== routes", 1)
    fk = FakeS([inv(rfeat("a", R))], bad={("a", "zs"): [bad_sql, extra]})
    r, p = gos("r_extra_bad", fk)
    zp = [x for x in fk.prompts if ".zs 接口助手" in x]
    check(r["fixed"] and len(zp) == 2 and "a_bad.sql" in zp[1].split("上次的报错：")[1] and not (p / "queries/a_bad.sql").exists(), "追加的坏 sql 预编译不过 → 带报错重写，坏 sql 不落盘", (r["stop"], len(zp)))
    dup_sql = zs_body("a", "/book/a", "a_act", extra_sql="a_list")
    fk = FakeS([inv(rfeat("a", R))], bad={("a", "zs"): [dup_sql, extra]})
    r, _ = gos("r_extra_dup", fk)
    zp = [x for x in fk.prompts if ".zs 接口助手" in x]
    check(r["fixed"] and len(zp) == 2 and "不能覆盖" in zp[1], "追加的 sql 与已有文件重名 → 不覆盖，带报错重写", (r["stop"], len(zp)))

    # 多文件 zs / ui
    multi = zs_body("a", "/book/a", "a_act") + "=== routes/a_ext.zs ===\n接口 POST /book/a2 动作 a_act2\n  用包 db http\n  设 rows = 查询 app.db a_list n={n}\n  设 group.low = {rows}\n  响应 lists {group}\n结束\n"
    ui2 = ("=== ui/a.ui ===\n界面 列表 a页\n  列表 low 占满\n    列 title 书名\n  结束\n结束\n"
           "=== ui/a_more.ui ===\n界面 列表 a更多\n  列表 low 占满\n    列 stock 库存\n  结束\n结束\n")
    fk = FakeS([inv(feat("a"))], bad={("a", "zs"): [multi], ("a", "ui"): [ui2]})
    r, p = gos("r_multi", fk)
    check(r["fixed"] and (p / "routes/a_ext.zs").is_file() and (p / "ui/a_more.ui").is_file() and recs(r)["a"]["步骤"]["zs"]["结果"] == "通过", "一个功能多个 zs / ui 文件（<功能>_*）都落盘", (r["stop"], recs(r)))
    stray = zs_body("a", "/book/a", "a_act") + "=== routes/account_ext.zs ===\nx\n"
    other_only = "=== routes/other.zs ===\nx\n"
    fk = FakeS([inv(feat("a", ui=False))], bad={("a", "zs"): [other_only, zs_body("a", "/book/a", "a_act")]})
    r, p = gos("r_naming", fk)
    zp = [x for x in fk.prompts if ".zs 接口助手" in x]
    err2 = zp[1].split("上次的报错：")[1] if len(zp) > 1 else ""
    check(r["fixed"] and "routes/a.zs" in err2 and "routes/a_*.zs" in err2 and "routes/other.zs" in err2, "范围外的文件被丢掉，重写报错说清允许的命名", err2[:300])

    # ui 解析失败 → 重写
    bad_ui = "=== ui/a.ui ===\n界面 表单 a页\n  字段 title 书名\n结束\n"
    fk = FakeS([inv(feat("a"))], bad={("a", "ui"): [bad_ui]})
    r, p = gos("r_ui_bad", fk)
    up = [x for x in fk.prompts if ".ui 界面助手" in x]
    err3 = up[1].split("上次的报错：")[1] if len(up) > 1 else ""
    check(len(up) == 2 and "ui/a.ui" in err3 and "分组" in err3 and r["v2"]["结论"] == "部分成功", "ui 解析失败 → 检查不过 → 带文件名和 gen 原话重写；两次都不过该功能失败", (r["stop"], err3[:300]))
    fk = FakeS([inv(feat("a"))], bad={("a", "ui"): [bad_ui, "=== ui/a.ui ===\n界面 表单 a页\n  分组 主体 竖排\n    字段 title 书名\n  结束\n结束\n"]})
    r, p = gos("r_ui_fix", fk)
    check(r["fixed"] and recs(r)["a"]["步骤"]["ui"]["尝试"] == 2, "ui 重写后通过", (r["stop"], recs(r)))

    # 角色
    RINV = lambda role="teacher", tpl="private": json.dumps({"模板": tpl, "角色": ["teacher", "student"], "功能": [dict(feat("a", ui=False), 接口=[{"路径": "/book/a", "动作": "a_act", "角色": role, "说明": ""}])]}, ensure_ascii=False)
    fk = FakeS([RINV()], ent_tpl="private", bad={("a", "zs"): [zs_body("a", "/book/a", "a_act"), zs_body("a", "/book/a", "a_act", role="teacher")]})
    r, p = gos("r_role", fk, req="做一个图书管理，要登录，老师和学生两种账号")
    zp = [x for x in fk.prompts if ".zs 接口助手" in x]
    err4 = zp[1].split("上次的报错：")[1] if len(zp) > 1 else ""
    check(r["fixed"] and len(zp) == 2 and "角色 teacher" in err4 and "/book/a" in err4, "清单标了角色的接口 zs 没写 角色 → 检查不过，带点名报错重写", (r["stop"], err4[:300]))
    check("角色 teacher" in (p / "routes/a.zs").read_text(encoding="utf-8"), "重写后的 zs 带 角色 teacher")
    auth = (p / "routes/auth_roles.zs").read_text(encoding="utf-8") if (p / "routes/auth_roles.zs").is_file() else ""
    check("认证 核对 app.db user_auth" in auth and "认证 角色 teacher 教师" in auth and "认证 角色 student 学生" in auth and (p / "queries/user_auth.sql").is_file(),
          "角色声明接 gen private 的登录：认证 核对 + 认证 角色 + user_auth.sql", auth)
    ue = (p / "entities/user.entity").read_text(encoding="utf-8") if (p / "entities/user.entity").is_file() else ""
    check("字段 role 文本 必填 默认 student" in ue and (p / "routes/auth.zs").is_file(), "user 实体加 role 列（默认最后一个角色），gen 的 auth.zs 还在", ue)
    import sqlite3
    cols = [c[1] for c in sqlite3.connect(p / "app.db").execute("PRAGMA table_info(user)")]
    check("role" in cols, "app.db 的 user 表已有 role 列（先加列再建库）", cols)
    ent_prompt = next(x for x in fk.prompts if "应用建模助手" in x)
    check('角色：["teacher","student"]' in ent_prompt.replace(" ", "") or "teacher" in ent_prompt.split("角色：")[-1][:40], "实体输入带角色", ent_prompt[-200:])
    check(verb("检查项目", p)({})["ok"] == "是", "带角色的 private 项目整体检查通过")
    # 模板选错
    fk = FakeS([RINV()], ent_tpl="full")
    r, _ = gos("r_role_tpl", fk, req="做一个图书管理，要登录，老师和学生两种账号")
    check(not r["fixed"] and "private" in r["stop"], "有角色而实体步选了别的模板 → 重写仍不过则失败", r["stop"])


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
        t_split_verbs()
        t_split_flow()
        t_split_fail()
        t_split_dry_cli()
        t_split_rules()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{'=' * 50}\n通过 {PASS}，失败 {FAIL}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
