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
    # 参数：词表、级别
    逐项 词 于 {词表}
      问 讲解 = 讲解「{词}」（{级别}）
    结束

包顶层和「动词」子目录里的 .zs 都会被扫到。

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

参数按位置绑定。值里不能有空格——需要传含空格的内容时先用「设」存进
变量，再用 {变量} 传入。
"""

import importlib.util
import inspect
import json
import re
from pathlib import Path
from typing import Callable

# 从脚本注释里读参数声明：# 参数：甲、乙、丙
PARAM_DECL_RE = re.compile(r"#\s*参数\s*[：:]\s*(.+)$")

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


def parse_param_decl(script: str) -> list[str]:
    """从脚本开头的注释里读出参数顺序，没有声明就返回空列表。"""
    for line in script.splitlines():
        s = line.strip()
        if not s.startswith("#"):
            if s:                      # 遇到第一条实际语句就不再找
                break
            continue
        m = PARAM_DECL_RE.match(s)
        if m:
            return [p.strip() for p in re.split(r"[、,，]", m.group(1)) if p.strip()]
    return []


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
        reg.register_script(f.stem, f, parse_param_decl(f.read_text(encoding="utf-8")))
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

    def register_script(self, name: str, path: Path, params: list[str]) -> None:
        if not self._check_name(name, "脚本"):
            return
        self._note_override(name, "定义")
        self._verbs[name] = (params, "script", path, self._current_pack)

    def register_python(self, name: str, fn: Callable, params: list[str]) -> None:
        if not self._check_name(name, "Python"):
            return
        self._note_override(name, "定义")
        self._verbs[name] = (params, "python", fn, self._current_pack)

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
            params = parse_param_decl(f.read_text(encoding="utf-8"))
            self.register_script(f.stem, f, params)
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

    def bind(self, name: str, args: list[str]) -> dict[str, str]:
        """按位置把实参绑到参数名上。"""
        params = self.params_of(name)
        if len(args) > len(params):
            raise VerbError(
                f"「{name}」最多接受 {len(params)} 个参数"
                f"（{'、'.join(params) or '无'}），这次给了 {len(args)} 个。"
                f"值里有空格的话，先用「设」存进变量再用 {{变量}} 传入。"
            )
        return dict(zip(params, args))

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
            sig = " ".join(f"<{p}>" for p in params)
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
