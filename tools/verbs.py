"""动词包：把 .zs 脚本和 Python 函数统一注册成 DSL 语句。

动词让调用方少写几行：

    词汇讲解 {词表} N5          ← 等价于执行 词汇讲解.zs 并传两个参数
    挑题 {题库} 3 促音变         ← 等价于调用 Python 函数 挑题(题库, 数量, 考点)

对写脚本的人来说两者没有区别，这正是重点：
DSL 表达得了的能力用 .zs 写（改措辞不碰代码），
DSL 表达不了的原子能力用 Python 写（查询、算术、外部接口）。

## 包的形状

    verbs/japanese/
        _verbs.py           入口。共享辅助函数的动词写在这里，
                            再调 scan_verbs 把子目录扫进来
        动词/
            假名进度.py      一文件一动词
            词汇讲解.zs      脚本动词
        五十音.json          数据，动词从这里读，改数据不动代码

入口始终是 `_verbs.py` 的 `register(reg, workspace)`——包自己决定要不要
扫子目录、扫哪个。不在 load_pack 里自动扫包顶层：那样包的结构就由引擎
规定死了，而且顶层的 .py 到底是动词还是辅助模块得靠命名约定猜。

典型的 `_verbs.py`：

    from pathlib import Path
    from tools.verbs import scan_verbs

    PACK_DIR = Path(".")        # 占位，加载时注入

    def register(reg, workspace):
        # 独立的动词一文件一个，放子目录
        scan_verbs(reg, PACK_DIR / "动词", workspace)

        # 共享辅助函数的一组写在这里，闭包里的 helper 不必重复
        def _load(路径):
            ...

        @reg.verb("从题库随机挑题")
        def 挑题(题库: str, 数量: str = "3") -> str:
            ...

## 单文件动词的约定

    # verbs/common/动词/算比例.py
    \"\"\"计算百分比，返回整数。例如 算比例 8 10 → 80\"\"\"

    def 算比例(分子: str, 分母: str) -> str:
        try:
            a, b = float(分子), float(分母)
        except ValueError:
            return "[参数不是数字]"
        return "0" if b == 0 else str(round(a / b * 100))

函数名跟文件名一致，模块 docstring 的第一行当动词说明。
需要路径时用注入的模块级变量：

    WORKSPACE   工作目录，文件读写的根
    PACK_DIR    包目录，读同包的数据文件用

下划线开头的 .py 跳过——那是子目录里的辅助模块。

## 脚本动词

放 .zs，第二行注释声明参数顺序：

    # 词汇讲解：讲解一组单词
    # 参数：词表 级别? 最多=3
    逐项 词 于 {词表}
      问 讲解 = 讲解「{词}」（{级别}）
    结束

包顶层和「动词」子目录里的 .zs 都会被扫到。

参数声明：分隔符是空白、顿号、逗号、全角逗号。`名` 必填；`名?` 可选（不传
为空串）；`名=值` 有默认值（字面文本，不展开变量；`名=` 等同 `名?`）。声明里
没有任何 `?` 或 `=` 的旧文件保持旧行为（少传为空、不报错）；有任意一个就按
新规则（裸名必填）。Python 动词取函数签名：没有默认值的必填。

## 数据放外面

动词里的表格、映射、常量放 .json，用 load_data() 读：

    五十音 = load_data(PACK_DIR, "五十音.json")

改数据不用动代码，也不用重启——文件每次读，几 KB 的表无所谓。

## 包

按需加载：

    reg = VerbRegistry(reserved=RESERVED)
    reg.load_pack(base / "common")
    reg.load_pack(base / "japanese")

不同 agent 挂不同的包。同名时后加载的覆盖先加载的，并记一条警告。

安全提醒：load_pack 会执行包里的 .py。动词包目录必须放在不可被外部
写入的位置，否则等于开放了任意代码执行。

## 调用形式

    词汇讲解 {词表} N5              直接执行，输出进结果
    设 结果 = 挑题 {题库} 3          返回值赋给变量

参数按位置绑定，也可以写 `键=值`（位置参数写在前面、可混用；写在 键=值 后面的
位置参数依次填还没给的参数）：

    词汇讲解 {词表} 级别=N5

词形如 `键=值` 且「键」是该动词声明的参数名时才当关键字参数，否则照位置参数
原样处理。同一参数给两次、必填没给、位置参数多于声明都报错。值里不能有空格
——需要传含空格的内容时先用「设」存进变量，再用 {变量} 传入。
"""

