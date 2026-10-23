# -*- coding: utf-8 -*-
"""业务层：services/<模块>.zs，一个文件一个模块、多个具名函数。

    业务 progress
      依赖 graph                 # 可调用哪些别的业务模块（不写就不能调）
      用包 db                    # 本文件里函数共用的包

      公开 函数 记作答 learner point_code answer?
        设 p = 调用 graph.取知识点 code={point_code}
        如果 {p} 为空
          报错 404 没有这个知识点
        结束
        返回 {"score": 1}
      结束

      函数 重算得分 learner         # 不写「公开」= 只给本模块用
        ...
      结束
    结束

调用：`设 r = 调用 模块.函数 键=值 …`（接口、业务函数、scripts 里都能用；`执行` 同义）。
同模块内可以只写函数名。末尾可加 `出错时 e` 接住业务错误（见 DSLEngine 的说明）。

三层各管什么：

    这个文件         解析 services/*.zs（Services）、调用规则（check_call / check_args）、
                     执行函数（ServiceMixin，混进 DSLEngine）
    dsl.py           引擎。「报错 4xx 文字」、事务并入、调用入口 _do_call 在这里挂钩
    dsl_http.py      Router 持有 Services，给每个请求的引擎设 services 和 svc_module
    dslagent/loadcheck.py  加载检查：用这里的解析和规则，不另写

调用规则（运行时和加载检查是同一套，都在这里）：

  - 只能调「公开」函数，同模块除外；
  - 跨模块必须在调用方所在业务文件的「依赖」里。接口文件属于哪个模块按文件名：
    routes/<模块>*.zs（模块名是文件名的前缀，取最长的）。接口可调本模块全部公开函数，
    调别的模块要本模块业务文件依赖它。对不上任何模块的接口 / 脚本（调用方未知）只能调
    公开函数，不查依赖；scripts 里的脚本沿用调起它的那一方；
  - 入参：必填必须给，不认识的键报错；
  - 调用深度上限 DSL_SERVICE_MAX_DEPTH（默认 32）。

函数是独立作用域：里面只有入参，看不到接口的请求字段（{request}、{current_user}…），
要用就当入参传进来。
"""

import os
import re
import threading
from pathlib import Path

from .db_errors import find_client_error
from .dsl_core import (
    BIZ_ERR_RE, BLOCK_OPENERS, CALL_PARAM_RE, BizError, DSLError, ScriptReturn,
    check_name, find_model_output_error, normalize, split_head,
)

DEFAULT_MAX_DEPTH = 32

# 「出错时 e」：调用语句的尾巴
ON_ERROR_RE = re.compile(r"\s+出错时\s+(\S+)\s*$")
# 模块.函数；不含 { } / 和 .zs 结尾的才是业务调用，其余仍是执行脚本
QUALIFIED_RE = re.compile(r"^([^\s./{}]+)\.([^\s./{}]+)$")
BARE_RE = re.compile(r"^[^\s./{}]+$")
TAIL_COMMENT_RE = re.compile(r"\s+#.*$")


def max_depth() -> int:
    try:
        return max(int(os.environ.get("DSL_SERVICE_MAX_DEPTH", DEFAULT_MAX_DEPTH)), 1)
    except ValueError:
        return DEFAULT_MAX_DEPTH


class Func:
    """一个业务函数。start / end 是 module.lines 里函数体的下标范围 [start, end)，
    header 是函数头那一行的行号（1 起）。"""

    def __init__(self, name, params, public, header, start, end):
        self.name = name
        self.params = params          # [(名, 是否可选)]
        self.public = public
        self.header = header
        self.start = start
        self.end = end

    @property
    def required(self):
        return [n for n, opt in self.params if not opt]

    @property
    def names(self):
        return [n for n, _ in self.params]


class Module:
    def __init__(self, name, path, rel, lines):
        self.name = name
        self.path = path
        self.rel = rel
        self.lines = lines            # 归一化后的全文行（函数体按下标跑，报错行号就是文件行号）
        self.deps = []                # [(模块名, 行号)]
        self.packs = []
        self.funcs = {}


