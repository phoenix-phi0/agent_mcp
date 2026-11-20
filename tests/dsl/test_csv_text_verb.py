# -*- coding: utf-8 -*-
"""K196：data 包动词 解析CSV文本（按字符串解析 CSV，不碰文件）。

    cd /workspace/agent_mcp && .venv/bin/python tests/dsl/test_csv_text_verb.py

覆盖：普通、引号内逗号 / 换行、转义引号、CRLF、BOM、首尾空白、空行、只有表头、空文本、
GBK 解码后的中文（含经 doc 包 读文档 读 GBK 文件再解析）、最大行数截断、坏格式不抛异常、
分隔符（制表符 / 分号 / 不合法）、在 DSL 脚本里调用（结构返回、{t.total} 取值）。
"""

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools import packs as PK  # noqa: E402
from tools.dsl import DSLEngine  # noqa: E402
from tools.mock import MockClient  # noqa: E402

passed = failed = 0


def check(ok, msg, detail=None):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg + ("" if ok or detail is None else f"\n      {detail!r}"))


def P(*a):
    return PK.call_verb("解析CSV文本", *a, packs=["data"], workspace=str(ROOT))


def main():
    print("一、基本")
    r = P("姓名,分数,备注\n甲,80,\n乙,90.5,好\n")
    check(r["header"] == ["姓名", "分数", "备注"] and r["rows"] == [["甲", "80", ""], ["乙", "90.5", "好"]]
          and r["total"] == 2 and r["truncated"] == "否" and r["error"] == "", "普通 csv：表头 + 行", r)
    check(r["columns"] == [{"name": "姓名", "values": ["甲", "乙"]}, {"name": "分数", "values": ["80", "90.5"]},
                           {"name": "备注", "values": ["", "好"]}], "columns 按表头逐列", r["columns"])
    check(set(r) == {"header", "rows", "columns", "total", "truncated", "error"}, "返回键齐全", sorted(r))

    print("二、引号")
    r = P('姓名,分数\n"张, 三",80\n"李四",90\n')
    check(r["rows"] == [["张, 三", "80"], ["李四", "90"]] and r["total"] == 2, "引号内逗号不切、外层引号去掉", r["rows"])
    r = P('a,b\n"第一行\n第二行",1\n"x\r\ny",2\n')
    check(r["rows"] == [["第一行\n第二行", "1"], ["x\r\ny", "2"]] and r["total"] == 2, "引号内换行（LF / CRLF）留在格里，不拆行", r["rows"])
    r = P('a,b\n"他说""好""",1\n"""",2\n')
    check(r["rows"] == [['他说"好"', "1"], ['"', "2"]], '转义引号 "" → "', r["rows"])
    r = P('a, b\n1, "x, y"\n')
    check(r["header"] == ["a", "b"] and r["rows"] == [["1", "x, y"]], "逗号后带空格再开引号也认（skipinitialspace）", r)

    print("三、换行、BOM、空白、空行")
    r = P("a,b\r\n1,x\r\n\r\n2,y\r\n")
    check(r["rows"] == [["1", "x"], ["2", "y"]] and r["total"] == 2, "CRLF、中间空行跳过", r)
    r = P("﻿编号,值\n1,2\n")
    check(r["header"] == ["编号", "值"], "开头 BOM 去掉，首列名干净", r["header"])
    r = P("  姓名 ,  分数  \n 甲 , 80 \n")
    check(r["header"] == ["姓名", "分数"] and r["rows"] == [["甲", "80"]], "每格去首尾空白", r)
    r = P("\n\n   \na,b\n\n  \n1,2\n,,\n\n")
    check(r["header"] == ["a", "b"] and r["rows"] == [["1", "2"], ["", "", ""]] and r["total"] == 2,
          "只含空白的行跳过；「,,」仍算一行（与原先按行切一致）", r)

    print("四、只有表头 / 空")
    r = P("a,b\n")
    check(r["header"] == ["a", "b"] and r["rows"] == [] and r["total"] == 0 and r["columns"][0] == {"name": "a", "values": []},
          "只有表头：rows 空、total 0", r)
    r = P("")
    check(r["header"] == [] and r["rows"] == [] and r["total"] == 0 and r["error"] == "", "空文本：全空、不报错", r)
    r = P("  \n\n")
    check(r["header"] == [] and r["total"] == 0, "只有空白：全空", r)

    print("五、GBK 解码后的中文")
    raw = '姓名,分数,评语\n张三,80,"好, 很好"\n李四,90,一般\n'.encode("gbk")
    r = P(raw.decode("gbk"))
    check(r["header"] == ["姓名", "分数", "评语"] and r["rows"][0] == ["张三", "80", "好, 很好"] and r["total"] == 2,
          "GBK 字节解码后的字符串照常解析（动词不碰编码）", r)
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "g.csv").write_bytes(raw)
        dd = PK.call_verb("读文档", "g.csv", packs=["doc"], workspace=td)
        text = dd.get("text") if isinstance(dd, dict) else ""
        r = P(text)
        check(not (isinstance(dd, dict) and dd.get("error")) and r["rows"] == [["张三", "80", "好, 很好"], ["李四", "90", "一般"]],
              "经 doc 包 读文档 读 GBK 文件 → 解析CSV文本：列正确", (dd, r))

    print("六、最大行数")
    big = "n,v\n" + "".join(f"{i},{i * 2}\n" for i in range(1, 5001))
    r = P(big, ",", "200")
    check(len(r["rows"]) == 200 and r["total"] == 5000 and r["truncated"] == "是" and r["rows"][-1] == ["200", "400"]
          and len(r["columns"][1]["values"]) == 200, "5000 行、最大行数 200：只回前 200 行，total 仍是 5000", (len(r["rows"]), r["total"], r["truncated"]))
    r = P(big)
    check(len(r["rows"]) == 5000 and r["truncated"] == "否", "不给最大行数：全部", len(r["rows"]))
    r = P(big, ",", "0")
    check(len(r["rows"]) == 5000, "最大行数 0：全部", len(r["rows"]))
    r = P(big, ",", "abc")
    check(r["rows"] == [] and "最大行数不合法" in r["error"], "最大行数不合法：不抛，error 写明", r["error"])
    r = P(big, ",", "9" * 5000)
    check(r["rows"] == [] and "最大行数不合法" in r["error"], "最大行数是几千位的数字串：不抛（int() 位数上限），error 写明", r["error"][:40])
    r = P(big, ",", "２００")
    check(r["rows"] == [] and "最大行数不合法" in r["error"], "最大行数是全角数字：不合法", r["error"][:40])

    print("七、坏格式不抛异常")
    r = P('a,b\n1,2\n"没闭合,3\n4,5\n')
    check(r["header"] == ["a", "b"] and r["rows"][0] == ["1", "2"] and "CSV 格式有问题" in r["error"] and "已尽力解析" in r["error"],
          "引号没闭合：保留前面的行，error 写明已尽力解析", r)
    r = P('a,b\n"x" y,1\n')
    check(r["rows"] == [["x y", "1"]] and "CSV 格式有问题" in r["error"], "闭合引号后紧跟字符：宽松解析 + error", r)
    r = P('a,b\n"x" ,1\n"y"\t,2\n"z" \n')
    check(r["rows"] == [["x", "1"], ["y", "2"], ["z"]] and r["error"] == "", "闭合引号后只跟空白：不算格式问题", r)
    r = P('a,b\n1,2\n"没闭合,3\n')
    check("第 3 行开始的引号没有闭合" in r["error"], "引号没闭合：error 指出从第几行开始", r["error"])
    r = P('a,b\n"x" y,1\n')
    check("第 2 行：闭合引号后面跟了「y」" in r["error"], "闭合引号后跟字符：error 指出行号和字符", r["error"])
    r = P("a,b\n1,2\n\"" + "长" * 140000 + "\",3\n4,5\n")
    check(r["rows"][0] == ["1", "2"] and "后面没有解析" in r["error"] and "CSV 格式有问题" in r["error"],
          "格子超过 csv 字段长度上限：不抛，保留前面的行，error 写明（不改全局 field_size_limit）", (r["rows"][:1], r["error"][:80]))
    r = P("a,b\n1,2,3\n4\n")
    check(r["rows"] == [["1", "2", "3"], ["4"]] and r["error"] == "" and r["columns"][1]["values"] == ["2", ""],
          "列数不齐不算错：rows 原样，columns 缺的补空串、多的不进", r)

    print("八、分隔符")
    check(P("a\tb\n1\t2\n", "\\t")["rows"] == [["1", "2"]], "\\t 当制表符")
    check(P("a\tb\n1\t2\n", "制表符")["rows"] == [["1", "2"]], "「制表符」当制表符")
    check(P('a;b\n"x;y";2\n', ";")["rows"] == [["x;y", "2"]], "分号分隔 + 引号")
    r = P("a,b\n", "ab")
    check(r["rows"] == [] and "分隔符不合法" in r["error"], "分隔符不合法：不抛，error 写明", r["error"])
    r = P("a,b\n", '"')
    check("分隔符不合法" in r["error"], "分隔符是引号：不合法", r["error"])

    print("九、DSL 脚本里调用")
    script = ('用包 data common\n'
              '设 src = {"s":"名,值\\n\\"甲, 乙\\",1\\n丙,2\\n"}\n'
              '设 t = 解析CSV文本 {src.s}\n'
              '打印 total={t.total}|h0={t.header.0}|c0={t.rows.0.0}|n={t.columns.1.name}\n'
              '遍历 col 于 {t.columns}\n'
              '  打印 col={col.name}:{col.values.0}\n'
              '结束\n'
              '设 t2 = 解析CSV文本 {src.s} , 1\n'
              '打印 t2={t2.total}/{t2.truncated}\n')
    out = DSLEngine(client=MockClient(offline=True), workdir=str(ROOT), verbose=False).run(script)
    check("total=2|h0=名|c0=甲, 乙|n=值" in out and "col=名:甲, 乙" in out and "col=值:1" in out and "t2=2/是" in out,
          "设 t = 解析CSV文本 {text}：返回结构，{t.total} {t.rows.0.0} 可取，遍历 columns", out)

    print(f"\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
