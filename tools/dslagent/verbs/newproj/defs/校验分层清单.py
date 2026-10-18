"""校验「分层清单」（--layered 模板第一步模型的输出）。参数：清单文本（可带围栏）或已解析的对象；第 2 个参数（可选）需求原文。
返回 {ok, errors, 模板, 角色, 角色模板, 数量, 调用上限, 规则表, 实体（拓扑序）, 查询, 接口, 界面}；errors 用「；」连接，可直接嵌进重写提示词。
规则：路径唯一、命名合规（entities/<实体>.entity、queries/<实体>_*.sql、routes/<实体>.zs 或 <实体>_*.zs、ui/*.ui）；sql 名以实体名为前缀且全局唯一
（不与 gen 自带的 <实体>_list/one/insert/update/delete 重名）；用sql 都在查询层里（也可以是 gen 自带的那五条）、用接口都在接口层里（也可以是 gen 自带的 CRUD 路径）；
每条规则至少分配到一个查询或接口项；接口都要有「入参」列表；有角色→private；实体关联无环（顺序见返回的「实体」）。
调用上限 = 2 + 4×文件数（实体 / 有 sql 的查询项 / 接口文件 / 界面文件）。
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 校验分层清单(清单: str = "", 需求: str = "") -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _layer as L
    r = L.validate(清单, 需求)
    r["errors"] = "；".join(r["errors"])
    r["ok"] = "是" if r["ok"] else "否"
    return r
