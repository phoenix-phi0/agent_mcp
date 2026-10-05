# -*- coding: utf-8 -*-
"""DSL 的模型可选：「模型 X」、「问 … 用 X」、config.json 的 models 别名、Agent(model=)。

    cd /home/ysc/mcp && .venv/bin/python tests/dsl/test_model_select.py

早先「模型 X」直接改 client.model。客户端是子脚本、动词子引擎、agent、
HTTP 服务的并发请求共用的，一个脚本写了「模型 快」，别的脚本、别的请求
也跟着换了模型，而且不报错。现在模型记在引擎上（跟「温度」一样），每次
调用传给客户端，client.model 不动。

配置用临时的 config.json（ZHIPU_CONFIG 指过去），不读真配置。
"""

import json
import os
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="model_select_"))
CFG = TMP / "config.json"
CFG.write_text(json.dumps({
    "api_key": "test-not-real",
    "model": "glm-default",
    "models": {"快": "glm-4-flash", "强": "glm-4.6"},
}, ensure_ascii=False), encoding="utf-8")
os.environ["ZHIPU_CONFIG"] = str(CFG)
for k in ("ZHIPU_MODEL", "ZHIPU_API_KEY", "ZHIPU_BASE_URL"):
    os.environ.pop(k, None)

from tools import config, DSLEngine, MockClient, ZhipuClient  # noqa: E402
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


def engine(mock=None):
    mock = mock or MockClient()
    return DSLEngine(mock, workdir=TMP, verbose=False), mock


def models_of(mock):
    """每次对话调用的 (提示词, model)。"""
    return [(c.get("prompt") or c["messages"][-1]["content"], c.get("model"))
            for c in mock.calls if c["type"] in ("chat", "chat_messages",
                                                 "stream")]


