# -*- coding: utf-8 -*-
"""项目：一个目录装齐一个应用的全部东西，一条命令跑起来。

    py -m gen init  我的应用/              建目录，放一份示例实体
    py -m gen gen   我的应用/              按实体生成 SQL、接口、界面
    py -m gen build 我的应用/              只编译界面（web/ 下）
    py -m gen run   我的应用/              建库 + 编译 + 起服务

目录长这样：

    我的应用/
      entities/   *.entity     数据定义
      queries/    *.sql        查询（gen 生成，可手改）
      routes/     *.zs         接口（gen 生成，可手改）
      ui/         *.ui         界面（gen 生成，可手改），也放 .md 内容文件
      web/                     编译产物，每次 build 覆盖，别手改
      app.db                   数据库，第一次 run 时建
      sessions/                会话。只有脚本用到「会话」时才出现——那是给
                               多轮交互记状态用的（练习模式记着刚出的题），
                               增删改查用不到。会话按请求里的 learner 字段分，
                               没有登录校验，别当成用户隔离

## 为什么要有「项目」

先前一次完整的「加一张表」要经过四个入口：生成器写到 gen/out/，手工
复制进 routes/ queries/，编辑器改 .ui，build.py 编译，dsl_http 起服务。
出的问题大半卡在接缝上——文件没搬、搬了没重启、改的是副本——而且端到端
一次都没跑通过，正是因为链太长没人走完。

项目把这些收到一个目录、一条命令：生成器直接写进来，服务直接读这里，
界面编译到这里的 web/，同一个进程把后端接口和前端页面一起服务。

## 生成不覆盖

`gen` 遇到已存在的文件默认**跳过**。生成是一次性的起点，落进项目之后就是
手写文本——重新生成冲掉手改是代码生成器的老问题。要覆盖显式加 --覆盖，
那时旧文件先存成 .bak。

## 数据库只建不删

`run` 只在 app.db 不存在时建库。实体改了字段，已有的库默认**不会**跟着变——
删表重建会丢数据。要重建就手动删掉 app.db。

路由里写一行「迁移 只加」（顶层，接口块外面）的项目，库已存在时按实体补上
缺的表、列、索引：只 CREATE TABLE IF NOT EXISTS / ADD COLUMN / CREATE INDEX IF
NOT EXISTS，不 DROP、不改已有的列，对不上的只告警。见 tools/migrate.py。
"""

import argparse
import shutil
import sqlite3
import sys
import webbrowser
from pathlib import Path

from .core import DEFAULT_DB, PARTS
from .core import generate as gen_entity
from .templates_ import TemplateError, required_fields

ROOT = Path(__file__).resolve().parent.parent
VUE_LOCAL = ROOT / "app2" / "assets" / "vue.global.prod.js"
VUE_CDN = "https://unpkg.com/vue@3/dist/vue.global.prod.js"

# 不预建 sessions/：会话只在脚本用到时才写，写的时候自己建目录。增删改查
# 的项目从头到尾用不到它，预建出来只是个让人疑惑的空目录。
SUBDIRS = ("entities", "queries", "routes", "ui", "web")

# 只有这些 issue 会挡住编译。其余的是提示（多个消息流、内容文件找不到），
# 说的是「还有东西没配」，不是界面写错了——挡住的话什么都看不到。
BLOCKING = {
    "syntax", "unknown_field", "untyped", "dup_screen", "path_conflict",
    "missing_endpoint", "not_screen", "empty_when", "unknown_entity",
    "unknown_screen", "unknown_overlay", "carry_without_goto",
}