class ServiceProblem(DSLError):
    """services 文件的解析问题，带位置。"""

    def __init__(self, rel, line, func, msg):
        self.rel, self.line, self.func, self.msg = rel, line, func, msg
        where = f"{rel}" + (f" 函数 {func}" if func else "") + (f"（第 {line} 行）" if line else "")
        super().__init__(f"[接口出错] {where}: {msg}")


def _clean(raw: str) -> str:
    return TAIL_COMMENT_RE.sub("", normalize(raw)).strip()


def parse_module(text: str, path: Path, rel: str = "") -> Module:
    """解析一个业务文件，第一个问题就抛 ServiceProblem。函数体不在这里查（loadcheck 逐个函数体
    走引擎的解析点）。"""
    rel = rel or path.name
    lines = [normalize(ln).rstrip() for ln in text.splitlines()]

    def bad(i, msg, func=""):
        raise ServiceProblem(rel, i + 1, func, msg)

    n = len(lines)
    i = 0
    while i < n and (not lines[i].strip() or lines[i].strip().startswith("#")):
        i += 1
    if i >= n:
        raise ServiceProblem(rel, 0, "", "文件是空的，应以「业务 模块名」开头")
    m = re.match(r"^业务\s+(\S+)\s*(?:#.*)?$", lines[i].strip())
    if not m:
        bad(i, "文件第一句应是「业务 模块名」")
    name = m.group(1)
    try:
        check_name(name)
    except DSLError:
        bad(i, f"模块名「{name}」不合法")
    if "." in name:
        bad(i, f"模块名「{name}」不能带点")
    if name != path.stem:
        bad(i, f"模块名「{name}」要和文件名一致（services/{name}.zs）")
    mod = Module(name, path, rel, lines)
    i += 1
    closed = False
    while i < n:
        raw = lines[i].strip()
        if not raw or raw.startswith("#"):
            i += 1
            continue
        line = _clean(raw)
        word, _, rest = line.partition(" ")
        rest = rest.strip()
        if closed:
            bad(i, "业务块「结束」之后不能再写东西")
        if word == "结束":
            closed = True
            i += 1
            continue
        if word == "依赖":
            names = [x for x in re.split(r"[,，\s]+", rest) if x]
            if not names:
                bad(i, "「依赖」后面要跟模块名")
            for d in names:
                if d == name:
                    bad(i, f"模块不能依赖自己（{d}）")
                if d not in [x for x, _ in mod.deps]:
                    mod.deps.append((d, i + 1))
            i += 1
            continue
        if word == "用包":
            mod.packs += [x for x in re.split(r"[,，\s]+", rest) if x and x not in mod.packs]
            i += 1
            continue
        public = False
        if word == "公开":
            public = True
            word, _, rest = rest.partition(" ")
            rest = rest.strip()
        if word != "函数":
            bad(i, f"业务块里只能写 依赖 / 用包 / [公开] 函数，现在是「{line.split(' ')[0]}」")
        toks = rest.split()
        if not toks:
            bad(i, "「函数」后面要跟函数名")
        fname = toks[0]
        try:
            check_name(fname)
        except DSLError:
            bad(i, f"函数名「{fname}」不合法")
        if "." in fname:
            bad(i, f"函数名「{fname}」不能带点", fname)
        if fname in mod.funcs:
            bad(i, f"函数「{fname}」重复定义（第 {mod.funcs[fname].header} 行已有）", fname)
        params = []
        for t in toks[1:]:
            opt = t.endswith("?")
            pn = t[:-1] if opt else t
            try:
                check_name(pn)
            except DSLError:
                bad(i, f"入参名「{t}」不合法", fname)
            if "." in pn:
                bad(i, f"入参名「{t}」不能带点", fname)
            if pn in [x for x, _ in params]:
                bad(i, f"入参「{pn}」重复", fname)
            params.append((pn, opt))
        # 函数体：到和「函数」配对的「结束」
        depth, j = 0, i + 1
        while j < n:
            head, _ = split_head(lines[j].strip())
            if head in BLOCK_OPENERS:
                depth += 1
            elif head == "end":
                if depth == 0:
                    break
                depth -= 1
            j += 1
        else:
            bad(i, "函数没有对应的「结束」", fname)
        mod.funcs[fname] = Func(fname, params, public, i + 1, i + 1, j)
        i = j + 1
    if not closed:
        raise ServiceProblem(rel, 0, "", "业务块没有对应的「结束」")
    return mod


