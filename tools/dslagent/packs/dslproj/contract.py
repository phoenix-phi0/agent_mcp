"""dslproj 的约定文件 contracts/<模块>.md：固定可解析的格式（写法见 packs/README.md「dslproj」一节）。

    模块 progress
    依赖 graph                              # 没有依赖写「依赖 无」（或不写这行）

    ## 表                                   # 本模块拥有的表（只记表名和字段，实体文件由模型写，比对只看表是否建了）
    表 answer
      id 整数 主键
      learner 文本 学习者
    表 answer_log 学习记录                   # 拥有学习者真实记录的表要标「学习记录」（只加不重建，见 tools/migrate.py）

    ## 函数
    公开 函数 记作答 learner point_code correct pass_line?    # 「公开」可省（私有）；入参末尾 ? = 可选
      返回 {score, mastered}
      报错 404 没有这个知识点                  # 可多条，码必须 4xx
      伪代码 调用 graph.取知识点 code=point_code，取不到 报错 404       # 一行一条；跨模块调用写 调用 模块.函数

    ## 接口
    POST /progress/answer -> 记作答 角色 teacher   # 方法 路径 -> 本模块的公开函数（一个接口只调这一个函数） [上传 <字段> [类型 <逗号隔开的扩展名>] [上限 <大小>]] [公开|角色 <代号>]
    POST /textbook_import/task -> 新建导入 上传 file 类型 pdf,docx,md,txt 上限 20MB 角色 teacher   # 带「上传」的接口：
                                  # 函数要有入参「<字段>_path」收存盘后的路径（骨架自动生成「先 存文件」「失败回 400」）；
                                  # 入参里有 file_name/file_size/file_ext 才会额外取「上传信息」传给函数

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

    ## 脚本                                  # 可选：本模块的后台任务脚本（不写这段 = 没有脚本；声明了就必须有这个文件，也不许多出没声明的）
    scripts/jobs_run.zs 入参 job_id；出错 scripts/jobs_run_fail.zs；逐项处理任务   # 路径 scripts/<模块>_<名>.zs；「入参」可省；「出错」可省；最后一段是一句话作用
                                  # 业务函数里写库建好任务后（事务之外）`后台执行 scripts/jobs_run.zs job_id={id} on_error=scripts/jobs_run_fail.zs`

    ## 内容文件                              # 可选：本模块拥有的内容文件（源数据；库是它的投影）。不写这段 = 本模块不写内容文件
    content/notes2/cards.jsonl 字段 no,front,back；写：本模块函数 保存卡片,撤下全部；读：本模块函数 按文件重灌,读回卡片；教师保存的卡片，库按它重灌
                                  # 路径 content/<本模块>/<路径>.jsonl（或 .json），路径里可含 {变量}；「字段」可省；「写」「读」列本模块的函数名（没有就不写那一段）；最后一段是一句话作用
                                  # 函数里只能 写JSONL / 写JSON / 删文件 本模块的 content/<本模块>/ 下的路径，且要在这段里有声明

## 认证
认证声明由程序生成（骨架写在账号模块的 routes 顶部，只有一份），约定里**任何模块都不写 `认证 …` 行**（写了会被拒）。
负责账号的模块必须有公开函数 `核对身份 username`，返回 `{username, role}`，查不到返回空；带 `## 用例`（存在的用户返回 role、不存在返回空）。
接口行可以在 `-> 函数` 之后加 `公开` 或 `角色 <代号>`；需要当前用户的函数把 learner / current_user / auth_mode 写成普通入参。

parse(text) -> (contract, 问题)；check(contract, name, upstream, all_modules) -> 问题（含「多余依赖」：声明的依赖在伪代码「调用 X.f」
和用例「先 调用 X.f」里都没出现）；heads(contract) -> 函数头文本；hash_of(text)。
"""
import hashlib
import re

from tools import entity as E

NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
PARAM_RE = re.compile(r"^[a-z_][a-z0-9_]*\??$")
IDENT = r"[A-Za-z0-9_一-鿿]+"
QCALL_RE = re.compile(rf"调用\s+({IDENT})\.({IDENT})")
METHODS = ("GET", "POST", "PUT", "DELETE")
SECTIONS = {"表": "表", "数据": "表", "函数": "函数", "接口": "接口", "用例": "用例", "脚本": "脚本", "内容文件": "内容文件"}
SCRIPT_RE = re.compile(r"^scripts/([a-z][a-z0-9_]*)\.zs$")
CONTENT_RE = re.compile(r"^content/([a-z][a-z0-9_]*)/([A-Za-z0-9_{}./-]+\.(?:jsonl|json))$")   # 内容文件路径：content/<模块>/…（.jsonl / .json，可含 {变量}）