import importlib.util
import inspect
import json
import re
from pathlib import Path
from typing import Callable, NamedTuple

# 从脚本注释里读参数声明：# 参数：甲 乙? 丙=默认
PARAM_DECL_RE = re.compile(r"#\s*参数\s*[：:]\s*(.+)$")
PARAM_SEP_RE = re.compile(r"[\s、,，]+")
KW_TOKEN_RE = re.compile(r"^([^\s=]+)=(.*)$", re.S)

# 包入口
PACK_PY = "_verbs.py"
PACK_ENTRY = "register"

# 加载时注入到模块里的变量名
WS_ATTR = "WORKSPACE"
PACK_ATTR = "PACK_DIR"

# 下划线开头的 .py 是辅助模块，不当动词
PRIVATE_PREFIX = "_"


class VerbError(Exception):
    """动词注册或调用出错。"""


class ParamSpec(NamedTuple):
    """一个参数。required：不传就报错；default：不传时的值（None 表示没有默认）。
    omit：不传时不往实现里传这个参数（Python 动词让函数自己的默认值生效）。"""
    name: str
    required: bool = True
    default: object = None
    omit: bool = False

    def show(self) -> str:
        """签名里的样子：<名> / <名?> / <名=默认>"""
        if self.required:
            return f"<{self.name}>"
        if self.default is None or self.default == "":
            return f"<{self.name}?>"
        return f"<{self.name}={self.default}>"


def parse_param_specs(script: str) -> tuple[list[ParamSpec], bool, int]:
    """读脚本开头的参数声明：(参数列表, 是否新规则, 声明所在行号 1 起)。

    新规则：声明里有任意一个 `?` 或 `=`；否则是旧文件，少传不报错。
    没有声明返回 ([], False, 0)。
    """
    for n, line in enumerate(script.splitlines(), 1):
        s = line.strip()
        if not s.startswith("#"):
            if s:                      # 遇到第一条实际语句就不再找
                break
            continue
        m = PARAM_DECL_RE.match(s)
        if not m:
            continue
        specs, strict = [], False
        for tok in PARAM_SEP_RE.split(m.group(1).strip()):
            if not tok:
                continue
            name, eq, val = tok.partition("=")
            name = name.strip()
            opt = name.endswith(("?", "？"))
            name = name.rstrip("?？").strip()
            if not name:
                continue
            if eq:
                strict = True
                specs.append(ParamSpec(name, False, val))
            elif opt:
                strict = True
                specs.append(ParamSpec(name, False, ""))
            else:
                specs.append(ParamSpec(name, True))
        return specs, strict, n
    return [], False, 0


def parse_param_decl(script: str) -> list[str]:
    """从脚本开头的注释里读出参数顺序（只要名字），没有声明就返回空列表。"""
    return [p.name for p in parse_param_specs(script)[0]]


