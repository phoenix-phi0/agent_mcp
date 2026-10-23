# -*- coding: utf-8 -*-
"""问JSON 语句自己支持末尾的「出错时 e」（K15a）。

    cd /workspace/agent_mcp && .venv/bin/python tests/dsl/test_ask_json_on_error.py

背景（K14b）：引擎只在 调用 语句尾部解析 出错时（dsl_service.parse_call_text），
问JSON 语句不剥这个后缀——修改代理照 调用 的样子给 tutor 写了
`问JSON j = … 出错时 ej 格式 delivered:数字`，「出错时 ej」被当提示词发给模型，
失败照旧穿透。现在 _do_ask_json 剥语句末尾的「出错时 <变量>」（tools/dsl_model.py
_split_on_error），接住 ModelOutputError（K14a 引入：JSON 解析失败 / 缺字段 /
类型不对）：e = {code, error}（跟 调用…出错时 同构，码 502），目标变量设成空串；
没出错 e 是空串；DSL 写法错不接；没写「出错时」行为完全不变。

覆盖：
  一、末尾 出错时 + 格式缺字段 → 接住，e.code=502，e.error 原文，j 空
  二、无「格式」解析失败 → 同样接住，发给模型的提示词不再带「出错时」
  三、成功 → e 空串、j 正常，提示词不含「出错时」（带/不带 格式 两条路都查）
  四、没写 出错时 → 照旧抛 ModelOutputError（行为不变，重问次数也不变）
  五、DSL 写法错（格式类型不认识）不接，照旧抛
  六、加载检查拦住「出错时 不在末尾」的写法，正确写法不报
  七、经业务层/接口真调也能接住（与 调用…出错时 同一待遇）
"""

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.dsl import DSLEngine                      # noqa: E402
from tools.dsl_core import ModelOutputError          # noqa: E402
from tools.dslagent.loadcheck import parse_script    # noqa: E402
from tools.dsl_http import Router                    # noqa: E402
from tools.mock import MockClient                    # noqa: E402

SERVICE = """业务 textbook

  公开 函数 抽取 文本
    问JSON r = {文本} 格式 title:文本 出错时 e
    如果 {e} 不为空
      返回 {"handled": true, "code": "{e.code}", "error": "{e.error}"}
    结束
    返回 {r}
  结束

  公开 函数 无格式抽取 文本
    问JSON r = {文本} 出错时 e
    如果 {e} 不为空
      返回 {"handled": true, "code": "{e.code}", "error": "{e.error}"}
    结束
    返回 {r}
  结束
结束
"""

ROUTE = """
接口 POST /textbook/try
  设 r = 调用 textbook.抽取 文本={文本} 出错时 e
  返回 {r}
结束

接口 POST /textbook/raw_try
  设 r = 调用 textbook.无格式抽取 文本={文本} 出错时 e
  返回 {r}
结束
"""

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


def run(script, replies):
    """裸引擎跑一句，回 (引擎, 输出)；异常原样抛给调用方。"""
    eng = DSLEngine(MockClient(replies=replies), verbose=False)
    return eng, eng.run(script)


def make_router(replies):
    ws = Path(tempfile.mkdtemp(prefix="askjson_onerr_"))
    (ws / "services").mkdir()
    (ws / "routes").mkdir()
    (ws / "services" / "textbook.zs").write_text(SERVICE, encoding="utf-8")
    (ws / "routes" / "textbook.zs").write_text(ROUTE, encoding="utf-8")
    router = Router(ws / "routes", ws, ws / "sessions", real=False)
    router.client_factory = lambda: MockClient(replies=replies, offline=True)
    c = router.app().test_client()

    def post(path, **form):
        r = c.post(path, json={"form": form})
        return r.status_code, (r.get_json(silent=True) or {})

    return post


def last_user_text(eng):
    """发给模型的最后一条 user 消息（带 格式 走 chat_messages）。"""
    call = eng.client.calls[-1]
    msgs = call.get("messages") or []
    return next((m["content"] for m in reversed(msgs)
                 if m["role"] == "user"), "")


