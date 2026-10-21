"""修改.zs 用：写修改计划（调模型，自己存 plan/changes/<序号>.zs）+ 检查修改计划（程序）。

计划是一份真正能被 `执行` 直接跑的 .zs 脚本，四种动词（产出约定）+ 直接改文件 + 三个验收动词 + 一个固定收尾动词：
    改需求 <节号> <内容>              # 内容可含转义的 \\n（多段正文），没有空格（中文标点，不留 ASCII 空格）
    新增模块 <名> 依赖=<…> 说明=<…>
    删除模块 <名>
    改约定 <模块> <改动条目>
    改文件 <文件> <原文> <新文>        # 代码和约定不一致时直接改文件；原文逐字、在文件里唯一；新文可省（＝删掉原文）
    加载检查 <模块> / 比对约定 <模块> / 跑用例 <模块>   # 验收动词（落实修改 对改过文件的模块会自动验收，这三行可省）
    落实修改                          # 固定末行：改过文件的模块先验收（不过就恢复文件并失败），再按依赖分层写/重写新增与改约定涉及的约定、同步顶层依赖
每行可带「# 对应问题 N」（落实修改 不用标）。四个内容类动词的值不能有 ASCII 空格（DSL 调用一行按空格分词，
值里要空格用中文标点；改需求 要分段用两个字符的 \\n，执行时由 改需求 动词解码成真正的换行）。

check_plan(text, issues, top, req_text) -> 问题列表（空 = 通过）：
- 格式：每行必须是四种动词或「落实修改」开头（parse_plan 已经按行拆出格式问题）
- 末行固定是「落实修改」（没有 → 报问题，提醒模型漏写）
- 改文件：2～3 个参数；文件存在、归属某个模块且在对应问题涉及模块的范围内（范围规则同 dslproj 的 scope_globs，
  kg/、tests/ 之类范围外一律拒绝）；原文在文件里（顺序套用前面的改文件之后）恰好出现一次；原文和新文不能一样
- 加载检查 / 比对约定 / 跑用例：模块要在 top.zs 里（或本计划新增）
- 模块存在：删除模块 / 改约定 的模块名要在 top.zs 里；新增模块 不能和已有模块重名
- 不成环：新增模块 的「依赖=」只能是 top.zs 里的模块或本次计划里别的「新增模块」，且合起来不成环
- 新增模块写了说明：「新增模块 …」必须带「说明=」
- 每个问题被覆盖：issues 里的编号都在至少一行「# 对应问题」里出现过
- 改需求的节号存在：「改需求 <节号> …」的节号要能在需求文本的「## <节号>」或「<节号>.」标题里找到（找不到需求文本时跳过这项）
"""
import re
from pathlib import Path

from tools.dsl_core import ScriptHalt

from .. import v2 as V2
from .core import prompt_text


def changes_dir(project):
    return Path(project) / "plan" / "changes"


def next_no(project):
    d = changes_dir(project)
    have = [int(f.stem) for f in d.glob("*.zs")] if d.is_dir() else []
    return max(have, default=0) + 1


def latest_plan_path(project):
    d = changes_dir(project)
    have = sorted((d.glob("*.zs") if d.is_dir() else []), key=lambda f: int(f.stem))
    return have[-1] if have else None


DIRECTIVE_RE = re.compile(r"^(改需求|新增模块|删除模块|改约定|改文件|加载检查|比对约定|跑用例)\s")
CLOSING_VERB = "落实修改"
ACCEPT_VERBS = ("加载检查", "比对约定", "跑用例")
FILE_ONLY_VERBS = ("改文件",) + ACCEPT_VERBS     # 只有这些（加固定收尾）的计划不需要重做任何模块，也不需要 build


TAG_RE = re.compile(r"^#\s*对应问题\s*([\d,，\s]+)\s*$")