# 自由文本入参：这些名字（或 *_path / *_text 结尾）装的是标题、内容、原因、备注这类用户随意写的文本，
# 用例要覆盖「值带空格 / 换行也原样保存」（见 text_space_problems）。
FREE_TEXT_PARAMS = {
    "content", "title", "body", "text", "reason", "note", "notes", "desc", "description",
    "summary", "comment", "remark", "answer", "reply", "message", "question", "explanation",
    "detail", "details", "memo", "intro", "source", "license", "sentence", "keyword",
    "keywords", "tone", "recent_text", "must_info", "word_text",
}

# 认证由程序生成：账号模块 = 有公开函数「核对身份」的模块
ACCOUNT_FN = "核对身份"
ROLE_LABELS = {"teacher": "教师", "student": "学生"}
# 接口行：<方法> <路径> -> <函数>，后面跟任意顺序的标记：上传 <字段> [类型 <扩展名,…>] [上限 <大小>]、公开、角色 <代号>
IFACE_HEAD_RE = re.compile(r"^(\w+)\s+(\S+)\s*(?:->|→)\s*(\S+)(.*)$")
UPLOAD_SIZE_RE = re.compile(r"^\d+(?:\.\d+)?(?:B|KB|MB|GB)?$", re.I)


def account_modules(contracts):
    """{模块: 约定} → 有公开函数「核对身份」的模块名（按名字排序）。"""
    return sorted(m for m, c in contracts.items() if any(f["名"] == ACCOUNT_FN and f["公开"] for f in c["函数"]))


def role_codes(contracts):
    """全项目接口行里出现过的角色代号（按代号排序，保证生成和比对一致）。"""
    return sorted({i["角色"] for c in contracts.values() for i in c["接口"] if i["角色"]})


def auth_block(contracts):
    """→ (账号模块 或 None, 认证行列表)。有账号模块才有认证块；没有账号模块返回 (None, [])。"""
    owners = account_modules(contracts)
    if not owners:
        return None, []
    owner = owners[0]
    lines = ["认证 可选", f"认证 核对 {owner}.{ACCOUNT_FN}", "认证 身份 learner 默认 me"]
    for code in role_codes(contracts):
        lines.append(f"认证 角色 {code} {ROLE_LABELS.get(code, code)}")
    return owner, lines


def auth_problems(contracts):
    """跨模块的认证约定问题 → {模块: [问题]}：有接口标了角色但没有账号模块；多个模块都有「核对身份」。"""
    out = {}
    owners = account_modules(contracts)
    if not owners:
        for m, c in contracts.items():
            roles = sorted({i["角色"] for i in c["接口"] if i["角色"]})
            if roles:
                out.setdefault(m, []).append(
                    f"接口标了角色 {'、'.join(roles)}，但项目里没有任何模块提供公开函数「{ACCOUNT_FN} username」"
                    f"（认证由程序生成，要求负责账号的模块有这个函数，返回 {{username, role}}，查不到返回空）")
    elif len(owners) > 1:
        for m in owners:
            out.setdefault(m, []).append(
                f"模块 {'、'.join(owners)} 都有公开函数「{ACCOUNT_FN}」，只能由一个账号模块提供")
    return out


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


