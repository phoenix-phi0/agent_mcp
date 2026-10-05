# -*- coding: utf-8 -*-
"""模型档位：models.json 的 tiers / aliases / default，config.json 旧别名兼容。

    cd /home/ysc/mcp && .venv/bin/python tests/dsl/test_model_tiers.py

每一节在新的临时目录里写 config.json 和 models.json（ZHIPU_CONFIG 指过去，
models.json 按「跟 config.json 同目录」的规则被找到），不读真配置。
智谱客户端不发真请求：requests.post 换成假的，只记下发出去的 model。
claude 用假程序（CBATCH_CLAUDE 指过去），同 test_model_backends.py。
"""

import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="model_tiers_"))
LOG = TMP / "calls"
LOG.mkdir()
for k in ("ZHIPU_MODEL", "ZHIPU_API_KEY", "ZHIPU_BASE_URL", "ZHIPU_MODELS",
          "DSL_CLAUDE_MAX_PROCS", "DSL_CLAUDE_TIMEOUT", "JP_DATA_DIR"):
    os.environ.pop(k, None)
os.environ["ZHIPU_CONFIG"] = str(TMP / "none" / "config.json")

FAKE_CLAUDE = r'''#!{py}
import json, os, sys, uuid
args = sys.argv[1:]
with open(os.path.join({log!r}, uuid.uuid4().hex + ".json"), "w") as f:
    json.dump({{"args": args}}, f)
model = args[args.index("--model") + 1] if "--model" in args else ""
print(json.dumps({{"type": "result", "subtype": "success", "is_error": False,
                  "result": "claude[" + model + "]"}}))
'''
fake = TMP / "fake_claude"
fake.write_text(FAKE_CLAUDE.format(py=sys.executable, log=str(LOG)),
                encoding="utf-8")
fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
os.environ["CBATCH_CLAUDE"] = str(fake)

from tools import config, DSLEngine, MockClient  # noqa: E402
from tools import zhipu  # noqa: E402
from tools.llm_router import wrap  # noqa: E402
from agents.base import Agent  # noqa: E402

KEY = "test-not-real"
TIERS = {"快": "glm-fast", "平衡": "glm-mid", "强": "glm-strong"}

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
    os.environ.pop("ZHIPU_MODELS", None)
    return config.load(reload=True), d


def load_err():
    try:
        config.load(reload=True)
        return ""
    except Exception as ex:  # noqa: BLE001
        return f"{type(ex).__name__}: {ex}"


# 假的 requests.post：记下发给智谱的 model
SENT = []


class _Resp:
    status_code = 200

    def json(self):
        return {"choices": [{"message": {"role": "assistant",
                                         "content": "好"}}], "usage": {}}


def _fake_post(url, headers=None, json=None, timeout=None):
    SENT.append(json.get("model"))
    return _Resp()


zhipu.requests.post = _fake_post


def zp():
    """套了路由的智谱客户端（DSLEngine / Agent 里实际用的就是这样）。"""
    SENT.clear()
    return wrap(zhipu.ZhipuClient(api_key=KEY))


def engine(client=None):
    client = client or MockClient()
    return DSLEngine(client, workdir=TMP, verbose=False), client


def claude_calls():
    out = []
    for f in LOG.glob("*.json"):
        out.append(json.loads(f.read_text(encoding="utf-8")))
        f.unlink()
    return out


def opt(rec, name):
    a = rec["args"]
    return a[a.index(name) + 1] if name in a else None


