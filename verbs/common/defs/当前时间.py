"""取当前本地时间。例如 设 t = 当前时间 → 2026-10-19 12:00:00；当前时间 日期 → 2026-10-19；当前时间 时间戳 → 整数秒"""
import os
from datetime import datetime

FORMATS = ("日期", "时间戳")


def 当前时间(格式: str = "") -> str:
    # 环境变量 DSL_NOW（YYYY-MM-DD HH:MM:SS，或只有日期）设了就用它：
    # 测试要的是固定值，不能让断言跟着墙上的钟走
    fixed = os.environ.get("DSL_NOW", "").strip()
    if fixed:
        try:
            now = datetime.strptime(fixed, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            try:
                now = datetime.strptime(fixed, "%Y-%m-%d")
            except ValueError:
                raise ValueError(f"当前时间：环境变量 DSL_NOW「{fixed}」格式应为 YYYY-MM-DD HH:MM:SS")
    else:
        now = datetime.now()
    fmt = (格式 or "").strip()
    if fmt == "":
        return now.strftime("%Y-%m-%d %H:%M:%S")
    if fmt == "日期":
        return now.strftime("%Y-%m-%d")
    if fmt == "时间戳":
        return str(int(now.timestamp()))
    raise ValueError(f"当前时间：格式「{fmt}」不认识，可用：日期 / 时间戳（不写就是 年-月-日 时:分:秒）")
