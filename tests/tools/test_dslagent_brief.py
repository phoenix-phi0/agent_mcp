# -*- coding: utf-8 -*-
"""K171：v3 实现简报（tools/dslagent/v3/brief.py）+ change2 / fix2 的 --impl-model / --brief 接入。

覆盖（全离线：历史快照用 git archive 从本仓库取，假模型 / 桩子进程，不调真模型）：
  ① K164 快照（669fc4a + K164 第一次 fix2 用的 subject.md，见 kg_K169 §1）：subject.科目助手设定 出 R1（assist_prompt 要 COALESCE）；
     669fc4a 原样（约定已写 COALESCE）不出
  ② K166 改前 513e0f0：teacher_assist.班级上下文 出 R2，点名第 128 行 t={row}；K166 修好后 f4d417c 不再出
  ③ R6：f6ede27 把「科目管理页面」返回里的 subj_levels 去掉（K161 实测发现的契约漏项）→ 点名缺 subj_levels；原样不报缺
  ④ K161 影响面（9a45f19 → f6ede27）：建议模块覆盖真值 7/7，assist_material / teacher_assist 列为参考；git HEAD vs 工作区的取法
  ⑤ 规则收窄：写入 / 入参 / 只判断有没有这一行 不出 R1；_no 一类参数不出 R2；不再有契约层 R2；调用 lint；约定检查结果
  ⑥ 接入：派代理 modify_module 用 --impl-model 的模型、--brief 写简报文件并经环境变量交给子进程；audit2 核查员不带简报；
     packs/dslproj materials() / fix_input() 只在环境变量指向本模块时加这一节
  ⑦ 默认行为不变：不加 --impl-model / --brief 时 fix2 的调用、模型、任务文本、记录目录与改前一致（没有 brief 目录 / 日志行 / 环境变量）
  ⑧ CLI：v3 brief、参数校验、-h

    cd /workspace/agent_mcp && .venv/bin/python tests/tools/test_dslagent_brief.py
"""
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

import test_dslagent_v3 as T                                       # noqa: E402  复用 v3 测试的假模型 / 参考项目
from tools.dslagent import roles as R                              # noqa: E402
from tools.dslagent.packs import dslproj as DP                     # noqa: E402
from tools.dslagent.v3 import brief as B, contracts as VC, core, scaffold as SF, top as VT   # noqa: E402

PASS = FAIL = 0
SNAP = {}

# K164 第一次 fix2（fix2_a）用的 subject.md 和 669fc4a 的差别（kg_K169 §1）：第 117、129 行没有 COALESCE 的说明，也没有最后那条用例
K164_117 = ("  伪代码 subject_id 为空或不是纯数字时按 1 处理；按 subject_id 查 subject_info 取 name（查询 subject_info_full），"
            "查 subject_ai 该科目行的 persona（新查询 subject_ai_persona）")
K164_129 = ("  伪代码 subject_id 为空或不是纯数字时按 1 处理；按 subject_id 查 subject_info 取 name、kind（查询 subject_info_full），"
            "查 subject_ai 该科目行的 assist_prompt（新查询 subject_ai_assist_prompt）；调用 科目等级 subject_id=subject_id 取 levels 列表")
K161_TRUTH = {"assist_draft", "lesson", "progress", "quiz", "subject", "textbook_import", "tutor"}


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
    d = T.fresh(f"k171_{rev}_")
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


def contracts_of(p):
    return {f.stem: f.read_text(encoding="utf-8") for f in sorted((p / "contracts").glob("*.md"))}


def hints(p, module, fn):
    mb = B.module_brief(p, module, [fn])
    return mb["函数"][0]["要点"] if mb["函数"] else None


def need(p, rev):
    check(p is not None, f"取到历史快照 {rev}（git archive）")
    return p is not None


