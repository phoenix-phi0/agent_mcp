# -*- coding: utf-8 -*-
"""生成 tests/ 下的待测应用。

    cd mcp
    py data/tests/gen.py

把 index.html / style.css / app.js 写到 fixture.ui 旁边，然后：

    cd data/tests
    npm install vue@3 jsdom     # 只需一次
    node test_page.js

字段表和选项跟 test_page.js 的断言是绑定的，改一处要改两处。
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent.parent          # mcp/
sys.path.insert(0, str(BASE))

from tools.ui import compile_ui    # noqa: E402

# 类型故意铺开：文本 / 长文本 / 枚举 / 日期 / 布尔 五种都占上，
# 断言里逐个对照生成的控件。
FIELDS = {
    "title": "文本",
    "body": "长文本",
    "status": {"type": "枚举", "required": True},
    "published_at": "日期",
    "featured": "布尔",
    "slug": "文本",
}

OPTIONS = {
    "title": "文章管理",
    "options_map": {"status": ["draft", "published", "archived"]},
    # 两行：一行字段齐全，一行有空值，顺便验证空值不炸
    "rows": [
        {"title": "第一篇", "status": "published", "published_at": "2026-01-15"},
        {"title": "草稿", "status": "draft", "published_at": ""},
    ],
}


def main() -> int:
    text = (HERE / "fixture.ui").read_text(encoding="utf-8")
    r = compile_ui(text, backend="vue", fields=FIELDS,
                   require_bind=True, options=OPTIONS)

    if r["issues"]:
        print("有问题：")
        for i in r["issues"]:
            print("  -", i)

    for name, content in r["result"]["files"].items():
        (HERE / name).write_text(content, encoding="utf-8")
        print(f"  {name}  {len(content)} 字节")

    print("\n接着跑：cd data/tests && node test_page.js")
    return 1 if r["issues"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