def parse_plan(text):
    """修改计划 .zs 文本 → ([{"动词", "内容", "对应问题"}], 问题列表)。只认 DIRECTIVE_RE 里的动词 + 落实修改 开头的行。

    「# 对应问题 N」要单独写一行，紧接在它标注的指令行**之前**（不能写在指令行末尾——这份计划要能被 `执行`
    原样当 DSL 脚本跑，DSL 不会剥掉一行末尾的 # 注释，写在行末会被当成这一行调用的参数，execution 时报错）。
    """
    items, probs = [], []
    pending = []
    for no, raw in enumerate((text or "").replace("\r\n", "\n").split("\n"), 1):
        line = raw.strip()
        if not line:
            continue
        m = TAG_RE.match(line)
        if m:
            pending = [int(x) for x in re.findall(r"\d+", m.group(1))]
            continue
        if line.startswith("#"):
            continue
        tags, pending = pending, []
        if line == CLOSING_VERB:
            items.append({"动词": CLOSING_VERB, "内容": "", "对应问题": tags, "行": no})
            continue
        if not DIRECTIVE_RE.match(line):
            probs.append(f"第 {no} 行：只能用 改需求 / 新增模块 / 删除模块 / 改约定 / 改文件 / 加载检查 / 比对约定 / 跑用例 / 落实修改 开头，现在是「{line[:40]}」")
            continue
        verb, _, rest = line.partition(" ")
        items.append({"动词": verb, "内容": rest.strip(), "对应问题": tags, "行": no})
    return items, probs


def user_text(issues_text, req_excerpt, task, top_text, catalog_text, contracts_text, files_text=""):
    parts = [f"【问题清单】\n{issues_text.strip()}"]
    if (task or "").strip():
        parts.append(f"【任务】\n{task.strip()}")
    if (req_excerpt or "").strip():
        parts.append(f"【需求中被引用 / 任务涉及的章节】\n{req_excerpt.strip()}")
    parts.append(f"【顶层规划 plan/top.zs】\n{(top_text or '').strip() or '（还没有）'}")
    if (catalog_text or "").strip():
        parts.append(f"【项目接口目录 plan/catalog.md】\n{catalog_text.strip()}")
    if (contracts_text or "").strip():
        parts.append(f"【涉及模块的约定（去掉用例）】\n{contracts_text.strip()}")
    if (files_text or "").strip():
        parts.append("【类型为 code 的问题涉及模块的现有文件原文（每行前面「  12| 」是行号前缀，不是文件内容，改文件的原文不要带它）】\n"
                     + files_text.strip())
    return "\n\n".join(parts)


def as_issues_text(问题):
    """问题清单入参可能是：渲染好的文本、读问题清单 的返回（{"items":…}）、或直接的 items 列表——统一成
    干净的编号文本（给模型看、也给「上次问题」拼接用）。"""
    if isinstance(问题, dict):
        items = 问题.get("items") or []
    elif isinstance(问题, list):
        items = 问题
    else:
        return str(问题 or "")
    if not items:
        return "（没有发现问题）"
    from . import issues as IS
    return "\n".join(IS.format_issue(i, it) for i, it in enumerate(items, 1))


def resolve_plan_text(project, ref):
    """计划入参可能是一份 plan/changes/<序号>.zs 的相对路径，也可能是计划原文（带换行）——统一成原文。"""
    s = ref or ""
    if isinstance(s, str) and "\n" not in s:
        p = Path(project) / s if not Path(s).is_absolute() else Path(s)
        if p.is_file():
            return p.read_text(encoding="utf-8")
    return s


def normalize_plan(text):
    """模型常在「改需求 / 改约定」的自由文本里夹 ASCII 空格（DSL 一行按空格分词，会超参数个数）：
    把第 2 个参数之后的空格换成两字符 \\_（改需求 / 改约定 执行时还原成空格，和 \\n 同理），不再靠反复让模型重写。"""
    out = []
    for line in (text or "").replace("\r\n", "\n").split("\n"):
        parts = line.split(None, 2)
        if len(parts) == 3 and parts[0] in ("改需求", "改约定"):
            line = f"{parts[0]} {parts[1]} " + re.sub(r"\s+", "\\\\_", parts[2].strip())
        out.append(line)
    return "\n".join(out)