class Services:
    """一个项目的 services/ 目录。解析一次缓存，refresh() 发现文件有改动就重载。

    modules：解析成功的模块；errors：[ServiceProblem 的文字]，解析错误、依赖指向不存在的模块、
    依赖成环都在里面。有 errors 时运行时第一次调业务函数会报出来，Router 启动时直接拒绝加载。"""

    def __init__(self, directory):
        self.dir = Path(directory)
        self.modules = {}
        self.errors = []
        self._sig = None
        self._lock = threading.Lock()
        self.refresh()

    def _signature(self):
        if not self.dir.is_dir():
            return ()
        out = []
        for f in sorted(self.dir.glob("*.zs")):
            st = f.stat()
            out.append((f.name, st.st_mtime_ns, st.st_size))
        return tuple(out)

    def refresh(self) -> bool:
        """文件有改动就重载，回是否重载了。"""
        sig = self._signature()
        if sig == self._sig:
            return False
        with self._lock:
            if sig == self._signature() and sig == self._sig:
                return False
            self._load(sig)
        return True

    def _load(self, sig):
        mods, errors = {}, []
        if self.dir.is_dir():
            for f in sorted(self.dir.glob("*.zs")):
                rel = f"services/{f.name}"
                try:
                    mod = parse_module(f.read_text(encoding="utf-8"), f, rel)
                except ServiceProblem as e:
                    errors.append(str(e))
                    continue
                except (OSError, UnicodeDecodeError) as e:
                    errors.append(f"[接口出错] {rel}: 读不了：{e}")
                    continue
                mods[mod.name] = mod
        errors += self._check_deps(mods)
        self.modules, self.errors, self._sig = mods, errors, sig

    @staticmethod
    def _check_deps(mods):
        errors = []
        for mod in mods.values():
            for d, line in mod.deps:
                if d not in mods:
                    errors.append(f"[接口出错] {mod.rel}（第 {line} 行）: 依赖的业务模块「{d}」不存在"
                                  f"（services/ 下有：{'、'.join(sorted(mods)) or '无'}）")
        # 成环：只在依赖都存在的边上找，每个环报一次
        seen_cycles = set()
        state = {}

        def walk(name, path):
            state[name] = 1
            for d, _ in mods[name].deps:
                if d not in mods:
                    continue
                if state.get(d) == 1:
                    cyc = path[path.index(d):] + [d]
                    key = frozenset(cyc)
                    if key not in seen_cycles:
                        seen_cycles.add(key)
                        errors.append(f"[接口出错] {mods[d].rel}: 业务模块依赖成环：{' → '.join(cyc)}")
                elif d not in state:
                    walk(d, path + [d])
            state[name] = 2

        for name in sorted(mods):
            if name not in state:
                walk(name, [name])
        return errors

    # ---- 查找与规则 ----

    def module_for(self, route_path) -> str | None:
        """接口文件 routes/<模块>*.zs 属于哪个模块：模块名是文件名（不含扩展名）的前缀，取最长的。"""
        stem = Path(str(route_path)).stem
        best = ""
        for name in self.modules:
            if stem.startswith(name) and len(name) > len(best):
                best = name
        return best or None

    def describe_modules(self) -> str:
        return "、".join(sorted(self.modules)) or "无"

    def lookup(self, caller, mod_name, fn_name, in_func=True) -> Func:
        """查函数并核对可见性。caller 是调用方所在的业务模块名，未知是 None。出问题抛 DSLError（不带行号）。"""
        mod = self.modules.get(mod_name)
        if mod is None:
            raise DSLError(f"没有业务模块「{mod_name}」（services/ 下有：{self.describe_modules()}）")
        fn = mod.funcs.get(fn_name)
        if fn is None:
            raise DSLError(f"业务模块「{mod_name}」里没有函数「{fn_name}」"
                           f"（有：{'、'.join(mod.funcs) or '无'}）")
        problem = self.check_call(caller, mod_name, fn, in_func)
        if problem:
            raise DSLError(problem)
        return fn

    def check_call(self, caller, mod_name, fn, in_func=True) -> str:
        """可见性规则，通过回空串。in_func：调用写在业务函数里（同模块可以调私有函数）；
        写在接口 / 脚本里只能调公开函数，哪怕接口按文件名属于这个模块。"""
        if caller == mod_name and in_func:
            return ""
        if not fn.public:
            return (f"{mod_name}.{fn.name} 不是公开函数，只能在 {mod_name} 模块内部调用"
                    f"（要给别的模块用，函数前加「公开」）")
        if caller is not None and caller != mod_name:
            cm = self.modules.get(caller)
            if cm is not None and mod_name not in [d for d, _ in cm.deps]:
                return (f"业务模块「{caller}」没有声明依赖「{mod_name}」，不能调 {mod_name}.{fn.name}"
                        f"（在 services/{caller}.zs 里加一行「依赖 {mod_name}」）")
        return ""

    @staticmethod
    def check_args(mod_name, fn, given) -> str:
        """入参核对：必填必须给，不认识的键报错。通过回空串。"""
        miss = [n for n in fn.required if n not in given]
        extra = [k for k in given if k not in fn.names]
        msgs = []
        if miss:
            msgs.append(f"缺少必填参数：{'、'.join(miss)}")
        if extra:
            msgs.append(f"不认识的参数：{'、'.join(extra)}")
        if not msgs:
            return ""
        sig = " ".join(n + ("?" if o else "") for n, o in fn.params) or "（无入参）"
        return f"{mod_name}.{fn.name} " + "；".join(msgs) + f"。入参：{sig}"


