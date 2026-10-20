# -*- coding: utf-8 -*-
"""顶层脚本传参：`python -m tools.dsl 脚本.zs 键=值 …`、`run`/`run_file`/`run_script` 的 params 字典。

    .venv/bin/python tests/dsl/test_top_params.py

一、bind_top_params：有 # 参数： 声明按动词绑定规则；没有声明原样注入
二、DSLEngine.run(script, params=...) / run_file(path, params=...)
三、模块级 run_script(path, params=...)
"""

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.dsl import DSLEngine, run_script               # noqa: E402
from tools.mock import MockClient                          # noqa: E402
from tools.verbs import VerbError, bind_top_params         # noqa: E402

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


def err(fn):
    try:
        fn()
    except VerbError as e:
        return str(e)
    return None


TMP = Path(tempfile.mkdtemp(prefix="topparams_"))


def main():
    print("[一、bind_top_params]")
    SCRIPT = "# 参数：甲 乙? 丙=默认\n返回 1\n"
    check(bind_top_params(SCRIPT, [("甲", "1")]) == {"甲": "1", "乙": "", "丙": "默认"},
          "必填给了、可选/默认缺省")
    check(bind_top_params(SCRIPT, [("甲", "1"), ("乙", "x"), ("丙", "y")]) ==
          {"甲": "1", "乙": "x", "丙": "y"}, "全给")
    e = err(lambda: bind_top_params(SCRIPT, [("乙", "x")]))
    check(e and "缺少必填参数「甲」" in e, "必填缺了报错")
    e = err(lambda: bind_top_params(SCRIPT, [("甲", "1"), ("丁", "x")]))
    check(e and "没有参数「丁」" in e, "未知键报错")
    e = err(lambda: bind_top_params(SCRIPT, [("甲", "1"), ("甲", "2")]))
    check(e and "给了两次" in e, "同一键给两次报错")

    OLD = "# 参数：甲 乙\n返回 1\n"
    check(bind_top_params(OLD, []) == {}, "旧式声明（无 ?/=）全不传不报错，也不注入")
    check(bind_top_params(OLD, [("甲", "1")]) == {"甲": "1"}, "旧式声明只传一个不报错")

    check(bind_top_params("返回 1\n", [("甲", "1"), ("乙", "2")]) == {"甲": "1", "乙": "2"},
          "没有声明：原样注入，不校验")

    print("\n[二、DSLEngine.run / run_file]")
    e1 = DSLEngine(client=MockClient(offline=True), workdir=TMP, verbose=False)
    e1.run("打印 {甲}-{乙}", params={"甲": "A", "乙": "B"})
    check("\n".join(e1.output) == "A-B", "run(params=...) 注入变量")

    (TMP / "p.zs").write_text("# 参数：甲 乙=默认\n打印 {甲}-{乙}", encoding="utf-8")
    e2 = DSLEngine(client=MockClient(offline=True), workdir=TMP, verbose=False)
    e2.run_file(TMP / "p.zs", params={"甲": "A"})
    check("\n".join(e2.output) == "A-默认", "run_file(params=...) 按声明绑定、默认值生效")

    e3 = DSLEngine(client=MockClient(offline=True), workdir=TMP, verbose=False)
    bad = err(lambda: e3.run_file(TMP / "p.zs", params={"丙": "x"}))
    check(bad and "没有参数「丙」" in bad, "run_file(params=...) 未知键报错")

    print("\n[三、run_script]")
    out = run_script(TMP / "p.zs", client=MockClient(offline=True), verbose=False,
                      params={"甲": "C", "乙": "D"})
    check(out == "C-D", "run_script(params=...) 端到端")

    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
