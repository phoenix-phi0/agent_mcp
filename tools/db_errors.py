# -*- coding: utf-8 -*-
"""用户造成的数据库错误：翻译成人看得懂的话，带上该回的状态码。

db 包写库时碰到约束冲突（重名、必填为空、关联不存在），不当成服务器
故障：变成 ClientError，路由器在错误链上找到它，就回它的状态码和说明，
而不是 500 加一段 SQLite 原文。

    UNIQUE constraint failed: note.title   →  409  标题已经存在
    NOT NULL constraint failed: note.title →  400  标题不能为空
    FOREIGN KEY constraint failed          →  409  关联的记录不存在，或者……

为什么值得做：状态码 500 的意思是「服务器坏了」，日志里会把重名这种
再正常不过的事当成故障；而 "UNIQUE constraint failed: note.title" 这句话
普通用户看不懂，看懂了也不知道该怎么办。

字段的中文名从项目的 .entity 里取（字段的标签）。取不到就用列名，不影响
状态码。只在出错时读，平时不碰。
"""

import re
import sqlite3
from pathlib import Path


class ClientError(Exception):
    """请求本身有问题，不是服务器故障。status 是该回的 HTTP 状态码。"""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def find_client_error(exc):
    """顺着错误链（from / 上下文）找 ClientError。引擎会一层层包成 DSLError，
    原来的异常挂在 __cause__ 上。"""
    seen = set()
    while exc is not None and id(exc) not in seen:
        if isinstance(exc, ClientError):
            return exc
        seen.add(id(exc))
        exc = exc.__cause__ or exc.__context__
    return None


def _labels(workspace) -> dict:
    """{(表, 列): 字段中文名}，从 workspace/entities/*.entity 读。读不到就空。"""
    try:
        from tools.entity import parse
        files = sorted(Path(workspace, "entities").glob("*.entity"))
        if not files:
            return {}
        out = {}
        for e in parse("\n\n".join(f.read_text(encoding="utf-8") for f in files)):
            for f in e.fields:
                label = getattr(f, "label", "") or ""
                if label:
                    out[(e.name, f.name)] = label
        return out
    except Exception:
        # 翻译是锦上添花：实体文件读不了，就用列名，别让报错本身再出错
        return {}


def _cols(detail: str) -> list:
    """"note.title" 或 "prereq.src, prereq.dst" → [("note","title"), ...]"""
    out = []
    for part in detail.split(","):
        part = part.strip()
        if "." in part:
            t, c = part.split(".", 1)
            out.append((t, c))
    return out


def translate(exc: sqlite3.IntegrityError, workspace) -> ClientError:
    """把一个约束冲突翻译成 ClientError。认不出的也不回 500——约束冲突
    总是数据的问题，给 409 加原文。"""
    msg = str(exc)
    labels = _labels(workspace)
    name = lambda tc: labels.get(tc, tc[1])

    m = re.match(r"UNIQUE constraint failed: (.+)", msg)
    if m:
        cols = _cols(m.group(1))
        if len(cols) == 1:
            return ClientError(f"{name(cols[0])}已经存在，换一个", 409)
        if cols:
            return ClientError("、".join(name(c) for c in cols) + " 的这个组合已经存在", 409)

    m = re.match(r"NOT NULL constraint failed: (.+)", msg)
    if m:
        cols = _cols(m.group(1))
        if cols:
            return ClientError(f"{name(cols[0])}不能为空", 400)

    if msg.startswith("FOREIGN KEY constraint failed"):
        return ClientError("关联的记录不存在，或者这条记录还被别的数据引用着", 409)

    if msg.startswith("CHECK constraint failed"):
        return ClientError("数据不符合要求", 400)

    return ClientError(f"数据冲突：{msg}", 409)
