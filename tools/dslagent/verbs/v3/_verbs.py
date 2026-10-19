"""v3 包（dslagent 私有）：v3 流程用的动词——规划（写规划 / 检查规划 / 存规划 / 已有规划 / 依赖分层 / 规划到通过 / 规划一份）、
生成（生成骨架 / 生成分配）、做模块（做模块 / 已完成 / 标记完成 / 记验收 / 做模块组 / 做一个模块）。

能用 .zs 写的套路用 .zs 写（规划到通过、规划一份、做模块组、做一个模块）；确定性的事和调模型在 Python（逻辑在 tools/dslagent/v3/）。
动词通过 current_engine().v3 拿运行上下文（项目、记录目录、v2 的 Model、状态），只能在 `python -m tools.dslagent v3` 起的流程里用。
"""

from pathlib import Path

from tools.verbs import scan_verbs

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def register(reg, workspace):
    scan_verbs(reg, PACK_DIR / "defs", workspace, pack_dir=PACK_DIR)
