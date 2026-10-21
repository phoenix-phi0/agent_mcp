# -*- coding: utf-8 -*-
"""动词参数：必填 / 可选 / 默认值，调用支持 键=值。

    .venv/bin/python tests/dsl/test_verb_params.py
"""

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools import packs                                # noqa: E402
from tools.dsl import DSLEngine, DSLError              # noqa: E402
from tools.mock import MockClient                      # noqa: E402
from tools.verbs import VerbRegistry, parse_param_specs  # noqa: E402
from tools.dslagent import loadcheck as LC             # noqa: E402

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


TMP = Path(tempfile.mkdtemp(prefix="verbparams_"))
(TMP / "新.zs").write_text(
    "# 新：测试\n# 参数：种类 需求? 最多=3 模型=sonnet 停在?\n"
    "返回 [{种类}|{需求}|{最多}|{模型}|{停在}]\n", encoding="utf-8")
(TMP / "逗号.zs").write_text("# 参数：甲、乙，丙,丁=1\n返回 {甲}{乙}{丙}{丁}\n", encoding="utf-8")
(TMP / "旧.zs").write_text("# 旧：旧写法\n# 参数：甲、乙\n返回 [{甲}|{乙}]\n", encoding="utf-8")
(TMP / "空默认.zs").write_text("# 参数：甲 乙=\n返回 [{甲}|{乙}]\n", encoding="utf-8")
(TMP / "结构.zs").write_text("# 参数：数据 名?\n设 n = 计算 1\n返回 {数据}\n", encoding="utf-8")
(TMP / "pk").mkdir()
(TMP / "pk" / "_verbs.py").write_text('''
def register(reg, workspace):
    @reg.verb("py 动词")
    def 加(甲: str, 乙: str = "5", 丙: str = "x") -> str:
        return f"{甲}-{乙}-{丙}"

    @reg.verb("收列表")
    def 收(列表, 名: str = "") -> list:
        return 列表
''', encoding="utf-8")

REG = VerbRegistry(reserved=set())
from tools.dsl_core import RESERVED                    # noqa: E402
REG.reserved = RESERVED
REG.load_dir(TMP)
REG.load_pack(TMP / "pk")


def run(script, **vars_):
    e = DSLEngine(client=MockClient(offline=True), workdir=TMP, verbose=False, verbs=REG)
    e.vars.update(vars_)
    e.run(script)
    return e


def out(script, **vars_):
    return "\n".join(run(script, **vars_).output)


def err(script):
    try:
        run(script)
    except DSLError as e:
        return str(e)
    return None


