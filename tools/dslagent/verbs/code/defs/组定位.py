"""plan4 定位.zs 专用：把定位结果拼成字典（子脚本「返回」结构用；源码里有引号换行也不怕）。
例如 设 out = 组定位 {outcome} {segs} {src} {note} {kw} {used} {log} {first}
plan6：多一个可选的 first——定位时模型直接给的改法（{edits:[…]}），读改测.zs 第一轮直接应用，不再单独问一次。"""


def 组定位(outcome: str = "", segs: str = "", src: str = "", note: str = "", kw: str = "",
          rounds: str = "", log: str = "", first=None) -> dict:
    out = {"outcome": outcome, "segs": segs, "src": src, "note": note, "kw": kw, "rounds": rounds, "log": log}
    if isinstance(first, str):
        try:
            import json
            first = json.loads(first)
        except ValueError:
            first = {}
    out["first"] = first if isinstance(first, dict) and first.get("edits") else {}
    return out