def test_k164_r1():
    print("①K164 快照：科目助手设定 出 R1（COALESCE）")
    p = copy_snapshot("669fc4a", "k171_k164")
    if not need(p, "669fc4a"):
        return
    h = hints(p, "subject", "科目助手设定")
    check(not any(x["rule"] == "R1" for x in h), "669fc4a 原样：约定已写 COALESCE，不出 R1", h)
    f = p / "contracts" / "subject.md"
    lines = f.read_text(encoding="utf-8").split("\n")
    check("COALESCE" in lines[116] and "COALESCE" in lines[128], "669fc4a subject.md 第 117、129 行是 COALESCE 的说明", (lines[116][:80], lines[128][:80]))
    lines[116], lines[128] = K164_117, K164_129
    f.write_text("\n".join(lines), encoding="utf-8")
    h = hints(p, "subject", "科目助手设定")
    r1 = [x for x in h if x["rule"] == "R1"]
    check(len(r1) == 1 and "subject_ai.assist_prompt" in r1[0]["note"] and "COALESCE" in r1[0]["note"] and "None" in r1[0]["note"],
          "K164 快照：科目助手设定 出 R1，点名 subject_ai.assist_prompt、写 COALESCE、说明 NULL 会变成文本 None", h)
    check("约定" in r1[0]["why"] if r1 else False, "依据来自约定（这时候还没有代码）", r1)
    h2 = hints(p, "subject", "科目老师设定")
    check(any(x["rule"] == "R1" and "subject_ai.persona" in x["note"] for x in h2), "顺带：科目老师设定 也出 R1（persona，K164 审查后补的那条）", h2)
    sec = B.section_for(p, "subject", "该模块的问题： 问题：科目助手设定 返回 custom 应为 ''，实际 'None'", base_texts=B.load_contracts(p)[1])
    check("### 函数 科目助手设定" in sec and "【R1】" in sec and "### 函数 科目访问" not in sec,
          "section_for：只列任务点名的函数（科目助手设定），带骨架和 R1", sec[:600])
    task = ("该模块的问题： 问题：模块 subject 全量回归不过：比对约定：缺函数「科目助手设定」\n用例 科目助手设定_没有科目行按日语：DSLError: "
            "第 1 行：业务模块「subject」里没有函数「科目助手设定」（有：科目访问、列我的科目、当前科目、科目老师设定、科目管理页面）")
    c = B.load_contracts(p)[0]["subject"]
    check(B.functions_in_task(task, c) == ["科目助手设定"], "报错原文里的「（有：…）」函数清单不算点名（K171 实验 B 踩到的）",
          B.functions_in_task(task, c))
    t2 = "问题：「科目助手设定」没有按本科目等级取 levels；依据：contracts/subject.md"
    check(B.functions_in_task(t2, c) == ["科目助手设定"], "函数名嵌在句子里（「本科目等级」里的科目等级）不算点名", B.functions_in_task(t2, c))
    check(B.functions_in_task("问题：科目助手设定没有实现", c) == ["科目助手设定"], "前后紧贴汉字、严格匹配不到时退回子串")
    cut = task[:-12] + "；依据：全量回归。 只改与这些问题有关的地方"
    check(B.functions_in_task(cut, c) == ["科目助手设定"], "清单被截断、没有右括号时也去掉（截到分号）", B.functions_in_task(cut, c))
    # 从空实现修：services 换成骨架（每个函数都是「报错 未实现」），任务没点名、契约没改 → 全部函数都算本轮要改的
    c = B.load_contracts(p)[0]["dictation"]
    (p / "services" / "dictation.zs").write_text(SF.service_text("dictation", c), encoding="utf-8")
    sec = B.section_for(p, "dictation", "该模块的问题： 问题：全部函数未实现", base_texts=B.load_contracts(p)[1])
    check(B.unimplemented(p, "dictation", c) == [f["名"] for f in c["函数"]] and sec.count("### 函数 ") == len(c["函数"]),
          "services 是骨架：每个「报错 未实现」的函数都列进简报（带骨架）", (len(c["函数"]), sec.count("### 函数 ")))
    check(B.unimplemented(snapshot("669fc4a"), "dictation", c) == [], "有实现的模块：没有「未实现」的函数")