def main():
    print("[一、声明解析]")
    specs, strict, ln = parse_param_specs("# 新\n# 参数：种类 需求? 最多=3 模型=sonnet 停在?\n返回 1\n")
    check([(p.name, p.required, p.default) for p in specs] ==
          [("种类", True, None), ("需求", False, ""), ("最多", False, "3"), ("模型", False, "sonnet"), ("停在", False, "")]
          and strict and ln == 2, "必填 / ? / =默认 三种声明，行号 2")
    check(REG.params_of("逗号") == ["甲", "乙", "丙", "丁"], "顿号 逗号 全角逗号 空白都是分隔符")
    check([p.name for p in parse_param_specs("# 参数：甲 乙\n")[0]] == ["甲", "乙"] and not parse_param_specs("# 参数：甲 乙\n")[1],
          "全裸名 = 旧规则")
    check(parse_param_specs("返回 1\n") == ([], False, 0), "没声明")

    print("\n[二、绑定]")
    check(out("设 r = 新 坦克\n打印 {r}") == "[坦克||3|sonnet|]", "只传必填：可选为空串、默认值生效")
    check(out("设 r = 新 坦克 要快 5\n打印 {r}") == "[坦克|要快|5|sonnet|]", "全位置")
    check(out("设 r = 新 坦克 模型=opus\n打印 {r}") == "[坦克||3|opus|]", "位置 + 键=值 混用")
    check(out("设 r = 新 最多=9 种类=A\n打印 {r}") == "[A||9|sonnet|]", "全部 键=值、顺序任意")
    check(out("设 r = 新 种类=A 需求=\n打印 {r}") == "[A||3|sonnet|]", "键= 给空串")
    check(out("设 r = 新 坦克 最多={n}\n打印 {r}", n="7") == "[坦克||7|sonnet|]", "键=值 里的 {变量} 展开")
    check(out("设 r = 空默认 a\n打印 {r}") == "[a|]", "名= 等同 名?（空串）")
    check(out("设 r = 逗号 1 2 3\n打印 {r}") == "1231", "逗号分隔声明 + 默认 1")
    check(out("设 默认 = ab\n设 r = 新 种类={默认}\n打印 {r}") == "[ab||3|sonnet|]", "值是变量")
    (TMP / "dv.zs").write_text("# 参数：甲 乙={甲}\n返回 [{乙}]\n", encoding="utf-8")
    REG.load_dir(TMP)
    check(out("设 r = dv q\n打印 {r}") == "[{甲}]", "默认值是字面文本，不展开变量")

    print("\n[三、旧文件兼容]")
    check(out("设 r = 旧 1\n打印 {r}") == "[1|{乙}]", "旧文件少传不报错（变量没绑，原样保留）")
    check(out("设 r = 旧\n打印 {r}") == "[{甲}|{乙}]", "旧文件全不传也不报错")
    check(out("设 r = 旧 乙=2 甲=1\n打印 {r}") == "[1|2]", "旧文件也能用 键=值")
    e = err("设 r = 旧 1 2 3")
    check(e and "最多接受 2 个" in e and "第 1 行" in e, "旧文件多传仍报错")

    print("\n[四、不误认]")
    check(out("设 a = 1\n设 b = 2\n设 x = 计算 {a} + {b}\n打印 {x}") == "3", "计算 正常")
    check(out("设 r = 新 坦克 x=y\n打印 {r}") == "[坦克|x=y|3|sonnet|]", "不是声明的键 → 位置参数原样 x=y")
    check(out("设 r = 新 A 需求=a=b\n打印 {r}") == "[A|a=b|3|sonnet|]", "值里再有 = 原样保留")
    e = err("计算 a=b")
    check(e and "计算：看不懂「a=b」" in e, "计算 a=b 仍是计算自己的报错，不被当 键=值")
    check(out("设 a = 1\n设 b = 2\n计算 {a}+{b}") == "3", "计算 单独一行不受影响")
    check(out("设 r = 计算 1 + 1\n打印 {r}") == "2", "计算 照常")

    print("\n[五、报错与行号]")
    e = err("打印 hi\n设 r = 新")
    check(e and "第 2 行" in e and "缺少必填参数「种类」" in e and "新" in e and "新.zs 第 2 行" in e, f"缺必填：动词 参数 调用行 声明行：{e}")
    e = err("设 r = 新 A 种类=B")
    check(e and "「种类」给了两次" in e and "第 1 行" in e, f"同一参数两次（位置 + 键）：{e}")
    e = err("设 r = 新 A 最多=1 最多=2")
    check(e and "「最多」给了两次" in e, "同一参数两次（键 + 键）")
    e = err("\n\n设 r = 新 A b 3 4 5 6")
    check(e and "最多接受 5 个" in e and "第 3 行" in e, f"位置参数过多：{e}")
    e = err("设 r = 新 A B 最多=1 x y z")
    check(e and "最多接受 5 个" in e, "键=值 后面的位置参数也计入过多")
    check(out("设 r = 新 A 最多=1 乙\n打印 {r}") == "[A|乙|1|sonnet|]", "键=值 后面的位置参数依次填没给的参数（旧脚本 推理 规则=x {甲} 的写法）")

    print("\n[六、Python 动词]")
    check(out("设 r = 加 1\n打印 {r}") == "1-5-x", "py：默认值取函数签名")
    check(out("设 r = 加 1 丙=z\n打印 {r}") == "1-5-z", "py：键=值")
    check(out("设 r = 加 丙=z 甲=1 乙=2\n打印 {r}") == "1-2-z", "py：全 键=值")
    e = err("设 r = 加")
    check(e and "缺少必填参数「甲」" in e, f"py：缺必填报错：{e}")
    e = err("设 r = 加 1 甲=2")
    check(e and "给了两次" in e, "py：重复给")
    check(out("设 r = 加 1 x=2\n打印 {r}") == "1-x=2-x", "py：非声明键原样当位置")

    print("\n[七、结构值保留]")
    (TMP / "x.json").write_text('[{"a":1},{"a":2}]', encoding="utf-8")
    o = out('读JSON L = x.json\n设 r = 收 列表={L}\n遍历 i 于 {r}\n打印 {i.a}\n结束')
    check(o == "1\n2", f"py：键=值 纯变量保留结构：{o!r}")
    o = out('读JSON L = x.json\n设 r = 结构 数据={L}\n遍历 i 于 {r}\n打印 {i.a}\n结束')
    check(o == "1\n2", f"zs：键=值 纯变量保留结构：{o!r}")

    print("\n[八、展示]")
    d = REG.describe()
    check("<种类> <需求?> <最多=3> <模型=sonnet> <停在?>" in d, "describe：? 与 =默认")
    check("<甲> <乙=5> <丙=x>" in d, "describe：Python 默认值")

    print("\n[九、加载检查]")
    root = TMP / "proj"
    (root / "scripts").mkdir(parents=True)
    (root / "routes").mkdir()
    (root / "verbs" / "pk").mkdir(parents=True)
    (root / "verbs" / "pk" / "新.zs").write_text("# 参数：甲 乙?\n返回 {甲}\n", encoding="utf-8")
    (root / "scripts" / "a.zs").write_text("用包 pk\n设 r = 新\n", encoding="utf-8")
    probs = LC.check_project(root)
    check(any("缺少必填参数「甲」" in p and "第 2 行" in p and "a.zs" in p for p in probs), f"缺必填：{probs}")
    (root / "scripts" / "a.zs").write_text("用包 pk\n新 1 甲=2\n新 1 2 3\n新 1 乙=2\n", encoding="utf-8")
    probs = LC.check_project(root)
    check(len(probs) == 2 and "给了两次" in probs[0] and "第 2 行" in probs[0] and "最多接受 2 个" in probs[1]
          and "第 3 行" in probs[1], f"重复 + 过多，合法的不报：{probs}")
    (root / "scripts" / "a.zs").write_text("用包 pk\n新 1\n新 甲=1 乙=2\n设 x = 新 q\n", encoding="utf-8")
    check(LC.check_project(root) == [], "合法调用不报")
    (root / "routes" / "r.zs").write_text("接口 POST /a\n  用包 pk\n  设 r = 新\n  返回 {r}\n结束\n", encoding="utf-8")
    probs = LC.check_project(root)
    check(any("缺少必填参数" in p and "r.zs 接口 POST /a" in p and "第 3 行" in p for p in probs), f"接口块里也查：{probs}")

    print("\n[十、用到表外动词]")
    root2 = TMP / "proj2"
    (root2 / "scripts").mkdir(parents=True)
    (root2 / "routes").mkdir()
    (root2 / "services").mkdir()
    (root2 / "verbs" / "qk").mkdir(parents=True)
    (root2 / "verbs" / "qk" / "切.zs").write_text("# 参数：x\n返回 {x}\n", encoding="utf-8")
    (root2 / "scripts" / "b.zs").write_text("设 r = 切 x\n", encoding="utf-8")
    probs = LC.check_project(root2)
    check(any("用到表外动词「切」" in p and "它在「qk」包里" in p and "用包 qk" in p and "b.zs" in p for p in probs),
          f"没点名的包里有这个动词 → 报清楚提示：{probs}")
    (root2 / "scripts" / "b.zs").write_text("设 t = 当前时间\n", encoding="utf-8")
    check(LC.check_project(root2) == [], "常驻包 common 的动词不用点名，不报")
    (root2 / "routes" / "r2.zs").write_text("接口 GET /b\n  设 r = 切 x\n  返回 {r}\n结束\n", encoding="utf-8")
    probs = LC.check_project(root2)
    check(any("用到表外动词「切」" in p and "r2.zs 接口 GET /b" in p for p in probs), f"接口块里也查：{probs}")
    (root2 / "routes" / "r2.zs").write_text("接口 GET /b\n  用包 qk\n  设 r = 切 x\n  返回 {r}\n结束\n", encoding="utf-8")
    check(not any("用到表外动词" in p for p in LC.check_project(root2)), "点名了 qk 就不报")
    (root2 / "services" / "x.zs").write_text(
        "业务 x\n  用包 db\n  公开 函数 f a\n    设 r = 切 a\n    返回 {r}\n  结束\n结束\n", encoding="utf-8")
    probs = LC.check_project(root2)
    check(any("用到表外动词「切」" in p and "services/x.zs" in p for p in probs), f"services 文件也查：{probs}")

    print("\n[十一、后台执行只认已有脚本]")
    (root2 / "services" / "x.zs").write_text(
        "业务 x\n  公开 函数 f a\n    后台执行 调用 g a={a}\n    返回 {a}\n  结束\n结束\n", encoding="utf-8")
    probs = LC.check_project(root2)
    check(any("后台执行 调用" in p and "services/x.zs" in p and "第 3 行" in p and "同步" in p for p in probs), f"后台执行跑函数 → 报：{probs}")
    (root2 / "services" / "x.zs").write_text(
        "业务 x\n  公开 函数 f a\n    后台执行 scripts/b.zs a={a}\n    返回 {a}\n  结束\n结束\n", encoding="utf-8")
    check(not any("后台执行" in p for p in LC.check_project(root2)), "后台执行已有脚本 → 不报")

    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
