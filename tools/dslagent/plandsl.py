"""modular 的规划文件：用 DSL 写（plan/top.zs 顶层规划、plan/layers.zs 层次×模块），程序解析成 validate_top / validate_split 吃的 dict。

语法（中文关键字、一行一件事、块用「结束」收尾、整行 # 开头是注释；解析报错带行号与原行）：

plan/top.zs
    项目 <目标一句话>
      使用者 <角色…> 单人|多人          # 角色是英文 snake；无登录就只写 单人 / 多人
      横切 账号 <账号与权限一句话>
      横切 调模型 <包> [处…]           # 可写多行
      横切 后台任务 <一句话>            # 可写多行
      横切 导入 <内容数据导入一句话>
      约束 <全局约束一句话>             # 可写多行
    结束
    模块 <名> <说明…> [依赖 <模块…>]
    共用流程 <流程名> 归 <模块> 用于 <模块…>
    主流程 <名> <角色|-> 经过 <模块…>
      步骤 <步骤…>                     # 一个词一步，可写多行
    结束
    构建顺序 <模块…>

plan/layers.zs
    模板 <full|private|…>
    角色 <角色…>                       # 可省
    关闭注册 是                        # 可省
    层 <层名> <职责…>                  # 可写多行
    约束 <全局约束>                    # 可写多行
    模块 <名>
      规则 <一条规则，一行一条>
      数据 <实体…>
      流程 <名> [用于 <接口文件…>] [调流程 <流程…>] [作用 <一句话，写在最后>]
      接口 <文件> [作用…]
      界面 <名> [作用…]
      能力 <包…>
      缺口 <sql|流程|待补> [动词 <动词…>] 事 <一句话，写在最后>
    结束
"""
import re

TOP_HEAD = "项目"
PEOPLE = ("单人", "多人")


class PlanError(Exception):
    """规划文件解析错误；str(e) 已带 文件名 第N行「原行」。"""


def _err(fname, ln, raw, msg):
    return PlanError(f"{fname} 第 {ln} 行「{raw.strip()}」：{msg}")


def _lines(text):
    """[(行号, 原行, 去掉两端空白的行)]，跳过空行和整行 # 注释。"""
    out = []
    for i, raw in enumerate(str(text or "").replace("\r\n", "\n").split("\n"), 1):
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        out.append((i, raw, s))
    return out


def unfence(text):
    t = str(text or "").strip()
    m = re.match(r"^```[^\n]*\n(.*?)\n?```\s*$", t, re.S)
    return m.group(1) if m else t


def _split(s):
    """'关键字 剩余' → (关键字, 剩余)。"""
    p = s.split(None, 1)
    return p[0], (p[1].strip() if len(p) > 1 else "")


def _segments(tokens, markers):
    """tokens 按 markers（关键字集合）切段：返回 (头部 tokens, {关键字: [tokens]})。同一关键字出现两次返回 None 键 '重复'。"""
    head, segs, cur = [], {}, None
    for t in tokens:
        if t in markers:
            if t in segs:
                segs["重复"] = [t]
            cur = t
            segs.setdefault(t, [])
        elif cur is None:
            head.append(t)
        else:
            segs[cur].append(t)
    return head, segs


# ================================================================== 顶层规划

