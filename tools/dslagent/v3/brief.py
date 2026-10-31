"""v3 实现简报（确定性，不调模型）：给一个模块 + 本轮要改的函数，整理出写代码之前该知道的事，只是提醒，不拦截。

    python -m tools.dslagent v3 brief --project DIR [--modules a,b] [--out DIR]

  骨架      函数头、入参（必填 / 可选）、返回、报错、接口与路由（scaffold.route_text 渲染，和骨架、比对约定同一份）、公开 / 角色
  依赖接口  伪代码「调用 模块.函数」点到的别模块公开函数：函数头、返回、返回字段；本函数读写的表与列（标出可空列）
  实现要点  只留抽样准的三条（K169）：
            R1 读可空列：现有代码 查一值/查一行 的 SQL 直接 SELECT 可空列（没 COALESCE）；或伪代码在「读」的分句里提到可空列 / 写了 NULL。
               写入的分句、函数入参都不算；函数伪代码已写 COALESCE/IFNULL 就不出
            R2 按位置传参（只看现有代码）：查一值/查一行/查询/写库 app.db q k={v}，v 是拼接文本、模型输出、调用方传入的文本、库里自由文本列。
               编号 / 用户名 / 日期这类名字（_id、_no、code、date、_at…）不算
            R6 编辑浮层字段 ⊆ 表格行字段：.ui 列表的行动作「打开 浮层」，浮层有字段，返回里提到这个列表键的整页函数要在每行带上这些字段
  影响面    契约 diff（git HEAD vs 工作区）：改动函数（new / yes / unknown / no + 伪代码变 / deleted）；建议 --modules = 改动函数所在模块 ∪
            签名变（new/yes/unknown/deleted）函数的直接调用方所在模块；只改伪代码的函数的调用方列为「参考」；直接调用方里契约没改的模块提示「可能漏改契约」
  只读检查  v3/contracts.check 的结果；伪代码提到别模块公开函数名却没写「调用 模块.函数」
v3 fix2 / change2 --brief 只把本模块那一节（只列本轮要改的函数）交给 modify_module（packs/dslproj materials() / fix_input()），不给 audit2 核查员。
"""
import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path

from tools import entity as E

from ..packs.dslproj import contract as C
from . import contracts as VC
from . import scaffold as SF
from . import top as VT

ENV_FILE = "DSLAGENT_BRIEF_FILE"        # modify_module 子进程从这个文件读本模块简报（v3 派代理写，packs/dslproj 读）
SECTION_TITLE = "本模块实现简报（自动推出，只是提醒）"

# ---------------------------------------------------------------- 抽取用的正则
POS_RE = re.compile(r"(?<![\w表])(查一值|查一行|查询|写库)\s+app\.db\s+(\w+)((?:\s+[\w.]+=\S*)*)")
SET_RE = re.compile(r"^\s*设\s+([\w.]+)\s*=\s*(.*)$")
ASKZ_RE = re.compile(r"^\s*设\s+(\w+)\s*=\s*(?:问JSON|问)\s")
ASKZ2_RE = re.compile(r"^\s*(?:问JSON|问)\s+(\w+)\s*=")
FN_RE = re.compile(r"^  (?:公开\s+)?函数\s+(\S+)(.*)$")
BRACE_RE = re.compile(r"\{([^{}]*)\}")
NULLWORD_RE = re.compile(r"可空|可选|允许为空|可以为空|没有时|没有则|为 ?NULL")
WRITE_RE = re.compile(r"插入|更新|删除|删掉|清空|写入|写库|写进|存入|存进|重灌|改成|改为|置为|置空|设为|加一行|写一行|新建|新增|保存|INSERT|UPDATE|DELETE", re.I)
CLAUSE_RE = re.compile(r"[，。；;,]")
SQLW_RE = re.compile(r"\b(?:INSERT\s+(?:OR\s+\w+\s+)?INTO|(?<!DO )UPDATE|DELETE\s+FROM|REPLACE\s+INTO)\s+(\w+)", re.I)
# 不会带首尾空白的参数名（编号 / 用户名 / 科目号 / 数量 / 日期这一类）；K169 抽样漏了 _no，这次连日期类一起补上
IDISH_RE = re.compile(r"(^|_)(id|ids|no|nos|code|codes|n|limit|offset|page|size|count|subject|current_user|current_role|auth_mode|learner|"
                      r"student|teacher|username|role|kind|status|level|mode|at|date|dates|day|days|time|ts|month|year|week|since|until|"
                      r"sort_by|need|point|point_code|direction|qtype|lesson|num|idx|k)$")