ESC_RE = re.compile(r"\\(\\|n|_|t)")
ESC_MAP = {"\\": "\\", "n": "\n", "_": " ", "t": "\t"}
BRACE_ESC_RE = re.compile(r"\{\{([^{}]*)\}\}")


def decode_edit_arg(s, braces=True):
    """改文件 的 文件/原文/新文 一个参数 → 真正的文本：DSL 的 {{x}} 已由引擎还原成 {x}（这里为检查阶段补做同样的还原），
    再单遍解 \\\\→\\、\\n→换行、\\_→空格、\\t→制表符（一行按空格分词，空格 / 换行只能这样写）。"""
    s = BRACE_ESC_RE.sub(lambda m: "{" + m.group(1) + "}", s or "") if braces else (s or "")
    return ESC_RE.sub(lambda m: ESC_MAP[m.group(1)], s)


def owner_module(module_names, rel):
    """项目相对路径 → 归属的模块名（按 dslproj 的 scope_globs，多个模块都匹配时取最长模块名）；不归任何模块 → None。"""
    from fnmatch import fnmatchcase
    from ..packs.dslproj import project as P
    for name in sorted(module_names, key=lambda n: (-len(n), n)):
        if any(fnmatchcase(rel, g) for g in P.scope_globs(name) if not g.startswith("tests/")):
            return name
    return None


def resolve_edit_path(project, module_names, rel):
    """改文件 的文件参数 → (绝对 Path, 项目相对路径, 归属模块, 错误文本)。范围外 / 越界 / 测试文件都给错误。"""
    rel = (rel or "").strip().replace("\\", "/")
    if not rel:
        return None, rel, None, "没写文件"
    root = Path(project).resolve()
    f = (root / rel).resolve()
    try:
        norm = f.relative_to(root).as_posix()
    except ValueError:
        return None, rel, None, f"文件「{rel}」在项目目录之外"
    if norm.startswith("tests/"):
        return None, norm, None, f"不许改测试文件「{norm}」"
    owner = owner_module(module_names, norm)
    if owner is None:
        return None, norm, None, f"文件「{norm}」不属于任何模块的范围（只能改 entities/ services/ routes/ queries/ 下属于某个模块的文件）"
    return f, norm, owner, ""


def read_raw(path):
    """按原样读（不转换换行）：CRLF 文件改完还是 CRLF。"""
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def locate_edit(text, old, new):
    """old 在 text 里的出现次数；text 是 CRLF 而 old 只用 LF 时换成 CRLF 再数（同 code 包 改文件 的 _locate）。→ (次数, old, new)。"""
    n = text.count(old)
    if n == 0 and "\r\n" in text and "\n" in old and "\r\n" not in old:
        crlf = old.replace("\n", "\r\n")
        k = text.count(crlf)
        if k:
            return k, crlf, new.replace("\r\n", "\n").replace("\n", "\r\n")
    return n, old, new


def edit_args(content, braces=True):
    """改文件 行的参数部分 → (文件, 原文, 新文) 已解码；参数个数不是 2～3 个 → None。braces=False：花括号已被引擎还原过（执行时）。"""
    parts = content.split()
    if len(parts) not in (2, 3):
        return None
    d = lambda x: decode_edit_arg(x, braces)
    return d(parts[0]), d(parts[1]), d(parts[2]) if len(parts) == 3 else ""


def issue_modules(item):
    mods = item.get("modules", item.get("涉及模块")) or ""
    if isinstance(mods, (list, tuple)):
        return {str(x).strip() for x in mods if str(x).strip()}
    return {x.strip() for x in re.split(r"[、,，]", str(mods)) if x.strip()}


def planned_files(items):
    """计划里 改文件 的目标文件（解码后，去重保序）。"""
    out = []
    for it in items:
        if it["动词"] == "改文件":
            a = edit_args(it["内容"])
            if a and a[0] not in out:
                out.append(a[0])
    return out