def parse_top(text, fname="plan/top.zs"):
    """DSL 文本 → validate_top 吃的 dict（原样，不校验语义）；语法错抛 PlanError。"""
    ls = _lines(unfence(text))
    obj = {"目标": "", "使用者": None, "主流程": [], "模块": [], "共用流程": [], "横切": {}, "构建顺序": None}
    cut = {"调模型": [], "后台任务": [], "全局约束": []}
    i, seen_proj, seen = 0, False, set()
    while i < len(ls):
        ln, raw, s = ls[i]
        kw, rest = _split(s)
        if kw == TOP_HEAD:
            if seen_proj:
                raise _err(fname, ln, raw, "「项目」块只能有一个")
            seen_proj = True
            if not rest:
                raise _err(fname, ln, raw, "项目 后面要写目标一句话")
            obj["目标"] = rest
            j, closed = i + 1, False
            while j < len(ls):
                l2, r2, s2 = ls[j]
                k2, v2 = _split(s2)
                if k2 == "结束":
                    closed = True
                    break
                if k2 == "使用者":
                    toks = v2.split()
                    if not toks or toks[-1] not in PEOPLE:
                        raise _err(fname, l2, r2, "使用者 的最后一项要是 单人 或 多人（前面是角色名）")
                    if obj["使用者"] is not None:
                        raise _err(fname, l2, r2, "使用者 只能写一行")
                    obj["使用者"] = {"角色": toks[:-1], "人数": toks[-1]}
                elif k2 == "横切":
                    sub, val = _split(v2)
                    if sub == "账号":
                        if not val:
                            raise _err(fname, l2, r2, "横切 账号 后面要写账号与权限一句话（无登录写「无账号」）")
                        cut["账号与权限"] = val
                    elif sub == "调模型":
                        pk, where = _split(val)
                        if not pk:
                            raise _err(fname, l2, r2, "横切 调模型 后面要写包名，可再跟用在哪")
                        cut["调模型"].append({"处": where, "包": pk})
                    elif sub == "后台任务":
                        if not val:
                            raise _err(fname, l2, r2, "横切 后台任务 后面要写一句话")
                        cut["后台任务"].append(val)
                    elif sub == "导入":
                        cut["内容数据导入"] = val
                    else:
                        raise _err(fname, l2, r2, "横切 后面只能是 账号 / 调模型 / 后台任务 / 导入")
                elif k2 == "约束":
                    if not v2:
                        raise _err(fname, l2, r2, "约束 后面要写一句话")
                    cut["全局约束"].append(v2)
                else:
                    raise _err(fname, l2, r2, "项目块里只能写 使用者 / 横切 / 约束，块用「结束」收尾")
                j += 1
            if not closed:
                raise _err(fname, ln, raw, "项目块没有「结束」")
            i = j + 1
            continue
        if kw == "模块":
            toks = rest.split()
            if not toks:
                raise _err(fname, ln, raw, "模块 后面要写 名 说明 [依赖 …]")
            head, segs = _segments(toks[1:], {"依赖"})
            desc = " ".join(head)
            obj["模块"].append({"名": toks[0], "说明": "" if desc == "-" else desc, "依赖": segs.get("依赖", [])})
        elif kw == "共用流程":
            toks = rest.split()
            if not toks:
                raise _err(fname, ln, raw, "共用流程 后面要写 流程名 归 模块 用于 模块…")
            head, segs = _segments(toks[1:], {"归", "用于"})
            if head or len(segs.get("归", [])) != 1 or "重复" in segs:
                raise _err(fname, ln, raw, "共用流程 写法：共用流程 <流程名> 归 <一个模块> 用于 <模块…>")
            obj["共用流程"].append({"流程名": toks[0], "归属模块": segs["归"][0], "被用于": segs.get("用于", [])})
        elif kw == "主流程":
            toks = rest.split()
            if not toks:
                raise _err(fname, ln, raw, "主流程 后面要写 名 角色|- 经过 模块…")
            head, segs = _segments(toks[1:], {"经过"})
            if len(head) != 1 or "重复" in segs:
                raise _err(fname, ln, raw, "主流程 写法：主流程 <名> <角色|-> 经过 <模块…>（不限角色写 -）")
            f = {"名": toks[0], "角色": "" if head[0] == "-" else head[0], "步骤": [], "经过模块": segs.get("经过", [])}
            j, closed = i + 1, False
            while j < len(ls):
                l2, r2, s2 = ls[j]
                k2, v2 = _split(s2)
                if k2 == "结束":
                    closed = True
                    break
                if k2 != "步骤":
                    raise _err(fname, l2, r2, "主流程块里只能写 步骤，块用「结束」收尾")
                f["步骤"] += v2.split()
                j += 1
            if not closed:
                raise _err(fname, ln, raw, "主流程块没有「结束」")
            obj["主流程"].append(f)
            i = j + 1
            continue
        elif kw == "构建顺序":
            if "构建顺序" in seen:
                raise _err(fname, ln, raw, "构建顺序 只能写一行")
            obj["构建顺序"] = rest.split()
        elif kw == "结束":
            raise _err(fname, ln, raw, "多余的「结束」")
        else:
            raise _err(fname, ln, raw, "不认识的关键字；可用：项目 / 模块 / 共用流程 / 主流程 / 构建顺序")
        seen.add(kw)
        i += 1
    if not seen_proj:
        raise PlanError(f"{fname}：缺少「项目 … 结束」块")
    if obj["使用者"] is None:
        raise PlanError(f"{fname}：项目块里缺少「使用者 …」一行")
    if obj["构建顺序"] is None:
        raise PlanError(f"{fname}：缺少「构建顺序 …」一行")
    obj["横切"] = cut
    for k in ("账号与权限", "内容数据导入"):
        cut.setdefault(k, "")
    return obj


def _w(s):
    """单个词：内部空白换成 -（DSL 里一个词不能含空格）。"""
    return re.sub(r"\s+", "-", str(s).strip()) or "-"


