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
import re
import shutil
import sqlite3
import sys
import webbrowser
from pathlib import Path

from .core import DEFAULT_DB, PARTS
from .core import generate as gen_entity
from .templates_ import TemplateError, project_params, render_project, required_fields

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
    "buttons_not_stream", "empty_button",
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
        if e.page:
            # 页面实体只撑 .ui 的字段表，没有表：给它生成增删改查会产出一堆
            # 查一张不存在的表的文件。
            out.append(f"  跳过实体 {e.name}（页面实体不建表，不生成增删改查）")
            continue
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

def render_auth(optional: bool = False, roles=None, no_register: bool = False) -> dict:
    """private 套的账号文件（用户表、注册登录接口与界面；有角色时再加 user_auth.sql、auth_roles.zs）。

    文本全在 gen/templates/private/project/，参数见 private/set.json 的「参数」。
    返回 {项目内相对路径: 内容}。
    """
    names = [str(r).strip() for r in (roles or []) if str(r).strip()]
    return render_project("private", {"认证": "可选" if optional else "必须",
                                      "开放注册": not no_register, "角色": names})


def add_auth(root: Path, optional: bool = False, roles=None, no_register: bool = False) -> list:
    """给项目加上用户表和登录注册。已存在的文件跳过，不覆盖。

    optional：写「认证 可选」而不是「认证 必须」——平时照旧不用登录，
    启动时加 --登录 才要求（单人本机用、多人用同一份路由）。
    roles / no_register：见 private 套的参数（角色、开放注册）。
    """
    _check_root(root)
    out = []
    for rel, text in render_auth(optional, roles, no_register).items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists():
            out.append(f"  跳过 {rel}（已存在）")
            continue
        p.write_text(text, encoding="utf-8")
        out.append(f"  写入 {rel}")
    return out


# ----------------------------------------------------------------------
# 权限（程序套，不靠模型）：private 项目里 gen 的增删改查默认只许教师类角色
# ----------------------------------------------------------------------

# gen 增删改查五个接口的（路径尾, 动作尾）。模板（default / full / private）三套一致，
# 靠它认出「这是 gen 生成的块」：模型追加的接口路径 / 动作不会同时撞上这两个
CRUD_TAILS = {"list": "refresh", "one": "open", "create": "save", "update": "update", "delete": "remove"}
CLOSED_MARK = project_params("private")["关注册标记"]
_API_HEAD = re.compile(r"^接口\s+(?:(?:GET|POST|PUT|DELETE)\s+)?(/\S*)(?:\s+动作\s+(\S+))?(\s+公开)?(?:\s+(?:角色|只许)\s+(\S+))?\s*$", re.I)


def gen_block(head: str, entities) -> str:
    """接口头行是不是 gen 为某个实体生成的增删改查之一。是则返回实体名，否则空串。"""
    m = _API_HEAD.match(head.strip())
    if not m or not m.group(2) or m.group(3):
        return ""
    parts = m.group(1).strip("/").split("/")
    if len(parts) != 2 or parts[0] not in entities or parts[1] not in CRUD_TAILS:
        return ""
    return parts[0] if m.group(2) == f"{parts[0]}_{CRUD_TAILS[parts[1]]}" else ""


def lock_crud(root: Path, role: str) -> list:
    """routes/*.zs 里 gen 生成的增删改查接口头行补上「角色 <role>」。

    只改 gen 块的头行：已有「角色 / 只许」的不动，模型追加的接口、其余内容与换行原样保留。
    重复调用结果不变（resume 时对已有项目重新套）。
    """
    out = []
    if not role:
        return out
    ents = {e.name for e in load_entities(root)}
    for f in sorted((root / "routes").glob("*.zs")):
        raw = f.read_bytes().decode("utf-8")
        lines = raw.splitlines(keepends=True)
        n = 0
        for i, ln in enumerate(lines):
            body = ln.rstrip("\r\n")
            if body.startswith("接口 ") and gen_block(body, ents):
                m = _API_HEAD.match(body.strip())
                if not m.group(4):
                    lines[i] = body.rstrip() + f" 角色 {role}" + ln[len(body):]
                    n += 1
        if n:
            f.write_bytes("".join(lines).encode("utf-8"))
            out.append(f"  {f.relative_to(root)}：{n} 个增删改查接口加「角色 {role}」")
    return out