def bind_top_params(script: str, pairs: "list[tuple[str, str]]") -> dict:
    """顶层脚本（`python -m tools.dsl 脚本.zs 键=值 …`、`run_file`/`run` 的 params 字典）的参数绑定。

    脚本头有 `# 参数：` 声明时，按与 .zs 动词相同的规则：必填缺了报错（旧声明——没有
    任何 `?` 或 `=` 的——少传不报错，不注入该键）、`名?` 不传为空串、`名=值` 不传用默认值、
    给了声明里没有的键报错、同一键给了两次报错。没有声明就把给的键原样注入，不做校验。
    """
    specs, strict, where = parse_param_specs(script)
    if not specs:
        return dict(pairs)
    names = {sp.name for sp in specs}
    got: dict = {}
    for k, v in pairs:
        if k not in names:
            raise VerbError(f"脚本没有参数「{k}」，有：{'、'.join(sorted(names)) or '无'}"
                            f"（声明：第 {where} 行）")
        if k in got:
            raise VerbError(f"参数「{k}」给了两次（声明：第 {where} 行）")
        got[k] = v
    for sp in specs:
        if sp.name in got:
            continue
        if sp.required:
            if strict:
                raise VerbError(f"缺少必填参数「{sp.name}」（声明：第 {where} 行）")
        else:
            got[sp.name] = sp.default
    return got


def _python_specs(fn: Callable, names: list[str]) -> list[ParamSpec]:
    """Python 动词的参数：没有默认值的必填，有默认值的不传时让函数自己用默认。"""
    try:
        sig = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        sig = {}
    out = []
    for n in names:
        p = sig.get(n)
        if p is None or p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
            out.append(ParamSpec(n, False, None, True) if p is not None
                       else ParamSpec(n, True))
        elif p.default is inspect.Parameter.empty:
            out.append(ParamSpec(n, True))
        else:
            d = p.default
            out.append(ParamSpec(n, False, "" if d is None else d, True))
    return out


def load_data(pack_dir: Path | str, name: str, default=None):
    """读包目录下的数据文件。给动词实现用。

    每次都重新读：几 KB 的表无所谓，换来的是改数据不用重启。
    """
    p = Path(pack_dir) / name
    if not p.is_file():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def as_list(x) -> list:
    """列表参数，给动词实现用：真列表原样（复制一份）；JSON 数组文本解析；空当
    空列表；别的报错。

    DSL 调动词时参数一律是文本，列表到了动词里是 JSON 文本；从 Python 直接调
    又是真列表——两种都得认。传错了东西（一段话当列表）报错而不是当成空列表：
    悄悄当成没有，后面的结果全错还看不出来。
    """
    if isinstance(x, list):
        return list(x)
    s = "" if x is None else str(x).strip()
    if not s:
        return []
    try:
        v = json.loads(s)
    except json.JSONDecodeError:
        v = None
    if not isinstance(v, list):
        raise ValueError(f"要一个列表（JSON 数组），给的是：{s[:60]}")
    return v