def main():
    soul = TMP / "soul.md"
    soul.write_text("你是测试助手。", encoding="utf-8")

    print("零、对照：不写模型，加 models.json 前后行为不变")
    setup({"model": "glm-default"})
    c = zp()
    c.chat("你好")
    before = list(SENT)
    setup({"model": "glm-default"}, {"default": "强", "tiers": TIERS})
    c = zp()
    c.chat("你好")
    check(before == ["glm-default"] and SENT == ["glm-default"],
          f"config.json 写了 model：加 models.json 前 {before}、后 {SENT}，"
          f"default 档位不起作用")
    e, mock = engine(MockClient(replies=["好的"]))
    e.run("问 答 = 你好")
    check(e.vars.get("答") == "好的" and mock.calls[0]["model"] is None,
          f"DSL 不写模型：交给客户端的 model={mock.calls[0]['model']!r}")
    e, _ = engine(zp())
    e.run("问 答 = 你好")
    check(SENT == ["glm-default"], f"DSL 不写模型实际发出：{SENT}")
    check(config.resolve_model("glm-4-air") == "glm-4-air"
          and config.resolve_model("") is None
          and config.resolve_model(None) is None,
          "不认识的名字原样返回，空返回 None")

    print("\n一、档位解析：模型 快 / 用 强 / Agent(model=平衡)")
    check([config.resolve_model(t) for t in ("快", "平衡", "强")]
          == ["glm-fast", "glm-mid", "glm-strong"]
          and config.resolve_model(" 强 ") == "glm-strong",
          "resolve_model 认三个档位（两边空格去掉）")
    e, _ = engine(zp())
    e.run("模型 快\n问 甲 = 一\n问 乙 = 二")
    check(SENT == ["glm-fast", "glm-fast"], f"模型 快：{SENT}")
    e, _ = engine(zp())
    e.run("问 甲 = 一 用 强\n问 乙 = 二")
    check(SENT == ["glm-strong", "glm-default"],
          f"用 强 只管这一次：{SENT}")
    e, mock = engine()
    e.run("问 甲 = 一 用 平衡")
    check(mock.prompts == ["一"] and mock.calls[0]["model"] == "glm-mid",
          f"用 平衡 从提示词里剥掉：{mock.prompts} {mock.calls[0]['model']!r}")
    e, mock = engine()
    e.run("问 甲 = 请 用 中文")
    check(mock.prompts == ["请 用 中文"] and mock.calls[0]["model"] is None,
          f"用 中文 不是档位，留在提示词里：{mock.prompts}")
    c = zp()
    Agent(soul=soul, workspace=TMP / "ws", client=c, model="平衡").send("你好")
    check(SENT == ["glm-mid"], f"Agent(model=平衡) 实际发出：{SENT}")
    c = zp()
    Agent(soul=soul, workspace=TMP / "ws", client=c).send("你好")
    check(SENT == ["glm-default"], f"Agent 不写模型：{SENT}")

    print("\n二、别名指向档位（只解析一层）")
    setup({"model": "glm-default"},
          {"tiers": TIERS, "aliases": {"大": "强", "便宜": "glm-cheap",
                                       "套娃": "大"}})
    check(config.resolve_model("大") == "glm-strong", "别名 大 → 强 → glm-strong")
    check(config.resolve_model("便宜") == "glm-cheap", "别名直接指向真名")
    check(config.resolve_model("套娃") == "强",
          f"只解析一层：套娃 → 大 → 强，停在「强」（{config.resolve_model('套娃')!r}）")
    e, _ = engine(zp())
    e.run("问 甲 = 一 用 大")
    check(SENT == ["glm-strong"], f"用 大：{SENT}")

    print("\n三、档位指向 claude:xxx 时经路由走 claude")
    setup({"model": "glm-default"},
          {"tiers": {**TIERS, "强": "claude:opus"},
           "aliases": {"克": "强"}})
    claude_calls()
    e, _ = engine(zp())
    e.run("问 甲 = 一 用 强")
    got = claude_calls()
    check(e.vars.get("甲") == "claude[opus]" and SENT == []
          and len(got) == 1 and opt(got[0], "--model") == "opus",
          f"用 强 → claude --model opus：{e.vars.get('甲')!r} 智谱={SENT}")
    e, _ = engine(zp())
    e.run("模型 克\n问 甲 = 一")
    got = claude_calls()
    check(e.vars.get("甲") == "claude[opus]" and len(got) == 1,
          f"模型 克（别名 → 档位 → claude:opus）：{e.vars.get('甲')!r}")
    a = Agent(soul=soul, workspace=TMP / "ws", client=zp(), model="强")
    check(a.send("你好") == "claude[opus]" and SENT == [],
          "Agent(model=强) 不带工具时走 claude")
    claude_calls()
    try:
        zp().chat_raw([{"role": "user", "content": "x"}], model="强",
                      tools=[{"type": "function",
                              "function": {"name": "f", "parameters": {}}}])
        err = ""
    except Exception as ex:  # noqa: BLE001
        err = str(ex)
    check("不支持「带工具」" in err, f"claude 档位带工具报错：{err[:60]}")
    # default 档位是 claude 且 config.json 没写 model：不写模型也走 claude
    setup({}, {"default": "强", "tiers": {**TIERS, "强": "claude:sonnet"}})
    check(config.get("model") == "claude:sonnet",
          f"client 默认模型 = default 档位：{config.get('model')!r}")
    e, _ = engine(zp())
    e.run("问 甲 = 一\n问 乙 = 二 用 快")
    got = claude_calls()
    check(e.vars.get("甲") == "claude[sonnet]" and len(got) == 1
          and SENT == ["glm-fast"],
          f"不写模型走 claude、用 快 走智谱：{e.vars.get('甲')!r} 智谱={SENT}")

    print("\n四、models.json 不存在：退回内置默认，不报错")
    cfg, d = setup({})
    check(not cfg["_models_found"] and cfg["tiers"] == {}
          and cfg["model"] == config.BUILTIN_MODEL,
          f"没有 models.json、config.json 没写 model：默认 {cfg['model']!r}")
    check(config.resolve_model("快") == "快", "没有档位时「快」原样返回")
    e, mock = engine()
    e.run("问 甲 = 写一句 用 快")
    check(mock.prompts == ["写一句 用 快"],
          f"没有档位时「用 快」留在提示词里：{mock.prompts}")
    c = zp()
    c.chat("x")
    check(SENT == [config.BUILTIN_MODEL], f"实际发出：{SENT}")
    cfg, _ = setup(None)
    check(not cfg["_found"] and not cfg["_models_found"]
          and cfg["model"] == config.BUILTIN_MODEL,
          "config.json 和 models.json 都没有也不报错")

    print("\n五、models.json 格式坏了：报错，指出文件和哪里不对")
    bad_cases = [
        ("不是 JSON", '{"tiers": {"快": "a",}', "格式错误"),
        ("最外层是列表", "[1, 2]", "最外层"),
        ("tiers 不是对象", {"tiers": ["快"]}, "tiers 应该是对象"),
        ("值不是字符串", {"tiers": {"快": 1}}, "非空字符串"),
        ("值是空串", {"tiers": {"快": " "}}, "非空字符串"),
        ("default 不是档位", {"default": "超强", "tiers": TIERS}, "超强"),
        ("档位和别名重名", {"tiers": TIERS, "aliases": {"快": "x"}}, "重名"),
        ("键写错", {"tier": TIERS}, "不认识的键"),
    ]
    for label, content, want in bad_cases:
        _, d = setup({"model": "m"}, "{}")
        (d / "models.json").write_text(
            content if isinstance(content, str)
            else json.dumps(content, ensure_ascii=False), encoding="utf-8")
        err = load_err()
        check("ValueError" in err and want in err
              and str(d / "models.json") in err,
              f"{label}：{err[:90]}")
    setup({"model": "m"}, {"_note": ["注释"], "tiers": TIERS})
    check(config.resolve_model("快") == "glm-fast", "_ 开头的键当注释，不报错")

    print("\n六、config.json 旧的 models 别名表兼容")
    setup({"model": "glm-default",
           "models": {"旧": "glm-old", "快": "glm-legacy-fast", "旧强": "强"}})
    check(config.resolve_model("快") == "glm-legacy-fast"
          and config.resolve_model("旧") == "glm-old",
          "没有 models.json 时旧别名照用")
    setup({"model": "glm-default",
           "models": {"旧": "glm-old", "快": "glm-legacy-fast", "旧强": "强"}},
          {"tiers": TIERS})
    check(config.resolve_model("旧") == "glm-old", "旧别名跟 models.json 合并")
    check(config.resolve_model("快") == "glm-fast",
          "重名时 models.json 的档位优先")
    check(config.resolve_model("旧强") == "glm-strong", "旧别名指向档位")
    e, _ = engine(zp())
    e.run("问 甲 = 一 用 旧")
    check(SENT == ["glm-old"], f"用 旧：{SENT}")

    print("\n七、默认模型优先级")
    setup({}, {"default": "强", "tiers": TIERS})
    check(config.get("model") == "glm-strong",
          f"config.json 没写 model：用 default 档位 {config.get('model')!r}")
    os.environ["ZHIPU_MODEL"] = "快"
    config.load(reload=True)
    check(config.get("model") == "glm-fast",
          f"ZHIPU_MODEL=快 盖过 default 档位并解析：{config.get('model')!r}")
    os.environ.pop("ZHIPU_MODEL")
    setup({"model": "平衡"}, {"default": "强", "tiers": TIERS})
    check(config.get("model") == "glm-mid",
          f"config.json 的 model 写档位名也认：{config.get('model')!r}")
    SENT.clear()
    zhipu.ZhipuClient(api_key=KEY, model="快").chat("x")
    zhipu.ZhipuClient(api_key=KEY, model="快").chat("x", model="强")
    check(SENT == ["glm-fast", "glm-strong"],
          f"ZhipuClient(model=快) 解析档位、显式参数优先：{SENT}")

    print("\n八、ZHIPU_MODELS 指定别的文件")
    _, d = setup({"model": "m"}, {"tiers": TIERS})
    other = d / "other.json"
    other.write_text(json.dumps({"tiers": {"快": "glm-other"}},
                                ensure_ascii=False), encoding="utf-8")
    os.environ["ZHIPU_MODELS"] = str(other)
    config.load(reload=True)
    check(config.resolve_model("快") == "glm-other"
          and config.resolve_model("强") == "强",
          "ZHIPU_MODELS 盖过 config.json 同目录的 models.json")
    os.environ.pop("ZHIPU_MODELS")

    print("\n九、python -m tools.config 打印档位表，不打印 key")
    _, d = setup({"model": "glm-default", "models": {"旧": "glm-old"}},
                 {"default": "平衡", "tiers": TIERS,
                  "aliases": {"大": "强", "克": "claude:sonnet"}})
    env = dict(os.environ)
    p = subprocess.run([sys.executable, "-m", "tools.config"], cwd=ROOT,
                       env=env, capture_output=True, text=True,
                       encoding="utf-8")
    out = p.stdout
    check(p.returncode == 0 and "快 → glm-fast" in out
          and "平衡 → glm-mid  ← default" in out
          and "大 → 强（= glm-strong）" in out and "旧 → glm-old" in out
          and "以 config.json 为准" in out,
          "档位、别名、default、config.json 优先的提示都打出来了")
    check(KEY not in out and "已设置" in out, "key 只说有没有，不打印")
    if p.returncode != 0 or "快 → glm-fast" not in out:
        print(out, p.stderr[-500:])

    print("\n十、项目根真的 models.json 能读（三档都在、default 是档位）")
    os.environ["ZHIPU_MODELS"] = str(ROOT / "models.json")
    cfg = config.load(reload=True)
    check(set(cfg["tiers"]) == {"快", "平衡", "强"}
          and cfg["default_tier"] in cfg["tiers"],
          f"models.json：{cfg['tiers']} default={cfg['default_tier']}")
    os.environ.pop("ZHIPU_MODELS")

    print(f"\n通过 {passed}，失败 {failed}")
    return failed


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
