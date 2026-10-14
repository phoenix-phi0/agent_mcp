# -*- coding: utf-8 -*-
"""tools/dslagent/dataset.py：训练数据样本（假模型跑一次 v2）、补标签命令、补录。不调真模型，样本只写临时目录。

    cd /home/ysc/mcp && .venv/bin/python tests/tools/test_dslagent_dataset.py

  一、实时记录：样本文件生成、字段齐全、gzip 可读、index 追加一行；没给 DSLAGENT_DATASET 的假模型运行不写
  二、写入目录不可写：运行结果不变，只在 stderr 记一行警告
  三、脱敏：样本里没有环境变量值，像密钥的串被替换
  四、补标签：追加 / 覆盖 / 前缀 / 格式错 / 找不到；index 同步
  五、读码轨迹（工具日志里的返回内容、grok 重取）、补录（v2 目录、旧目录、幂等、隐藏测试标签）
"""
import contextlib
import gzip
import io
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))

import test_dslagent_v2 as T          # noqa: E402  复用假模型和小项目（导入时只建临时目录，不跑用例）
from tools.dslagent import dataset as DS      # noqa: E402

PASS = FAIL = 0
TMP = Path(tempfile.mkdtemp(prefix="dslagent_ds_"))


def check(cond, msg, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✓ " + msg)
    else:
        FAIL += 1
        print("  ✗ " + msg + (f"\n      {str(extra)[:1500]}" if extra != "" else ""))


def rows(base):
    f = Path(base) / "index.jsonl"
    return [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()] if f.exists() else []


def t_live():
    print("一、实时记录")
    base = TMP / "data1"
    os.environ[DS.ENV] = str(base)
    os.environ["DSLAGENT_FAKE_TOKEN"] = "zzTOKENvalue1234567890"
    r, p, out = T.go("ds_ok", T.Fake())
    rs = rows(base)
    check(r["fixed"] and len(rs) == 1, "成功运行：index 追加一行", rs)
    row = rs[0]
    f = Path(row["文件"])
    check(f.exists() and f.suffix == ".gz" and f.parent == base / "runs", "样本文件在 runs/ 下", f)
    with gzip.open(f, "rt", encoding="utf-8") as fh:
        s = json.load(fh)
    for k in ("run_id", "时间", "git_head", "项目", "输入", "规划尝试", "执行", "子任务调用", "结果", "labels", "missing", "模型", "dsl_options"):
        check(k in s, f"字段 {k}")
    check(s["输入"]["任务"] == T.TASK and "【任务原文】" in s["输入"]["规划user"] and s["输入"]["system"]["哈希"],
          "输入：任务原文、规划 user、system 哈希", s["输入"].get("system"))
    check("system" not in s["规划尝试"][0] and s["规划尝试"][0]["system哈希"] == s["输入"]["system"]["哈希"], "system 只记哈希不记全文")
    a = s["规划尝试"][0]
    check(len(s["规划尝试"]) == 1 and a["tag"] == "plan" and a["输出zs"].startswith("用包") and a["计划检查"]["通过"] is True,
          "规划尝试：输出 .zs、计划检查通过", a["计划检查"])
    check(s["执行"]["执行的计划版本"] == 1 and s["执行"]["脚本正常结束"] and s["执行"]["终止"]["状态"] == "成功", "执行：版本、正常结束、终止状态")
    check([x["agent"] for x in s["子任务调用"]] == ["bound"] and s["子任务调用"][0]["user"] and s["子任务调用"][0]["回复原文"],
          "子任务调用：bound 一次，有提示词和回复", [x["tag"] for x in s["子任务调用"]])
    check(s["结果"]["状态"] == "成功" and s["结果"]["验收"]["通过"] is True and s["结果"]["边界复核"].get("结论"),
          "结果：验收、边界复核", s["结果"]["边界复核"])
    check(row["首轮计划过检查"] is True and row["最终状态"] == "成功" and row["fixed"] is True and row["隐藏测试标签"] is False
          and row["任务"] == T.TASK[:80] and row["计划尝试数"] == 1 and row["规划模型"],
          "index 行：首轮过检查、最终状态、fixed、无标签、任务前 80 字", row)
    check("zzTOKENvalue1234567890" not in json.dumps(s, ensure_ascii=False) and s["backfill"] == "否" and s["来源"] == "live",
          "样本里没有环境变量的值；backfill=否")
    r2, _, _ = T.go("ds_ok2", T.Fake())
    check(len(rows(base)) == 2 and rows(base)[0]["run_id"] != rows(base)[1]["run_id"], "再跑一次：index 再追加一行、run_id 不同")
    # 计划没过检查重写 1 次：两个规划尝试，首轮不过
    bad = T.Fake(plan=["用包 common text code\n终止 成功 x\n", T.PLAN_OK])
    r3, _, _ = T.go("ds_rewrite", bad)
    s3 = DS.load(rows(base)[-1]["run_id"], base)
    check([a["tag"] for a in s3["规划尝试"]] == ["plan", "plan_fix"] and rows(base)[-1]["首轮计划过检查"] is False
          and s3["规划尝试"][0]["计划检查"]["通过"] is False and s3["规划尝试"][1]["计划检查"]["通过"] is True
          and s3["执行"]["执行的计划版本"] == 2, "重写：两个规划尝试，首轮没过、第二轮过，执行的是第 2 版", rows(base)[-1])
    # 没给目录的假模型运行不写
    del os.environ[DS.ENV]
    calls = []
    orig = DS.record
    DS.record = lambda *a, **k: calls.append(1)
    try:
        T.go("ds_nodir", T.Fake())
    finally:
        DS.record = orig
    check(not calls, "没设 DSLAGENT_DATASET 的假模型运行不记录（测试不会写进真数据目录）")


def t_unwritable():
    print("二、写入目录不可写")
    base_ok = TMP / "data_ok"
    os.environ[DS.ENV] = str(base_ok)
    r_ok, _, _ = T.go("ds_w1", T.Fake())
    blocker = TMP / "afile"
    blocker.write_text("x", encoding="utf-8")
    os.environ[DS.ENV] = str(blocker / "sub")          # 父路径是文件，建不了目录
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        r_bad, p, out = T.go("ds_w2", T.Fake())
    check(r_bad["fixed"] == r_ok["fixed"] and r_bad["reply"]["状态"] == r_ok["reply"]["状态"] == "成功"
          and r_bad["calls"] == r_ok["calls"] and "x + x" in T.util(p), "目录不可写：运行结果不变（成功、调用数、改动）", r_bad.get("stop"))
    check(err.getvalue().count("[dataset] 写样本失败") == 1 and (out / "result.json").exists(), "只记一行警告，result.json 照写", err.getvalue())
    ro = TMP / "ro"
    ro.mkdir()
    ro.chmod(0o500)
    os.environ[DS.ENV] = str(ro / "d")
    with contextlib.redirect_stderr(io.StringIO()):
        r_ro, _, _ = T.go("ds_w3", T.Fake())
    ro.chmod(0o700)
    check(r_ro["fixed"], "只读目录：运行结果不变")


def t_scrub():
    print("三、脱敏")
    st = {}
    x = DS.scrub({"a": "key sk-abcdefghijklmnopqrstuvwx1234 end", "b": ['api_key = "abcdefgh12345678"', "Bearer abcdefghijklmnopqrstuvwxyz0123"],
                  "c": "普通文本 token 不带值"}, st)
    check("sk-abcdef" not in json.dumps(x) and "abcdefgh12345678" not in json.dumps(x) and "Bearer abcdef" not in json.dumps(x)
          and x["c"] == "普通文本 token 不带值" and st["n"] == 3, "密钥样的串换成 [REDACTED]，普通文本不动", x)
    base = TMP / "data_scrub"
    os.environ[DS.ENV] = str(base)
    T.go("ds_sc", T.Fake(), task=T.TASK + " 备注：key sk-abcdefghijklmnopqrstuvwx1234")
    s = DS.load(rows(base)[0]["run_id"], base)
    check("sk-abcdefghijkl" not in json.dumps(s, ensure_ascii=False) and s["脱敏处数"] >= 1, "落盘样本脱敏并记处数", s["脱敏处数"])


def t_label():
    print("四、补标签")
    base = TMP / "data_label"
    os.environ[DS.ENV] = str(base)
    T.go("ds_lb", T.Fake())
    rid = rows(base)[0]["run_id"]
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = DS.main(["label", rid, "hidden_pass=是", "hidden_detail=10 passed"])
    s = DS.load(rid, base)
    check(rc == 0 and s["labels"] == {"hidden_pass": "是", "hidden_detail": "10 passed"}, "追加标签", s["labels"])
    check(rows(base)[0]["隐藏测试标签"] is True and len(rows(base)) == 1, "index 同步（有标签，仍一行）", rows(base))
    with contextlib.redirect_stdout(io.StringIO()):
        DS.main(["label", rid[:14], "hidden_pass=true", "note=x=y"])
    s = DS.load(rid, base)
    check(s["labels"]["hidden_pass"] == "是" and s["labels"]["note"] == "x=y" and s["labels"]["hidden_detail"] == "10 passed",
          "run_id 前缀可用；true→是；值里可含 =；旧标签保留；同名覆盖", s["labels"])
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        rc1 = DS.main(["label", "nope", "a=b"])
    check(rc1 == 1 and "找不到" in err.getvalue(), "找不到样本：退出码 1")
    try:
        DS.label(rid, ["没有等号"])
        ok = False
    except ValueError:
        ok = True
    check(ok, "不是 key=value 报错")
    check(DS.main(["label"]) == 2, "缺参数：退出码 2")
    # 标签进 stats / 筛选
    check(DS.stats(base)["隐藏测试标签"] == {"True": 1}, "stats 里能看到有标签的数量", DS.stats(base))


def t_reads_backfill():
    print("五、读码轨迹与补录")
    # 手工拼一个 claude 规划的运行目录：dsl 工具日志里有返回内容
    d = TMP / "hand" / "out"
    (d / "calls").mkdir(parents=True)
    (d / "toollogs").mkdir()
    (d / "calls" / "01_plan.prompt.txt").write_text("[system]\nSYS\n\n[user]\n【任务原文】\n改个东西\n\n## 文件大纲\nx", encoding="utf-8")
    (d / "calls" / "01_plan.reply.txt").write_text("用包 common\n终止 成功 ok", encoding="utf-8")
    (d / "calls.json").write_text(json.dumps([{"n": 1, "tag": "plan", "engine": "claude", "model": "sonnet", "sec": 1.0, "cost": 0.1}]), encoding="utf-8")
    (d / "plan_tools.json").write_text(json.dumps([
        {"调用": "plan", "尝试": 1, "序": 1, "工具": "dsl", "参数": "打印 读片段 a.py:1-3", "返回字数": 5, "状态": "ok"},
        {"调用": "plan", "尝试": 1, "序": 2, "工具": "dsl", "参数": "打印 x", "返回字数": 1, "状态": "ok"}]), encoding="utf-8")
    (d / "toollogs" / "plan_a1.jsonl").write_text(json.dumps({"n": 1, "code": "打印 读片段 a.py:1-3", "status": "ok", "reply": "[打印]\nline1"}) + "\n"
                                                  + json.dumps({"n": 2, "code": "打印 x", "status": "ok"}) + "\n", encoding="utf-8")
    (d / "plan_v1.zs").write_text("用包 common\n终止 成功 ok", encoding="utf-8")
    (d / "result.json").write_text(json.dumps({"project": "/nonexistent/myproj", "fixed": True, "status": "成功", "planner": "v2", "cost": 0.1,
                                               "seconds": 3, "calls": 1, "v2": {"检查": [{"阶段": "空跑", "问题": ""}], "models": {"plan": "sonnet"}}}),
                                   encoding="utf-8")
    s = DS.build_v2(d)
    tr = s["规划尝试"][0]["读码轨迹"]
    check(s["输入"]["任务"] == "改个东西" and tr[0]["返回内容"] == "[打印]\nline1" and tr[1]["返回内容"] is None and "读码返回内容" in s["missing"],
          "dsl 工具日志有 reply 的取全文；没有的留空并记进 missing（不编）", tr)
    # grok：在项目上按参数重取
    proj = TMP / "gproj"
    (proj / "pkg").mkdir(parents=True)
    (proj / "pkg" / "m.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    got = DS.capture_reads(proj, [{"工具": "read_file", "参数": {"target_file": "pkg/m.py"}}, {"工具": "grep", "参数": {"pattern": "def f"}},
                                  {"工具": "read_file", "参数": {"target_file": "/etc/passwd"}}, {"工具": "dsl", "参数": "打印 x"}])
    check(set(got) == {"0", "1"} and "1|def f():" in got["0"] and "pkg/m.py:1:def f():" in got["1"], "grok 读码返回内容按参数重取；越界 / 非 grok 工具不取", got)
    # 补录
    base = TMP / "data_bf"
    r1 = DS.backfill_dir(d, base, hint="hand")
    check(r1.startswith("bf-"), "补录 v2 目录", r1)
    sb = DS.load(r1, base)
    check(sb["backfill"] == "是" and sb["项目"] == "myproj" and sb["git_head_近似"] is True and sb["结果"]["状态"] == "成功", "补录样本：backfill=是、项目名、近似 git", sb["项目"])
    check(DS.backfill_dir(d, base) == "exists" and len(rows(base)) == 1, "同目录再补录：不重复")
    # 旧目录（多版 .zs + 旁边 row.json 的隐藏测试结果）
    old = TMP / "exp" / "run_A" / "p"
    old.mkdir(parents=True)
    (old.parent / "task.txt").write_text("旧任务描述", encoding="utf-8")
    (old.parent / "row.json").write_text(json.dumps({"name": "run_A", "hidden": False, "existing": True, "hidden_tail": "1 failed"}), encoding="utf-8")
    (old / "plan_v1.zs").write_text("用包 common\n终止 失败 x", encoding="utf-8")
    (old / "plan_v1_raw.txt").write_text("raw", encoding="utf-8")
    (old / "result.json").write_text(json.dumps({"project": "/x/repo", "fixed": False, "stop": "没修好", "cost": 0.2, "seconds": 5}), encoding="utf-8")
    r2 = DS.backfill_dir(old, base, hint="exp1")
    so = DS.load(r2, base)
    check(so["labels"].get("hidden_pass") == "否" and so["labels"]["hidden_detail"] == "1 failed" and "读码轨迹" in so["missing"]
          and so["结果"]["状态"] == "失败" and so["输入"]["任务"] == "旧任务描述", "旧目录：任务、.zs、结果、隐藏测试标签，缺的字段列在 missing", so["labels"])
    # 没任务 / 没 .zs 的拼不出来 → 跳过
    nod = TMP / "exp" / "run_B"
    nod.mkdir(parents=True)
    (nod / "result.json").write_text("{}", encoding="utf-8")
    check(DS.backfill_dir(nod, base).startswith("skip:"), "拼不出的目录跳过")
    stat = DS.backfill(exp=TMP / "exp", jobs=TMP / "nojobs", base=TMP / "data_bf2")
    check(stat["新增"] == 1 and stat["按来源"] == {"exp": 1}, "backfill 扫实验目录（跳过拼不出的）", stat)


def main():
    try:
        t_live()
        t_unwritable()
        t_scrub()
        t_label()
        t_reads_backfill()
    finally:
        os.environ.pop(DS.ENV, None)
        shutil.rmtree(TMP, ignore_errors=True)
        shutil.rmtree(T.TMP, ignore_errors=True)
    print(f"\n{'=' * 50}\n通过 {PASS}，失败 {FAIL}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
