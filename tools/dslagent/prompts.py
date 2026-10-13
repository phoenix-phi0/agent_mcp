"""规划提示的共用部分（v2 和旧路径都用）：DSL 速查 / 可用动词 / 写法要点，以及计划检查没过时让模型改脚本的 fix_prompt。

不变的大段放在规划调用的系统提示里（v2：v2.plan_system；旧路径：legacy/prompts.py 的 SYSTEM），跨调用读缓存。
旧路径专用的规划提示（模板没修好时第 2、3 版 / 任务路径）和 定位.zs / 读改测.zs 的固定说明在 legacy/prompts.py。
"""

from . import promptfile as PF

CHEAT = PF.text("cheat.md")
VERBS = PF.text("verbs.md")
TIPS = PF.text("tips.md")
SEE = PF.text("see.txt")


def fix_prompt(script, problem):
    return PF.tpl("fix_prompt.tpl.txt", SEE=SEE, problem=problem,
                  numbered="\n".join(f"{i:3d}| {l}" for i, l in enumerate(script.splitlines(), 1)))