def main():
    print("零、对照：不写模型，问照常能用")
    e, mock = engine(MockClient(replies=["好的"]))
    e.run("问 答 = 你好\n打印 {答}")
    check(e.vars.get("答") == "好的" and mock.prompts == ["你好"],
          f"问 能用：答={e.vars.get('答')!r} 提示词={mock.prompts}")
    check(mock.last_model is None and mock.calls[0]["model"] is None,
          f"不写模型时客户端收到 None（用它自己的默认）：{mock.last_model!r}")
    check(mock.model == "mock-model", "client.model 没被动")

    print("\n一、config 别名解析")
    check(config.resolve_model("快") == "glm-4-flash", "别名 快 → glm-4-flash")
    check(config.resolve_model("glm-4-air") == "glm-4-air", "不是别名原样返回")
    check(config.resolve_model("") is None and config.resolve_model(None) is None,
          "空 → None")
    check(config.resolve_model(" 强 ") == "glm-4.6", "两边空格去掉再查")

    print("\n二、ZhipuClient：model= 进 payload，不传还是默认")
    zc = ZhipuClient()
    sent = []
    zc._post = lambda path, payload: (sent.append(payload) or
        {"choices": [{"message": {"role": "assistant", "content": "{}"}}]})
    zc.chat("x")
    check(sent[-1]["model"] == "glm-default", f"不传：{sent[-1]['model']}")
    zc.chat("x", model="快")
    check(sent[-1]["model"] == "glm-4-flash", f"chat 别名：{sent[-1]['model']}")
    zc.chat_raw([{"role": "user", "content": "x"}], model="强")
    check(sent[-1]["model"] == "glm-4.6", f"chat_raw：{sent[-1]['model']}")
    zc.chat_json("x", model="glm-4-air")
    check(sent[-1]["model"] == "glm-4-air", f"chat_json 真名：{sent[-1]['model']}")
    zc.chat_raw([{"role": "user", "content": "x"}])
    check(sent[-1]["model"] == "glm-default" and zc.model == "glm-default",
          "用过别的模型之后，不传仍是默认，client.model 没变")

    print("\n三、「模型 快」让后面的问收到解析后的名字")
    e, mock = engine()
    e.run("问 一 = 前\n模型 快\n问 二 = 后\n对话 三 = 聊")
    got = models_of(mock)
    check(got == [("前", None), ("后", "glm-4-flash"), ("聊", "glm-4-flash")],
          f"设之前 None，之后 glm-4-flash：{got}")
    check(mock.model == "mock-model", f"client.model 没被改：{mock.model}")
    e2, _ = engine(mock)
    mock.reset()
    e2.run("问 四 = 另一个脚本")
    check(mock.last_model is None,
          f"同一个客户端上的另一个脚本不受影响：{mock.last_model!r}")

    print("\n四、子脚本里的「模型」不影响父脚本")
    (TMP / "sub.zs").write_text("问 子一 = 子前\n模型 强\n问 子二 = 子后\n",
                                encoding="utf-8")
    e, mock = engine()
    e.run("模型 快\n执行 sub.zs\n问 父 = 父后")
    got = models_of(mock)
    check(got == [("子前", "glm-4-flash"), ("子后", "glm-4.6"),
                  ("父后", "glm-4-flash")],
          f"子脚本继承父的模型、改了只管自己，父还是快：{got}")
    check(e.model == "glm-4-flash" and mock.model == "mock-model",
          f"父引擎 {e.model}，client.model {mock.model}")

    print("\n五、「问 … 用 X」只管这一次")
    e, mock = engine()
    e.run("问 一 = 甲 用 强\n问 二 = 乙\n模型 快\n问 三 = 丙 用 glm-4-air\n问 四 = 丁")
    got = models_of(mock)
    check(got == [("甲", "glm-4.6"), ("乙", None), ("丙", "glm-4-air"),
                  ("丁", "glm-4-flash")],
          f"后缀剥掉、只这一次生效，之后回到引擎上的模型：{got}")
    e, mock = engine()
    e.run("问 一 = 请 用 中文\n问 二 = 怎么用 这个词\n问 三 = 这个 用 法")
    got = models_of(mock)
    check(got == [("请 用 中文", None), ("怎么用 这个词", None),
                  ("这个 用 法", None)],
          f"提示词里正常的「用」不误伤：{got}")
    e, mock = engine(MockClient(replies=["没有", "有答案"]))
    e.run("问 一 = 甲 重试 3 次 直到 包含 答案 用 快")
    got = models_of(mock)
    check(got == [("甲", "glm-4-flash"), ("甲", "glm-4-flash")]
          and e.vars.get("一") == "有答案",
          f"跟重试一起用，每次重试都用这个模型：{got}")
    e, mock = engine()
    e.run("设 m = 强\n问 一 = 甲 用 {m}")
    check(models_of(mock) == [("甲", "glm-4.6")], f"用 {{变量}}：{models_of(mock)}")
    e, mock = engine()
    try:
        out = e.run("问 一 = 甲 用 {没定义}")
    except Exception as ex:  # noqa: BLE001
        out = str(ex)
    check(not mock.calls and "没有定义" in out,
          f"变量没定义就报错，不把「{{没定义}}」当模型名发出去：{out.strip()[:60]}")

    print("\n六、并发：两个脚本共用一个客户端，各用各的模型")
    mock = MockClient()
    errs = []

    def worker(alias, tag):
        try:
            for i in range(30):
                DSLEngine(mock, workdir=TMP, verbose=False).run(
                    f"模型 {alias}\n问 x = {tag}{i}")
        except Exception as ex:  # noqa: BLE001
            errs.append(ex)

    ts = [threading.Thread(target=worker, args=("快", "甲")),
          threading.Thread(target=worker, args=("强", "乙"))]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    wrong = [(p, m) for p, m in models_of(mock)
             if m != {"甲": "glm-4-flash", "乙": "glm-4.6"}[p[0]]]
    check(not errs and len(mock.calls) == 60 and not wrong,
          f"60 次调用没有串线：错 {wrong[:3]} 异常 {errs[:1]}")

    print("\n七、Agent(model=)")
    soul = TMP / "soul.md"
    soul.write_text("你是测试用的 agent。", encoding="utf-8")
    mock = MockClient(replies=["嗯"])
    Agent(soul=soul, workspace=TMP / "ws", client=mock).send("你好")
    check(mock.last_model is None, f"不传 model：客户端收到 None：{mock.last_model!r}")
    mock = MockClient(replies=["嗯"])
    a = Agent(soul=soul, workspace=TMP / "ws", client=mock, model="快")
    check(a.send("你好") == "嗯" and mock.last_model == "快",
          f"Agent(model=快) 传到客户端：{mock.last_model!r}")
    check(mock.model == "mock-model", "client.model 没被改")
    from agents.japanese import make_teacher
    mock = MockClient(replies=["嗯"])
    make_teacher(client=mock, workspace=TMP / "jp", with_flows=False,
                 model="强").send("你好")
    check(mock.last_model == "强", f"make_teacher 透传 model：{mock.last_model!r}")
    from agents.web import make_builder
    mock = MockClient(replies=["嗯"])
    make_builder(client=mock, workspace=TMP / "web", model="glm-4-air").send("你好")
    check(mock.last_model == "glm-4-air",
          f"make_builder 透传 model：{mock.last_model!r}")

    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