def only_file_edits(items):
    """计划里除了固定收尾动词，全是 改文件 / 验收动词，且至少有一个 改文件 → 不需要重做任何模块、也不需要 build。"""
    body = [it for it in items if it["动词"] != CLOSING_VERB]
    return bool(body) and all(it["动词"] in FILE_ONLY_VERBS for it in body) and any(it["动词"] == "改文件" for it in body)


FILE_CAP = 12000


def code_files_text(project, top, issues_text):
    """类型为 code 的问题涉及的模块，范围内现有文件原文（entities / services / routes / queries，不含 tests），
    每个上限 12000 字，每行前加「  12| 」行号前缀（行号不是内容）。没有 code 类型的问题 → 空串。"""
    from . import issues as IS
    from ..packs.dslproj import project as P
    names = {m["名"] for m in top.get("模块", [])}
    want = set()
    for it in IS.parse_issues(issues_text):
        if it.get("type") == "code":
            want |= issue_modules(it)
    want &= names
    root = Path(project)
    parts = []
    for name in sorted(want):
        for rel in sorted({str(f.relative_to(root)) for g in P.scope_globs(name) for f in root.glob(g) if f.is_file()}):
            if rel.startswith("tests/"):
                continue
            body = (root / rel).read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
            cut = len(body) > FILE_CAP
            body = body[:FILE_CAP]
            num = "\n".join(f"{i:4d}| {l}" for i, l in enumerate(body.splitlines(), 1))
            parts.append(f"### {rel}（模块 {name}）\n```\n{num}\n```" + ("\n（文件过长，后面略）" if cut else ""))
    return "\n\n".join(parts)


def restore_edits(ctx, modules=None):
    """把 ctx.file_edits 登记的文件恢复成改之前的原文（modules 缺省＝全部），登记清掉。→ 恢复的文件数。"""
    n = 0
    with ctx.lock:
        for m in list(ctx.file_edits):
            if modules is not None and m not in modules:
                continue
            for rel, orig in ctx.file_edits.pop(m).items():
                f = Path(ctx.project) / rel
                if orig is None:
                    f.unlink(missing_ok=True)
                else:
                    with open(f, "w", encoding="utf-8", newline="") as fh:
                        fh.write(orig)
                n += 1
    return n

CONTRACT_CAP = 12000


def involved_contracts_text(project, top, issues_text):
    """涉及模块（问题清单各条 modules 的并集，只取 top.zs 里有的；并集为空就取 top.zs 全部模块）的现有约定，
    去掉用例，按模块名排序，每份前面标「### <模块>」，单份超 12000 字截断；没有约定文件的模块跳过。"""
    from . import contracts as CT, issues as IS, planning as PL
    names = {m["名"] for m in top.get("模块", [])}
    want = set()
    for it in IS.parse_issues(issues_text):
        want.update(x.strip() for x in re.split(r"[、,，]", it.get("modules") or "") if x.strip())
    want &= names
    parts = []
    for name in sorted(want or names):
        f = CT.path_of(project, name)
        if not f.is_file():
            continue
        body = PL.without_cases(f.read_text(encoding="utf-8")).strip()
        if len(body) > CONTRACT_CAP:
            body = body[:CONTRACT_CAP] + "\n（后面略）"
        parts.append(f"### {name}\n{body}")
    return "\n\n".join(parts)


def write(ctx, issues_text, task="", model="sonnet"):
    """调一次模型写修改计划文本（未必通过 parse_plan；检查留给 检查修改计划）。"""
    ctx.guard()
    ctx.take_call()
    top_text = ctx.top_path().read_text(encoding="utf-8") if ctx.top_path().is_file() else ""
    from . import catalog as CAT
    cat_f = CAT.path_of(ctx.project)
    catalog_text = cat_f.read_text(encoding="utf-8") if cat_f.is_file() else ""
    from . import top as VT
    contracts_text = involved_contracts_text(ctx.project, VT.parse(top_text)[0], issues_text)
    files_text = code_files_text(ctx.project, VT.parse(top_text)[0], issues_text)
    user = user_text(issues_text, ctx.req, task, top_text, catalog_text, contracts_text, files_text)
    try:
        text = ctx.M(prompt_text("change_plan.md"), user, "v3_change_plan", model or "sonnet")
    except V2.Stop as e:
        raise ScriptHalt("超出预期", str(e), "") from None
    except RuntimeError as e:
        ctx.log("修改计划", 事件="模型没有回应", 原因=str(e)[:200])
        text = ""
    return normalize_plan((text or "").strip()) + "\n"


