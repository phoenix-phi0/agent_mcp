# -*- coding: utf-8 -*-
"""`--llm` / 脚本里的「模型 X」真的生效（K18）：v3 audit2 整条（假模型）里 派任务 的调用记录
engine/model/effort 与指定一致；问 / 问JSON / 派任务 全链路；无「模型」语句走默认 sonnet；
Model.spec 认 engines.parse 的完整模型串（旧的不校验透传保留）；派代理 按角色回退时 calls.json
里有记录（实际 engine/model + 回退原因）。零真实模型调用。

    cd /workspace/agent_mcp && .venv/bin/python tests/tools/test_dslagent_llm.py

复用 test_dslagent_v3.py 的夹具（参考实现项目、假模型 Fake）。
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_dslagent_v3 as T                                   # noqa: E402

check, fresh, core, Fake = T.check, T.fresh, T.core, T.Fake
from tools.dslagent import common as C                         # noqa: E402
from tools.dslagent import engines as EG                       # noqa: E402
from tools.dslagent import v2 as V2                            # noqa: E402


def a2_ok():
    return json.dumps({"result": {"result": "ok"}, "status": "成功", "reason": ""}, ensure_ascii=False)


class A2Fake(Fake):
    """audit2 用的假模型：dsl* 一律回 result=ok（格式对得上 audit2 的回复格式字段）。"""

    def __call__(self, system, user, tag, timeout, **kw):
        self.calls.append({"tag": tag, "user": user, "model": kw.get("model")})
        if "门牌" in user:                      # 问JSON 的提示词带「门牌」标记
            return {"text": '{"x": 1}', "cost": 0.01}
        if tag.startswith("dsl"):
            return {"text": a2_ok(), "cost": 0.01}
        return {"text": "ok", "cost": 0.01}


def audit2_project():
    p = T.full_project()
    (p / "plan").mkdir(exist_ok=True)
    (p / "plan" / "top.zs").write_text(T.TOP3, encoding="utf-8")
    return p


def rec_model(sp):
    return sp["model"] or sp["engine"]


def test_audit2_llm():
    print("audit2 整条（假模型）：--llm 指什么，派任务 的调用记录就是什么（engine/model/effort）")
    p = audit2_project()
    for llm in ("sonnet", "goose:glm-x", "codex:cx", "grok:high"):
        out = fresh("a2out")
        fk = A2Fake()
        res = core.run_entry("audit2", p, out, "需求", extra_vars={"llm": llm}, backend=fk)
        sp = EG.parse(llm)
        calls = json.loads((out / "calls.json").read_text(encoding="utf-8"))
        dsl = [c for c in calls if str(c.get("tag", "")).startswith("dsl")]
        check(res["status"] == "成功" and len(dsl) == 3, f"{llm}：跑成、三个有代码的模块各派一次",
              (res.get("status"), res.get("reason"), [c.get("tag") for c in dsl]))
        check(all(c["engine"] == sp["engine"] and c["model"] == rec_model(sp) and c["effort"] == sp["effort"] for c in dsl),
              f"{llm}：calls.json 里 engine/model/effort 与指定一致",
              [(c["engine"], c["model"], c["effort"]) for c in dsl])
        want = None if llm == "sonnet" else sp["spec"]      # sonnet = 缺省，backend 不多传 model
        got = [c["model"] for c in fk.calls if c["tag"].startswith("dsl")]
        check(got == [want] * 3, f"{llm}：backend 收到的 model 与指定一致（sonnet 缺省不传）", got)


def run_script(p, out, text, fk):
    """不经过 run_entry 的迷你入口：同样的 V3Engine + v2.Client + Model（写 calls.json 同 run_entry）。"""
    M = V2.Model(out, backend=fk, max_calls=50)
    ctx = core.Ctx(p, out, "需求", M)
    eng = core.V3Engine(client=V2.Client(M), workdir=p, verbose=False, verbs_root=C.VERBS)
    eng.v3, ctx.usage = ctx, eng.usage
    eng.vars.update({"req": "需求", "syntax": ""})
    eng.run(text)
    (out / "calls.json").write_text(json.dumps(M.log, ensure_ascii=False, indent=1), encoding="utf-8")
    return M, eng


def test_model_stmt_chain():
    print("「模型 X」之后的 问 / 问JSON / 派任务 都用 X；无「模型」语句走默认 sonnet")
    p, out = fresh("p"), fresh("o")
    fk = A2Fake()
    M, _e = run_script(p, out, "用包 common v3\n"
                   "模型 goose:gx\n"
                   "问 a = 回一个字\n"
                   "问JSON b = 回一个门牌 JSON {\"x\": 1} 格式 x:数字\n"
                   "设 r = 派任务 查一下 result:文本\n", fk)
    tags = [(c["tag"], c["engine"], c["model"], c["effort"]) for c in M.log]
    check(len(M.log) == 3 and all(t[0].startswith("dsl") for t in tags), "三次调用：问 / 问JSON / 派任务", tags)
    check(all(e == "goose" and m == "gx" for _t, e, m, _f in tags), "三次全走 goose:gx（不再落回 sonnet）", tags)
    q2, out2 = fresh("p"), fresh("o")
    fk2 = A2Fake()
    M2, e2 = run_script(q2, out2, "用包 common v3\n设 r = 派任务 查一下 result:文本\n", fk2)
    check(len(M2.log) == 1 and M2.log[0]["engine"] == "claude" and M2.log[0]["model"] == "sonnet",
          "没有「模型」语句：默认 claude/sonnet", M2.log)
    check(fk2.calls[0]["model"] is None and e2.returned is None, "默认时 backend 不多传 model", fk2.calls[0])
    p3, out3 = fresh("p"), fresh("o")
    M3, _e3 = run_script(p3, out3, "用包 common v3\n模型 codex:cx:low\n设 r = 派任务 查一下 result:文本\n", A2Fake())
    check(M3.log[0]["engine"] == "codex" and M3.log[0]["model"] == "cx" and M3.log[0]["effort"] == "low",
          "「模型 codex:cx:low」：engine/model/effort 都记对", M3.log[0])


def test_spec_parse():
    print("Model.spec：model 参数认 engines.parse 的完整模型串；不认识的串当 claude 模型名（旧透传）；routes 仍优先")
    M = V2.Model(tempfile.mkdtemp(prefix="k18_"))
    for s, want in (("goose:glm-x", ("goose", "glm-x", None)), ("goose", ("goose", None, None)),
                    ("codex:cx", ("codex", "cx", "medium")), ("codex:cx:low", ("codex", "cx", "low")),
                    ("grok:high", ("grok", None, "high")), ("opus", ("claude", "opus", None)),
                    ("claude-sonnet-5-5", ("claude", "claude-sonnet-5-5", None)),
                    ("glm-5.3", ("claude", "glm-5.3", None))):
        sp = M.spec("dsl01", s)
        check((sp["engine"], sp["model"], sp["effort"]) == want, f"spec({s!r}) → {want}", sp)
    check(M.spec("dsl01")["model"] == "sonnet" and M.spec("dsl01")["engine"] == "claude", "不给 model：默认 sonnet")
    M2 = V2.Model(tempfile.mkdtemp(prefix="k18_"), routes={"sub": "opus"})
    sp = M2.spec("dsl01", "goose:gx")
    check(sp["engine"] == "claude" and sp["model"] == "opus", "routes.sub 写了仍优先（v2 既有语义不变）", sp)


class RoleFake(Fake):
    """派代理 用：按 backend 收到的 model 回复（默认模型回坏 JSON、回退模型回好 JSON）。"""

    def __call__(self, system, user, tag, timeout, **kw):
        m = kw.get("model")
        self.calls.append({"tag": tag, "model": m, "user": user})
        if m == "goose:gpt-6-luna:medium":
            return {"text": "不是 json", "cost": 0.01}
        if m == "sonnet":
            return {"text": '[{"问题": "漏了锁", "依据": "x"}]', "cost": 0.02}
        return {"text": "ok", "cost": 0.01}


def test_agent_fallback_in_calls():
    print("派代理 按角色回退（logic_check：goose 默认 → sonnet 回退）：calls.json 记实际 engine/model 和回退原因")
    p, out = fresh("p"), fresh("o")
    fk = RoleFake()
    M, e = run_script(p, out, "用包 common v3\n"
                   "设 inp.约定 = 这份约定的内容\n"
                   "设 r = 派代理 角色=logic_check 任务=检查这份约定 入参={inp}\n"
                   "返回 {r.status}\n", fk)
    check(e.returned and e.returned[0] == "ok", "脚本跑完、派代理 回 ok", (e.returned, e.halted))
    check([c["model"] for c in fk.calls] == ["goose:gpt-6-luna:medium", "sonnet"],
          "先默认模型、回复不合格后回退模型（roles.zs 的角色模型，不受「模型」语句影响）", fk.calls)
    fb = [c for c in M.log if "回退" in c]
    check(len(fb) == 1, "calls.json（M.log）里有一条回退记录", M.log)
    r0 = fb[0]
    check(r0["engine"] == "claude" and r0["model"] == "sonnet" and r0["tag"] == "agent_logic_check",
          "回退记录：实际用的 engine/model（回退模型 sonnet）", r0)
    check("goose:gpt-6-luna:medium" in r0["回退"] and ("回退" in r0["回退"]), "回退原因写明默认模型和原因", r0["回退"])
    check(r0["n"] == M.n and r0["cost"] == 0.02, "回退记录占编号、带那次的花费", (r0["n"], M.n, r0["cost"]))


def test_agent_fallback_v2_role():
    print("执行方式 v2 的角色没跑起来换回退模型：同样写进 calls.json")
    from tools.dslagent import roles as R
    calls = []

    def v2_fb(spec, req):
        calls.append(spec)
        return ({"fixed": False, "stop": "引擎错误", "started": False, "calls": 0} if len(calls) == 1
                else {"fixed": True, "cost": 0.1, "sec": 2.0, "calls": 2, "started": True, "files": ["a"]})
    out = fresh("o")
    M = V2.Model(out, backend=None, max_calls=50)
    r = R.dispatch_agent("modify_module", "x", {"模块": "report"}, out_dir=out, v2_backend=v2_fb, mlog=M)
    check(r["status"] == "ok" and r.get("fallback") is True and calls == ["sonnet", "sonnet"],
          "默认 sonnet 没跑起来 → 回退模型再起一次（roles.zs 的 modify_module 两档都是 sonnet）", (r, calls))
    fb = [c for c in M.log if "回退" in c]
    check(len(fb) == 1 and fb[0]["engine"] == "claude" and fb[0]["model"] == "sonnet" and "modify_module" in fb[0]["tag"]
          and "没跑起来" in fb[0]["回退"], "calls.json 记了回退：实际 engine/model + 原因", fb)
    check(fb[0]["n"] == M.n, "回退记录占编号", (fb[0]["n"], M.n))


if __name__ == "__main__":
    try:
        test_audit2_llm()
        test_model_stmt_chain()
        test_spec_parse()
        test_agent_fallback_in_calls()
        test_agent_fallback_v2_role()
    finally:
        shutil.rmtree(T.TMP, ignore_errors=True)
    print(f"\n通过 {T.PASS}，失败 {T.FAIL}")
    sys.exit(1 if T.FAIL else 0)
