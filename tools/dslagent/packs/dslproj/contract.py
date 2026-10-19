"""dslproj 的约定文件 contracts/<模块>.md：固定可解析的格式（写法见 packs/README.md「dslproj」一节）。

    模块 progress
    依赖 graph                              # 没有依赖写「依赖 无」（或不写这行）

    ## 表                                   # 本模块拥有的表（只记表名和字段，实体文件由模型写，比对只看表是否建了）
    表 answer
      id 整数 主键
      learner 文本 学习者

    ## 函数
    公开 函数 记作答 learner point_code correct pass_line?    # 「公开」可省（私有）；入参末尾 ? = 可选
      返回 {score, mastered}
      报错 404 没有这个知识点                  # 可多条，码必须 4xx
      伪代码 调用 graph.取知识点 code=point_code，取不到 报错 404       # 一行一条；跨模块调用写 调用 模块.函数

    ## 接口
    POST /progress/answer -> 记作答           # 方法 路径 -> 本模块的公开函数（一个接口只调这一个函数）

    ## 用例                                  # 每个公开函数至少一条
    用例 记作答_全对
      先 数据 point code=P1 title=一次函数          # 直接往表里插一行（造前置数据，表可以是上游模块的）
      先 调用 graph.加边 src=P1 dst=P2             # 或调公开函数造前置（可多条，按顺序）
      调用 记作答 learner=u1 point_code=P1 correct=1   # 恰好一条，本模块的公开函数；值里不能有空格，「空」= 空串
      得 score=100 mastered=1                   # 返回对象的字段（数字按数值比）；或「得 为空」「得 有返回」
      库 answer 共 1 行                          # 可多条：「库 表 共 N 行」「库 表 含 k=v …」「库 表 无 k=v …」
    用例 记作答_没有知识点
      调用 记作答 learner=u1 point_code=NOPE correct=1
      报错 404                                  # 期望业务错误码（和「得」二选一）

parse(text) -> (contract, 问题)；check(contract, name, upstream, all_modules) -> 问题；heads(contract) -> 函数头文本；hash_of(text)。
"""
import hashlib
import re

NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
PARAM_RE = re.compile(r"^[a-z_][a-z0-9_]*\??$")
IDENT = r"[A-Za-z0-9_一-鿿]+"
QCALL_RE = re.compile(rf"调用\s+({IDENT})\.({IDENT})")
METHODS = ("GET", "POST", "PUT", "DELETE")
SECTIONS = {"表": "表", "数据": "表", "函数": "函数", "接口": "接口", "用例": "用例"}


