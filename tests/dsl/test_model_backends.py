# -*- coding: utf-8 -*-
"""模型名前缀分派：claude:… 走本机 claude -p，zcode 走 zcode -p，其余照旧。

    cd /home/ysc/mcp && .venv/bin/python tests/dsl/test_model_backends.py

不起真的 claude / zcode：临时目录里放两个假程序（CBATCH_CLAUDE、ZCODE_BIN
指过去），每次被调用把收到的参数、cwd、时间写一个 JSON 文件，输出跟真的
同格式的 JSON。行为用环境变量控制（FAKE_REPLY / FAKE_IS_ERROR / FAKE_EXIT /
FAKE_SLEEP），子进程继承 os.environ。

配置用临时的 config.json（ZHIPU_CONFIG 指过去），不读真配置。
"""

import json
import os
import stat
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="model_backends_"))
LOG = TMP / "calls"
LOG.mkdir()
CFG = TMP / "config.json"
CFG.write_text(json.dumps({
    "api_key": "test-not-real",
    "model": "glm-default",
    "models": {"快": "glm-4-flash", "克": "claude:sonnet", "码": "zcode"},
}, ensure_ascii=False), encoding="utf-8")
os.environ["ZHIPU_CONFIG"] = str(CFG)
for k in ("ZHIPU_MODEL", "ZHIPU_API_KEY", "ZHIPU_BASE_URL",
          "DSL_CLAUDE_MAX_PROCS", "DSL_ZCODE_MAX_PROCS",
          "DSL_CLAUDE_TIMEOUT", "DSL_ZCODE_TIMEOUT"):
    os.environ.pop(k, None)

# 假程序：记下参数，按环境变量决定输出
FAKE = r'''#!{py}
import json, os, sys, time, uuid
kind = {kind!r}
t0 = time.time()
args = sys.argv[1:]
if os.environ.get("FAKE_SLEEP"):
    time.sleep(float(os.environ["FAKE_SLEEP"]))
rec = {{"kind": kind, "args": args, "cwd": os.getcwd(),
       "cwd_files": os.listdir("."), "stdin": sys.stdin.read(),
       "has_api_key": "ANTHROPIC_API_KEY" in os.environ,
       "start": t0, "end": time.time()}}
with open(os.path.join({log!r}, uuid.uuid4().hex + ".json"), "w") as f:
    json.dump(rec, f, ensure_ascii=False)
if os.environ.get("FAKE_EXIT"):
    sys.stderr.write("第一行错误\n第二行错误\n")
    sys.exit(int(os.environ["FAKE_EXIT"]))
model = args[args.index("--model") + 1] if "--model" in args else ""
reply = os.environ.get("FAKE_REPLY") or (kind + "[" + model + "]")
if kind == "claude":
    print(json.dumps({{"type": "result", "subtype": "success",
                      "is_error": bool(os.environ.get("FAKE_IS_ERROR")),
                      "result": reply}}, ensure_ascii=False))
else:
    print(json.dumps({{"ok": True, "result": reply}}, ensure_ascii=False))
'''
for kind in ("claude", "zcode"):
    p = TMP / f"fake_{kind}"
    p.write_text(FAKE.format(py=sys.executable, kind=kind, log=str(LOG)),
                 encoding="utf-8")
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
os.environ["CBATCH_CLAUDE"] = str(TMP / "fake_claude")
os.environ["ZCODE_BIN"] = str(TMP / "fake_zcode")
# 假的值，只看它有没有被传给子进程
os.environ["ANTHROPIC_API_KEY"] = "fake-for-test"

from tools import config, DSLEngine, MockClient  # noqa: E402
from agents.base import Agent  # noqa: E402

config.load(reload=True)

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


def calls():
    """取出并清空假程序的调用记录，按开始时间排。"""
    out = []
    for f in LOG.glob("*.json"):
        out.append(json.loads(f.read_text(encoding="utf-8")))
        f.unlink()
    return sorted(out, key=lambda r: r["start"])


def opt(rec, name):
    a = rec["args"]
    return a[a.index(name) + 1] if name in a else None


def engine(mock=None):
    mock = mock or MockClient()
    return DSLEngine(mock, workdir=TMP, verbose=False), mock


def run_err(e, script):
    try:
        e.run(script)
        return ""
    except Exception as ex:  # noqa: BLE001
        return f"{type(ex).__name__}: {ex}"


def fake(**kw):
    for k in ("FAKE_REPLY", "FAKE_IS_ERROR", "FAKE_EXIT", "FAKE_SLEEP"):
        os.environ.pop(k, None)
    for k, v in kw.items():
        os.environ[k] = str(v)


