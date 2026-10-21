"""全量回归：对有代码的模块重新跑一次「加载检查 + 比对约定 + 跑用例」（含已完成、约定 hash 没变的），只检查、只返回结果：
不重做模块、不改 plan/state.json、不记验收。不过的模块怎么重做由调用方的 .zs 写（plan/build.zs 末尾就是：检查 → 按依赖分层重做 → 再检查，最多 2 轮）。
返回 {count, items:[{issue,modules,basis}], failed:[{module,reason}], failed_text, summary, code_modules:[{module,files}]}；failed 每个不过的模块一条（reason 是失败原文），
failed_text 是「模块：原因」一行一个；没有代码时 count=0、summary 写「还没有代码，跳过」、code_modules=[]。
code_modules 是有代码的模块，files = 派任务 的入参列表（contracts/<模块>.md + 该模块代码文件，超 400 行的文件按「文件:起-止」切段，每个文件最多 5 段），核查.zs 用它对每个有代码的模块派代码核查。
方式：旧参数，只认 核查（等同默认），其他值报错。
没有 plan/top.zs → 跳过（count=0）；plan/top.zs 在但有问题 → 终止 失败（不当作没有代码）。
例如 设 r = 全量回归
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 全量回归(方式: str = "") -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _v3ctx as X
    from tools.dslagent.v3 import regress as RG
    if 方式 not in ("", "核查"):
        X.fail(f"全量回归：方式只认 核查（现在默认就是只检查），不认「{方式}」")
    c = X.ctx()
    top = X.top_or_none(c)
    if top is None:
        return {"count": 0, "items": [], "failed": [], "failed_text": "", "summary": "还没有 plan/top.zs，跳过", "code_modules": []}
    return RG.audit_regression(c, top)
