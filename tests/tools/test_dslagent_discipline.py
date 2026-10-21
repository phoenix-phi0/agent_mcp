# -*- coding: utf-8 -*-
"""子任务纪律段 + opencode 思考预算 + 子任务回复外壳补齐：不调真模型。

    cd /home/ysc/mcp && .venv/bin/python tests/tools/test_dslagent_discipline.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools import dsl_task as T                          # noqa: E402
from tools import json_repair as JR                      # noqa: E402
from tools.dslagent import agents as AG, engines as E    # noqa: E402
from tools.dslagent import v2 as V2                      # noqa: E402

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


def t_parse():
    print("一、引擎串（预算）")
    P = E.parse
    a = P("opencode:bailian-cli/qwen3.8-flash")
    check(a == {"engine": "opencode", "model": "bailian-cli/qwen3.8-flash", "effort": None, "spec": "opencode:bailian-cli/qwen3.8-flash"} and "budget" not in a,
          "不写预算：结构与原来逐字一致", a)
    b = P("opencode:bailian-cli/qwen3.8-flash:budget=6000")
    check((b["engine"], b["model"], b["budget"]) == ("opencode", "bailian-cli/qwen3.8-flash", 6000), "写预算 → budget=6000、model 不带后缀", b)
    for bad in ("budget=0", "budget=", "budget=-5", "budget=abc", "budget=6000.5", "budget=99999999", "budget=06000"):
        check(raises(lambda bad=bad: P(f"opencode:a/b:{bad}"), "预算") is True, f"非法预算 {bad} → 报错")
    check(raises(lambda: P("opencode:ab:budget=5"), "provider/model") is True, "预算前的模型不合法仍报错")
    check(E.normalize({"sub": "opencode:a/b:budget=3000"}) == {"sub": "opencode:a/b:budget=3000"}, "DSLAGENT_MODELS / models 里能写")
    import os
    os.environ[E.ENV] = json.dumps({"sub": "opencode:a/b:budget=3000"})
    try:
        check(E.from_env() == {"sub": "opencode:a/b:budget=3000"}, "from_env 读环境变量里的预算串")
    finally:
        del os.environ[E.ENV]
    check(raises(lambda: E.normalize({"sub": "opencode:a/b:budget=x"}), "预算") is True, "models 里写坏预算 → 报错")
    check(V2._rec_model(P("opencode:a/b:budget=6000")) == "a/b:budget=6000" and V2._rec_model(P("opencode:a/b")) == "a/b", "calls.json 记的模型带预算")


class _FakeProc:
    def __init__(self, cmd, user, timeout, idle, first_cap, cwd, env, reply_path, events=True):
        _FakeProc.seen = {"cmd": cmd, "env": env}
        self.p = type("P", (), {"stdout": iter([json.dumps({"type": "text", "part": {"text": "ok"}}) + "\n"]), "returncode": 0})()
        self.t0, self.killed = 0, False

    def event(self, now=None): return 1.0
    def active(self, now=None): pass
    def write_reply(self, s): pass
    def text_guard(self, s, total=None): pass
    def log_event(self, l): pass
    def kill(self, why=None): pass
    def close(self): return "", ""


def _run_oc(**kw):
    old = E._Proc
    E._Proc = _FakeProc
    try:
        r = E.call(E.parse(kw.pop("spec")), "SYS", "USER", 20)
    finally:
        E._Proc = old
    return r, json.loads(_FakeProc.seen["env"]["OPENCODE_CONFIG_CONTENT"])


def t_cfg():
    print("二、配置注入（mock 子进程）")
    r, cfg = _run_oc(spec="opencode:bailian-cli/qwen3.8-flash:budget=6000")
    o = cfg.get("provider", {}).get("bailian-cli", {}).get("models", {}).get("qwen3.8-flash", {}).get("options")
    check(o == {"enable_thinking": True, "thinking_budget": 6000}, "env 配置合并了 provider.<p>.models.<m>.options", cfg.get("provider"))
    check(cfg["agent"] and r["text"] == "ok" and r["model"] == "bailian-cli/qwen3.8-flash", "agent 配置仍在、-m 不带预算后缀", _FakeProc.seen["cmd"])
    check("-m" in _FakeProc.seen["cmd"] and _FakeProc.seen["cmd"][_FakeProc.seen["cmd"].index("-m") + 1] == "bailian-cli/qwen3.8-flash", "命令行 -m 是纯模型名")
    r, cfg2 = _run_oc(spec="opencode:bailian-cli/qwen3.8-flash")
    check("provider" not in cfg2, "没写预算：配置里没有 provider 段（与原来一致）", cfg2.keys())
    check({k: v for k, v in cfg.items() if k != "provider"} == cfg2, "写预算只多一个 provider 段，其余不变")
    c = {"provider": {"p": {"models": {"m": {"options": {"x": 1}}}}}}
    E._oc_budget(c, "p/m", 5)
    check(c["provider"]["p"]["models"]["m"]["options"] == {"x": 1, "enable_thinking": True, "thinking_budget": 5}, "已有 options 项保留")


def t_shell():
    print("三、外壳补齐")
    spec = [("edits", False, "列表", None)] if False else []
    ed = [{"file": "a.py", "old": "x", "new": "y"}]
    p = T.parse_check(json.dumps({"edits": ed}), [], shell=True)
    check(p["value"] and p["value"]["status"] == "成功" and p["value"]["result"]["edits"] == ed and "外壳补齐" in p["repaired"], "{edits:[…]} → 补齐、状态成功、记外壳补齐", p)
    p = T.parse_check("```json\n" + json.dumps({"edits": ed, "思路": "t"}) + "\n```", [], shell=True)
    check(p["value"] and p["value"].get("thought") == "t" and "thought" not in p["value"]["result"], "带围栏 + 思路：思路留顶层", p)
    p = T.parse_check(json.dumps({"edits": ed, "说明": "s"}), [], shell=True)
    check(p["value"] and p["value"]["result"] == {"edits": ed, "说明": "s"}, "edits 的兄弟字段进 结果")
    p = T.parse_check(json.dumps({"edits": ed}), [], shell=False)
    check(p["value"] is None, "不开 shell（fix / 工具模式）仍按原样判不合格")
    p = T.parse_check(json.dumps({"edits": "oops"}), [], shell=True)
    check(p["value"] is None and "外壳补齐" not in (p["repaired"] or ""), "edits 不是列表 → 不补，走重问")
    p = T.parse_check(json.dumps({"结果": {"edits": ed}}), [], shell=True)
    check(p["value"] is None and "缺少" in "".join(p["problems"]) or p["value"] is None, "有 结果 无 状态 → 不是缺外壳，不补（原判定）", p["problems"])
    p = T.parse_check(json.dumps({"状态": "成功", "edits": ed}), [], shell=True)
    check(p["value"] is None, "已有 状态 → 不补")
    p = T.parse_check("纯文字回复", [], shell=True)
    check(p["value"] is None, "非 JSON → 不补")
    p = T.parse_check(json.dumps({"result": {"edits": ed}, "status": "成功", "reason": ""}), [], shell=True)
    check(p["value"] and not p["repaired"], "标准回复：不标补齐")
    p = T.parse_check(json.dumps({"edits": []}), [], shell=True)
    check(p["value"] and p["value"]["result"]["edits"] == [], "edits 空列表也补（校验交给后续套用）")
    d, f = JR.fill_shell([1])
    check(d == [1] and f is False, "非字典原样返回")


class _Client:
    def __init__(self, replies):
        self.replies, self.n = list(replies), 0
        self.M = type("M", (), {"spec": staticmethod(lambda tag: {"engine": "claude"})})()

    def chat_messages(self, msgs, temperature=None, model=None):
        self.n += 1
        return self.replies.pop(0)


def t_dispatch():
    print("四、dispatch_json 端到端（假客户端）")
    ed = [{"file": "a.py", "old": "x", "new": "y"}]
    eng = type("E", (), {"system": "S", "temperature": 0, "model": None, "workdir": "."})()
    eng.client = _Client([json.dumps({"edits": ed})])
    r = T.dispatch_json(eng, "改", [], "", [])
    check(r.get("status") == "成功" and r["result"]["edits"] == ed and "外壳补齐" in r.get("repaired", "") and eng.client.n == 1, "缺外壳不重问、记外壳补齐", r)
    eng.client = _Client(["不是 json", json.dumps({"结果": {"edits": ed}, "状态": "成功", "原因": ""})])
    r = T.dispatch_json(eng, "改", [], "", [])
    check(r.get("status") == "成功" and eng.client.n == 2, "其他格式错误仍走重问", r)


def t_prompt():
    print("五、提示词含纪律段")
    s = AG.SUB_JSON.system_text()
    check("## 执行纪律与输出前自检" in s and "每个 old 都从入参原文逐字照抄" in s and "不改 tests/ 下的文件" in s, "sub 系统提示词含纪律段", s[-300:])
    check(s.index("## 执行纪律与输出前自检") < s.index("## 输出"), "纪律段在「输出」之前")


def main():
    for t in (t_parse, t_cfg, t_shell, t_dispatch, t_prompt):
        t()
    print(f"\n通过 {PASS}，失败 {FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
