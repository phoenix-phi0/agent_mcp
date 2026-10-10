# -*- coding: utf-8 -*-
"""派任务的「工具」模式（tools/dslagent/toolsub.py + dslmcp.py）。假 claude CLI（fake_claude_tool.py，真的拉起 MCP 服务、走 stream-json）+
真 v2.Model / call_claude / MCP，不调真模型。

    cd /home/ysc/mcp && .venv/bin/python tests/tools/test_dslagent_tool.py

  一、工具改后回 JSON 成功：文件真改了，计划里 改文件 {r.结果} 空操作，日志一行（edited / files）、记录工具调用 / 轮数
  二、工具结果报错后修正成功：改法原文对不上 → 工具结果里是报错 → 修正后套上
  三、轮数用尽触发兜底（error_max_turns）：恢复快照，用 json 模式重发，fallback=1
  四、兜底成功：json 模式给的 edits 由计划里的 改文件 套上；最终回复不是 JSON 也兜底
  五、最终文本含 <invoke 被拦（reason=输出工具调用格式）：重试 1 次；2 次 → 兜底；真实工具调用不算
  六、MCP 服务：白名单违规 / 空跑报错作为工具结果、变量跨调用共享、开关 DSLAGENT_SUBTASK=tool
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="dslagent_tool_"))
os.environ["DSLAGENT_STATE"] = str(TMP / "state")
os.environ["DSLAGENT_TMP"] = str(TMP / "dtmp")
os.environ["TMPDIR"] = str(TMP / "dtmp")
os.environ.pop("DSLAGENT_SUBTASK", None)
os.environ["CBATCH_CLAUDE"] = str(ROOT / "tests" / "tools" / "fake_claude_tool.py")
(TMP / "dtmp").mkdir()

from tools.dslagent import dslmcp as DM         # noqa: E402
from tools.dslagent import dslcheck as SS       # noqa: E402
from tools.dslagent import v2 as V              # noqa: E402
from tools.mock import MockClient               # noqa: E402

PASS = FAIL = 0


def check(cond, msg, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✓ " + msg)
    else:
        FAIL += 1
        print("  ✗ " + msg + (f"\n      {str(extra)[:1500]}" if extra != "" else ""))


UTIL = '''def clamp(x, lo, hi):
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x
'''
EDIT_BODY = """#改法 e1
@@ 改 pkg/util.py
<<<<<<< 原文
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x
=======
    return max(lo, min(x, hi))
