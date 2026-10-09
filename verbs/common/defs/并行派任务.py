"""并行派一组互不依赖的子任务，返回结果列表（顺序同输入）。例如 设 rs = 并行派任务 {jobs} 3

列表的每项是 {任务, 入参, 逻辑, 格式}（同 派任务 的四个参数，也认 task/inputs/logic/format），
或者一段文本（只有任务描述）。并发上限缺省 3（1–8）。每项的结果是 {结果, 状态, 原因}，
某项失败不影响别的项。拼列表用 列表加项：

    设 jobs = 解析JSON []
    设 job.任务 = 检查 a.py 的导入
    设 jobs = 列表加项 {jobs} {job}
    设 rs = 并行派任务 {jobs} 2
    遍历 r 于 {rs} … {r.状态} … 结束
细节见 tools/dsl_task.py。
"""

from tools.dsl import current_engine
from tools.dsl_task import DEFAULT_PARALLEL, dispatch_many


def 并行派任务(列表="", 并发=str(DEFAULT_PARALLEL)) -> list:
    return dispatch_many(current_engine(), 列表, 并发)
