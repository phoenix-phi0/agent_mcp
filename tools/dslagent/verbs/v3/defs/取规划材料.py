"""取规划材料：纯程序，把规划层子任务要读的材料读成一个字典 {需求, 顶层, 目录, 约定}：
需求 = 需求全文（参数 需求 可以是需求文件路径，也可以直接是需求文本），顶层 = plan/top.zs 全文，目录 = plan/catalog.md 全文，
约定 = 每个有约定文件的模块按名排序，「### <模块>」+ 约定全文去用例（单份超 12000 字截断，注明「（后面略）」）。缺的项是空串。
子任务读不到工作目录之外的文件，规划层的 派任务 必须把它的返回当入参（入参={mat}），不能只传需求。
例如 设 mat = 取规划材料 需求={req_file}
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 取规划材料(需求: str = "") -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _v3ctx as X
    from tools.dslagent.v3 import audit as AU
    return AU.material(X.ctx(), 需求)
