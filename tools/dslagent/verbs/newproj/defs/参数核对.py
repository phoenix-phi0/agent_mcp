"""参数核对（程序，不调模型）：routes 下的 zs 里每个 查询 / 查一行 / 查一值 / 写库 / 查询表 / 查一行表 / 查一值表 / 写库表 调用，
找出它用的 queries/<名>.sql 里的 :参数，检查每个参数有来源——调用处具名参数（k={v}，{v} 本身也要有来源）、{request} 里接口「入参」声明的字段
（加上路由器注入的 current_user / current_role / auth_mode / 身份变量）、之前 设 过的 {对象.字段}。查不到来源 = 不过，msg 点名接口、sql、缺的参数。
参数：文件（路径或用 | 隔开的几个路径，相对项目目录）、接口声明（可选：{路径: [入参…]} 的 JSON，或清单接口项列表）。
没声明入参的接口，{request} 里除路由器注入的之外一个字段都不认（宁严勿松）。返回 {ok, msg, 检查数}。
"""
import sys
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 参数核对(文件: str = "", 接口声明=None) -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _gen as G
    import _params as P
    if G.is_dry():
        return {"ok": "是", "msg": "（空跑）未真的核对", "checked": 0}
    root = Path(WORKSPACE).resolve()
    decl, err = P.declared(接口声明)
    if err:
        return {"ok": "否", "msg": err, "checked": 0}
    errs, n = [], 0
    for rel in [x.strip() for x in str(文件 or "").split("|") if x.strip()]:
        p, e = G.sandbox_resolve(root, rel)
        if e:
            return {"ok": "否", "msg": e, "checked": n}
        if not p.is_file():
            errs.append(f"{rel} 不存在")
            continue
        e2, k = P.check_text(p.read_text(encoding="utf-8", errors="replace"), rel, root / "queries", decl, P.identity_vars(root))
        errs += e2
        n += k
    return {"ok": "否" if errs else "是", "msg": "；".join(errs) if errs else f"{n} 处调用的参数都有来源", "checked": n}
