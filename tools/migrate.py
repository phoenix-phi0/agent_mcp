# -*- coding: utf-8 -*-
"""老库只加不改：实体里有、库里还没有的表、列、索引补上，别的一律不碰。

    from tools.migrate import migrate_additive
    r = migrate_additive("kg/app.db", "kg/entities")
    # {"tables": [...], "columns": ["表.列", ...], "indexes": [...], "warnings": [...]}

项目里开这个开关：路由目录任意一个 .zs 的顶层（接口块外面）写一行

    迁移 只加

`gen run`、`python -m tools.dsl_http` 起服务前、`ensure_db` 碰到已有的库时就会
跑一遍。不写这行的项目行为不变：库在就不动（见 gen/project.py 的 ensure_db）。

为什么要有它：ensure_db 只在库不存在时建表，实体后加的表、列，已有的库里
不会凭空出现，接口一查就是 no such table / no such column。重新生成建表
语句又会先 DROP 全部表——学习记录这类真数据不能走那条路。

只做三件事，都从实体渲染出来的建表语句里取，不手抄（手抄的跟新建库渲染的
哪怕差一点——类型、默认值、外键——一边正常一边出怪问题，很难查）：

  - CREATE TABLE IF NOT EXISTS    库里没有的表，连同它的索引
  - ALTER TABLE ADD COLUMN        已有的表里缺的列
  - CREATE INDEX IF NOT EXISTS    缺的索引（库里已经有一个同表、同列、同唯一性
                                  的索引，名字不一样也算有，不重复建）

**绝不 DROP、不重建、不改已有的列。** 实体跟库对不上、又不是「缺了补上」能
解决的（列类型、必填、默认值、主键不一样，库里多出实体没有的列，SQLite 的
ADD COLUMN 加不了的列：主键、唯一、必填又没默认值、默认值是表达式），只记一条
warning 交给人看，表原样不动——那些得人决定怎么迁，自动做就可能丢数据。

对比列定义不解析 SQL 文本：把渲染出来的整份建表语句在内存库里跑一遍，两边
都用 PRAGMA table_info / index_list 读，比的是 SQLite 自己认的结果。
"""

import re
import sqlite3
from pathlib import Path

# 路由目录里打开这个开关的那一行（顶层，接口块外面）
SWITCH_RE = re.compile(r"^迁移\s+只加\s*$")

# 列定义行开头是这些词的是表级约束，不是列
_TABLE_CONSTRAINTS = {"FOREIGN", "UNIQUE", "CHECK", "PRIMARY", "CONSTRAINT"}


def entities_text(entities) -> str:
    """实体目录（读其中所有 .entity）、单个 .entity 文件，或者实体文本本身。"""
    if isinstance(entities, Path) or (isinstance(entities, str) and "\n" not in entities
                                      and Path(entities).exists()):
        p = Path(entities)
        if p.is_dir():
            return "\n\n".join(f.read_text(encoding="utf-8")
                               for f in sorted(p.glob("*.entity")))
        return p.read_text(encoding="utf-8")
    return str(entities)


def _statements(sql: str):
    """渲染结果按语句切开，去掉注释行。返回 (建表 {表: 语句}, 建索引 [语句])。

    渲染结果是「DROP 一串 + CREATE TABLE 一串 + CREATE INDEX 一串」，这里只挑
    CREATE 的。DROP 一句都不执行。
    """
    tables, indexes = {}, []
    for stmt in re.split(r";\s*\n", sql + "\n"):
        body = "\n".join(l for l in stmt.splitlines()
                         if l.strip() and not l.strip().startswith("--")).strip().rstrip(";")
        m = re.match(r"CREATE TABLE (\w+)", body)
        if m:
            tables[m.group(1)] = body
        elif re.match(r"CREATE (UNIQUE )?INDEX ", body):
            indexes.append(body)
    return tables, indexes


def _column_defs(create: str) -> dict:
    """建表语句里每列的定义原文 {列名: 定义}，ALTER TABLE ADD COLUMN 照抄用。"""
    m = re.search(r"\((.*)\)\s*$", create, re.S)
    out = {}
    for line in (m.group(1) if m else "").splitlines():
        col = line.strip().rstrip(",")
        name = col.split(" ", 1)[0]
        if re.fullmatch(r"\w+", name) and name.upper() not in _TABLE_CONSTRAINTS:
            out[name] = col
    return out


def _columns(con, table: str) -> dict:
    """{列名: (类型, 必填, 默认值, 主键序号)}"""
    return {r[1]: ((r[2] or "").upper(), r[3], r[4], r[5])
            for r in con.execute(f'PRAGMA table_info("{table}")')}


def _index_shapes(con, table: str) -> dict:
    """{索引名: (是否唯一, (列, ...))}，含 UNIQUE 约束和主键自带的索引。"""
    out = {}
    for r in con.execute(f'PRAGMA index_list("{table}")'):
        cols = tuple(c[2] for c in con.execute(f'PRAGMA index_info("{r[1]}")'))
        out[r[1]] = (bool(r[2]), cols)
    return out


