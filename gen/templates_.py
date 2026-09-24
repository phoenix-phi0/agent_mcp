# -*- coding: utf-8 -*-
"""模板集：一套模板决定生成什么形状。

    gen/templates/
      默认/
        list.sql.j2      routes.zs.j2
        one.sql.j2       screens.ui.j2
        insert.sql.j2
        update.sql.j2
        delete.sql.j2
      只读/              只有查询，没有增删改
      ...

换套模板就换个形状——带搜索分页的、主从结构的、工作流的，各做一套，
不用改 Python。

## 文件名决定产物路径

    list.sql.j2      →  queries/<实体>_list.sql
    routes.zs.j2     →  routes/<实体>.zs          .zs 的主模板
    admin.zs.j2      →  routes/<实体>_admin.zs    同一套里别的 .zs
    screens.ui.j2    →  ui/<实体>.ui              .ui 的主模板

规则是：产物名 = 实体名 + 下划线 + 模板名，只有 .zs 和 .ui 的主模板
（routes、screens）省掉后半截。所以一套里加多少个模板都行，加一条查询
只要丢个 `.sql.j2`，加一组管理接口只要丢个 `admin.zs.j2`，不用改代码。

两个模板算出同一个产物路径时直接报错，不会悄悄覆盖。

## 分隔符不动

`.zs` 和 `.ui` 里没有 `{{ }}`，`.sql` 里也没有——所以用 Jinja 默认的
就行。`templates/frontend/` 那套要改成 `<% %>` 是因为 Vue 自己用
`{{ }}`，这边没这问题。

**但 `.zs` 里有 `{变量}`**（单层花括号），跟 Jinja 的 `{{ }}` 差一层。
模板里写 `{变量}` 是安全的，写 `{{变量}}` 会被 Jinja 吃掉——所以生成
`.zs` 时插值要写成 `{​{ '{' }}变量}` 或者用 `{% raw %}`。
默认模板里用的是后者，看着清楚些。
"""

from pathlib import Path

from .filters import FILTERS

HERE = Path(__file__).resolve().parent
TEMPLATE_ROOT = HERE / "templates"
DEFAULT_SET = "default"

# 后缀 → 产物目录
LAYOUT = {".sql": "queries", ".zs": "routes", ".ui": "ui"}

# .zs 和 .ui 里「主」模板的名字：它的产物就叫 <实体>.zs / <实体>.ui。
# 同一套里别的 .zs/.ui 模板产物带上模板名：admin.zs.j2 → <实体>_admin.zs。
#
# 早先 .zs 和 .ui 的产物一律只用实体名，一套里放两个 .zs 模板，两个都生成
# 到 routes/<实体>.zs，后一个悄悄覆盖前一个。主模板的名字保持原样，已经
# 生成过的项目不受影响。
PRIMARY = {".zs": "routes", ".ui": "screens"}


class TemplateError(Exception):
    """模板集不存在，或者渲染炸了。"""


def sets(root: Path = TEMPLATE_ROOT) -> list:
    """有哪些模板集。"""
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir())


def _env(set_dir: Path):
    from jinja2 import Environment, FileSystemLoader, StrictUndefined

    env = Environment(
        loader=FileSystemLoader(str(set_dir)),
        autoescape=False,           # 产出的是代码，转义会把 < & " 变成实体
        undefined=StrictUndefined,  # 名字打错了要炸，不能悄悄渲染成空
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    env.filters.update(FILTERS)
    return env


def _target(tpl_name: str, entity_name: str) -> str:
    """模板文件名 → 产物路径。

    `list.sql.j2`    → `queries/article_list.sql`
    `routes.zs.j2`   → `routes/article.zs`         主模板
    `admin.zs.j2`    → `routes/article_admin.zs`   同一套里的其他 .zs
    `screens.ui.j2`  → `ui/article.ui`             主模板
    """
    stem = tpl_name[:-3] if tpl_name.endswith(".j2") else tpl_name
    suffix = Path(stem).suffix          # .sql / .zs / .ui
    base = Path(stem).stem              # list / routes / admin
    if suffix not in LAYOUT:
        raise TemplateError(
            f"不认识的产物类型：{tpl_name}。支持：{'、'.join(LAYOUT)}")
    if PRIMARY.get(suffix) == base:
        name = f"{entity_name}{suffix}"
    else:
        name = f"{entity_name}_{base}{suffix}"
    return f"{LAYOUT[suffix]}/{name}"


def required_fields(set_name: str, root: Path = TEMPLATE_ROOT) -> list:
    """模板集要求实体必须有的字段，写在集目录的 requires.txt 里，一行一个。

    比如 private 要求 owner：没有 owner 的实体套不了这套模板（查询里的
    WHERE owner = … 无处落脚）。项目生成时跳过这种实体并说一声，而不是
    渲染到一半报一个看不懂的 SQL 错。
    """
    f = Path(root) / set_name / "requires.txt"
    if not f.is_file():
        return []
    return [x.strip() for x in f.read_text(encoding="utf-8").splitlines()
            if x.strip() and not x.strip().startswith("#")]


def render(entity, set_name: str = DEFAULT_SET, db: str = "app.db",
           root: Path = TEMPLATE_ROOT, only=None) -> dict:
    """用一套模板渲染一个实体。返回 {产物路径: 内容}。

    only 是产物目录名的集合（queries / routes / ui），不给就全要。

    两个模板算出同一个产物路径时直接报错，说清楚是哪两个——早先是后一个
    悄悄覆盖前一个，丢了东西而且看不出来。
    """
    set_dir = Path(root) / set_name
    if not set_dir.is_dir():
        have = "、".join(sets(root)) or "无"
        raise TemplateError(f"没有模板集「{set_name}」。有：{have}")

    env = _env(set_dir)
    out, source = {}, {}
    for tpl in sorted(set_dir.glob("*.j2")):
        path = _target(tpl.name, entity.name)
        if path in source:
            raise TemplateError(
                f"{set_name}/{source[path]} 和 {set_name}/{tpl.name} "
                f"都会生成 {path}，后一个会覆盖前一个。改掉其中一个的文件名。")
        source[path] = tpl.name
        if only and path.split("/")[0] not in only:
            continue
        try:
            out[path] = env.get_template(tpl.name).render(e=entity, db=db)
        except Exception as ex:
            # 模板名带上：一套模板十来个文件，不说是哪个没法查
            raise TemplateError(f"{set_name}/{tpl.name}：{ex}") from ex
    return out