def test_k166_r2():
    print("②K166 改前 513e0f0：班级上下文 出 R2（第 128 行 t={row}）")
    p = snapshot("513e0f0")
    if not need(p, "513e0f0"):
        return
    h = hints(p, "teacher_assist", "班级上下文")
    r2 = [x for x in h if x["rule"] == "R2"]
    check(len(r2) == 1 and "t={row}" in r2[0]["note"] and "第 128 行" in r2[0]["note"] and "teacher_assist_len" in r2[0]["note"],
          "R2 点名 t={row}→teacher_assist_len（第 128 行）", h)
    check(r2 and "t={head}" in r2[0]["note"] and "t={tail}" in r2[0]["note"], "同一函数的 t={head}、t={tail} 也列出", r2)
    check(r2 and "拼接文本" in r2[0]["why"], "来源：拼接文本", r2)
    p2 = snapshot("f4d417c")
    if need(p2, "f4d417c"):
        h = hints(p2, "teacher_assist", "班级上下文")
        check(not any(x["rule"] == "R2" for x in h), "K166 修好后（f4d417c，已改对象传参）：不再出 R2", h)


def test_r6_subj_levels():
    print("③R6：科目表格行缺 subj_levels")
    p = copy_snapshot("f6ede27", "k171_r6")
    if not need(p, "f6ede27"):
        return
    h = hints(p, "subject", "科目管理页面")
    r6 = [x for x in h if x["rule"] == "R6"]
    missing = r6[0]["note"].split("没列出：", 1)[1] if r6 and "没列出：" in r6[0]["note"] else ""
    check(len(r6) == 1 and "subj_levels" in r6[0]["note"] and "subj_levels" not in missing,
          "原样（返回里已有 subj_levels）：R6 列出浮层字段，不报缺 subj_levels", r6)
    check(missing == "subj_intro", "f6ede27 时返回还缺 subj_intro（K163 才补的那条，kg_K165 已记）：照实报出", missing)
    f = p / "contracts" / "subject.md"
    t = f.read_text(encoding="utf-8")
    row = "subjects 是表格行 [{subj_id, subj_code, subj_name, subj_kind, subj_levels, subj_visibility"
    check(row in t, "f6ede27 科目管理页面 返回里有 subj_levels（去掉它模拟 K161 实测发现的漏项）")
    t = t.replace(row, row.replace("subj_levels, ", ""), 1)
    t = t.replace("（subj_levels 要在行里：从行上点「编辑」时前端直接拿这一行填表单、不再发「载入」，行里没有的字段编辑框就是空的）", "", 1)
    f.write_text(t, encoding="utf-8")
    h = hints(p, "subject", "科目管理页面")
    r6 = [x for x in h if x["rule"] == "R6"]
    check(len(r6) == 1 and "约定返回里没列出：subj_levels" in r6[0]["note"].replace("、subj_intro", "").replace("subj_intro、", ""),
          "去掉后：R6 点名 约定返回里没列出 subj_levels", r6)
    check(r6 and "ui/subject.ui" in r6[0]["why"] and "编辑科目" in r6[0]["why"], "依据：ui/subject.ui 的列表行动作打开「编辑科目」浮层", r6)


