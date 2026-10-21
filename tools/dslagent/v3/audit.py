"""核查.zs 用的 Python 部分（动词的壳在 verbs/v3/defs）：

  tasks(...)      核查任务表：每个模块一项 {任务, 入参, 逻辑, 格式}，给 并行派任务 用（deep 核查：读代码的子任务）
  read_file(...)  取文件：需求文件 / 项目目录内文件 / v3 自带提示词（@名字）→ 文本
  merge(...)      存问题清单：把各路结果（程序 / 回归 / 冒烟 / 规划 / 模块 / 疑点）并成一份、去重、丢掉不合格项

模型子任务的回复固定是 {result, status, reason}（见 tools/dsl_task.py），核查类的 result 是 {found: 是否, items: 列表}。
"""
import re
from pathlib import Path

from . import catalog as CAT
from . import contracts as VC
from . import issues as IS
from . import planning as PL
from . import regress as RG
from ..packs.dslproj import contract as C

PROMPTS = Path(__file__).parent / "prompts"
SEG = 400                       # 一段代码引用最多多少行（tools/dsl_task.MAX_LINES）
REQ_CAP = 14000
FORMAT = "found:是否,items:列表"
KEYS = ("issue", "modules", "basis", "type")

MODULE_TASK = (
    "核查模块 {m}：把约定和代码、需求对一遍，找出问题。只读不改。{known}"
    "已知问题（程序检查、回归、冒烟已经查出的）不用重复。")
MODULE_LOGIC = (
    "1. 逐个约定函数核对代码有没有按伪代码实现（分支、报错码、返回字段、写库）；\n"
    "2. 每个接口的路径、方法、参数、角色（公开 / 角色 / 认证）是否和约定、路由代码一致；\n"
    "3. 需求里和本模块相关的要点有没有做到；\n"
    "4. 每条问题写明依据（文件和行）与类型：code=代码和约定不一致、contract=约定有问题、req=需求没覆盖；\n"
    "5. 回复的 result 是 {found, items}：items 每项是对象 {issue, modules, basis, type}，modules 写模块名，"
    "type 只能是 code / contract / req；没有问题 found=否、items 为空数组；有问题 found=是、items 非空。")


def read_file(ctx, path):
    """→ (文本, 说明)。路径限需求文件、项目目录内；「@名字」读 v3/prompts/名字。读不到文本为空串，说明写原因。"""
    path = (path or "").strip()
    if not path:
        return "", "没给路径"
    if path.startswith("@"):
        f = (PROMPTS / path[1:]).resolve()
        if PROMPTS.resolve() not in f.parents or not f.is_file():
            return "", f"v3 自带提示词「{path[1:]}」不存在"
        return f.read_text(encoding="utf-8"), ""
    p = Path(path)
    root = Path(ctx.project).resolve()
    f = (p if p.is_absolute() else root / p).resolve()
    req = Path(ctx.req_path).resolve() if getattr(ctx, "req_path", None) else None
    if req is not None and f == req:
        pass
    elif root != f and root not in f.parents:
        return "", f"路径「{path}」不在需求文件或项目目录内"
    if not f.is_file():
        return "", f"文件「{path}」不存在"
    return f.read_text(encoding="utf-8", errors="replace"), ""


def split_sections(req_text):
    """需求按标题行（# 开头）拆成 [(标题, 全文)]；开头没有标题的部分标题为空。"""
    secs, cur, head = [], [], ""
    for line in (req_text or "").replace("\r\n", "\n").split("\n"):
        if re.match(r"^#{1,6}\s", line):
            if cur:
                secs.append((head, "\n".join(cur)))
            head, cur = line.strip(), [line]
        else:
            cur.append(line)
    if cur:
        secs.append((head, "\n".join(cur)))
    return secs