def _iface_tail(tail):
    """接口行 -> 函数 之后的标记（上传 / 类型 / 上限 / 公开 / 角色），顺序不限。
    → (上传dict|None, 公开bool, 角色str, 问题列表)。"""
    toks = tail.split()
    probs = []
    upload, public, role = None, False, ""
    i = 0
    while i < len(toks):
        t = toks[i]
        if t == "上传":
            if i + 1 >= len(toks):
                probs.append("「上传」后面要跟字段名")
                break
            upload = {"字段": toks[i + 1], "类型": "", "上限": ""}
            i += 2
        elif t == "类型":
            if upload is None or i + 1 >= len(toks):
                probs.append("「类型」要写在「上传 <字段>」后面，且后面要跟扩展名列表")
                i += 1
            else:
                upload["类型"] = toks[i + 1]
                i += 2
        elif t == "上限":
            if upload is None or i + 1 >= len(toks):
                probs.append("「上限」要写在「上传 <字段>」后面，且后面要跟大小")
                i += 1
            else:
                upload["上限"] = toks[i + 1]
                i += 2
        elif t == "公开":
            public = True
            i += 1
        elif t == "角色":
            if i + 1 >= len(toks):
                probs.append("「角色」后面要跟代号")
                break
            role = toks[i + 1]
            i += 2
        else:
            probs.append(f"不认识的接口标记「{t}」（只有 上传 <字段> [类型 …] [上限 …] / 公开 / 角色 <代号>）")
            i += 1
    if upload and upload["上限"] and not UPLOAD_SIZE_RE.match(upload["上限"]):
        probs.append(f"「上限 {upload['上限']}」写错了，写成 20MB / 500KB / 字节数")
    return upload, public, role, probs


def parse(text):
    """→ (contract, 问题)。contract = {模块, 依赖, 表, 函数, 接口, 用例, 脚本, 内容文件}；各项带「行」。"""
    probs = []
    c = {"模块": None, "依赖": [], "表": [], "函数": [], "接口": [], "用例": [], "脚本": [], "内容文件": []}
    sec, cur = None, None
    for no, raw in enumerate(text.replace("\r", "").splitlines(), 1):
        if raw.strip().startswith("```"):
            continue
        if raw.strip().startswith("##"):
            title = raw.strip().lstrip("#").strip()
            sec = SECTIONS.get(title)
            cur = None
            if sec is None:
                probs.append(f"第 {no} 行：不认识的小节「{title}」（只有 表 / 函数 / 接口 / 用例 / 脚本 / 内容文件）")
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
            elif h == "认证":
                probs.append(f"第 {no} 行：认证由程序生成，约定里不写（删掉这行）；账号模块提供公开函数「{ACCOUNT_FN} username」即可")
            else:
                probs.append(f"第 {no} 行：小节之前只能写「模块 <名>」「依赖 …」，现在是「{s[:40]}」")
        elif sec == "表":
            if h == "表":
                if len(parts) not in (2, 3) or (len(parts) == 3 and parts[2] != "学习记录"):
                    probs.append(f"第 {no} 行：表写法是「表 <表名> [学习记录]」，现在是「{s}」")
                    continue
                cur = {"名": parts[1], "字段": [], "学习记录": len(parts) == 3, "行": no}
                c["表"].append(cur)
            elif cur is None:
                probs.append(f"第 {no} 行：字段要写在「表 <表名>」下面")
            elif len(parts) < 2:
                probs.append(f"第 {no} 行：字段写法是「名 类型 [说明]」，现在是「{s}」")
            else:
                cur["字段"].append({"名": parts[0], "类型": parts[1], "说明": " ".join(parts[2:]), "行": no})
        elif sec == "函数":
            if h == "私有" and parts[1:2] == ["函数"]:
                probs.append(f"第 {no} 行：私有函数不用写「私有」前缀，直接写「函数 <名> …」就是私有的（只有公开函数才要写「公开 函数 …」），现在是「{s[:40]}」")
                cur = None
                continue
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
            m = IFACE_HEAD_RE.match(s)
            if not m:
                probs.append(f"第 {no} 行：接口写法是「<GET|POST|PUT|DELETE> <路径> -> <函数名> [上传 <字段> [类型 …] [上限 …]] [公开|角色 <代号>]」，现在是「{s}」")
            else:
                method, path, fn, tail = m.groups()
                upload, pub, role, tail_probs = _iface_tail(tail.strip())
                probs += [f"第 {no} 行：{p}" for p in tail_probs]
                if pub and role:
                    probs.append(f"第 {no} 行：接口「{path}」不能同时写「公开」和「角色」")
                c["接口"].append({"方法": method.upper(), "路径": path, "函数": fn, "公开": bool(pub), "角色": role or "",
                                  "上传": upload, "行": no})
        elif sec == "用例":
            _case_line(c, s, parts, h, no, probs)
            cur = c["用例"][-1] if c["用例"] else None
        elif sec == "脚本":
            _script_line(c, s, no, probs)
        elif sec == "内容文件":
            _content_line(c, s, no, probs)
    if not c["模块"]:
        probs.append("缺「模块 <名>」")
    return c, probs