def test_k161_impact():
    print("④K161 影响面（9a45f19 → f6ede27）")
    a, b = snapshot("9a45f19"), snapshot("f6ede27")
    if not (need(a, "9a45f19") and need(b, "f6ede27")):
        return
    imp = B.impact(contracts_of(a), contracts_of(b))
    sug = set(imp["建议模块"])
    check(K161_TRUTH <= sug, f"建议模块覆盖真值 {len(K161_TRUTH & sug)}/7", imp["建议模块"])
    check(len(sug) == 8 and sug - K161_TRUTH == {"report"}, "只多 report（它自己的契约改了措辞，K168 同口径 7/8）", imp["建议模块"])
    check(set(imp["参考模块"]) == {"assist_material", "teacher_assist"}, "assist_material、teacher_assist 列为参考（调的函数只改了伪代码）", imp["参考模块"])
    check(imp["可能漏改契约"] == [], "直接调用方的契约都改了：没有「可能漏改契约」", imp["可能漏改契约"])
    sc = {x["函数"]: x["签名"] for x in imp["改动函数"]}
    check(sc.get("subject.科目等级") == "new" and sc.get("report.取点等级") == "unknown", "签名口径：科目等级 new、取点等级 unknown（同 K168）",
          {k: sc.get(k) for k in ("subject.科目等级", "report.取点等级")})
    md = B.impact_md(imp)
    check("建议 --modules assist_draft,lesson,progress,quiz,report,subject,textbook_import,tutor" in md, "impact_md 给出建议的 --modules 串", md[:400])

    # git HEAD vs 工作区：临时仓库里提交 9a45f19 的契约，再把工作区换成 f6ede27 的
    import shutil
    g = T.fresh("k171_git")
    proj = g / "kg_v4"
    shutil.copytree(a / "contracts", proj / "contracts")
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    for cmd in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "base"]):
        subprocess.run(["git", "-C", str(g)] + cmd, check=True, env=env, capture_output=True)
    base = B.git_base_texts(proj)
    check(base is not None and set(base) == set(contracts_of(a)), "git_base_texts：取到 HEAD 的全部契约", sorted(base or {})[:5])
    shutil.rmtree(proj / "contracts")
    shutil.copytree(b / "contracts", proj / "contracts")
    imp2 = B.impact(B.git_base_texts(proj), contracts_of(proj))
    check(imp2["建议模块"] == imp["建议模块"], "HEAD vs 工作区 得出同样的建议", imp2["建议模块"])
    # 「可能漏改契约」：把 progress 的契约退回 HEAD（它直接调用了签名变的 subject.科目等级 / lesson 的函数）
    (proj / "contracts" / "progress.md").write_text(base["progress"], encoding="utf-8")
    imp3 = B.impact(B.git_base_texts(proj), contracts_of(proj))
    callers_new = {m for m, why in imp3["理由"].items() if any("直接调用" in w for w in why)}
    check(set(imp3["可能漏改契约"]) == callers_new - {x["函数"].split(".")[0] for x in imp3["改动函数"]},
          "可能漏改契约 = 直接调用了签名变的函数、自己契约却没改的模块", (imp3["可能漏改契约"], sorted(callers_new)))
    nogit = T.fresh("k171_nogit")
    shutil.copytree(b / "contracts", nogit / "contracts")
    check(B.git_base_texts(nogit) is None and "没有影响面" in B.impact_md(None), "不在 git 仓库里：没有影响面，不报错")


