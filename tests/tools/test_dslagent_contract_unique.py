# -*- coding: utf-8 -*-
"""约定「唯一」↔ 实体旗标的比对与加载检查（K16b）：约定里确定性写出的唯一（紧跟逗号 / 括号只有「唯一」/ 自成一词 / a + b 唯一）
    实体里必须有「唯一」旗标（多列用行首「唯一 a b」），比对约定报不一致；实体标签写了唯一没旗标，加载检查报错。
    不调模型。

    cd /workspace/agent_mcp && .venv/bin/python tests/tools/test_dslagent_contract_unique.py
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="dslagent_uniq_"))
os.environ["DSLAGENT_TMP"] = str(TMP / "tmp")
os.environ["DSLAGENT_DATASET"] = str(TMP / "dataset")
os.environ["DSLAGENT_STATE"] = str(TMP / "state")

from tools.dslagent import loadcheck as LC                               # noqa: E402
from tools.dslagent.packs.dslproj import contract as C, project as P     # noqa: E402
from tools.dslagent.v3 import scaffold as SF                             # noqa: E402

PASS = FAIL = 0


def check(cond, msg, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✓ " + msg)
    else:
        FAIL += 1
        print("  ✗ " + msg + (f"\n      {str(extra)[:1500]}" if extra != "" else ""))


CONTRACT_TAIL = """

## 函数
公开 函数 取 code
  返回 {code}
  伪代码 返回 {"code": code}

## 接口
GET /t -> 取

## 用例
用例 取_有
  调用 取 code=A
  得 有返回
"""


def mk(name, table_lines, entity_body):
    """搭一个最小项目：contracts/t1.md（## 表 用 table_lines）+ entities/t1.entity（entity_body）。"""
    p = TMP / name
    shutil.rmtree(p, ignore_errors=True)
    (p / "contracts").mkdir(parents=True)
    (p / "contracts" / "t1.md").write_text("模块 t1\n依赖 无\n\n## 表\n" + table_lines + CONTRACT_TAIL,
                                           encoding="utf-8")
    (p / "entities").mkdir(parents=True)
    (p / "entities" / "t1.entity").write_text(entity_body, encoding="utf-8")
    return p


def run(p):
    c, _ = C.parse((p / "contracts" / "t1.md").read_text(encoding="utf-8"))
    return P.compare(p, "t1", c, ["t1"])["差异"]


UNIQ = "没写「唯一」旗标"


def t_compare_single():
    print("比对约定：单列唯一")
    good = [
        ("token", "  code 文本 唯一 知识点编号",
         "  字段 code 文本 必填 唯一 知识点编号\n结束\n",
         "  字段 code 文本 必填 知识点编号\n结束\n"),
        ("紧跟逗号", "  code 文本 系列编号，唯一（默认系列编号为 hanabira）",
         "  字段 code 文本 必填 唯一 系列编号，唯一（默认系列编号为 hanabira）\n结束\n",
         "  字段 code 文本 必填 系列编号，唯一（默认系列编号为 hanabira）\n结束\n"),
        ("括号唯一", "  code 文本 编号（唯一）",
         "  字段 code 文本 必填 唯一 编号（唯一）\n结束\n",
         "  字段 code 文本 必填 编号（唯一）\n结束\n"),
    ]
    for tag, cline, ok_line, bad_line in good:
        p = mk(f"cmp_s_{tag}", f"表 thing\n{cline}\n", f"实体 thing 东西\n{ok_line}")
        d = run(p)
        check(not any(UNIQ in x for x in d), f"约定{tag}写唯一 + 实体有旗标 → 不报", d)
        p = mk(f"cmp_s_{tag}_bad", f"表 thing\n{cline}\n", f"实体 thing 东西\n{bad_line}")
        d = run(p)
        check(any(UNIQ in x and "thing.code" in x and "字段 code 文本 必填 唯一" in x for x in d),
              f"约定{tag}写唯一 + 实体没旗标 → 报（写明表.字段和正确写法）", d)
    # 说明文字里「唯一标识」这类不认：实体没旗标也不报（不模糊匹配）
    p = mk("cmp_s_prose", "表 thing\n  code 文本 唯一标识的生成规则见约定\n", "  字段 code 文本 必填 唯一标识的生成规则见约定\n结束\n")
    check(not any(UNIQ in x for x in run(p)), "「唯一标识」不是唯一声明 → 不报", run(p))


def t_compare_multi():
    print("比对约定：多列唯一")
    ctext = "表 task\n  learner 文本 学习者\n  point_code 文本 知识点编号；learner + point_code 唯一\n"
    p = mk("cmp_m_ok", ctext, "实体 task 任务\n  字段 learner 文本 必填 学习者\n  字段 point_code 文本 必填 知识点\n  唯一 learner point_code\n结束\n")
    check(not any("唯一" in x for x in run(p)), "约定 a + b 唯一 + 实体有「唯一 a b」行 → 不报", run(p))
    p = mk("cmp_m_no", ctext, "实体 task 任务\n  字段 learner 文本 必填 学习者\n  字段 point_code 文本 必填 知识点\n结束\n")
    d = run(p)
    check(any("合起来唯一" in x and "唯一 learner point_code" in x for x in d), "没有多列声明 → 报（正确写法「唯一 a b」）", d)
    # 列不全一样不算：单列旗标顶不了多列
    p = mk("cmp_m_wrong", ctext, "实体 task 任务\n  字段 learner 文本 必填 唯一 学习者\n  字段 point_code 文本 必填 知识点\n结束\n")
    d = run(p)
    check(any("合起来唯一" in x for x in d), "只有单列旗标、没有多列「唯一 a b」行 → 报", d)
    # 顺序无关
    p = mk("cmp_m_order", ctext, "实体 task 任务\n  字段 learner 文本 必填 学习者\n  字段 point_code 文本 必填 知识点\n  唯一 point_code learner\n结束\n")
    check(not any("唯一" in x for x in run(p)), "多列声明列顺序不同 → 不报", run(p))