FREE_DESC_RE = re.compile(r"名|标题|内容|说明|文本|原文|摘要|解析|提问|回答|备注|设定|预览")
SHORT_DESC_RE = re.compile(r"编号|编码|用户名|时间|日期")
PROP_VERBS = ("替换", "截取", "拼接", "连接", "解析JSON")     # 输出仍是同一段文本（或从它解析出来的）的动词：来源沿着传下去
TEXTY = ("concat", "model", "param", "dbfree")
KIND_ZH = {"concat": "拼接文本", "model": "模型输出", "param": "调用方传入的文本", "dbfree": "库里自由文本"}
SIG_CHANGED = ("new", "yes", "unknown", "deleted")
KEY_RE = re.compile(r"[{,，]\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?=[,，}:：])")


def word_in(w, t):
    return re.search(rf"(?<![A-Za-z0-9_]){re.escape(w)}(?![A-Za-z0-9_])", t) is not None


def ret_fields(text):
    """「返回」里花括号内的键名（{a, b}、[{a, b}]、{k: v} 的 k）；没有花括号 → None（取不出）。"""
    if "{" not in (text or ""):
        return None
    return sorted(set(KEY_RE.findall(text)))


# ---------------------------------------------------------------- 读项目
def load_contracts(project):
    """→ ({模块: 约定}, {模块: 原文}, {模块: 解析问题})。"""
    cs, texts, broken = {}, {}, {}
    for f in sorted((Path(project) / "contracts").glob("*.md")):
        t = f.read_text(encoding="utf-8")
        c, probs = C.parse(t)
        if probs:
            broken[f.stem] = probs
        if c["模块"]:
            cs[c["模块"]], texts[c["模块"]] = c, t
    return cs, texts, broken