def test_rules_narrowed():
    print("⑤规则收窄（K169 抽样的误报）、lint、约定检查")
    p = snapshot("f4d417c")
    if not need(p, "f4d417c"):
        return
    for mod, fn, why in (("kg", "建条目", "after_form/prev_code 是入参、写进库"), ("lesson", "导入课文", "intro/license/source 是入参"),
                         ("vocab", "删除单词", "读的行只用来判断有没有")):
        h = hints(p, mod, fn)
        check(not any(x["rule"] == "R1" for x in h), f"{mod}.{fn} 不出 R1（{why}）", h)
    for mod, fn, why in (("report", "取题干", "question_no 是题号"), ("account", "建学生", "契约层「密码长度」不再触发"),
                         ("assist_material", "改材料", "契约层「60 个字」不再触发")):
        h = hints(p, mod, fn)
        check(not any(x["rule"] == "R2" for x in h), f"{mod}.{fn} 不出 R2（{why}）", h)
    h = hints(p, "vocab", "新建单词")
    check(any(x["rule"] == "R2" and "kana={kana}" in x["note"] for x in h), "vocab.新建单词 仍出 R2（kana 按位置传，K169 抽样的真风险）", h)
    allh = [x for m in B.load_contracts(p)[0] for f in B.module_brief(p, m)["函数"] for x in f["要点"]]
    check({x["rule"] for x in allh} <= {"R1", "R2", "R6"}, "只出 R1 / R2 / R6", sorted({x["rule"] for x in allh}))
    check(len(allh) < 137, f"HEAD 上要点 {len(allh)} 条（K169 的 137 条去掉了契约层 R2、R3–R5 和写入 / 入参类 R1）", len(allh))

    cs = {"a": {"模块": "a", "函数": [{"名": "列我的科目", "公开": True, "入参": [], "返回": "", "报错": [], "伪代码": [], "行": 3}]},
          "b": {"模块": "b", "函数": [{"名": "汇总", "公开": True, "入参": [], "返回": "", "报错": [], "行": 5,
                                     "伪代码": [{"文字": "先按 列我的科目 取科目列表再汇总", "行": 6}, {"文字": "调用 a.列我的科目", "行": 7}]}]}}
    lint = B.lint_mentions(cs)
    check(lint == [{"模块": "b", "函数": "汇总", "行": 6, "提到": "列我的科目", "所在模块": ["a"]}],
          "lint：提到别模块公开函数名却没写「调用 a.列我的科目」（第 6 行），写了调用的第 7 行不报", lint)
    b = B.build(p, modules=["subject"], base_texts={})
    want = VC.check((p / "contracts" / "subject.md").read_text(encoding="utf-8"), "subject", VT.load((p / "plan" / "top.zs").read_text(encoding="utf-8")), p)
    check(b["约定检查"] == {"subject": want} and want, "约定检查：就是 v3/contracts.check 的结果（f4d417c subject 有 8 条「可选入参传空」）", len(want))
    check("约定检查 subject：" in B.to_md(b), "md 的只读检查里列出来（提醒，不拦截）")
    fn = next(x for x in b["模块"][0]["函数"] if x["名"] == "列我的科目")
    check(fn["骨架"]["接口"] and "调用 subject.列我的科目 learner={learner} current_role={current_role}" in fn["骨架"]["接口"][0]["路由"],
          "骨架：接口路由用 scaffold.route_text 渲染（和骨架 / 比对约定同一份）", fn["骨架"]["接口"])
    fn = next(x for x in b["模块"][0]["函数"] if x["名"] == "科目助手设定")
    deps = [u["函数"] for u in fn["依赖"]["调用"]]
    tabs = {t["表"]: t for t in fn["依赖"]["表"]}
    check("subject_ai" in tabs and any("assist_prompt（可空）" == c for c in tabs["subject_ai"]["列"]), "依赖：读 subject_ai，标出 assist_prompt 可空", tabs.get("subject_ai"))
    check(deps == [], "科目助手设定 没有跨模块调用（「调用 科目等级」是本模块）", deps)
    md = B.to_md(b)
    check(md.startswith("# 实现简报") and "## 模块 subject" in md and "## 只读检查" in md, "to_md：影响面 / 模块 / 只读检查 三段", md[:200])


def _proj3():
    p = T.full_project()
    (p / "plan").mkdir(exist_ok=True)
    (p / "plan" / "top.zs").write_text(T.TOP3, encoding="utf-8")
    return p


def _reply(result, issue="", basis=""):
    r = {"result": result}
    if issue:
        r.update(issue=issue, basis=basis)
    return json.dumps({"result": r, "status": "成功", "reason": ""}, ensure_ascii=False)


# 假模型的 tag 是全局递增编号：第 1 次核查 dsl01–03（graph 有问题），改完第 2 次核查 dsl04–06 全 ok
AUDIT_THEN_OK = {"dsl01": [_reply("module_issue", "graph 的 取知识点 少了 title", "services/graph.zs")],
                 **{f"dsl0{k}": [_reply("ok")] for k in range(2, 7)}}