SAMPLE = """\
# 示例实体。改它、删它、再加几个都行，改完跑 py -m gen gen 这个目录。
#
# 故意放两个：一个应用里有多个实体时，界面之间能互相跳、动作名不能撞，
# 这两件事只有两个以上才测得出来。

实体 note 笔记
  字段 title 文本 必填 标题
  字段 body 长文本 正文
  字段 pinned 布尔 必填 默认 否 置顶
  字段 created_at 文本 必填 默认 now 创建于
结束


实体 todo 待办
  字段 task 文本 必填 事项
  字段 done 布尔 必填 默认 否 完成
  字段 due 文本 截止
结束
"""


class ProjectError(Exception):
    """目录不对、实体有错、界面编译不过。"""


# ----------------------------------------------------------------------
# 目录与实体
# ----------------------------------------------------------------------


def init(root: Path, sample: bool = True) -> list:
    """建项目目录。已存在的不动。"""
    out = []
    root.mkdir(parents=True, exist_ok=True)
    for name in SUBDIRS:
        d = root / name
        if not d.is_dir():
            d.mkdir()
            out.append(f"  建了 {name}/")
    if sample and not list((root / "entities").glob("*.entity")):
        (root / "entities" / "sample.entity").write_text(SAMPLE, encoding="utf-8")
        out.append("  放了 entities/sample.entity")
    return out or ["  目录都在，没动"]


def _check_root(root: Path) -> None:
    if not (root / "entities").is_dir():
        raise ProjectError(
            f"{root} 不像项目目录（没有 entities/）。先 py -m gen init {root}")


def entities_text(root: Path) -> str:
    """所有 .entity 拼起来。建库和解析都用它，保证两边看到的是同一份。"""
    files = sorted((root / "entities").glob("*.entity"))
    if not files:
        raise ProjectError(f"{root / 'entities'} 下没有 .entity 文件")
    return "\n\n".join(f.read_text(encoding="utf-8") for f in files)


def load_entities(root: Path) -> list:
    from tools.entity import parse, validate

    try:
        entities = parse(entities_text(root))
    except ProjectError:
        raise
    except Exception as e:
        raise ProjectError(f"实体解析失败：{e}") from e
    problems = validate(entities)
    if problems:
        raise ProjectError("实体定义有问题：\n  " + "\n  ".join(problems))
    return entities


# ----------------------------------------------------------------------
# 生成
# ----------------------------------------------------------------------


def generate(root: Path, template_set: str = "full", only=None,
             parts=PARTS, force: bool = False) -> list:
    """按实体生成产物，**直接写进项目**。已存在的默认跳过。

    跳过而不是覆盖：生成是一次性的起点，落进项目之后就是手写文本。
    force=True 时覆盖，旧文件先存成 .bak。
    """
    _check_root(root)
    entities = load_entities(root)
    if only:
        names = {x.name for x in entities}
        missing = [n for n in only if n not in names]
        if missing:
            raise ProjectError(f"没有实体：{'、'.join(missing)}。"
                               f"有这些：{'、'.join(sorted(names))}")
        entities = [e for e in entities if e.name in only]

    out = []
    # 先把所有实体都渲染完、查完撞车，再统一写——查到一半才发现撞车的话，
    # 前面实体的文件已经写下去了。
    #
    # 跨实体也可能撞车：实体 note 的 admin.zs.j2 生成 note_admin.zs，一个
    # 叫 note_admin 的实体的主模板也生成 note_admin.zs。不查的话第二个会被
    # 当成「已存在」跳过（加 --覆盖 则悄悄盖掉第一个）。
    plan, produced = [], {}
    need = required_fields(template_set)
    for e in entities:
        have = {f.name for f in e.fields}
        missing = [n for n in need if n not in have]
        if missing:
            # 比如「私有」要 owner，而用户表自己没有 owner——它不是谁的数据
            out.append(f"  跳过实体 {e.name}（模板「{template_set}」要求字段 "
                       f"{'、'.join(missing)}）")
            continue
        try:
            files = gen_entity(e, DEFAULT_DB, parts, template_set)
        except TemplateError as ex:
            raise ProjectError(str(ex)) from ex
        for rel in files:
            if rel in produced:
                raise ProjectError(
                    f"实体 {produced[rel]} 和 {e.name} 都会生成 {rel}，"
                    f"后一个会覆盖前一个。改掉其中一个实体名，或者改模板文件名。")
            produced[rel] = e.name
        plan.append(files)

    for files in plan:
        for rel, text in sorted(files.items()):
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            if p.is_file() and not force:
                out.append(f"  跳过 {rel}（已存在，要覆盖加 --覆盖）")
                continue
            if p.is_file():
                p.with_suffix(p.suffix + ".bak").write_text(
                    p.read_text(encoding="utf-8"), encoding="utf-8")
                out.append(f"  覆盖 {rel}（旧的存成 .bak）")
            else:
                out.append(f"  写入 {rel}")
            p.write_text(text, encoding="utf-8")
    return out