def render_top(obj):
    """顶层规划 dict → plan/top.zs 文本（宽松：缺键当空；parse_top(render_top(x)) 与 x 等价）。"""
    u = obj.get("使用者") if isinstance(obj.get("使用者"), dict) else {}
    c = obj.get("横切") if isinstance(obj.get("横切"), dict) else {}
    L = [f"项目 {str(obj.get('目标') or '').strip() or '（未写目标）'}"]
    L.append("  使用者 " + " ".join([*map(str, u.get("角色") or []), str(u.get("人数") or "多人")]))
    if c.get("账号与权限"):
        L.append(f"  横切 账号 {c['账号与权限']}")
    for x in c.get("调模型") or []:
        if isinstance(x, dict):
            L.append(f"  横切 调模型 {x.get('包') or '-'}" + (f" {x['处']}" if x.get("处") else ""))
    L += [f"  横切 后台任务 {t}" for t in c.get("后台任务") or []]
    if c.get("内容数据导入"):
        L.append(f"  横切 导入 {c['内容数据导入']}")
    L += [f"  约束 {t}" for t in c.get("全局约束") or []]
    L.append("结束")
    for m in obj.get("模块") or []:
        L.append(f"模块 {m.get('名')} {' '.join(str(m.get('说明') or '-').split())}" + (f" 依赖 {' '.join(m['依赖'])}" if m.get("依赖") else ""))
    for s in obj.get("共用流程") or []:
        L.append(f"共用流程 {s.get('流程名')} 归 {s.get('归属模块')} 用于 {' '.join(s.get('被用于') or [])}")
    for f in obj.get("主流程") or []:
        L.append(f"主流程 {_w(f.get('名'))} {f.get('角色') or '-'} 经过 {' '.join(f.get('经过模块') or [])}")
        if f.get("步骤"):
            L.append("  步骤 " + " ".join(_w(x) for x in f["步骤"]))
        L.append("结束")
    L.append("构建顺序 " + " ".join(obj.get("构建顺序") or []))
    return "\n".join(L) + "\n"


# ================================================================== 层次×模块

def parse_layers(text, fname="plan/layers.zs"):
    """DSL 文本 → validate_split 吃的 dict。"""
    ls = _lines(unfence(text))
    obj = {"模板": "", "角色": [], "层": {}, "全局约束": [], "模块": []}
    i = 0
    while i < len(ls):
        ln, raw, s = ls[i]
        kw, rest = _split(s)
        if kw == "模板":
            if not rest or len(rest.split()) != 1:
                raise _err(fname, ln, raw, "模板 后面写一个模板名")
            obj["模板"] = rest
        elif kw == "角色":
            obj["角色"] += rest.split()
        elif kw == "关闭注册":
            obj["关闭注册"] = rest or "是"
        elif kw == "层":
            n, d = _split(rest)
            if not n:
                raise _err(fname, ln, raw, "层 后面要写 层名 职责")
            obj["层"][n] = d
        elif kw == "约束":
            if not rest:
                raise _err(fname, ln, raw, "约束 后面要写一句话")
            obj["全局约束"].append(rest)
        elif kw == "模块":
            if len(rest.split()) != 1:
                raise _err(fname, ln, raw, "模块 后面只写模块名（内容写在下面，块用「结束」收尾）")
            m = {"名": rest, "规则": [], "数据": [], "流程": [], "接口": [], "界面": [], "能力": [], "缺口": []}
            j, closed = i + 1, False
            while j < len(ls):
                l2, r2, s2 = ls[j]
                k2, v2 = _split(s2)
                if k2 == "结束":
                    closed = True
                    break
                if k2 == "规则":
                    if not v2:
                        raise _err(fname, l2, r2, "规则 后面要写一条规则")
                    m["规则"].append(v2)
                elif k2 == "数据":
                    m["数据"] += v2.split()
                elif k2 == "能力":
                    m["能力"] += v2.split()
                elif k2 == "流程":
                    toks = v2.split()
                    if not toks:
                        raise _err(fname, l2, r2, "流程 后面要写 名 [用于 …] [调流程 …] [作用 …]")
                    head, segs = _segments(toks[1:], {"用于", "调流程", "作用"}) if "作用" not in toks[1:] else _flow_segs(toks[1:])
                    if head or "重复" in segs:
                        raise _err(fname, l2, r2, "流程 写法：流程 <名> 用于 <接口文件…> 调流程 <流程…> 作用 <一句话，写在最后>")
                    m["流程"].append({"名": toks[0], "作用": " ".join(segs.get("作用", [])), "用于": segs.get("用于", []), "调流程": segs.get("调流程", [])})
                elif k2 in ("接口", "界面"):
                    n, d = _split(v2)
                    if not n:
                        raise _err(fname, l2, r2, f"{k2} 后面要写名字 [作用]")
                    m[k2].append({"文件" if k2 == "接口" else "名": n, "作用": d})
                elif k2 == "缺口":
                    toks = v2.split()
                    head, segs = _gap_segs(toks)
                    if len(head) != 1 or "重复" in segs or not segs.get("事"):
                        raise _err(fname, l2, r2, "缺口 写法：缺口 <sql|流程|待补> [动词 <动词…>] 事 <一句话，写在最后>")
                    m["缺口"].append({"事": " ".join(segs["事"]), "办法": head[0], "用动词": segs.get("动词", [])})
                else:
                    raise _err(fname, l2, r2, "模块块里只能写 规则 / 数据 / 流程 / 接口 / 界面 / 能力 / 缺口，块用「结束」收尾")
                j += 1
            if not closed:
                raise _err(fname, ln, raw, f"模块「{rest}」块没有「结束」")
            obj["模块"].append(m)
            i = j + 1
            continue
        elif kw == "结束":
            raise _err(fname, ln, raw, "多余的「结束」")
        else:
            raise _err(fname, ln, raw, "不认识的关键字；可用：模板 / 角色 / 关闭注册 / 层 / 约束 / 模块")
        i += 1
    if not obj["模板"]:
        raise PlanError(f"{fname}：缺少「模板 …」一行")
    return obj


