# -*- coding: utf-8 -*-
"""拼起来：读实体、渲染模板、写盘、自检。

生成逻辑不在这儿——在 `gen/templates/<模板集>/` 下的 `.j2` 里。这个
文件只管把实体喂进去、把产物拿出来。

换套模板就换个形状（带搜索分页的、只读的、带审核流的），不用改 Python。
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.entity import parse, validate                # noqa: E402

from .filters import 主键, 主键自增, 数据库填            # noqa: E402
from .templates_ import (DEFAULT_SET, TemplateError,     # noqa: E402
                         render, sets)

ENTITY_DIR = ROOT / "entities"
DEFAULT_DB = "app.db"

# 产物写这儿，不直接往项目里塞。
#
# 往 routes/ 里扔文件是会立刻生效的——dsl_http 下次扫描就把它当真接口
# 注册了。而生成的东西该先过一遍人眼。
OUT_DIR = ROOT / "gen" / "out"

# 产物的三类，界面上按这个勾选。对应产物路径的第一段（queries/x.sql）。
#
# 界面不写死这几个名字，从 /api/files 拿——先前前后端各写一遍，把 sql
# 改成 queries 之后前端没跟上，后端收到不认识的名字静默过滤掉，表现成
# 「SQL 不生成」而且不报错。
PARTS = ("queries", "routes", "ui")

# 给界面显示用的名字。目录名是给机器看的，勾选框上该写人话。
PART_LABELS = {"queries": "SQL", "routes": "接口", "ui": "界面"}


def generate(entity, db: str = DEFAULT_DB, parts=PARTS,
             template_set: str = DEFAULT_SET) -> dict:
    """渲染一个实体，返回 {产物路径: 内容}。

    返回字典而不是直接写盘：调用方可能是命令行、界面、或者别的脚本，
    写不写、写哪些该由它们定。
    """
    return render(entity, template_set, db, only=set(parts))


def write(files: dict, out_dir: Path = OUT_DIR) -> list:
    """落盘到 gen/out/ 下。

    目录结构跟项目里一模一样（queries/ routes/ ui/），所以复制过去是
    `cp -r gen/out/* .` 一句话。

    不按实体分子目录：文件名都带实体名前缀（learner_list.sql、
    learner.zs），混在一起也分得清；分了目录反而让「整个搬过去」变成
    挨个搬。

    直接覆盖不备份——这儿的东西本来就是生成物，重新生成就是要新的。
    真正需要备份的是往项目里复制那一步，而那一步由人做。
    """
    base = Path(out_dir).resolve()
    out = []
    for rel, text in sorted(files.items()):
        p = (base / rel).resolve()
        if base not in p.parents and p.parent != base:
            out.append(f"  跳过越界路径 {rel}")
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        out.append(f"  {rel}")
    return out


def load(entity_dir: Path = ENTITY_DIR) -> list:
    """读目录下所有 .entity。"""
    entity_dir = Path(entity_dir)
    if not entity_dir.is_dir():
        raise SystemExit(f"找不到 {entity_dir}")
    files = sorted(entity_dir.glob("*.entity"))
    if not files:
        raise SystemExit(f"{entity_dir} 下没有 .entity 文件")

    out = []
    for f in files:
        try:
            out.extend(parse(f.read_text(encoding="utf-8")))
        except Exception as e:
            raise SystemExit(f"{f.name}：{e}")

    problems = validate(out)
    if problems:
        print("实体定义有问题：")
        for p in problems:
            print("  -", p)
        raise SystemExit(1)
    return out


def check(entity, db: str = DEFAULT_DB,
          template_set: str = DEFAULT_SET) -> list:
    """几条机器能判的。全是踩出来的坑。

    **这些检查跟「默认」模板集绑着**——「INSERT 里不该有自增主键」这种
    话，换套模板可能就不成立了（比如导入历史数据的模板就是要客户端给
    时间戳）。

    所以换模板集时这里会少检查一些东西，而不是误报。真要每套模板各有
    各的检查，那该让模板集自带一个 check.py——现在还没到那份上。

    自检只能抓想到的错。这几条是实测发现 bug 之后补的，不是设计时想
    出来的。
    """
    if template_set != DEFAULT_SET:
        return [f"（自检只覆盖「{DEFAULT_SET}」模板集，"
                f"「{template_set}」的产物请自己看）"]

    try:
        files = render(entity, template_set, db)
    except TemplateError as e:
        return [f"渲染失败：{e}"]

    notes = []
    name = entity.name
    pk, 自增 = 主键(entity), 主键自增(entity)

    ins = files.get(f"queries/{name}_insert.sql", "")
    列部分 = ins.split("VALUES")[0]

    if 自增 and f"{pk}," in 列部分:
        notes.append(f"INSERT 里不该有自增主键 {pk}")
    if not 自增 and pk not in 列部分:
        notes.append(f"INSERT 里少了显式主键 {pk}——插进去会是 NULL")

    for f in entity.fields:
        if 数据库填(f) and f.name in 列部分:
            notes.append(f"{f.name} 是「默认 {f.default}」，不该进 INSERT")
        if f.type in ("整数", "布尔", "小数") and f"CAST(:{f.name}" not in ins:
            notes.append(f"{f.name} 是{f.type}，INSERT 里没 CAST")

    upd = files.get(f"queries/{name}_update.sql", "")
    if f"{pk} =" in upd.split("WHERE")[0]:
        notes.append(f"UPDATE 的 SET 里有主键 {pk}")

    选出的 = files.get(f"queries/{name}_list.sql", "").split("FROM")[0]
    if pk not in 选出的:
        notes.append(f"列表没带 {pk}，界面点编辑时不知道改哪条")
    for f in entity.fields:
        if f.type == "长文本" and f.name in 选出的:
            notes.append(f"列表里带了长文本字段 {f.name}")

    zs = files.get(f"routes/{name}.zs", "")
    # 主键不从 {session.xxx} 取：没有任何地方设过它。先前这条自检检查的
    # 正是那个错误写法，于是 bug 被当成了规则。
    if "{session." in zs:
        notes.append("接口里引用了 {session.xxx}，但没有地方会设它")
    # 增删改走「写库表 … {request}」：「写库」按空格切参数，用户输入含空格
    # 就会错位，而且不报错
    for 动作 in ("insert", "update", "delete"):
        if f"{name}_{动作} {{request}}" not in zs:
            notes.append(f"{动作} 没用「写库表 … {{request}}」，参数含空格会切错")
    if zs.count("事务") < 3:
        notes.append("增删改三个写操作该各有一个事务")

    if f"全部字段 {name}" not in files.get(f"ui/{name}.ui", ""):
        notes.append("表单该用「全部字段」，不该把字段列出来")

    return notes