def _script_line(c, s, no, probs):
    """## 脚本 的一行：scripts/<模块>_<名>.zs [入参 a,b]；[出错 scripts/<模块>_<名>_fail.zs]；<一句话作用>（分号 ；或 ; 隔开，出错可省）。"""
    segs = [x.strip() for x in re.split(r"[；;]", s)]
    toks = segs[0].split()
    if not toks or not SCRIPT_RE.match(toks[0]):
        probs.append(f"第 {no} 行：脚本写法是「scripts/<模块>_<名>.zs [入参 a,b]；[出错 scripts/<模块>_<名>_fail.zs]；一句话作用」，现在是「{s[:60]}」")
        return
    args = []
    if toks[1:2] == ["入参"]:
        args = [x for x in re.split(r"[\s,，、]+", " ".join(toks[2:])) if x]
    elif toks[1:]:
        probs.append(f"第 {no} 行：脚本路径后面只能写「入参 a,b」，现在是「{' '.join(toks[1:])[:40]}」")
    bad = [a for a in args if not NAME_RE.match(a)]
    if bad:
        probs.append(f"第 {no} 行：脚本入参 {bad} 不合法（英文 snake）")
    fail, note = "", []
    for seg in segs[1:]:
        m = re.match(r"^出错\s+(\S+)$", seg)
        if m:
            if fail:
                probs.append(f"第 {no} 行：「出错」只能写一次")
            fail = m.group(1)
            if not SCRIPT_RE.match(fail):
                probs.append(f"第 {no} 行：出错脚本「{fail}」写法是 scripts/<模块>_<名>.zs")
        elif seg:
            note.append(seg)
    c["脚本"].append({"路径": toks[0], "入参": args, "出错": fail, "作用": "；".join(note), "行": no})


def _content_line(c, s, no, probs):
    """## 内容文件 的一行：content/<模块>/<路径>.jsonl [字段 a,b,c]；[写：本模块函数 X,Y]；[读：本模块函数 Z]；<一句话作用>（分号 ；或 ; 隔开）。"""
    segs = [x.strip() for x in re.split(r"[；;]", s)]
    toks = segs[0].split()
    if not toks or not toks[0].startswith("content/"):
        probs.append(f"第 {no} 行：内容文件写法是「content/<模块>/<路径>.jsonl [字段 a,b,c]；写：本模块函数 X,Y；读：本模块函数 Z；一句话作用」，现在是「{s[:60]}」")
        return
    fields = []
    if toks[1:2] == ["字段"]:
        fields = [x for x in re.split(r"[\s,，、]+", " ".join(toks[2:])) if x]
    elif toks[1:]:
        probs.append(f"第 {no} 行：内容文件路径后面只能写「字段 a,b,c」，现在是「{' '.join(toks[1:])[:40]}」")
    bad = [a for a in fields if not NAME_RE.match(a)]
    if bad:
        probs.append(f"第 {no} 行：内容文件字段 {bad} 不合法（英文 snake）")
    writers, readers, note = [], [], []
    for seg in segs[1:]:
        m = re.match(r"^(写|读)\s*[:：]\s*(?:本模块函数\s*)?(.*)$", seg)
        if m:
            names = [x for x in re.split(r"[\s,，、]+", m.group(2)) if x and x != "无"]
            (writers if m.group(1) == "写" else readers).extend(names)
        elif seg:
            note.append(seg)
    c["内容文件"].append({"路径": toks[0], "字段": fields, "写": writers, "读": readers, "作用": "；".join(note), "行": no})


def declared_content(c):
    """约定里声明的内容文件路径（保序）。"""
    return [x["路径"] for x in c.get("内容文件", [])]


def unique_decls(c):
    """约定「## 表」里确定性可识别的唯一声明 → {"单列": [(表, 字段, 行)], "多列": [(表, [字段…], 行)]}。

    约定格式里「唯一」没有专门的旗标写法，历来写在字段说明文字里。这里只认 tools/entity.py
    text_declares_unique / unique_columns 的四种明确写法，其余位置的「唯一」（「唯一标识」「唯一的实现」）
    不认、不模糊匹配：比对约定拿它和实体旗标对账，宁可漏认也不误报。

      1. 「唯一」自成一词：        code 文本 唯一 知识点编号
      2. 紧跟逗号、后面不再接字：  username 文本 用户名，唯一 / code 文本 系列编号，唯一（默认系列编号为 hanabira）
      3. 括号里只有「唯一」：      username 文本 用户名（唯一）
      4. 多列（a + b 唯一）：      point_code 文本 知识点编号；learner + point_code 唯一
    """
    single, multi = [], []
    for t in c["表"]:
        for f in t["字段"]:
            d = f["说明"]
            cols = E.unique_columns(d)
            if cols:
                multi.append((t["名"], cols, f["行"]))
            if E.text_declares_unique(d):
                single.append((t["名"], f["名"], f["行"]))
    return {"单列": single, "多列": multi}


