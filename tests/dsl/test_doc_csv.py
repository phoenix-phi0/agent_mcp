# -*- coding: utf-8 -*-
"""doc 包「读文档」收 csv / tsv（E4，见 K124 设计 §10）。

    cd /home/ysc/mcp && .venv/bin/python tests/dsl/test_doc_csv.py

  一、直接调 read_document：带 BOM 的 UTF-8（Excel 另存的那种）BOM 去掉、
      中文表头原样、CRLF 换成 \\n、GBK 的也认得、空文件不算错、tsv 同样收、
      xlsx 照旧不收（报错里列出能收的）
  二、在脚本里用：用包 doc、设 d = 读文档 x.csv，取到 text / kind / chars；
      路径越界照旧拦
"""

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools import packs                                # noqa: E402
from tools.dsl import DSLEngine                        # noqa: E402
from tools.mock import MockClient                      # noqa: E402

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


def load_docmod():
    import importlib.util
    spec = importlib.util.spec_from_file_location("doc_verbs", ROOT / "verbs/doc/_verbs.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    doc = load_docmod()
    tmp = Path(tempfile.mkdtemp(prefix="doc_csv_"))
    rows = "姓名,班级,得分\r\n张三,一班,88\r\n李四,二班,\r\n"

    print("一、直接调 read_document")
    (tmp / "bom.csv").write_bytes(b"\xef\xbb\xbf" + rows.encode("utf-8"))
    d = doc.read_document(tmp / "bom.csv")
    check(d["kind"] == "csv" and d["error"] == "", f"带 BOM 的 csv 读得了：kind={d['kind']} error={d['error']!r}")
    check(d["text"].startswith("姓名,班级,得分") and "﻿" not in d["text"],
          f"BOM 去掉、中文表头原样：{d['text'][:12]!r}")
    check(d["text"] == "姓名,班级,得分\n张三,一班,88\n李四,二班,\n",
          f"CRLF 换成 \\n、空格子原样保留：{d['text']!r}")
    check(d["paragraphs"] == 3 and d["chars"] == len(d["text"]) and d["pages"] == 0,
          f"行数 {d['paragraphs']}、字数 {d['chars']}、页数 {d['pages']}")

    (tmp / "plain.csv").write_bytes(rows.encode("utf-8"))
    d2 = doc.read_document(tmp / "plain.csv")
    check(d2["text"] == d["text"] and not d2["error"], "不带 BOM 的 UTF-8 结果跟带 BOM 的一样")

    (tmp / "gbk.csv").write_bytes(rows.encode("gbk"))
    d3 = doc.read_document(tmp / "gbk.csv")
    check(d3["text"] == d["text"] and not d3["error"], f"GBK 编码的也认得：{d3['text'][:12]!r}")

    (tmp / "empty.csv").write_bytes(b"")
    e = doc.read_document(tmp / "empty.csv")
    check(e["kind"] == "csv" and e["error"] == "" and e["text"] == ""
          and e["chars"] == 0 and e["paragraphs"] == 0,
          f"空文件不算错：text={e['text']!r} chars={e['chars']} error={e['error']!r}")
    (tmp / "bomonly.csv").write_bytes(b"\xef\xbb\xbf")
    e2 = doc.read_document(tmp / "bomonly.csv")
    check(e2["text"] == "" and e2["error"] == "", f"只有一个 BOM 的也当空文件：{e2['text']!r}")

    (tmp / "a.tsv").write_bytes("学号\t得分\n1\t90\n".encode("utf-8-sig"))
    t = doc.read_document(tmp / "a.tsv")
    check(t["kind"] == "tsv" and t["text"] == "学号\t得分\n1\t90\n" and not t["error"],
          f"tsv 同样收：{t['text']!r}")

    (tmp / "UP.CSV").write_bytes(rows.encode("utf-8"))
    u = doc.read_document(tmp / "UP.CSV")
    check(u["kind"] == "csv" and not u["error"], "扩展名大写 .CSV 也认")

    (tmp / "bin.csv").write_bytes(b"PK\x03\x04\x00\x00\x00binary")
    b = doc.read_document(tmp / "bin.csv")
    check("二进制" in b["error"], f"改了扩展名的二进制文件报人话：{b['error']!r}")

    (tmp / "a.xlsx").write_bytes(b"PK\x03\x04")
    x = doc.read_document(tmp / "a.xlsx")
    check("不支持 .xlsx" in x["error"] and "csv" in x["error"],
          f"xlsx 照旧不收，报错里列出能收 csv：{x['error']!r}")

    print("二、在脚本里用")
    reg = packs.registry(["common", "doc"], tmp, cache=False)
    eng = DSLEngine(client=MockClient(offline=True), workdir=tmp, verbose=False,
                    verbs=reg, verbs_root=packs.verbs_root())
    eng.run("设 d = 读文档 bom.csv\n设 k = {d.kind}\n设 n = {d.chars}\n")
    got = eng.vars.get("d") or {}
    check(isinstance(got, dict) and got.get("text", "").startswith("姓名,班级,得分")
          and str(eng.vars.get("k")) == "csv" and str(eng.vars.get("n")) == str(len(d["text"])),
          f"设 d = 读文档 bom.csv：kind={eng.vars.get('k')} chars={eng.vars.get('n')}")
    eng.run("设 e = 读文档 empty.csv\n")
    check((eng.vars.get("e") or {}).get("error") == "" and (eng.vars.get("e") or {}).get("text") == "",
          "脚本里读空 csv：error 为空、text 为空")
    (tmp.parent / f"{tmp.name}_outside.csv").write_bytes(rows.encode("utf-8"))
    msg = ""
    try:
        eng.run(f"设 z = 读文档 ../{tmp.name}_outside.csv\n")
    except Exception as ex:
        msg = str(ex)
    finally:
        (tmp.parent / f"{tmp.name}_outside.csv").unlink()
    check("越界" in msg, f"路径越界照旧拦（工作目录外真有这个 csv）：{msg[:40]!r}")

    print(f"\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
