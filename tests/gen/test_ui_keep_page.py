# -*- coding: utf-8 -*-
"""K190：.ui 的「列 … 不折行」「浮层 … 关后不载入」。
没用的 .ui 生成物里一个字都没有（对照），用了的才有；浮层带的参数进映射，刷新后关浮层靠它算回地址。"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.ui import compile_ui, parse  # noqa: E402

fails = total = 0


def check(ok, msg, extra=""):
    global fails, total
    total += 1
    fails += 0 if ok else 1
    print(("  ✓ " if ok else "  ✗ ") + msg + ("" if ok else f" :: {extra}"))


def build(ui):
    r = compile_ui(parse(ui), backend="vue", fields={}, require_bind=False,
                   options={"title": "t", "options_map": {}, "endpoints": {"page_one": "/p/one", "full_one": "/p/full"}})
    return r["result"]["files"]


PLAIN = """界面 自定义 甲 载入 page_one
  列表 表 绑 rows
    列 at 时间
    列 text 内容
    动作 open_full 打开 全文 带 rid 看全文
  结束
  浮层 全文 载入 full_one
    动作 close_full 次要 关闭 返回
  结束
结束
"""
FLAGGED = PLAIN.replace("列 at 时间", "列 at 不折行 时间").replace("浮层 全文 载入", "浮层 全文 关后不载入 载入")

a, b = build(PLAIN), build(FLAGGED)
html_a = "".join(v for k, v in a.items() if k != "style.css")
html_b = "".join(v for k, v in b.items() if k != "style.css")
for word in ("keepPageOverlays", "pageLoaded", "prevOverlay", "cell-nowrap"):
    check(word not in html_a and word not in a.get("style.css", ""), f"没用修饰：生成物没有 {word}")
check('<th class="cell-nowrap">时间</th>' in html_b, "用了：表头带 class", "")
check('<td class="cell-nowrap">{{ row.at }}</td>' in html_b, "用了：单元格带 class")
check("<td>{{ row.text }}</td>" in html_b, "别的列不受影响")
check(".cell-nowrap { white-space:nowrap; }" in b["style.css"], "用了：样式里有 nowrap")
m = re.search(r"const keepPageOverlays = (\{.*?\});", html_b)
check(m and json.loads(m.group(1)) == {"全文": ["rid"]}, "映射里是浮层名和它带的参数", m.group(1) if m else "")
check("不折行 时间" not in html_b and ">不折行<" not in html_b and "全文 关后不载入" not in html_b, "修饰词没进显示文字（模板注释里提到它们不算）")
print(f"通过 {total - fails}，失败 {fails}")
sys.exit(1 if fails else 0)