def main():
    fake()
    print("零、对照：不带前缀照旧走内层客户端，不起 claude / zcode")
    e, mock = engine(MockClient(replies=["智谱答"]))
    e.run("问 一 = 你好\n问 二 = 再问 用 快")
    got = [(c["prompt"], c["model"]) for c in mock.calls]
    check(got == [("你好", None), ("再问", "glm-4-flash")]
          and e.vars.get("一") == "智谱答",
          f"内层收到原样的调用：{got}")
    check(calls() == [], "没有起任何外部进程")

    print("\n一、问 … 用 claude:haiku")
    e, mock = engine()
    e.run("问 答 = 只回复两个字：你好 用 claude:haiku")
    rs = calls()
    r = rs[0] if rs else {"args": [], "cwd": "", "cwd_files": [1]}
    check(len(rs) == 1 and not mock.calls, f"起了一次 claude，内层没被调：{len(rs)}")
    check(e.vars.get("答") == "claude[haiku]", f"结果存进变量：{e.vars.get('答')!r}")
    check(opt(r, "--model") == "haiku", f"--model haiku：{opt(r, '--model')!r}")
    check("--tools" in r["args"] and opt(r, "--tools") == "",
          f'--tools "" 在参数里：{opt(r, "--tools")!r}')
    check("--strict-mcp-config" in r["args"]
          and opt(r, "--output-format") == "json"
          and opt(r, "-p") == "只回复两个字：你好",
          f"纯问答参数齐全：{r['args'][:4]}")
    check(bool(opt(r, "--system-prompt")),
          "没写「系统」也换掉了默认系统提示词")
    check(r["cwd_files"] == [] and not r["cwd"].startswith(str(ROOT))
          and not Path(r["cwd"]).exists(),
          f"在空的临时目录里跑，跑完删掉：{r['cwd']}")
    check(r["stdin"] == "" and r["has_api_key"] is False,
          "标准输入是空的，ANTHROPIC_API_KEY 没传给子进程")

    print("\n二、别名映射到 claude；系统提示词传过去")
    e, mock = engine()
    e.run("系统 你是日语老师\n问 答 = 讲讲は和が 用 克")
    rs = calls()
    check(len(rs) == 1 and opt(rs[0], "--model") == "sonnet"
          and opt(rs[0], "--system-prompt") == "你是日语老师" and not mock.calls,
          f"克 → claude:sonnet，系统提示词照传："
          f"{[(opt(x, '--model'), opt(x, '--system-prompt')) for x in rs]}")

    print("\n三、模型 claude:sonnet 之后都走 claude，用 X 仍可临时换回智谱")
    e, mock = engine()
    e.run("模型 claude:sonnet\n问 一 = 甲\n问 二 = 乙\n流式 三 = 丙\n"
          "问 四 = 丁 用 快\n问 五 = 戊")
    rs = calls()
    check([(opt(x, "-p"), opt(x, "--model")) for x in rs]
          == [("甲", "sonnet"), ("乙", "sonnet"), ("丙", "sonnet"),
              ("戊", "sonnet")],
          f"四次走 claude：{[(opt(x, '-p'), opt(x, '--model')) for x in rs]}")
    check([(c["prompt"], c["model"]) for c in mock.calls]
          == [("丁", "glm-4-flash")], f"「用 快」那次走内层：{mock.calls[:1]}")
    check(e.vars.get("三") == "claude[sonnet]",
          f"流式降级成一次性返回：{e.vars.get('三')!r}")

    print("\n四、问JSON：要求只输出 JSON，剥代码围栏")
    fake(FAKE_REPLY='```json\n{"意图": "出题", "数量": 3}\n```')
    e, mock = engine()
    e.run("问JSON 决策 = 提取意图 用 claude:haiku\n打印 {决策.意图}")
    rs = calls()
    check(e.vars.get("决策") == {"意图": "出题", "数量": 3},
          f"解析成结构：{e.vars.get('决策')!r}")
    check(rs and "只输出 JSON" in opt(rs[0], "-p"),
          f"提示词里加了要求：{opt(rs[0], '-p')[-30:] if rs else None}")
    fake(FAKE_REPLY="我不知道")
    err = run_err(engine()[0], "问JSON 决策 = 提取 用 claude:haiku")
    calls()
    check("合法 JSON" in err, f"不是 JSON 就报错：{err[:80]}")
    fake()

    print("\n五、对话：历史拼成文本，标明用户/助手")
    e, mock = engine()
    e.run("模型 claude:haiku\n对话 一 = 第一句\n对话 二 = 第二句")
    rs = calls()
    p2 = opt(rs[1], "-p") if len(rs) == 2 else ""
    check(len(rs) == 2 and opt(rs[0], "-p") == "第一句",
          f"第一轮只发这一句：{opt(rs[0], '-p') if rs else None!r}")
    check("用户：第一句" in p2 and "助手：claude[haiku]" in p2
          and p2.rstrip().endswith("用户：第二句"),
          f"第二轮带上历史：{p2[-60:]!r}")
    check(len(e.history) >= 4 and e.history[-1]["content"] == "claude[haiku]",
          f"历史照常追加：{len(e.history)} 条")

    print("\n六、带工具 + claude：报清楚的错，不起进程")
    from tools.dsl import make_verbs
    reg = make_verbs()

    @reg.verb("统计题数")
    def 题目数(课程: str = "") -> str:
        return "57"

    e = DSLEngine(MockClient(), workdir=TMP, verbose=False, verbs=reg)
    err = run_err(e, "问 答 = 有几道题 带工具 题目数 用 claude:haiku")
    check("不支持" in err and "带工具" in err and "智谱" in err,
          f"错误说清楚了：{err[:80]}")
    check(calls() == [], "没起 claude")
    e = DSLEngine(MockClient(replies=["57 道"]), workdir=TMP, verbose=False,
                  verbs=reg)
    e.run("问 答 = 有几道题 带工具 题目数")
    check(e.vars.get("答") == "57 道", "对照：不带前缀的带工具照常")

    print("\n七、claude 报错")
    fake(FAKE_IS_ERROR=1, FAKE_REPLY="额度用完了")
    err = run_err(engine()[0], "问 答 = x 用 claude:haiku")
    check("claude 报错" in err and "额度用完了" in err, f"is_error：{err[:80]}")
    fake(FAKE_EXIT=2)
    err = run_err(engine()[0], "问 答 = x 用 claude:haiku")
    check("退出码 2" in err and "第一行错误" in err,
          f"退出码非 0，带 stderr：{err[:100]!r}")
    fake()
    os.environ["CBATCH_CLAUDE"] = str(TMP / "没有这个程序")
    err = run_err(engine()[0], "问 答 = x 用 claude:haiku")
    os.environ["CBATCH_CLAUDE"] = str(TMP / "fake_claude")
    check("找不到 claude" in err, f"程序不存在：{err[:80]}")
    fake(FAKE_SLEEP=3)
    os.environ["DSL_CLAUDE_TIMEOUT"] = "1"
    t0 = time.time()
    err = run_err(engine()[0], "问 答 = x 用 claude:haiku")
    os.environ.pop("DSL_CLAUDE_TIMEOUT")
    check("超过 1 秒" in err and time.time() - t0 < 2.5,
          f"超时可配置：{err[:60]}（{time.time() - t0:.1f}s）")
    fake()
    calls()

    print("\n八、zcode")
    e, mock = engine()
    e.run("系统 简短回答\n问 一 = 甲 用 zcode\n问 二 = 乙 用 zcode:随便\n"
          "问 三 = 丙 用 码")
    rs = calls()
    check([x["kind"] for x in rs] == ["zcode"] * 3 and not mock.calls,
          f"三次都走 zcode：{[x['kind'] for x in rs]}")
    check(e.vars.get("一") == "zcode[]", f"结果：{e.vars.get('一')!r}")
    a = rs[0]["args"] if rs else []
    check("--json" in a and "-p" in a and "--disallowedTools" in a
          and all(t in a for t in ("Bash", "Edit", "Write", "Read"))
          and "--model" not in a,
          f"禁掉内置工具、要 JSON、不传模型：{a[:6]}")
    check(rs and opt(rs[0], "-p").startswith("简短回答")
          and rs[0]["cwd_files"] == [],
          "系统提示词拼在提示词前面，空目录里跑")
    os.environ["ZCODE_BIN"] = str(TMP / "没有这个程序")
    err = run_err(engine()[0], "问 答 = x 用 zcode")
    os.environ["ZCODE_BIN"] = str(TMP / "fake_zcode")
    check("找不到 zcode" in err, f"程序不存在：{err[:60]}")

    print("\n九、信号量：并发 4 个，同时运行不超过 2 个")
    fake(FAKE_SLEEP=0.6)
    errs = []

    def worker(i):
        try:
            DSLEngine(MockClient(), workdir=TMP, verbose=False).run(
                f"问 x = 并发{i} 用 claude:haiku")
        except Exception as ex:  # noqa: BLE001
            errs.append(ex)

    ts = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    fake()
    rs = calls()
    peak = max(sum(1 for y in rs if y["start"] < x["end"] and x["start"] < y["end"])
               for x in rs) if rs else 0
    check(not errs and len(rs) == 4, f"4 次都跑完：{len(rs)} 异常 {errs[:1]}")
    check(peak == 2, f"同时运行最多 2 个（也确实并行了）：{peak}")

    print("\n十、Agent(model=claude:…)")
    soul = TMP / "soul.md"
    soul.write_text("你是测试用的 agent。", encoding="utf-8")
    mock = MockClient(replies=["嗯"])
    a = Agent(soul=soul, workspace=TMP / "ws", client=mock, model="claude:haiku")
    reply = a.send("你好")
    rs = calls()
    check(reply == "claude[haiku]" and len(rs) == 1 and not mock.calls,
          f"不带工具的 agent 走 claude：{reply!r}")
    check(rs and "你是测试用的 agent" in opt(rs[0], "--system-prompt"),
          "SOUL 当系统提示词传过去")
    mock = MockClient(replies=["嗯"])
    a = Agent(soul=soul, workspace=TMP / "ws2", client=mock)
    check(a.send("你好") == "嗯" and mock.last_model is None and calls() == [],
          "对照：不传 model 的 agent 照旧走内层")

    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