def table_columns(project, cs):
    """表 → {列: {"类型", "可空", "说明"}}：先取 entities/*.entity，再用约定「表」段补（约定先于实体时只有约定里有）。
    可空 = 实体没写「必填」也没默认值；或约定说明写了可空 / 可选 / 没有时 / 为 NULL。"""
    out = defaultdict(dict)
    for f in sorted((Path(project) / "entities").glob("*.entity")):
        try:
            ents = E.parse(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001  实体写坏了由加载检查报，这里少一份事实就是了
            continue
        for e in ents:
            if e.page:
                continue
            for fl in e.fields:
                out[e.name][fl.name] = {"类型": fl.type, "可空": not fl.required and not fl.default, "说明": fl.label or ""}
    for c in cs.values():
        for t in c["表"]:
            for fl in t["字段"]:
                col = out[t["名"]].setdefault(fl["名"], {"类型": fl["类型"], "可空": "主键" not in fl["说明"] and fl["名"] != "id",
                                                       "说明": fl["说明"]})
                if NULLWORD_RE.search(fl["说明"]):
                    col["可空"] = True
    return dict(out)


def free_columns(cols):
    """列名 → 是否自由文本（长文本，或说明里带「名 / 标题 / 内容…」的文本列）；同名列跨表合并，有一处是就算。"""
    out = defaultdict(bool)
    for t in cols.values():
        for c, d in t.items():
            free = d["类型"] == "长文本" or (d["类型"] == "文本" and bool(FREE_DESC_RE.search(d["说明"]))
                                            and not SHORT_DESC_RE.search(d["说明"]))
            out[c] = out[c] or free
    return out


def code_blocks(text):
    """services/<m>.zs → {函数: {"head": 入参词, "at": 行号, "lines": [(行号, 原文)]}}，只取 2 格缩进的「函数」块。"""
    fns, cur = {}, None
    for no, ln in enumerate(text.splitlines(), 1):
        m = FN_RE.match(ln)
        if m:
            cur = m.group(1)
            fns[cur] = {"head": m.group(2).split(), "lines": [], "at": no}
            continue
        if cur and (ln.startswith("    ") or not ln.strip()):
            fns[cur]["lines"].append((no, ln))
        elif cur and ln.strip():
            cur = None
    return fns


def sql_info(project, q):
    p = Path(project) / "queries" / f"{q}.sql"
    if not p.is_file():
        return None
    s = p.read_text(encoding="utf-8")
    m = re.search(r"\bSELECT\b(.*?)\bFROM\b", s, re.I | re.S)
    froms = sorted({x for a, b in re.findall(r"\bFROM\s+(\w+)|\bJOIN\s+(\w+)", s, re.I) for x in (a, b) if x})
    return {"writes": sorted({m2.group(1) for m2 in SQLW_RE.finditer(s)}), "select": m.group(1) if m else "", "from": froms}


def parse_ui(project):
    """每个 .ui：列表（绑的键、行上打开的浮层）、浮层字段。"""
    res = []
    for f in sorted((Path(project) / "ui").glob("*.ui")):
        lists, overlays = [], {}
        cur_list = cur_ov = None
        for ln in f.read_text(encoding="utf-8").splitlines():
            s = ln.strip()
            if s.startswith("#"):
                continue
            m = re.match(r"^列表\s+\S+\s+绑\s+(\w+)", s)
            if m:
                cur_list, cur_ov = {"key": m.group(1), "opens": []}, None
                lists.append(cur_list)
                continue
            m = re.match(r"^浮层\s+(\S+)", s)
            if m:
                cur_ov, cur_list = overlays.setdefault(m.group(1), []), None
                continue
            if cur_list is not None:
                m = re.match(r"^动作\s+\S+\s+打开\s+(\S+)", s)
                if m:
                    cur_list["opens"].append(m.group(1))
            if cur_ov is not None:
                m = re.match(r"^字段\s+(\w+)", s)
                if m:
                    cur_ov.append(m.group(1))
        res.append({"file": f.name, "lists": lists, "overlays": overlays})
    return res


# ---------------------------------------------------------------- 规则
def _clauses(text):
    return [x for x in CLAUSE_RE.split(text) if x.strip()]


def contract_reads(fn, cols):
    """伪代码里「读」到的可空列（同一行提到表名；列所在分句没有写入动词；不是函数入参）→ ([表.列], [写了 NULL 的行])。"""
    params = {p.rstrip("?") for p in fn["入参"]}
    hit, nulls = [], []
    for p in fn["伪代码"]:
        t = p["文字"]
        for tb, tcols in cols.items():
            if not word_in(tb, t):
                continue
            for cl in _clauses(t):
                if WRITE_RE.search(cl):
                    continue
                for col, d in tcols.items():
                    if d["可空"] and col not in params and word_in(col, cl):
                        hit.append(f"{tb}.{col}")
        if "NULL" in t and any("NULL" in cl and not WRITE_RE.search(cl) for cl in _clauses(t)):
            nulls.append(p["行"])
    return sorted(set(hit)), nulls


def code_verbs(project):
    """业务层能用的动词名（db / common / text / data 包 + 调用 / 计算 / 问 / 问JSON）：分辨「设 x = 动词 …」和「设 x = 拼接文本」。"""
    from .. import loadcheck as LC
    try:
        names = set(LC.load_verbs(Path(project), ["db", "common", "text", "data"]).names())
    except Exception:  # noqa: BLE001  动词表读不出就只认下面这几个
        names = set()
    return names | {"调用", "计算", "问", "问JSON"} | set(PROP_VERBS)


def code_facts(project, module, blk, cols, free, verbs=()):
    """一个函数的现有代码 → {"raw": [查询:表.列@行], "pos": [{行, 查询, 参数, 来源}], "queries": [..], "writes": [..], "sql": {查询: sql_info}}。"""
    params = {x.rstrip("?") for x in blk["head"]}
    src, raw, pos, queries, writes, sqls = {}, [], [], [], [], {}
    for no, ln in blk["lines"]:
        s = ln.strip()
        if s.startswith("#"):
            continue
        ma = ASKZ_RE.match(ln) or ASKZ2_RE.match(ln)
        if ma:
            src[ma.group(1)] = "model"
        ms = SET_RE.match(ln)
        if ms and not ma:
            var, rhs = ms.group(1), ms.group(2).strip()
            first = rhs.split()[0] if rhs.split() else ""
            inner = [x.split()[0].split(".")[0] for x in BRACE_RE.findall(rhs) if x.split()]
            if first in PROP_VERBS:
                kinds = [src.get(x) or ("param" if x in params and not IDISH_RE.search(x) else None) for x in inner]
                kinds = [k for k in kinds if k in TEXTY]
                if kinds:
                    src[var] = "model" if "model" in kinds else "concat"
            elif first in ("查一值", "查一行", "查询"):
                src.setdefault(var, "db")
            elif first in verbs or first.startswith(("[", "-")) or re.fullmatch(r"-?\d+(\.\d+)?", rhs):
                pass
            elif "{" in rhs and not re.fullmatch(r"\{[^{}]*\}", rhs):
                src[var] = "concat"
            elif re.fullmatch(r"\{([\w.]+)(?:\s+或[^{}]*)?\}", rhs):
                ref = rhs[1:].split("}")[0].split()[0]
                base = ref.split(".")[0]
                if "." in ref:
                    if free.get(ref.split(".")[-1]) and not IDISH_RE.search(ref.split(".")[-1]):
                        src[var] = "dbfree"
                elif src.get(base) in TEXTY:
                    src[var] = src[base]
                elif base in params and not IDISH_RE.search(base):
                    src[var] = "param"
        for mp in POS_RE.finditer(ln):
            verb, q, args = mp.groups()
            queries.append(q)
            qi = sqls[q] = sql_info(project, q)
            if qi:
                writes += qi["writes"]
                if verb in ("查一值", "查一行"):
                    row_var = ms.group(1) if ms and verb == "查一行" else None
                    for tb in qi["from"]:
                        for col, d in cols.get(tb, {}).items():
                            if d["可空"] and word_in(col, qi["select"]) and not re.search(
                                    rf"(?:COALESCE|IFNULL)\s*\([^)]*\b{re.escape(col)}\b", qi["select"], re.I):
                                raw.append((f"{q}:{tb}.{col}@{no}", row_var, col))
            for k, v in re.findall(r"([\w.]+)=(\S*)", args):
                mv = re.fullmatch(r"\{([\w.]+)(?:\s+或[^{}]*)?\}", v)
                if not mv:
                    continue
                ref = mv.group(1)
                base, kind = ref.split(".")[0], None
                if "." in ref:
                    col = ref.split(".")[-1]
                    if free.get(col) and not IDISH_RE.search(col):
                        kind = "dbfree"
                elif src.get(base) in TEXTY:
                    kind = src[base]
                elif base in params and not IDISH_RE.search(base):
                    kind = "param"
                if kind and not IDISH_RE.search(k):
                    pos.append({"行": no, "查询": q, "参数": f"{k}={{{ref}}}", "来源": kind})
    # 查一行 取到的可空列，函数里从没用过（没有 {行.列…}）就不算：只用来判断有没有这行（K169 抽样 vocab.删除单词）
    body = "\n".join(ln for _, ln in blk["lines"])
    raw = [r for r, v, col in raw if v is None or re.search(rf"\{{{re.escape(v)}\.{re.escape(col)}\b", body)]
    return {"raw": raw, "pos": pos, "queries": sorted(set(queries)), "writes": sorted(set(writes)), "sql": sqls}


def hints_for(module, fn, cols, cf, ui, fname):
    """一个函数的实现要点 [{rule, note, why}]。cf：code_facts（没有现有代码时 None）。"""
    out = []
    texts = [fn["返回"]] + [p["文字"] for p in fn["伪代码"]]
    says_coalesce = any(re.search(r"COALESCE|IFNULL", t, re.I) for t in texts)
    rd, nulls = contract_reads(fn, cols)
    raw = (cf or {}).get("raw") or []
    if (rd or nulls or raw) and not says_coalesce:
        why = []
        if rd:
            why.append("约定在读的地方提到可空列 " + "、".join(rd))
        if nulls:
            why.append("约定写了 NULL：" + "、".join(f"{fname}:{n}" for n in nulls))
        if raw:
            why.append("现有查询直接取可空列：" + "、".join(sorted({r.split("@")[0] for r in raw})))
        cols_txt = "、".join(sorted(set(rd) | {r.split(":")[1].split("@")[0] for r in raw})) or "可空列"
        out.append({"rule": "R1", "note": f"读 {cols_txt}：查询里写 COALESCE(列, '') AS 列（查一值/查一行 取到 NULL 会变成文本 None，"
                                          f"「{{x 或}}」兜不住）；取行字段时写 {{行.字段 或 默认}}", "why": "；".join(why)})
    pos = (cf or {}).get("pos") or []
    if pos:
        items = sorted({f"{p['参数']}→{p['查询']}（第 {p['行']} 行）" for p in pos})
        kinds = sorted({p["来源"] for p in pos})
        out.append({"rule": "R2", "note": "这些参数按位置 k={v} 传，值有首尾空白时直接报错：装进对象，用 查一值表/查一行表/查询表/写库表 传（"
                                          + "；".join(items) + "）",
                    "why": "来源：" + "、".join(KIND_ZH[k] for k in kinds) + f"；位置：services/{module}.zs " + "、".join(
                        str(n) for n in sorted({p['行'] for p in pos}))})
    page = bool(re.search(r"整页|页面状态|形状同", fn["返回"])) or fn["名"].endswith("页面")
    mentions = set(re.findall(r"\b([a-z_][a-z0-9_]*)\b", fn["返回"]))
    if page:
        for u in ui:
            for L in u["lists"]:
                if L["key"] not in mentions:
                    continue
                flds = sorted({x for ov in L["opens"] for x in u["overlays"].get(ov, [])})
                if not flds:
                    continue
                missing = [x for x in flds if x not in mentions]
                out.append({"rule": "R6", "note": f"表格行 {L['key']} 的每一行必须带上编辑浮层字段 {'、'.join(flds)}（从行上点开浮层时前端直接拿这一行填表单、"
                                                  "不发载入）" + (f"；约定返回里没列出：{'、'.join(missing)}" if missing else ""),
                            "why": f"ui/{u['file']} 列表 {L['key']} 的行动作打开浮层 {'、'.join(L['opens'])}"})
    return out


# ---------------------------------------------------------------- 骨架 / 依赖
def calls_of(fn, module):
    """伪代码里「调用 模块.函数」点到的别模块函数 → [(模块, 函数)]（去重保序）。"""
    out = []
    for p in fn["伪代码"]:
        for m in C.QCALL_RE.finditer(p["文字"]):
            if m.group(1) != module and (m.group(1), m.group(2)) not in out:
                out.append((m.group(1), m.group(2)))
    return out


def skeleton(module, c, fn, cs):
    req, opt, _ = C.params(fn)
    routes = []
    for i in c["接口"]:
        if i["函数"] != fn["名"]:
            continue
        try:
            body = SF.route_text(module, dict(c, 接口=[i]), {module: c}).strip()
        except Exception as e:  # noqa: BLE001  模板 / 封装写坏了由约定检查报
            body = f"（路由渲染不出：{e}）"
        who = "公开（不用登录）" if i["公开"] else (f"角色 {i['角色']}" if i["角色"] else "登录即可")
        routes.append({"接口": f"{i['方法']} {i['路径']}", "身份": who, "动作": i["动作"], "路由": body})
    return {"函数头": C.head_text(fn), "必填": req, "可选": opt, "返回": fn["返回"], "返回字段": ret_fields(fn["返回"]),
            "报错": [f"{e['码']} {e['文字']}".strip() for e in fn["报错"]], "接口": routes}


def deps_of(module, fn, cs, cols, cf):
    ups = []
    for m, name in calls_of(fn, module):
        uc = cs.get(m)
        uf = next((f for f in (uc or {}).get("函数", []) if f["名"] == name), None)
        if uf is None:
            ups.append({"函数": f"{m}.{name}", "问题": f"{m} 的约定里没有这个函数"})
            continue
        ups.append({"函数": f"{m}.{name}", "函数头": C.head_text(uf), "公开": uf["公开"], "返回": uf["返回"], "返回字段": ret_fields(uf["返回"])})
    reads, writes = set(), set((cf or {}).get("writes") or [])
    for p in fn["伪代码"]:
        t = p["文字"]
        for tb in cols:
            if word_in(tb, t):
                (writes if any(WRITE_RE.search(cl) and word_in(tb, cl) for cl in _clauses(t)) else reads).add(tb)
    for qi in ((cf or {}).get("sql") or {}).values():
        reads.update((qi or {}).get("from", []))
    tables = []
    for tb in sorted(reads | writes):
        tcols = cols.get(tb, {})
        tables.append({"表": tb, "读": tb in reads, "写": tb in writes,
                       "列": [c + ("（可空）" if d["可空"] else "") for c, d in tcols.items()]})
    return {"调用": ups, "表": tables}


# ---------------------------------------------------------------- 影响面
def sig_changed(old, new):
    if old is None:
        return "new"
    if old["入参"] != new["入参"]:
        return "yes"
    if old["返回"] == new["返回"]:
        return "no"
    a, b = ret_fields(old["返回"]), ret_fields(new["返回"])
    if a is None or b is None:
        return "unknown"
    return "yes" if a != b else "no"


def git_base_texts(project, rev="HEAD"):
    """git <rev> 里 <project>/contracts/*.md 的原文 → {文件名去 .md: 原文}；项目不在 git 仓库里 → None。"""
    project = Path(project).resolve()
    try:
        top = subprocess.run(["git", "-C", str(project), "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    rel = project.relative_to(Path(top).resolve()).as_posix()
    pre = f"{rel}/contracts/" if rel != "." else "contracts/"
    ls = subprocess.run(["git", "-C", top, "ls-tree", "--name-only", rev, pre], capture_output=True, text=True)
    if ls.returncode != 0:
        return None
    out = {}
    for path in ls.stdout.split():
        if path.endswith(".md"):
            r = subprocess.run(["git", "-C", top, "show", f"{rev}:{path}"], capture_output=True)
            if r.returncode == 0:
                out[Path(path).stem] = r.stdout.decode("utf-8", "replace")
    return out


def impact(base_texts, cur_texts):
    """契约 diff → {改动函数: [{函数, 签名, 伪代码变}], 建议模块, 参考模块, 可能漏改契约, 理由}。base_texts / cur_texts：{模块: 原文}。"""
    def fns(texts):
        out, mods = {}, {}
        for name, t in texts.items():
            c, _ = C.parse(t)
            m = c["模块"] or name
            mods[m] = c
            for f in c["函数"]:
                out[(m, f["名"])] = f
        return out, mods
    a, _ = fns(base_texts)
    b, cur_mods = fns(cur_texts)
    changed = []
    for k in sorted(set(a) | set(b)):
        old, new = a.get(k), b.get(k)
        if new is None:
            changed.append({"函数": f"{k[0]}.{k[1]}", "签名": "deleted", "伪代码变": False})
            continue
        sc = sig_changed(old, new)
        bc = old is not None and [p["文字"] for p in old["伪代码"]] != [p["文字"] for p in new["伪代码"]]
        if sc == "no" and not bc:
            continue
        changed.append({"函数": f"{k[0]}.{k[1]}", "签名": sc, "伪代码变": bool(bc)})
    callers = defaultdict(set)              # 被调函数 → 调用方模块（只看别模块的直接调用）
    for (m, _), f in b.items():
        for um, uf in calls_of(f, m):
            callers[f"{um}.{uf}"].add(m)
    for (m, _), f in a.items():             # 删掉的函数：调用方取改前契约
        for um, uf in calls_of(f, m):
            if f"{um}.{uf}" in {x["函数"] for x in changed if x["签名"] == "deleted"}:
                callers[f"{um}.{uf}"].add(m)
    why = defaultdict(list)
    for x in changed:
        why[x["函数"].split(".", 1)[0]].append(f"{x['函数']} 改了（签名 {x['签名']}{'，伪代码变' if x['伪代码变'] else ''}）")
    norm = C.normalize
    text_changed = sorted(m for m in set(base_texts) | set(cur_texts) if norm(base_texts.get(m, "")) != norm(cur_texts.get(m, "")))
    for m in text_changed:
        if m not in why:
            why[m].append("约定文件改了（函数以外的部分）")
    suggest, ref = set(why), defaultdict(list)
    for x in changed:
        for cm in sorted(callers.get(x["函数"], ())):
            if x["签名"] in SIG_CHANGED:
                suggest.add(cm)
                why[cm].append(f"直接调用 {x['函数']}（签名 {x['签名']}）")
            else:
                ref[cm].append(x["函数"])
    changed_mods = {x["函数"].split(".", 1)[0] for x in changed} | set(text_changed)
    missed = sorted(m for m in suggest if m not in changed_mods)
    return {"改动函数": changed, "建议模块": sorted(suggest), "参考模块": {m: sorted(set(v)) for m, v in sorted(ref.items()) if m not in suggest},
            "可能漏改契约": missed, "理由": {m: why[m] for m in sorted(suggest)}}


# ---------------------------------------------------------------- 只读检查
def lint_mentions(cs):
    """伪代码提到别模块公开函数名却没写「调用 模块.函数」→ [{模块, 函数, 行, 提到}]。本模块也有同名函数的不算；名字少于 3 个字的不算。"""
    pub = defaultdict(set)
    for m, c in cs.items():
        for f in c["函数"]:
            if f["公开"] and len(f["名"]) >= 3:
                pub[f["名"]].add(m)
    out = []
    for m, c in cs.items():
        own = {f["名"] for f in c["函数"]}
        for f in c["函数"]:
            for p in f["伪代码"]:
                t = p["文字"]
                called = {(x.group(1), x.group(2)) for x in C.QCALL_RE.finditer(t)}
                for name, owners in pub.items():
                    if name in own or name not in t:
                        continue
                    others = sorted(o for o in owners if o != m)
                    if others and not any((o, name) in called for o in others):
                        out.append({"模块": m, "函数": f["名"], "行": p["行"], "提到": name, "所在模块": others})
    return out


def contract_checks(project, modules, texts):
    tf = Path(project) / "plan" / "top.zs"
    if not tf.is_file():
        return {m: ["没有 plan/top.zs，跳过约定检查"] for m in modules}
    try:
        top = VT.load(tf.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        return {m: [f"plan/top.zs 读不出：{e}"] for m in modules}
    out = {}
    for m in modules:
        try:
            out[m] = VC.check(texts[m], m, top, project) if m in texts else [f"没有 contracts/{m}.md"]
        except Exception as e:  # noqa: BLE001  检查自己出错不挡简报
            out[m] = [f"约定检查出错：{type(e).__name__}: {e}"]
    return out


# ---------------------------------------------------------------- 组装
def module_brief(project, module, functions=None, cs=None, cols=None, ui=None):
    """一个模块的简报 {模块, 函数: [{名, 骨架, 依赖, 要点}]}；functions 为 None = 全部函数，给了只列这些（不在约定里的忽略）。"""
    project = Path(project)
    if cs is None:
        cs = load_contracts(project)[0]
    if cols is None:
        cols = table_columns(project, cs)
    if ui is None:
        ui = parse_ui(project)
    c = cs.get(module)
    if c is None:
        return {"模块": module, "函数": [], "问题": f"没有 contracts/{module}.md 或解析不出模块名"}
    free = free_columns(cols)
    svc = project / "services" / f"{module}.zs"
    blocks = code_blocks(svc.read_text(encoding="utf-8")) if svc.is_file() else {}
    want = None if functions is None else set(functions)
    verbs = code_verbs(project) if blocks else set()
    out = []
    for fn in c["函数"]:
        if want is not None and fn["名"] not in want:
            continue
        blk = blocks.get(fn["名"])
        cf = code_facts(project, module, blk, cols, free, verbs) if blk else None
        item = {"名": fn["名"], "行": fn["行"], "骨架": skeleton(module, c, fn, cs), "依赖": deps_of(module, fn, cs, cols, cf),
                "要点": hints_for(module, fn, cols, cf, ui, f"contracts/{module}.md"), "有代码": bool(blk)}
        out.append(item)
    return {"模块": module, "函数": out}


def build(project, modules=None, base_texts=None, functions=None):
    """整份简报：{影响面, 模块: [module_brief], 约定检查, 调用lint}。
    modules 为 None → 影响面的改动函数所在模块（函数只列改了的）；base_texts 为 None → git HEAD 的契约（取不到就没有影响面）。
    functions：{模块: [函数名]}，给了就按它列函数。"""
    project = Path(project)
    cs, texts, broken = load_contracts(project)
    cols, ui = table_columns(project, cs), parse_ui(project)
    if base_texts is None:
        base_texts = git_base_texts(project)
    imp = impact(base_texts, texts) if base_texts is not None else None
    changed = defaultdict(list)
    for x in (imp or {}).get("改动函数", []):
        if x["签名"] != "deleted":
            m, f = x["函数"].split(".", 1)
            changed[m].append(f)
    mods = list(modules) if modules else sorted(changed)
    briefs = []
    for m in mods:
        fl = (functions or {}).get(m)
        if fl is None and m in changed:
            fl = changed[m]
        briefs.append(module_brief(project, m, fl, cs, cols, ui))
    lint = [x for x in lint_mentions(cs) if not mods or x["模块"] in mods]
    return {"项目": str(project), "影响面": imp, "模块": briefs, "约定检查": contract_checks(project, mods, texts),
            "调用lint": lint, "约定解析问题": broken}


def _fn_md(item, full=True):
    sk, dp = item["骨架"], item["依赖"]
    L = [f"### 函数 {item['名']}（约定第 {item['行']} 行{'' if item['有代码'] else '，还没有代码'}）"]
    if full:
        L.append(f"- 函数头：`{sk['函数头']}`；必填 {('、'.join(sk['必填']) or '无')}；可选 {('、'.join(sk['可选']) or '无')}")
        if sk["返回"]:
            L.append(f"- 返回：{sk['返回']}" + (f"（字段 {'、'.join(sk['返回字段'])}）" if sk["返回字段"] else ""))
        if sk["报错"]:
            L.append("- 报错：" + "；".join(sk["报错"]))
        for r in sk["接口"]:
            L.append(f"- 接口 {r['接口']}，{r['身份']}{('，动作 ' + r['动作']) if r['动作'] else ''}；路由（程序生成，照抄）：")
            L.append("```\n" + r["路由"] + "\n```")
        for u in dp["调用"]:
            if "问题" in u:
                L.append(f"- 调用 {u['函数']}：{u['问题']}")
            else:
                L.append(f"- 调用 {u['函数']}：`{u['函数头']}`" + (f" → 返回 {u['返回']}" if u["返回"] else "")
                         + ("" if u["公开"] else "（不是公开函数，不能跨模块调用）"))
        for t in dp["表"]:
            rw = "读写" if t["读"] and t["写"] else ("写" if t["写"] else "读")
            L.append(f"- {rw}表 {t['表']}：" + ("、".join(t["列"]) or "（没有列信息）"))
    for h in item["要点"]:
        L.append(f"- 【{h['rule']}】{h['note']}（依据：{h['why']}）")
    return "\n".join(L)


def module_md(mb, full=True):
    """一个模块的简报 → markdown（给 modify_module 的那一节就是它）。"""
    if not mb["函数"]:
        return f"（{mb.get('问题') or '没有要列的函数'}）"
    return "\n\n".join(_fn_md(x, full) for x in mb["函数"])


def impact_md(imp):
    if imp is None:
        return "（项目不在 git 仓库里或取不到 HEAD 的契约，没有影响面）"
    if not imp["改动函数"] and not imp["建议模块"]:
        return "契约和 HEAD 一样，没有改动。"
    L = ["改动函数：" + "；".join(f"{x['函数']}（签名 {x['签名']}{'，伪代码变' if x['伪代码变'] else ''}）" for x in imp["改动函数"]),
         f"建议 --modules {','.join(imp['建议模块'])}"]
    for m, w in imp["理由"].items():
        L.append(f"- {m}：" + "；".join(w))
    if imp["参考模块"]:
        L.append("参考（调用的函数只改了伪代码，一般不用改）：" + "；".join(f"{m}（{'、'.join(v)}）" for m, v in imp["参考模块"].items()))
    if imp["可能漏改契约"]:
        L.append("可能漏改契约（直接调用了签名变的函数，自己的契约却没改）：" + "、".join(imp["可能漏改契约"]))
    return "\n".join(L)


def to_md(b):
    L = ["# 实现简报（自动推出，只是提醒；以约定为准）", "", "## 影响面", impact_md(b["影响面"])]
    for mb in b["模块"]:
        L += ["", f"## 模块 {mb['模块']}", module_md(mb)]
    probs = {m: p for m, p in b["约定检查"].items() if p}
    L += ["", "## 只读检查（提醒，不拦截）"]
    if probs:
        L += [f"- 约定检查 {m}：" + "；".join(p) for m, p in probs.items()]
    else:
        L.append("- 约定检查：点名模块都通过" if b["约定检查"] else "- 约定检查：没有点名模块")
    for x in b["调用lint"]:
        L.append(f"- {x['模块']}.{x['函数']}（约定第 {x['行']} 行）提到 {'、'.join(x['所在模块'])} 的公开函数「{x['提到']}」，却没写「调用 模块.{x['提到']}」")
    for m, p in b["约定解析问题"].items():
        L.append(f"- contracts/{m}.md 解析问题：{p[0]}")
    return "\n".join(L) + "\n"


HAVE_LIST_RE = re.compile(r"[（(]有[：:][^）)；\n]*[）)]?")      # 清单可能被截断、没有右括号：截到右括号 / 分号 / 换行


def functions_in_task(task, c):
    """任务文本（核查问题）里点名的本模块函数名。先去掉报错原文里的「（有：科目访问、列我的科目…）」清单
    （跑用例报「没有函数 X」时会列出模块全部函数，K171 实验 B 因此把 subject 32 个函数全列进了简报）。"""
    t = HAVE_LIST_RE.sub("", task or "")
    # 函数名前后不是汉字 / 字母数字才算点名（「科目助手设定」、assist.生成草稿、科目助手设定_用例名），免得「本科目」命中「本科目等级」这类句子；
    # 一个都对不上时退回子串匹配（问题原文里函数名紧贴着汉字写的也能认出来）
    strict = [f["名"] for f in c["函数"]
              if re.search(rf"(?<![\u4e00-\u9fffA-Za-z0-9]){re.escape(f['名'])}(?![\u4e00-\u9fffA-Za-z0-9])", t)]
    return strict or [f["名"] for f in c["函数"] if f["名"] in t]


def unimplemented(project, module, c):
    """约定里有、services/<模块>.zs 里还没有代码（没有这个函数块，或者块里是骨架的「报错 未实现」）的函数名。"""
    svc = Path(project) / "services" / f"{module}.zs"
    blocks = code_blocks(svc.read_text(encoding="utf-8")) if svc.is_file() else {}
    return [f["名"] for f in c["函数"] if f["名"] not in blocks
            or any(ln.strip() == "报错 未实现" for _, ln in blocks[f["名"]]["lines"])]


def section_for(project, module, task="", base_texts=None):
    """给 modify_module 的「本模块实现简报」一节的正文：只列本轮要改的函数（任务里点名的 ∪ 契约 diff 里本模块改了的 ∪ 还没实现的）；
    都没有 → 只列出了要点的函数（不带骨架）；还是没有 → 空串（不加这一节）。"""
    project = Path(project)
    cs, texts, _ = load_contracts(project)
    c = cs.get(module)
    if c is None:
        return ""
    if base_texts is None:
        base_texts = git_base_texts(project)
    names = functions_in_task(task, c)
    if base_texts is not None:
        names += [x["函数"].split(".", 1)[1] for x in impact(base_texts, texts)["改动函数"]
                  if x["函数"].split(".", 1)[0] == module and x["签名"] != "deleted"]
    names += unimplemented(project, module, c)
    names = list(dict.fromkeys(names))
    if names:
        return module_md(module_brief(project, module, names, cs))
    mb = module_brief(project, module, None, cs)
    mb["函数"] = [x for x in mb["函数"] if x["要点"]]
    return module_md(mb, full=False) if mb["函数"] else ""


def read_section(module):
    """modify_module 子进程里：环境变量 DSLAGENT_BRIEF_FILE 指向的 JSON {模块, 正文}，模块对得上就返回正文，否则空串。"""
    import os
    f = os.environ.get(ENV_FILE)
    if not f:
        return ""
    try:
        d = json.loads(Path(f).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    return d.get("正文", "") if d.get("模块") == module else ""


def main(project, modules=None, out=None):
    """CLI：python -m tools.dslagent v3 brief。写 out/brief.json、brief.md（没给 out 就打印 md），返回简报 dict。"""
    b = build(project, modules=modules)
    md = to_md(b)
    if out:
        o = Path(out)
        o.mkdir(parents=True, exist_ok=True)
        (o / "brief.json").write_text(json.dumps(b, ensure_ascii=False, indent=1), encoding="utf-8")
        (o / "brief.md").write_text(md, encoding="utf-8")
    else:
        print(md)
    return b
