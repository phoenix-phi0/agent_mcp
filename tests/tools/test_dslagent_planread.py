# -*- coding: utf-8 -*-
"""dslagent v2 规划（任务原文 + 文件大纲 + 只读 dsl 工具按需读代码；老的 full 方式已删除）：不调真模型。

    cd /home/ysc/mcp && .venv/bin/python tests/tools/test_dslagent_planread.py

  一、read 的输入：user 只有 任务原文 + 文件大纲（没有代码片段 / 引用行 / 登记处 / 测试断言 / 补查结果）；system = 原 system 去掉讲资料包各节的那句 + 末尾一小段；
     不调补查（preq）、不调 pack.collect / pack.extra；包没实现 plan_outline 时 user 只有任务原文
  二、read 的规划调用：挂只读 dslmcp（--readonly、workdir=待改项目）、--max-turns 12、只许 mcp__dsl__dsl；
     计划检查不过的重写也走 read；保险（空闲超时 / 输出工具调用格式）失败重试 1 次，仍失败判失败
  三、只读工具（真起 MCP）：读片段 / 搜索代码 / 查引用 / 设 / 打印可用；改文件 / 写文件 / #改法 / 如果 / 终止 检查不过，文件不动；日志记返回字数
  四、真 call_claude + 假 claude CLI：argv（--allowedTools / --max-turns / --mcp-config）、工具调用记进 plan_tools.json（工具名、参数、返回字数）
  五、full：user 含数据包、先补查，system 与改动前一致；不认识的取值报错
"""
import json
import os
import shutil
import sys
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import test_dslagent_v2 as T                   # noqa: E402  复用它的假项目 / 计划

ROOT = T.ROOT
V, K, TMP = T.V, T.K, T.TMP
from tools.dslagent import dslmcp as DM         # noqa: E402
from tools.dslagent import packs                # noqa: E402
from tools.dslagent import prompts as DPR       # noqa: E402
from tools.dslagent import promptfile as PF       # noqa: E402

PASS = FAIL = 0