def hide_password_hash(root: Path) -> list:
    """user 的列表 / 单条查询不再选 password_hash；update 不再写它（表单里本来就没有了）。"""
    out = []
    for name in ("user_list", "user_one", "user_update"):
        f = root / "queries" / f"{name}.sql"
        if not f.is_file():
            continue
        t = f.read_bytes().decode("utf-8")
        if "password_hash" not in t:
            continue
        if name == "user_update":
            t2 = re.sub(r",\s*\r?\n\s*password_hash = :password_hash", "", t)
            t2 = re.sub(r"\n\s*password_hash = :password_hash,[ \t]*(\r?\n)", r"\1", t2) if t2 == t else t2
        else:
            t2 = re.sub(r"password_hash,\s*", "", t, count=1)
            t2 = re.sub(r",\s*password_hash\b", "", t2, count=1) if t2 == t else t2
        if t2 != t:
            f.write_bytes(t2.encode("utf-8"))
            out.append(f"  {f.relative_to(root)}：去掉 password_hash")
    return out


def _register_span(lines: list):
    """/auth/register 接口体在 lines 里的 (头行下标, 结束行下标)；找不到返回 None。"""
    from tools.dsl_http import INNER_OPENERS
    for i, ln in enumerate(lines):
        if re.match(r"^接口\s+(?:POST\s+)?/auth/register\b", ln):
            j = i + 1
            depth = 1
            while j < len(lines):
                h = lines[j].strip().split(" ")[0]
                if h in INNER_OPENERS:
                    depth += 1
                elif h in ("结束", "end"):
                    depth -= 1
                    if depth == 0:
                        return i, j
                j += 1
            return None
    return None


def close_register(root: Path) -> list:
    """关掉公开注册：routes/auth.zs 的 /auth/register 保留接口头（界面动作还在），内容换成 403。

    换成的内容取自 private 套 auth.zs 模板在「开放注册=false」时的渲染，和新项目一致。
    """
    f = root / "routes" / "auth.zs"
    if not f.is_file():
        return []
    raw = f.read_bytes().decode("utf-8")
    if CLOSED_MARK in raw:
        return []
    nl = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.split(nl)
    span = _register_span(lines)
    if not span:
        return []
    closed = render_auth(no_register=True)["routes/auth.zs"].split("\n")
    cspan = _register_span(closed)
    lines[span[0] + 1:span[1]] = closed[cspan[0] + 1:cspan[1]]
    f.write_bytes(nl.join(lines).encode("utf-8"))
    return ["  routes/auth.zs：/auth/register 改为 403（不开放自助注册）"]


def apply_perms(root: Path, roles, no_register: bool = False) -> list:
    """private 项目的权限，一次套全（可对已有项目重复调用）：
    角色 ≥2 个时 gen 增删改查加「角色 <第一个角色>」（第一个 = 教师类，默认注册角色是最后一个）；
    user 查询不返回 password_hash；no_register 时关公开注册。"""
    root = Path(root)
    _check_root(root)
    roles = [str(r).strip() for r in (roles or []) if str(r).strip()]
    out = []
    if len(roles) >= 2:
        out += lock_crud(root, roles[0])
    out += hide_password_hash(root)
    if no_register:
        out += close_register(root)
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
    from tools.migrate import (migrate_additive, rebuild_names, rebuild_tables, report,
                               report_rebuild, switch_on)

    db = root / DEFAULT_DB
    if db.is_file():
        names = rebuild_names(root / "routes")      # 「迁移 重建 表…」点名的表
        if switch_on(root / "routes"):
            lines = report(migrate_additive(db, root / "entities"), names)
            if names:
                lines += report_rebuild(rebuild_tables(db, root / "entities", names))
            return "\n".join([f"  {DEFAULT_DB} 已存在，按实体只加不改（迁移 只加）"] + lines)
        if names:
            lines = report_rebuild(rebuild_tables(db, root / "entities", names))
            return "\n".join([f"  {DEFAULT_DB} 已存在，只重建点名的表（迁移 重建）"] + lines)
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


