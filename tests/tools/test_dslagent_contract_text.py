# -*- coding: utf-8 -*-
"""约定检查的「自由文本入参要有带空格 / 换行的用例」（K16c 2a）：模块有自由文本入参的公开函数
    （content / title / *_path / *_text 这些名字），而所有用例的值都不含空格、也不含字面 \n → 报一条；
    「先 文件 内容=…」（可带空格）或任何值里的字面 \n 都算覆盖。不调模型。

    cd /workspace/agent_mcp && .venv/bin/python tests/tools/test_dslagent_contract_text.py
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="dslagent_text_"))
os.environ["DSLAGENT_TMP"] = str(TMP / "tmp")
os.environ["DSLAGENT_DATASET"] = str(TMP / "dataset")
os.environ["DSLAGENT_STATE"] = str(TMP / "state")

from tools.dslagent.packs.dslproj import contract as C  # noqa: E402

PASS = FAIL = 0


def check(cond, msg, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✓ " + msg)
    else:
        FAIL += 1
        print("  ✗ " + msg + (f"\n      {str(extra)[:1500]}" if extra != "" else ""))


def mk(text):
    c, probs = C.parse(text)
    assert not probs, probs
    return c


BASE = """模块 note
依赖 无

## 表
表 note_item
  id 整数 主键
  content 文本 内容

## 函数
公开 函数 保存 content
  返回 {id}
  伪代码 往 note_item 插入一行 content

## 接口
POST /note/save -> 保存

## 用例
用例 保存_简单
  调用 保存 content=你好
  得 id=1
"""


def one(c):
    p = C.text_space_problems(c)
    return p[0] if p else ""


# 1. content 入参、值里没空格 / 换行 → 报
p = one(mk(BASE))
check("content" in p and "空格" in p, "content 入参无覆盖值 → 报", p)

# 2. 「先 文件 内容」带空格 → 不报（哪怕空格不在自由文本函数的直接入参上，模块级覆盖即算）
t = BASE.replace("用例 保存_简单\n  调用 保存 content=你好\n  得 id=1",
                 "用例 保存_文件\n  先 文件 in/a.md 内容=第一课 标题\n  调用 保存 content=x\n  得 id=1")
check(one(mk(t)) == "", "先 文件 内容带空格 → 不报", t)

# 3. 调用值里写字面 \n → 不报
t = BASE.replace("content=你好", "content=第一行\\n第二行")
check(one(mk(t)) == "", "调用值带字面 \\n → 不报", t)

# 4. 库 含 值里带 \n 也算覆盖
t = BASE.replace("  得 id=1", "  库 note_item 含 content=a\\nb")
check(one(mk(t)) == "", "库 含 值带 \\n → 不报", t)

# 5. 没有自由文本入参 → 不报
t = BASE.replace("公开 函数 保存 content", "公开 函数 保存 code").replace("content 文本 内容", "code 文本 代号").replace("content=你好", "code=A").replace("content=x", "code=x").replace("content=a\\nb", "code=a")
check(one(mk(t)) == "", "没有自由文本入参 → 不报", t)

# 6. 只有私有函数有 content → 不报（公开函数 列出 没有自由文本入参）
t = """模块 note
依赖 无

## 表
表 note_item
  id 整数 主键
  content 文本 内容

## 函数
函数 保存 content
  返回 {id}
  伪代码 往 note_item 插入一行 content
公开 函数 列出
  返回 {total}
  伪代码 数 note_item

## 接口
GET /note/list -> 列出

## 用例
用例 列出_空
  调用 列出
  得 total=0
"""
c = mk(t)
check(one(c) == "", "私有函数的 content 不触发", t)

# 7. *_path 入参（文件文本）触发；「先 文件 内容」带 \n 覆盖
t = BASE.replace("公开 函数 保存 content", "公开 函数 导入 file_path") \
       .replace("  content 文本 内容", "  title 文本 标题") \
       .replace("  伪代码 往 note_item 插入一行 content", "  伪代码 读 file_path 按\n  伪代码 往 note_item 插入各行 title") \
       .replace("  调用 保存 content=你好", "  先 文件 in/a.txt 内容=甲\\n乙\n  调用 导入 file_path=in/a.txt")
check(one(mk(t)) == "", "*_path 入参 + 先 文件 内容带 \\n → 不报", t)
t2 = t.replace("内容=甲\\n乙", "内容=甲")
p = one(mk(t2))
check("file_path" in p, "*_path 入参无覆盖 → 报", p)

# 8. 可选入参 content? 也算自由文本
t = BASE.replace("公开 函数 保存 content", "公开 函数 保存 content?").replace("content=你好", "content=你好")
p = one(mk(t))
check("content" in p, "可选 content? 无覆盖 → 报", p)

# 9. check() 全量里包含这条（不是孤立的函数）
c = mk(BASE)
allp = C.check(c, "note", {}, ["note"])
check(any("自由文本" in x for x in allp), "C.check 汇总里出现", allp)

# 10. 「先 数据」的值里带字面 \n 也算覆盖
t = BASE.replace("  调用 保存 content=你好", "  先 数据 note_item content=a\\nb\n  调用 保存 content=你好")
check(one(mk(t)) == "", "先 数据 值带 \\n → 不报", t)

print(f"\nRan {PASS + FAIL} checks: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