def _ledger(out):
    f = Path(out) / "agents.jsonl"
    return [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines()] if f.is_file() else []


def _log(out):
    f = Path(out) / "v3_log.jsonl"
    return [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines()] if f.is_file() else []


def test_wiring():
    print("⑥接入：--impl-model / --brief 只作用于 modify_module")
    p = _proj3()
    out = T.fresh("k171_f2b")
    fk = T.Fake(scripts=dict(AUDIT_THEN_OK, v3_agent_modify_module=["改好了"]))
    res = core.run_entry("fix2", p, out, "需求", extra_vars={"llm": "sonnet", "rounds": 2}, backend=fk, module_cmd=T.CMD,
                         impl_model="haiku", brief=True)
    mm = [c for c in fk.calls if c["tag"] == "v3_agent_modify_module"]
    au = [c for c in fk.calls if c["tag"].startswith("dsl")]
    check(res["status"] == "成功" and len(mm) == 1 and mm[0]["model"] == "haiku", "modify_module 用 --impl-model 的 haiku", [(c["tag"], c["model"]) for c in fk.calls])
    check(au and all(c["model"] != "haiku" for c in au) and not any("实现简报" in c["user"] or "【R" in c["user"] for c in au),
          "audit2 核查员：模型不变、提示里没有简报", [c["model"] for c in au])
    led = [r for r in _ledger(out) if r.get("role") == "modify_module"]
    check(led and led[0].get("model") == "haiku", "账本 agents.jsonl 记 modify_module 的模型 haiku", led)
    bf = sorted((out / "brief").glob("graph_*.json"))
    d = json.loads(bf[0].read_text(encoding="utf-8")) if bf else {}
    check(len(bf) == 1 and d.get("模块") == "graph" and "### 函数 取知识点" in d.get("正文", ""), "--brief：out/brief/graph_1.json 写了 graph 的简报，只列任务点名的 取知识点",
          d.get("正文", "")[:300])
    check("### 函数 加边" not in d.get("正文", ""), "没点名的函数不列", d.get("正文", "")[:600])
    lg = _log(out)
    check(any(r["类"] == "实现简报" and r.get("状态") == "已附" for r in lg) and any(r["类"] == "实现设置" for r in lg),
          "v3_log.jsonl 记了 实现设置 / 实现简报", [r["类"] for r in lg])
    check(any(r["类"] == "简报影响面" for r in lg) and (out / "brief_impact.md").is_file() and (out / "brief_impact.json").is_file(),
          "--brief：开始前把影响面写进日志和记录目录（这个项目不在 git 里：写明没有影响面）", [r for r in lg if r["类"] == "简报影响面"])

    # 真起子进程：env / 模型交到 v2 子进程手里（桩子进程把看到的环境变量写下来）
    stub = T.fresh("k171_stub") / "stub.py"
    seen = stub.parent / "seen.json"
    stub.write_text("import json, os, sys\n"
                    f"open({str(seen)!r}, 'w').write(json.dumps({{k: os.environ.get(k) for k in ('DSLAGENT_MODELS', 'DSLAGENT_BRIEF_FILE')}}))\n"
                    "print(json.dumps({'fixed': False, 'calls': 1, 'cost': 0.0, 'stop': 'stub'}))\n", encoding="utf-8")
    bfile = stub.parent / "b.json"
    bfile.write_text(json.dumps({"模块": "graph", "正文": "### 函数 取知识点\n- 【R1】示例"}, ensure_ascii=False), encoding="utf-8")
    od = T.fresh("k171_disp")
    r = R.dispatch_agent("modify_module", "改", {"模块": "graph"}, out_dir=od, project=p, module_cmd=[sys.executable, str(stub)],
                         model="haiku", env={B.ENV_FILE: str(bfile)})
    s = json.loads(seen.read_text(encoding="utf-8"))
    check(r["model"] == "haiku" and json.loads(s["DSLAGENT_MODELS"]).get("plan") == "haiku" and s["DSLAGENT_BRIEF_FILE"] == str(bfile),
          "子进程：DSLAGENT_MODELS 各步骤 = haiku，DSLAGENT_BRIEF_FILE 指向简报", (r["model"], s))
    os.environ.pop(B.ENV_FILE, None)
    r = R.dispatch_agent("modify_module", "改", {"模块": "graph"}, out_dir=T.fresh("k171_disp"), project=p, module_cmd=[sys.executable, str(stub)])
    s = json.loads(seen.read_text(encoding="utf-8"))
    check(r["model"] == "sonnet" and json.loads(s["DSLAGENT_MODELS"]).get("plan") == "sonnet" and s["DSLAGENT_BRIEF_FILE"] is None,
          "不传 model / env：默认 sonnet、没有 DSLAGENT_BRIEF_FILE（同旧）", (r["model"], s))

    # packs/dslproj：materials() / fix_input() 只在环境变量指向本模块时加这一节
    task, ctx = "模块 graph\n改", {"task": "模块 graph\n改"}
    plain_m, plain_f = DP.materials(task, p, None)["text"], DP.fix_input(p, ctx, ["用例 x：不对"])
    check("实现简报" not in plain_m and "实现简报" not in plain_f, "没有环境变量：materials / fix_input 不带简报（同旧）")
    os.environ[B.ENV_FILE] = str(bfile)
    try:
        m1 = DP.materials(task, p, None)
        f1 = DP.fix_input(p, ctx, ["用例 x：不对"])
        check("## 本模块实现简报（自动推出，只是提醒）" in m1["text"] and "【R1】示例" in m1["text"] and m1["记录"].get("实现简报字数"),
              "materials：加「本模块实现简报（自动推出，只是提醒）」一节", m1["text"][:300])
        check(m1["text"].index("本模块实现简报") > m1["text"].index("## 本模块约定") and m1["text"].index("本模块实现简报") < m1["text"].index("## 上游模块"),
              "materials：这一节在「本模块约定」之后、上游函数之前")
        check("【本模块实现简报（自动推出，只是提醒）" in f1 and "【R1】示例" in f1, "fix_input：同样带这一节", f1[:300])
        check(m1["text"].replace(m1["text"][m1["text"].index("## 本模块实现简报"):m1["text"].index("## 上游模块")], "") == plain_m,
              "materials：除了这一节其余与不加时逐字相同")
        other = DP.materials("模块 vocab\n改", p, None)["text"]
        check("实现简报" not in other, "简报是 graph 的，做 vocab 时不带")
    finally:
        os.environ.pop(B.ENV_FILE, None)