def save(project, text):
    no = next_no(project)
    d = changes_dir(project)
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{no}.zs"
    p.write_text(text, encoding="utf-8", newline="\n")
    return str(p.relative_to(Path(project)))


SECTION_RE = re.compile(r"^(?:##+\s*(?=[一二三四五六七八九十百]+(?:[.\s、．]|$))|(?:##+\s*)?(?=\d))(\d+(?:\.\d+)*|[一二三四五六七八九十百]+)(?:[.\s、．]|$)")


def req_sections(req_text):
    """需求文本里出现过的节号（「## 3」「3.2 」这类行首数字编号）集合。"""
    out = set()
    for raw in (req_text or "").replace("\r\n", "\n").split("\n"):
        m = SECTION_RE.match(raw.strip())
        if m:
            out.add(m.group(1))
    return out


def _new_mod_deps(items):
    deps = {}
    for it in items:
        if it["动词"] != "新增模块":
            continue
        name = it["内容"].split()[0] if it["内容"].split() else ""
        m = re.search(r"依赖=(\S*)", it["内容"])
        dep_str = m.group(1) if m else ""
        deps[name] = [d for d in re.split(r"[,，]", dep_str) if d and d != "无"]
    return deps


def _check_file_edit(it, issues, project, mod_names, texts):
    line = it["行"]
    a = edit_args(it["内容"])
    if a is None:
        n = len(it["内容"].split())
        return [f"第 {line} 行：改文件 要 2～3 个参数（文件、原文、新文；新文可省＝删掉原文），这行有 {n} 个——原文 / 新文里的空格写 \\_、换行写 \\n、反斜杠写 \\\\，花括号 {{x}} 写成 {{{{x}}}}"]
    if project is None:
        return []
    f, old, new = a
    path, rel, owner, err = resolve_edit_path(project, mod_names, f)
    if err:
        return [f"第 {line} 行：改文件：{err}"]
    tagged = set()
    for no in it["对应问题"]:
        if 1 <= no <= len(issues):
            tagged |= issue_modules(issues[no - 1])
    if tagged and owner not in tagged:
        return [f"第 {line} 行：改文件的「{rel}」属于模块 {owner}，不在对应问题涉及的模块（{'、'.join(sorted(tagged))}）里——只能改问题涉及模块的文件"]
    if rel not in texts:
        if not path.is_file():
            return [f"第 {line} 行：改文件：文件「{rel}」不存在"]
        texts[rel] = read_raw(path)
    if not old:
        return [f"第 {line} 行：改文件：原文是空的"]
    n, old2, new2 = locate_edit(texts[rel], old, new)
    if n == 0:
        return [f"第 {line} 行：改文件：「{rel}」里找不到原文（出现 0 次；要一字不差、缩进一致，别带行号前缀；前面几处改过之后的文本才是这里的对照）。开头：{old.splitlines()[0][:60] if old.splitlines() else ''}"]
    if n > 1:
        return [f"第 {line} 行：改文件：原文在「{rel}」里出现 {n} 次，必须唯一——多带几行上下文让它唯一"]
    if old2 == new2:
        return [f"第 {line} 行：改文件：原文和新文一样，没有改动"]
    texts[rel] = texts[rel].replace(old2, new2)
    return []


