# -*- coding: utf-8 -*-
"""dslagent v2 按步骤指定模型（dsl_options.models → DSLAGENT_MODELS；引擎在 tools/dslagent/engines.py）：不调真模型。

    cd /home/ysc/mcp && .venv/bin/python tests/tools/test_dslagent_models.py

  一、解析 / 校验：模型串各格式、强度取值、步骤名、字符串简写；read 规划支持 claude / codex / grok（opencode 不行）、tool 子任务只支持 claude；tag → 步骤
  二、路由（假 Python backend 跑 v2.run）：每步走对模型、缺省 sonnet、字符串简写、旧 DSLAGENT_PLAN_MODEL 兼容、models.plan 优先并记一句、
     非法 DSLAGENT_MODELS 判失败不调模型、calls.json 记 engine / model / effort、result.json 记生效的 models
  三、各引擎（假 codex / grok / opencode / claude 可执行脚本）：argv / stdin；保险：首事件前静默、空闲超时、<invoke、超长、rc≠0、尝试调用工具
  四、整条流程走假二进制：read 规划走 codex 挂 MCP（参数、plan_tools.json）、边界复核走 grok；full 规划走 opencode；失败重试 1 次
"""
import json
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import test_dslagent_v2 as T                   # noqa: E402  复用它的假项目 / 计划 / 假 backend

TMP, V = T.TMP, T.V
from tools.dslagent import engines as E, packs          # noqa: E402
from tools.dslagent import guard as G                    # noqa: E402
from tools.dslagent import promptfile as PF               # noqa: E402

PASS = FAIL = 0


def check(cond, msg, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✓ " + msg)
    else:
        FAIL += 1
        print("  ✗ " + msg + (f"\n      {str(extra)[:1500]}" if extra != "" else ""))


def raises(fn, *needles):
    try:
        fn()
    except ValueError as e:
        return all(n in str(e) for n in needles) or str(e)
    return "没报错"


# ------------------------------------------------------------------ 一、解析 / 校验

def t_parse():
    print("一、解析 / 校验")
    P = E.parse
    check(P("sonnet")["engine"] == "claude" and P("opus")["model"] == "opus" and P("haiku")["effort"] is None, "sonnet / opus / haiku → claude")
    check(P("claude-opus-4-1")["engine"] == "claude" and P("claude-sonnet-5-5")["model"] == "claude-sonnet-5-5", "完整 claude 模型名 → claude")
    c = P("codex:gpt-5.1")
    check((c["engine"], c["model"], c["effort"]) == ("codex", "gpt-5.1", "medium"), "codex:<模型> 强度缺省 medium", c)
    c = P("codex:gpt-5.1:xhigh")
    check((c["model"], c["effort"]) == ("gpt-5.1", "xhigh"), "codex:<模型>:<强度>", c)
    g = P("grok")
    check((g["engine"], g["model"], g["effort"]) == ("grok", None, "low"), "grok 强度缺省 low", g)
    check(P("grok:high")["effort"] == "high" and P("grok:xhigh")["effort"] == "xhigh", "grok:<强度>")
    o = P("opencode:zhipuai-coding-plan/glm-5.3")
    check((o["engine"], o["model"]) == ("opencode", "zhipuai-coding-plan/glm-5.3"), "opencode:<provider/model>", o)
    for bad, needles in [("gpt-5", ("不认识",)), ("", ("非空",)), (5, ("非空",)), ("codex:", ("codex:<模型>",)), ("codex", ("codex:<模型>",)),
                         ("codex:gpt-5:turbo", ("强度", "turbo")), ("codex:gpt-5:low:x", ("codex",)), ("grok:turbo", ("强度", "turbo")),
                         ("grok:", ("grok[:",)), ("grok:low:x", ("grok[:",)), ("grok:minimal", ("强度",)),
                         ("opencode:glm", ("provider/model",)), ("opencode:", ("provider/model",)), ("opus 4", ("不认识",))]:
        r = raises(lambda: P(bad), *needles)
        check(r is True, f"模型串 {bad!r} 报错", r)
    n = E.normalize
    check(n(None) == {} and n("") == {} and n({}) == {}, "空 → {}")
    check(n("opus") == {k: "opus" for k in E.STEPS}, "字符串 = 四步全用它")
    check(n({"plan": "opus", "bound": "grok:high"}) == {"plan": "opus", "bound": "grok:high"}, "字典只留写了的步骤")
    check(n({"plan": "", "sub": None, "fix": "haiku"}) == {"fix": "haiku"}, "空值 / None 当没写")
    r = raises(lambda: n({"plan": "opus", "judge": "opus"}), "judge", "plan")
    check(r is True, "步骤名不认识 → 报错并列出可用的", r)
    check(raises(lambda: n({"fix": "codex:gpt:turbo"}), "强度") is True, "字典里某项强度不对 → 报错")
    check(raises(lambda: n(["plan"]), "字典或字符串") is True, "类型不对 → 报错")
    V_ = E.validate
    check(V_({"plan": "codex:gpt-5"}, "json") == {"plan": "codex:gpt-5"} and V_({"plan": "opus"}, "tool"), "规划：claude / codex 可以")
    check(V_({"plan": "grok:medium"}, "json") == {"plan": "grok:medium"} and V_("grok", "json"), "规划：grok 可以（含字符串简写）")
    for eng in ("opencode:a/b",):
        r = raises(lambda: V_({"plan": eng}, "json"), "不能做规划", "claude")
        check(r is True, f"规划用 {eng} → 报错，说明 opencode 不能做规划", r)
    check(V_({"sub": "grok", "fix": "opencode:a/b", "bound": "codex:x"}, "json"), "sub / fix / bound 随便哪个引擎（json 子任务）")
    r = raises(lambda: V_({"sub": "codex:gpt-5"}, "tool"), "DSLAGENT_SUBTASK=tool", "claude")
    check(r is True, "tool 子任务用 codex → 报错", r)
    check(V_({"sub": "opus"}, "tool") == {"sub": "opus"}, "tool 子任务用 claude 可以")
    check(V_("grok", "json") == {k: "grok" for k in E.STEPS}, "字符串简写同样走组合检查（grok + json 通过）")
    check(raises(lambda: V_("opencode:a/b", "json"), "不能做规划") is True, "字符串简写 opencode → 报错（plan 也是 opencode）")
    S = E.step_of
    check([S(x) for x in ("plan", "plan_fix", "dsl01", "dsl12_读", "fix", "fix_reask", "bound", "bfix", "bfix_reask", "zzz")]
          == ["plan", "plan", "sub", "sub", "fix", "fix", "bound", "bound", "bound", None], "tag → 步骤")
    check(E.effective({"plan": "opus"}) == {"plan": "opus", "sub": "sonnet", "fix": "sonnet", "bound": "sonnet"}, "effective 补缺省 sonnet")
    os.environ["DSLAGENT_MODELS"] = "{坏"
    try:
        check(raises(E.from_env, "JSON") is True, "DSLAGENT_MODELS 不是 JSON → 报错")
        os.environ["DSLAGENT_MODELS"] = json.dumps({"plan": "opus"})
        check(E.from_env() == {"plan": "opus"}, "from_env 读 JSON")
    finally:
        del os.environ["DSLAGENT_MODELS"]
    check(E.from_env() == {}, "没设 → {}")


# ------------------------------------------------------------------ 二、路由（假 Python backend）

class MFake(T.Fake):
    pass


def run_with(name, fake, models=None, env=None, **kw):
    old = {k: os.environ.get(k) for k in ("DSLAGENT_MODELS", "DSLAGENT_PLAN_MODEL", "DSLAGENT_PLAN_MODE", "DSLAGENT_SUBTASK")}
    for k in old:
        os.environ.pop(k, None)
    if models is not None:
        os.environ["DSLAGENT_MODELS"] = models if isinstance(models, str) else json.dumps(models)
    os.environ.update(env or {})
    try:
        return T.go(name, fake, **kw)
    finally:
        for k, v in old.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)