def normalize(text):
    return "\n".join(l.rstrip() for l in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")).strip() + "\n"


def hash_of(text):
    return hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()


def _strip_comment(s):
    i = s.find("#")
    while i >= 0:
        if i == 0 or s[i - 1] in " \t":
            return s[:i].rstrip()
        i = s.find("#", i + 1)
    return s.rstrip()


def _kv(text):
    out = {}
    for t in text.split():
        k, _, v = t.partition("=")
        if k:
            out[k] = v
    return out


def parse(text):
    """→ (contract, 问题)。contract = {模块, 依赖, 表, 函数, 接口, 用例}；各项带「行」。"""
    probs = []
    c = {"模块": None, "依赖": [], "表": [], "函数": [], "接口": [], "用例": []}
    sec, cur = None, None
    for no, raw in enumerate(text.replace("\r", "").splitlines(), 1):
        if raw.strip().startswith("```"):
            continue
        if raw.strip().startswith("##"):
            title = raw.strip().lstrip("#").strip()
            sec = SECTIONS.get(title)
            cur = None
            if sec is None:
                probs.append(f"第 {no} 行：不认识的小节「{title}」（只有 表 / 函数 / 接口 / 用例）")
            continue
        s = _strip_comment(raw).strip()
        if not s or s.startswith("#"):
            continue
        parts = s.split()
        h = parts[0]
        if sec is None:
            if h == "模块" and len(parts) == 2:
                c["模块"] = parts[1]
            elif h == "依赖":
                rest = [x for x in re.split(r"[\s,，、]+", " ".join(parts[1:])) if x and x != "无"]
                c["依赖"] = list(dict.fromkeys(rest))
            else:
                probs.append(f"第 {no} 行：小节之前只能写「模块 <名>」「依赖 …」，现在是「{s[:40]}」")
        elif sec == "表":
            if h == "表":
                if len(parts) != 2:
                    probs.append(f"第 {no} 行：表写法是「表 <表名>」")
                    continue
                cur = {"名": parts[1], "字段": [], "行": no}
                c["表"].append(cur)
            elif cur is None:
                probs.append(f"第 {no} 行：字段要写在「表 <表名>」下面")
            elif len(parts) < 2:
                probs.append(f"第 {no} 行：字段写法是「名 类型 [说明]」，现在是「{s}」")
            else:
                cur["字段"].append({"名": parts[0], "类型": parts[1], "说明": " ".join(parts[2:]), "行": no})
        elif sec == "函数":
            pub = h == "公开"
            if pub or h == "函数":
                fp = parts[1:] if pub else parts
                if len(fp) < 2 or fp[0] != "函数":
                    probs.append(f"第 {no} 行：函数写法是「[公开] 函数 <名> <入参…>」，现在是「{s}」")
                    cur = None
                    continue
                cur = {"名": fp[1], "公开": pub, "入参": fp[2:], "返回": "", "报错": [], "伪代码": [], "行": no}
                c["函数"].append(cur)
            elif cur is None:
                probs.append(f"第 {no} 行：「{h}」要写在某个函数下面")
            elif h == "返回":
                cur["返回"] = " ".join(parts[1:])
            elif h == "报错":
                m = re.match(r"^报错\s+(\d{3})\s*(.*)$", s)
                if not m:
                    probs.append(f"第 {no} 行：报错写法是「报错 <4xx码> <文字>」，现在是「{s}」")
                else:
                    cur["报错"].append({"码": int(m.group(1)), "文字": m.group(2), "行": no})
            elif h == "伪代码":
                cur["伪代码"].append({"文字": s[len("伪代码"):].strip(), "行": no})
            else:
                probs.append(f"第 {no} 行：函数下面只能写 返回 / 报错 / 伪代码，现在是「{h}」")
        elif sec == "接口":
            m = re.match(r"^(\w+)\s+(\S+)\s*(?:->|→)\s*(\S+)$", s)
            if not m:
                probs.append(f"第 {no} 行：接口写法是「<GET|POST|PUT|DELETE> <路径> -> <函数名>」，现在是「{s}」")
            else:
                c["接口"].append({"方法": m.group(1).upper(), "路径": m.group(2), "函数": m.group(3), "行": no})
        elif sec == "用例":
            _case_line(c, s, parts, h, no, probs)
            cur = c["用例"][-1] if c["用例"] else None
    if not c["模块"]:
        probs.append("缺「模块 <名>」")
    return c, probs


def _case_line(c, s, parts, h, no, probs):
    cases = c["用例"]
    if h == "用例":
        if len(parts) != 2:
            probs.append(f"第 {no} 行：用例写法是「用例 <名>」（名里不要空格）")
            return
        cases.append({"名": parts[1], "先": [], "调用": None, "得": None, "为空": False, "有返回": False, "报错": None, "库": [], "行": no})
        return
    if not cases:
        probs.append(f"第 {no} 行：「{h}」要写在某个「用例 <名>」下面")
        return
    u = cases[-1]
    if h == "先":
        m = re.match(rf"^先\s+数据\s+(\w+)((?:\s+\S+=\S*)+)$", s)
        if m:
            u["先"].append({"种类": "数据", "表": m.group(1), "值": _kv(m.group(2)), "行": no})
            return
        m = re.match(rf"^先\s+调用\s+({IDENT}\.{IDENT}|{IDENT})((?:\s+\S+=\S*)*)$", s)
        if m:
            u["先"].append({"种类": "调用", "目标": m.group(1), "参数": _kv(m.group(2)), "行": no})
            return
        probs.append(f"第 {no} 行：先 写法是「先 数据 表 k=v …」或「先 调用 [模块.]函数 k=v …」，现在是「{s}」")
    elif h == "调用":
        m = re.match(rf"^调用\s+({IDENT})((?:\s+\S+=\S*)*)$", s)
        if not m:
            probs.append(f"第 {no} 行：调用 写法是「调用 函数 k=v …」（本模块的公开函数），现在是「{s}」")
        elif u["调用"] is not None:
            probs.append(f"第 {no} 行：一个用例只写一条「调用」")
        else:
            u["调用"] = {"目标": m.group(1), "参数": _kv(m.group(2)), "行": no}
    elif h == "得":
        if parts[1:] == ["为空"]:
            u["为空"] = True
        elif parts[1:] == ["有返回"]:
            u["有返回"] = True
        else:
            bad = [t for t in parts[1:] if "=" not in t]
            if bad or len(parts) < 2:
                probs.append(f"第 {no} 行：得 写法是「得 k=v …」「得 为空」「得 有返回」（值里不能有空格），现在是「{s}」")
            else:
                u["得"] = {**(u["得"] or {}), **_kv(" ".join(parts[1:]))}
    elif h == "报错":
        m = re.match(r"^报错\s+(\d{3})\s*$", s)
        if not m:
            probs.append(f"第 {no} 行：用例里的报错写法是「报错 <码>」，现在是「{s}」")
        else:
            u["报错"] = int(m.group(1))
    elif h == "库":
        m = re.match(r"^库\s+(\w+)\s+共\s+(\d+)\s*行$", s)
        if m:
            u["库"].append({"表": m.group(1), "种类": "共", "行数": int(m.group(2)), "行": no})
            return
        m = re.match(r"^库\s+(\w+)\s+(含|无)((?:\s+\S+=\S*)+)$", s)
        if m:
            u["库"].append({"表": m.group(1), "种类": m.group(2), "值": _kv(m.group(3)), "行": no})
            return
        probs.append(f"第 {no} 行：库 写法是「库 表 共 N 行」「库 表 含 k=v …」「库 表 无 k=v …」，现在是「{s}」")
    else:
        probs.append(f"第 {no} 行：用例下面只能写 先 / 调用 / 得 / 报错 / 库，现在是「{h}」")


def params(fn):
    """入参 → (必填列表, 可选列表, 不合法的)。"""
    req, opt, bad = [], [], []
    for p in fn["入参"]:
        if not PARAM_RE.match(p):
            bad.append(p)
        elif p.endswith("?"):
            opt.append(p[:-1])
        else:
            req.append(p)
    return req, opt, bad


def check(c, name, upstream, all_modules):
    """约定检查。upstream：{上游模块名: 它的约定}（c['依赖'] 里的）；all_modules：项目全部模块名。返回问题列表。"""
    probs = []
    if c["模块"] != name:
        probs.append(f"「模块」写的是 {c['模块']!r}，应该是 {name}")
    for d in c["依赖"]:
        if d not in all_modules:
            probs.append(f"依赖的模块「{d}」在项目里没有约定文件（contracts/{d}.md）")
        elif d not in upstream:
            probs.append(f"依赖的模块「{d}」的约定解析不通过")
    tnames = set()
    for t in c["表"]:
        if not NAME_RE.match(t["名"]):
            probs.append(f"第 {t['行']} 行：表名「{t['名']}」要用英文 snake")
        if t["名"] in tnames:
            probs.append(f"第 {t['行']} 行：表「{t['名']}」重复")
        tnames.add(t["名"])
    fns = {}
    for f in c["函数"]:
        if f["名"] in fns:
            probs.append(f"第 {f['行']} 行：函数「{f['名']}」重复")
        fns[f["名"]] = f
        if params(f)[2]:
            probs.append(f"第 {f['行']} 行：函数「{f['名']}」的入参 {params(f)[2]} 不合法（英文 snake，可选的末尾加 ?）")
        for e in f["报错"]:
            if not 400 <= e["码"] <= 499:
                probs.append(f"第 {e['行']} 行：报错码 {e['码']} 不是 4xx")
    if not c["函数"]:
        probs.append("一个函数都没写（## 函数）")
    elif not any(f["公开"] for f in c["函数"]):
        probs.append("没有公开函数（至少一个要写成「公开 函数 …」）")

    def target(mod, fn, where, need_dep):
        if mod == name:
            if fn not in fns:
                probs.append(f"{where}：调用 {mod}.{fn}，但本模块没有函数「{fn}」")
            return
        if need_dep and mod not in c["依赖"]:
            probs.append(f"{where}：调用 {mod}.{fn}，但 {mod} 不在本模块的「依赖」里")
            return
        up = upstream.get(mod)
        if up is None:
            probs.append(f"{where}：调用 {mod}.{fn}，但没有 {mod} 的约定可查")
            return
        f = next((x for x in up["函数"] if x["名"] == fn), None)
        if f is None or not f["公开"]:
            probs.append(f"{where}：调用 {mod}.{fn}，但 {mod} 的约定里没有公开函数「{fn}」")

    for f in c["函数"]:
        for p in f["伪代码"]:
            for m in QCALL_RE.finditer(p["文字"]):
                target(m.group(1), m.group(2), f"第 {p['行']} 行（函数 {f['名']} 的伪代码）", True)
    seen = set()
    for i in c["接口"]:
        key = (i["方法"], i["路径"])
        if key in seen:
            probs.append(f"第 {i['行']} 行：接口 {i['方法']} {i['路径']} 重复")
        seen.add(key)
        if i["方法"] not in METHODS:
            probs.append(f"第 {i['行']} 行：方法「{i['方法']}」不在 {'/'.join(METHODS)} 里")
        if not i["路径"].startswith("/"):
            probs.append(f"第 {i['行']} 行：路径「{i['路径']}」要以 / 开头")
        f = fns.get(i["函数"])
        if f is None or not f["公开"]:
            probs.append(f"第 {i['行']} 行：接口 {i['路径']} 调的函数「{i['函数']}」不是本模块的公开函数")
    covered, names = set(), set()
    for u in c["用例"]:
        if u["名"] in names:
            probs.append(f"第 {u['行']} 行：用例「{u['名']}」重名")
        names.add(u["名"])
        if u["调用"] is None:
            probs.append(f"第 {u['行']} 行：用例「{u['名']}」缺「调用」")
            continue
        if u["得"] is None and not u["为空"] and not u["有返回"] and u["报错"] is None and not u["库"]:
            probs.append(f"第 {u['行']} 行：用例「{u['名']}」缺期望（得 … / 报错 <码> / 库 …）")
        if u["报错"] is not None and not 400 <= u["报错"] <= 499:
            probs.append(f"第 {u['行']} 行：用例「{u['名']}」的报错码 {u['报错']} 不是 4xx")
        for st in u["先"]:
            if st["种类"] == "调用":
                mod, _, fn = st["目标"].rpartition(".")
                target(mod or name, fn, f"第 {st['行']} 行（用例 {u['名']} 的 先）", False)
        fn = u["调用"]["目标"]
        f = fns.get(fn)
        if f is None or not f["公开"]:
            probs.append(f"第 {u['调用']['行']} 行：用例 {u['名']} 调的「{fn}」不是本模块的公开函数")
            continue
        covered.add(fn)
        req, opt, _ = params(f)
        given = set(u["调用"]["参数"])
        if set(req) - given:
            probs.append(f"第 {u['调用']['行']} 行：用例 {u['名']} 缺必填入参 {sorted(set(req) - given)}")
        if given - set(req) - set(opt):
            probs.append(f"第 {u['调用']['行']} 行：用例 {u['名']} 传了函数没有的入参 {sorted(given - set(req) - set(opt))}")
    for f in c["函数"]:
        if f["公开"] and f["名"] not in covered:
            probs.append(f"第 {f['行']} 行：公开函数「{f['名']}」一条验收用例都没有（## 用例）")
    return probs


def head_text(f):
    return f"{'公开 ' if f['公开'] else ''}函数 {f['名']} {' '.join(f['入参'])}".rstrip()


def public_heads(c):
    """上游模块给下游看的：公开函数头 + 返回 / 报错行。"""
    out = []
    for f in c["函数"]:
        if not f["公开"]:
            continue
        out.append(head_text(f))
        if f["返回"]:
            out.append(f"  返回 {f['返回']}")
        out += [f"  报错 {e['码']} {e['文字']}".rstrip() for e in f["报错"]]
    return "\n".join(out)
