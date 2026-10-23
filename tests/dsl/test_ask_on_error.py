# -*- coding: utf-8 -*-
"""「问」语句原生支持末尾的「出错时 e」（K22a）。

    cd /workspace/agent_mcp && .venv/bin/python tests/dsl/test_ask_on_error.py

背景（K21）：tutor 的自由文本回复/总结要按约定在模型调用失败时回 400，只能把
「问」改成「问JSON … 格式 reply:文本 出错时 qe」——让模型把长回复塞进 JSON，
易出格式问题、多耗重问。根因：「问」没有「出错时」写法。现在 _do_ask 剥语句
末尾的「出错时 <变量>」（复用 K15a 的 _split_on_error，只认末尾），接住
ModelOutputError 族（K20 起含 ModelCallError，模型调用本身失败，码 503）：
e = {code, error}（跟 调用…出错时 的 e 同构），目标变量设成空串；没出错 e 是
空串；DSL 写法错、编程错误不接；没写「出错时」行为完全不变（照旧抛，
model_call 标记还在，接口层 502 + 一句人话）。

覆盖：
  一、末尾 出错时 + 服务失败（RuntimeError）→ 接住，e.code=503、r 空
  二、超时（TimeoutError）→ 同样接住
  三、带模型后缀（用 快 出错时 e，出错时在最末尾）→ 同样接住
  四、成功 → e 空串、r 正常，发给模型的提示词不含「出错时」
  五、没写 出错时 → 照旧抛，接口 502 + 一句人话（行为不变）
  六、写法错不接：出错时 写在中间（后面还跟 用）→ 照旧 502，成功时提示词里
      含「出错时 e」；变量名非法（出错时 1x）不剥，照旧 502
  七、编程错误不接：问接住后 计算 "abc" + 1 的 TypeError 穿透，照旧 500
  八、加载检查拦「出错时 不在末尾」的写法，末尾写法与提示词正文不误报
"""

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.dslagent.loadcheck import parse_script    # noqa: E402
from tools.dsl_http import Router                    # noqa: E402
from tools.mock import MockClient                    # noqa: E402

SERVICE = """业务 tutor

  公开 函数 试 文本
    问 r = 讲一讲：{文本} 出错时 e
    如果 {e} 不为空
      返回 {"handled": "是", "code": "{e.code}", "error": "{e.error}", "r": "{r}"}
    结束
    返回 {"handled": "否", "r": "{r}"}
  结束

  公开 函数 带档 文本
    问 r = {文本} 用 快 出错时 e
    如果 {e} 不为空
      返回 {"handled": "是", "code": "{e.code}", "error": "{e.error}", "r": "{r}"}
    结束
    返回 {"handled": "否", "r": "{r}"}
  结束

  公开 函数 普通 文本
    问 r = 讲一讲：{文本}
    返回 {r}
  结束

  公开 函数 中间 文本
    问 r = {文本} 出错时 e 用 快
    返回 {"r": "{r}"}
  结束

  公开 函数 非法名 文本
    问 r = {文本} 出错时 1x
    返回 {r}
  结束

  公开 函数 会炸 文本
    问 r = {文本} 出错时 e
    设 n = 计算 {文本} + 1
    返回 {"n": "{n}"}
  结束
结束
"""