REMEDY_PLAN = T.plan('''
设 res = 改文件 {e1}
设 t = 跑测试
如果 {t.passed} 不等于 是
  设 r = 派任务 修测试 {t.summary} 修好 edits:列表
  设 res = 改文件 {r.结果}
结束
终止 成功 好
''', edits=T.EDIT_DOUBLE.replace("return x + x", "return x * 3"))
REMEDY_FIX = {"结果": {"edits": [{"file": "pkg/util.py", "old": "return x * 3", "new": "return x + x"}]}, "状态": "成功", "原因": ""}
RESID_PLAN = T.PLAN_OK.replace("预算 调用 4 秒 300\n", "预算 调用 4 秒 300\n# 旧写法: return x \\* 2$\n")
RESID_FIX = {"结果": {"edits": [{"file": "pkg/other.py", "old": "    return x * 2", "new": "    return x + x"}], "说明": "twice 也改"},
             "状态": "成功", "原因": ""}


def models_of(f):
    return {t: m for t, m in f.models}


def t_routes():
    print("二、路由（假 backend 跑 v2.run）")
    M = {"plan": "opus", "sub": "haiku", "fix": "claude-sonnet-5-5", "bound": "opus"}
    f = MFake(plan=REMEDY_PLAN, dsl=REMEDY_FIX)
    r, p, out = run_with("rt_sub", f, M)
    mm = models_of(f)
    check(r["fixed"] and f.tags() == ["plan", "dsl01", "bound"], "全流程（规划 / 子任务 / 边界复核）", (f.tags(), r.get("stop")))
    check(mm == {"plan": "opus", "dsl01": "haiku", "bound": "opus"}, "plan → plan 模型；dsl01 → sub；bound → bound", mm)
    f = MFake(plan=RESID_PLAN, fix=RESID_FIX)
    r, p, out = run_with("rt_fix", f, M)
    check(r["fixed"] and models_of(f).get("fix") == "claude-sonnet-5-5" and "fix" in f.tags(), "验收补改 fix → fix 模型", (f.tags(), models_of(f)))
    f = MFake(bound=T.BOUND_RAISE, bfix=T.FIX_CLAMP)
    r, p, out = run_with("rt_bfix", f, M)
    mm = models_of(f)
    check(mm.get("bound") == "opus" and mm.get("bfix") == "opus" and "bfix" in f.tags(), "边界复核补改 bfix 跟 bound", (f.tags(), mm))
    # 不是 claude 的串：假 backend 收到完整模型串（真引擎走 engines.call，见第三 / 四）
    f = MFake(plan=REMEDY_PLAN, dsl=REMEDY_FIX)
    r, p, out = run_with("rt_mixed", f, {"sub": "grok:high", "bound": "codex:gpt-5.1:low"})
    check(models_of(f) == {"plan": None, "dsl01": "grok:high", "bound": "codex:gpt-5.1:low"}, "没写的步骤 backend 不多传 model（sonnet）", models_of(f))
    calls = json.loads((out / "calls.json").read_text(encoding="utf-8"))
    by = {c["tag"]: c for c in calls}
    check(by["plan"]["engine"] == "claude" and by["plan"]["model"] == "sonnet" and by["plan"]["effort"] is None, "calls.json：plan 记 claude / sonnet", by["plan"])
    check((by["dsl01"]["engine"], by["dsl01"]["model"], by["dsl01"]["effort"]) == ("grok", "grok", "high"), "calls.json：grok 记 model=grok / effort=high（不记成 sonnet）", by["dsl01"])
    check((by["bound"]["engine"], by["bound"]["model"], by["bound"]["effort"]) == ("codex", "gpt-5.1", "low"), "calls.json：codex 记 model / effort", by["bound"])
    from tools.dslagent import v2 as _v2
    check([_v2._rec_model(E.parse(x)) for x in ("grok:low", "codex:gpt-6-luna:high", "sonnet", "opencode:a/b")] == ["grok", "gpt-6-luna", "sonnet", "a/b"],
          "calls.json 记的模型：grok → grok、codex → 模型名、claude 照旧、opencode → 模型名（tool 模式同一函数）")
    check(r["v2"]["models"] == {"plan": "sonnet", "sub": "grok:high", "fix": "sonnet", "bound": "codex:gpt-5.1:low"}, "result.json 的 v2.models 是生效的四步", r["v2"]["models"])
    saved = json.loads((out / "result.json").read_text(encoding="utf-8"))
    check(saved["v2"]["models"] == r["v2"]["models"], "写进了 result.json")
    # 字符串简写
    f = MFake(plan=REMEDY_PLAN, dsl=REMEDY_FIX)
    r, p, out = run_with("rt_str", f, json.dumps("opus"))
    check(models_of(f) == {"plan": "opus", "dsl01": "opus", "bound": "opus"} and r["v2"]["models"] == {k: "opus" for k in E.STEPS},
          "字符串 = 四步全用它", models_of(f))
    # 没设 models：全 sonnet，backend 不多传 model
    f = MFake(plan=REMEDY_PLAN, dsl=REMEDY_FIX)
    r, p, out = run_with("rt_none", f)
    check(all(m is None for m in models_of(f).values()) and r["v2"]["models"] == {k: "sonnet" for k in E.STEPS}, "不设 models → 四步 sonnet", models_of(f))
    # 兼容：旧的 DSLAGENT_PLAN_MODEL 只管规划（plan / plan_fix）
    f = MFake()
    r, p, out = run_with("rt_legacy", f, env={"DSLAGENT_PLAN_MODEL": "opus"})
    check(models_of(f) == {"plan": "opus", "bound": None} and r["plan_model"] == "opus" and r["v2"]["models"]["plan"] == "opus"
          and "规划模型说明" not in r["v2"], "旧透传 DSLAGENT_PLAN_MODEL：规划用它，其它 sonnet，没有覆盖说明", (models_of(f), r["v2"]))
    # models.plan 写了以它为准，并记一句
    f = MFake()
    r, p, out = run_with("rt_over", f, {"plan": "haiku"}, env={"DSLAGENT_PLAN_MODEL": "opus"})
    check(models_of(f)["plan"] == "haiku" and r["plan_model"] == "haiku" and "models.plan=haiku" in r["v2"]["规划模型说明"]
          and "model=opus" in r["v2"]["规划模型说明"] and r["v2"]["models"]["plan"] == "haiku", "models.plan 优先于 model，结果里记一句", r["v2"].get("规划模型说明"))
    f = MFake()
    r, p, out = run_with("rt_same", f, {"plan": "opus"}, env={"DSLAGENT_PLAN_MODEL": "opus"})
    check("规划模型说明" not in r["v2"], "两者相同不用记说明")
    # 非法 DSLAGENT_MODELS
    for name, val, needle in [("rt_bad1", {"plan": "gpt-9"}, "不认识"), ("rt_bad2", {"judge": "opus"}, "步骤名"), ("rt_bad3", "{坏", "JSON"),
                              ("rt_bad4", {"plan": "opencode:a/b"}, "不能做规划")]:
        f = MFake()
        r, p, out = run_with(name, f, val)
        check(r["reply"]["状态"] == "失败" and needle in r["reply"]["原因"] and not f.log and not r["changed_files"],
              f"运行时再校验：{val!r} → 失败、不调模型", r["reply"])
    f = MFake()
    r, p, out = run_with("rt_tool", f, {"sub": "codex:gpt-5"}, env={"DSLAGENT_SUBTASK": "tool"})
    check(r["reply"]["状态"] == "失败" and "DSLAGENT_SUBTASK=tool" in r["reply"]["原因"] and not f.log, "tool 子任务 + codex → 失败、不调模型", r["reply"])


