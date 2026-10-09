"""派一个子任务给模型，回复固定为 {结果, 状态, 原因}。例如 设 r = 派任务 {desc} {inputs} {logic} 改法:列表,说明:文本

参数按位置：任务描述、入参、处理逻辑、回复格式字段（后三个可省；带空格的先「设」进变量）。
  入参    {名: 值} 对象 / 列表 / 逗号分隔；值是「文件:起-止」时动词读出那几行附上
  格式    结果 的字段，写法同 问JSON 的「格式」（字段:类型，逗号或空格隔开，字段? 可选）
状态只能是 成功 / 失败 / 超出预期；回复不合格重答 1 次，仍不合格返回 状态=失败 原因=格式不合格。
模型、通道、系统提示同 问JSON（跟着调用它的脚本）。空跑时不调模型，给结构合法的假结果。

    设 inputs.src = pkg/calc.py:1-40
    设 inputs.test = {t.summary}
    设 r = 派任务 {desc} {inputs} {logic} edits:列表,note:文本
    如果 {r.状态} 等于 成功 … 否则如果 {r.状态} 等于 超出预期 … 结束
细节见 tools/dsl_task.py。
"""

from tools.dsl import current_engine
from tools.dsl_task import dispatch


def 派任务(任务="", 入参="", 逻辑="", 格式="") -> dict:
    return dispatch(current_engine(), 任务, 入参, 逻辑, 格式)
