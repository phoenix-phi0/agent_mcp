# -*- coding: utf-8 -*-
"""模板集：一套模板决定生成什么形状。

    gen/templates/
      _base/            抽象基础套：三套共用的骨架（Jinja extends，差异点留成变量/块）
      default/          默认：三个界面，只取前几个短字段
      full/             完整：列表 + 浮层，增删改后回传最新列表
      private/          私有：full + 登录隔离（owner），另带账号的项目级文件
        set.json        清单：名、说明、继承、要求字段、参数、项目级文件
        project/*.j2    项目级模板（每个项目生成一次，如 user.entity、auth.zs）

每套有一个 set.json（见 describe()）。「继承」让一套只写与基础套的差异：
找模板时先找本套目录，再沿继承链往上找；模板里 `{% extends "@_base/x.j2" %}`
指名某一套的文件（@套名/文件名）。`python -m gen tpl` 管理这些（list / show /
diff / where / check / render / new / doc）。没有 set.json 的目录也算一套
（无继承、无参数），老写法照旧能用。

## 文件名决定产物路径

    list.sql.j2      →  queries/<实体>_list.sql
    routes.zs.j2     →  routes/<实体>.zs          .zs 的主模板
    admin.zs.j2      →  routes/<实体>_admin.zs    同一套里别的 .zs
    screens.ui.j2    →  ui/<实体>.ui              .ui 的主模板

规则是：产物名 = 实体名 + 下划线 + 模板名，只有 .zs 和 .ui 的主模板
（routes、screens）省掉后半截。所以一套里加多少个模板都行，加一条查询
只要丢个 `.sql.j2`，加一组管理接口只要丢个 `admin.zs.j2`，不用改代码。
文件名以 `_` 开头的是被引用的片段、子目录（project/）是项目级模板，都不按实体产出。

两个模板算出同一个产物路径时直接报错，不会悄悄覆盖。

注意：仓库根的 `templates/`（db/、frontend/）是建库和前端模板，跟这里的
gen/templates/ 同名不同用途。

## 分隔符不动

`.zs` 和 `.ui` 里没有 `{{ }}`，`.sql` 里也没有——所以用 Jinja 默认的
就行。`templates/frontend/` 那套要改成 `<% %>` 是因为 Vue 自己用
`{{ }}`，这边没这问题。

**但 `.zs` 里有 `{变量}`**（单层花括号），跟 Jinja 的 `{{ }}` 差一层。
模板里写 `{变量}` 是安全的，写 `{{变量}}` 会被 Jinja 吃掉——所以生成
`.zs` 时插值要写成 `{​{ '{' }}变量}` 或者用 `{% raw %}`。
默认模板里用的是后者，看着清楚些。
"""

import json
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


BASE_SET = "_base"
MANIFEST = "set.json"


def sets(root: Path = TEMPLATE_ROOT, abstract: bool = False) -> list:
    """有哪些模板集。默认不含抽象基础套（名字以 _ 开头，或清单里 抽象 = true）。"""
    root = Path(root)
    if not root.is_dir():
        return []
    names = sorted(p.name for p in root.iterdir() if p.is_dir())
    if abstract:
        return names
    return [n for n in names if not n.startswith("_") and not _manifest(root, n).get("抽象")]


def _manifest(root: Path, name: str) -> dict:
    """读 set.json；没有就是空清单（老式目录）。坏的 JSON 抛 TemplateError。"""
    f = Path(root) / name / MANIFEST
    if not f.is_file():
        return {}
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except ValueError as ex:
        raise TemplateError(f"{name}/{MANIFEST} 不是合法的 JSON：{ex}") from ex
    if not isinstance(data, dict):
        raise TemplateError(f"{name}/{MANIFEST} 顶层要是对象")
    return data


def chain(set_name: str, root: Path = TEMPLATE_ROOT) -> list:
    """继承链：[本套, 父, 祖父, …]。父不存在或成环抛 TemplateError。"""
    root = Path(root)
    out = []
    cur = set_name
    while cur:
        if cur in out:
            raise TemplateError("模板集继承成环：" + " → ".join(out + [cur]))
        if not (root / cur).is_dir():
            if not out:
                have = "、".join(sets(root)) or "无"
                raise TemplateError(f"没有模板集「{cur}」。有：{have}")
            raise TemplateError(f"模板集「{out[-1]}」继承的「{cur}」不存在")
        out.append(cur)
        cur = str(_manifest(root, cur).get("继承") or "")
    return out


def describe(set_name: str, root: Path = TEMPLATE_ROOT) -> dict:
    """一套的清单（已合并继承）：名、说明、继承、继承链、要求字段、参数、项目级文件、抽象。

    要求字段 / 参数：本套没写就沿用父套的（参数按名合并，子覆盖父）。
    项目级文件：本套没写就沿用父套的。旧的 requires.txt 在清单没写要求字段时兼容读。
    """
    root = Path(root)
    ch = chain(set_name, root)
    mans = [_manifest(root, n) for n in ch]
    own = mans[0]
    requires, project, params = None, None, {}
    for n, m in zip(ch, mans):
        if requires is None:
            if "要求字段" in m:
                requires = [str(x) for x in m["要求字段"]]
            else:
                legacy = root / n / "requires.txt"
                if legacy.is_file():
                    requires = [x.strip() for x in legacy.read_text(encoding="utf-8").splitlines()
                                if x.strip() and not x.strip().startswith("#")]
        if project is None and "项目级文件" in m:
            project = [dict(x, 来自=n) for x in m["项目级文件"]]
    for m in reversed(mans):
        params.update({k: dict(v) for k, v in (m.get("参数") or {}).items()})
    return {
        "名": set_name,
        "说明": str(own.get("说明", "")),
        "提示": str(own.get("提示", "")),
        "继承": str(own.get("继承", "")),
        "继承链": ch,
        "抽象": bool(own.get("抽象", False)),
        "要求字段": requires or [],
        "参数": params,
        "项目级文件": project or [],
    }