# 「改密码」也算：登录之后才用得上的账号页，不进导航、不当入口
AUTH_SCREENS = ("登录", "注册", "改密码")

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


# 按「端」拆出来的页面：地址 -> 文件，起服务时照它把 /teacher 送到 teacher.html
PAGES_FILE = "pages.json"


def split_pages(screens, roles: dict) -> list:
    """按界面的「端」把一个应用拆成几个页面，每个页面一个入口地址。

    主页面（地址 /）是入口界面（screens 里第一个不是登录页的）所在的端，没写
    「端」的界面也归它；别的端各一个页面，地址取「认证 角色 teacher 教师」里
    的角色代号（/teacher），没有对得上的代号用 end1、end2。登录、改密码这些
    账号页每个页面都有。只有一端（或都没写「端」）时就一个页面，跟原来一样。

    roles 是 {角色代号: 中文名}（tools/dsl_http.py 的 auth_config）。返回
    [{end, slug, main, screens}]，主页面在最前、slug 是空串。
    """
    app = [s for s in screens if s.name not in AUTH_SCREENS]
    auth = [s for s in screens if s.name in AUTH_SCREENS]
    main = app[0].audience if app else ""
    ends = []
    for s in app:
        if s.audience and s.audience != main and s.audience not in ends:
            ends.append(s.audience)
    pages = [{"end": main, "slug": "", "main": True,
              "screens": [s for s in screens if s.name in AUTH_SCREENS
                          or not s.audience or s.audience == main]}]
    code_of = {label: code for code, label in roles.items()}
    for i, end in enumerate(ends, 1):
        slug = end if end in roles else code_of.get(end, "")
        if not (slug.isascii() and slug.isidentifier()):
            slug = f"end{i}"
        pages.append({"end": end, "slug": slug, "main": False,
                      "screens": [s for s in app if s.audience == end] + auth})
    return pages


def page_options(pages: list, page: dict, roles: dict) -> dict:
    """render_vue 的 page（见 tools/ui.py）：这一页是哪一端、别的端在哪个地址。"""
    if len(pages) == 1:
        return {}
    code_of = {label: code for code, label in roles.items()}
    ends = {}
    for pg in pages:
        path = "/" + pg["slug"]
        for key in (pg["end"], code_of.get(pg["end"], "")):
            if key:
                ends[key] = path
    main_end = pages[0]["end"]
    mine = {s.name for s in page["screens"]}
    return {"end": page["end"], "main": page["main"], "role": page["slug"],
            "badge": "" if page["main"] else f"{page['end']}端",
            "ends": ends,
            "home": None if page["main"] else
            {"path": "/", "label": f"打开{main_end}端" if main_end else "打开主页"},
            "elsewhere": {s.name: (pg["end"] or "主页")
                          for pg in pages if pg is not page
                          for s in pg["screens"] if s.name not in mine}}