# ----------------------------------------------------------------------
# 认证
# ----------------------------------------------------------------------

AUTH_FILES = {
    "entities/user.entity": """\
# 用户。由 py -m gen auth 生成。
#
# password_hash 存的是 scrypt 哈希，不是密码本身。界面上的密码框绑的是
# password（见 ui/auth.ui）；注册、登录两个动词在 Python 里哈希和核对，
# 密码不进数据库，也不经过脚本变量。

实体 user 用户
  字段 username 文本 必填 唯一 用户名
  字段 password_hash 文本 必填 密码
  字段 created_at 文本 必填 默认 now 注册于
结束
""",
    "queries/user_insert.sql": """\
-- 注册。password_hash 由「注册用户」动词算好传进来。
-- username 是唯一的，重名时插入失败，动词报「用户名已被占用」。
INSERT INTO user(username, password_hash)
VALUES(:username, :password_hash)
""",
    "queries/user_by_name.sql": """\
-- 登录时按用户名取出哈希。「登录」动词要的就是这两列，顺序不能换。
SELECT username, password_hash FROM user WHERE username = :username
""",
    "routes/auth.zs": """\
# 注册、登录、退出。由 py -m gen auth 生成。
#
# 下面这行打开认证：整个项目的接口都要求登录，只有标了「公开」的例外。
# 检查在路由器里做，不靠每个接口自己记得——手写的接口忘了检查，就是一个
# 不设防的口子。

认证 必须


# 注册成功直接登录。go 是 @来处：回到被要求登录之前的那个界面。
接口 POST /auth/register 动作 auth_register 公开
  用包 auth http
  设 result = 注册用户 app.db user_insert {request}
  如果 {result} 开头是 [
    返回 {"error":"{result}"} 400
  结束
  返回 {"go":"@来处","messages":[{"who":"系统","text":"注册成功","kind":"ok"}]}
结束


# 登录失败不区分「没这个人」和「密码错」
接口 POST /auth/login 动作 auth_login 公开
  用包 auth http
  设 user = 登录 app.db user_by_name {request}
  如果 {user} 为空
    返回 {"error":"用户名或密码不对"} 400
  结束
  返回 {"go":"@来处","messages":[{"who":"系统","text":"已登录","kind":"ok"}]}
结束


接口 POST /auth/logout 动作 auth_logout 公开
  用包 auth http
  设 result = 退出登录
  返回 {"go":"登录","messages":[{"who":"系统","text":"已退出","kind":"ok"}]}
结束


# 现在是谁。没登录时 user 是空串。
接口 POST /auth/me 动作 auth_me 公开
  返回 {"user":"{current_user}"}
结束
""",
    "ui/auth.ui": """\
# 登录、注册两个界面。由 py -m gen auth 生成，随便改。
#
# 界面名「登录」是约定：前端收到 401 时跳到叫这个名字的界面。改名的话
# 401 就不会自动跳了。
#
# 密码框：字段名 password_hash 用来查类型（它在用户表里），「绑 password」
# 让提交时的键叫 password——注册、登录动词收的是明文 password，在 Python
# 里哈希，哈希值从不经过前端。

界面 表单 登录
  分组 主体 竖排 间距 12px
    字段 username 用户名
    字段 password_hash 绑 password 控件 密码 密码
  结束

  分组 底栏 横排 底栏
    动作 auth_login 提交 远程 登录
    动作 toregister 次要 切到 注册 没有账号？注册
  结束
结束


界面 表单 注册
  分组 主体 竖排 间距 12px
    字段 username 用户名
    字段 password_hash 绑 password 控件 密码 密码（至少 6 位）
  结束

  分组 底栏 横排 底栏
    动作 auth_register 提交 远程 注册
    动作 tologin 次要 切到 登录 已有账号？登录
  结束
结束
""",
}


