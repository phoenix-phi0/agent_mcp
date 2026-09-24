# -*- coding: utf-8 -*-
"""自检：不靠 curl，直接把整条 HTTP 链路跑一遍。

    py -m tools.dsl_http_check                 检查 mcp/routes/
    py -m tools.dsl_http_check --routes dsl/routes

不起真的服务器——用 Flask 的 test_client 在进程内发请求，省得开两个窗口
来回切。最后做一次端口绑定测试，确认真服务器起得来。

检查顺序按依赖排，前面的不过后面的没意义：

    1. flask 装了没
    2. 接口块切分、端口声明     纯文本处理，不碰引擎
    3. 动词包加载               http 包在不在
    4. 「返回」语句             引擎层，HTTP 之外也要对
    5. 进程内发请求             参数注入、会话读写、响应组装
    6. 会话跨请求保持
    7. 端口能不能绑
"""

import argparse
import json
import socket
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_ok = 0
_bad = 0


def check(name: str, cond, detail: str = "") -> bool:
    global _ok, _bad
    if cond:
        _ok += 1
        print(f"  ✓ {name}")
    else:
        _bad += 1
        print(f"  ✗ {name}" + (f"\n      {detail}" if detail else ""))
    return bool(cond)


def brief(obj, n: int = 160) -> str:
    try:
        s = json.dumps(obj, ensure_ascii=False)
    except TypeError:
        s = str(obj)
    return s[:n]


