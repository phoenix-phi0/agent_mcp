# -*- coding: utf-8 -*-
"""模型名的通道：api:zhipu/… / api:anthropic/… / cli:claude/… / cli:zcode。

    cd /home/ysc/mcp && .venv/bin/python tests/dsl/test_model_channels.py

覆盖 config.parse_model、能力表（config.BACKENDS）、路由按 (通道, 提供方)
分派、档位 fallback、models.json 新格式校验、python -m tools.config 的输出。

不起真的 claude / zcode：假程序同 test_model_backends.py（CBATCH_CLAUDE、
ZCODE_BIN 指过去，每次调用记一个 JSON 文件）。智谱不发真请求：
requests.post 换成假的，只记下发出去的 model。配置在临时目录里，不读真配置。
"""

import json
import logging
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="model_channels_"))
LOG = TMP / "calls"
LOG.mkdir()
for k in ("ZHIPU_MODEL", "ZHIPU_API_KEY", "ZHIPU_BASE_URL", "ZHIPU_MODELS",
          "DSL_CLAUDE_MAX_PROCS", "DSL_ZCODE_MAX_PROCS", "DSL_CLAUDE_TIMEOUT",
          "DSL_ZCODE_TIMEOUT", "JP_DATA_DIR"):
    os.environ.pop(k, None)
os.environ["ZHIPU_CONFIG"] = str(TMP / "none" / "config.json")

FAKE = r'''#!{py}
import json, os, sys, time, uuid
kind = {kind!r}
args = sys.argv[1:]
with open(os.path.join({log!r}, uuid.uuid4().hex + ".json"), "w") as f:
    json.dump({{"kind": kind, "args": args, "t": time.time()}}, f,
              ensure_ascii=False)
model = args[args.index("--model") + 1] if "--model" in args else ""
reply = kind + "[" + model + "]"
if kind == "claude":
    print(json.dumps({{"type": "result", "subtype": "success",
                      "is_error": False, "result": reply}}))
else:
    print(json.dumps({{"ok": True, "result": reply}}))
'''
for kind in ("claude", "zcode"):
    p = TMP / f"fake_{kind}"
    p.write_text(FAKE.format(py=sys.executable, kind=kind, log=str(LOG)),
                 encoding="utf-8")
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
os.environ["CBATCH_CLAUDE"] = str(TMP / "fake_claude")
os.environ["ZCODE_BIN"] = str(TMP / "fake_zcode")

from tools import config, DSLEngine, MockClient  # noqa: E402
from tools import zhipu  # noqa: E402
from tools.dsl import make_verbs  # noqa: E402
from tools.llm_router import wrap  # noqa: E402
from agents.base import Agent  # noqa: E402
from agents.registry import Registry  # noqa: E402

KEY = "test-not-real"

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


_n = 0


def setup(cfg=None, models=None):
    """新目录里写 config.json / models.json（None 不写，str 原样写），重新加载。"""
    global _n
    _n += 1
    d = TMP / f"c{_n}"
    d.mkdir()
    if cfg is not None:
        (d / "config.json").write_text(
            json.dumps({"api_key": KEY, **cfg}, ensure_ascii=False),
            encoding="utf-8")
    if models is not None:
        (d / "models.json").write_text(
            models if isinstance(models, str)
            else json.dumps(models, ensure_ascii=False), encoding="utf-8")
    os.environ["ZHIPU_CONFIG"] = str(d / "config.json")
    return config.load(reload=True), d


def err_of(fn):
    try:
        fn()
        return ""
    except Exception as ex:  # noqa: BLE001
        return f"{type(ex).__name__}: {ex}"


# 假的 requests.post：记下发给智谱的 model
SENT = []


class _Resp:
    status_code = 200

    def json(self):
        return {"choices": [{"message": {"role": "assistant",
                                         "content": "智谱答"}}], "usage": {}}


def _fake_post(url, headers=None, json=None, timeout=None, **kw):
    SENT.append(json.get("model"))
    return _Resp()


zhipu.requests.post = _fake_post


def zp(**kw):
    SENT.clear()
    return wrap(zhipu.ZhipuClient(api_key=KEY, **kw))


def calls():
    out = []
    for f in LOG.glob("*.json"):
        out.append(json.loads(f.read_text(encoding="utf-8")))
        f.unlink()
    return sorted(out, key=lambda r: r["t"])


def opt(rec, name):
    a = rec["args"]
    return a[a.index(name) + 1] if name in a else None