def add_auth(root: Path) -> list:
    """给项目加上用户表和登录注册。已存在的文件跳过，不覆盖。"""
    _check_root(root)
    out = []
    for rel, text in AUTH_FILES.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists():
            out.append(f"  跳过 {rel}（已存在）")
            continue
        p.write_text(text, encoding="utf-8")
        out.append(f"  写入 {rel}")
    return out


# ----------------------------------------------------------------------
# 数据库
# ----------------------------------------------------------------------


def ensure_db(root: Path) -> str:
    """库不存在就按实体建，存在就不动。

    不删表重建：那会丢数据，而实体改了字段正是最常重跑的时候。

    路由里写了「迁移 只加」的项目，库已存在时按实体补上缺的表、列、索引，
    别的不碰（tools/migrate.py）。没写的项目照旧：要按新定义重建就手动删 app.db。
    """
    from tools.entity import render_sql
    from tools.migrate import migrate_additive, report, switch_on

    db = root / DEFAULT_DB
    if db.is_file():
        if switch_on(root / "routes"):
            lines = report(migrate_additive(db, root / "entities"))
            return "\n".join([f"  {DEFAULT_DB} 已存在，按实体只加不改（迁移 只加）"] + lines)
        return f"  {DEFAULT_DB} 已存在，没动（实体改了字段的话要手动删掉重建）"
    sql = render_sql(entities_text(root))
    con = sqlite3.connect(db)
    try:
        con.executescript(sql)
        con.commit()
    finally:
        con.close()
    return f"  建了 {DEFAULT_DB}"


# ----------------------------------------------------------------------
# 编译界面
# ----------------------------------------------------------------------


AUTH_SCREENS = ("登录", "注册")

# 同属一个实体的界面：「笔记列表」这一项在「笔记编辑」「笔记新建」上也
# 高亮。只认这几个后缀，不用 startswith——不然「笔记」会把别的实体的
# 「笔记本列表」也算进来。
GROUP_SUFFIXES = ("列表", "编辑", "新建", "详情")


def compute_nav(screens, has_auth: bool) -> list:
    """顶部导航：每个列表界面一项。

    只在有两个以上列表界面、或者开了认证时才要：一个实体、没登录这回事的
    应用，界面之间的「切到」已经够了，多一条导航只是占地方。开了认证则
    需要一个到处都在的「退出登录」，放在导航里。
    """
    lists = [s for s in screens
             if (s.role or "") == "列表" and s.name not in AUTH_SCREENS]
    if len(lists) < 2 and not has_auth:
        return []
    names = [s.name for s in screens]
    out = []
    for s in lists:
        label = s.name[:-2] if s.name.endswith("列表") and len(s.name) > 2 else s.name
        group = [n for n in names if n == s.name
                 or (n.startswith(label) and n[len(label):] in GROUP_SUFFIXES)]
        out.append({"label": label, "target": s.name, "group": group})
    return out


