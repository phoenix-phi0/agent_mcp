"""接口封装模板：约定「## 接口」行写「模板 <中文名> [参数=值 …]」，模板集中放在
tools/dslagent/templates/iface/（一个模板一个文件，文件名英文、中文名写在文件第一行），
加新模板不改代码。文件的格式（人能直接读懂改，这里确定性解析渲染）：

    # 注释行（# 开头）忽略
    模板 <中文名>                          # 第一行；约定里就写这个名字（不含空格）
    用途 <一句话>
    参数 <名> <必填|可选> <约束> <含义…>    # 约束：snake 英文snake / snake_list 逗号隔开的snake /
                                           #       free 一句话文字 / go 跳转目标（界面名|@来处|#界面?参数）
    例子 <接口行示例>
    主体 [当 <参数>[,<参数>…]]             # 路由主体，插在「调用」之后；占位符 <<参数>> 引用参数。
      <路由行…>                            # 「当」= 只在这些参数都给了值时渲染；不带「当」的是缺省块。
                                           # 渲染时带「当」的优先（按文件里的顺序取第一个参数齐的），都不中才用缺省块。

渲染只做「替换 <<参数>>」，路由主体只用现有响应动词（表格 / 响应 form|state|go、消息）和「设」，
结尾不写「返回」（脚本正常跑完时响应桶就是返回体）。含空格的参数值（消息文字）由模板一次兜住：
先「设」给变量再传——值整个是 {变量} 时引擎不按空格切（verbs 的参数切分规则）。

骨架生成（v3.scaffold）、比对约定（packs.dslproj.project.compare，直接拿 route_body 和实际路由逐行比）
和接口冒烟（v3.regress._envelope，把渲染出的路由体逐行解释成前端信封）都吃同一份渲染结果，
所以加新模板这三处都不用改。
"""
import re
from pathlib import Path

DIR = Path(__file__).resolve().parent / "templates" / "iface"
PLACEHOLDER_RE = re.compile(r"<<([^<>\s]+)>>")
SNAKE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
GO_RE = re.compile(r"^@来处$|^#[^?\s]+(?:\?[^=\s]+=[^=\s]+)?$|^[^@#?\s]+$")
CONSTRAINTS = ("snake", "snake_list", "free", "go")
_HEAD = ("模板", "用途", "参数", "例子", "主体")


def _parse(text):
    """模板文件文本 → (tpl, 问题)。tpl = {"名","用途","参数":{名:{必填,约束,含义}},"顺序","例子","主体":[{当,行}]}。"""
    tpl = {"名": "", "用途": "", "参数": {}, "顺序": [], "例子": "", "主体": []}
    probs = []
    cur = None
    for raw in text.replace("\r", "").splitlines():
        s = raw.rstrip()
        t = s.strip()
        if not t or t.startswith("#"):
            continue
        head = t.split()[0]
        if head in _HEAD:
            cur = None
            if head == "模板":
                parts = t.split()
                if len(parts) != 2:
                    probs.append("首行写法是「模板 <中文名>」（中文名里不要空格）")
                else:
                    tpl["名"] = parts[1]
            elif head == "用途":
                tpl["用途"] = t[len("用途"):].strip()
            elif head == "参数":
                parts = t.split()
                if len(parts) < 4 or parts[2] not in ("必填", "可选") or parts[3] not in CONSTRAINTS:
                    probs.append(f"参数行写法是「参数 <名> <必填|可选> <{'/'.join(CONSTRAINTS)}> <含义…>」，现在是「{t}」")
                elif parts[1] in tpl["参数"]:
                    probs.append(f"参数「{parts[1]}」重复")
                else:
                    tpl["参数"][parts[1]] = {"必填": parts[2] == "必填", "约束": parts[3], "含义": " ".join(parts[4:])}
                    tpl["顺序"].append(parts[1])
            elif head == "例子":
                tpl["例子"] = t[len("例子"):].strip()
            else:
                m = re.match(r"^主体(?:\s+当\s+(\S+))?\s*$", t)
                if not m:
                    probs.append(f"主体行写法是「主体」或「主体 当 <参数>[,<参数>…]」，现在是「{t}」")
                    continue
                cur = {"当": [x for x in (m.group(1) or "").split(",") if x], "行": []}
                tpl["主体"].append(cur)
            continue
        if cur is None:
            probs.append(f"不认识的模板行「{t[:40]}」（只有 模板 / 用途 / 参数 / 例子 / 主体，路由行要缩进写在「主体」下面）")
            continue
        cur["行"].append(s)
    if not tpl["名"]:
        probs.append("缺「模板 <中文名>」首行")
    if not tpl["主体"]:
        probs.append("缺「主体」（路由主体）")
    for b in tpl["主体"]:
        for g in b["当"]:
            if g not in tpl["参数"]:
                probs.append(f"「主体 当 {g}」的 {g} 不是声明的参数")
        for line in b["行"]:
            for ph in PLACEHOLDER_RE.findall(line):
                if ph not in tpl["参数"]:
                    probs.append(f"主体里的占位符 <<{ph}>> 不是声明的参数")
    return tpl, probs


def all_():
    """{中文名: tpl}。模板文件是仓库自己的文件，写法坏了抛 ValueError（炸出来，不能吞）。"""
    out = {}
    for f in sorted(DIR.glob("*.zs")):
        tpl, probs = _parse(f.read_text(encoding="utf-8"))
        if probs:
            raise ValueError(f"接口模板 {f.name} 写法不对：{'；'.join(probs)}")
        if tpl["名"] in out:
            raise ValueError(f"接口模板中文名「{tpl['名']}」重复（{f.name}）")
        out[tpl["名"]] = tpl
    return out


