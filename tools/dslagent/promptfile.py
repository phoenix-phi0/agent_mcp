"""提示词文件加载（带缓存；文件缺失 / 不是 UTF-8 / 模板缺占位直接报清楚的错）。两部分：

1. 旧路径文本：从 tools/dslagent/prompts/（现在只剩 legacy/）按相对路径读。
   text(rel)      文件原文，逐字（不去首尾换行、不改换行符）。
   tpl(rel, **kw) 模板：按 str.format 填占位（文件里的字面花括号写 {{ }}）；缺占位报 KeyError 并带文件名。
   js(rel)        JSON 文件解析后的对象。
2. agent 文件：tools/dslagent/agents/<名>.md（一个 agent 一个文件），公用大块在 agents/shared/。约定见 agents/README.md。
   agent_doc(名)               解析：frontmatter（meta）、正文（body）、「## 变体：xx」（variants）、「## 模板：xx」（templates）
   render(名, engine=, **vars) 展开正文：单独一行 `{{插入 路径}}` 换成 shared/ 下该文件的原文（`lib/…` 指 tools/dslagent/lib/），
                               路径里的 `{包}` 换成 vars["包"]（缺省 code）；正文只有一行 `{{沿用 别的.md}}` 就整个用那个 agent 的；
                               最后按 engine 选「## 变体：<engine>」，把「### 原文」换成「### 改成」（原文必须找得到，找不到报错）。
   template(名, 模板名, **kw)  「## 模板：xx」小节按 str.format 填占位。
   shared(rel)                 agents/shared/ 下文件原文，逐字。
"""
import json
import re
from pathlib import Path

DIR = Path(__file__).resolve().parent / "prompts"
AGENTS_DIR = Path(__file__).resolve().parent / "agents"
SHARED_DIR = AGENTS_DIR / "shared"
LIB_DIR = Path(__file__).resolve().parent / "lib"
_cache = {}


def text(rel):
    if rel not in _cache:
        p = DIR / rel
        try:
            raw = p.read_bytes()
        except OSError as e:
            raise FileNotFoundError(f"提示词文件读不到：{p}（prompts/ 下的 {rel}）：{e}") from None
        try:
            _cache[rel] = raw.decode("utf-8")
        except UnicodeDecodeError as e:
            raise ValueError(f"提示词文件不是 UTF-8：{p}：{e}") from None
    return _cache[rel]


def tpl(rel, **kw):
    try:
        return text(rel).format(**kw)
    except KeyError as e:
        raise KeyError(f"提示词模板 {DIR / rel} 里的占位 {e} 没有给值（给了：{'、'.join(sorted(kw))}）") from None
    except (IndexError, ValueError) as e:
        raise ValueError(f"提示词模板 {DIR / rel} 的占位写法不对：{e}（字面花括号写成 {{{{ }}}}）") from None


def js(rel):
    try:
        return json.loads(text(rel))
    except json.JSONDecodeError as e:
        raise ValueError(f"提示词文件 {DIR / rel} 不是合法 JSON：{e}") from None


# ------------------------------------------------------------------ agent 文件

_HEAD = re.compile(r"^## (变体|模板)：(.+?)[ \t]*$", re.M)
_INSERT = re.compile(r"^\{\{插入 (.+?)\}\}$", re.M)
_REUSE = re.compile(r"\{\{沿用 (.+?)\}\}")
_PAIR = re.compile(r"^### (原文|改成)[ \t]*$", re.M)


def _read(p, what):
    try:
        return p.read_bytes().decode("utf-8")
    except OSError as e:
        raise FileNotFoundError(f"{what}读不到：{p}：{e}") from None
    except UnicodeDecodeError as e:
        raise ValueError(f"{what}不是 UTF-8：{p}：{e}") from None


def shared(rel):
    """agents/shared/ 下的文件原文，逐字（lib/ 开头的指 tools/dslagent/lib/）。"""
    key = ("shared", rel)
    if key not in _cache:
        p = LIB_DIR / rel[4:] if rel.startswith("lib/") else SHARED_DIR / rel
        _cache[key] = _read(p, "公用提示词文件")
    return _cache[key]