def build(root: Path, entry: str = "", title: str = "") -> list:
    """把 ui/*.ui 合并、展开、编译到 web/。有挡路的问题就抛。"""
    from tools import ui_entity, ui_site
    from tools.dsl_http import endpoints_of
    from tools.entity import field_table, options_map
    from tools.ui import compile_ui

    _check_root(root)
    ui_files = sorted((root / "ui").glob("*.ui"))
    if not ui_files:
        raise ProjectError(f"{root / 'ui'} 下没有 .ui。先 py -m gen gen {root}")

    entities = load_entities(root)
    try:
        screens, notes = ui_site.merge(
            {f.name: f.read_text(encoding="utf-8") for f in ui_files}, entry)
    except ui_site.SiteError as e:
        raise ProjectError(str(e)) from e
    if not screens:
        # 一个界面都没有。run 那边已经会说「没有 .ui，只起接口」，build
        # 直接调用时也得有同样的退路——否则下面按入口重排时 pop 一个空
        # 列表，抛的是 IndexError，看不出是「没有界面」。
        return ["  ui/ 下没有界面，跳过编译"]
    if not entry:
        # 入口不给的话，跳过「登录」「注册」：auth.ui 按文件名排在最前，
        # 不跳的话已经登录的人每次打开都先看到登录页。打开的是应用界面，
        # 没登录的话它进入时的刷新会拿到 401，前端再跳去登录、登录完回来。
        idx = next((i for i, s in enumerate(screens)
                    if s.name not in ("登录", "注册")), 0)
        screens.insert(0, screens.pop(idx))

    issues = list(ui_entity.expand(screens, entities))
    try:
        endpoints = endpoints_of(root / "routes")
    except Exception as e:
        raise ProjectError(f"读接口失败：{e}") from e

    r = compile_ui(screens, backend="vue", fields=field_table(entities),
                   require_bind=True,
                   options={"title": title or root.name,
                            "options_map": options_map(entities),
                            "endpoints": endpoints,
                            "content_root": str(root / "ui"),
                            "nav": compute_nav(screens, "auth_logout" in endpoints)})
    issues += r["issues"]

    blocking = [i for i in issues if getattr(i, "code", "") in BLOCKING]
    lines = [f"  {len(ui_files)} 个 .ui，{len(screens)} 个界面，"
             f"{len(endpoints)} 个接口"]
    lines += [f"  [提示] {x}" for x in notes]
    lines += [f"  [提示] {i}" for i in issues if i not in blocking]
    if blocking:
        raise ProjectError("界面编译不过：\n" + "\n".join(
            f"  {i}" for i in blocking))

    web = root / "web"
    web.mkdir(exist_ok=True)
    files = dict(r["result"]["files"])
    if VUE_LOCAL.is_file():
        shutil.copy2(VUE_LOCAL, web / VUE_LOCAL.name)
        files["index.html"] = files["index.html"].replace(
            VUE_CDN, f"./{VUE_LOCAL.name}")
    else:
        lines.append("  [提示] 没有本地 Vue，页面从 CDN 加载，断网会白屏")
    for name, text in files.items():
        (web / name).write_text(text, encoding="utf-8")
    lines.append(f"  编译到 web/（{', '.join(sorted(files))}）")
    return lines


# ----------------------------------------------------------------------
# 运行
# ----------------------------------------------------------------------


def make_app(root: Path, real: bool = False):
    """后端接口 + 前端页面，同一个 Flask 应用。

    同一个进程同一个端口：前端发请求用的是相对路径，分两个端口就要处理
    跨域，而这是本地单人用的工具，没必要。
    """
    from flask import abort, send_from_directory

    from tools.dsl_http import Router

    router = Router(root / "routes", root, root / "sessions", real=real)
    app = router.app()
    web = (root / "web").resolve()

    @app.get("/")
    def _index():
        return send_from_directory(web, "index.html")

    # 只服务 web/ 下真实存在的文件。接口是 POST，跟这条 GET 不冲突。
    @app.get("/<path:name>")
    def _static(name):
        p = (web / name).resolve()
        if web not in p.parents or not p.is_file():
            abort(404)
        return send_from_directory(web, name)

    return app, router