def _import_file(path: Path, mod_name: str):
    """按文件路径导入一个模块，不经过 sys.path。"""
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载 {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def scan_verbs(reg: "VerbRegistry", directory: Path | str,
               workspace: Path | str | None = None,
               pack_dir: Path | str | None = None) -> int:
    """扫描一个目录，把里面的 .py 和 .zs 都注册成动词。

    给 `_verbs.py` 的 register() 调用：

        scan_verbs(reg, PACK_DIR / "动词", workspace)

    .py 的约定是函数名跟文件名一致。找不到同名函数时退而求其次，取模块里
    第一个非下划线开头的函数——文件名含连字符之类没法当标识符时这条兜底
    有用，但不建议依赖。

    返回注册成功的数量。出错不抛异常，记进 reg.warnings——一个动词写坏了
    不该让整个包加载失败，那样连报错都看不全。
    """
    directory = Path(directory)
    if not directory.is_dir():
        return 0

    ws = Path(workspace) if workspace else directory
    pd = Path(pack_dir) if pack_dir else directory.parent
    tag = directory.name
    count = 0

    for f in sorted(directory.glob("*.zs")):
        reg.register_script(f.stem, f, f.read_text(encoding="utf-8"))
        count += 1

    for f in sorted(directory.glob("*.py")):
        if f.name.startswith(PRIVATE_PREFIX):
            continue
        try:
            module = _import_file(f, f"_verb_{tag}_{f.stem}")
        except Exception as e:
            reg.warnings.append(f"{f.name} 导入失败：{type(e).__name__}: {e}")
            continue

        setattr(module, WS_ATTR, ws)
        setattr(module, PACK_ATTR, pd)

        fn = getattr(module, f.stem, None)
        if not callable(fn):
            fn = next(
                (v for k, v in vars(module).items()
                 if callable(v) and not k.startswith("_")
                 and getattr(v, "__module__", "").startswith("_verb_")),
                None)
        if fn is None:
            reg.warnings.append(f"{f.name} 里没找到跟文件同名的函数")
            continue

        fn.__verb_description__ = (module.__doc__ or "").strip().split("\n")[0]
        reg.register_python(f.stem, fn, list(inspect.signature(fn).parameters))
        count += 1

    return count


class VerbRegistry:
    """动词表。脚本动词和 Python 动词都注册在这里。"""

    def __init__(self, reserved: set[str] | None = None):
        # 名字 -> (参数名列表, 类型, 实现, 来自哪个包)
        self._verbs: dict[str, tuple[list[str], str, object, str]] = {}
        # 名字 -> (参数规格列表, 新规则?, 声明所在 "文件 第 N 行")
        self._sigs: dict[str, tuple[list[ParamSpec], bool, str]] = {}
        self.reserved = reserved or set()
        self.warnings: list[str] = []
        self.packs: list[str] = []
        self._current_pack = ""

    # ------------------------------------------------------------------
    # 注册
    # ------------------------------------------------------------------

    def _check_name(self, name: str, kind: str) -> bool:
        if name in self.reserved:
            self.warnings.append(f"动词「{name}」与内置语句同名，已跳过（{kind}）")
            return False
        return True

    def _note_override(self, name: str, kind: str) -> None:
        """同名时记一条警告，说明谁覆盖了谁。"""
        if name not in self._verbs:
            return
        old_pack = self._verbs[name][3]
        new_pack = self._current_pack or "(直接注册)"
        if old_pack == new_pack:
            self.warnings.append(f"包 {new_pack} 内动词「{name}」被重复注册")
        else:
            self.warnings.append(
                f"动词「{name}」：{new_pack} 覆盖了 {old_pack} 的同名{kind}"
            )

    def register_script(self, name: str, path: Path,
                        script: "str | list[str]") -> None:
        """script 是 .zs 的全文（读头部的参数声明）；给名字列表也行（全必填、旧规则）。"""
        if not self._check_name(name, "脚本"):
            return
        self._note_override(name, "定义")
        if isinstance(script, str):
            specs, strict, ln = parse_param_specs(script)
        else:
            specs, strict, ln = [ParamSpec(n) for n in script], False, 0
        where = f"{Path(path).name} 第 {ln} 行" if ln else Path(path).name
        self._verbs[name] = ([p.name for p in specs], "script", path, self._current_pack)
        self._sigs[name] = (specs, strict, where)

    def register_python(self, name: str, fn: Callable, params: list[str]) -> None:
        if not self._check_name(name, "Python"):
            return
        self._note_override(name, "定义")
        self._verbs[name] = (params, "python", fn, self._current_pack)
        code = getattr(fn, "__code__", None)
        where = (f"{Path(code.co_filename).name} 第 {code.co_firstlineno} 行"
                 if code else name)
        self._sigs[name] = (_python_specs(fn, params), True, where)

    def verb(self, description: str = "", name: str | None = None):
        """装饰器：注册一个 Python 动词。参数顺序取自函数签名。"""
        def deco(fn: Callable) -> Callable:
            verb_name = name or fn.__name__
            params = list(inspect.signature(fn).parameters)
            self.register_python(verb_name, fn, params)
            fn.__verb_description__ = description
            return fn
        return deco

    # ------------------------------------------------------------------
    # 加载
    # ------------------------------------------------------------------

    def load_dir(self, directory: Path) -> int:
        """只扫描目录里的 .zs，不执行 Python。返回注册数量。"""
        directory = Path(directory)
        if not directory.is_dir():
            return 0
        count = 0
        for f in sorted(directory.glob("*.zs")):
            self.register_script(f.stem, f, f.read_text(encoding="utf-8"))
            count += 1
        return count

    def load_pack(self, directory: Path, workspace: Path | None = None) -> int:
        """加载一个动词包。

        入口是 `_verbs.py` 的 register()。包顶层的 .zs 也会扫（不用写代码
        就能加脚本动词），但 .py 一律由 register() 自己决定怎么处理——
        通常是调 scan_verbs 扫「动词」子目录。

        注意这会执行包里的 .py，包目录必须不可被外部写入。
        """
        directory = Path(directory)
        if not directory.is_dir():
            self.warnings.append(f"动词包不存在：{directory}")
            return 0

        pack = directory.name
        ws = Path(workspace) if workspace else directory
        prev, self._current_pack = self._current_pack, pack
        try:
            count = self.load_dir(directory)

            py = directory / PACK_PY
            if py.is_file():
                count += self._load_pack_python(py, pack, ws)

            if pack not in self.packs:
                self.packs.append(pack)
            return count
        finally:
            self._current_pack = prev

    def _load_pack_python(self, py: Path, pack: str, workspace: Path) -> int:
        """导入包里的 _verbs.py 并调用它的 register()。"""
        before = len(self._verbs)
        try:
            module = _import_file(py, f"_verbpack_{pack}")
        except Exception as e:
            self.warnings.append(
                f"包 {pack} 的 {PACK_PY} 导入失败：{type(e).__name__}: {e}")
            return 0

        setattr(module, WS_ATTR, workspace)
        setattr(module, PACK_ATTR, py.parent)

        entry = getattr(module, PACK_ENTRY, None)
        if not callable(entry):
            self.warnings.append(f"包 {pack} 的 {PACK_PY} 缺少 {PACK_ENTRY}() 函数")
            return 0

        try:
            entry(self, Path(workspace))
        except Exception as e:
            self.warnings.append(
                f"包 {pack} 的 {PACK_ENTRY}() 执行失败：{type(e).__name__}: {e}")
            return 0

        return len(self._verbs) - before

    def load_packs(self, base: Path, names: list[str],
                   workspace: Path | None = None) -> int:
        """按名字加载 base 下的若干个包，顺序即优先级（后者覆盖前者）。"""
        base = Path(base)
        return sum(self.load_pack(base / n, workspace) for n in names)

    def available_packs(self, base: Path) -> list[str]:
        """列出 base 下所有可加载的包。"""
        base = Path(base)
        if not base.is_dir():
            return []
        found = []
        for d in sorted(base.iterdir()):
            if not d.is_dir():
                continue
            if any(d.glob("*.zs")) or (d / PACK_PY).is_file():
                found.append(d.name)
        return found

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def has(self, name: str) -> bool:
        return name in self._verbs

    def names(self) -> list[str]:
        return sorted(self._verbs)

    def params_of(self, name: str) -> list[str]:
        return list(self._verbs[name][0]) if name in self._verbs else []

    def kind_of(self, name: str) -> str:
        return self._verbs[name][1] if name in self._verbs else ""

    def pack_of(self, name: str) -> str:
        return self._verbs[name][3] if name in self._verbs else ""

    def specs_of(self, name: str) -> list[ParamSpec]:
        return list(self._sigs[name][0]) if name in self._sigs else []

    def split_call(self, name: str, tokens: list[str]) -> tuple[list[str], list[tuple[str, str]], list[str]]:
        """把调用的词拆成 (位置参数, 键=值, 写在 键=值 后面的位置参数)。词形如 `键=值`
        且键是该动词声明的参数名才算关键字参数，别的词都是位置参数。"""
        names = set(self.params_of(name))
        pos: list[str] = []
        kws: list[tuple[str, str]] = []
        late: list[str] = []
        for t in tokens:
            m = KW_TOKEN_RE.match(t)
            if m and m.group(1) in names:
                kws.append((m.group(1), m.group(2)))
            elif kws:
                late.append(t)
            else:
                pos.append(t)
        return pos, kws, late

    def bind(self, name: str, args: list, kwargs: "list[tuple[str, object]] | None" = None,
             late: "list | None" = None) -> dict:
        """把实参绑到参数名上：args 按位置，kwargs 是 [(键, 值)]，late 是写在 键=值
        后面的位置参数（依次填还没给的参数，旧脚本 `推理 规则=x {甲} {乙}` 是这么写的）。

        同一参数给两次、位置参数过多报错；缺必填：新规则（和 Python 动词）报错，
        旧规则的 .zs 少传就是没有这个变量。
        """
        params = self.params_of(name)
        specs, strict, where = self._sigs.get(name, ([ParamSpec(p) for p in params], False, name))
        sig = " ".join(p.show() for p in specs) or "无"
        late = list(late or [])

        def too_many(n):
            return VerbError(
                f"「{name}」最多接受 {len(params)} 个参数"
                f"（{'、'.join(params) or '无'}），这次给了 {n} 个。"
                f"值里有空格的话，先用「设」存进变量再用 {{变量}} 传入。"
                f"（声明：{where}）")

        if len(args) > len(params):
            raise too_many(len(args) + len(kwargs or []) + len(late))
        got = dict(zip(params, args))
        for k, v in kwargs or []:
            if k not in params:
                raise VerbError(f"「{name}」没有参数「{k}」，有：{'、'.join(params) or '无'}（声明：{where}）")
            if k in got:
                raise VerbError(f"「{name}」的参数「{k}」给了两次（声明：{where}）")
            got[k] = v
        for v in late:
            slot = next((p for p in params if p not in got), None)
            if slot is None:
                raise too_many(len(args) + len(kwargs or []) + len(late))
            got[slot] = v
        for sp in specs:
            if sp.name in got:
                continue
            if sp.required:
                if strict:
                    raise VerbError(f"「{name}」缺少必填参数「{sp.name}」，签名：{name} {sig}（声明：{where}）")
            elif not sp.omit:
                got[sp.name] = sp.default
        return got

    def check_call(self, name: str, tokens: list[str]) -> str | None:
        """静态检查一次调用（只看词的个数和键，不求值）。没问题返回 None。"""
        try:
            pos, kws, late = self.split_call(name, tokens)
            self.bind(name, ["x"] * len(pos), [(k, "x") for k, _ in kws], ["x"] * len(late))
        except VerbError as e:
            return str(e)
        return None

    def resolve(self, name: str) -> tuple[str, object]:
        """返回 (类型, 实现)。类型是 'script' 或 'python'。"""
        if name not in self._verbs:
            raise VerbError(f"没有名为「{name}」的动词")
        _, kind, impl, _ = self._verbs[name]
        return kind, impl

    def describe(self, by_pack: bool = True) -> str:
        """人类可读的动词清单。"""
        if not self._verbs:
            return "  (无动词)"

        def one(n: str) -> str:
            params, kind, impl, _ = self._verbs[n]
            tag = "脚本" if kind == "script" else "Python"
            if kind == "python":
                desc = getattr(impl, "__verb_description__", "")
            else:
                desc = ""
                for line in Path(impl).read_text(encoding="utf-8").splitlines():
                    s = line.strip()
                    if s.startswith("#") and not PARAM_DECL_RE.match(s):
                        desc = s.lstrip("#").strip()
                        break
            sig = " ".join(p.show() for p in self._sigs[n][0])
            return f"  {n} {sig}  [{tag}] {desc}"

        if not by_pack:
            return "\n".join(one(n) for n in sorted(self._verbs))

        groups: dict[str, list[str]] = {}
        for n in sorted(self._verbs):
            groups.setdefault(self._verbs[n][3] or "(未分包)", []).append(n)

        out = []
        for pack in sorted(groups):
            out.append(f"【{pack}】")
            out.extend(one(n) for n in groups[pack])
        return "\n".join(out)
