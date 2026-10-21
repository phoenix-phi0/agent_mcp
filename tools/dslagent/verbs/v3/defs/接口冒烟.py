"""接口冒烟：项目拷到临时目录、按全部 entities 建库，用 tools.dsl_http 的真实 Router（进程内 Flask 测试客户端）
加载全部 routes / services；约定里每个接口取所调函数第一条正常用例，用 cases 造数据（seed_case）在同一份数据上
各跑一次「直接调用」与「走 HTTP」，核对状态码与返回是否一致（随机 / 时间字段只比结构，差异记备注）。
不过的模块同全量回归的规则重做，最多 2 轮，仍不过 终止 失败。含上传的接口暂跳过并记备注。
多人模式（登录 / 角色）留给 A3，这里先不开登录。
例如 接口冒烟
方式=核查（核查.zs 用）：只报告，不重做、不改 state；每个不过的接口一条 item（issue = 方法 路径 + 直接调用与 HTTP 的差异原文），完整结果存 out/smoke_<n>.json / .txt（n 接着已有的往后排），返回带 files；没有代码时跳过。
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 接口冒烟(方式: str = "") -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _v3ctx as X
    from tools.dsl import current_engine
    from tools.dslagent.v3 import planning as PL, regress as RG
    c = X.ctx()
    try:
        top = PL.current_top(c)
    except ValueError as e:
        if 方式 == "核查":
            return {"count": 0, "items": [], "summary": "还没有 plan/top.zs，跳过"}
        X.fail(e)
    if 方式 == "核查":
        return RG.audit_smoke(c, top)
    r = RG.interface_smoke(c, current_engine(), top)
    return {"status": r["状态"], **({"rounds": r["轮数"]} if "轮数" in r else {})}
