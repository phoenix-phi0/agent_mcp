"""plan2 读改测.zs 专用：把几段文本拼成结果字典（子脚本「返回」结构用；文本里有引号换行也不怕）。
例如 设 out = 组结果 {outcome} {rounds} {msg} {tsum} {reason} {log} [{need}]
plan5：多一个可选的 need（outcome=缺原文 时缺的位置）。"""


def 组结果(outcome: str = "", rounds: str = "", msg: str = "", test: str = "", reason: str = "", log: str = "",
          need: str = "") -> dict:
    return {"outcome": outcome, "rounds": rounds, "last": {"msg": msg, "test": test}, "reason": reason, "log": log,
            "need": "" if need in ("无", None) else need}
