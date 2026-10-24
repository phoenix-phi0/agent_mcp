"""dslproj 的约定文件 contracts/<模块>.md：固定可解析的格式（写法见 packs/README.md「dslproj」一节）。

    模块 progress
    依赖 graph                              # 没有依赖写「依赖 无」（或不写这行）

    ## 表                                   # 本模块拥有的表（只记表名和字段，实体文件由模型写，比对只看表是否建了）
    表 answer
      id 整数 主键
      learner 文本 学习者
    表 answer_log 学习记录                   # 拥有学习者真实记录的表要标「学习记录」（只加不重建，见 tools/migrate.py）

    ## 页面字段                              # 可选：页面专用字段（.ui 的列/表单要绑、业务表里没有的：tally、verdict、job_state 这类）
    页面 account_view 账号页面               # 实体名英文 snake + 中文名；不建表，骨架写成「页面 实体 …」（不进建库/迁移，查询/写库不能用）
      account_state 文本 状态                # 名 类型 说明，写法与「## 表」的字段行一致

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
    POST /note/list -> 列笔记 动作 note_list 模板 列表 键=notes 行=title,updated_at   # 封装标记（顺序不限，可不写）：动作 <名> 绑前端 .ui 的远程动作（必须
                                  # 和「模板」一起写，只有动作没有模板在检查里报）；模板 <中文名> [参数=值 …]＝返回封装走模板（只能用【接口封装模板】
                                  # 清单里的，骨架按模板生成组装信封的路由；参数缺 / 多 / 不合法都在检查里报）。
                                  # 传 <入参>=<定值> …＝调函数时这个入参用固定值（可多个；定值按空格切词、不能带空格，如 传 disabled=1）；
                                  # 参数 <前端键>=<入参> …＝前端表单键 <前端键> 的值传给函数入参 <入参>（可多个；前端键和函数参数名不一致时用）。
                                  # 「传」「参数」都要写在声明了「模板」的封装接口上，入参必须在函数头里、同一个入参不能既「传」定值又改名（检查里报）。
                                  # 有「动作」或「模板」的接口方法必须 POST（前端只会 POST）；出错照旧走 {"error": …} + 4xx

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
from tools.dslagent import iftpl

NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
PARAM_RE = re.compile(r"^[a-z_][a-z0-9_]*\??$")
IDENT = r"[A-Za-z0-9_一-鿿]+"
QCALL_RE = re.compile(rf"调用\s+({IDENT})\.({IDENT})")
METHODS = ("GET", "POST", "PUT", "DELETE")
SECTIONS = {"表": "表", "数据": "表", "页面字段": "页面字段", "函数": "函数", "接口": "接口", "用例": "用例", "脚本": "脚本", "内容文件": "内容文件"}
SCRIPT_RE = re.compile(r"^scripts/([a-z][a-z0-9_]*)\.zs$")
CONTENT_RE = re.compile(r"^content/([a-z][a-z0-9_]*)/([A-Za-z0-9_{}./-]+\.(?:jsonl|json))$")   # 内容文件路径：content/<模块>/…（.jsonl / .json，可含 {变量}）

# 自由文本入参：这些名字（或 *_text 结尾）装的是标题、内容、原因、备注这类用户随意写的文本，
# 用例要覆盖「值带空格 / 换行也原样保存」（见 text_space_problems；K19a 起只是提示，不拦约定加载）。
# 名单只收「用户写的整段文本」：路径（*_path，如 file_path）、检索关键词（keyword / keywords，
# teacher_rules 等还会把关键词里的空白规整掉）、来源 / 版权等标识（source / license，实际取值是
# model、S1 这类代号）、语气枚举（tone）、单词本身（word_text）跟空格覆盖关系不大，K19a 起不收。
FREE_TEXT_PARAMS = {
    "content", "title", "body", "text", "reason", "note", "notes", "desc", "description",
    "summary", "comment", "remark", "answer", "reply", "message", "question", "explanation",
    "detail", "details", "memo", "intro", "sentence", "recent_text", "must_info",
}

# 认证由程序生成：账号模块 = 有公开函数「核对身份」的模块
ACCOUNT_FN = "核对身份"
ROLE_LABELS = {"teacher": "教师", "student": "学生"}
# 接口行：<方法> <路径> -> <函数>，后面跟任意顺序的标记：上传 <字段> [类型 <扩展名,…>] [上限 <大小>]、公开、角色 <代号>、
# 动作 <名>、模板 <中文名> [参数=值 …]（返回封装一律走模板，模板文件见 templates/iface/，解析渲染见 tools/dslagent/iftpl.py）
IFACE_HEAD_RE = re.compile(r"^(\w+)\s+(\S+)\s*(?:->|→)\s*(\S+)(.*)$")
UPLOAD_SIZE_RE = re.compile(r"^\d+(?:\.\d+)?(?:B|KB|MB|GB)?$", re.I)


def has_wrap(i):
    """接口声明了封装（「动作 <名>」或「模板 <中文名> …」）→ 这是给前端用的接口（K25 起「动作」也算封装：
    要 POST、路由要绑动作、结尾不写「返回」；K26 起信封组装一律走模板，K27a 起「动作」必须配「模板」，
    只有动作没有模板的约定在检查里报）。"""
    return bool(i.get("动作")) or i.get("模板") is not None


def empty_wrap():
    """接口封装的缺省值（parse 出的每个接口都带这些键；「动作」「模板」都没写的旧接口行为与从前完全一样）。"""
    return {"动作": "", "模板": None, "传": {}, "参数": {}}


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
        # 行内 # 只有后跟空白 / 行尾才算注释开头（跳转 #首页?参数 这种 token 里的 # 不是注释）
        if i == 0 or (s[i - 1] in " \t" and (i + 1 >= len(s) or s[i + 1] in " \t")):
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
    """接口行 -> 函数 之后的标记（上传 / 类型 / 上限 / 公开 / 角色 / 动作 / 模板 [参数=值 …] /
    传 <入参>=<定值> … / 参数 <前端键>=<入参> …），顺序不限。
    「模板 <中文名>」后面的 键=值 token 都是它的参数（碰到没有 = 的标记就停）；「传」「参数」各只写一次，
    后面连续的 k=v token 都是它们的（定值按空格切词、不能带空格）。
    → (上传dict|None, 公开bool, 角色str, 动作str, 模板dict|None, 传dict, 参数dict, 问题列表)。"""
    toks = tail.split()
    probs = []
    upload, public, role = None, False, ""
    action, tpl = "", None
    fixed, ren = {}, {}          # 传：入参 -> 定值；参数：前端键 -> 入参
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
        elif t == "动作":
            if i + 1 >= len(toks):
                probs.append("「动作」后面要跟一个词")
                break
            if action:
                probs.append("「动作」只能写一次")
            action = toks[i + 1]
            i += 2
        elif t == "模板":
            if tpl is not None:
                probs.append("「模板」只能写一次")
                i += 1
                continue
            if i + 1 >= len(toks):
                probs.append("「模板」后面要跟模板中文名（可用模板见写约定输入里的【接口封装模板】清单）")
                break
            name = toks[i + 1]
            i += 2
            params = {}
            while i < len(toks) and "=" in toks[i]:
                k, _, v = toks[i].partition("=")
                if k in params:
                    probs.append(f"模板参数「{k}」重复")
                params[k] = v
                i += 1
            tpl = {"名": name, "参数": params}
        elif t == "传":
            if fixed:
                probs.append("「传」只能写一次")
                i += 1
                continue
            i += 1
            while i < len(toks) and "=" in toks[i]:
                k, _, v = toks[i].partition("=")
                if k in fixed:
                    probs.append(f"「传」的入参「{k}」重复")
                elif v == "":
                    probs.append(f"「传 {k}=」缺定值（定值直接写字面值，按空格切词、不能带空格，如 传 disabled=1）")
                else:
                    fixed[k] = v
                i += 1
            if not fixed:
                probs.append("「传」后面要跟 入参=定值 …（如 传 disabled=1；多个用空格隔开）")
        elif t == "参数":
            if ren:
                probs.append("「参数」只能写一次")
                i += 1
                continue
            i += 1
            while i < len(toks) and "=" in toks[i]:
                k, _, v = toks[i].partition("=")
                if k in ren:
                    probs.append(f"「参数」的前端键「{k}」重复")
                elif not NAME_RE.match(k):
                    probs.append(f"「参数」的前端键「{k}」要用英文 snake（前端表单键，要和 .ui 字段名对得上）")
                elif v == "":
                    probs.append(f"「参数 {k}=」缺函数入参（写法是 参数 <前端键>=<函数入参>，如 参数 reset_user=username）")
                elif v in ren.values():
                    probs.append(f"「参数 {k}={v}」：入参「{v}」已经被「参数」映射过（一个入参只收一个前端键）")
                else:
                    ren[k] = v
                i += 1
            if not ren:
                probs.append("「参数」后面要跟 前端键=函数入参 …（如 参数 reset_user=username；多个用空格隔开）")
        else:
            probs.append(f"不认识的接口标记「{t}」（只有 上传 <字段> [类型 …] [上限 …] / 公开 / 角色 <代号> / 动作 <名> / "
                         f"模板 <中文名> [参数=值 …] / 传 <入参>=<定值> … / 参数 <前端键>=<入参> …；返回封装只能用模板，清单见写约定的输入）")
            i += 1
    # 「传」×「参数」的交叉冲突在循环外查（两边的标记顺序不限，只看结果）：
    # 同一入参既传定值又被改名；前端键撞「传」的入参名。
    for k in sorted(set(fixed) & set(ren.values())):
        f = next(x for x, v in ren.items() if v == k)
        probs.append(f"「传 {k}={fixed[k]}」和「参数 {f}={k}」撞了同一个入参「{k}」（既传定值又改名，二选一）")
    for k in sorted(set(fixed) & set(ren)):
        probs.append(f"「参数 {k}={ren[k]}」：前端键「{k}」和「传」的入参重名（定值入参前端不发，换一个前端键）")
    if upload and upload["上限"] and not UPLOAD_SIZE_RE.match(upload["上限"]):
        probs.append(f"「上限 {upload['上限']}」写错了，写成 20MB / 500KB / 字节数")
    return upload, public, role, action, tpl, fixed, ren, probs


def parse(text):
    """→ (contract, 问题)。contract = {模块, 依赖, 表, 函数, 接口, 用例, 脚本, 内容文件}；各项带「行」。"""
    probs = []
    c = {"模块": None, "依赖": [], "表": [], "页面字段": [], "函数": [], "接口": [], "用例": [], "脚本": [], "内容文件": []}
    sec, cur = None, None
    for no, raw in enumerate(text.replace("\r", "").splitlines(), 1):
        if raw.strip().startswith("```"):
            continue
        if raw.strip().startswith("##"):
            title = raw.strip().lstrip("#").strip()
            sec = SECTIONS.get(title)
            cur = None
            if sec is None:
                probs.append(f"第 {no} 行：不认识的小节「{title}」（只有 表 / 页面字段 / 函数 / 接口 / 用例 / 脚本 / 内容文件）")
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
        elif sec == "页面字段":
            if h == "页面":
                if len(parts) not in (2, 3):
                    probs.append(f"第 {no} 行：页面写法是「页面 <实体名> [中文名]」，现在是「{s}」")
                    continue
                cur = {"名": parts[1], "中文名": parts[2] if len(parts) == 3 else parts[1],
                       "字段": [], "行": no}
                c["页面字段"].append(cur)
            elif cur is None:
                probs.append(f"第 {no} 行：字段要写在「页面 <实体名>」下面")
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
                probs.append(f"第 {no} 行：接口写法是「<GET|POST|PUT|DELETE> <路径> -> <函数名> [上传 <字段> [类型 …] [上限 …]] [公开|角色 <代号>] "
                             f"[动作 <名>] [模板 <中文名> [参数=值 …]]]，现在是「{s}」")
            else:
                method, path, fn, tail = m.groups()
                upload, pub, role, action, tpl, fixed, ren, tail_probs = _iface_tail(tail.strip())
                probs += [f"第 {no} 行：{p}" for p in tail_probs]
                if pub and role:
                    probs.append(f"第 {no} 行：接口「{path}」不能同时写「公开」和「角色」")
                c["接口"].append({"方法": method.upper(), "路径": path, "函数": fn, "公开": bool(pub), "角色": role or "",
                                  "上传": upload, "动作": action, "模板": tpl, "传": fixed, "参数": ren, "行": no})
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


# file_name/file_size/file_ext 入参 -> 「上传信息」返回里的字段名；只有函数声明了才取
UPLOAD_INFO_FIELDS = {"file_name": "name", "file_size": "size", "file_ext": "ext"}


def upload_lines(i, req, opt):
    """接口声明了「上传」时，先存文件（失败回 400），函数要 file_name/file_size/file_ext
    入参才额外取「上传信息」。返回要插在「调用」之前的那几行（已带两格缩进）。"""
    up = i["上传"]
    field = up["字段"]
    path_var = f"{field}_path"
    call = f"存文件 {field}"
    if up["类型"]:
        call += f" 类型={up['类型']}"
    if up["上限"]:
        call += f" 上限={up['上限']}"
    lines = [f"  设 {path_var} = {call}",
             f"  如果 {{{path_var}}} 开头是 [",
             f'    返回 {{"error":"{{{path_var}}}"}} 400',
             "  结束"]
    have = set(req) | set(opt)
    if have & set(UPLOAD_INFO_FIELDS):
        info_var = f"{field}_info"
        lines.append(f"  设 {info_var} = 上传信息 {field}")
        for pname, attr in UPLOAD_INFO_FIELDS.items():
            if pname in have:
                lines.append(f"  设 {pname} = {{{info_var}.{attr}}}")
    return lines


def route_body(module, i, fn):
    """封装接口的路由体：存文件（声明了「上传」时）→ 调用 → 模板渲染出的组装行（已带缩进，结尾不写「返回」）。
    K27a 起「动作」必须配「模板」（约定检查会拦只有动作的约定），这里总是按模板渲染。
    调用行的参数（K28b）：「传 入参=定值」写定值字面量、「参数 前端键=入参」写 入参={前端键}，其余照旧 p={p}（可选 p={p 或}）。
    骨架生成（v3.scaffold.route_text）和比对约定（project.compare 拿它和实际路由逐行比）共用这一份渲染，
    模板怎么改都不会出现「生成的」和「比对的」两套写法漂移。"""
    req, opt, _ = params(fn)
    lines = upload_lines(i, req, opt) if i["上传"] else []
    fixed, ren = i.get("传") or {}, i.get("参数") or {}
    front = {p: f for f, p in ren.items()}          # 入参 -> 前端键

    def arg(p, alt=""):
        if p in fixed:
            return f"{p}={fixed[p]}"                # 定值：写字面值（前端不发这个键）
        if p in front:
            return f"{p}={{{front[p]}{alt}}}"       # 改名：前端表单键的值传给函数入参
        return f"{p}={{{p}{alt}}}"

    args = [arg(p) for p in req] + [arg(p, " 或") for p in opt]
    lines.append(f"  设 r = 调用 {module}.{i['函数']}{(' ' + ' '.join(args)) if args else ''}")
    if not i["模板"]:
        raise ValueError(f"接口 {i['路径']} 声明了「动作 {i['动作']}」却没有「模板」：前端动作的接口要用模板组装返回"
                         f"（可用模板：{'、'.join(iftpl.names())}；约定检查会拦，这里不该走到）")
    lines += iftpl.render(i["模板"]["名"], i["模板"]["参数"])
    return lines


def form_args(i, kv):
    """接口冒烟发 HTTP 用的表单（v3.regress 用）：约定「参数 前端键=入参」把函数入参的键换成前端键、
    「传」定值的入参不发（路由里那是字面值，前端也不发这个键）。封装接口的调用行按 route_body 引用前端键，
    表单不对齐改名参数就收不到值。没写「传」「参数」的接口原样返回。"""
    ren, fixed = i.get("参数") or {}, set(i.get("传") or ())
    front = {p: f for f, p in ren.items()}
    return {front.get(k, k): v for k, v in kv.items() if k not in fixed}


def route_call_args(i, kv):
    """接口冒烟「直接调用」用的入参（v3.regress 用）：「传」定值的入参用约定的字面值——路由的调用行
    写的是定值字面量，不看用例给的这个键的值；其余照用例。「参数」改名只影响 HTTP 表单（form_args），
    直接调用本来就按函数入参名传，不动。"""
    fixed = i.get("传") or {}
    if not fixed:
        return kv
    out = dict(kv)
    out.update(fixed)
    return out


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
    pnames = set()
    for pg in c["页面字段"]:
        if not NAME_RE.match(pg["名"]):
            probs.append(f"第 {pg['行']} 行：页面实体名「{pg['名']}」要用英文 snake")
        if pg["名"] in pnames:
            probs.append(f"第 {pg['行']} 行：页面实体「{pg['名']}」重复")
        if pg["名"] in tnames:
            probs.append(f"第 {pg['行']} 行：「{pg['名']}」既是「## 表」里的表又是页面实体（页面实体不建表，一个名字只能是一样）")
        pnames.add(pg["名"])
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
    seen_act = set()
    for i in c["接口"]:
        key = (i["方法"], i["路径"])
        if key in seen:
            probs.append(f"第 {i['行']} 行：接口 {i['方法']} {i['路径']} 重复")
        seen.add(key)
        if i["方法"] not in METHODS:
            probs.append(f"第 {i['行']} 行：方法「{i['方法']}」不在 {'/'.join(METHODS)} 里")
        if not i["路径"].startswith("/"):
            probs.append(f"第 {i['行']} 行：路径「{i['路径']}」要以 / 开头")
        if has_wrap(i) and i["方法"] != "POST":
            marked = "、".join([f"动作 {i['动作']}" if i["动作"] else "", f"模板 {i['模板']['名']}" if i["模板"] else ""]).strip("、")
            probs.append(f"第 {i['行']} 行：接口 {i['路径']} 声明了封装（{marked}），是给前端用的，"
                         f"方法要写 POST（前端一律发 POST {chr(123)}action, form{chr(125)}，GET/DELETE 前端打不通）")
        if i["动作"]:
            if not NAME_RE.match(i["动作"]):
                probs.append(f"第 {i['行']} 行：动作名「{i['动作']}」要用英文 snake（和 .ui 里「动作 <名> 远程」的名字一字不差）")
            if i["动作"] in seen_act:
                probs.append(f"第 {i['行']} 行：动作「{i['动作']}」被本模块两个接口声明（一个动作名只能绑一个接口）")
            seen_act.add(i["动作"])
        if i["动作"] and i["模板"] is None:
            probs.append(f"第 {i['行']} 行：接口 {i['路径']} 声明了「动作 {i['动作']}」却没有「模板」——前端动作的接口要用模板组装返回"
                         f"（只写「动作」的接口会返回空信封，前端拿到什么都不显示）；可用模板：{'、'.join(iftpl.names())}"
                         f"（写约定的输入里有模板清单）")
        if i["模板"]:
            for p in iftpl.validate(i["模板"]["名"], i["模板"]["参数"]):
                probs.append(f"第 {i['行']} 行：{p}")
        f = fns.get(i["函数"])
        if f is None or not f["公开"]:
            probs.append(f"第 {i['行']} 行：接口 {i['路径']} 调的函数「{i['函数']}」不是本模块的公开函数")
        if i["上传"] and f is not None:
            path_param = f"{i['上传']['字段']}_path"
            names = [p.rstrip("?") for p in f["入参"]]
            if path_param not in names:
                probs.append(f"第 {i['行']} 行：接口 {i['路径']} 声明了「上传 {i['上传']['字段']}」，但函数「{i['函数']}」没有入参「{path_param}」接收存盘路径")
        if f is not None and (i["传"] or i["参数"]):
            if i["模板"] is None:
                probs.append(f"第 {i['行']} 行：「传 …」「参数 …」只对声明了「模板」的封装接口有意义"
                             f"（裸接口没有前端键可改，调用参数就是函数入参）")
            else:
                pnames = [p.rstrip("?") for p in f["入参"]]
                for k in sorted(i["传"]):
                    if k not in pnames:
                        probs.append(f"第 {i['行']} 行：「传 {k}={i['传'][k]}」的 {k} 不是函数「{i['函数']}」的入参"
                                     f"（「传」只能给函数头里有的入参定值）")
                for fk, p in sorted(i["参数"].items()):
                    if p not in pnames:
                        probs.append(f"第 {i['行']} 行：「参数 {fk}={p}」的 {p} 不是函数「{i['函数']}」的入参")
                    elif fk in pnames and fk != p:
                        probs.append(f"第 {i['行']} 行：「参数 {fk}={p}」的前端键「{fk}」和函数入参「{fk}」重名"
                                     f"（同名入参本来就照 {fk}={{{fk}}} 传，别让一个表单键喂两个入参）")
                if i["上传"]:
                    path_param = f"{i['上传']['字段']}_path"
                    for k in sorted((set(i["传"]) | set(i["参数"].values())) & {path_param}):
                        probs.append(f"第 {i['行']} 行：入参「{k}」由「上传 {i['上传']['字段']}」的存盘路径传入，不能再用「传」/「参数」改写")
    probs += _auth_problems(c, fns)
    probs += _script_problems(c, name, all_modules)
    probs += _content_problems(c, name)
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
    """函数入参里的自由文本参数名（去掉 ? 后按 FREE_TEXT_PARAMS / *_text 认；*_path 是路径，不算自由文本）。"""
    return [p.rstrip("?") for p in f["入参"]
            if p.rstrip("?") in FREE_TEXT_PARAMS or p.rstrip("?").endswith("_text")]


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
    """自由文本入参的空格 / 换行覆盖**提示**（K16c 2a 定的规则；K19a 起从 C.check 的拦截问题挪到
    project.compare 的「提示」，不算问题、不拦约定加载 / 跑用例 / 核查，在 比对约定 动词的 hints
    和验收摘要里可见）：模块有接收自由文本的公开函数，而所有用例的值
    都不含空格、也不含字面 \\n（换行的唯一写法）→ 提示一条。用例语法里「调用 / 先 数据 / 得 / 库」的值
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
