"""旧路径专用的提示：模板没修好时让模型写 .zs 计划（第 2、3 版 / 任务路径），以及 定位.zs / 读改测.zs 的固定说明。
共用的 CHEAT / VERBS / TIPS / SEE / fix_prompt 在 ../prompts.py。文本文件在 prompts/legacy/。

不变的大段（DSL 速查 / 可用动词 / 写法要点 / 语法示意，≈4.7k token）放在规划调用的系统提示 SYSTEM 里，
常驻进程 + /clear 之后跨调用、跨运行都能读缓存（plan7 实测规划调用 cache 读占输入 94%，单次 $0.029 → $0.008）；
用户提示只放每次不同的部分（任务、测试摘要、文件清单、上一版脚本和输出）。
"""

from .. import promptfile as PF
from ..prompts import CHEAT, SEE, TIPS, VERBS, fix_prompt  # noqa: F401  共用的，旧名仍可从这里取

SKELETON = PF.text("legacy/skeleton.md")
SYSTEM = PF.tpl("legacy/system.tpl.txt", CHEAT=CHEAT, VERBS=VERBS, TIPS=TIPS, SKELETON=SKELETON)

TEMPLATE_NOTE = PF.text("legacy/template_note.txt")


def _intro(test_cmd):
    return f"Python 项目（测试命令：{test_cmd}；测试文件不能改）"


def first_prompt(desc, files, test, budget, plan_cap, versions_left, test_cmd):
    return PF.tpl("legacy/first_prompt.tpl.txt", intro=_intro(test_cmd), SEE=SEE, desc=desc, test=test, files=files,
                  plan_cap=plan_cap, budget=budget, versions_left=versions_left)


def replan_prompt(desc, files, test0, budget, plan_cap, versions_left, ver, prev_script, prev_out, prev_err, test_now, diff,
                  test_cmd, template_note=""):
    return PF.tpl("legacy/replan_prompt.tpl.txt", intro=_intro(test_cmd), SEE=SEE, ver=ver, next_ver=ver + 1,
                  note=f"{template_note}\n\n" if template_note else "", desc=desc, test0=test0, files=files,
                  prev_script=prev_script, prev_out=prev_out or "（没有输出）",
                  err=PF.tpl("legacy/replan_err.tpl.txt", prev_err=prev_err) if prev_err else "",
                  test_now=test_now, diff=diff or "（还没有改动源码）", plan_cap=plan_cap, budget=budget,
                  versions_left=versions_left)


def task_first_prompt(desc, files, test, budget, plan_cap, versions_left, test_cmd):
    """任务路径（开局测试全过、不是修 bug）的第 1 版规划提示；系统提示同 SYSTEM。"""
    return PF.tpl("legacy/task_first_prompt.tpl.txt", intro=_intro(test_cmd), SEE=SEE, desc=desc, test=test, files=files,
                  plan_cap=plan_cap, budget=budget, versions_left=versions_left)


def task_replan_prompt(desc, files, test0, budget, plan_cap, versions_left, ver, prev_script, prev_out, prev_err, test_now,
                       diff, test_cmd, note=""):
    return PF.tpl("legacy/task_replan_prompt.tpl.txt", intro=_intro(test_cmd), SEE=SEE, ver=ver, next_ver=ver + 1,
                  note=f"{note}\n\n" if note else "", desc=desc, test0=test0, files=files,
                  prev_script=prev_script, prev_out=prev_out or "（没有输出）",
                  err=PF.tpl("legacy/replan_err.tpl.txt", prev_err=prev_err) if prev_err else "",
                  test_now=test_now, diff=diff or "（还没有改动）", plan_cap=plan_cap, budget=budget,
                  versions_left=versions_left)


# ------------------------------------------------------------ 定位.zs / 读改测.zs 的固定说明（系统提示）
# 两个子脚本的 问JSON 以前把规则、动作说明、「输出格式」说明都拼在用户消息末尾，变化内容在前：
# CLI 的缓存断点打在整条用户消息上，一字不同就整条重写，缓存读 0%（plan11 B 臂）。
# 现在固定说明全放进 LIB_SYSTEM（两种用途合一份：一个常驻进程、共用一段缓存前缀），用户消息只放变化内容，
# 以 LOC_TAG / RCT_TAG 开头；engine.AgentEngine 看到这两个开头就改用 LIB_SYSTEM 作系统提示，
# 并剥掉 DSL 自动附在末尾、已写进 LIB_SYSTEM 的那段格式说明（格式校验和重问照旧）。
# LIB_SYSTEM 不含路径、轮次、时间等变化内容，跨调用、跨运行逐字不变。
LOC_TAG, RCT_TAG = "【定位】", "【读改测】"
# 与 lib/定位.zs、lib/读改测.zs 里 问JSON 的「格式 …」逐字一致（单测核对）
LOC_FORMAT = "action:改|换关键词|读这些|运行看看 kw?:文本 segs?:文本 code?:文本 edits?:列表 reason:文本"
RCT_FORMAT = "action:改|无需改 reason:文本 edits?:列表 need?:文本"


def _tail(fmt):
    from tools.dsl_model import _format_note, _split_format
    return _format_note(_split_format("提示 格式 " + fmt, 0)[1])


LOC_TAIL, RCT_TAIL = _tail(LOC_FORMAT), _tail(RCT_FORMAT)

LIB_SYSTEM = PF.tpl("legacy/lib_system.tpl.txt", LOC_TAG=LOC_TAG, RCT_TAG=RCT_TAG, LOC_TAIL=LOC_TAIL, RCT_TAIL=RCT_TAIL)


def lib_tail(prompt):
    """定位 / 读改测 的用户消息 → 已写进 LIB_SYSTEM 的那段格式说明；别的提示 → None。"""
    if prompt.startswith(LOC_TAG):
        return LOC_TAIL
    if prompt.startswith(RCT_TAG):
        return RCT_TAIL
    return None