def t_compare_edges():
    print("比对约定：边界")
    # 实体语法解析不了 → 跳过唯一比对（不误报；语法错由建表 / 跑用例报）
    p = mk("cmp_e_parse", "表 thing\n  code 文本 系列编号，唯一\n", "实体 thing 东西\n  字段 code 乱写 必填 x\n结束\n")
    check(not any("唯一" in x for x in run(p)), "实体解析不了 → 跳过唯一比对，不报也不误报", run(p))
    # 实体整个缺失 → 缺实体另有报法，唯一不重复报
    p = mk("cmp_e_noent", "表 thing\n  code 文本 系列编号，唯一\n", "")
    d = run(p)
    check(not any(UNIQ in x for x in d) and any("没有对应的「实体" in x for x in d), "实体文件缺失 → 只报缺实体", d)


def t_loadcheck():
    print("加载检查：实体标签唯一没旗标")
    def ent(body):
        p = TMP / "lc"
        shutil.rmtree(p, ignore_errors=True)
        (p / "entities").mkdir(parents=True)
        (p / "entities" / "t1.entity").write_text("实体 thing 东西\n" + body + "结束\n", encoding="utf-8")
        return p
    p = ent("  字段 code 文本 必填 系列编号，唯一（默认系列编号为 hanabira）\n")
    probs = LC.check_entity_uniques(p)
    check(len(probs) == 1 and "entities/t1.entity" in probs[0] and UNIQ in probs[0]
          and "字段 code 文本 必填 唯一" in probs[0], "标签写唯一没旗标 → 报错（报错不选警告：命中就是库真没有 UNIQUE）", probs)
    p = ent("  字段 code 文本 必填 唯一 系列编号，唯一\n")
    check(LC.check_entity_uniques(p) == [], "有旗标 → 不报", LC.check_entity_uniques(p))
    p = ent("  字段 learner 文本 必填 学习者\n  字段 point_code 文本 必填 知识点；learner + point_code 唯一\n  唯一 learner point_code\n")
    check(LC.check_entity_uniques(p) == [], "多列用「唯一 a b」行、列字段不用旗标 → 不报", LC.check_entity_uniques(p))
    p = ent("  字段 code 文本 必填 唯一标识的规则\n")
    check(LC.check_entity_uniques(p) == [], "「唯一标识」这类 prose → 不报", LC.check_entity_uniques(p))
    (TMP / "lc_bad" / "entities").mkdir(parents=True, exist_ok=True)
    (TMP / "lc_bad" / "entities" / "t1.entity").write_text("实体 thing 东西\n  字段 code 乱写 必填 x\n结束\n", encoding="utf-8")
    check(LC.check_entity_uniques(TMP / "lc_bad") == [], "实体语法解析不了 → 跳过，不报", LC.check_entity_uniques(TMP / "lc_bad"))
    # 经 加载检查动词 的过滤（project.load_problems）：实体文件的问题算到对应模块头上
    p = ent("  字段 code 文本 必填 系列编号，唯一\n")
    (p / "services").mkdir()
    (p / "services" / "t1.zs").write_text("业务 t1\n  用包 db\n结束\n", encoding="utf-8")
    probs = P.load_problems(p, "t1", ["t1"])
    check(any("entities/t1.entity" in x and UNIQ in x for x in probs), "加载检查（load_problems）报本模块实体的缺旗标", probs)


def t_scaffold():
    print("骨架生成：约定唯一落成旗标 / 唯一行")
    ctext = "表 thing\n  code 文本 唯一 知识点编号\n  learner 文本 学习者\n  point_code 文本 知识点编号；learner + point_code 唯一\n"
    c, probs = C.parse("模块 t1\n依赖 无\n\n## 表\n" + ctext + CONTRACT_TAIL)
    check(not probs, "约定解析通过", probs)
    text = SF.entity_text(c)
    check("字段 code 文本 必填 唯一 " in text and "\n  唯一 learner point_code\n" in text,
          "骨架：单列带「唯一」旗标、多列带「唯一 a b」行", text)
    p = TMP / "sc"
    shutil.rmtree(p, ignore_errors=True)
    (p / "entities").mkdir(parents=True)
    (p / "entities" / "t1.entity").write_text(text, encoding="utf-8")
    check(LC.check_entity_uniques(p) == [], "生成的实体过加载检查（骨架开局不被自己的检查打回）", LC.check_entity_uniques(p))


def main():
    t_compare_single()
    t_compare_multi()
    t_compare_edges()
    t_loadcheck()
    t_scaffold()
    print(f"\n通过 {PASS}，失败 {FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