def declared_scripts(c):
    """约定里声明的全部脚本路径（主脚本 + 出错脚本，去重保序）。"""
    out = []
    for sc in c.get("脚本", []):
        for p in (sc["路径"], sc["出错"]):
            if p and p not in out:
                out.append(p)
    return out


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
        m = re.match(r"^先\s+文件\s+(\S+)((?:\s+\S+=.*)?)$", s)
        if m:
            path, rest = m.group(1), m.group(2).strip()
            content = ""
            if rest:
                k, sep, v = rest.partition("=")
                if sep and k == "内容":
                    content = v
                else:
                    probs.append(f"第 {no} 行：先 文件 只认「内容=…」，现在是「{rest}」")
            u["先"].append({"种类": "文件", "路径": path, "内容": content, "行": no})
            return
        probs.append(f"第 {no} 行：先 写法是「先 数据 表 k=v …」「先 调用 [模块.]函数 k=v …」或「先 文件 <相对路径> [内容=…]」，现在是「{s}」")
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


def _auth_problems(c, fns):
    """「核对身份」的形状：必须是公开函数、入参恰好是 username（返回 {username, role}、查不到返回空由用例覆盖）。"""
    f = fns.get(ACCOUNT_FN)
    if f is None:
        return []
    probs = []
    if not f["公开"]:
        probs.append(f"函数「{ACCOUNT_FN}」必须是公开函数（认证核对要从路由层调它）")
    if [p.rstrip("?") for p in f["入参"]] != ["username"] or any(p.endswith("?") for p in f["入参"]):
        probs.append(f"函数「{ACCOUNT_FN}」的入参必须恰好是一个必填的 username，现在是 {' '.join(f['入参']) or '（无）'}")
    return probs


def _script_problems(c, name, all_modules):
    """## 脚本：路径要归本模块（文件名以「<本模块>_」开头，且不被更长的同前缀模块名认走）、不重复；出错脚本不能同时当主脚本。"""
    probs, seen = [], set()
    mods = set(all_modules) | {name}
    mains = {sc["路径"] for sc in c.get("脚本", [])}
    for sc in c.get("脚本", []):
        if sc["路径"] in seen:
            probs.append(f"第 {sc['行']} 行：脚本「{sc['路径']}」重复")
        seen.add(sc["路径"])
        for p in (sc["路径"], sc["出错"]):
            if not p or not SCRIPT_RE.match(p):
                continue
            stem = p[len("scripts/"):-len(".zs")]
            own = max((m for m in mods if stem.startswith(m + "_")), key=len, default=None)
            if own != name:
                probs.append(f"第 {sc['行']} 行：脚本「{p}」不属于本模块（文件名要以「{name}_」开头" +
                             (f"，现在归 {own}" if own else "") + "）")
        if sc["出错"] and sc["出错"] in mains:
            probs.append(f"第 {sc['行']} 行：出错脚本「{sc['出错']}」不能同时是别的脚本")
    return probs