def _cannot_add(definition: str) -> str:
    """SQLite 的 ADD COLUMN 加不了的列，返回原因；加得了返回空串。"""
    up = definition.upper()
    if "PRIMARY KEY" in up:
        return "是主键"
    if re.search(r"\bUNIQUE\b", up):
        return "带唯一约束"
    if "NOT NULL" in up and "DEFAULT" not in up:
        return "必填又没有默认值，已有的行填不出值"
    return ""


def _describe(shape) -> str:
    kind, notnull, default, pk = shape
    bits = [kind or "无类型"]
    if notnull:
        bits.append("NOT NULL")
    if default is not None:
        bits.append(f"DEFAULT {default}")
    if pk:
        bits.append("主键")
    return " ".join(bits)


def migrate_additive(db, entities) -> dict:
    """按实体给已有的库补表、补列、补索引，只加不改。见模块说明。

    db 是库文件路径，不存在就什么都不做（建新库是 ensure_db 的事）。entities
    是实体目录、.entity 文件或实体文本。重复执行是幂等的：第二次什么都不补。
    返回 {"tables", "columns", "indexes", "warnings"}，前三个是这次补了什么。
    """
    from .entity import render_sql

    result = {"tables": [], "columns": [], "indexes": [], "warnings": []}
    db = Path(db)
    if not db.is_file():
        return result
    sql = render_sql(entities_text(entities), strict=True)
    tables, indexes = _statements(sql)
    warn = result["warnings"].append

    # 照实体建一个内存库当「应该长什么样」
    want = sqlite3.connect(":memory:")
    want.executescript(sql)
    con = sqlite3.connect(db)
    try:
        have = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        for table, create in tables.items():
            if table not in have:
                con.execute(create.replace("CREATE TABLE ", "CREATE TABLE IF NOT EXISTS ", 1))
                result["tables"].append(table)
                continue
            got, need = _columns(con, table), _columns(want, table)
            defs = _column_defs(create)
            for name, shape in need.items():
                if name in got:
                    if got[name] != shape:
                        warn(f"{table}.{name}：库里是「{_describe(got[name])}」，实体是"
                             f"「{_describe(shape)}」，没改（改列要重建表，得人来定）")
                    continue
                why = _cannot_add(defs.get(name, ""))
                if why:
                    warn(f"{table}.{name}：库里没有这一列，但它{why}，ADD COLUMN 加不了，没加")
                    continue
                try:
                    con.execute(f'ALTER TABLE "{table}" ADD COLUMN {defs[name]}')
                except sqlite3.OperationalError as e:
                    warn(f"{table}.{name}：补列失败（{e}），没加")
                    continue
                result["columns"].append(f"{table}.{name}")
            for name in got.keys() - need.keys():
                warn(f"{table}.{name}：实体里没有这一列，库里留着没删")

        for stmt in indexes:
            m = re.match(r"CREATE (UNIQUE )?INDEX (?:IF NOT EXISTS )?(\w+)\s+ON (\w+)\(", stmt)
            name, table = m.group(2), m.group(3)
            shape = _index_shapes(want, table)[name]
            existing = _index_shapes(con, table)
            if name in existing:
                if existing[name] != shape:
                    warn(f"索引 {name}：库里的跟实体的不一样，没动")
                continue
            if shape in existing.values():
                continue        # 同表同列同唯一性的索引已经有了，只是名字不同
            try:
                con.execute(stmt if "IF NOT EXISTS" in stmt else
                            stmt.replace("INDEX ", "INDEX IF NOT EXISTS ", 1))
            except sqlite3.IntegrityError as e:
                # 唯一索引建不起来：库里已经有重复的行。不删数据，交给人
                warn(f"索引 {name}：建不起来（{e}），库里已有重复的行，没动")
                continue
            result["indexes"].append(name)
        con.commit()
        return result
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
        want.close()


def report(result: dict) -> list:
    """migrate_additive 的结果写成给人看的几行。什么都没补、也没有警告时是空列表。"""
    lines = []
    if result.get("tables"):
        lines.append(f"  已有的库里补建了表：{'、'.join(result['tables'])}")
    if result.get("columns"):
        lines.append(f"  已有的表里补了列：{'、'.join(result['columns'])}")
    if result.get("indexes"):
        lines.append(f"  补了索引：{'、'.join(result['indexes'])}")
    lines.extend(f"  [迁移警告] {w}" for w in result.get("warnings") or [])
    return lines


def switch_on(routes_dir) -> bool:
    """路由目录里有没有哪个文件在顶层写了「迁移 只加」。跟「认证 必须」同一种开关。"""
    from .dsl_http import top_level_flag
    return top_level_flag(routes_dir, SWITCH_RE)


def migrate_project(root, routes_dir=None, db_name: str = "app.db") -> list:
    """项目目录：开了开关就按 entities/ 补 app.db，返回给人看的几行；没开返回空列表。

    routes_dir 不给就是 root/routes（gen 的项目都是这样）；dsl_http 的路由目录
    可以另给。
    """
    root = Path(root)
    if not switch_on(Path(routes_dir) if routes_dir else root / "routes"):
        return []
    return report(migrate_additive(root / db_name, root / "entities"))