def relevant_req(req_text, module, desc, tables, task=""):
    """需求里和本模块相关的节：提到模块名、表名，或命中说明里的词（≥2 个）。一节都没命中给全文（截断）。"""
    words = {w for w in re.split(r"[\s，。、；：:,.;（）()「」/\-—]+", desc or "") if len(w) >= 2}
    picked = []
    for head, body in split_sections(req_text):
        hit = module in body or any(t in body for t in tables) or sum(1 for w in words if w in body) >= 2
        if hit:
            picked.append(body.strip())
    text = "\n\n".join(picked) if picked else (req_text or "").strip()
    if task.strip():
        text += f"\n\n（本轮任务：{task.strip()}）"
    return text[:REQ_CAP] + ("\n……（需求太长，已截断）" if len(text) > REQ_CAP else "")


def _modules_of(items_or_dict):
    """已知问题的各种形态（核查类动词的返回 dict / 条目列表 / 它们的集合 / 文本）→ 条目列表。"""
    out = []
    if isinstance(items_or_dict, dict):
        if isinstance(items_or_dict.get("items"), list):
            out += [i for i in items_or_dict["items"] if isinstance(i, dict)]
        else:
            for v in items_or_dict.values():
                out += _modules_of(v)
    elif isinstance(items_or_dict, list):
        for v in items_or_dict:
            out += _modules_of(v) if not isinstance(v, dict) or "items" in v else [v]
    return out


def known_text(known, module):
    """已知问题里和本模块有关（涉及模块含它，或没写模块）的条目 → 文本。"""
    rows = []
    for it in _modules_of(known):
        mods = [x for x in re.split(r"[,，、\s]+", str(it.get("modules") or "")) if x]
        if mods and module not in mods:
            continue
        rows.append(f"- {str(it.get('issue') or '')[:400]}（{it.get('basis') or ''}）")
    return "\n".join(rows)[:3000]


def _code_refs(project, module, mods):
    """模块代码文件 → {小标题: "文件:起-止"}；超过 SEG 行的分段。"""
    refs = {}
    for rel in RG.code_files(project, module, mods):
        n = len((Path(project) / rel).read_text(encoding="utf-8", errors="replace").splitlines()) or 1
        segs = [(a, min(a + SEG - 1, n)) for a in range(1, n + 1, SEG)]
        for i, (a, b) in enumerate(segs, 1):
            refs[rel if len(segs) == 1 else f"{rel}（第 {i}/{len(segs)} 段）"] = f"{rel}:{a}-{b}"
    return refs


def tasks(ctx, mods, task="", known=None):
    """模块名列表 → 并行派任务用的列表（每个模块一项，顺序同 mods）。"""
    project = Path(ctx.project)
    top_desc = {}
    top_f = ctx.top_path()
    if top_f.is_file():
        top_desc = CAT.top_comments(top_f.read_text(encoding="utf-8"))
    all_mods = list(mods)
    try:
        all_mods = [m["名"] for m in PL.current_top(ctx)["模块"]]
    except ValueError:
        pass
    jobs = []
    for m in mods:
        cf = VC.path_of(project, m)
        ctext, cobj = "", None
        if cf.is_file():
            raw = cf.read_text(encoding="utf-8")
            ctext = PL.without_cases(raw)
            cobj, probs = C.parse(raw)
            if probs:
                cobj = None
        ups, tables = [], []
        if cobj:
            tables = [t["名"] for t in cobj["表"]]
            for d in cobj["依赖"]:
                df = VC.path_of(project, d)
                if df.is_file():
                    dc, p2 = C.parse(df.read_text(encoding="utf-8"))
                    if not p2:
                        ups.append(f"【{d}】\n{C.public_heads(dc)}")
        inputs = {
            "需求相关节": relevant_req(ctx.req, m, top_desc.get(m, ""), tables, task),
            "约定全文（去用例）": ctext or "（还没有约定文件）",
            "上游公开函数头": "\n\n".join(ups) or "（没有上游依赖）",
            **_code_refs(project, m, all_mods),
        }
        kt = known_text(known, m)
        desc = MODULE_TASK.format(m=m, known=(f"\n本模块的已知问题：\n{kt}\n" if kt else "\n"))
        jobs.append({"任务": desc, "入参": inputs, "逻辑": MODULE_LOGIC, "格式": FORMAT})
    return jobs


