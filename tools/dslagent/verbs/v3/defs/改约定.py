"""改约定 <模块> <改动条目>：不在这里调模型，只登记到 ctx.pending_contracts[模块]（累积多条，换行连接）；
落实修改 时带着「上一版 + 条目」走 规划一份 的强制问题通道，只跑程序检查，不逐份复核。
模块不在 plan/top.zs 里、也不是本计划新增的（看 ctx.pending_contracts 是否已经登记过「新增模块」）就 终止 失败。
例如 改约定 progress 加一个按知识点统计的接口
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 改约定(模块: str, 改动条目: str) -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _v3ctx as X
    from tools.dslagent.v3 import top as VT
    c = X.ctx()
    name = (模块 or "").strip()
    if not name:
        X.fail("改约定要写模块名")
    top_text = c.top_path().read_text(encoding="utf-8") if c.top_path().is_file() else ""
    top = VT.parse(top_text)[0] if top_text else {"模块": []}
    live = {m["名"] for m in top["模块"]}
    if name not in live and name not in c.pending_contracts:
        X.fail(f"改约定的模块「{name}」不在 plan/top.zs 里（也不是本计划新增的）")
    note = (改动条目 or "").strip()
    old = c.pending_contracts.get(name) or ""
    c.pending_contracts[name] = (old + ("\n" if old else "") + f"- {note}") if note else old
    c.log("修改计划", 事件="改约定", 模块=name, 条目=note)
    return {"模块": name}