class _ChainLoader:
    """Jinja 加载器：名字先在本套找，再沿继承链往上找；`@套名/文件` 从指名的那套起找。"""

    def __new__(cls, root: Path, set_name: str):
        from jinja2 import BaseLoader, TemplateNotFound

        class Loader(BaseLoader):
            def get_source(self, environment, template):
                start, rest = set_name, template
                if template.startswith("@"):
                    start, _, rest = template[1:].partition("/")
                try:
                    dirs = chain(start, root)
                except TemplateError as ex:
                    raise TemplateNotFound(template, str(ex)) from ex
                for n in dirs:
                    f = Path(root) / n / rest
                    if f.is_file():
                        mtime = f.stat().st_mtime
                        return (f.read_text(encoding="utf-8"), str(f),
                                lambda f=f, m=mtime: f.stat().st_mtime == m)
                raise TemplateNotFound(template)

        return Loader()


def _env(root: Path, set_name: str):
    from jinja2 import Environment, StrictUndefined

    env = Environment(
        loader=_ChainLoader(Path(root), set_name),
        autoescape=False,           # 产出的是代码，转义会把 < & " 变成实体
        undefined=StrictUndefined,  # 名字打错了要炸，不能悄悄渲染成空
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    env.filters.update(FILTERS)
    return env


def products(set_name: str, root: Path = TEMPLATE_ROOT) -> dict:
    """这套能产出的模板：{模板文件名: 文件所在的套}（本套覆盖父套同名文件）。"""
    root = Path(root)
    out = {}
    for n in reversed(chain(set_name, root)):
        for f in (root / n).glob("*.j2"):
            if not f.name.startswith("_"):
                out[f.name] = n
    return dict(sorted(out.items()))


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
    """模板集要求实体必须有的字段（set.json 的 要求字段；旧的 requires.txt 兼容读）。

    比如 private 要求 owner：没有 owner 的实体套不了这套模板（查询里的
    WHERE owner = … 无处落脚）。项目生成时跳过这种实体并说一声，而不是
    渲染到一半报一个看不懂的 SQL 错。
    """
    if not (Path(root) / set_name).is_dir():
        return []
    return describe(set_name, root)["要求字段"]


def render(entity, set_name: str = DEFAULT_SET, db: str = "app.db",
           root: Path = TEMPLATE_ROOT, only=None) -> dict:
    """用一套模板渲染一个实体。返回 {产物路径: 内容}。

    only 是产物目录名的集合（queries / routes / ui），不给就全要。

    两个模板算出同一个产物路径时直接报错，说清楚是哪两个——早先是后一个
    悄悄覆盖前一个，丢了东西而且看不出来。
    """
    root = Path(root)
    prods = products(set_name, root)       # 套不存在在这里抛 TemplateError

    env = _env(root, set_name)
    out, source = {}, {}
    for tpl in prods:
        path = _target(tpl, entity.name)
        if path in source:
            raise TemplateError(
                f"{set_name}/{source[path]} 和 {set_name}/{tpl} "
                f"都会生成 {path}，后一个会覆盖前一个。改掉其中一个的文件名。")
        source[path] = tpl
        if only and path.split("/")[0] not in only:
            continue
        try:
            out[path] = env.get_template(tpl).render(e=entity, db=db)
        except Exception as ex:
            # 模板名带上：一套模板十来个文件，不说是哪个没法查
            raise TemplateError(f"{set_name}/{tpl}：{ex}") from ex
    return out


def project_params(set_name: str, params=None, root: Path = TEMPLATE_ROOT) -> dict:
    """清单里的参数默认值 + 调用方给的覆盖。给了清单里没有的参数名就报错。"""
    decl = describe(set_name, root)["参数"]
    out = {k: v.get("默认") for k, v in decl.items()}
    for k, v in (params or {}).items():
        if k not in decl:
            raise TemplateError(f"模板集「{set_name}」没有参数「{k}」。有：{'、'.join(decl) or '无'}")
        out[k] = v
    return out


def render_project(set_name: str, params=None, root: Path = TEMPLATE_ROOT) -> dict:
    """渲染一套的项目级文件（每个项目一次，如账号）。返回 {项目内相对路径: 内容}，按清单顺序。

    清单里 `当 = "<参数名>"` 的文件，该参数为空（假、空串、空列表）时不生成。
    """
    info = describe(set_name, root)
    values = project_params(set_name, params, root)
    env = _env(root, set_name)
    out = {}
    for pf in info["项目级文件"]:
        gate = pf.get("当")
        if gate:
            if gate not in values:
                raise TemplateError(f"{set_name}：项目级文件 {pf.get('路径')} 的「当」写了没声明的参数「{gate}」")
            if not values[gate]:
                continue
        try:
            out[pf["路径"]] = env.get_template(pf["模板"]).render(**values)
        except KeyError as ex:
            raise TemplateError(f"{set_name}：项目级文件缺 {ex}（需要 路径、模板）") from ex
        except Exception as ex:
            raise TemplateError(f"{set_name}/{pf.get('模板')}：{ex}") from ex
    return out
