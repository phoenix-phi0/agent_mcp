# -*- coding: utf-8 -*-
"""「出错时」要能接住模型调用本身的失败（超时、限流、服务不可用、网络断）：
K20 之前这类失败抛 RuntimeError（zhipu HTTP 失败）/ BackendError（CLI 后端），
`调用 … 出错时` 和 `问JSON … 出错时` 都接不住，接口 500 / 整个任务失败。
现在模型调用语句把它们包成 ModelCallError（ModelOutputError 的子类，码 503），
现有分类逻辑认 ModelOutputError 族，两种「出错时」都接得住。

    cd /workspace/agent_mcp && .venv/bin/python tests/dsl/test_on_error_model_call.py

覆盖（业务层经 HTTP 接口真调，假客户端抛各类服务失败）：
  一、问（普通文本）抛 RuntimeError（HTTP 429 限流）→ 调用…出错时 接住，code=503
  二、问JSON 不带「格式」→ 接住，code=503
  三、问JSON 带「格式」→ 接住，code=503
  四、超时（TimeoutError）→ 接住；BackendError（CLI 后端不可用）→ 接住
  五、编程错误（TypeError）不被接住，照旧 500
  六、没写 出错时 照旧抛：plain 问 仍回 502 + 一句人话（model_call 标记还在）
"""

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.dsl_http import Router                    # noqa: E402
from tools.mock import MockClient                    # noqa: E402
from tools.llm_router import BackendError            # noqa: E402

SERVICE = """业务 tutor

  公开 函数 判意图 文本
    问 r = 判断意图：{文本}
    返回 {r}
  结束

  公开 函数 抽原文 文本
    问JSON r = {文本}
    返回 {r}
  结束

  公开 函数 抽格式 文本
    问JSON r = {文本} 格式 title:文本
    返回 {r}
  结束

  公开 函数 会炸 文本
    问 r = {文本}
    设 n = 计算 {文本} + 1
    返回 {"n": "{n}"}
  结束
结束
"""

ROUTE = """
# 模型调用本身失败（超时 / 限流 / 服务不可用）要能被 出错时 接住
接口 POST /tutor/try
  设 r = 调用 tutor.判意图 文本={文本} 出错时 e
  如果 {e} 不为空
    返回 {"handled": true, "code": "{e.code}", "error": "{e.error}"}
  结束
  返回 {r}
结束

接口 POST /tutor/json_try
  设 r = 调用 tutor.抽原文 文本={文本} 出错时 e
  如果 {e} 不为空
    返回 {"handled": true, "code": "{e.code}", "error": "{e.error}"}
  结束
  返回 {r}
结束

接口 POST /tutor/fmt_try
  设 r = 调用 tutor.抽格式 文本={文本} 出错时 e
  如果 {e} 不为空
    返回 {"handled": true, "code": "{e.code}", "error": "{e.error}"}
  结束
  返回 {r}
结束

接口 POST /tutor/dslerr_try
  设 r = 调用 tutor.判意图 文本={文本} 出错时 e
  设 n = 计算 {文本} + 1
  如果 {e} 不为空
    返回 {"handled": true, "code": "{e.code}", "error": "{e.error}"}
  结束
  返回 {r}
结束

# 没写 出错时：模型调用失败照旧往上抛（model_call 标记还在，接口层待遇不变）
接口 POST /tutor/plain
  设 r = 调用 tutor.判意图 文本={文本}
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


def make_router(bomb):
    """bomb：假客户端每次被调都抛的异常。"""
    def handler(prompt, system):
        raise bomb
    ws = Path(tempfile.mkdtemp(prefix="k20_"))
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

    return post


def main():
    print("一、问（普通文本）抛 RuntimeError（HTTP 429 限流）：调用…出错时 接住")
    post = make_router(RuntimeError("智谱接口返回 429: Rate limit exceeded"))
    st, body, _ = post("/tutor/try", 文本="第一课")
    err = body.get("error", "")
    check(st == 200 and body.get("handled") is True, f"接住了：{st} {body}")
    check(body.get("code") == "503", f"code 是 503：{body.get('code')}")
    check("模型调用失败" in err and "429" in err and "Rate limit" in err,
          f"e.error 带前缀和原文：{err[:120]}")

    print("二、问JSON 不带「格式」：同样接住")
    post = make_router(RuntimeError("智谱接口返回 503: Service Unavailable"))
    st, body, _ = post("/tutor/json_try", 文本="第一课")
    err = body.get("error", "")
    check(st == 200 and body.get("handled") is True and body.get("code") == "503",
          f"接住了：{st} {body}")
    check("模型调用失败" in err, f"e.error：{err[:120]}")

    print("三、问JSON 带「格式」：同样接住")
    post = make_router(RuntimeError("网络 Stream decode error"))
    st, body, _ = post("/tutor/fmt_try", 文本="第一课")
    check(st == 200 and body.get("handled") is True and body.get("code") == "503",
          f"接住了：{st} {body}")

    print("四、超时与 CLI 后端不可用：也接住")
    post = make_router(TimeoutError("Read timed out. (read timeout=90)"))
    st, body, _ = post("/tutor/try", 文本="第一课")
    check(st == 200 and body.get("handled") is True and body.get("code") == "503"
          and "timed out" in body.get("error", ""),
          f"TimeoutError 接住：{body}")
    post = make_router(BackendError("claude 起不来：exit 1"))
    st, body, _ = post("/tutor/try", 文本="第一课")
    check(st == 200 and body.get("handled") is True and body.get("code") == "503"
          and "claude 起不来" in body.get("error", ""),
          f"BackendError 接住：{body}")

    print("五、编程错误（TypeError）不被接住")
    post = make_router(RuntimeError("智谱接口返回 429: Rate limit"))
    # 会炸 里先 问（服务失败被 出错时 接住、r 为空），接着 计算 "abc" + 1
    # 抛 TypeError —— 编程错误，不接
    st, body, text = post("/tutor/dslerr_try", 文本="abc")
    check(st == 500 and body.get("handled") is None,
          f"TypeError 穿透 出错时：{st} {text[:120]}")
    check("不是数字" in text, f"报错是计算那句：{text[:160]}")

    print("六、没写 出错时 的行为不变：照旧抛、接口仍 502 + 一句人话")
    post = make_router(RuntimeError("智谱接口返回 429: Rate limit"))
    st, body, _ = post("/tutor/plain", 文本="第一课")
    check(st == 502, f"照旧 502：{st}")
    check("模型这次没有回应" in body.get("error", ""),
          f"一句人话还在：{body}")

    print(f"\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
