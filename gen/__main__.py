# -*- coding: utf-8 -*-
"""命令行入口。

    py -m gen                      列出有哪些实体
    py -m gen article              看会生成什么
    py -m gen article --write      写盘
    py -m gen --all --write        所有实体
    py -m gen article --check      只跑自检
    py -m gen tpl list|show|diff|where|check|render|new|doc   模板集管理（见 gen/tpl.py）

默认只打印不写盘：生成的 SQL 和接口会覆盖已有文件，看清楚再写。
"""

import argparse
from pathlib import Path

from .core import (DEFAULT_DB, ENTITY_DIR, OUT_DIR, PARTS, check,
                   generate, load, write)
from .filters import 主键, 主键自增
from .templates_ import DEFAULT_SET, TemplateError, sets


def main() -> int:
    # 项目命令：py -m gen init|gen|build|run 目录。跟下面按实体生成的老用法
    # 并存——第一个参数是这四个词之一就走项目那边。
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "tpl":
        from .tpl import main as tpl_main
        return tpl_main(sys.argv[2:])
    if len(sys.argv) > 1 and sys.argv[1] in ("init", "gen", "build", "run", "auth"):
        from .project import main as project_main
        return project_main(sys.argv[1:])

    p = argparse.ArgumentParser(
        prog="gen", description="从 .entity 生成前后端文件")
    p.add_argument("entity", nargs="?", default="", help="实体名")
    p.add_argument("--all", action="store_true", help="所有实体")
    p.add_argument("--entities", default=str(ENTITY_DIR),
                   help="实体定义放哪儿")
    p.add_argument("--db", default=DEFAULT_DB, help="接口里用哪个库")
    p.add_argument("--write", action="store_true", help="写盘（默认只打印）")
    p.add_argument("--check", action="store_true", help="只跑自检")
    p.add_argument("--只", dest="parts", default="",
                   help=f"只生成某几类，逗号分隔：{','.join(PARTS)}。默认全要")
    p.add_argument("--模板", dest="tpl", default=DEFAULT_SET,
                   help="用哪套模板（gen/templates/ 下的目录名）")
    p.add_argument("--列模板", action="store_true", help="看有哪些模板集")
    p.add_argument("--web", action="store_true", help="生成器的网页界面")
    p.add_argument("--edit", action="store_true",
                   help=".ui 编辑器：左边写，右边实时看界面")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8100)
    args = p.parse_args()

    if args.列模板:
        有 = sets()
        print("模板集：" + ("、".join(有) or "无"))
        return 0

    if args.edit:
        from .editor import serve as serve_editor
        return serve_editor(entity_dir=Path(args.entities),
                            host=args.host,
                            port=args.port if args.port != 8100 else 8110)

    if args.web:
        # 界面版单独一个模块：它要 Flask，而命令行不该为此多个依赖
        from .web import serve
        return serve(Path(args.entities), args.host, args.port)

    entities = load(Path(args.entities))

    parts = [x.strip() for x in args.parts.split(",") if x.strip()] or PARTS
    坏的名字 = [x for x in parts if x not in PARTS]
    if 坏的名字:
        print(f"不认识：{'、'.join(坏的名字)}。可用：{'、'.join(PARTS)}")
        return 1

    if not args.all:
        if not args.entity:
            print("实体：" + "、".join(e.name for e in entities))
            print("\n用法：py -m gen <实体名> [--write]")
            return 0
        entities = [e for e in entities if e.name == args.entity]
        if not entities:
            print(f"没有实体「{args.entity}」")
            return 1

    坏的 = 0
    for e in entities:
        pk = 主键(e)
        print(f"\n{'=' * 60}")
        print(f"{e.name}（{e.label}）　{len(e.fields)} 字段　"
              f"主键 {pk}{'（自增）' if 主键自增(e) else ''}")
        print("=" * 60)

        notes = check(e, args.db, args.tpl)
        坏的 += len(notes)
        for n in notes:
            print(f"  [自检] {n}")
        if not notes:
            print("  自检通过")

        if args.check:
            continue

        try:
            files = generate(e, args.db, parts, args.tpl)
        except TemplateError as ex:
            print(f"  [渲染失败] {ex}")
            坏的 += 1
            continue
        if args.write:
            print()
            for line in write(files):
                print(line)
        else:
            for rel, text in sorted(files.items()):
                print(f"\n--- {rel} ---")
                print(text)

    if not args.write and not args.check:
        print(f"\n（只是预览。加 --write 写到 {OUT_DIR} 下）")
    return 1 if 坏的 else 0


if __name__ == "__main__":
    raise SystemExit(main())
