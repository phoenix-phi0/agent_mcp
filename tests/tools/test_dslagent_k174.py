# -*- coding: utf-8 -*-
"""K174：简报补强（依赖伪代码 / 设计声明写死盘点 / 用例数据值域）+ G1 约定闸（audit2 开头跑 v3/contracts.check，含豁免）。

覆盖（全离线：历史快照用 git archive / git show 从本仓库取，假模型，不调真模型）：
  ① 依赖伪代码（brief a）：deps_of 附上游函数的伪代码节选（dep_body：超长截断并注明全文位置）；
     deps_md 同一模块同一上游只列一次；module_md 加「被调函数的伪代码」一节
     （K171 实验 A：Haiku 缺上游 vocab 的语义、不肯猜）；kg_v4 实测 assist_draft.生成草稿 截断为 8/15 行
  ② 设计声明 load_declare（brief b）：箭头 / Tab / K168 5 列 / 值域 四种写法；正则写错、新来源不是 模块.函数、值域少列都进「问题」
  ③ 写死盘点 scan_hardcodes：约定（函数的返回 + 伪代码）、services、ui 三处；新来源函数自己的块和提到新来源函数名的行不算；
     人设正则排除「你是想…」问句（K168 §5.2）；hardcode_md 列 文件:行、注释行标记、找不到时的说法、按模块过滤
  ④ 用例值域 case_domain_issues（brief c）：K161 回放夹具（f6ede27 把 levels=空 改成 初一,初二 的行还原回去）报出
     quiz 7/7、assist_draft 6/6（另有 校验草稿本科目条目 等 2 条已知额外命中）；f6ede27 原样 0 条；
     当前 HEAD 误报 2 条（目标 ≤2）；哨兵值「全部」、空值、用例名点名的概念不查；rows_json 里的 JSON 对象也查；
     设计声明的 值域 行加字段
  ⑤ 豁免（G1）：写对就免（表名前缀 / 可选传空）；规则名不对、没写理由、可选传空没点名入参、豁免没对上下一行的违约、
     点错入参都报；问题文字不提示豁免写法；kg_v4 全项目 contracts.check 0 条
  ⑥ 约定闸（G1）：默认拦截——有违约的 audit2 立刻 contract_issue、不跑回归不派核查员（0 次模型调用）；
     m4-rest 快照（K148 时期）11 条被拦下（含 assist_material 改材料_标题为空，K148 停下的原因）；
     提醒 = contract_warnings 照常审；关 = 不查（同 K174 之前）；范围外模块的违约进 skipped_issues 不拦；
     豁免对上后放行；干净项目不受影响。默认参数下 fix2 行为不变的逐字对比见 test_dslagent_brief ⑦
  ⑦ CLI：--contract-check / --declare 的参数校验；brief --declare 端到端；设计声明的问题行打到 stderr

    /workspace/agent_mcp/.venv/bin/python tests/tools/test_dslagent_k174.py
"""
import re
import difflib
import io
import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "tools"))

import test_dslagent_v3 as T                                   # noqa: E402  复用 v3 测试的假模型 / 参考项目
from tools.dslagent.v3 import brief as B, contracts as VC, core, top as VT   # noqa: E402

PASS = FAIL = 0
SNAP = {}

QUIZ7 = {"跨科目_追加题目其它科目带编码前缀", "跨科目_追加题目其它科目缺编码前缀400", "跨科目_追加题目公开科目非负责教师403",
         "跨科目_追加题目学生403", "跨科目_追加题目协作教师可写", "跨科目_删助手题目公开科目非负责教师403",
         "跨科目_导入题库保留本科目助手题不动别科目"}
AD6 = {"跨科目_确认草稿权限被收回403", "跨科目_确认草稿学生403", "跨科目_确认草稿协作教师题号带科目编码",
       "跨科目_放弃草稿只读老师也能放弃自己的", "跨科目_撤销草稿只读老师403", "跨科目_撤销草稿协作教师可撤"}