# ------------------------------------------------------------------ 三、各引擎（假二进制）

FAKE_PY = HERE / "fake_engine_tool.py"
BINS = TMP / "bins"
BINS.mkdir(exist_ok=True)
for _n in ("codex", "grok", "opencode", "claude"):
    _p = BINS / _n
    _p.write_text(f'#!/bin/sh\nexec {sys.executable} {FAKE_PY} {_n} "$@"\n', encoding="utf-8")
    _p.chmod(0o755)
ENV_BINS = {"DSLAGENT_CODEX_BIN": str(BINS / "codex"), "DSLAGENT_GROK_BIN": str(BINS / "grok"), "DSLAGENT_OC_BIN": str(BINS / "opencode"),
            "CBATCH_CLAUDE": str(BINS / "claude")}
REC = TMP / "rec.jsonl"
_cfg_n = [0]


def setup_fake(cfg):
    """写假引擎的回复脚本，清掉计数和记录；返回脚本路径。"""
    _cfg_n[0] += 1
    path = TMP / f"engines_{_cfg_n[0]}.json"
    path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    REC.unlink(missing_ok=True)
    os.environ.update(ENV_BINS, FAKE_ENGINES=str(path), FAKE_REC=str(REC))
    return path


def recs():
    return [json.loads(x) for x in REC.read_text(encoding="utf-8").splitlines()] if REC.exists() else []