def run(root: Path, host: str = "127.0.0.1", port=None, real: bool = False,
        entry: str = "", open_browser: bool = True) -> int:
    from tools.dsl_http import resolve_port

    _check_root(root)
    print("数据库：")
    print(ensure_db(root))
    print("界面：")
    if not list((root / "ui").glob("*.ui")):
        # 只有接口的项目（比如知识图谱的导入和查询）也该能跑起来
        print("  没有 .ui，只起接口")
    else:
        for line in build(root, entry):
            print(line)

    app, router = make_app(root, real)
    print("接口：")
    print(router.describe())

    chosen, source = resolve_port(host, port, router.ports)
    if chosen is None:
        print(f"\n{source}")
        return 1

    url = f"http://{host}:{chosen}/"
    print(f"\n打开 {url}（{source}）"
          + ("" if real else "，假模型客户端——增删改查用不到模型"))
    if open_browser:
        # WSL 里通常打不开 Windows 的浏览器，失败了也没关系，地址已经打印了
        try:
            webbrowser.open(url)
        except Exception:
            pass
    app.run(host=host, port=chosen, threaded=True, debug=False)
    return 0


# ----------------------------------------------------------------------
# 命令行
# ----------------------------------------------------------------------


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="gen", description="项目：一个目录一个应用")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="建项目目录，放一份示例实体")
    s.add_argument("dir")
    s.add_argument("--空", dest="empty", action="store_true", help="不放示例")

    s = sub.add_parser("gen", help="按实体生成 SQL、接口、界面到项目里")
    s.add_argument("dir")
    s.add_argument("--模板", dest="tpl", default="full",
                   help="模板集：default / full / private（private 要实体有 owner 字段）")
    s.add_argument("--实体", dest="only", default="", help="逗号分隔，默认全部")
    s.add_argument("--覆盖", dest="force", action="store_true",
                   help="覆盖已存在的文件（旧的存 .bak）")

    s = sub.add_parser("build", help="编译界面到 web/")
    s.add_argument("dir")
    s.add_argument("--入口", dest="entry", default="")

    s = sub.add_parser("auth", help="加上用户表、登录注册，并打开认证")
    s.add_argument("dir")

    s = sub.add_parser("run", help="建库 + 编译 + 起服务")
    s.add_argument("dir")
    s.add_argument("--入口", dest="entry", default="")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=None)
    s.add_argument("--real", action="store_true", help="用真模型客户端")
    s.add_argument("--不开浏览器", dest="no_browser", action="store_true")

    args = p.parse_args(argv)
    root = Path(args.dir).resolve()

    try:
        if args.cmd == "init":
            print(f"项目 {root}")
            for line in init(root, sample=not args.empty):
                print(line)
            print(f"\n下一步：py -m gen gen {args.dir}")
            return 0
        if args.cmd == "gen":
            only = [x.strip() for x in args.only.split(",") if x.strip()]
            print(f"生成（模板「{args.tpl}」）：")
            for line in generate(root, args.tpl, only or None,
                                 force=args.force):
                print(line)
            print(f"\n下一步：py -m gen run {args.dir}")
            return 0
        if args.cmd == "build":
            for line in build(root, args.entry):
                print(line)
            return 0
        if args.cmd == "auth":
            print("认证：")
            for line in add_auth(root):
                print(line)
            print(f"\n整个项目的接口现在都要求登录（routes/auth.zs 里的「认证 必须」）。"
                  f"\n要每人只看自己的数据：实体加一行 `字段 owner 文本 必填 索引`，"
                  f"\n然后 py -m gen gen {args.dir} --模板 private")
            return 0
        if args.cmd == "run":
            return run(root, args.host, args.port, args.real, args.entry,
                       open_browser=not args.no_browser)
    except ProjectError as e:
        print(f"\n[出错] {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