# 路由的 warning 日志收集起来看
class _Grab(logging.Handler):
    def __init__(self):
        super().__init__()
        self.lines = []

    def emit(self, record):
        self.lines.append(record.getMessage())


GRAB = _Grab()
logging.getLogger("tools.llm_router").addHandler(GRAB)

# 「带工具」用的动词
REG = make_verbs()


@REG.verb("统计题数")
def 题目数(课程: str = "") -> str:
    return "57"


def engine(client=None):
    client = client or MockClient()
    return DSLEngine(client, workdir=TMP, verbose=False, verbs=REG), client


TOOLS = [{"type": "function", "function": {"name": "f", "parameters": {}}}]
MSGS = [{"role": "user", "content": "x"}]


def main():
    soul = TMP / "soul.md"
    soul.write_text("你是测试助手。", encoding="utf-8")
    setup({"model": "glm-default"},
          {"tiers": {"快": "glm-fast", "平衡": "api:zhipu/glm-mid"},
           "aliases": {"克": "claude:sonnet", "码": "zcode"}})

    print("零、对照：裸名、旧写法行为不变")
    e, mock = engine(MockClient(replies=["好"]))
    e.run("问 一 = 甲\n问 二 = 乙 用 快\n问 三 = 丙 用 glm-4-air")
    check([c["model"] for c in mock.calls] == [None, "glm-fast", "glm-4-air"],
          f"不写 / 档位裸名 / 真名，内层收到的跟以前一样："
          f"{[c['model'] for c in mock.calls]}")
    mock = MockClient(replies=["嗯"])
    Agent(soul=soul, workspace=TMP / "ws", client=mock, model="快").send("你好")
    check(mock.last_model == "快",
          f"Agent(model=快)（档位是裸名）内层照旧收到原名：{mock.last_model!r}")
    e, mock = engine()
    e.run("问 一 = 甲 用 claude:haiku\n问 二 = 乙 用 克\n问 三 = 丙 用 zcode:随便"
          "\n问 四 = 丁 用 码")
    rs = calls()
    check([(r["kind"], opt(r, "--model")) for r in rs]
          == [("claude", "haiku"), ("claude", "sonnet"), ("zcode", None),
              ("zcode", None)] and not mock.calls,
          f"旧写法 claude:… / zcode / zcode:xx 照旧走 CLI："
          f"{[(r['kind'], opt(r, '--model')) for r in rs]}")
    c = zp()
    c.chat("x")
    c.chat("x", model="快")
    check(SENT == ["glm-default", "glm-fast"], f"智谱实际发出：{SENT}")

    print("\n一、parse_model：各种写法")
    P = config.parse_model
    cases = [
        ("glm-5.3", ("api", "zhipu", "glm-5.3", True), "api:zhipu/glm-5.3"),
        ("api:zhipu/glm-5.3", ("api", "zhipu", "glm-5.3", False),
         "api:zhipu/glm-5.3"),
        (" api:zhipu/glm-5.3 ", ("api", "zhipu", "glm-5.3", False),
         "api:zhipu/glm-5.3"),
        ("api:anthropic/claude-x", ("api", "anthropic", "claude-x", False),
         "api:anthropic/claude-x"),
        ("cli:claude/sonnet", ("cli", "claude", "sonnet", False),
         "cli:claude/sonnet"),
        ("cli:claude", ("cli", "claude", "", False), "cli:claude"),
        ("cli:zcode", ("cli", "zcode", "", False), "cli:zcode"),
        ("claude:haiku", ("cli", "claude", "haiku", True), "cli:claude/haiku"),
        ("cli:claude/sonnet@low", ("cli", "claude", "sonnet@low", False),
         "cli:claude/sonnet@low"),
        ("claude:opus@max", ("cli", "claude", "opus@max", True),
         "cli:claude/opus@max"),
        ("claude", ("cli", "claude", "", True), "cli:claude"),
        ("zcode", ("cli", "zcode", "", True), "cli:zcode"),
        ("zcode:随便", ("cli", "zcode", "", True), "cli:zcode"),
    ]
    for raw, want, canon in cases:
        s = P(raw)
        check((s.channel, s.provider, s.model, s.legacy) == want
              and s.canonical == canon and s.raw == raw.strip(),
              f"{raw!r} → {s.canonical}（legacy={s.legacy}）")

    print("\n二、parse_model：非法输入报清楚的错")
    bad = [
        ("foo:bar", "不认识的通道「foo」"),
        ("api:", "缺提供方"),
        ("api:/glm-5.3", "缺提供方"),
        ("cli:/sonnet", "缺提供方"),
        ("api:openai/gpt", "没有提供方「openai」"),
        ("cli:gemini", "没有提供方「gemini」"),
        ("api:zhipu", "要写模型"),
        ("api:zhipu/", "缺模型名"),
        ("cli:zcode/glm-5", "不能选模型"),
        ("cli:claude/sonnet@fast", "努力程度「fast」不认识"),
        ("cli:claude/sonnet@", "努力程度「」不认识"),
        ("cli:claude/@low", "「@」前面要写模型"),
        ("api:zhipu/glm-5.3@low", "只有 cli:claude 能写"),
        ("glm-5.3@low", "只有 cli:claude 能写"),
        ("", "不能是空的"),
        (None, "不能是空的"),
    ]
    for raw, want in bad:
        err = err_of(lambda: P(raw))
        check("ModelNameError" in err and want in err,
              f"{raw!r}：{err[:80]}")
    check(issubclass(config.ModelNameError, ValueError),
          "ModelNameError 是 ValueError")

    print("\n三、规范名分派到正确的后端")
    e, mock = engine(MockClient(replies=["智谱"]))
    e.run("问 一 = 甲 用 api:zhipu/glm-x\n问 二 = 乙 用 平衡")
    check([c["model"] for c in mock.calls] == ["glm-x", "glm-mid"]
          and calls() == [],
          f"api:zhipu/… 交给内层，传的是去掉前缀的模型名："
          f"{[c['model'] for c in mock.calls]}")
    e, mock = engine()
    e.run("问 一 = 甲 用 cli:claude/haiku\n问 二 = 乙 用 cli:claude\n"
          "问 三 = 丙 用 cli:zcode")
    rs = calls()
    check([(r["kind"], opt(r, "--model")) for r in rs]
          == [("claude", "haiku"), ("claude", None), ("zcode", None)]
          and not mock.calls
          and e.vars.get("一") == "claude[haiku]"
          and e.vars.get("三") == "zcode[]",
          f"cli:claude/haiku、cli:claude（不传 --model）、cli:zcode："
          f"{[(r['kind'], opt(r, '--model')) for r in rs]}")
    check(all(opt(r, "--effort") is None for r in rs), "没写 @ 就不带 --effort")
    e, mock = engine()
    e.run("问 一 = 甲 用 cli:claude/sonnet@low\n问 二 = 乙 用 claude:opus@max")
    rs = calls()
    check([(opt(r, "--model"), opt(r, "--effort")) for r in rs]
          == [("sonnet", "low"), ("opus", "max")] and not mock.calls,
          f"@ 拆成 --model 和 --effort："
          f"{[(opt(r, '--model'), opt(r, '--effort')) for r in rs]}")
    e, mock = engine()
    e.run("模型 cli:claude/opus\n问 一 = 甲\n问 二 = 乙 用 api:zhipu/glm-y")
    rs = calls()
    check(len(rs) == 1 and opt(rs[0], "--model") == "opus"
          and [c["model"] for c in mock.calls] == ["glm-y"],
          "模型 cli:claude/opus 之后走 claude，用 api:zhipu/… 临时换回")
    e, mock = engine()
    err = err_of(lambda: e.run("问 一 = 甲 用 cli:zcode/glm-5"))
    check("不能选模型" in err and calls() == [] and not mock.calls,
          f"cli:zcode/xx 报错，不起进程：{err[:70]}")
    err = err_of(lambda: engine()[0].run("问 一 = 甲 用 api:anthropic/claude-x"))
    check("api:anthropic 还没接入" in err and calls() == [],
          f"api:anthropic 调用时报错：{err[:70]}")
    err = err_of(lambda: engine()[0].run("问 一 = 甲 用 foo:bar"))
    check("不认识的通道" in err, f"用 foo:bar 报错：{err[:70]}")
    c = zp()
    c.chat("x", model="api:zhipu/glm-z")
    check(SENT == ["glm-z"], f"ZhipuClient 收到规范名发出去的是 glm-z：{SENT}")
    err = err_of(lambda: zhipu.ZhipuClient(api_key=KEY).chat(
        "x", model="cli:claude/haiku"))
    check("不是智谱模型" in err and "cli:claude/haiku" in err,
          f"没套路由的 ZhipuClient 收到 cli 名字报错：{err[:70]}")
    mock = MockClient()
    a = Agent(soul=soul, workspace=TMP / "ws", client=mock,
              model="cli:claude/haiku")
    check(a.send("你好") == "claude[haiku]" and not mock.calls
          and len(calls()) == 1, "Agent(model=cli:claude/haiku) 走 claude")

    print("\n四、能力表")
    check(config.BACKENDS[("api", "zhipu")].caps
          == {"tools": "yes", "stream": "yes"}
          and config.BACKENDS[("cli", "claude")].caps
          == {"tools": "no", "stream": "degraded"}
          and config.BACKENDS[("cli", "zcode")].caps
          == {"tools": "no", "stream": "degraded"}
          and not config.BACKENDS[("api", "anthropic")].ready,
          "api 带工具/真流式，cli 不带工具/流式降级，anthropic 未接入")
    for name in ("cli:claude/haiku", "claude:haiku", "cli:zcode"):
        err = err_of(lambda: wrap(MockClient()).chat_raw(MSGS, model=name,
                                                          tools=TOOLS))
        canon = config.parse_model(name).canonical
        check("CapabilityError" in err and canon in err and "带工具" in err
              and "fallback" in err and "api" in err,
              f"{name} 带工具报错，有规范名、能力、办法：{err[:90]}")
    check(calls() == [], "没起进程")
    e, mock = engine()
    err = err_of(lambda: e.run("问 答 = 有几道题 带工具 题目数 用 cli:claude/haiku"))
    check("cli:claude/haiku" in err and "带工具" in err and calls() == [],
          f"DSL「带工具」+ cli：{err[:80]}")
    e, mock = engine(MockClient(replies=["57 道"]))
    e.run("问 答 = 有几道题 带工具 题目数 用 api:zhipu/glm-t")
    check(e.vars.get("答") == "57 道" and mock.last_model == "glm-t",
          "对照：api 通道带工具照常")
    e, mock = engine()
    e.run("流式 一 = 甲 用 cli:claude/haiku\n流式 二 = 乙 用 cli:zcode")
    rs = calls()
    check(e.vars.get("一") == "claude[haiku]" and e.vars.get("二") == "zcode[]"
          and len(rs) == 2 and not GRAB.lines,
          f"cli 流式降级成一次性返回，不报错：{e.vars.get('一')!r}")
    e, mock = engine(MockClient(replies=["流"]))
    e.run("流式 一 = 甲 用 平衡")
    check(e.vars.get("一") == "流" and mock.calls[0]["type"] == "stream"
          and mock.calls[0]["model"] == "glm-mid",
          "api 流式交给内层的 stream")

    print("\n五、档位 fallback")
    _, d = setup({"model": "glm-default"},
                 {"tiers": {"快": "glm-fast",
                            "强": {"model": "cli:claude/haiku",
                                   "fallback": "api:zhipu/glm-fb"},
                            "裸": "cli:claude/sonnet",
                            "坏": {"model": "cli:claude/opus",
                                   "fallback": "cli:zcode"},
                            "远": {"model": "cli:claude/opus",
                                   "fallback": "api:anthropic/claude-x"}},
                  "aliases": {"大": "强", "直": "cli:claude/haiku"}})
    GRAB.lines.clear()
    e, mock = engine(MockClient(replies=["57 道"]))
    e.run("问 答 = 有几道题 带工具 题目数 用 强")
    check(e.vars.get("答") == "57 道" and mock.last_model == "glm-fb"
          and calls() == [],
          f"带工具：改用 fallback，内层收到 glm-fb：{mock.last_model!r}")
    line = GRAB.lines[0] if GRAB.lines else ""
    check("强" in line and "cli:claude/haiku" in line
          and "api:zhipu/glm-fb" in line and "带工具" in line,
          f"记了 warning：{line}")
    GRAB.lines.clear()
    e, mock = engine()
    e.run("问 答 = 你好 用 强")
    rs = calls()
    check(e.vars.get("答") == "claude[haiku]" and len(rs) == 1
          and not mock.calls and not GRAB.lines,
          "不带工具：仍走主模型 claude，不记日志")
    e, mock = engine()
    e.run("流式 答 = 你好 用 强")
    check(e.vars.get("答") == "claude[haiku]" and len(calls()) == 1
          and not GRAB.lines, "流式只是降级，不触发 fallback")
    e, mock = engine(MockClient(replies=["57 道"]))
    e.run("模型 强\n问 答 = 有几道题 带工具 题目数\n问 二 = 你好")
    rs = calls()
    check(mock.last_model == "glm-fb" and e.vars.get("二") == "claude[haiku]"
          and len(rs) == 1,
          "「模型 强」之后：带工具那句走 fallback，普通的仍走 claude")
    GRAB.lines.clear()
    e, mock = engine(MockClient(replies=["57 道"]))
    e.run("问 答 = 有几道题 带工具 题目数 用 大")
    check(mock.last_model == "glm-fb" and GRAB.lines and "强" in GRAB.lines[0],
          f"别名 大 → 档位 强，继承 fallback：{mock.last_model!r}")
    e, mock = engine()
    e.run("设 m = 大\n问 答 = 你好 用 {m}")
    check(e.vars.get("答") == "claude[haiku]" and len(calls()) == 1,
          "别名不带工具仍走主模型")
    err = err_of(lambda: engine()[0].run("问 答 = 题 带工具 题目数 用 直"))
    check("cli:claude/haiku" in err and "带工具" in err,
          f"别名直接指向模型（不是档位）没有 fallback，照样报错：{err[:60]}")
    err = err_of(lambda: engine()[0].run("问 答 = 题 带工具 题目数 用 裸"))
    check("cli:claude/sonnet" in err and "带工具" in err
          and "没写 fallback" in err,
          f"档位没写 fallback：直接报错：{err[:90]}")
    err = err_of(lambda: engine()[0].run("问 答 = 题 带工具 题目数 用 坏"))
    check("cli:zcode" in err and "也不支持" in err and "坏" in err,
          f"fallback 自己也不能带工具：报错：{err[:100]}")
    err = err_of(lambda: engine()[0].run("问 答 = 题 带工具 题目数 用 远"))
    check("api:anthropic 还没接入" in err, f"fallback 没接入：{err[:70]}")
    check(calls() == [], "以上报错的都没起进程")
    # Agent 带工具走 fallback
    reg = Registry()

    @reg.tool("加一")
    def add_one(n: str) -> str:
        return str(int(n) + 1)

    GRAB.lines.clear()
    mock = MockClient(replies=["好"])
    a = Agent(soul=soul, workspace=TMP / "ws", client=mock, tools=reg,
              model="强")
    check(a.send("你好") == "好" and mock.last_model == "glm-fb"
          and calls() == [] and GRAB.lines,
          f"Agent(model=强) 带工具：改用 fallback：{mock.last_model!r}")
    mock = MockClient(replies=["好"])
    a = Agent(soul=soul, workspace=TMP / "ws", client=mock, model="强")
    check(a.send("你好") == "claude[haiku]" and len(calls()) == 1,
          "Agent(model=强) 不带工具：走 claude")
    # default 档位带 fallback：不写模型也继承
    setup({}, {"default": "强",
               "tiers": {"强": {"model": "cli:claude/haiku",
                                "fallback": "api:zhipu/glm-fb"}}})
    GRAB.lines.clear()
    e, _ = engine(zp())
    e.run("问 一 = 你好\n问 二 = 有几道题 带工具 题目数")
    rs = calls()
    check(e.vars.get("一") == "claude[haiku]" and len(rs) == 1
          and SENT == ["glm-fb"] and GRAB.lines,
          f"default 档位：不写模型走 claude，带工具改用 fallback：智谱={SENT}")

    print("\n六、models.json 新格式校验")
    bad_cases = [
        ("对象缺 model", {"tiers": {"强": {"fallback": "glm-5.3"}}},
         "要有 model"),
        ("对象 model 空", {"tiers": {"强": {"model": " "}}}, "要有 model"),
        ("fallback 空", {"tiers": {"强": {"model": "cli:claude",
                                          "fallback": ""}}}, "fallback 得是"),
        ("fallback 不是字符串", {"tiers": {"强": {"model": "cli:claude",
                                                "fallback": 3}}},
         "fallback 得是"),
        ("fallback 非法", {"tiers": {"强": {"model": "cli:claude",
                                            "fallback": "foo:bar"}}},
         "不认识的通道"),
        ("fallback 写档位名", {"tiers": {"快": "glm-fast",
                                       "强": {"model": "cli:claude",
                                              "fallback": "快"}}},
         "不能写档位或别名"),
        ("对象里多余的键", {"tiers": {"强": {"model": "cli:claude",
                                             "fallbak": "glm-5.3"}}},
         "不认识的键"),
        ("别名写对象", {"tiers": {}, "aliases": {"克": {"model": "cli:claude"}}},
         "别名只能写字符串"),
        ("档位值非法", {"tiers": {"快": "cli:zcode/glm"}}, "不能选模型"),
        ("别名值非法", {"aliases": {"克": "api:zhipu"}}, "要写模型"),
    ]
    for label, content, want in bad_cases:
        _, d = setup({"model": "m"}, "{}")
        (d / "models.json").write_text(json.dumps(content, ensure_ascii=False),
                                       encoding="utf-8")
        err = err_of(lambda: config.load(reload=True))
        check("ValueError" in err and want in err
              and str(d / "models.json") in err, f"{label}：{err[-70:]}")
    cfg, _ = setup({"model": "m"},
                   {"tiers": {"强": {"model": "cli:claude/opus",
                                     "fallback": "glm-5.3", "_说明": "注释"}}})
    check(cfg["tiers"] == {"强": "cli:claude/opus"}
          and cfg["tier_fallbacks"] == {"强": "glm-5.3"}
          and config.resolve_model("强") == "cli:claude/opus"
          and config.resolve_model("强").tier == "强",
          "对象写法：tiers 里是模型名，fallback 单独一张表，_ 开头当注释")

    print("\n七、python -m tools.config")
    setup({"model": "glm-default"},
          {"default": "平衡",
           "tiers": {"快": "api:zhipu/glm-fast", "平衡": "glm-mid",
                     "强": {"model": "cli:claude/opus",
                            "fallback": "api:zhipu/glm-strong"}},
           "aliases": {"克": "claude:sonnet", "码": "zcode:随便", "大": "强",
                       "z": "cli:zcode"}})
    p = subprocess.run([sys.executable, "-m", "tools.config"], cwd=ROOT,
                       env=dict(os.environ), capture_output=True, text=True,
                       encoding="utf-8")
    out = p.stdout
    lines = out.splitlines()

    def after(head):
        """「head」那行的下一行（详情行）。"""
        for i, x in enumerate(lines):
            if x.strip().startswith(head):
                return lines[i + 1] if i + 1 < len(lines) else ""
        return ""

    check(p.returncode == 0 and "api:zhipu/glm-fast · API · 带工具：能 · 流式：真"
          in after("快 →"), f"api 档位：{after('快 →').strip()}")
    check("（裸名，等于 api:zhipu/glm-mid）" in after("平衡 →"),
          f"裸名档位：{after('平衡 →').strip()}")
    check("cli:claude/opus · CLI · 带工具：不能 · 流式：降级" in after("强 →")
          and "fallback（主模型缺能力时改用）：api:zhipu/glm-strong" in out,
          "cli 档位 + fallback 都打出来了")
    check("旧写法，建议改成 cli:claude/sonnet" in after("克 →")
          and "旧写法，后半忽略，建议改成 cli:zcode" in after("码 →"),
          f"旧写法有提示：{after('克 →').strip()}")
    check("fallback（继承档位「强」）" in out, "别名指向档位：显示继承的 fallback")
    check("旧写法" not in after("z →") and "cli:zcode · CLI" in after("z →"),
          "规范名不标旧写法")
    check(KEY not in out and "已设置" in out, "不打印 key")
    if p.returncode != 0:
        print(out, p.stderr[-500:])

    print("\n八、项目根的 models.json：全是规范名")
    os.environ["ZHIPU_MODELS"] = str(ROOT / "models.json")
    cfg = config.load(reload=True)
    names = {**cfg["tiers"], **{k: v for k, v in cfg["aliases"].items()
                                if cfg["_alias_from"].get(k) == "models.json"}}
    specs = {k: config.parse_model(v) for k, v in names.items()}
    check(all(not s.legacy and s.raw == s.canonical for s in specs.values()),
          f"没有旧写法：{names}")
    check(specs["快"].canonical == "cli:claude/haiku"
          and specs["平衡"].canonical == "cli:claude/sonnet"
          and specs["强"].canonical == "cli:claude/opus"
          and specs["克"].canonical == "cli:claude/sonnet"
          and specs["克快"].canonical == "cli:claude/sonnet@low"
          and specs["克强"].canonical == "cli:claude/opus"
          and specs["z"].canonical == "cli:zcode"
          and cfg["default_tier"] == "平衡",
          "三档和克/克快/克强/z 都走 cli")
    # 三档走 claude，带工具时得有地方接：每档配一个智谱模型做 fallback
    check(cfg["tier_fallbacks"] == {"快": "api:zhipu/glm-5.3-flashx",
                               "平衡": "api:zhipu/glm-5.3-flash",
                               "强": "api:zhipu/glm-5.3"},
          f"三档各有智谱 fallback：{cfg.get('tier_fallbacks')}")
    os.environ.pop("ZHIPU_MODELS")

    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