def t_engines():
    print("三、各引擎（假 codex / grok / opencode）")
    old = (G.IDLE_SEC, G.IDLE_OC, G.MAX_OUT)
    first_env = {"DSLAGENT_CODEX_FIRST_CAP": "1", "DSLAGENT_GROK_FIRST_CAP": "1", "DSLAGENT_OC_FIRST_CAP": "1"}
    os.environ.update(first_env)
    G.IDLE_SEC, G.IDLE_OC = 1, 1
    try:
        for name, spec in (("codex", "codex:gpt-5.1:high"), ("grok", "grok:medium"), ("opencode", "opencode:zhipuai-coding-plan/glm-5.3")):
            sp = E.parse(spec)
            print(f"  -- {name}")
            setup_fake({name: [{"text": "你好 .zs"}]})
            r = E.call(sp, "SYS-文本", "USER-文本", 20, reply_path=TMP / f"rp_{name}.txt")
            check(r["text"] == "你好 .zs" and r["rc"] == 0 and not r["reason"] and r["engine"] == name and r["ttft"] is not None,
                  "正常：text / rc / engine / ttft", r)
            check(set(("text", "sec", "ttft", "cost", "usage", "rc", "stderr", "reason", "partial")) <= set(r), "返回字段同 call_claude")
            check((TMP / f"rp_{name}.txt").read_text(encoding="utf-8").strip() == "你好 .zs", "reply_path 边收边写")
            a = recs()[0]
            argv = a["argv"]
            if name == "codex":
                kv = lambda k: [x for x in argv if x.startswith(k)]   # noqa: E731
                check(argv[0] == "exec" and "--json" in argv and "--ephemeral" in argv and "--ignore-user-config" in argv and "--ignore-rules" in argv
                      and argv[argv.index("-s") + 1] == "read-only" and argv[argv.index("--disable") + 1] == "shell_tool" and argv[-1] == "-"
                      and "-o" in argv, "codex argv：exec / --json / read-only / 关 shell_tool / 忽略用户配置 / stdin", argv)
                check(argv[argv.index("-m") + 1] == "gpt-5.1" and 'model_reasoning_effort="high"' in argv and kv("developer_instructions=")
                      and json.loads(kv("developer_instructions=")[0].split("=", 1)[1]) == "SYS-文本" and a["stdin"] == "USER-文本",
                      "codex：-m、强度、system 走 developer_instructions、user 走 stdin", argv[-8:])
                check(not kv("mcp_servers"), "不带 mcp_config 时不挂 MCP")
            elif name == "grok":
                check(argv[argv.index("-p") + 1] == "USER-文本" and argv[argv.index("--system-prompt-override") + 1] == "SYS-文本"
                      and argv[argv.index("--reasoning-effort") + 1] == "medium" and "--model" not in argv
                      and argv[argv.index("--output-format") + 1] == "streaming-json" and "--no-subagents" in argv, "grok argv：-p、system override、强度、无 --model", argv)
            else:
                check(argv[:3] == ["run", "--format", "json"] and argv[argv.index("-m") + 1] == "zhipuai-coding-plan/glm-5.3" and "--pure" not in argv
                      and a["stdin"] == "USER-文本" and "USER-文本" not in argv, "opencode argv：run --format json、-m、无 --pure、user 走 stdin", argv)
            # 保险
            setup_fake({name: [{"mode": "silent"}]})
            r = E.call(sp, "s", "u", 30)
            check(r["reason"] == "首字前静默超时" and r["text"] == "" and r["sec"] < 10, "首事件前静默 → 杀（首字前静默超时）", r)
            setup_fake({name: [{"mode": "idle"}]})
            r = E.call(sp, "s", "u", 30)
            check(r["reason"] == "空闲超时" and r["text"] == "" and r["sec"] < 15, "空闲超时 → 杀", r)
            setup_fake({name: [{"mode": "invoke"}]})
            r = E.call(sp, "s", "u", 30)
            check(r["reason"] == "输出工具调用格式" and r["text"] == "", "文本里的 <invoke → 杀", r)
            setup_fake({name: [{"mode": "big"}]})
            r = E.call(sp, "s", "u", 30)
            check(r["reason"] == "输出超长" and r["text"] == "", "输出超长 → 杀", r)
            setup_fake({name: [{"mode": "rc"}]})
            r = E.call(sp, "s", "u", 30)
            check(r["rc"] == 3 and r["text"] == "" and "boom" in r["stderr"] and not r["reason"], "rc≠0 → 无文本、带 stderr", r)
            setup_fake({name: [{"mode": "tool"}]})
            r = E.call(sp, "s", "u", 30)
            check(r["reason"] == "尝试调用工具" and r["text"] == "", "尝试调用命令 / 工具 → 杀", r)
            setup_fake({name: [{"mode": "idle"}]})
            r = E.call(sp, "s", "u", 1.5)
            check(r["reason"] in ("总超时", "空闲超时"), "总超时兜底", r["reason"])
            if name == "codex":
                setup_fake({name: [{"text": "x"}]})
                E.call(sp, "s", "u", 30, mcp_config=str(_mcp_cfg()))
                argv = recs()[0]["argv"]
                check(any(x.startswith("mcp_servers.dsl.command=") for x in argv) and any(x.startswith("mcp_servers.dsl.args=") for x in argv)
                      and 'mcp_servers.dsl.default_tools_approval_mode="approve"' in argv, "codex + mcp_config：-c mcp_servers.dsl.command / args / approve", argv)
        # 没有强度 / 模型的缺省
        setup_fake({"codex": [{"text": "x"}], "opencode": [{"text": "x"}]})
        E.call(E.parse("codex:gpt-5"), "s", "u", 20)
        check('model_reasoning_effort="medium"' in recs()[0]["argv"], "codex 强度缺省 medium")
        E.call(E.parse("opencode:a/b"), "s", "u", 20)
        check("--variant" not in recs()[1]["argv"], "opencode 没有强度参数")
        setup_fake({"grok": [{"text": "x"}]})
        E.call(E.parse("grok"), "s", "u", 20)
        check(recs()[0]["argv"][recs()[0]["argv"].index("--reasoning-effort") + 1] == "low", "grok 强度缺省 low")
        # 二进制查找：环境变量 > PATH > ~/.local/bin/codex
        saved = os.environ.pop("DSLAGENT_CODEX_BIN")
        try:
            check(E.codex_bin().endswith("/codex"), "codex 二进制：没有覆盖时找 PATH，再找 ~/.local/bin/codex", E.codex_bin())
            old_path = os.environ["PATH"]
            os.environ["PATH"] = "/nonexistent"
            check(E.codex_bin() == str(Path.home() / ".local" / "bin" / "codex"), "PATH 上没有 → ~/.local/bin/codex", E.codex_bin())
            os.environ["PATH"] = old_path
        finally:
            os.environ["DSLAGENT_CODEX_BIN"] = saved
    finally:
        G.IDLE_SEC, G.IDLE_OC, G.MAX_OUT = old
        for k in first_env:
            os.environ.pop(k, None)