_CACHE = {}
_CACHE_LOCK = threading.Lock()


def get_services(directory) -> Services:
    """按目录缓存的 Services（同一个目录共用一份），顺带 refresh。"""
    key = str(Path(directory).resolve())
    with _CACHE_LOCK:
        svc = _CACHE.get(key)
        if svc is None:
            svc = _CACHE[key] = Services(key)
    svc.refresh()
    return svc


def parse_call_text(rest: str):
    """「目标 键=值 … [出错时 e]」→ (目标, 参数原文, 接错误的变量名或空)。"""
    on_err = ""
    m = ON_ERROR_RE.search(rest)
    if m:
        on_err = m.group(1)
        rest = rest[:m.start()]
    parts = rest.split(None, 1)
    return (parts[0] if parts else ""), (parts[1] if len(parts) > 1 else ""), on_err


def split_target(target: str, funcs=None):
    """调用目标是业务函数时回 (模块或None, 函数名)，是脚本回 None。

    「模块.函数」不含 { } / 且不以 .zs 结尾；只写函数名只有在 funcs（调用方模块的函数表）里
    有这个名字时才算，否则还是执行脚本。"""
    if not target or target.endswith(".zs"):
        return None
    m = QUALIFIED_RE.match(target)
    if m:
        return m.group(1), m.group(2)
    if funcs is not None and BARE_RE.match(target) and target in funcs:
        return None, target
    return None