def check_plan(text, issues, top, req_text="", project=None):
    """→ 问题列表（空 = 通过）。issues：问题清单条目列表（1 开始编号与原清单一致）；top：top.load 的结果；
    project：给了才检查 改文件（文件存在 / 原文唯一 / 范围）。"""
    items, probs = parse_plan(text)
    if not items and not probs:
        probs.append("计划是空的，没有一行指令")
    content_items = [it for it in items if it["动词"] != CLOSING_VERB]
    if not items or items[-1]["动词"] != CLOSING_VERB:
        probs.append(f"计划最后一行必须是固定的收尾动词「{CLOSING_VERB}」（没有写，或写在了中间）")
    if sum(1 for it in items if it["动词"] == CLOSING_VERB) > 1:
        probs.append(f"「{CLOSING_VERB}」只能出现一次，写在最后一行")
    items = content_items
    mod_names = {m["名"] for m in top.get("模块", [])}
    new_mods = set()
    covered = set()
    file_texts = {}                      # 改文件 检查用：项目相对路径 → 顺序套用前面几处之后的文本
    for it in items:
        covered.update(it["对应问题"])
        verb, content = it["动词"], it["内容"]
        if verb == "新增模块":
            name = content.split()[0] if content.split() else ""
            if not name:
                probs.append(f"第 {it['行']} 行：新增模块 要写模块名")
            elif name in mod_names or name in new_mods:
                probs.append(f"第 {it['行']} 行：新增模块「{name}」已经存在，不能重名")
            else:
                new_mods.add(name)
            if "说明=" not in content:
                probs.append(f"第 {it['行']} 行：新增模块「{name}」没写「说明=」")
        elif verb == "删除模块":
            name = content.strip()
            if name not in mod_names:
                probs.append(f"第 {it['行']} 行：删除模块「{name}」不在 plan/top.zs 里")
        elif verb == "改约定":
            name = content.split()[0] if content.split() else ""
            if len(content.split()) > 2:
                probs.append(f"第 {it['行']} 行：改约定只接受 2 个参数（模块、改动条目），这行有 {len(content.split())} 个——条目里不能有 ASCII 空格，用中文标点分隔")
            if name not in mod_names and name not in new_mods:
                probs.append(f"第 {it['行']} 行：改约定的模块「{name}」不在 plan/top.zs 里（也不是本计划新增的）")
        elif verb == "改文件":
            probs.extend(_check_file_edit(it, issues, project, mod_names | new_mods, file_texts))
        elif verb in ACCEPT_VERBS:
            parts = content.split()
            if len(parts) != 1:
                probs.append(f"第 {it['行']} 行：{verb} 只接受 1 个参数（模块名），这行有 {len(parts)} 个")
            elif parts[0] not in mod_names and parts[0] not in new_mods:
                probs.append(f"第 {it['行']} 行：{verb} 的模块「{parts[0]}」不在 plan/top.zs 里（也不是本计划新增的）")
        elif verb == "改需求":
            sec = content.split()[0] if content.split() else ""
            if len(content.split()) > 2:
                probs.append(f"第 {it['行']} 行：改需求只接受 2 个参数（节号、新正文），这行有 {len(content.split())} 个——新正文里不能有 ASCII 空格（含「## 标题」里的空格：节标题已保留，正文不要重写标题），用中文标点分隔")
            secs = req_sections(req_text)
            if req_text and secs and sec not in secs:
                probs.append(f"第 {it['行']} 行：改需求的节号「{sec}」在需求文本里找不到")
    deps = _new_mod_deps(items)
    all_names = mod_names | new_mods
    from . import top as VT
    for m in top.get("模块", []):
        deps.setdefault(m["名"], m["依赖"])
    for name, ds in deps.items():
        for d in ds:
            if d not in all_names:
                probs.append(f"新增模块「{name}」依赖的「{d}」不是已有模块也不是本计划新增的模块")
    cyc = VT.find_cycle(deps)
    if cyc:
        probs.append("计划里的模块依赖成环：" + " → ".join(cyc))
    want = {i + 1 for i in range(len(issues))}
    missing = sorted(want - covered)
    if missing:
        probs.append("问题清单里这些编号没有被任何一行计划覆盖（# 对应问题 N）：" + "、".join(str(x) for x in missing))
    return probs
