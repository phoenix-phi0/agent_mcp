# -*- coding: utf-8 -*-
"""改文件 / 计划检查的新定位方式：点名函数整段替换（@@ 改 路径 函数 名）、函数内锚点（函数 + 原文）、
缩进容错（精确 0 次时忽略行首行尾空白、唯一才套用，新文按同样的缩进差挪）；#改法 段的解析和回写；
核对计划 与 改文件 结果一致；旧写法行为不变。不调模型。

    cd /workspace/agent_mcp && .venv/bin/python tests/tools/test_dslagent_edit_locate.py
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="dslagent_locate_"))
os.environ["DSLAGENT_STATE"] = str(TMP / "state")
os.environ.pop("DSLAGENT_RULES", None)
(TMP / "state").mkdir()

from tools import dsl_sections as S                # noqa: E402
from tools.dslagent import dslcheck as DC          # noqa: E402
from tools.dslagent import plan as P               # noqa: E402
from tools.dslagent.common import _verb_module     # noqa: E402
from tools.dslagent.engine import AgentEngine      # noqa: E402
from tools.mock import MockClient                  # noqa: E402

M = _verb_module("改文件")
passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


ZS = """业务 report
  依赖 account
  用包 common db

  公开 函数 全班表 sort_by?
    设 rows = 调用 account.学生列表
    如果 {found} 等于 0
      报错 404 没有这个学生
    结束
    返回 {rows}
  结束

  公开 函数 学生详情 student
    设 found = 0
    如果 {found} 等于 0
      报错 404 没有这个学生
    结束
    遍历 s 于 {sc.rows}
      如果 {s.score} 小于 80
        设 wn = 计算 {wn} + 1
      结束
    结束
    返回 {wn}
  结束

  函数 内部工具 x
    返回 {x}
  结束
结束
"""
PY = """import os


class A:
    def run(self):
        return 1

    def stop(self):
        return 0


class B:
    def run(self):
        return 2


def helper(x):
    if x:
        return 1
    return 0