def test_default_unchanged():
    print("⑦默认参数下 fix2 行为与改前一致（回归）")
    p = _proj3()
    out = T.fresh("k171_f2d")
    fk = T.Fake(scripts=dict(AUDIT_THEN_OK, v3_agent_modify_module=["改好了"]))
    res = core.run_entry("fix2", p, out, "需求", extra_vars={"llm": "sonnet", "rounds": 2}, backend=fk, module_cmd=T.CMD)
    tags = [c["tag"] for c in fk.calls]
    mm = [c for c in fk.calls if c["tag"] == "v3_agent_modify_module"]
    check(res["status"] == "成功" and tags == ["dsl01", "dsl02", "dsl03", "v3_agent_modify_module", "dsl04", "dsl05", "dsl06"],
          "调用顺序同旧：核查 3 个模块 → 改 graph → 再核查 3 个 → 成功", (res["status"], res["reason"][:200], tags))
    check(mm and mm[0]["model"] == "sonnet", "modify_module 用角色登记表的默认模型 sonnet", [c["model"] for c in mm])
    check(mm and mm[0]["user"] == "模块 graph\n该模块的问题： 问题：graph 的 取知识点 少了 title；依据：services/graph.zs。 只改与这些问题有关的地方，其他函数不动；约定不能改。\n",
          "派给 modify_module 的任务文本逐字同旧", mm[0]["user"] if mm else None)
    lg = _log(out)
    check(not (out / "brief").exists() and not (out / "brief_impact.md").exists() and not any(r["类"] in ("实现简报", "实现设置", "简报影响面") for r in lg),
          "没有 brief 目录、brief_impact、日志里没有简报行", [r["类"] for r in lg])
    led = [r for r in _ledger(out) if r.get("role") == "modify_module"]
    check(led and led[0].get("model") == "sonnet", "账本记 sonnet", led)
    check(B.ENV_FILE not in os.environ, "父进程环境里没有 DSLAGENT_BRIEF_FILE")