def check(cond, msg, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✓ " + msg)
    else:
        FAIL += 1
        print("  ✗ " + msg + (f"\n      {str(extra)[:1500]}" if extra != "" else ""))


class RFake(T.Fake):
    """T.Fake + 接 tool 模式的额外参数（mcp_config / max_turns / reply_path），并记下来。"""

    def __init__(self, **replies):
        super().__init__(**replies)
        self.kws = []

    def __call__(self, system, user, tag, timeout, model=None, **kw):
        self.kws.append((tag, model, kw))
        r = super().__call__(system, user, tag, timeout, model=model)
        if r["text"].startswith("GUARD:"):         # 模拟保险触发：没有文本，reason 是 call_claude 给的原因
            return {"text": "", "reason": r["text"][6:], "cost": 0.01, "sec": 0.0}
        return r


def go(name, fake, **kw):
    return T.go(name, fake, **kw)


def user_of(f, tag):
    return next(u for t, _, u in f.log if t == tag)


def system_of(f, tag):
    return next(s for t, s, _ in f.log if t == tag)


# ------------------------------------------------------------------ 一、read 的输入

CODE_MARKS = ["## 候选模块", "## 开局测试", "同列名字共现行", "被点名字的全部引用行", "## 补查结果", "【数据包】", "```python",
              "### pkg/util.py L", "    return x * 2", "def double(x):\n"]


def t_input():
    print("一、read 的输入")
    f = RFake()
    r, p, out = go("rd_ok", f)
    check(r["reply"]["状态"] == "成功" and r["fixed"] and "x + x" in T.util(p), "read 全流程成功（改法套上、验收过）", r.get("stop"))
    check(f.tags() == ["plan", "bound"], "没有补查（preq）这一步", f.tags())
    u = user_of(f, "plan")
    check(u.startswith("【任务原文】\n" + T.TASK) and "## 文件大纲" in u and "pkg/util.py（共" in u, "user = 任务原文 + 文件大纲", u[:400])
    check(not any(m in u for m in CODE_MARKS), "user 里没有代码片段 / 引用行 / 登记处 / 测试断言 / 补查结果",
          [m for m in CODE_MARKS if m in u])
    check("double:" in u and "clamp:" in u, "大纲给的是函数名:起-止", u[-300:])
    s = system_of(f, "plan")
    READ_TAIL = PF.agent_doc("plan").variants["grok"][0][0]      # agents/plan.md「变体：grok」的原文＝claude / codex 的读法说明
    OLD = ("你看不到别的文件，也不能运行任何东西。", "- 改法：数据包 / 补查结果里能看到原文的改动，", "- 子任务：数据包里没有原文、或要看运行结果才能决定怎么改的，",
           "脚本必须覆盖数据包和补查结果里查到的**每一个**位置", "不用 定位.zs / 读改测.zs（数据包已给原文）。",
           "你看不到代码，只能靠脚本里的动词去读；读到的内容要嵌进 问JSON 的提示词里，模型才看得到")
    check(READ_TAIL in s, "读法说明在 read 的 system 里")
    check(not any(a in s for a in OLD), "与按需读矛盾的旧说法都不在 system 里", [a[:20] for a in OLD if a in s])
    check("- 用 dsl 工具：读片段、搜索代码、查引用\n- 读片段按大纲里的 文件:起-止 取\n- 读够就停，直接输出完整 .zs" in s,
          "读法说明的原话在 system 里", s[:300])
    check("「补查结果」" not in s and "确定性抽出" not in s and "候选文件的大纲" in s, "讲资料包各节 / 补查结果的那句已去掉", s[:200])
    check(s == V.plan_system(packs.current()), "plan_system 就是 agents/plan.md 展开后的 system")
    v = r["v2"]
    check("规划方式" not in v and "补查" not in v and "补查项" not in v and v["大纲字符"] == len(u.split("\n\n", 1)[1])
          and (out / "outline.md").is_file() and not (out / "pack.md").exists() and v["候选"],
          "记录：大纲字符 / outline.md（没有 pack.md、没有补查字段）", {k: v.get(k) for k in ("大纲字符", "候选")})
    check(set(v["步骤秒"]) == {"1大纲", "3规划", "4执行", "5验收", "6边界复核"}, "步骤里没有 2补查", v["步骤秒"])

    # 资料包不再有 collect / extra / QUERY_SYS（full 方式已删）
    check(not any(hasattr(K, n) for n in ("collect", "extra", "QUERY_SYS", "PRE_SYS", "run_queries")), "packs.code 没有 collect / extra / 补查入口")
    check(not hasattr(V, "plan_user") and not hasattr(V, "plan_mode") and not hasattr(V, "parse_json"), "v2 没有 plan_user / plan_mode / parse_json")

    # 包没实现 plan_outline → 只有任务原文
    mod = types.ModuleType("tests_pack_nooutline")
    mod.__dict__.update({k: v for k, v in K.__dict__.items() if k not in ("plan_outline", "materials") and not k.startswith("__")})
    mod.NAME = "nooutline"
    sys.modules[mod.__name__] = mod
    packs.REGISTRY["nooutline"] = mod.__name__
    os.environ["DSLAGENT_PACK"], os.environ["DSLAGENT_VERIFY"] = "nooutline", "code"
    try:
        f = RFake()
        r, p, out = go("rd_noout", f)
    finally:
        os.environ.pop("DSLAGENT_PACK"), os.environ.pop("DSLAGENT_VERIFY")
        packs.REGISTRY.pop("nooutline")
    check(r["fixed"] and user_of(f, "plan") == "【任务原文】\n" + T.TASK, "包没有 plan_outline → user 只有任务原文", user_of(f, "plan")[:300])


# ------------------------------------------------------------------ 二、read 的规划调用

BAD = "用包 common text code\n预算 调用 2 秒 60\n设 x = 转大写 ls\n终止 成功 好\n\n#清单\n改 pkg/util.py:double\n"


def t_call():
    print("二、read 的规划调用")
    f = RFake()
    r, p, out = go("rd_call", f)
    tag, model, kw = f.kws[0]
    cfg = json.loads(Path(kw["mcp_config"]).read_text(encoding="utf-8"))["mcpServers"]["dsl"]
    a = cfg["args"]
    check(tag == "plan" and kw["max_turns"] == 12 and model is None, "规划调用 max_turns=12、没多传 model", f.kws[0])
    check("--readonly" in a and a[a.index("--workdir") + 1] == str(p.resolve()) and cfg["args"][0].endswith("dslmcp.py"),
          "挂 dslmcp --readonly，workdir = 待改项目", a)
    check("mcp_config" not in f.kws[1][2], "边界复核（bound）不挂工具", f.kws[1])
    calls = json.loads((out / "calls.json").read_text(encoding="utf-8"))
    check(calls[0]["tool"] == 1 and calls[0]["tag"] == "plan" and calls[0]["model"] == "sonnet", "calls.json 记这次是工具调用", calls[0])

    f = RFake(plan=[BAD, T.PLAN_OK])
    r, p, out = go("rd_fix", f)
    check(f.tags() == ["plan", "plan_fix", "bound"] and r["fixed"], "计划检查不过 → 重写 1 次（plan_fix）后成功", f.tags())
    fx = [k for k in f.kws if k[0] == "plan_fix"][0]
    check("mcp_config" in fx[2] and fx[2]["max_turns"] == 12 and "--readonly" in json.loads(
        Path(fx[2]["mcp_config"]).read_text(encoding="utf-8"))["mcpServers"]["dsl"]["args"], "重写也走 read（同样挂只读工具、12 轮）", fx)
    check(system_of(f, "plan_fix") == system_of(f, "plan") and "没通过检查" in user_of(f, "plan_fix")
          and "转大写" in user_of(f, "plan_fix"), "重写：system 同 read、user 是 fix_prompt", user_of(f, "plan_fix")[:200])

    f = RFake(plan=["GUARD:空闲超时", T.PLAN_OK])
    r, p, out = go("rd_retry", f)
    calls = json.loads((out / "calls.json").read_text(encoding="utf-8"))
    check(f.tags() == ["plan", "plan", "bound"] and r["fixed"] and calls[0].get("failed") == "空闲超时" and not calls[1].get("failed"),
          "空闲超时 → 同输入重试 1 次，成功", (f.tags(), [c.get("failed") for c in calls]))
    check(user_of(f, "plan") == f.log[1][2] and f.log[0][1] == f.log[1][1], "重试输入不变")

    f = RFake(plan=["先看看 <invoke name=x>", T.PLAN_OK])
    r, p, out = go("rd_invoke", f)
    check(f.tags() == ["plan", "plan", "bound"] and r["fixed"], "最终文本里写 <invoke → 当失败重试 1 次", f.tags())

    f = RFake(plan="GUARD:空闲超时")
    r, p, out = go("rd_twice", f)
    check(f.tags() == ["plan", "plan"] and r["reply"]["状态"] == "失败" and "模型没有回应" in r["reply"]["原因"]
          and "空闲超时" in r["reply"]["原因"] and not r["changed_files"], "重试仍失败 → 状态失败、项目不动", r["reply"])

    os.environ["DSLAGENT_PLAN_MODEL"] = "opus"
    try:
        f = RFake()
        r, p, out = go("rd_model", f)
    finally:
        del os.environ["DSLAGENT_PLAN_MODEL"]
    check(f.kws[0][1] == "opus" and f.kws[1][1] is None, "DSLAGENT_PLAN_MODEL 对 read 规划也生效", f.kws)

    for bad, needles in (("half", ("half", "已去掉")), ("full", ("已移除", "full"))):
        os.environ["DSLAGENT_PLAN_MODE"] = bad
        try:
            f = RFake()
            r, p, out = T.go("rd_bad_" + bad, f)
        finally:
            os.environ.pop("DSLAGENT_PLAN_MODE")
        check(r["reply"]["状态"] == "失败" and all(n in r["reply"]["原因"] for n in needles) and not f.log and not r["changed_files"],
              f"DSLAGENT_PLAN_MODE={bad} → 失败、不调模型、说明已去掉 / 已移除", r["reply"])
    os.environ["DSLAGENT_PLAN_MODE"] = "read"
    try:
        f = RFake()
        r, p, out = T.go("rd_read", f)
    finally:
        os.environ.pop("DSLAGENT_PLAN_MODE")
    check(r["fixed"], "DSLAGENT_PLAN_MODE=read 等于没设")


# ------------------------------------------------------------------ 三、只读工具

def t_readonly():
    print("三、只读工具（真起 MCP）")
    p = T.make_proj("ro")
    log = TMP / "ro.jsonl"
    log.unlink(missing_ok=True)
    srv = DM.Server(p, log, str(V.VERBS), readonly=True)

    def call(code):
        r = srv.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "dsl", "arguments": {"code": code}}})
        return r["result"]["content"][0]["text"]
    lst = srv.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]
    desc = lst[0]["description"]
    check(len(lst) == 1 and lst[0]["name"] == "dsl" and "只读" in desc and "读片段" in desc and "改文件" not in desc and "#改法" not in desc,
          "tools/list：只有 dsl，描述是只读版", desc[:80])
    t = call("设 r = 读片段 pkg/util.py:1-3\n打印 {r}")
    check("   1| def clamp(x, lo, hi):" in t, "读片段可用", t)
    t = call("设 h = 搜索代码 double\n打印 {h}")
    check("pkg/util.py" in t, "搜索代码可用（变量跨调用保留）", t)
    t = call("设 q = 查引用 twice py\n打印 {q.n}")
    check(t.strip().endswith("2") or "[打印]" in t, "查引用可用", t)
    before = (p / "pkg" / "util.py").read_text(encoding="utf-8")
    for code, why in [(T.EDIT_DOUBLE.replace("#改法 e1", "#改法 e1").join(["设 res = 改文件 {e1}\n", ""]), "改文件 + #改法"),
                      ("设 res = 改文件 {e1}", "改文件"),
                      ("设 w = 写文件 {e}", "写文件"),
                      ("写文件 {e}", "裸写文件"),
                      ("如果 1 等于 1\n  打印 x\n结束", "如果"),
                      ("终止 成功 好", "终止"),
                      ("设 t = 跑测试", "跑测试"),
                      ("设 r = 派任务 a b", "派任务")]:
        t = call(code)
        check("检查不过" in t and "文件没有改动" in t, f"拒绝：{why}", t[:300])
    check((p / "pkg" / "util.py").read_text(encoding="utf-8") == before, "文件没动")
    rows = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]
    check(all("out_chars" in x and x["out_chars"] > 0 for x in rows) and [x["status"] for x in rows][:3] == ["ok", "ok", "ok"]
          and rows[0]["out_chars"] == len(rows[0].get("reply") or "") or rows[0]["out_chars"] > 20, "日志每行记返回字数 out_chars", rows[:2])
    # 非只读的服务器照旧（子任务 tool 模式）：out_chars 也记，描述仍有 改文件
    srv2 = DM.Server(p, TMP / "rw.jsonl", str(V.VERBS))
    d2 = srv2.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"][0]["description"]
    check("改文件" in d2 and "只读" not in d2, "不带 --readonly 的行为不变（子任务 tool 模式）")