"""
SRC = {"services/report.zs": ZS, "pkg/m.py": PY, "pkg/__init__.py": "",
       "tests/__init__.py": "", "tests/test_m.py": "x = 1\n"}


def project(name, files=SRC):
    d = TMP / name
    shutil.rmtree(d, ignore_errors=True)
    for rel, text in files.items():
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        (d / rel).write_text(text, encoding="utf-8", newline="")
    return d


def run_sec(proj, sec):
    m = MockClient(handler=lambda p, s=None: "嗯", offline=True)
    eng = AgentEngine(client=m, workdir=proj, verbose=False, verbs_root=P.PKG / "verbs")
    eng.run("用包 common text code\n设 res = 改文件 {e1}\n#改法 e1\n" + sec)
    return eng.vars["res"]


def run_json(proj, e):
    m = MockClient(handler=lambda p, s=None: "嗯", offline=True)
    eng = AgentEngine(client=m, workdir=proj, verbose=False, verbs_root=P.PKG / "verbs")
    eng.vars["e"] = json.dumps(e, ensure_ascii=False)
    eng.run("用包 common text code\n设 res = 改文件 {e}\n")
    return eng.vars["res"]


def probs(proj, sec, info=None):
    _, secs, _, _ = S.split_sections("#改法 e1\n" + sec)
    return M.核对计划(proj, secs, info)


def fblk(path, func, new):
    return f"@@ 改 {path} 函数 {func}\n<<<<<<< 新函数\n{new}\n>>>>>>> 新文\n"


def ablk(path, func, old, new):
    return f"@@ 改 {path} 函数 {func}\n<<<<<<< 原文\n{old}\n=======\n{new}\n>>>>>>> 新文\n"


def blk(path, old, new):
    return f"@@ 改 {path}\n<<<<<<< 原文\n{old}\n=======\n{new}\n>>>>>>> 新文\n"


def read(p, rel):
    return (p / rel).read_text(encoding="utf-8")


def test_spans():
    print("一、函数范围")
    sp = M._func_spans(ZS, "学生详情")
    body = ZS[sp[0][0]:sp[0][1]]
    check(len(sp) == 1 and body.startswith("  公开 函数 学生详情 student\n") and body.endswith("    返回 {wn}\n  结束\n"),
          f".zs：函数头到同缩进的 结束：{body[-30:]!r}")
    sp = M._func_spans(ZS, "内部工具")
    check(len(sp) == 1 and ZS[sp[0][0]:sp[0][1]] == "  函数 内部工具 x\n    返回 {x}\n  结束\n", "不带 公开 的 函数 也认")
    check(M._func_spans(ZS, "学生") == [], "名字要整词相等（学生 ≠ 学生详情）")
    check(len(M._func_spans(PY, "run")) == 2, ".py：两个类里各有一个 run")
    sp = M._func_spans(PY, "B.run")
    check(len(sp) == 1 and PY[sp[0][0]:sp[0][1]] == "    def run(self):\n        return 2\n", "Class.method 点名到具体方法")
    sp = M._func_spans(PY, "helper")
    check(PY[sp[0][0]:sp[0][1]] == "def helper(x):\n    if x:\n        return 1\n    return 0\n", ".py：到缩进回落（文末）")
    check(M._func_of({"函数": "公开 函数 学生详情 student"}) == "学生详情" and M._func_of({"func": "def run(self):"}) == "run"
          and M._func_of({"function": "A.stop"}) == "A.stop" and M._func_of({"old": "x"}) == "", "func / 函数 / function 别名，整行函数头只取名字")


def test_parse():
    print("二、#改法 段解析与回写")
    sec = ("#改法 e1\n" + fblk("services/report.zs", "学生详情", "  公开 函数 学生详情 student\n    返回 1\n  结束")
           + ablk("services/report.zs", "全班表", "x", "y") + blk("pkg/m.py", "a", "b")
           + "@@ 改 pkg/m.py 函数 helper\n<<<<<<< 原文\n\n=======\ndef helper(x):\n    return 9\n>>>>>>> 新文\n")
    _, secs, _, pr = S.split_sections(sec)
    ed = secs["e1"]["edits"]
    check(pr == [] and len(ed) == 4, f"四块都认：{pr}")
    check(ed[0] == {"file": "services/report.zs", "func": "学生详情", "old": "", "new": "  公开 函数 学生详情 student\n    返回 1\n  结束"},
          f"函数 + 只有新函数 = 整段替换：{ed[0]}")
    check(ed[1] == {"file": "services/report.zs", "func": "全班表", "old": "x", "new": "y"}, f"函数 + 原文/新文 = 锚点：{ed[1]}")
    check(ed[2] == {"file": "pkg/m.py", "old": "a", "new": "b"}, "旧写法不带 func 键")
    check(ed[3]["func"] == "helper" and ed[3]["old"] == "" and ed[3]["new"].startswith("def helper"), "函数 + 原文为空 = 整段替换")
    txt = S.edits_text("e1", secs["e1"])
    _, again, _, _ = S.split_sections(txt)
    check(again["e1"] == secs["e1"] and "@@ 改 services/report.zs 函数 学生详情" in txt, "edits_text 回写后再解析一致")
    _, _, _, pr = S.split_sections("#改法 e1\n@@ 改 pkg/m.py\n<<<<<<< 原文\nabc\n>>>>>>> 新文\n")
    check(len(pr) == 1 and "缺 =======" in pr[0] and "函数 名" in pr[0], f"旧写法缺 ======= 照旧报错，并提示函数写法：{pr}")
    _, _, _, pr = S.split_sections("#改法 e1\n@@ 改 pkg/m.py 函数 helper\n<<<<<<< 新函数\n\n>>>>>>> 新文\n")
    check(len(pr) == 1 and "新函数是空的" in pr[0], f"新函数为空报错：{pr}")
    _, secs, _, pr = S.split_sections("#改法 e1\n" + blk("pkg/m.py", "a", "b") + ">>>>>>> 新文\n\n#清单\n改 pkg/m.py\n")
    check(pr == [] and len(secs["e1"]["edits"]) == 1, f"块结尾后重复的一行 >>>>>>> 忽略：{pr}")
    _, secs, _, pr = S.split_sections("#改法 e1\n@@ 改 pkg/m.py\n>>>>>>> 新文\n")
    check(any("认不出" in x for x in pr), f"不是紧跟块结尾的 >>>>>>> 照旧报错：{pr}")
    _, secs, _, pr = S.split_sections("#改法 e1\n@@ 改 pkg/m.py 函数: helper\n<<<<<<< 新函数\ndef helper(x):\n    return 2\n>>>>>>> 新文\n")
    check(pr == [] and secs["e1"]["edits"][0]["func"] == "helper", "「函数: 名」写法也认")


def test_func_replace():
    print("三、点名函数整段替换")
    p = project("func")
    new = "  公开 函数 学生详情 student pass_line\n    返回 {pass_line}\n  结束"
    r = run_sec(p, fblk("services/report.zs", "学生详情", new))
    t = read(p, "services/report.zs")
    check(r["ok"] == "是" and new + "\n\n  函数 内部工具 x" in t and "遍历 s 于" not in t and t.count("报错 404 没有这个学生") == 1,
          f"整段换掉、前后函数不动：{r['msg']}")
    check("按函数 学生详情 整段替换" in r["msg"] and r.get("modes") == ["函数"], f"msg 注明、modes 记下：{r}")
    p = project("func_ind")
    r = run_sec(p, fblk("services/report.zs", "内部工具", "函数 内部工具 x\n  返回 {x} + 1\n结束"))
    t = read(p, "services/report.zs")
    check(r["ok"] == "是" and "  函数 内部工具 x\n    返回 {x} + 1\n  结束\n结束\n" in t and "挪了 +2 格" in r["msg"],
          f"新函数顶格写：按原函数缩进整体挪齐：{r['msg']}")
    p = project("func_py")
    r = run_sec(p, fblk("pkg/m.py", "B.run", "    def run(self):\n        return 22"))
    t = read(p, "pkg/m.py")
    check(r["ok"] == "是" and "return 22" in t and "        return 1\n" in t and "return 2\n" not in t, f".py Class.method：{r['msg']}")
    p = project("func_err")
    r = run_sec(p, fblk("services/report.zs", "没有的函数", "x"))
    check(r["ok"] == "否" and "没有叫「没有的函数」的函数" in r["msg"] and "学生详情" in r["msg"] and read(p, "services/report.zs") == ZS,
          f"没有这个函数：列候选、不改：{r['msg']}")
    r = run_sec(p, fblk("pkg/m.py", "run", "def run(self):\n    return 3"))
    check(r["ok"] == "否" and "有 2 个" in r["msg"] and "第 5、13 行" in r["msg"] and read(p, "pkg/m.py") == PY,
          f"函数名不唯一：报行号、不改：{r['msg']}")
    r = run_sec(p, fblk("services/report.zs", "内部工具", "  函数 内部工具 x\n    返回 {x}\n  结束"))
    check(r["ok"] == "否" and "没有改动" in r["msg"], f"新函数和原来一样：报没有改动：{r['msg']}")
    r = run_json(p, {"file": "pkg/m.py", "func": "helper", "new": "def helper(x):\n    return 7"})
    check(r["ok"] == "是" and read(p, "pkg/m.py").endswith("def helper(x):\n    return 7\n"), f"JSON 单项 {{file, func, new}} 也收：{r['msg']}")
    r = run_json(p, {"edits": [{"file": "pkg/m.py", "函数": "A.stop", "new": "    def stop(self):\n        return -1"}]})
    check(r["ok"] == "是" and "return -1" in read(p, "pkg/m.py"), f"edits 里用 函数 键：{r['msg']}")
    r = run_json(p, {"edits": [{"file": "tests/test_m.py", "func": "x", "new": "y"}]})
    check(r["ok"] == "否" and "测试文件" in r["msg"], "点名函数也不许改测试文件")


def test_anchor():
    print("四、函数内锚点")
    p = project("anchor")
    old = "      报错 404 没有这个学生"
    r = run_sec(p, blk("services/report.zs", old, "      报错 404 查无此人"))
    check(r["ok"] == "否" and "出现了 2 次" in r["msg"] and "函数 名" in r["msg"], f"不带函数：2 次、提示可用函数锚点：{r['msg']}")
    r = run_sec(p, ablk("services/report.zs", "学生详情", old, "      报错 404 查无此人"))
    t = read(p, "services/report.zs")
    check(r["ok"] == "是" and t.count("报错 404 查无此人") == 1 and t.index("查无此人") > t.index("公开 函数 学生详情")
          and r.get("modes") == ["锚点"], f"带函数：只改 学生详情 里那一处：{r['msg']}")
    p = project("anchor2")
    r = run_sec(p, ablk("services/report.zs", "学生详情", "    返回 {rows}", "x"))
    check(r["ok"] == "否" and "函数 学生详情" in r["msg"] and "出现 0 次" in r["msg"], f"原文不在这个函数里：0 次：{r['msg']}")
    r = run_sec(p, ablk("services/report.zs", "学生详情", "结束", "x"))
    check(r["ok"] == "否" and "函数 学生详情" in r["msg"] and "次" in r["msg"] and read(p, "services/report.zs") == ZS,
          f"函数里也不唯一：报次数：{r['msg']}")
    r = run_sec(p, ablk("services/report.zs", "学生详情", "  如果 {s.score} 小于 80", "  如果 {s.score} 小于 {pass_line}"))
    check(r["ok"] == "是" and "      如果 {s.score} 小于 {pass_line}\n" in read(p, "services/report.zs"), f"锚点 + 子串精确匹配：{r['msg']}")
    p = project("anchor3")
    r = run_sec(p, ablk("services/report.zs", "学生详情", "       报错 404 没有这个学生", "       报错 404 查无此人"))
    t = read(p, "services/report.zs")
    check(r["ok"] == "是" and "\n      报错 404 查无此人\n" in t and r.get("modes") == ["锚点+缩进容错"], f"锚点里再用缩进容错：{r['msg']}")


def test_fuzzy():
    print("五、缩进容错")
    p = project("fz")
    old = "     如果 {s.score} 小于 80\n       设 wn = 计算 {wn} + 1"        # 整体少 1 格
    new = "     如果 {s.score} 小于 {pass_line}\n       设 wn = 计算 {wn} + 1"
    r = run_sec(p, blk("services/report.zs", old, new))
    t = read(p, "services/report.zs")
    check(r["ok"] == "是" and "\n      如果 {s.score} 小于 {pass_line}\n        设 wn = 计算 {wn} + 1\n" in t,
          f"整体差 1 格：套上，新文同样挪 +1：{r['msg']}")
    check("缩进容错" in r["msg"] and "+1" in r["msg"] and r.get("modes") == ["缩进容错"], "msg 注明用了缩进容错")
    p = project("fz2")
    r = run_sec(p, blk("pkg/m.py", "  if x:\n      return 1", "  if x:\n      return 11"))
    check(r["ok"] == "是" and "    if x:\n        return 11\n" in read(p, "pkg/m.py"), f".py 少 2 格：{r['msg']}")
    p = project("fz3")
    r = run_sec(p, blk("pkg/m.py", "def helper(x):   \n    return 0", "def helper(x):\n    return 5"))
    check(r["ok"] == "否" and "return 5" not in read(p, "pkg/m.py"), f"按行比，不是连续行（中间有 if）不套：{r['msg']}")
    r = run_sec(p, blk("pkg/m.py", "    return 0   ", "    return 5"))
    check(r["ok"] == "否" and "也不唯一" in r["msg"], f"忽略空白后 2 处（A.stop、helper）：不套：{r['msg']}")
    r = run_sec(p, blk("pkg/m.py", "        return 2   ", "        return 5"))
    check(r["ok"] == "是" and "        return 5\n" in read(p, "pkg/m.py") and "只差行尾空白" in r["msg"], f"只差行尾空白：{r['msg']}")
    p = project("fz4")
    r = run_sec(p, blk("services/report.zs", "    报错 404 没有这个学生", "x"))
    check(r["ok"] == "否" and "出现 2 次" not in r["msg"], f"精确匹配到 2 次（子串）：照旧报多次：{r['msg']}")
    r = run_sec(p, blk("services/report.zs", "  如果 {found} 等于 0\n    报错 404 没有这个学生", "x"))
    check(r["ok"] == "否" and "出现 0 次" in r["msg"] and "也不唯一" in r["msg"] and read(p, "services/report.zs") == ZS,
          f"忽略缩进后 2 处：不套、说明：{r['msg']}")
    r = run_sec(p, blk("services/report.zs", "     如果 {s.score} 小于 80\n         设 wn = 计算 {wn} + 1", "x"))
    check(r["ok"] == "否" and "缩进差不一致" in r["msg"], f"各行缩进差不一致：不套：{r['msg']}")


def test_check_agrees():
    print("六、核对计划 与 改文件 一致")
    cases = [
        ("func", fblk("services/report.zs", "学生详情", "  公开 函数 学生详情 student\n    返回 1\n  结束"), True, "函数"),
        ("anchor", ablk("services/report.zs", "学生详情", "      报错 404 没有这个学生", "      报错 404 无"), True, "锚点"),
        ("fuzzy", blk("services/report.zs", "       如果 {s.score} 小于 80", "       如果 {s.score} 小于 90"), True, "缩进容错"),
        ("exact", blk("pkg/m.py", "        return 2", "        return 3"), True, None),
        ("many", blk("services/report.zs", "      报错 404 没有这个学生", "x"), False, None),
        ("nofunc", fblk("services/report.zs", "无此函数", "x"), False, None),
        ("manyfunc", fblk("pkg/m.py", "run", "x"), False, None),
        ("fz_many", blk("services/report.zs", "  如果 {found} 等于 0\n    报错 404 没有这个学生", "x"), False, None),
        ("seq", fblk("services/report.zs", "学生详情", "  公开 函数 学生详情 student\n    返回 1\n  结束")
         + ablk("services/report.zs", "学生详情", "    返回 1", "    返回 2"), True, "函数"),
    ]
    for tag, sec, ok, mode in cases:
        p = project("agree_" + tag)
        info = []
        pr = probs(p, sec, info)
        unchanged = read(p, "services/report.zs") == ZS
        r = run_sec(p, sec)
        check((pr == []) == ok and (r["ok"] == "是") == ok and unchanged
              and (mode is None or (info and info[0]["mode"] == mode)),
              f"{tag}：检查{'通过' if ok else '报错'}、改文件{'套上' if ok else '不套'}、检查只读、info={[i['mode'] for i in info]}：{pr[:1]} {r['msg'][:80]}")
    p = project("agree_msg")
    pr = probs(p, blk("services/report.zs", "      报错 404 没有这个学生", "x"))
    check(len(pr) == 1 and "出现 2 次" in pr[0] and "第 8 行" in pr[0] and "第 16 行" in pr[0] and "函数 名" in pr[0],
          f"多次：照旧报次数和行号，并提示函数锚点：{pr}")
    pr = probs(p, ablk("services/report.zs", "学生详情", "结束", "x"))
    check(len(pr) == 1 and "函数 学生详情 内" in pr[0] and "第 17 行" in pr[0], f"锚点内多次：行号按整个文件算：{pr}")
    pr = probs(p, fblk("services/report.zs", "无此函数", "x"))
    check(len(pr) == 1 and "没有叫「无此函数」的函数" in pr[0] and "全班表" in pr[0], f"没有这个函数：{pr}")
    pr = DC.edit_problems(p, "用包 common text code\n设 r = 改文件 {e1}\n#改法 e1\n"
                          + fblk("services/report.zs", "学生详情", "  公开 函数 学生详情 student\n    返回 1\n  结束"))
    check(pr == [], f"dslcheck.edit_problems 走同一套：{pr}")


def test_crlf():
    print("七、CRLF")
    files = dict(SRC, **{"pkg/m.py": PY.replace("\n", "\r\n")})
    p = project("crlf", files)
    r = run_sec(p, fblk("pkg/m.py", "helper", "def helper(x):\n    return 8"))
    raw = (p / "pkg/m.py").read_bytes().decode("utf-8")
    check(r["ok"] == "是" and raw.endswith("def helper(x):\r\n    return 8\r\n") and "\n" not in raw.replace("\r\n", ""),
          f"整段替换按 CRLF 写回：{r['msg']}")
    p = project("crlf2", files)
    r = run_sec(p, blk("pkg/m.py", "   def stop(self):\n       return 0", "   def stop(self):\n       return 4"))
    raw = (p / "pkg/m.py").read_bytes().decode("utf-8")
    check(r["ok"] == "是" and "    def stop(self):\r\n        return 4\r\n" in raw, f"缩进容错按 CRLF 写回：{r['msg']}")


def test_prompts():
    print("八、提示词讲到函数写法")
    from tools.dslagent import v2, packs
    for name in ("code", "dslproj"):
        s = v2.plan_system(packs.pick(name))
        check("函数 名" in s and "新函数" in s, f"{name} 规划 system 讲了 @@ 改 路径 函数 名")
    t = (P.PKG / "agents" / "plan_fix.md").read_text(encoding="utf-8")
    check("@@ 改 路径 函数 名" in t, "plan_fix 用户模板提示改用函数写法")


def main():
    try:
        test_spans()
        test_parse()
        test_func_replace()
        test_anchor()
        test_fuzzy()
        test_check_agrees()
        test_crlf()
        test_prompts()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n通过 {passed}，失败 {failed}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