def main():
    print("一、末尾 出错时 + 格式缺字段：接住，e 同构，j 空")
    eng, out = run("问JSON j = 请判断 格式 delivered:数字 出错时 e\n"
                   "打印 尾|{j}|{e.code}|{e.error}", ["{}"])
    e = eng.vars.get("e")
    check(isinstance(e, dict) and e.get("code") == 502,
          f"e.code = 502：{e}")
    check("问JSON 格式不对" in (e or {}).get("error", "")
          and "缺少字段 delivered" in e["error"],
          f"e.error 含原文：{e['error'][:100]}")
    check("|" in out and out.split("|")[1] == "",
          f"j 是空串，脚本能继续：{out!r}")

    print("二、无「格式」解析失败：同样接住，提示词不带「出错时」")
    eng, _ = run("问JSON j = 请判断 出错时 e", ["这不是JSON"])
    e = eng.vars.get("e")
    check(isinstance(e, dict) and e.get("code") == 502
          and "模型没有返回合法 JSON" in e.get("error", ""),
          f"接住了：{e}")
    check(eng.client.calls and eng.client.calls[0]["prompt"] == "请判断",
          f"发给模型的提示词是「请判断」：{eng.client.calls[0]['prompt']!r}")

    print("三、成功：e 空串、j 正常、提示词不含「出错时」")
    eng, _ = run("问JSON j = 请判断 格式 delivered:数字 出错时 e",
                 ['{"delivered": 1}'])
    check(eng.vars.get("e") == "" and eng.vars["j"] == {"delivered": 1},
          f"e={eng.vars.get('e')!r} j={eng.vars.get('j')!r}")
    check("出错时" not in last_user_text(eng),
          f"提示词不含「出错时」：{last_user_text(eng)[:80]!r}")
    eng, _ = run("问JSON j = 请判断 出错时 e", ['{"delivered": 1}'])
    check(eng.vars.get("e") == "" and eng.vars["j"] == {"delivered": 1},
          f"无格式成功：e={eng.vars.get('e')!r} j={eng.vars.get('j')!r}")
    check(eng.client.calls[0]["prompt"] == "请判断",
          f"无格式提示词不含「出错时」：{eng.client.calls[0]['prompt']!r}")

    print("四、没写 出错时：照旧抛（行为不变，重问次数不变）")
    eng = DSLEngine(MockClient(replies=["{}"]), verbose=False)
    try:
        eng.run("问JSON j = 请判断 格式 delivered:数字\n打印 到不了")
        check(False, f"该抛没抛：vars={eng.vars}")
    except ModelOutputError as err:
        check("问JSON 格式不对" in str(err) and "缺少字段 delivered" in str(err),
              f"照旧抛 ModelOutputError：{str(err)[:80]}")
    check(len(eng.client.calls) == 3, f"重问次数不变（3 次调用）：{len(eng.client.calls)}")
    check("到不了" not in eng.output, "脚本停了")

    print("五、DSL 写法错不接：格式类型不认识照旧抛")
    try:
        eng, _ = run("问JSON j = 请判断 格式 a:不对 出错时 e", [])
        check(False, f"该抛没抛：vars={eng.vars}")
    except Exception as err:  # noqa: BLE001
        check("不认识" in str(err) and not isinstance(err, ModelOutputError),
              f"DSLError 原样抛：{type(err).__name__}: {err}")

    print("六、加载检查：中间位置的 出错时 拦下，末尾的不报")
    msg = parse_script("问JSON j = 请判断 出错时 ej 格式 delivered:数字\n打印 {j}")
    check(msg is not None and "出错时 要写在语句末尾" in msg,
          f"中间位置被拦：{msg}")
    msg = parse_script("问JSON j = 判断 出错时 e 用 快")
    check(msg is not None and "出错时 要写在语句末尾" in msg,
          f"出错时 + 用 也算中间位置，被拦：{msg}")
    check(parse_script("问JSON j = 请判断 格式 delivered:数字 出错时 e") is None,
          "末尾 出错时（带格式）不报")
    check(parse_script("问JSON j = 请判断 出错时 e") is None,
          "末尾 出错时（无格式）不报")

    print("七、经业务层 / 接口真调：与 调用…出错时 同一待遇")
    post = make_router(["{}"])
    st, body = post("/textbook/try", 文本="第一课")
    check(st == 200 and body.get("handled") is True and body.get("code") == "502"
          and "缺少字段 title" in body.get("error", ""),
          f"带格式：{st} {body}")
    post = make_router(["这不是JSON"])
    st, body = post("/textbook/raw_try", 文本="第一课")
    check(st == 200 and body.get("handled") is True and body.get("code") == "502"
          and "模型没有返回合法 JSON" in body.get("error", ""),
          f"无格式：{st} {body}")

    print(f"\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