def _flow_segs(tokens):
    """流程行：作用 之后全是作用文字（可含「用于」之类的词）。"""
    k = tokens.index("作用")
    head, segs = _segments(tokens[:k], {"用于", "调流程"})
    segs["作用"] = tokens[k + 1:]
    return head, segs


def _gap_segs(tokens):
    """缺口行：事 之后全是事的文字。"""
    if "事" not in tokens:
        return tokens, {}
    k = tokens.index("事")
    head, segs = _segments(tokens[:k], {"动词"})
    segs["事"] = tokens[k + 1:]
    return head, segs


def render_layers(obj):
    """层次×模块 dict（原始形或 validate_split 规范化后的形：模块可以是 {名: 项} 字典）→ plan/layers.zs 文本。"""
    mods = obj.get("模块") or []
    if isinstance(mods, dict):
        mods = list(mods.values())
    lay = obj.get("层")
    if isinstance(lay, list):
        desc = obj.get("层说明") if isinstance(obj.get("层说明"), dict) else {}
        lay = {str(k): desc.get(k, "") for k in lay}
    L = [f"模板 {obj.get('模板')}"]
    if obj.get("角色"):
        L.append("角色 " + " ".join(obj["角色"]))
    if str(obj.get("关闭注册") or "").strip() in ("是", "true", "True", "1"):
        L.append("关闭注册 是")
    for k, d in (lay if isinstance(lay, dict) else {}).items():
        L.append(f"层 {k}" + (f" {d}" if d else ""))
    L += [f"约束 {t}" for t in obj.get("全局约束") or []]
    for m in mods:
        if not isinstance(m, dict):
            continue
        L.append(f"模块 {m.get('名')}")
        L += [f"  规则 {t}" for t in m.get("规则") or []]
        if m.get("数据"):
            L.append("  数据 " + " ".join(m["数据"]))
        for f in m.get("流程") or []:
            L.append(f"  流程 {f.get('名')}" + (f" 用于 {' '.join(f['用于'])}" if f.get("用于") else "") + (f" 调流程 {' '.join(f['调流程'])}" if f.get("调流程") else "")
                     + (f" 作用 {f['作用']}" if f.get("作用") else ""))
        for f in m.get("接口") or []:
            f = f if isinstance(f, dict) else {"文件": f}
            L.append(f"  接口 {f.get('文件')}" + (f" {f['作用']}" if f.get("作用") else ""))
        for f in m.get("界面") or []:
            f = f if isinstance(f, dict) else {"名": f}
            L.append(f"  界面 {f.get('名')}" + (f" {f['作用']}" if f.get("作用") else ""))
        if m.get("能力"):
            L.append("  能力 " + " ".join(m["能力"]))
        for g in m.get("缺口") or []:
            L.append(f"  缺口 {g.get('办法')}" + (f" 动词 {' '.join(g['用动词'])}" if g.get("用动词") else "") + f" 事 {g.get('事')}")
        L.append("结束")
    return "\n".join(L) + "\n"