def _mcp_cfg():
    d = TMP / "mcpcfg"
    d.mkdir(exist_ok=True)
    p = d / "m.json"
    p.write_text(json.dumps({"mcpServers": {"dsl": {"command": sys.executable, "args": ["-c", "pass", "--a", "中文"]}}}, ensure_ascii=False), encoding="utf-8")
    return p


# ------------------------------------------------------------------ 四、整条流程（假二进制）

def run_real(name, models, env=None):
    old = {k: os.environ.get(k) for k in ("DSLAGENT_MODELS", "DSLAGENT_PLAN_MODE", "DSLAGENT_PLAN_MODEL", "DSLAGENT_SUBTASK")}
    for k in old:
        os.environ.pop(k, None)
    os.environ["DSLAGENT_MODELS"] = json.dumps(models)
    os.environ.update(env or {})
    try:
        p = T.make_proj(name)
        out = TMP / f"out_{name}"
        shutil.rmtree(out, ignore_errors=True)
        return V.run(p, T.TASK, out, test_cmd=T.TEST_CMD), p, out
    finally:
        for k, v in old.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)


def t_flow():
    print("四、整条流程（假二进制）")
    # read 规划走 codex 挂只读 MCP（真的调一次 dsl 工具），边界复核走 grok
    setup_fake({"codex": [{"text": T.PLAN_OK, "call": "设 r = 读片段 pkg/util.py:1-9\n打印 {r}"}], "grok": [{"text": T.BOUND_OK}]})
    r, p, out = run_real("fl_codex", {"plan": "codex:gpt-5.1:high", "bound": "grok:high"})
    check(r["fixed"] and "x + x" in T.util(p), "read 规划 codex + 边界复核 grok：全流程成功", r.get("stop"))
    rc = recs()
    check([x["engine"] for x in rc] == ["codex", "grok"], "只调了 codex（规划）和 grok（边界复核），没有 claude", [x["engine"] for x in rc])
    argv = rc[0]["argv"]
    srv_args = json.loads(next(x for x in argv if x.startswith("mcp_servers.dsl.args=")).split("=", 1)[1])
    check(next(x for x in argv if x.startswith("mcp_servers.dsl.command=")) == "mcp_servers.dsl.command=" + json.dumps(sys.executable)
          and "--readonly" in srv_args and srv_args[srv_args.index("--workdir") + 1] == str(p) and 'mcp_servers.dsl.default_tools_approval_mode="approve"' in argv
          and argv[argv.index("-m") + 1] == "gpt-5.1" and 'model_reasoning_effort="high"' in argv, "read 规划 codex：挂只读 dslmcp（workdir=项目）、approve、模型 / 强度", srv_args)
    check(rc[0]["stdin"].startswith("【任务原文】") and "## 文件大纲" in rc[0]["stdin"], "codex 的 stdin = 任务原文 + 大纲")
    tools = json.loads((out / "plan_tools.json").read_text(encoding="utf-8"))
    check(len(tools) == 1 and "读片段" in tools[0]["参数"] and tools[0]["返回字数"] > 50 and tools[0]["状态"] == "ok", "plan_tools.json 照写（工具名、参数、返回字数）", tools)
    check(r["v2"]["规划工具"]["次数"] == 1, "result.json 有规划工具汇总", r["v2"].get("规划工具"))
    calls = json.loads((out / "calls.json").read_text(encoding="utf-8"))
    check([(c["tag"], c["engine"], c["model"], c["effort"]) for c in calls] == [("plan", "codex", "gpt-5.1", "high"), ("bound", "grok", "grok", "high")]
          and calls[0]["tool"] == 1 and calls[0]["tool_calls"] == 1, "calls.json：engine / model / effort（codex 规划记工具调用 1 次）", calls)
    check(r["v2"]["models"] == {"plan": "codex:gpt-5.1:high", "sub": "sonnet", "fix": "sonnet", "bound": "grok:high"}, "v2.models 记生效的四步", r["v2"]["models"])

    # 规划走 claude（缺省 sonnet），子任务走 opencode，边界复核走 claude haiku（假 claude）
    setup_fake({"opencode": [{"text": json.dumps(REMEDY_FIX, ensure_ascii=False)}], "claude": [{"text": REMEDY_PLAN}, {"text": T.BOUND_OK}]})
    r, p, out = run_real("fl_oc", {"sub": "opencode:zhipuai-coding-plan/glm-5.3", "bound": "haiku"})
    rc = recs()
    check(r["fixed"] and [x["engine"] for x in rc] == ["claude", "opencode", "claude"], "规划 claude + 子任务 opencode + 边界复核 claude", ([x["engine"] for x in rc], r.get("stop")))
    check(rc[2]["argv"][rc[2]["argv"].index("--model") + 1] == "haiku", "claude 步骤带 --model haiku")
    check(rc[1]["argv"][rc[1]["argv"].index("-m") + 1] == "zhipuai-coding-plan/glm-5.3", "opencode 的 -m")

    # 失败重试 1 次：首次 rc≠0，第二次成功；记录 retry / first_fail
    setup_fake({"codex": [{"mode": "rc"}, {"text": T.PLAN_OK}], "claude": [{"text": T.BOUND_OK}]})
    r, p, out = run_real("fl_retry", {"plan": "codex:gpt-5.1"})
    calls = json.loads((out / "calls.json").read_text(encoding="utf-8"))
    check(r["fixed"] and [c["engine"] for c in calls] == ["codex", "codex", "claude"] and calls[0].get("failed") == "rc=3"
          and not calls[1].get("failed"), "read 规划 codex 失败 → 同输入重试 1 次后成功（第一次记 failed）",
          [(c["tag"], c.get("failed"), c.get("retry")) for c in calls])
    check(len([x for x in recs() if x["engine"] == "codex"]) == 2, "codex 被调了 2 次", [x["engine"] for x in recs()])

    # 两次都失败 → 判失败，项目不动
    setup_fake({"codex": [{"mode": "rc"}]})
    r, p, out = run_real("fl_fail", {"plan": "codex:gpt-5.1"})
    check(r["reply"]["状态"] == "失败" and "模型没有回应" in r["reply"]["原因"] and "rc=3" in r["reply"]["原因"] and not r["changed_files"]
          and T.util(p) == T.UTIL, "两次都失败 → 状态失败、项目不动", r["reply"])

    # sub / fix 走 codex（json 子任务）：计划里派任务 → codex；验收残留补改 → grok
    setup_fake({"codex": [{"text": json.dumps(REMEDY_FIX, ensure_ascii=False)}], "claude": [{"text": REMEDY_PLAN}], "grok": [{"text": T.BOUND_OK}]})
    r, p, out = run_real("fl_sub", {"sub": "codex:gpt-5.1:low", "bound": "grok"})
    rc = recs()
    check(r["fixed"], "sub 走 codex（派任务）、bound 走 grok、plan 走 claude：全流程成功", ([x["engine"] for x in rc], r.get("stop")))
    check([x["engine"] for x in rc] == ["claude", "codex", "grok"], "调用顺序：规划 claude → 子任务 codex → 边界复核 grok", [x["engine"] for x in rc])