def _content_problems(c, name):
    """## 内容文件：路径以 content/<本模块>/ 开头、后缀 .jsonl / .json、不含 ..、不重复；写 / 读列的函数要是本模块的函数。"""
    probs, seen = [], set()
    fnames = {f["名"] for f in c["函数"]}
    for x in c.get("内容文件", []):
        p = x["路径"]
        if p in seen:
            probs.append(f"第 {x['行']} 行：内容文件「{p}」重复")
        seen.add(p)
        m = CONTENT_RE.match(p)
        if ".." in p.split("/") or p.count("{") != p.count("}"):
            probs.append(f"第 {x['行']} 行：内容文件路径「{p}」不合法（不能含 ..，{{}} 要成对）")
        elif not m:
            probs.append(f"第 {x['行']} 行：内容文件路径「{p}」写法是 content/{name}/<路径>.jsonl（后缀只能是 .jsonl 或 .json）")
        elif m.group(1) != name:
            probs.append(f"第 {x['行']} 行：内容文件「{p}」不属于本模块（路径要以 content/{name}/ 开头；别的模块的内容文件不能碰，要数据就调对方的公开函数）")
        for what in ("写", "读"):
            for fn in x[what]:
                if fn not in fnames:
                    probs.append(f"第 {x['行']} 行：内容文件「{p}」的「{what}」里写了函数「{fn}」，本模块没有这个函数")
    return probs


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
    used_deps = set()
    for f in c["函数"]:
        for p in f["伪代码"]:
            for m in QCALL_RE.finditer(p["文字"]):
                used_deps.add(m.group(1))
    for u in c["用例"]:
        for st in u["先"]:
            if st["种类"] == "调用":
                mod, _, _ = st["目标"].rpartition(".")
                if mod:
                    used_deps.add(mod)
    for d in c["依赖"]:
        if d not in used_deps:
            probs.append(f"依赖「{d}」声明了，但伪代码「调用 {d}.…」和用例「先 调用 {d}.…」里都没出现，是多余依赖（删掉，或者补上调用）")
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
        if i["上传"] and f is not None:
            path_param = f"{i['上传']['字段']}_path"
            names = [p.rstrip("?") for p in f["入参"]]
            if path_param not in names:
                probs.append(f"第 {i['行']} 行：接口 {i['路径']} 声明了「上传 {i['上传']['字段']}」，但函数「{i['函数']}」没有入参「{path_param}」接收存盘路径")
    probs += _auth_problems(c, fns)
    probs += _script_problems(c, name, all_modules)
    probs += _content_problems(c, name)
    probs += text_space_problems(c)
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
            elif st["种类"] == "文件":
                path = st["路径"].replace("\\", "/")
                if path.startswith("/") or any(part == ".." for part in path.split("/")):
                    probs.append(f"第 {st['行']} 行：用例 {u['名']} 的「先 文件」路径「{st['路径']}」必须是相对路径且不含 ..")
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


def _free_text_params(f):
    """函数入参里的自由文本参数名（去掉 ? 后按 FREE_TEXT_PARAMS / *_path / *_text 认）。"""
    return [p.rstrip("?") for p in f["入参"]
            if p.rstrip("?") in FREE_TEXT_PARAMS or p.rstrip("?").endswith(("_path", "_text"))]


def _case_values(c):
    """用例里出现过的全部 k=v 值（调用 / 先 数据 / 先 调用 / 得 / 库 的值，以及「先 文件」的内容）。"""
    for u in c["用例"]:
        if u["调用"]:
            yield from u["调用"]["参数"].values()
        yield from (u["得"] or {}).values()
        for chk in u["库"]:
            yield from chk.get("值", {}).values()
        for st in u["先"]:
            if st["种类"] in ("数据", "调用"):
                yield from st["值"].values() if st["种类"] == "数据" else st["参数"].values()
            elif st["种类"] == "文件":
                yield st["内容"]


def text_space_problems(c):
    """自由文本入参的空格 / 换行覆盖（K16c 2a）：模块有接收自由文本的公开函数，而所有用例的值
    都不含空格、也不含字面 \\n（换行的唯一写法）→ 报一条。用例语法里「调用 / 先 数据 / 得 / 库」的值
    按空白切开、不能带空格，只有「先 文件 内容=…」能带空格（\\n 还原成真换行），所以文本带空格走文件、
    不能走文件的入参值里写字面 \\n，都算覆盖。"""
    fns = [(f, p) for f in c["函数"] if f["公开"] for p in _free_text_params(f)]
    if not fns:
        return []
    if any(" " in v or "\\n" in v for v in _case_values(c)):
        return []
    names = "、".join(f"{f['名']} 的 {p}" for f, p in fns[:3]) + ("…" if len(fns) > 3 else "")
    return [f"公开函数 {names} 是自由文本入参，但所有用例的值都不含空格 / 换行："
            f"至少一条用例的文本带空格或换行（走文件的入参用「先 文件 … 内容=…」，内容可带空格、换行写 \\n；"
            f"不能走文件的入参值里写字面 \\n，如 content=第一行\\n第二行），并用「库 …」或返回值核对原样保存"]


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