def _clip(t, tail):
    """小节文字去掉标题行的换行和后面的一个空行（正文开头没有标题，只有 frontmatter 后已去掉的空行）；
    tail="more" 去掉末尾的分隔空行（后面还有小节），否则去掉文件末尾的一个换行。"""
    if t.startswith("\n\n"):
        t = t[2:]
    if tail == "more":
        t = t[:-2] if t.endswith("\n\n") else t
    elif t.endswith("\n"):
        t = t[:-1]
    return t


class Doc:
    def __init__(self, path):
        self.path = path
        raw = _read(path, "agent 文件")
        m = re.match(r"---\n(.*?)\n---\n\n", raw, re.S)
        if not m:
            raise ValueError(f"agent 文件 {path} 开头要有 frontmatter（--- 包起来的「键: 值」行，后面空一行再写正文）")
        self.meta = {}
        for ln in m.group(1).split("\n"):
            k, sep, v = ln.partition(":")
            if not sep:
                k, sep, v = ln.partition("：")
            if not sep:
                raise ValueError(f"agent 文件 {path} 的 frontmatter 行不是「键: 值」：{ln!r}")
            self.meta[k.strip()] = v.strip()
        rest = raw[m.end():]
        marks = list(_HEAD.finditer(rest))
        self.body = _clip(rest[:marks[0].start()] if marks else rest, "more" if marks else "end")
        self.variants, self.templates = {}, {}
        for i, h in enumerate(marks):
            last = i + 1 == len(marks)
            seg = rest[h.end():(len(rest) if last else marks[i + 1].start())]
            seg = _clip(seg, "end" if last else "more")
            (self.variants if h.group(1) == "变体" else self.templates)[h.group(2)] = (
                self._pairs(seg, h.group(2)) if h.group(1) == "变体" else seg)

    def _pairs(self, seg, name):
        ps = list(_PAIR.finditer(seg))
        out, i = [], 0
        while i < len(ps):
            if ps[i].group(1) != "原文" or i + 1 >= len(ps) or ps[i + 1].group(1) != "改成":
                raise ValueError(f"{self.path} 的「变体：{name}」里「### 原文」「### 改成」要成对、按这个顺序")
            a = _clip(seg[ps[i].end():ps[i + 1].start()], "more")
            b = _clip(seg[ps[i + 1].end():(ps[i + 2].start() if i + 2 < len(ps) else len(seg))],
                      "more" if i + 2 < len(ps) else "end")
            out.append((a, b))
            i += 2
        return out


def agent_doc(name):
    name = name if name.endswith(".md") else name + ".md"
    key = ("agent", name)
    if key not in _cache:
        _cache[key] = Doc(AGENTS_DIR / name)
    return _cache[key]


def render(name, engine=None, **vars):
    d = agent_doc(name)
    vars.setdefault("包", "code")
    m = _REUSE.fullmatch(d.body.strip())
    if m:
        return render(m.group(1), engine, **vars)
    text = _INSERT.sub(lambda m: shared(m.group(1).replace("{包}", vars["包"])), d.body)
    for a, b in d.variants.get(engine or "", ()):
        if a not in text:
            raise ValueError(f"{d.path} 的「变体：{engine}」：原文在提示词里找不到：{a[:40]!r}…")
        text = text.replace(a, b, 1)
    return text


def template(name, tname, **kw):
    d = agent_doc(name)
    if tname not in d.templates:
        raise KeyError(f"{d.path} 里没有「## 模板：{tname}」")
    try:
        return d.templates[tname].format(**kw)
    except KeyError as e:
        raise KeyError(f"{d.path} 的模板「{tname}」里的占位 {e} 没有给值（给了：{'、'.join(sorted(kw))}）") from None
    except (IndexError, ValueError) as e:
        raise ValueError(f"{d.path} 的模板「{tname}」占位写法不对：{e}（字面花括号写成 {{{{ }}}}）") from None
