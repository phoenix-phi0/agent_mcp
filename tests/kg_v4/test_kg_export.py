#!/usr/bin/env python
# -*- coding: utf-8 -*-
# kg_v4 导出功能直连测试（K103s）：起真服务 → t1 登录 → 建知识点 → 调导出接口，
# 返回的文本含该编号。纯 HTTP（urllib），不用浏览器、不需要 playwright。
# 背景：e2e_walk 全量里「导出生成了文本」稳定失败（ERR_ALPN_NEGOTIATION_FAILED，
# 待查），本测试单独确认导出功能本身可用。
#
#     cd /workspace/agent_mcp && .venv/bin/python tests/kg_v4/test_kg_export.py
# 退出码 0 全过 / 1 有失败 / 2 环境起不来。复用 e2e_walk 的建库与起服务。
import http.cookiejar
import json
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[2]))
import e2e_walk as E  # noqa: E402

CODE, TITLE = "exp99.p1", "导出点甲"


def main():
    tmp = Path(tempfile.mkdtemp(prefix="kg_export_"))
    proc = None
    ok_n = fail_n = 0
    try:
        try:
            proj = E.build_workspace(tmp, E.REPO / "kg_v4", kg_mgmt=True)
            port = E.free_port()
            proc = E.start_server(proj, port, open(tmp / "server.log", "w"))
        except Exception as e:
            print("环境起不来：", e)
            return 2
        base = f"http://127.0.0.1:{port}"
        op = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

        def call(method, path, body=None):
            data = None if body is None else json.dumps(body).encode()
            req = urllib.request.Request(base + path, data=data, method=method,
                                         headers={"Content-Type": "application/json"})
            try:
                with op.open(req, timeout=30) as r:
                    return r.status, r.read().decode("utf-8")
            except urllib.error.HTTPError as e:
                return e.code, e.read().decode("utf-8", "replace")

        def ck(ok, msg, detail=""):
            nonlocal ok_n, fail_n
            if ok:
                ok_n += 1
                print("  OK " + msg)
            else:
                fail_n += 1
                print("  XX " + msg + "\n      " + str(detail)[:400])

        st, tx = call("POST", "/account/login", {"username": E.TEACHER_USER, "password": E.TEST_PASSWORD})
        ck(st == 200, "t1 登录", (st, tx))
        st, tx = call("POST", "/kg/manage/point/save", {"kgp_code": CODE, "kgp_title": TITLE})
        ck(st == 200, "建知识点", (st, tx))
        st, tx = call("POST", "/kg/manage/export", {"exp_kind": "知识点"})
        ck(st == 200 and CODE in tx and TITLE in tx, "页面导出（kgm_export）含新建编号", (st, tx))
        st, tx = call("GET", "/kg/export/text?kind=point")
        ck(st == 200 and CODE in tx, "GET /kg/export/text 含新建编号", (st, tx))
        st, tx = call("POST", "/kg/manage/export", {"exp_kind": "全部"})
        ck(st == 200 and CODE in tx, "导出「全部」含新建编号", (st, tx))
        print(f"\n通过 {ok_n}/共 {ok_n + fail_n}")
        return 1 if fail_n else 0
    finally:
        E.stop_server(proc)
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
