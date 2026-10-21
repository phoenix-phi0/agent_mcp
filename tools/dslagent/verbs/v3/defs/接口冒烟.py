"""接口冒烟：项目拷到临时目录、按全部 entities 建库，用 tools.dsl_http 的真实 Router（进程内 Flask 测试客户端）
加载全部 routes / services；约定里每个接口取所调函数第一条正常用例，用 cases 造数据（seed_case）在同一份数据上
各跑一次「直接调用」与「走 HTTP」，核对状态码与返回是否一致（随机 / 时间字段只比结构，差异记备注）。
只检查、只返回结果：不重做模块、不改 plan/state.json、不记验收；不过的模块怎么重做由调用方的 .zs 写（见 plan/build.zs）。含上传的接口暂跳过并记备注。
每个不过的接口一条 item（issue = 方法 路径 + 直接调用与 HTTP 的差异原文）；完整结果存 out/smoke_<n>.json / .txt（n 接着已有的往后排）。
返回 {count, items, failed:[{module,reason}], failed_text, notes, notes_text, summary, files}；failed 每个不过的模块一条（reason 是它所有问题的原文），
failed_text 是「模块：原因」一行一个；没有代码时跳过（count=0，没有 files）。
方式：旧参数，只认 核查（等同默认），其他值报错。
多人模式（登录 / 角色）留给 A3，这里先不开登录。
例如 设 r = 接口冒烟
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 接口冒烟(方式: str = "") -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _v3ctx as X
    from tools.dslagent.v3 import planning as PL, regress as RG
    if 方式 not in ("", "核查"):
        X.fail(f"接口冒烟：方式只认 核查（现在默认就是只检查），不认「{方式}」")
    c = X.ctx()
    try:
        top = PL.current_top(c)
    except ValueError:
        return {"count": 0, "items": [], "failed": [], "failed_text": "", "notes": [], "notes_text": "", "summary": "还没有 plan/top.zs，跳过"}
    return RG.audit_smoke(c, top)