class ServiceMixin:
    """DSLEngine 里跑业务函数的那部分。依赖引擎的属性：services / svc_module / in_func / svc_depth /
    svc_chain / _sub_engine / _resolve_items / _deliver / store。"""

    def _svc(self) -> Services:
        svc = self.services
        if svc is None:
            svc = self.services = get_services(self.workdir / "services")
        if self.svc_depth == 0:
            svc.refresh()
        if svc.errors:
            shown = "\n".join(svc.errors[:5]) + (f"\n还有 {len(svc.errors) - 5} 处" if len(svc.errors) > 5 else "")
            raise DSLError(f"业务层加载失败：\n{shown}")
        return svc

    def _service_target(self, target: str):
        """调用目标是业务函数就回 (模块或None, 函数名)，否则 None。"""
        funcs = None
        if self.in_func and self.services is not None:
            mod = self.services.modules.get(self.svc_module)
            funcs = mod.funcs if mod is not None else None
        return split_target(target, funcs)

    def _do_service_call(self, mod_name, fn_name, tail: str, on_err: str, lineno: int,
                         assign_to=None) -> None:
        where = f"第 {lineno + 1} 行"
        svc = self._svc()
        if mod_name is None:
            mod_name = self.svc_module
        try:
            fn = svc.lookup(self.svc_module, mod_name, fn_name, self.in_func)
        except DSLError as e:
            raise DSLError(f"{where}：{e}") from None
        if self.svc_depth >= max_depth():
            raise DSLError(f"{where}：业务函数调用深度超过 {max_depth()}（递归失控？）调用链："
                           f"{' → '.join(self.svc_chain[-8:] + (f'{mod_name}.{fn_name}',))}")
        given = {}
        for m in CALL_PARAM_RE.finditer(tail):
            given[m.group(1).strip()] = self._resolve_items(m.group(2).strip())
        problem = svc.check_args(mod_name, fn, given)
        if problem:
            raise DSLError(f"{where}：{problem}")
        module = svc.modules[mod_name]
        sub = self._sub_engine()
        sub.vars = {n: given.get(n, "") for n in fn.names}
        sub.services = svc
        sub.svc_module = mod_name
        sub.in_func = True
        sub.svc_depth = self.svc_depth + 1
        sub.svc_chain = self.svc_chain + (f"{mod_name}.{fn_name}",)
        sub.strict_verbs = False
        label = f"{mod_name}.{fn_name}"
        self._trace(f"{where}：调用 {label}")
        result = ""
        try:
            for p in module.packs:
                sub._do_use(p, fn.header - 1)
            try:
                sub._exec_block(module.lines, fn.start, fn.end)
            except ScriptReturn as r:
                result = r.value
        except BizError as e:
            if not on_err:
                raise
            self._swallow(on_err, e, assign_to)
            return
        except Exception as e:  # noqa: BLE001
            ce = find_client_error(e)
            if ce is not None and on_err:
                self._swallow(on_err, ce, assign_to)
                return
            # 模型返回的内容不合格（问JSON 解析失败 / 缺字段 / 类型不对）也是
            # 「这一单没做成」，不是脚本写错：一样让 出错时 接住，不接时照原样
            # 往上抛（还是 DSLError，接口层待遇不变）
            mo = find_model_output_error(e)
            if mo is not None and on_err:
                self._swallow(on_err, mo, assign_to)
                return
            elif isinstance(e, DSLError):
                raise DSLError(f"业务 {label}（{module.rel}）: {e}") from e
            else:
                raise
        if on_err:
            self.store(on_err, "")
        self._deliver(result, assign_to)

    def _swallow(self, var: str, err, assign_to=None) -> None:
        """接住的业务错误放进变量：{code, error}；赋值的变量（设 r = 调用 …）设成空串。
        调用成功时 出错时 后面的变量是空串，所以接住后用「如果 {e} 不为空」判断。"""
        self.store(var, {"code": err.status, "error": err.message})
        if assign_to:
            self.store(assign_to, "")


def biz_error_from(rest: str, expand):
    """「报错 404 文字」→ BizError；不是这个写法（第一个词不是 4xx 码）回 None，交给 common 包的报错动词。"""
    m = BIZ_ERR_RE.match(rest.strip())
    if not m:
        return None
    return BizError(expand(m.group(2) or "").strip() or f"错误 {m.group(1)}", int(m.group(1)))