# ------------------------------------------------------------------ 四、真 call_claude + 假 claude CLI

def t_cli():
    print("四、真 call_claude + 假 claude CLI")
    rec = TMP / "rec.jsonl"
    rec.unlink(missing_ok=True)
    steps = TMP / "steps.json"
    read = "设 r = 读片段 pkg/util.py:1-9\n打印 {r}"
    steps.write_text(json.dumps({"attempts": [
        [{"call": read}, {"call": "设 res = 改文件 {e1}\n" + T.EDIT_DOUBLE}, {"call": "设 h = 搜索代码 twice"}, {"text": T.PLAN_OK}],
        [{"text": T.BOUND_OK}]]}, ensure_ascii=False), encoding="utf-8")
    env = dict(CBATCH_CLAUDE=str(HERE / "fake_claude_tool.py"), FAKE_STEPS=str(steps), FAKE_REC=str(rec))
    old = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    try:
        p = T.make_proj("cli")
        out = TMP / "out_cli"
        shutil.rmtree(out, ignore_errors=True)
        r = V.run(p, T.TASK, out, test_cmd=T.TEST_CMD)
    finally:
        for k, v in old.items():
            os.environ.pop(k) if v is None else os.environ.__setitem__(k, v)
    check(r["fixed"] and "x + x" in T.util(p), "假 CLI 走完 read 全流程（工具读 → 计划 → 执行 → 验收）", r.get("stop"))
    recs = [json.loads(x) for x in rec.read_text(encoding="utf-8").splitlines()]
    a = recs[0]["argv"]
    arg = lambda k: a[a.index(k) + 1]   # noqa: E731
    check(len(recs) == 2, "CLI 只调 2 次：规划 + 边界复核（没有补查）", len(recs))
    check(arg("--max-turns") == "12" and arg("--allowedTools") == "mcp__dsl__dsl" and arg("--tools") == ""
          and "--strict-mcp-config" in a and "--mcp-config" in a, "规划那次 argv：max-turns 12、只许 mcp__dsl__dsl、内置工具关", a)
    cfg = json.loads(Path(arg("--mcp-config")).read_text(encoding="utf-8"))["mcpServers"]
    check(list(cfg) == ["dsl"] and "--readonly" in cfg["dsl"]["args"], "MCP 只有一个 dsl、带 --readonly")
    u = recs[0]["stdin"]
    check(u.startswith("【任务原文】") and "## 文件大纲" in u and not any(m in u for m in CODE_MARKS), "stdin = 任务原文 + 大纲", u[:200])
    check("--mcp-config" not in recs[1]["argv"], "边界复核那次不挂工具")
    tools = json.loads((out / "plan_tools.json").read_text(encoding="utf-8"))
    check([x["工具"] for x in tools] == ["dsl"] * 3 and "读片段" in tools[0]["参数"] and tools[0]["返回字数"] > 50
          and [x["状态"] for x in tools] == ["ok", "check", "ok"] and tools[1]["返回字数"] > 0,
          "plan_tools.json 记了每次工具调用（工具名、参数、返回字数、状态；改文件被拒）", tools)
    check(r["v2"]["规划工具"] == {"次数": 3, "返回字数": sum(x["返回字数"] for x in tools)}, "result.json 里有规划工具汇总", r["v2"].get("规划工具"))


# ------------------------------------------------------------------ 五、plan_mode 选项已去掉

def t_plan_mode():
    print("五、plan_mode 选项已去掉")
    for v in ("", "read", " READ "):
        V.check_plan_mode(v)
    check(True, "空 / read（大小写、空白不计）通过")
    for bad, needles in (("full", ("已移除", "full")), ("half", ("half", "已去掉"))):
        try:
            V.check_plan_mode(bad)
            check(False, f"check_plan_mode({bad!r}) 要报错")
        except ValueError as e:
            check(all(n in str(e) for n in needles), f"check_plan_mode({bad!r}) 报错说明", str(e))
    os.environ.pop("DSLAGENT_PLAN_MODE", None)
    V.check_plan_mode()
    check(True, "环境变量没设通过")


def main():
    for t in (t_input, t_call, t_readonly, t_cli, t_plan_mode):
        t()
    print(f"\n通过 {PASS}，失败 {FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
