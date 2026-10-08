# -*- coding: utf-8 -*-
"""知识图谱的教师端桌面入口：双击就开教师端窗口（/teacher）。

等于 `pythonw kg/app.pyw --teacher`，逻辑全在 app.pyw，这里只补一个参数。
默认单人模式；多人加 --login，先 `py -m kg create-teacher <用户名>` 建教师账号。
"""

import runpy
import sys
from pathlib import Path

if __name__ == "__main__":
    sys.argv.insert(1, "--teacher")
    # 按路径跑 app.pyw（.pyw 不能 import）；它自己按 __file__ 定位 kg/ 和仓库根，
    # 双击时工作目录是哪儿都一样
    runpy.run_path(str(Path(__file__).resolve().parent / "app.pyw"), run_name="__main__")
