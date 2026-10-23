# -*- coding: utf-8 -*-
"""「出错时」要能接住模型输出错误：问JSON 返回的内容不合格（缺字段、不是合法
JSON）时，调用语句带「出错时 e」的业务层能接住；DSL 写法错误仍然不接。

    cd /workspace/agent_mcp && .venv/bin/python tests/dsl/test_on_error_model_output.py

背景（K13 audit：textbook_import 的处理块想把「模型回得不对」标成失败可重试，
实际整个任务被标失败）：原来 出错时 只接得住 BizError（报错 4xx）和错误链上有
ClientError 的错误，问JSON 的「格式不对」是普通 DSLError，会穿过 出错时 直接炸。
现在这类错误抛 ModelOutputError（DSLError 的子类，tools/dsl_core.py），业务层
分类时单独认它（tools/dsl_service.py _do_service_call）。

覆盖（业务层经 HTTP 接口真调，模型用 MockClient）：
  一、问JSON 带「格式」缺字段 → 出错时 接住，e.error 含原文，e.code = 502
  二、问JSON 不带「格式」解析失败 → 同样接住
  三、隔一层调用（函数调函数，内层没写出错时）也能接住（错误链上找）
  四、报错 4xx 照旧接住；成功时 e 是空串、正常返回
  五、DSL 写法错误（计算里不是数字）不被接住，照旧 500
  六、不接的行为没变：没写 出错时 的问JSON 格式错仍是 500 + 脚本出错
"""

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.dsl_http import Router                    # noqa: E402
from tools.mock import MockClient                    # noqa: E402

SERVICE = """业务 textbook

  公开 函数 抽取 文本
    问JSON r = {文本} 格式 title:文本 points:列表
    返回 {r}
  结束

  公开 函数 抽取原文 文本
    问JSON r = {文本}
    返回 {r}
  结束

  公开 函数 处理 文本
    设 r = 调用 textbook.抽取 文本={文本}
    返回 {r}
  结束

  公开 函数 会炸 文本
    设 n = 计算 {文本} + 1
    返回 {"n": "{n}"}
  结束

  公开 函数 拒绝 文本
    报错 429 太快了
  结束
结束
"""

ROUTE = """
# 模型输出不合格要能被 出错时 接住
接口 POST /textbook/try
  设 r = 调用 textbook.抽取 文本={文本} 出错时 e
  如果 {e} 不为空
    返回 {"handled": true, "code": "{e.code}", "error": "{e.error}"}
  结束
  返回 {r}
结束

接口 POST /textbook/raw_try
  设 r = 调用 textbook.抽取原文 文本={文本} 出错时 e
  如果 {e} 不为空
    返回 {"handled": true, "code": "{e.code}", "error": "{e.error}"}
  结束
  返回 {r}
结束

接口 POST /textbook/deep_try
  设 r = 调用 textbook.处理 文本={文本} 出错时 e
  如果 {e} 不为空
    返回 {"handled": true, "code": "{e.code}", "error": "{e.error}"}
  结束
  返回 {r}
结束

接口 POST /textbook/biz_try
  设 r = 调用 textbook.拒绝 文本={文本} 出错时 e
  如果 {e} 不为空
    返回 {"handled": true, "code": "{e.code}", "error": "{e.error}"}
  结束
  返回 {r}
结束

接口 POST /textbook/dslerr_try
  设 r = 调用 textbook.会炸 文本={文本} 出错时 e
  如果 {e} 不为空
    返回 {"handled": true, "code": "{e.code}", "error": "{e.error}"}
  结束
  返回 {r}
结束

# 没写 出错时：问JSON 格式错照旧 500（行为不该变）
接口 POST /textbook/plain
  设 r = 调用 textbook.抽取 文本={文本}
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


def make_router(replies):
    ws = Path(tempfile.mkdtemp(prefix="onerr_"))
    (ws / "services").mkdir()
    (ws / "routes").mkdir()
    (ws / "services" / "textbook.zs").write_text(SERVICE, encoding="utf-8")
    (ws / "routes" / "textbook.zs").write_text(ROUTE, encoding="utf-8")
    router = Router(ws / "routes", ws, ws / "sessions", real=False)
    router.client_factory = lambda: MockClient(replies=replies, offline=True)
    c = router.app().test_client()

    def post(path, **form):
        r = c.post(path, json={"form": form})
        return r.status_code, (r.get_json(silent=True) or {}), r.get_data(as_text=True)

    return post


def main():
    print("一、问JSON 带「格式」缺字段：被 出错时 接住")
    # {} 缺 title 和 points；默认重问 2 次（共问 3 次）后报错
    post = make_router(["{}"])
    st, body, _ = post("/textbook/try", 文本="第一课")
    err = body.get("error", "")
    check(st == 200 and body.get("handled") is True, f"接住了：{st} {body}")
    check(body.get("code") == "502", f"code 是 502：{body.get('code')}")
    check("问JSON 格式不对" in err and "缺少字段 title" in err
          and "缺少字段 points" in err, f"e.error 含原文：{err[:120]}")
    check("最后一次回复：{}" in err, f"e.error 带最后一次回复：{err[-60:]}")

    print("二、问JSON 不带「格式」解析失败：同样接住")
    post = make_router(["这不是JSON"])
    st, body, _ = post("/textbook/raw_try", 文本="第一课")
    err = body.get("error", "")
    check(st == 200 and body.get("handled") is True and body.get("code") == "502",
          f"接住了：{st} {body}")
    check("模型没有返回合法 JSON" in err, f"e.error 含原文：{err[:120]}")

    print("三、隔一层调用（内层没写出错时）：错误链上也能找到")
    post = make_router(["{}"])
    st, body, _ = post("/textbook/deep_try", 文本="第一课")
    err = body.get("error", "")
    check(st == 200 and body.get("handled") is True, f"接住了：{st} {body}")
    check("问JSON 格式不对" in err, f"e.error 仍是原文、不带中间层包装：{err[:120]}")

    print("四、报错 4xx 照旧；成功时 e 是空串")
    post = make_router([])
    st, body, _ = post("/textbook/biz_try", 文本="x")
    check(st == 200 and body.get("handled") is True and body.get("code") == "429"
          and body.get("error") == "太快了", f"4xx 照旧接住：{body}")
    post = make_router(['{"title":"第1课","points":["a"]}'])
    st, body, _ = post("/textbook/try", 文本="第一课")
    check(st == 200 and body == {"title": "第1课", "points": ["a"]},
          f"成功时正常返回、不走 出错时：{st} {body}")

    print("五、DSL 写法错误不被接住")
    post = make_router(["{}"])
    st, body, text = post("/textbook/dslerr_try", 文本="abc")
    check(st == 500 and body.get("handled") is None, f"计算错穿透 出错时：{st} {text[:120]}")
    check("不是数字" in text, f"报错是计算那句：{text[:160]}")

    print("六、没写 出错时 的行为不变")
    post = make_router(["{}"])
    st, body, text = post("/textbook/plain", 文本="第一课")
    check(st == 500, f"照旧 500：{st}")
    check("问JSON 格式不对" in text, f"报错原文还在：{text[:160]}")

    print(f"\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