def check(cond, msg, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
    print(("  ✓ " if cond else "  ✗ ") + msg + ("" if cond or extra == "" else f"\n      {str(extra)[:1500]}"))


def snapshot(rev):
    """本仓库 rev 的 kg_v4 → 临时目录里的项目路径（同一 rev 只导一次；取不到返回 None）。"""
    if rev in SNAP:
        return SNAP[rev]
    r = subprocess.run(["git", "-C", str(ROOT), "archive", rev, "kg_v4"], capture_output=True)
    if r.returncode != 0:
        SNAP[rev] = None
        return None
    d = T.fresh(f"k174_{rev.replace('-', '_')}_")
    with tarfile.open(fileobj=io.BytesIO(r.stdout)) as tf:
        tf.extractall(d)
    SNAP[rev] = d / "kg_v4"
    return SNAP[rev]


def copy_snapshot(rev, name):
    import shutil
    src = snapshot(rev)
    if src is None:
        return None
    d = T.fresh(name) / "kg_v4"
    shutil.copytree(src, d)
    return d


def need(p, rev):
    check(p is not None, f"取到历史快照 {rev}（git archive）")
    return p is not None


def k161_project():
    """f6ede27 的 kg_v4，把 K161 提交里 levels=空 → levels=初一,初二 改动的那几行还原回去（人工修数据之前的状态）。"""
    p = copy_snapshot("f6ede27", "k174_k161")

    def show(rev, path):
        r = subprocess.run(["git", "-C", str(ROOT), "show", f"{rev}:{path}"], capture_output=True, text=True)
        return r.stdout.split("\n")

    for f in ("quiz", "assist_draft"):
        path = f"kg_v4/contracts/{f}.md"
        old, new = show("f6ede27~1", path), show("f6ede27", path)
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
            if tag != "replace":
                continue
            for k in range(j1, j2):
                cand = new[k].replace("levels=初一,初二", "levels=空")
                if cand != new[k] and cand in old[i1:i2]:
                    new[k] = cand
        (p / "contracts" / f"{f}.md").write_text("\n".join(new), encoding="utf-8")
    return p


def test_dep_body():
    print("①依赖伪代码（brief a）")
    uf = {"伪代码": [{"文字": f"第{i}句" + "字" * 100} for i in range(30)]}
    d = B.dep_body(uf, limit=250)
    check(d["截断"] is True and len(d["行"]) == 2 and d["共"] == 30 and not d["行"][-1].endswith("…"),
          "dep_body 超 250 字截断：放得下的整行放、放不下且余量 <80 字的那行不放", d)
    d = B.dep_body(uf, limit=290)
    check(d["截断"] is True and len(d["行"]) == 3 and d["行"][-1].endswith("…"), "余量 ≥80 字：那行截断加「…」", d)
    d = B.dep_body(uf, limit=100000)
    check(d["截断"] is False and len(d["行"]) == 30 and d["共"] == 30, "不超长：整段放，不注明截断", d)
    mb = B.module_brief(T.SOL, "vocab")
    u = mb["函数"][0]["依赖"]["调用"][0]
    check(u["函数"] == "graph.取知识点" and u["伪代码"] == {"行": ["按 code 查 graph_point 表的一行，原样返回（查不到就返回空）"], "共": 1, "截断": False}
          and u["位置"] == "contracts/graph.md:15", "deps_of 附上游伪代码节选和全文位置", u)
    md = B.module_md(mb)
    check("### 被调函数的伪代码（上游语义，只读；以对方约定为准）" in md and "#### graph.取知识点 的伪代码（contracts/graph.md:15）" in md,
          "module_md 加「被调函数的伪代码」一节（K171 实验 A：实现模型缺上游语义）", md[:200])
    check("被调函数的伪代码" not in B.module_md(mb, full=False), "full=False（要点口径）不附伪代码")
    mb2 = {"函数": [{"依赖": {"调用": [dict(u), dict(u)]}}, {"依赖": {"调用": [dict(u)]}}]}
    check(B.deps_md(mb2).count("#### graph.取知识点 的伪代码") == 1, "同一上游函数被多个函数调用：模块里只附一次", B.deps_md(mb2))
    k = ROOT / "kg_v4"
    mdk = B.module_md(B.module_brief(k, "teacher_assist"))
    check(re.search(r"#### assist_draft\.生成草稿 的伪代码（共 \d+ 行，超长截断了；全文见 contracts/assist_draft\.md:\d+）", mdk),
          "kg_v4 实测：生成草稿超 1500 字，截断并注明全文位置", [l for l in mdk.split("\n") if "生成草稿 的伪代码" in l])
    check(mdk.count("#### assist_draft.列草稿 的伪代码") == 1, "列草稿 被 问助手 / 列对话页面 都调用：只附一次", mdk.count("#### assist_draft.列草稿 的伪代码"))


def test_load_declare():
    print("②设计声明 load_declare（brief b）")
    f = T.fresh("k174_decl") / "d.tsv"
    f.write_text("\n".join([
        "# 注释行",
        "",
        "lit:一次函数 → graph.取知识点  说明文字",
        "enum:N5..N1\tgraph.取等级\t备注",
        "改动\tfn:subject.科目等级\tenum:N5..N1\tlevels\tK168 依据",
        "值域\tkind\tgeneral,exam",
        "re:([坏正则)\tvocab.记作答",
        "旧值没来源",
        "旧值 → 不是函数来源",
        "值域\t只两列",
    ]) + "\n", encoding="utf-8")
    d = B.load_declare(f)
    check([(x["旧值"], x["新来源"]) for x in d["写死"]] ==
          [("lit:一次函数", "graph.取知识点"), ("enum:N5..N1", "graph.取等级"), ("enum:N5..N1", "subject.科目等级")],
          "箭头 / Tab / K168 5 列（fn: 前缀去掉）三种写法都认", d["写死"])
    check(d["值域"] == {"kind": "general,exam"}, "值域行 → {字段: 来源}", d["值域"])
    check(len(d["问题"]) == 4 and any("正则写错了" in x for x in d["问题"]) and any("看不懂" in x for x in d["问题"])
          and any("模块.函数" in x for x in d["问题"]) and any("值域写法" in x for x in d["问题"]),
          "正则写错 / 看不懂 / 新来源不是 模块.函数 / 值域少列 都进「问题」", d["问题"])


def test_scan_hardcodes():
    print("③写死盘点 scan_hardcodes（brief b）")
    p = T.full_project()
    vf = p / "contracts" / "vocab.md"
    vf.write_text(vf.read_text(encoding="utf-8").replace(
        '  伪代码 返回 {"ok": 1,', '  伪代码 等级写死为 N5、N4、N3，后面还有 N2、N1\n  伪代码 返回 {"ok": 1,', 1), encoding="utf-8")
    gf = p / "contracts" / "graph.md"
    gf.write_text(gf.read_text(encoding="utf-8").replace(
        "  伪代码 否则往 graph_edge 表插入一行",
        "  伪代码 提示语：你是想让我出题的老师吗（这是问句，不是人设）\n"
        "  伪代码 人设：你是严谨的日语老师，按知识点出题\n"
        "  伪代码 否则往 graph_edge 表插入一行", 1), encoding="utf-8")
    sf = p / "services" / "vocab.zs"
    sf.write_text(sf.read_text(encoding="utf-8") + "\n# 旧的等级顺序 N5..N1 写死在这里\n", encoding="utf-8")
    (p / "ui").mkdir(exist_ok=True)
    (p / "ui" / "vocab.ui").write_text("页面 词表\n  文本 等级范围 N5 到 N1\n  文本 你是想让我出题的老师吗？\n", encoding="utf-8")
    df = T.fresh("k174_hd") / "d.tsv"
    df.write_text("enum:N5..N1 → graph.取等级\npersona:老师 → subject.默认人设\n", encoding="utf-8")
    decl = B.load_declare(df)
    res = B.scan_hardcodes(p, decl, B.load_contracts(p)[1])
    e = next((x for x in res if x["旧值"] == "enum:N5..N1"), None)
    check(e is not None and {s["文件"] for s in e["位置"]} == {"contracts/vocab.md", "services/vocab.zs", "ui/vocab.ui"},
          "写死的枚举在约定（伪代码）、services（注释行）、ui 三处都找到", e)
    check(e and {(s["文件"], s["注释"]) for s in e["位置"]} == {("contracts/vocab.md", False), ("services/vocab.zs", True), ("ui/vocab.ui", False)},
          "注释行标「注释」", e and [(s["文件"], s["注释"]) for s in e["位置"]])
    pe = next((x for x in res if x["旧值"] == "persona:老师"), None)
    check(pe is not None and [s["文件"] for s in pe["位置"]] == ["contracts/graph.md"]
          and "你是严谨的日语老师" in pe["位置"][0]["原文"],
          "人设：只报真的人设句；「你是想让我出题的老师吗」问句不报（约定和 ui 里各一处都没算，K168 §5.2）", pe)
    L = B.hardcode_md(res)
    check(any("contracts/vocab.md:" in x for x in L) and any("（注释）" in x for x in L), "hardcode_md 列 文件:行，注释行标（注释）", L)
    check(all("ui/" not in x and "graph.md" not in x for x in B.hardcode_md(res, module="vocab")),
          "按模块过滤：vocab 只列自己的约定和 services，ui 和别的模块不列", B.hardcode_md(res, module="vocab"))
    check(B.hardcode_md([{"旧值": "lit:甲", "新来源": "graph.f", "位置": []}]) ==
          ["- 旧值 lit:甲 → 新来源 graph.f：没找到还写死旧值的地方"], "没有位置时的说法", B.hardcode_md([{"旧值": "lit:甲", "新来源": "graph.f", "位置": []}]))
    # 新来源函数自己的块、提到新来源函数名的行不算
    vf2 = p / "contracts" / "graph.md"
    vf2.write_text(vf2.read_text(encoding="utf-8").replace(
        "  伪代码 按 code 查 graph_point 表的一行",
        "  伪代码 按 code 查 graph_point 表的一行，等级取 N5..N1（改用 graph.取等级 之后就不写死了）\n"
        "  伪代码 另一处还是写死 N5..N1", 1), encoding="utf-8")
    res2 = B.scan_hardcodes(p, decl, B.load_contracts(p)[1])
    e2 = next((x for x in res2 if x["旧值"] == "enum:N5..N1"), None)
    check(e2 and sorted(s["行"] for s in e2["位置"] if s["文件"] == "contracts/graph.md") and
          all("取等级" not in s["原文"] for s in e2["位置"]),
          "提到新来源函数名（graph.取等级）的行不算；没提的写死行照报", e2 and [s for s in e2["位置"] if s["文件"] == "contracts/graph.md"])


def test_case_domain():
    print("④用例数据值域 case_domain_issues（brief c）")
    cs = {"m": {"模块": "m", "用例": [
        {"名": "正常", "先": [{"种类": "数据", "表": "subject_info", "值": {"id": 1, "levels": "入门,基础"}, "行": 1},
                              {"种类": "数据", "表": "quiz_question", "值": {"subject_id": 1, "level": "入门"}, "行": 2}], "调用": None},
        {"名": "冲突", "先": [{"种类": "数据", "表": "subject_info", "值": {"id": 1, "levels": "入门,基础"}, "行": 10}],
         "调用": {"目标": "出题", "参数": {"subject_id": 1, "level": "高等"}, "行": 11}},
        {"名": "没有科目行按默认", "先": [], "调用": {"目标": "出题", "参数": {"level": "N3"}, "行": 20}},
        {"名": "默认冲突", "先": [], "调用": {"目标": "出题", "参数": {"level": "初一"}, "行": 21}},
        {"名": "哨兵", "先": [], "调用": {"目标": "载入页面", "参数": {"level": "全部"}, "行": 22}},
        {"名": "等级非法400", "先": [], "调用": {"目标": "出题", "参数": {"level": "初三"}, "行": 23}},
        {"名": "JSON参数", "先": [{"种类": "数据", "表": "subject_info", "值": {"id": 2, "levels": "空"}, "行": 30}],
         "调用": {"目标": "追加题目", "参数": {"subject_id": 2, "rows_json": "[{\"level\": \"初一\"}, {\"level\": \"N2\"}]"}, "行": 31}}]}}
    iss = B.case_domain_issues(cs)
    check([x["用例"] for x in iss] == ["冲突", "默认冲突", "JSON参数"] and iss[0]["值域"] == ["入门", "基础"]
          and "没有 subject_info 行，按 N5..N1" in iss[1]["说明"] and iss[2]["科目"] == 2 and "rows_json" in iss[2]["说明"],
          "值不在该用例造的科目 levels 里、没造科目按 N5..N1、rows_json 里的 JSON 对象也查", iss)
    check(not any(x["用例"] in ("正常", "没有科目行按默认", "哨兵", "等级非法400") for x in iss),
          "值在值域里不报；「全部」哨兵不查；用例名点到「等级」的是故意测非法值，不查", iss)
    iss2 = B.case_domain_issues(cs, {"level": "入门,基础"})
    check(any(x["用例"] == "没有科目行按默认" for x in iss2) and iss2[0]["值域"] == ["入门", "基础"],
          "设计声明的 值域 行给字段定死值域（不再按科目）", [x for x in iss2 if x["用例"] == "没有科目行按默认"])
    L = B.domain_md(iss)
    check(len(L) == 3 and L[0].startswith("- contracts/m.md:11 用例 冲突："), "domain_md 一个用例一行（文件:行 + 用例名）", L)

    kp = k161_project()
    per = {}
    for x in B.case_domain_issues(B.load_contracts(kp)[0]):
        per.setdefault(x["模块"], set()).add(x["用例"])
    check(per.get("quiz") == QUIZ7, "K161 回放夹具：quiz 7/7 全报出（修数据前这些用例的数学科目 levels 为空、题目 level=初一）", per.get("quiz"))
    check(per.get("assist_draft") == AD6 | {"跨科目_校验草稿本科目条目"},
          "assist_draft 6/6 全报出（另有 校验草稿本科目条目 1 条：K161 没改它，等级不在值域当空不算错，已知额外命中）",
          per.get("assist_draft"))
    check(per.get("teacher_assist") == {"确认草稿页面_只读老师403"}, "teacher_assist 1 条同口径额外命中", per.get("teacher_assist"))
    fp = snapshot("f6ede27")
    if need(fp, "f6ede27"):
        iss3 = [x for x in B.case_domain_issues(B.load_contracts(fp)[0]) if x["模块"] in ("quiz", "assist_draft")]
        check({x["用例"] for x in iss3} == {"跨科目_校验草稿本科目条目"} and not any(x["模块"] == "quiz" for x in iss3),
              "f6ede27 原样（levels=初一,初二 已修）：quiz 0 条、assist_draft 只剩已知额外命中那条", iss3)
    hp = snapshot("HEAD")
    if need(hp, "HEAD"):
        iss4 = B.case_domain_issues(B.load_contracts(hp)[0])
        check(len(iss4) == 2 and {(x["模块"], x["用例"]) for x in iss4} ==
              {("assist_draft", "跨科目_校验草稿本科目条目"), ("teacher_assist", "确认草稿页面_只读老师403")},
              "当前 HEAD 误报 2 条（目标 ≤2）：都是跨科目造数 payload 里 level=初一 的位置", iss4)


def test_exemptions():
    print("⑤豁免（G1）")
    p = T.full_project()
    (p / "plan").mkdir(exist_ok=True)
    (p / "plan" / "top.zs").write_text(T.TOP3, encoding="utf-8")
    top = VT.load((p / "plan" / "top.zs").read_text(encoding="utf-8"))
    base = T.contract_text("graph")

    def probs(text):
        return VC.check(text, "graph", top, p)

    v = base.replace("表 graph_point\n", "表 wrong_point\n", 1)
    ps = probs(v)
    check(len(ps) == 1 and "要以「graph_」开头" in ps[0] and "豁免" not in ps[0], "表名前缀违约报 1 条，问题文字不提示豁免写法", ps)
    v2 = v.replace("表 wrong_point\n", "# 约定检查豁免 表名前缀：表在别处建好，沿用旧名\n表 wrong_point\n", 1)
    check(probs(v2) == [], "豁免写对：不再报", probs(v2))
    v3 = v.replace("表 graph_edge\n", "# 约定检查豁免 表名前缀：放错地方的豁免\n表 graph_edge\n", 1)
    ps = probs(v3)
    check(len(ps) == 2 and any("没有对上" in x for x in ps), "豁免放在不违约的行上：原违约照报 + 豁免没对上违约也报", ps)
    v4 = v.replace("表 wrong_point\n", "# 约定检查豁免 表名后缀：理由写错规则名\n表 wrong_point\n", 1)
    ps = probs(v4)
    check(any("只认 表名前缀 / 可选传空" in x for x in ps) and len(ps) == 2, "规则名不认：报出，原违约也还在", ps)
    v5 = v.replace("表 wrong_point\n", "# 约定检查豁免 表名前缀\n表 wrong_point\n", 1)
    check(any("要写理由" in x for x in probs(v5)), "没写理由：报出", probs(v5))
    v6 = v.replace("表 wrong_point\n", "# 约定检查豁免 可选传空：规则和违约对不上\n表 wrong_point\n", 1)
    ps = probs(v6)
    check(any("要写明豁免哪个入参" in x for x in ps), "可选传空没点名入参：报出", ps)
    w = (base.replace("公开 函数 取知识点 code\n", "公开 函数 取知识点 code note?\n", 1)
              .replace("  调用 取知识点 code=P1\n", "  调用 取知识点 code=P1 note=空\n", 1))
    ps = probs(w)
    check(len(ps) == 1 and "note 传了「空」" in ps[0] and "豁免" not in ps[0], "可选入参传空报 1 条，不提示豁免写法", ps)
    w2 = w.replace("  调用 取知识点 code=P1 note=空\n", "# 约定检查豁免 可选传空 note：传空和不传一样\n  调用 取知识点 code=P1 note=空\n", 1)
    check(probs(w2) == [], "可选传空豁免点名入参：不再报", probs(w2))
    w3 = w.replace("  调用 取知识点 code=P1 note=空\n", "# 约定检查豁免 可选传空 note2：点错了\n  调用 取知识点 code=P1 note=空\n", 1)
    ps = probs(w3)
    check(len(ps) == 2 and any("没有对上" in x for x in ps), "点错入参：原违约照报 + 豁免没对上", ps)
    w4 = base.replace("  调用 取知识点 code=P1\n", "# 约定检查豁免 可选传空 note：过期\n  调用 取知识点 code=P1\n", 1)
    check(any("没有对上" in x for x in probs(w4)), "违约已没了、豁免还留着：报出（免得过期）", probs(w4))

    kp = ROOT / "kg_v4"
    top2 = VT.load((kp / "plan" / "top.zs").read_text(encoding="utf-8"))
    n = sum(len(VC.check((kp / "contracts" / f"{m['名']}.md").read_text(encoding="utf-8"), m["名"], top2, kp))
            for m in top2["模块"] if (kp / "contracts" / f"{m['名']}.md").is_file())
    check(n == 0, "kg_v4 全项目 contracts.check 0 条（12 条违约全部豁免）", n)
    src = (kp / "contracts" / "subject.md").read_text(encoding="utf-8")
    check(src.count("# 约定检查豁免 可选传空") == 8, "subject 8 条可选传空豁免（current_role×5、name、subj_persona×2）", src.count("# 约定检查豁免 可选传空"))


def _proj(bad=True, exempt=False):
    p = T.full_project()
    (p / "plan").mkdir(exist_ok=True)
    (p / "plan" / "top.zs").write_text(T.TOP3, encoding="utf-8")
    if bad:
        f = p / "contracts" / "graph.md"
        f.write_text(f.read_text(encoding="utf-8").replace(
            "表 graph_point\n",
            ("# 约定检查豁免 表名前缀：表在别处建好，沿用旧名\n" if exempt else "") + "表 wrong_point\n", 1), encoding="utf-8")
    return p


def _run_gate(p, **extra):
    fk = T.Fake(scripts={f"dsl0{k}": [T.a2_reply("ok")] for k in range(1, 5)})
    res = core.run_entry("audit2", p, T.fresh("k174_g"), "需求", extra_vars={"llm": "sonnet", **extra}, backend=fk)
    ajf = p / "plan" / "audit2.json"
    return res, res.get("returned") or {}, fk, (json.loads(ajf.read_text(encoding="utf-8")) if ajf.is_file() else None)


def test_gate():
    print("⑥约定闸（G1：audit2 开头跑 v3/contracts.check）")
    res, ret, fk, aj = _run_gate(_proj())
    check(res["status"] == "成功" and ret.get("result") == "contract_issue" and ret.get("contract_check") == "拦截",
          "默认拦截：范围内有违约 → 立刻 contract_issue（contract_check=拦截）", (res["status"], ret))
    check(fk.calls == [], "不跑回归、不派核查员：0 次模型调用", [c["tag"] for c in fk.calls])
    check(len(ret.get("issues") or []) == 1 and ret["issues"][0]["module"] == "graph"
          and ret["issues"][0]["basis"] == "约定检查 contracts/graph.md",
          "issues 来自 v3/contracts.check（module / basis 口径）", ret.get("issues"))
    check(aj == ret, "plan/audit2.json 同步落盘", aj)

    res, ret, fk, aj = _run_gate(_proj(), contract_check="提醒")
    check(fk.n("dsl") == 3 and ret.get("result") != "contract_issue" and aj and any(i["module"] == "graph" for i in aj.get("contract_warnings", [])),
          "提醒：照常审完（3 个核查员都派了），违约进 contract_warnings、不改 result", (ret.get("result"), aj))
    check("contract_check" not in aj, "提醒模式 audit2.json 不写 contract_check 键", aj)

    res, ret, fk, aj = _run_gate(_proj(), contract_check="关")
    check(fk.n("dsl") == 3 and "contract_warnings" not in (aj or {}) and ret.get("result") == "module_issue"
          and "wrong_point" in ret["issues"][0]["issue"],
          "关：不查约定（同 K174 之前）；违约项目照常审，只报回归自己的 module_issue（表名比对）", (ret.get("result"), aj))

    res, ret, fk, aj = _run_gate(_proj(), scope="|vocab|progress|", modules="vocab,progress")
    check(fk.n("dsl") == 2 and ret.get("result") != "contract_issue"
          and any(k.get("kind") == "contract_check" and k.get("module") == "graph" for k in (aj or {}).get("skipped_issues", [])),
          "给了范围：范围外模块（graph）的违约不拦，记进 skipped_issues（kind=contract_check）", (ret.get("result"), (aj or {}).get("skipped_issues")))

    res, ret, fk, aj = _run_gate(_proj(exempt=True))
    check(fk.n("dsl") == 3 and "contract_warnings" not in (aj or {})
          and not any(k.get("kind") == "contract_check" for k in (aj or {}).get("skipped_issues", [])),
          "豁免对上：闸放行，照常审完", (aj, [c["tag"] for c in fk.calls]))

    res, ret, fk, aj = _run_gate(_proj(bad=False))
    check(fk.n("dsl") == 3 and ret.get("result") == "ok", "干净项目不受影响（默认拦截也照常审完）", (ret, [c["tag"] for c in fk.calls]))

    mp = snapshot("m4-rest")
    if need(mp, "m4-rest"):
        top = VT.load((mp / "plan" / "top.zs").read_text(encoding="utf-8"))
        items = VC.check_project(mp, top)
        check(len(items) == 11 and all(i["basis"].startswith("约定检查") for i in items),
              "m4-rest 快照（K148 时期）check_project 11 条（subject 6、dictation 1、assist_draft 1、assist_file 1、assist_material 2）", len(items))
        check(any("改材料_标题为空" in i["issue"] and i["modules"] == "assist_material" for i in items),
              "含 assist_material 改材料_标题为空（K148 停下的那条）", [i["issue"][:60] for i in items if i["modules"] == "assist_material"])
        fk = T.Fake()
        res = core.run_entry("audit2", mp, T.fresh("k174_m4"), "需求", extra_vars={"llm": "sonnet"}, backend=fk)
        ret, aj = res.get("returned") or {}, json.loads((mp / "plan" / "audit2.json").read_text(encoding="utf-8"))
        check(ret.get("result") == "contract_issue" and aj.get("contract_check") == "拦截" and len(aj.get("issues") or []) == 11 and fk.calls == [],
              "m4-rest 在 audit2 开头被拦下（假模型，0 次调用）", (ret.get("result"), len(aj.get("issues") or []), len(fk.calls)))


def test_cli():
    print("⑦CLI")
    py = [sys.executable, "-m", "tools.dslagent", "v3"]
    rq = T.fresh("k174_req") / "r.md"
    rq.write_text("需求", encoding="utf-8")
    base = ["--req", str(rq), "--out", str(T.fresh("k174_o")), "--project", str(T.fresh("k174_p"))]
    cp = subprocess.run(py + ["change2"] + base + ["--contract-check", "拦截"], cwd=ROOT, capture_output=True, text=True)
    check(cp.returncode == 2 and "--contract-check" in cp.stderr, "--contract-check 只对 audit2 / fix2 有效：change2 退出码 2", cp.stderr[-200:])
    d = T.fresh("k174_d") / "d.tsv"
    d.write_text("lit:一次函数 → graph.取知识点\n值域\tcorrect\t0,1\n", encoding="utf-8")
    cp = subprocess.run(py + ["fix2"] + base + ["--declare", str(d)], cwd=ROOT, capture_output=True, text=True)
    check(cp.returncode == 2 and "--declare" in cp.stderr, "fix2 --declare 不带 --brief：退出码 2", cp.stderr[-200:])
    cp = subprocess.run(py + ["brief", "--project", str(T.SOL), "--declare", "/nope.tsv"], cwd=ROOT, capture_output=True, text=True)
    check(cp.returncode == 2 and "不存在" in cp.stderr, "brief --declare 文件不存在：退出码 2", cp.stderr[-200:])
    o = T.fresh("k174_bo")
    cp = subprocess.run(py + ["brief", "--project", str(T.SOL), "--declare", str(d), "--out", str(o)], cwd=ROOT, capture_output=True, text=True)
    md = (o / "brief.md").read_text(encoding="utf-8") if (o / "brief.md").is_file() else ""
    check(cp.returncode == 0 and "## 写死盘点" in md and "- 旧值 lit:一次函数 → 新来源 graph.取知识点" in md
          and "## 用例数据值域检查" in md, "brief --declare：写死盘点 / 值域检查两节进 brief.md", md[:300])
    d2 = T.fresh("k174_d2") / "bad.tsv"
    d2.write_text("re:([坏)\ta.b\n", encoding="utf-8")
    cp = subprocess.run(py + ["brief", "--project", str(T.SOL), "--declare", str(d2), "--out", str(T.fresh("k174_bo2"))],
                        cwd=ROOT, capture_output=True, text=True)
    check(cp.returncode == 0 and "[设计声明]" in cp.stderr and "正则写错了" in cp.stderr,
          "声明里的问题行打到 stderr（exit 0，只是提醒）", cp.stderr[-200:])


if __name__ == "__main__":
    os.environ.pop(B.ENV_FILE, None)
    test_dep_body()
    test_load_declare()
    test_scan_hardcodes()
    test_case_domain()
    test_exemptions()
    test_gate()
    test_cli()
    print(f"\n通过 {PASS}，失败 {FAIL}")
    sys.exit(1 if FAIL else 0)