def main() -> int:
    p = argparse.ArgumentParser(description="DSL HTTP 自检")
    p.add_argument("--routes", default=str(ROOT / "routes"))
    args = p.parse_args()
    routes = Path(args.routes)
    if not routes.is_absolute():
        routes = ROOT / routes

    print("=" * 52)
    print(f"DSL HTTP 自检　{routes}")
    print("=" * 52)

    # ---- 1. 依赖 ----
    print("\n[依赖]")
    try:
        import flask
        check(f"flask 已安装（{flask.__version__}）", True)
    except ImportError:
        check("flask 已安装", False, "pip install flask")
        return 1

    from .dsl import DSLEngine
    from .dsl_http import Router, split_endpoints
    from .mock import MockClient
    from . import packs

    # ---- 2. 接口块切分 ----
    print("\n[接口块与端口声明]")
    sample = """
服务 9999

接口 POST /a
  设 x = 1
  如果 {x} 等于 1
    打印 内层
  结束
结束

接口 GET /b
  打印 乙
结束
"""
    eps, port = split_endpoints(sample, Path("样例.zs"))
    check("切出两个接口", len(eps) == 2, f"实际 {len(eps)}")
    check("读到端口声明", port == 9999, f"实际 {port}")
    if len(eps) == 2:
        check("方法和路径正确",
              (eps[0].method, eps[0].path, eps[1].method, eps[1].path)
              == ("POST", "/a", "GET", "/b"),
              f"{eps[0]!r} {eps[1]!r}")
        # 块内的「结束」不能被当成接口的收尾
        check("内层结束没被误认",
              "打印 内层" in eps[0].script and "接口" not in eps[0].script)

    if not routes.is_dir():
        check(f"路由目录存在（{routes}）", False, "先建目录并放 .zs")
        return 1

    # ---- 3. 动词包 ----
    print("\n[动词包]")
    reg = packs.registry(["common", "quiz", "http"], ROOT)
    for name in ("消息", "状态", "响应", "挑题号", "判题"):
        check(f"动词 {name} 在", reg.has(name))
    for w in reg.warnings:
        print(f"      [警告] {w}")

    # ---- 4. 返回语句 ----
    # 这是引擎层的能力，HTTP 之外也该对。放在发请求之前测，断了好定位。
    print("\n[返回语句]")
    def ran(script: str):
        e = DSLEngine(MockClient(), workdir=ROOT, verbose=False)
        e.run(script)
        return e.returned

    r = ran('返回 {"code":0}')
    check("JSON 被解析成结构", r is not None and r[0] == {"code": 0}, brief(r))
    r = ran("返回 ok")
    check("纯文本原样返回", r is not None and r[0] == "ok", brief(r))
    r = ran('返回 {"error":"x"} 400')
    check("状态码被认出", r is not None and r[1] == 400, brief(r))
    r = ran("打印 一\n返回 二\n打印 三")
    check("返回后不再执行", r is not None and r[0] == "二", brief(r))
    e = DSLEngine(MockClient(), workdir=ROOT, verbose=False)
    out = e.run("打印 只打印")
    check("没返回时 returned 是 None", e.returned is None, brief(e.returned))
    check("输出仍然正常", out == "只打印", out)
    r = ran("如果 1 小于 2\n  遍历 x 于 a,b\n    返回 深层返回\n  结束\n结束")
    check("嵌套块里也能返回", r is not None and r[0] == "深层返回", brief(r))

    # ---- 5. 进程内发请求 ----
    print("\n[进程内请求]")
    with tempfile.TemporaryDirectory() as tmp:
        router = Router(routes, ROOT, Path(tmp), real=False, verbose=False)
        check("扫到接口", len(router.table) > 0, f"{routes} 下没有接口块")
        if not router.table:
            return 1
        for (m, q) in sorted(router.table):
            print(f"      {m} {q}")
        if router.port:
            print(f"      脚本声明端口 {router.port}")
        for w in router.warnings:
            print(f"      [警告] {w}")

        client = router.app().test_client()

        # 未知路径
        r404 = client.post("/没有这个", json={})
        check("未知路径返回 404", r404.status_code == 404, str(r404.status_code))

        # 有 /health 就试纯文本返回
        if ("GET", "/health") in router.table:
            rh = client.get("/health")
            check("GET /health 返回 200", rh.status_code == 200)
            check("纯文本不包 JSON", rh.get_data(as_text=True).strip() == "ok",
                  rh.get_data(as_text=True)[:60])

        # 有 /api/user 就试早返回和状态码
        if ("POST", "/api/user") in router.table:
            r1 = client.post("/api/user", json={})
            check("缺参数时状态码 400", r1.status_code == 400, str(r1.status_code))
            r2 = client.post("/api/user", json={"id": "7"})
            d2 = r2.get_json() or {}
            check("给了参数返回 200", r2.status_code == 200)
            check("参数注入到返回值里",
                  (d2.get("data") or {}).get("id") == "7", brief(d2))

        # 会话：连发两次看计数
        counter = next((q for (m, q) in router.table
                        if q in ("/count", "/count2")), None)
        if counter:
            a = client.post(counter, json={"learner": "自检"}).get_json()
            b = client.post(counter, json={"learner": "自检"}).get_json()
            print(f"      第一次 {brief(a)}")
            print(f"      第二次 {brief(b)}")
            check("会话文件已建",
                  (Path(tmp) / "自检.json").is_file())
            check("计数在涨", brief(a) != brief(b),
                  "两次返回一样，会话可能没存住")

        # 教学接口：start → answer 的完整链路
        if ("POST", "/drill/start") in router.table:
            print("\n[练习链路]")
            s = client.post("/drill/start", json={
                "learner": "自检2", "course": "doushi_01", "kind": "词义"})
            ds = s.get_json() or {}
            print(f"      {brief(ds)}")
            check("start 返回 200", s.status_code == 200)
            msgs = ds.get("messages") or []
            check("start 出了题", any(m.get("who") == "题目" for m in msgs),
                  "没有 who=题目 的消息，可能是挑题号返回空")

            sess = Path(tmp) / "自检2.json"
            if check("会话已建", sess.is_file()):
                saved = json.loads(sess.read_text(encoding="utf-8"))
                check("记住了课程", saved.get("课程") == "doushi_01",
                      brief(saved))
                check("记住了题号", bool(saved.get("题号")))

                a = client.post("/drill/answer",
                                json={"learner": "自检2", "answer": "A"})
                da = a.get_json() or {}
                print(f"      {brief(da)}")
                check("answer 判了题",
                      any(m.get("who") == "批改"
                          for m in (da.get("messages") or [])),
                      "没有 who=批改 的消息，可能是会话没读回来")
                after = json.loads(sess.read_text(encoding="utf-8"))
                check("总数加了一", str(after.get("总")) == "1",
                      str(after.get("总")))
                check("答完清空题号", not after.get("题号"))

    # ---- 7. 端口 ----
    print("\n[端口]")
    port = router.port or 8090
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", port))
            check(f"{port} 可用", True)
        except OSError as e:
            check(f"{port} 可用", False, f"{e}，换 --port")

    print("\n" + "=" * 52)
    print(f"通过 {_ok}，失败 {_bad}")
    if not _bad:
        print("\n可以起真服务器了：")
        print("  py -m tools.dsl_http --mock")
    print("=" * 52)
    return 1 if _bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