def build(root: Path, entry: str = "", title: str = "") -> list:
    """把 ui/*.ui 合并、展开、编译到 web/。有挡路的问题就抛。

    界面写了不同的「端」（kg 的「端 学生」「端 教师」）时拆成几个页面：主页面
    照旧是 index.html（地址 /），别的端是 <代号>.html（地址 /<代号>，比如
    /teacher），见 split_pages。各页只有自己那一端的界面，标题后面带端名
    （「日语学习·教师端」）。
    """
    from tools import ui_entity, ui_site
    from tools.dsl_http import auth_config, endpoints_of
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
        # 全是解析失败的话，原因就在 notes 里（「<文件>：解析失败 …」），也要带出去
        return ["  ui/ 下没有界面，跳过编译"] + [f"  [提示] {x}" for x in notes if "解析失败" in x]
    if not entry:
        # 入口不给的话，跳过「登录」「注册」：auth.ui 按文件名排在最前，
        # 不跳的话已经登录的人每次打开都先看到登录页。打开的是应用界面，
        # 没登录的话它进入时的刷新会拿到 401，前端再跳去登录、登录完回来。
        idx = next((i for i, s in enumerate(screens)
                    if s.name not in AUTH_SCREENS), 0)
        screens.insert(0, screens.pop(idx))

    issues = list(ui_entity.expand(screens, entities))
    try:
        endpoints = endpoints_of(root / "routes")
    except Exception as e:
        raise ProjectError(f"读接口失败：{e}") from e

    try:
        roles = auth_config(root / "routes")["roles"] if (root / "routes").is_dir() else {}
    except Exception:
        roles = {}
    title = title or root.name
    pages = split_pages(screens, roles)
    results = []
    for page in pages:
        r = compile_ui(page["screens"], backend="vue", fields=field_table(entities),
                       require_bind=True,
                       options={"title": title if page["main"] else f"{title}·{page['end']}端",
                                "options_map": options_map(entities),
                                "endpoints": endpoints,
                                "content_root": str(root / "ui"),
                                "nav": compute_nav(page["screens"], "auth_logout" in endpoints),
                                "page": page_options(pages, page, roles)})
        # 各页面的问题合在一起报，同一条（共用的登录页上的）只报一次
        seen = {(i.code, str(i)) for i in issues}
        issues += [i for i in r["issues"] if (i.code, str(i)) not in seen]
        results.append((page, r))

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
    files = {}
    routes = {}
    for page, r in results:
        got = dict(r["result"]["files"])
        if VUE_LOCAL.is_file():
            got["index.html"] = got["index.html"].replace(VUE_CDN, f"./{VUE_LOCAL.name}")
        if page["main"]:
            files.update(got)
            continue
        # 非主页面：<代号>.html 引自己的 <代号>.js / <代号>.css
        slug = page["slug"]
        html = got["index.html"]
        for old, new in (('href="./style.css"', f'href="./{slug}.css"'),
                         ('src="./app.js"', f'src="./{slug}.js"')):
            assert html.count(old) == 1, f"index.html 里的 {old} 不是正好一处"
            html = html.replace(old, new)
        files[f"{slug}.html"] = html
        files[f"{slug}.js"] = got["app.js"]
        files[f"{slug}.css"] = got["style.css"]
        routes[slug] = f"{slug}.html"
        # 端名本身也能当地址（/教师）
        routes[page["end"]] = f"{slug}.html"
    if VUE_LOCAL.is_file():
        shutil.copy2(VUE_LOCAL, web / VUE_LOCAL.name)
    else:
        lines.append("  [提示] 没有本地 Vue，页面从 CDN 加载，断网会白屏")
    import json
    if routes:
        files[PAGES_FILE] = json.dumps(routes, ensure_ascii=False, indent=1) + "\n"
    else:
        # 原来拆过、现在不拆了：留着旧的 pages.json，/teacher 还会打开过时的页面
        (web / PAGES_FILE).unlink(missing_ok=True)
    for name, text in files.items():
        (web / name).write_text(text, encoding="utf-8")
    lines.append(f"  编译到 web/（{', '.join(sorted(files))}）")
    for page in pages[1:]:
        lines.append(f"  {page['end']}端：/{page['slug']}（{len(page['screens']) - len([s for s in page['screens'] if s.name in AUTH_SCREENS])} 个界面），"
                     f"其余在 /")
    return lines


# ----------------------------------------------------------------------
# 运行
# ----------------------------------------------------------------------