def test_cli():
    print("⑧CLI")
    p = snapshot("513e0f0")
    py = [sys.executable, "-m", "tools.dslagent", "v3"]
    cp = subprocess.run(py + ["-h"], cwd=ROOT, capture_output=True, text=True)
    check("--impl-model" in cp.stdout and "--brief" in cp.stdout and "brief" in cp.stdout, "v3 -h 列出 brief / --impl-model / --brief", cp.stdout[-400:])
    if p is not None:
        o = T.fresh("k171_cli")
        cp = subprocess.run(py + ["brief", "--project", str(p), "--modules", "teacher_assist", "--out", str(o)], cwd=ROOT, capture_output=True, text=True)
        last = json.loads(cp.stdout.strip().splitlines()[-1]) if cp.returncode == 0 else {}
        bj = json.loads((o / "brief.json").read_text(encoding="utf-8")) if (o / "brief.json").is_file() else {}
        check(cp.returncode == 0 and last.get("模块") == ["teacher_assist"] and (o / "brief.md").is_file()
              and "t={row}" in (o / "brief.md").read_text(encoding="utf-8") and bj.get("模块"), "v3 brief --modules --out：写 brief.json / brief.md", cp.stderr[-400:])
        cp = subprocess.run(py + ["brief", "--project", str(p), "--modules", "teacher_assist"], cwd=ROOT, capture_output=True, text=True)
        check(cp.returncode == 0 and cp.stdout.startswith("# 实现简报"), "不给 --out：打印 md，最后一行 JSON", cp.stdout[:100])
    rq = T.fresh("k171_req") / "r.md"
    rq.write_text("需求", encoding="utf-8")
    base = py + ["--req", str(rq), "--out", str(T.fresh("k171_o")), "--project", str(T.fresh("k171_p"))]
    cp = subprocess.run(base[:4] + ["audit2"] + base[4:] + ["--brief"], cwd=ROOT, capture_output=True, text=True)
    check(cp.returncode == 2 and "--brief" in cp.stderr, "audit2 加 --brief：退出码 2（只对 change2 / fix2 有效）", cp.stderr[-200:])
    cp = subprocess.run(base[:4] + ["fix2"] + base[4:] + ["--impl-model", "nope-model"], cwd=ROOT, capture_output=True, text=True)
    check(cp.returncode == 2 and "--impl-model" in cp.stderr, "--impl-model 模型串不认识：退出码 2", cp.stderr[-200:])
    cp = subprocess.run(py + ["fix2", "--project", str(T.fresh("k171_p"))], cwd=ROOT, capture_output=True, text=True)
    check(cp.returncode == 2 and "--req" in cp.stderr, "fix2 缺 --req / --out：退出码 2（同旧）", cp.stderr[-200:])


if __name__ == "__main__":
    os.environ.pop(B.ENV_FILE, None)
    test_k164_r1()
    test_k166_r2()
    test_r6_subj_levels()
    test_k161_impact()
    test_rules_narrowed()
    test_wiring()
    test_default_unchanged()
    test_cli()
    print(f"\n通过 {PASS}，失败 {FAIL}")
    sys.exit(1 if FAIL else 0)