>>>>>>> 新文
"""
EDIT = "设 r = 改文件 {e1}\n打印 {r.msg}\n" + EDIT_BODY
EDIT_MISS = EDIT.replace("    if x < lo:", "    if x <= lo:")
FINAL = json.dumps({"结果": {"edits": [], "说明": "pkg/util.py 的 clamp 改成 max/min"}, "状态": "成功", "原因": ""}, ensure_ascii=False)
JSON_EDITS = json.dumps({"结果": {"edits": [{"file": "pkg/util.py", "old": "    if x < lo:\n        return lo\n    if x > hi:\n        return hi\n    return x\n",
                                            "new": "    return max(lo, min(x, hi))\n"}], "说明": "json 兜底"}, "状态": "成功", "原因": ""},
                        ensure_ascii=False)
MAIN = """用包 common text code
设 desc = 任务：clamp改成max/min写法
设 inp.src = pkg/util.py:1-6
设 r = 派任务 {desc} {inp} 无 edits:列表,说明:文本
打印 状态={r.状态}
打印 说明={r.结果.说明}
打印 原因={r.原因}
设 e = 改文件 {r.结果}
打印 套用={e.ok}
"""
NEW = "return max(lo, min(x, hi))"


def project():
    d = Path(tempfile.mkdtemp(dir=TMP, prefix="proj_"))
    (d / "pkg").mkdir()
    (d / "pkg" / "util.py").write_text(UTIL, encoding="utf-8")
    return d


def run_main(attempts, json_replies=None, script=MAIN):
    """attempts：假 CLI 每次调用演的步骤；json_replies：兜底（json 模式）时模型回的文本。返回 (引擎, 输出, util.py 文本, 模型记录, 兜底 prompt 数)。"""
    proj, out = project(), Path(tempfile.mkdtemp(dir=TMP, prefix="out_"))
    steps = out / "steps.json"
    steps.write_text(json.dumps({"attempts": attempts}, ensure_ascii=False), encoding="utf-8")
    os.environ["FAKE_STEPS"] = str(steps)
    jr = list(json_replies or [])
    seen = []

    def backend(system, user, tag, timeout, **kw):
        if "mcp_config" in kw:
            return V.call_claude(system, user, timeout, reply_path=kw.get("reply_path"), mcp_config=kw["mcp_config"],
                                 max_turns=kw["max_turns"])
        seen.append(tag)
        return {"text": jr.pop(0) if jr else FINAL, "cost": 0.001, "rc": 0}
    M = V.Model(out, backend=backend)
    M.real = True            # call_claude 带 reply_path
    eng = V._engine_cls()(client=V.Client(M), workdir=proj, verbose=False, verbs_root=V.VERBS)
    eng.subtask_mode = "tool"
    eng.sublog = []
    eng.run(script)
    return eng, "\n".join(eng.output), (proj / "pkg" / "util.py").read_text(encoding="utf-8"), M, seen, out


def logrows(out):
    rows = []
    for f in sorted((out / "toollogs").glob("*.jsonl")):
        rows += [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines()]
    return rows


def t_edit():
    print("\n一、工具改后回 JSON 成功")
    eng, o, src, M, seen, out = run_main([[{"call": EDIT}, {"text": FINAL}]])
    check(NEW in src, "文件真改了", src)
    check("状态=成功" in o and "套用=是" in o, "计划里 改文件 {r.结果}（edits 为空）是空操作", o)
    log = eng.sublog[0] if eng.sublog else {}
    check(log.get("模式") == "工具" and log.get("工具调用") == 1 and log.get("轮数") == 2 and log.get("fallback") == 0, "sublog：工具模式 1 次调用 2 轮 无兜底", log)
    check(log.get("工具改文件") == ["pkg/util.py"] and "工具里改了：pkg/util.py" in o, "结果写明改了哪个文件", (log, o))
    rows = logrows(out)
    check(len(rows) == 1 and rows[0]["edited"] and rows[0]["files"] == ["pkg/util.py"] and rows[0]["code_len"] == len(EDIT) and "ts" in rows[0],
          "MCP 日志一行：时间 / code 长度 / 是否改文件 / 改了哪些 / 耗时", rows)
    check(len(M.log) == 1 and M.log[0].get("tool") == 1 and M.cost > 0, "Model 记 1 次调用、费用入账", M.log)
    check(log.get("缓存读", 0) > 0, "记缓存读 token", log)
    proj = project()
    base = V.snapshot(proj)
    (proj / "pkg" / "util.py").write_text("x = 1\n", encoding="utf-8")
    V.restore(proj, base, V.changed(base, V.snapshot(proj)))
    check((proj / "pkg" / "util.py").read_text(encoding="utf-8") == UTIL, "快照回滚能覆盖工具改的文件")


def t_fix():
    print("\n二、工具结果报错后修正成功")
    eng, o, src, M, seen, out = run_main([[{"call": EDIT_MISS}, {"call": EDIT}, {"text": FINAL}]])
    check(NEW in src and "状态=成功" in o, "第 1 次对不上、第 2 次修正套上、回 JSON", (o, src))
    log = eng.sublog[0]
    rows = logrows(out)
    check(log["工具调用"] == 2 and log["轮数"] == 3 and log["fallback"] == 0, "2 次工具调用 3 轮 无兜底", log)
    check([r["status"] for r in rows] == ["dry", "ok"] and [r["edited"] for r in rows] == [False, True], "日志：第 1 次空跑没过（未改）、第 2 次改了", rows)
    check(len(list((out / "calls").glob("*reply.txt"))) == 1, "回复落盘 calls/NN_tag.reply.txt")


def t_turns_fallback():
    print("\n三、轮数用尽 → 兜底；四、兜底成功")
    reads = [{"call": "设 t = 读片段 pkg/util.py:1-3\n"}] * 8
    eng, o, src, M, seen, out = run_main([reads, [{"call": EDIT}, {"call": "设 t = 读片段 pkg/util.py:1-3\n"}] * 4], [JSON_EDITS])
    log = eng.sublog[0]
    check(log["fallback"] == 1 and "轮数用尽" in log["fallback_reason"], "轮数用尽未回 JSON → fallback=1，记原因", log)
    check(len(seen) == 1, "用 json 模式（backend 无 mcp）重发 1 次", seen)
    check(NEW in src and "套用=是" in o and "状态=成功" in o, "兜底成功：json 的 edits 由计划里 改文件 套上", (o, src))
    # 第一次尝试里工具改过文件 → 兜底前恢复快照
    reads2 = [{"call": EDIT}] + [{"call": "设 t = 读片段 pkg/util.py:1-3\n"}] * 8
    eng, o, src, M, seen, out = run_main([reads2], [JSON_EDITS])
    check(eng.sublog[0]["fallback"] == 1 and NEW in src and "套用=是" in o, "工具改过又用尽轮数：先恢复快照，兜底 edits 才套得上", (o, src))
    # 最终回复不是合法 JSON
    eng, o, src, M, seen, out = run_main([[{"call": EDIT}, {"text": "我改好了，没有 JSON"}]], [JSON_EDITS])
    log = eng.sublog[0]
    check(log["fallback"] == 1 and "不是合法 JSON" in log["fallback_reason"] and NEW in src and "套用=是" in o, "最终回复不是 JSON → 兜底成功", (log, o))
    # 兜底的 json 也失败 → 子任务失败
    eng, o, src, M, seen, out = run_main([[{"text": "没 JSON"}]], ["还是没 JSON", "仍然没有"])
    check("状态=失败" in o and eng.sublog[0]["fallback"] == 1 and src == UTIL, "兜底也不合格 → 状态失败，文件不动", o)


def t_invoke():
    print("\n五、<invoke 被拦")
    bad = [{"text": "<invoke name=\"x\">"}, {"sleep": 30}]
    eng, o, src, M, seen, out = run_main([bad, [{"call": EDIT}, {"text": FINAL}]])
    log = eng.sublog[0]
    check(log["保险触发"] == ["输出工具调用格式"] and log["fallback"] == 0 and NEW in src and "状态=成功" in o, "触发 1 次 → 重试成功，不兜底", (log, o))
    check(any(x.get("failed") == "输出工具调用格式" for x in M.log) and M.log[0]["sec"] < 20, "第 1 次被快速杀掉（不等 sleep）", M.log)
    eng, o, src, M, seen, out = run_main([bad, bad], [JSON_EDITS])
    log = eng.sublog[0]
    check(log["保险触发"] == ["输出工具调用格式"] * 2 and log["fallback"] == 1 and "保险触发 2 次" in log["fallback_reason"], "触发 2 次 → 兜底", log)
    check(NEW in src and "套用=是" in o, "兜底 json 成功", (o, src))
    # 真实工具调用不算：中途一轮文字里没有、tool_use 块里有 "<invoke" 字样的代码也不拦
    sneaky = EDIT.replace("打印 {r.msg}", "打印 <invoke")
    eng, o, src, M, seen, out = run_main([[{"call": sneaky}, {"text": FINAL}]])
    check(eng.sublog[0]["保险触发"] == [] and NEW in src, "真实工具调用（tool_use）不算「输出工具调用格式」", eng.sublog[0])
    # 只查最终文本：中途文字（非最终）里的 <invoke 在 stream 里已经杀（当前一轮），最终文本合格的不受影响
    eng, o, src, M, seen, out = run_main([[{"call": EDIT}, {"text": FINAL + " <function_calls>"}], [{"call": EDIT}, {"text": FINAL}]])
    check(eng.sublog[0]["保险触发"] == ["输出工具调用格式"] and eng.sublog[0]["fallback"] == 0, "最终文本含 <function_calls> 也被拦（重试后成功）", eng.sublog[0])


def t_server():
    print("\n六、MCP 服务 / 开关")
    proj = project()
    log = TMP / "srv.jsonl"
    srv = DM.Server(proj, log, V.VERBS)
    t, info = srv.run_code("终止 成功 好\n")
    check("检查不过" in t and info["status"] == "check" and not info["edited"], "白名单违规（终止）作为工具结果返回", t)
    t, info = srv.run_code("设 a = 1\n设 s = 读片段 pkg/util.py:1-2\n")
    t2, info2 = srv.run_code("打印 a={a}\n")
    check("a=1" in t2, "变量跨调用共享", t2)
    t, info = srv.run_code(EDIT_MISS)
    check("空跑没过" in t and (proj / "pkg" / "util.py").read_text(encoding="utf-8") == UTIL, "改法原文对不上 → 空跑报错，文件不动", t)
    t, info = srv.run_code("用包 common text code\n" + EDIT)
    check(info["edited"] and info["files"] == ["pkg/util.py"] and NEW in (proj / "pkg" / "util.py").read_text(encoding="utf-8"), "改文件真改", (t, info))
    big = srv.run_code("设 s = 读片段 pkg/util.py:1-6\n" + "打印 " + "字" * 9000 + "\n")[0]
    check(len(big) <= 6100, "输出 ≤ 6000 字（截断）", len(big))
    # JSON-RPC
    r = srv.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    check([x["name"] for x in r["result"]["tools"]] == ["dsl"], "只暴露一个工具 dsl", r)
    check(srv.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None, "通知不回")
    check(SS.env_mode() == "json", "缺省 json")
    os.environ["DSLAGENT_SUBTASK"] = "tool"
    try:
        check(SS.env_mode() == "tool", "DSLAGENT_SUBTASK=tool → tool")
        eng = V._engine_cls()(client=MockClient(default=FINAL, offline=True), workdir=project(), verbose=False, verbs_root=V.VERBS)
        check(eng.subtask_mode == "tool", "v2 引擎 subtask_mode=tool")
        eng.dry_run = True
        eng.sublog = []
        eng.run(MAIN)
        check("状态=成功" in "\n".join(eng.output), "空跑给假结果、不调模型")
    finally:
        os.environ.pop("DSLAGENT_SUBTASK", None)


def t_parallel():
    print("\n七、并行：4 个 MCP 进程各用自己的状态目录，并发读 / 搜不报错")
    import subprocess
    from concurrent.futures import ThreadPoolExecutor
    proj = project()
    base = TMP / "par"
    base.mkdir()

    def one(i):
        st = base / f"s{i}"
        reqs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}]
        for k in range(2, 8):
            code = "设 s = 读片段 pkg/util.py:1-6\n打印 {s}\n" if k % 2 == 0 else "设 h = 搜索代码 clamp\n打印 {h}\n"
            reqs.append({"jsonrpc": "2.0", "id": k, "method": "tools/call", "params": {"name": "dsl", "arguments": {"code": code}}})
        inp = "\n".join(json.dumps(r) for r in reqs) + "\n"
        p = subprocess.run([sys.executable, str(ROOT / "tools" / "dslagent" / "dslmcp.py"), "--workdir", str(proj),
                            "--log", str(base / f"l{i}.jsonl"), "--state", str(st)], input=inp, capture_output=True, text=True, timeout=120)
        outs = [json.loads(x) for x in p.stdout.splitlines() if x.strip()]
        return p.returncode, outs, st

    with ThreadPoolExecutor(4) as ex:
        res = list(ex.map(one, range(4)))
    check(all(rc == 0 for rc, _, _ in res), "4 个进程都正常退出", [r[0] for r in res])
    bad = [o for _, outs, _ in res for o in outs if "error" in o or any(w in o["result"].get("content", [{}])[0].get("text", "")
           for w in ("运行出错", "工具内部出错", "检查不过", "空跑没过"))]
    check(not bad and all(len(o) == 7 for _, o, _ in res), "每个进程 7 条响应、无报错", bad[:2])
    check(len({str(st) for _, _, st in res}) == 4 and all(st.is_dir() for _, _, st in res), "状态目录各自独立", [str(r[2]) for r in res])


def main():
    try:
        t_edit()
        t_fix()
        t_turns_fallback()
        t_invoke()
        t_server()
        t_parallel()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{'=' * 50}\n通过 {PASS}，失败 {FAIL}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
