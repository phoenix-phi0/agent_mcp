"""做模块：起子进程跑一次完整的 v2（python -m tools.dslagent run --pack dslproj），任务 = 「模块 <名>」+ 上次失败原因。
范围激活、环境变量是进程级的，所以不在本进程里跑；每轮在项目的拷贝里做，只把本模块范围内的文件拷回项目。
返回 {status: 成功|失败, reason, cost, calls, round, model, log_dir, secs}。status 是 v2 自己的判断，验收（加载检查 / 比对约定 / 跑用例）由调用方另做。
例如 设 r = 做模块 graph {失败} 模型=opus
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 做模块(模块: str, 上次失败: str = "", 模型: str = "sonnet") -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _v3ctx as X
    from tools.dslagent.v3 import modrun
    r = modrun.run_module(X.ctx(), 模块.strip(), 上次失败, 模型 or "sonnet")
    return {"status": r["状态"], "reason": r["原因"], "cost": r["花费"], "calls": r["调用"], "round": r["轮"],
            "model": r["模型"], "log_dir": r["记录目录"], "secs": r["秒"]}