ROUTE = """
接口 POST /tutor/try
  设 r = 调用 tutor.试 文本={文本}
  返回 {r}
结束

接口 POST /tutor/tier_try
  设 r = 调用 tutor.带档 文本={文本}
  返回 {r}
结束

接口 POST /tutor/plain
  设 r = 调用 tutor.普通 文本={文本}
  返回 {r}
结束

接口 POST /tutor/mid
  设 r = 调用 tutor.中间 文本={文本}
  返回 {r}
结束

接口 POST /tutor/badname
  设 r = 调用 tutor.非法名 文本={文本}
  返回 {r}
结束

接口 POST /tutor/dslerr
  设 r = 调用 tutor.会炸 文本={文本}
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


def make_router(bomb=None):
    """bomb：假客户端每次被调都抛的异常；None 则正常回「好的回复」并记录提示词。"""
    seen = []

    def handler(prompt, system):
        seen.append(prompt)
        if bomb is not None:
            raise bomb
        return "好的回复"

    ws = Path(tempfile.mkdtemp(prefix="k22a_"))
    (ws / "services").mkdir()
    (ws / "routes").mkdir()
    (ws / "services" / "tutor.zs").write_text(SERVICE, encoding="utf-8")
    (ws / "routes" / "tutor.zs").write_text(ROUTE, encoding="utf-8")
    router = Router(ws / "routes", ws, ws / "sessions", real=False)
    router.client_factory = lambda: MockClient(handler=handler, offline=True)
    c = router.app().test_client()

    def post(path, **form):
        r = c.post(path, json={"form": form})
        return r.status_code, (r.get_json(silent=True) or {}), r.get_data(as_text=True)

    return post, seen


def main():
    print("一、末尾 出错时 + 服务失败（RuntimeError）：接住 code=503、r 空")
    post, _ = make_router(RuntimeError("智谱接口返回 503: Service Unavailable"))
    st, body, _ = post("/tutor/try", 文本="第一课")
    check(st == 200 and body.get("handled") == "是", f"接住了：{st} {body}")
    check(body.get("code") == "503", f"e.code 是 503：{body.get('code')}")
    check("模型调用失败" in body.get("error", "") and "503" in body.get("error", ""),
          f"e.error 带前缀和原文：{body.get('error', '')[:120]}")
    check(body.get("r") == "", f"r 是空串：{body.get('r')!r}")

    print("二、超时（TimeoutError）：同样接住")
    post, _ = make_router(TimeoutError("Read timed out. (read timeout=90)"))
    st, body, _ = post("/tutor/try", 文本="第一课")
    check(st == 200 and body.get("handled") == "是" and body.get("code") == "503",
          f"TimeoutError 接住：{st} {body}")

    print("三、带模型后缀（用 快 出错时 e，出错时在最末尾）：同样接住")
    post, _ = make_router(RuntimeError("智谱接口返回 429: Rate limit exceeded"))
    st, body, _ = post("/tutor/tier_try", 文本="第一课")
    check(st == 200 and body.get("handled") == "是" and body.get("code") == "503",
          f"带「用 快」也接住：{st} {body}")

    print("四、成功：e 空串、r 正常、提示词不含「出错时」")
    post, seen = make_router()
    st, body, _ = post("/tutor/try", 文本="第一课")
    check(st == 200 and body.get("handled") == "否" and body.get("r") == "好的回复",
          f"正常回复：{st} {body}")
    check(seen == ["讲一讲：第一课"],
          f"发给模型的提示词不含「出错时」：{seen}")
    st, body, _ = post("/tutor/tier_try", 文本="第二课")
    check(st == 200 and body.get("handled") == "否" and body.get("r") == "好的回复",
          f"带「用 快」的正常回复：{st} {body}")

    print("五、没写 出错时：照旧抛，接口 502 + 一句人话（行为不变）")
    post, _ = make_router(RuntimeError("智谱接口返回 429: Rate limit"))
    st, body, _ = post("/tutor/plain", 文本="第一课")
    check(st == 502, f"照旧 502：{st}")
    check("模型这次没有回应" in body.get("error", ""), f"一句人话还在：{body}")

    print("六、写法错不接：出错时 写在中间 / 变量名非法")
    post, seen = make_router(RuntimeError("智谱接口返回 503: Service Unavailable"))
    st, body, _ = post("/tutor/mid", 文本="第一课")
    check(st == 502, f"中间位置的 出错时 不接、照旧 502：{st}")
    st, body, _ = post("/tutor/badname", 文本="第一课")
    check(st == 502, f"变量名非法（出错时 1x）不剥、照旧 502：{st}")
    post, seen = make_router()
    st, body, _ = post("/tutor/mid", 文本="第一课")
    check(st == 200 and seen and "出错时 e" in seen[0],
          f"中间位置的 出错时 进了提示词：prompt={seen}")

    print("七、编程错误不接：接住问之后 计算 \"abc\" + 1 的 TypeError 穿透")
    post, _ = make_router(RuntimeError("智谱接口返回 503: Service Unavailable"))
    st, body, text = post("/tutor/dslerr", 文本="abc")
    check(st == 500, f"TypeError 穿透 出错时：{st}")
    check("不是数字" in text, f"报错是计算那句：{text[:160]}")

    print("八、加载检查：中间位置拦下，末尾与提示词正文不报")
    msg = parse_script("问 r = 请讲 出错时 e 用 快\n打印 {r}")
    check(msg is not None and "问 的 出错时 要写在语句末尾" in msg,
          f"中间位置（出错时 e 用 快）被拦：{msg}")
    msg = parse_script("问 r = 请讲 出错时 e 附 a.md\n打印 {r}")
    check(msg is not None and "问 的 出错时 要写在语句末尾" in msg,
          f"中间位置（出错时 e 附）被拦：{msg}")
    check(parse_script("问 r = 请讲 出错时 e\n打印 {r}") is None,
          "末尾 出错时 不报")
    check(parse_script("问 r = 请讲 用 快 出错时 e\n打印 {r}") is None,
          "带模型后缀、出错时在末尾 不报")
    check(parse_script("问 r = 请在出错时 通知 我们重试\n打印 {r}") is None,
          "提示词正文含「出错时」不误报")

    print(f"\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