# ------------------------------------------------------------------ 存问题清单

def _clean_one(it):
    """一条结果项 → (规整后的条目, 问题文本)；合格问题文本为空。"""
    if not isinstance(it, dict):
        return None, "不是对象"
    miss = [k for k in KEYS if k not in it or it[k] is None]
    if miss:
        return None, "缺字段 " + "、".join(miss)
    mods = it["modules"]
    if isinstance(mods, list):
        mods = "、".join(str(x) for x in mods)
    out = {"issue": str(it["issue"]).strip(), "modules": str(mods).strip(),
           "basis": str(it["basis"]).strip(), "type": str(it["type"]).strip()}
    if not out["issue"] or not out["basis"] or not out["modules"]:
        return None, "issue / modules / basis 不能为空"
    if out["type"] not in IS.ISSUE_TYPES:
        return None, f"type「{out['type']}」不在 {'/'.join(IS.ISSUE_TYPES)} 之内"
    return out, ""


def _as_list(v):
    return v if isinstance(v, list) else ([] if v in (None, "") else [v])


def _program_items(v, label, kept, dropped):
    """程序类结果（{count, items, …} 或条目列表）：逐项规整。"""
    if v in (None, ""):
        return
    items = v.get("items") if isinstance(v, dict) else v
    for it in _as_list(items):
        out, why = _clean_one(it)
        if out:
            kept.append(out)
        else:
            dropped.append({"source": label, "reason": why, "raw": it})


def _model_items(r, label, module, kept, dropped, unchecked):
    """子任务的返回 {result, status, reason}：status 非成功 → unchecked；否则 found / items 一致才收。"""
    if not isinstance(r, dict) or r.get("status") != "成功":
        r = r if isinstance(r, dict) else {}
        reason = str(r.get("reason") or r.get("status") or "没有返回")
        if r.get("问题"):                       # 回复格式不合格时 派任务 把具体哪儿不对放在「问题」里
            reason += f"（{r['问题']}）"
        unchecked.append({"module": module, "reason": reason[:500]})
        return
    res = r.get("result")
    if not isinstance(res, dict) or "found" not in res or not isinstance(res.get("items"), list):
        dropped.append({"source": label, "reason": "result 缺 found / items", "raw": res})
        return
    found = res["found"] in (True, "是", "true", "True")
    if found != bool(res["items"]):
        dropped.append({"source": label, "reason": f"found={'是' if found else '否'} 但 items {'非空' if res['items'] else '为空'}，前后矛盾",
                        "raw": res})
        return
    for it in res["items"]:
        out, why = _clean_one(it)
        if out:
            kept.append(out)
        else:
            dropped.append({"source": label, "reason": why, "raw": it})


def merge(程序=None, 回归=None, 冒烟=None, 规划=None, 模块=None, 疑点=None, 模块名=""):
    """→ (items, unchecked, dropped)。按（issue, modules）去重，顺序：程序、回归、冒烟、规划、模块、疑点。"""
    kept, dropped, unchecked = [], [], []
    for v, label in ((程序, "程序"), (回归, "回归"), (冒烟, "冒烟")):
        _program_items(v, label, kept, dropped)
    if 规划 not in (None, ""):
        _model_items(规划, "规划", "规划层", kept, dropped, unchecked)
    if 模块 not in (None, ""):
        names = [x for x in re.split(r"[,，、\s]+", 模块名 if isinstance(模块名, str) else ",".join(map(str, 模块名))) if x]
        for i, r in enumerate(_as_list(模块)):
            name = names[i] if i < len(names) else f"#{i + 1}"
            _model_items(r, f"模块 {name}", name, kept, dropped, unchecked)
    _program_items(疑点, "疑点", kept, dropped)
    seen, items = set(), []
    for it in kept:
        key = (it["issue"], it["modules"])
        if key not in seen:
            seen.add(key)
            items.append(it)
    return items, unchecked, dropped
