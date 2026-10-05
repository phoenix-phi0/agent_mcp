# -*- coding: utf-8 -*-
"""测试用的建库和导入。

测试要的只是「库里有数据」。以前直接调 Python 导入器，那条路现在没人走了
——导入改成了 DSL（kg/routes/kg_import2.zs、word_import.zs）。测试再走老路
的话，验证的是一条死路：DSL 版哪天坏了，测试照样全绿。

所以统一从这里走接口。不起服务也能调：Flask 的测试客户端打的是同一段代码。
"""

import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

KG = ROOT / "kg"


def make_ws(tmp: Path, with_content: bool = True) -> Path:
    """照着 kg 项目搭一个临时工作区，建好表。"""
    from tools.entity import render_sql

    # scripts/ 是接口用「执行」调的子脚本（做题的出题部分），漏了的话那几个
    # 接口报「找不到脚本」
    dirs = ("entities", "queries", "routes", "scripts") + (("content",) if with_content else ())
    for d in dirs:
        shutil.copytree(KG / d, tmp / d)
    if not with_content:
        (tmp / "content").mkdir()

    text = "\n\n".join(f.read_text(encoding="utf-8")
                       for f in sorted((tmp / "entities").glob("*.entity")))
    con = sqlite3.connect(tmp / "app.db")
    con.executescript(render_sql(text, strict=True))
    # .entity 表达不了多列唯一，跟 py -m kg setup 里那步一致
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_mastery"
                " ON mastery(learner, point)")
    con.commit()
    con.close()
    return tmp


def client(ws: Path):
    from gen.project import make_app
    app, _ = make_app(ws, real=False)
    return app.test_client()


def import_graph(ws: Path) -> dict:
    """导入知识点、条目、边、对照。走 DSL 接口，跟 py -m kg 同一条路。"""
    return client(ws).post("/kg/import2", json={"form": {}}).get_json() or {}


def import_words(ws: Path, file: str = "content/words.jsonl") -> dict:
    return client(ws).post("/word/import2",
                           json={"form": {"file": file}}).get_json() or {}
