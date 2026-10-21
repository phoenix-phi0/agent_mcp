"""存问题清单：把核查各路的结果合并存成 plan/issues/<序号>.md（序号接着上一份往后编，带「类型：」行）。
参数都可省，按名字传：程序 / 回归 / 冒烟 / 疑点 = 对应动词（全局检查 / 全量回归 方式=核查 / 接口冒烟 方式=核查 / 逻辑核查）的返回；
规划 = 派任务 的返回，模块 = 并行派任务 的返回（模块名 = 逗号隔开的模块名，顺序同 模块）。
规划 / 模块 先看 status：不是成功的记入 unchecked（模块名 + reason），不能当作没问题；成功的取 result.found / result.items。
found=是 但 items 为空、found=否 但 items 非空、某项缺 issue/modules/basis/type 或 type 不在 code/contract/req 之内 → 该项丢弃，
记入 dropped（带原文），不重调模型。合并后按（issue, modules）去重，统一序号。
返回 {path, count, unchecked, dropped}。
例如 设 s = 存问题清单 程序={a} 回归={b} 冒烟={c} 规划={p} 模块={m} 模块名={mods} 疑点={e}
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 存问题清单(程序=None, 回归=None, 冒烟=None, 规划=None, 模块=None, 疑点=None, 模块名="") -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _v3ctx as X
    from tools.dslagent.v3 import audit as AU, issues as IS
    c = X.ctx()
    items, unchecked, dropped = AU.merge(程序, 回归, 冒烟, 规划, 模块, 疑点, 模块名)
    rel = IS.save(c.project, items)
    c.log("核查", 事件="存问题清单", 路径=rel, 条数=len(items), 没核查=unchecked, 丢弃=len(dropped))
    return {"path": rel, "count": len(items), "unchecked": unchecked, "dropped": dropped}