def get(name):
    return all_().get(name)


def names():
    return sorted(all_())


def _value_problem(constraint, v):
    """参数值违反约束 → 一句话说明；合法 → 空串。"""
    if v == "":
        return "值不能为空"
    if constraint == "snake":
        return "" if SNAKE_RE.match(v) else "要英文 snake（小写字母开头，小写字母 / 数字 / 下划线）"
    if constraint == "snake_list":
        parts = v.split(",")
        bad = [x for x in parts if not x or not SNAKE_RE.match(x)]
        return "" if not bad else "要是逗号隔开的英文 snake 字段名"
    if constraint == "go":
        return "" if GO_RE.match(v) else "要是界面名 / @来处 / #界面?参数（不含空格）"
    return ""          # free：一句话文字，不切参数就行


def validate(name, params):
    """约定里的「模板 <名> 键=值 …」按模板定义校验 → 问题列表（空 = 通过）。
    查：未知模板、缺必填参数、多余参数、取值不合法。"""
    tpl = get(name)
    if tpl is None:
        return [f"不认识的封装模板「{name}」（可用：{'、'.join(names()) or '（还没有模板）'}；写约定的输入里有模板清单）"]
    probs = []
    known = set(tpl["参数"])
    for k in tpl["顺序"]:
        if k in params:
            bad = _value_problem(tpl["参数"][k]["约束"], params[k])
            if bad:
                probs.append(f"模板 {name} 的参数「{k}={params[k]}」不合法：{bad}")
    for k in sorted(set(params) - known):
        probs.append(f"模板 {name} 没有参数「{k}」（有的：{'、'.join(tpl['顺序']) or '无'}）")
    missing = [k for k in tpl["顺序"] if tpl["参数"][k]["必填"] and k not in params]
    if missing:
        probs.append(f"模板 {name} 缺必填参数 {'、'.join(missing)}")
    return probs


def render(name, params):
    """按模板渲染路由主体（插在「调用」之后的那些行，带缩进）。模板 / 参数不对抛 ValueError。"""
    probs = validate(name, params)
    if probs:
        raise ValueError(probs[0])
    tpl = get(name)
    block = next((b for b in tpl["主体"] if b["当"] and all(params.get(g) for g in b["当"])), None)
    if block is None:
        block = next((b for b in tpl["主体"] if not b["当"]), None)
    if block is None:
        raise ValueError(f"模板 {name} 的参数 {'、'.join(sorted(params)) or '（无）'} 命不中任何主体块")
    return [PLACEHOLDER_RE.sub(lambda m: params[m.group(1)], line) for line in block["行"]]


def envelope(name, params, r):
    """模板渲染出的路由体 + 直接调用结果 r → 前端信封（接口冒烟用）。
    逐行解释渲染结果，只认「设 变量 = 值」和现有的响应动词（表格 / 响应 form|state|go / 消息），
    与 Router 的响应桶行为一致；加新模板不用改这里。"""
    env, vs = {}, {}
    for line in render(name, params):
        s = line.strip()
        m = re.match(r"^设\s+([A-Za-z_]\w*)\s*=\s*(.*)$", s)
        if m:
            vs[m.group(1)] = _expand(m.group(2), vs)
            continue
        m = re.match(r"^表格\s+(\S+)\s+(\S+)$", s)
        if m:
            env.setdefault("lists", {})[m.group(1)] = _pick(m.group(2), r, vs)
            continue
        m = re.match(r"^响应\s+form\s+(\S+)$", s)
        if m:
            env["form"] = _pick(m.group(1), r, vs)
            continue
        m = re.match(r'^响应\s+state\s+\{"(.+?)":(.+)\}$', s)
        if m:
            env.setdefault("state", {})[m.group(1)] = _pick(m.group(2), r, vs)
            continue
        m = re.match(r"^响应\s+go\s+(\S+)$", s)
        if m:
            env["go"] = m.group(1)
            continue
        m = re.match(r"^消息\s+(\S+)\s+(\S+)(?:\s+(\S+))?\s*$", s)
        if m:
            msg = {"who": m.group(1), "text": _expand(m.group(2), vs)}
            if m.group(3):
                msg["kind"] = m.group(3)
            env.setdefault("messages", []).append(msg)
    return env


def _pick(token, r, vs):
    """{r} / {r.字段} → 直接调用结果的对应值；单个 {变量} → 「设」过的值；其余原样。"""
    m = re.match(r"^\{r(?:\.([A-Za-z_]\w*))?\}$", token)
    if m:
        return r if m.group(1) is None else (r.get(m.group(1)) if isinstance(r, dict) else None)
    return _expand(token, vs)


def _expand(token, vs):
    m = re.match(r"^\{([A-Za-z_]\w*)\}$", token)
    return vs[m.group(1)] if m and m.group(1) in vs else token


def listing():
    """给写约定 / 复核约定的模型看的模板清单（中文名、用途、参数、例子），从模板文件生成，不手抄。"""
    out = []
    tpl_all = all_()
    for name in names():
        t = tpl_all[name]
        ps = "；".join(f"{k} {'必填' if t['参数'][k]['必填'] else '可选'}（{t['参数'][k]['含义']}）" for k in t["顺序"])
        out.append(f"- 模板 {name}：{t['用途']}\n  参数：{ps or '（无）'}\n  例子：{t['例子']}")
    return "\n".join(out)