def t_grok_read():
    print("五、grok read 规划（自带只读工具）")
    old = (G.IDLE_SEC, E.GROK_READ_CAP)
    G.IDLE_SEC = 2
    os.environ["DSLAGENT_GROK_FIRST_CAP"] = "5"
    try:
        sp = E.parse("grok:medium")
        proj = TMP / "grok_read_cwd"
        proj.mkdir(exist_ok=True)
        setup_fake({"grok": [{"text": "OUT .zs", "reads": [["read_file", {"path": "a.py", "start": 1, "end": 5}, 120], ["grep", {"pattern": "def f"}, 30]]}]})
        r = E.call(sp, "SYS", "USER", 20, read_cwd=str(proj))
        a = recs()[0]
        argv = a["argv"]
        deny = [argv[i + 1] for i, x in enumerate(argv) if x == "--deny"]
        dis = argv[argv.index("--disallowed-tools") + 1].split(",")
        check(a["cwd"] == str(proj) and argv[argv.index("--tools") + 1] == "read_file,grep,list_dir" and argv[argv.index("--max-turns") + 1] == "10"
              and argv[argv.index("--reasoning-effort") + 1] == "medium" and argv[argv.index("--permission-mode") + 1] == "dontAsk"
              and "--no-subagents" in argv and "--disable-web-search" in argv, "grok read 参数：cwd=项目、只读三件套、max-turns 10、强度、dontAsk、无子代理 / 联网", (a["cwd"], argv))
        check({"write", "Edit", "Bash", "run_terminal_command", "MCPTool"} <= set(deny)
              and {"write", "search_replace", "run_terminal_command", "spawn_subagent", "web_search", "web_fetch"} <= set(dis)
              and not ({"read_file", "grep", "list_dir"} & set(dis)), "grok read：写 / 编辑 / 命令 / 联网 / 子代理 deny，只读工具不在禁用表", (deny, dis))
        check(r["text"] == "OUT .zs" and not r["reason"] and r["rc"] == 0 and r["tool_calls"] == 2, "读完后回复 = 最后一次工具调用之后的文本", r)
        check(r["calls"] == [{"工具": "read_file", "参数": {"path": "a.py", "start": 1, "end": 5}, "返回字数": 120}, {"工具": "grep", "参数": {"pattern": "def f"}, "返回字数": 30}],
              "calls 记工具名、参数、返回字数", r["calls"])
        setup_fake({"grok": [{"text": "x"}]})
        E.call(sp, "SYS", "USER", 20)
        a = recs()[0]
        check(a["cwd"] != str(proj) and a["argv"][a["argv"].index("--tools") + 1] == "read_file" and "--max-turns" not in a["argv"], "不带 read_cwd 时仍是老参数（空目录、无 max-turns）")
        setup_fake({"grok": [{"mode": "write"}]})
        r = E.call(sp, "s", "u", 30, read_cwd=str(proj))
        check(r["reason"] == "调用被禁工具" and r["text"] == "" and r["sec"] < 10, "出现被禁工具调用（write）→ 杀（调用被禁工具）", r)
        E.GROK_READ_CAP = 100
        setup_fake({"grok": [{"text": "x", "reads": [["read_file", {"path": "a"}, 60], ["read_file", {"path": "b"}, 60]]}]})
        r = E.call(sp, "s", "u", 30, read_cwd=str(proj))
        check(r["reason"] == "读超限" and r["text"] == "", "累计读入超上限 → 杀（读超限）", r)
        E.GROK_READ_CAP = old[1]
        check("调用被禁工具" in G.GUARD_REASONS and "读超限" in G.GUARD_REASONS, "两种原因都算保险触发（失败重试）")
        # 提示：grok 版那句；claude / codex 不变
        pk = packs.current()
        sg, sc = V.plan_system(pk, "grok"), V.plan_system(pk)
        READ_TAIL, READ_TAIL_GROK = PF.agent_doc("plan").variants["grok"][0]      # agents/plan.md「变体：grok」第一对：dsl 版 → grok 版
        check(READ_TAIL_GROK in sg and READ_TAIL not in sg and "limit 不超过 120" in sg and "合计最多 8 次" in sg and "limit 不超过 200" not in sg and "dsl 工具" not in sg
              and "搜索代码 / 查引用" not in sg, "grok 的 read system：换成 grok 版那句，不再提 dsl 工具", sg[:400])
        check(READ_TAIL in sc and READ_TAIL_GROK not in sc and sc == V.plan_system(pk, "claude") == V.plan_system(pk, "codex"),
              "claude / codex 的 read system 不变")
        check(len(sg) < len(sc) + 400, "没有复制整份 system")
        # 整条流程：规划走 grok read，plan_tools.json 记录
        setup_fake({"grok": [{"text": T.PLAN_OK, "reads": [["read_file", {"path": "pkg/util.py", "start": 1, "end": 9}, 88]]}], "claude": [{"text": T.BOUND_OK}]})
        r, p, out = run_real("fl_grok_read", {"plan": "grok:high"})
        rc = [x for x in recs() if x["engine"] == "grok"]
        check(r["fixed"] and "x + x" in T.util(p), "read 规划走 grok：全流程成功", r.get("stop"))
        check(rc[0]["cwd"] == str(p) and rc[0]["argv"][rc[0]["argv"].index("--reasoning-effort") + 1] == "high" and READ_TAIL_GROK in rc[0]["argv"][rc[0]["argv"].index("--system-prompt-override") + 1]
              and rc[0]["stdin"].startswith("【任务原文】") and "## 文件大纲" in rc[0]["stdin"], "流程里 grok：cwd=项目、强度、grok 版 system、user=任务+大纲")
        tools = json.loads((out / "plan_tools.json").read_text(encoding="utf-8"))
        check(len(tools) == 1 and tools[0]["工具"] == "read_file" and tools[0]["参数"]["path"] == "pkg/util.py" and tools[0]["返回字数"] == 88
              and tools[0]["调用"] == "plan" and tools[0]["尝试"] == 1 and "序" in tools[0], "plan_tools.json 记 工具 / 参数 / 返回字数", tools)
        check(r["v2"]["规划工具"] == {"次数": 1, "返回字数": 88}, "result 里有规划工具汇总", r["v2"].get("规划工具"))
        # 被禁工具 → 重试 1 次
        setup_fake({"grok": [{"mode": "write"}, {"text": T.PLAN_OK}], "claude": [{"text": T.BOUND_OK}]})
        r, p, out = run_real("fl_grok_ban", {"plan": "grok"})
        calls = json.loads((out / "calls.json").read_text(encoding="utf-8"))
        check(r["fixed"] and calls[0].get("failed") == "调用被禁工具" and not calls[1].get("failed") and T.util(p) != T.UTIL,
              "被禁工具调用 → 同输入重试 1 次后成功", [(c["tag"], c.get("failed")) for c in calls])
    finally:
        G.IDLE_SEC, E.GROK_READ_CAP = old
        os.environ.pop("DSLAGENT_GROK_FIRST_CAP", None)


