# -*- coding: utf-8 -*-
"""JSON 字面量里「"{变量}"」插值自动做 JSON 转义。

    cd /workspace/agent_mcp && .venv/bin/python tests/dsl/test_json_literal.py

`设 x = {"stem": "{q.stem}"}` 这类右值，引号里的 {变量} 值含换行、双引号、反斜杠、
制表符时，原样插入会让字面量解析失败、整体退化成文本。现在位于 JSON 字符串引号之内的
{变量} 按 json.dumps(str(v))[1:-1] 转义；字面量外的 {变量}、引号外的 {对象} 整体插入不变。
"""

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.dsl import DSLEngine  # noqa: E402

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


def run(script, **v):
    e = DSLEngine(client=None, workdir=tempfile.gettempdir(), verbose=False)
    e.vars.update(v)
    e.run(script)
    return e


SPECIAL = {"换行": "a\nb\n", "双引号": 'say "hi"', "反斜杠": "c:\\x\\n", "制表符": "a\tb",
           "中文": "你好，世界", "普通值": "plain", "混合": 'q"\\\n\t你'}

print("字符串值：字面量能解析、字段字节级一致")
for name, v in SPECIAL.items():
    e = run('设 x = {"stem": "{v}", "n": 1}\n设 y = {x.stem}\n设 z = {x.n}\n', v=v)
    x = e.vars["x"]
    check(isinstance(json.loads(x), dict) and json.loads(x)["stem"] == v, f"{name}：json.loads 后 stem 一致")
    check(e.vars["y"] == v and e.vars["z"] == 1, f"{name}：{{x.stem}} 取回原值")
    if name == "普通值" or name == "中文":
        check(x == json.dumps({"stem": v, "n": 1}, ensure_ascii=False).replace('":', '": ').replace(',"', ', "')
              or x == '{"stem": "%s", "n": 1}' % v, f"{name}：展开结果逐字不变")

print("嵌套对象、数组里的字符串项、多个变量")
v = 'q"\n'
e = run('设 x = {"a": {"b": "{v}"}, "l": ["{v}", "z{v}"], "k": "{v}-{w}"}\n', v=v, w="\\")
d = json.loads(e.vars["x"])
check(d["a"]["b"] == v and d["l"] == [v, "z" + v] and d["k"] == v + "-\\", "嵌套 / 数组项 / 同一串多个变量")
e = run('设 x = [{"t": "{v}"}, "{v}"]\n', v=v)
check(json.loads(e.vars["x"]) == [{"t": v}, v], "顶层数组")

print("非字符串值在引号内：转文本再转义")
dd = {"s": 'a"\n', "n": 3}
e = run('设 x = {"n": "{num}", "o": "{d}", "b": "{f}"}\n', num=5, d=dd, f=True)
x = json.loads(e.vars["x"])
check(x["n"] == "5" and x["o"] == json.dumps(dd, ensure_ascii=False, separators=(",", ":")) and x["b"] == "是",
      "数字 / 对象 / 布尔 在引号内变成转义后的文本")

print("{对象} 整体插入（引号外）不变")
e = run('设 x = {"o": {d}, "k": "{v}"}\n设 y = {x.o.s}\n', d=dd, v="1\n2")
check(e.vars["y"] == 'a"\n' and json.loads(e.vars["x"])["o"] == dd and json.loads(e.vars["x"])["k"] == "1\n2",
      "{d} 引号外仍整体插入且 {x.o.s} 取到原值")

print("字面量外的 {变量} 不转义")
v = 'a"\nb\\'
e = run('设 m = 他说 "{v}" 然后\n设 j = 值：{v}\n设 k = "{v}"\n设 l = 说 {"a": "{v}"} 完\n', v=v)
check(e.vars["m"] == '他说 "%s" 然后' % v and e.vars["j"] == "值：" + v and e.vars["k"] == '"%s"' % v,
      "普通文本里的引号和变量原样")
check(e.vars["l"] == '说 {"a": "%s"} 完' % v, "不以 { 开头的文本里即使长得像 JSON 也不转义")
e = run('设 t = {不是 JSON 的 "{v}" 文字}\n', v=v)
check(e.vars["t"] == '{不是 JSON 的 "%s" 文字}' % v, "以 { 开头但不是 JSON：退回原样展开")

print("返回 的字面量同样转义")
e = run('返回 {"msg": "{v}"}\n', v=v)
check(e.returned is not None and e.returned[0] == {"msg": v}, "返回 {…} 得到字典")

print("设 x.字段 对字面量文本不再整体换掉")
e = run('设 x = {"a": "{v}"}\n设 x.b = 1\n', v="p\nq")
check(e.vars["x"] == {"a": "p\nq", "b": "1"}, "字面量文本的头部变量按结构写字段")
e = run('设 s = 你好\n设 s.b = 1\n')
check(e.vars["s"] == {"b": "1"}, "普通文本头部仍换成字典（行为不变）")

print("设 x.字段 的头部是列表文本")
e = run('设 x = []\n设 x.b = 1\n')
check(e.vars["x"] == {"b": "1"}, "空列表文本 + 非下标字段：换成字典（同 3acd215 之前）")
e = run('设 x = [1,2]\n设 x.b = 1\n')
check(e.vars["x"] == {"b": "1"}, "[1,2] + 非下标字段：换成字典")
e = run('设 x = [1,2]\n设 x.0 = 9\n')
check(e.vars["x"] == ["9", 2], "[1,2] + 下标 0：按列表改")
e = run('设 x = {"a": 1}\n设 x.b = 2\n')
check(e.vars["x"] == {"a": 1, "b": "2"}, "字典文本头部保留原字段")

print(f"\n通过 {passed}，失败 {failed}")
sys.exit(1 if failed else 0)