def make_app(root: Path, real: bool = False, login: bool = False,
             secure_cookie: bool = False):
    """后端接口 + 前端页面，同一个 Flask 应用。

    同一个进程同一个端口：前端发请求用的是相对路径，分两个端口就要处理
    跨域，而这是本地单人用的工具，没必要。

    login：路由写了「认证 可选」的项目，这次要求登录（见 tools/dsl_http.py
    「认证」一节）。secure_cookie：登录 cookie 只走 https。
    """
    from flask import abort, send_from_directory

    from tools.dsl_http import Router

    router = Router(root / "routes", root, root / "sessions", real=real,
                    login=login, secure_cookie=secure_cookie)
    app = router.app()
    web = (root / "web").resolve()

    @app.get("/")
    def _index():
        return send_from_directory(web, "index.html")

    def page_of(name: str) -> str:
        """按「端」拆出来的页面（/teacher、/教师）对到哪个 html，不是就空串。
        每次现读 pages.json：服务开着时重新 build 过也对得上。"""
        f = web / PAGES_FILE
        if not f.is_file():
            return ""
        import json
        try:
            return str(json.loads(f.read_text(encoding="utf-8")).get(name) or "")
        except ValueError:
            return ""

    # 只服务 web/ 下真实存在的文件。接口是 POST，跟这条 GET 不冲突。
    @app.get("/<path:name>")
    def _static(name):
        page = page_of(name.rstrip("/"))
        if page:
            if name.endswith("/"):
                # /teacher/ 下面的 ./teacher.js 会解析成 /teacher/teacher.js
                from flask import redirect
                return redirect("/" + name.rstrip("/"))
            return send_from_directory(web, page)
        p = (web / name).resolve()
        if web not in p.parents or not p.is_file():
            abort(404)
        return send_from_directory(web, name)

    return app, router


def run(root: Path, host: str = "127.0.0.1", port=None, real: bool = False,
        entry: str = "", open_browser: bool = True, login: bool = False,
        secure_cookie: bool = False, title: str = "") -> int:
    from tools.dsl_http import listen_warning, resolve_port

    _check_root(root)
    print("数据库：")
    print(ensure_db(root))
    print("界面：")
    if not list((root / "ui").glob("*.ui")):
        # 只有接口的项目（比如知识图谱的导入和查询）也该能跑起来
        print("  没有 .ui，只起接口")
    else:
        for line in build(root, entry, title):
            print(line)

    from tools.dsl import DSLError
    try:
        app, router = make_app(root, real, login=login, secure_cookie=secure_cookie)
    except DSLError as e:
        raise ProjectError(str(e)) from e
    print("接口：")
    print(router.describe())

    chosen, source = resolve_port(host, port, router.ports)
    if chosen is None:
        print(f"\n{source}")
        return 1

    url = f"http://{host}:{chosen}/"
    print(f"\n打开 {url}（{source}）"
          + ("" if real else "，假模型客户端——增删改查用不到模型"))
    print("登录：要求登录（多人模式）" if router.auth_required
          else "登录：不用登录（单人模式）", flush=True)
    warn = listen_warning(host, router.auth_required)
    if warn:
        print(warn, flush=True)
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
    s.add_argument("--标题", dest="title", default="", help="页面标题，默认是目录名")

    s = sub.add_parser("auth", help="加上用户表、登录注册，并打开认证")
    s.add_argument("dir")
    s.add_argument("--可选", dest="optional", action="store_true",
                   help="写「认证 可选」：平时不要登录，gen run --登录 时才要求")

    s = sub.add_parser("run", help="建库 + 编译 + 起服务")
    s.add_argument("dir")
    s.add_argument("--入口", dest="entry", default="")
    s.add_argument("--标题", dest="title", default="", help="页面标题，默认是目录名")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=None)
    s.add_argument("--real", action="store_true", help="用真模型客户端")
    s.add_argument("--不开浏览器", dest="no_browser", action="store_true")
    s.add_argument("--登录", dest="login", action="store_true",
                   help="路由写了「认证 可选」的项目：这次要求登录（多人用）")
    s.add_argument("--安全cookie", dest="secure_cookie", action="store_true",
                   help="登录 cookie 只走 https（放在 https 反向代理后面时开）")

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
            for line in build(root, args.entry, args.title):
                print(line)
            return 0
        if args.cmd == "auth":
            print("认证：")
            for line in add_auth(root, optional=args.optional):
                print(line)
            print(f"\n整个项目的接口现在都要求登录（routes/auth.zs 里的「认证 必须」）。"
                  f"\n要每人只看自己的数据：实体加一行 `字段 owner 文本 必填 索引`，"
                  f"\n然后 py -m gen gen {args.dir} --模板 private")
            return 0
        if args.cmd == "run":
            return run(root, args.host, args.port, args.real, args.entry,
                       open_browser=not args.no_browser, login=args.login,
                       secure_cookie=args.secure_cookie, title=args.title)
    except ProjectError as e:
        print(f"\n[出错] {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