def t_grok_wrapup():
    print("六、grok 读超限 → 收尾调用（不原样重试）")
    from tools.dslagent import wrapup as WU
    old = (G.IDLE_SEC, E.GROK_READ_CAP)
    G.IDLE_SEC = 5
    os.environ["DSLAGENT_GROK_FIRST_CAP"] = "5"
    try:
        # 重取：去重、顺序、越界、grep、list_dir
        proj = TMP / "wrap_proj"
        shutil.rmtree(proj, ignore_errors=True)
        (proj / "pkg").mkdir(parents=True)
        (proj / "pkg" / "a.py").write_text("".join(f"line{i}\n" for i in range(1, 21)), encoding="utf-8")
        (proj / "pkg" / "b.py").write_text("def f():\n    return 1\n", encoding="utf-8")
        calls = [{"工具": "read_file", "参数": {"target_file": str(proj / "pkg/a.py"), "offset": 3, "limit": 2}, "返回字数": 1},
                 {"工具": "grep", "参数": {"pattern": "def f", "glob": "**/*.{py}"}, "返回字数": 1},
                 {"工具": "read_file", "参数": {"target_file": str(proj / "pkg/a.py"), "offset": 3, "limit": 2}, "返回字数": 1},
                 {"工具": "read_file", "参数": {"target_file": "/etc/passwd"}, "返回字数": 1},
                 {"工具": "list_dir", "参数": {"target_directory": "pkg"}, "返回字数": 1}]
        txt, n, chars = WU.reread(proj, calls)
        check(n == 3 and chars == len(txt) and txt.index("3|line3") < txt.index("pkg/b.py:1:def f():") < txt.index("### list_dir pkg")
              and txt.count("3|line3") == 1 and "root:" not in txt, "重取：重复调用只取一次、越界取不到、按调用顺序拼", (n, txt))
        # 截断：超过上限去掉最早的、保留靠后的
        big = [{"工具": "read_file", "参数": {"target_file": f"pkg/big{i}.py"}, "返回字数": 1} for i in range(4)]
        for i in range(4):
            (proj / "pkg" / f"big{i}.py").write_text(f"# big{i}\n" + ("x" * 49) + "\n", encoding="utf-8")
        txt, n, chars = WU.reread(proj, big, cap=200)
        check(n == 4 and chars == len(txt) <= 200 and "big3" in txt and "big2" in txt and "big0" not in txt and "big1" not in txt,
              "已读内容超上限：去掉最早的段，保留靠后的", (n, chars, txt))
        one = WU.reread(proj, big[:1], cap=20)
        check(one[2] == 20 and one[0] == WU.reread(proj, big[:1])[0][-20:], "只剩一段还超：保留它靠后的部分", one)
        check(WU.CAP == 120000, "默认上限 120000 字")
        # 整条流程：读超限 → 收尾调用
        pk = packs.current()
        E.GROK_READ_CAP = 100
        reads = [["read_file", {"target_file": "pkg/util.py", "offset": 1, "limit": 5}, 60], ["grep", {"pattern": "def double", "path": "pkg"}, 60]]
        setup_fake({"grok": [{"text": "半截", "reads": reads}, {"text": T.PLAN_OK}], "claude": [{"text": T.BOUND_OK}]})
        r, p, out = run_real("fl_grok_wrap", {"plan": "grok"})
        gr = [x for x in recs() if x["engine"] == "grok"]
        calls_j = json.loads((out / "calls.json").read_text(encoding="utf-8"))
        tags = [c["tag"] for c in calls_j]
        argv = gr[1]["argv"]
        sysp = argv[argv.index("--system-prompt-override") + 1]
        check(len(gr) == 2 and tags[:2] == ["plan", "plan_wrapup"] and calls_j[0].get("failed") == "读超限" and not calls_j[1].get("failed")
              and not any(c.get("retry") for c in calls_j), "读超限 → 第二次是 plan_wrapup、不是原样重试的 plan", (tags, [c.get("failed") for c in calls_j]))
        check("--max-turns" not in argv and argv[argv.index("--tools") + 1] == "read_file" and "read_file,grep,list_dir" not in argv and gr[1]["cwd"] != str(p),
              "收尾调用不带工具（不放开 read_file / grep / list_dir，不给项目 cwd）", argv)
        check(gr[1]["stdin"].startswith("【任务原文】") and "## 文件大纲" in gr[1]["stdin"] and "【已读内容】" in gr[1]["stdin"]
              and "读取额度已用完" in gr[1]["stdin"] and "### grep def double" in gr[1]["stdin"] and "pkg/util.py L1-5" in gr[1]["stdin"],
              "收尾 user = 任务原文 + 大纲 + 已读内容 + 说明", gr[1]["stdin"][-600:])
        check("## 本次不能调用工具" in sysp and PF.template("plan.md", "收尾说明") in sysp and sysp.startswith(V.plan_system(pk, "grok")),
              "收尾 system = grok 变体 + 模板「收尾说明」", sysp[-300:])
        check(r["fixed"] and r["v2"]["检查"][0].get("问题") == "" and T.util(p) != T.UTIL, "收尾产出的计划照常过检查并执行", r.get("stop"))
        w = r["v2"]["收尾"]
        check(w["触发"] is True and w["次"] == 1 and w["段数"] == 2 and w["字数"] > 0 and r["calls_by_purpose"].get("plan_wrapup") == 1,
              "result.json 记 触发 / 重取段数 / 字数，calls_by_purpose 有 plan_wrapup", (w, r["calls_by_purpose"]))
        check(calls_j[1]["engine"] == "grok" and not calls_j[1].get("tool"), "calls.json 里收尾调用记 engine=grok、不是工具调用", calls_j[1])
        # 没超限：不触发，字段在但为 False
        E.GROK_READ_CAP = old[1]
        setup_fake({"grok": [{"text": T.PLAN_OK, "reads": [["read_file", {"target_file": "pkg/util.py"}, 10]]}], "claude": [{"text": T.BOUND_OK}]})
        r, p, out = run_real("fl_grok_nowrap", {"plan": "grok"})
        check(r["fixed"] and r["v2"]["收尾"]["触发"] is False and "plan_wrapup" not in r["calls_by_purpose"], "没读超限：不触发收尾", r["v2"].get("收尾"))
        # 到轮数上限（max_turns_reached，rc=1，无回复）：引擎层记 error_max_turns，整条流程走收尾、不原样重试
        setup_fake({"grok": [{"mode": "maxturns", "reads": reads}]})
        r = E.call(E.parse("grok:medium"), "s", "u", 30, read_cwd=str(proj))
        check(r["subtype"] == "error_max_turns" and r["text"] == "" and r["rc"] == 1 and len(r["calls"]) == 2, "grok 到轮数上限：subtype=error_max_turns、无回复、calls 保留", r)
        setup_fake({"grok": [{"mode": "maxturns", "reads": reads}, {"text": T.PLAN_OK}], "claude": [{"text": T.BOUND_OK}]})
        r, p, out = run_real("fl_grok_maxturns", {"plan": "grok"})
        gr = [x for x in recs() if x["engine"] == "grok"]
        calls_j = json.loads((out / "calls.json").read_text(encoding="utf-8"))
        check(len(gr) == 2 and [c["tag"] for c in calls_j][:2] == ["plan", "plan_wrapup"] and calls_j[0].get("failed") == "轮数用尽"
              and not any(c.get("retry") for c in calls_j) and "--max-turns" not in gr[1]["argv"], "到轮数上限 → plan_wrapup、不原样重试", ([c["tag"] for c in calls_j], len(gr)))
        check(r["fixed"] and r["v2"]["收尾"]["触发"] is True and r["v2"]["收尾"]["段数"] == 2, "到轮数上限的收尾：计划照常执行、记 收尾 触发", r["v2"].get("收尾"))
        # 读超限以外的失败（被禁工具）照旧原样重试
        setup_fake({"grok": [{"mode": "write"}, {"text": T.PLAN_OK}], "claude": [{"text": T.BOUND_OK}]})
        r, p, out = run_real("fl_grok_ban2", {"plan": "grok"})
        check([c["tag"] for c in json.loads((out / "calls.json").read_text(encoding="utf-8"))][:2] == ["plan", "plan"] and r["v2"]["收尾"]["触发"] is False,
              "被禁工具仍是原样重试，不走收尾")
        # claude / codex 规划：读超限不适用，没有收尾字段
        setup_fake({"claude": [{"text": T.BOUND_OK}]})
        r, p, out = run_real("fl_claude_nowrap", {})
        check("收尾" not in r["v2"], "claude 规划路径不变：没有收尾记录")
        setup_fake({"codex": [{"text": T.PLAN_OK}], "claude": [{"text": T.BOUND_OK}]})
        r, p, out = run_real("fl_codex_nowrap", {"plan": "codex:gpt-5.1"})
        check(r["fixed"] and "收尾" not in r["v2"], "codex 规划路径不变：没有收尾记录", r.get("stop"))
        check(E.step_of("plan_wrapup") == "plan", "tag plan_wrapup 归 plan 步骤（用 models.plan 的引擎）")
    finally:
        G.IDLE_SEC, E.GROK_READ_CAP = old
        os.environ.pop("DSLAGENT_GROK_FIRST_CAP", None)


def main():
    for t in (t_parse, t_routes, t_engines, t_flow, t_grok_read, t_grok_wrapup):
        t()
    print(f"\n通过 {PASS}，失败 {FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
