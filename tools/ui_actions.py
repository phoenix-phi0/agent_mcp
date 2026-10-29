"""ui/*.ui 的远程动作提取：确定性、不调模型，给两头用——

  1. v3 写顶层 / 写约定时作为只读输入给模型（前端有哪些动作、各页面发什么、读什么）；
  2. 约定检查 / 比对约定核对「每个 .ui 远程动作都有且只有一个接口声明了它」。

只读 .ui，不改任何语法：解析直接用 tools.ui.parse（同一个解析器，编译前端用的也是它）。
一个「远程」动作 = 前端会发 POST {action, form} 的一次请求（tools/dsl_http.py 的 Router 摊平 form）。

    actions_of(project)  → [{动作, 界面, 端, 表单, lists, state, 带, 触发时机}]（按 .ui 文件与页面顺序）
    summary(project)     → 给提示词的一段文字（每个动作一行；没有 ui/ 返回空串）
    remote_names(project) → {动作名}（比对 .ui 覆盖用）
"""
from pathlib import Path


def ui_files(project):
    """项目 ui/ 下的 .ui（非递归，与 gen/project.py build 的取法一致）。"""
    d = Path(project) / "ui"
    return sorted(d.glob("*.ui")) if d.is_dir() else []


def _key(node):
    """组件读写的数据键：「绑」另指时用它，否则用名字（tools/ui.py 的 bind 同一规则）。"""
    return node.bind or node.name


def _screen_keys(screen):
    """一个界面读的数据键 → {"表单": [字段键], "lists": [数据键], "state": [共享路径]}（去重保序）。

    - 表单：界面上的「字段」（浮层里的也算，共用一张表单），提交时按这些键发；
    - lists：「列表」的数据键（「绑」或名字）+ 下拉的「选项来自 <键>」；
    - state：「共享」字段的路径、「显示」节点读的路径。
    """
    form, lists, state = [], [], []
    for n in screen.walk():
        if n.kind == "字段":
            form.append(_key(n))
            if n.has("共享"):
                state.append(_key(n))
            if n.source:
                lists.append(n.source)
        elif n.kind == "列表":
            lists.append(_key(n))
        elif n.kind == "显示":
            state.append(_key(n))
    dedup = lambda xs: list(dict.fromkeys(x for x in xs if x))  # noqa: E731
    return {"表单": dedup(form), "lists": dedup(lists), "state": dedup(state)}


def _timing(a):
    """动作的触发时机文字（进入时 / 载入 / 触发 / 每隔 / 回车…），提示词里给模型看。"""
    tags = [w for w in ("进入时", "隐藏", "清空", "提交", "回车") if a.has(w)]
    if a.every:
        tags.append(f"每隔 {a.every}s")
    if a.load:
        tags.append(f"被「载入 {a.load}」引用")
    if a.trigger:
        tags.append(f"被「触发 {a.trigger}」引用")
    return " ".join(tags)


def actions_of(project):
    """→ 远程动作列表，按文件与页面顺序。每项：
    {动作, 界面, 端, 表单, lists, state, 带, 触发时机, 文件, 行}
    「动作 <名> 远程」是按钮发起的请求；界面/浮层上的「载入 x」「触发 x」和字段的「改时 x」也是一次远程调用
    （带着地址参数进来时自动跑，tools/ui.py 的 check 和 gen build 都按动作名对 endpoints），一并提取。
    消息流「按钮 a,b」白名单里的动作是消息上的按钮点出的请求，也提取。"""
    from tools.ui import parse

    out = []
    for f in ui_files(project):
        try:
            screens = parse(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001  .ui 语法错由 gen build / 检查规划报，这里不重复
            continue
        for s in screens:
            keys = _screen_keys(s)
            seen = {}
            for a in s.actions():
                if not a.has("远程"):
                    continue
                seen[a.name] = {
                    "动作": a.name, "界面": s.name, "端": s.audience or "",
                    "表单": keys["表单"], "lists": keys["lists"], "state": keys["state"],
                    "带": a.carry or "", "触发时机": _timing(a),
                    "文件": f.name, "行": a.line,
                }
            for n in s.walk():
                for attr, word in (("load", "载入"), ("trigger", "触发"), ("on_change", "改时")):
                    name = getattr(n, attr, "") or ""
                    if name and name not in seen:
                        seen[name] = {
                            "动作": name, "界面": s.name, "端": s.audience or "",
                            "表单": keys["表单"], "lists": keys["lists"], "state": keys["state"],
                            "带": "", "触发时机": f"被「{word} {name}」引用（进页面 / 值一改就调）",
                            "文件": f.name, "行": n.line,
                        }
                # 消息流「按钮 a,b」：后端回的消息上的按钮点了调这些动作（带的键在消息的 carry 里）
                if n.kind == "消息流":
                    for name in [x.strip() for x in (n.buttons or "").split(",") if x.strip()]:
                        if name not in seen:
                            seen[name] = {
                                "动作": name, "界面": s.name, "端": s.audience or "",
                                "表单": keys["表单"], "lists": keys["lists"], "state": keys["state"],
                                "带": "消息的 carry", "触发时机": f"消息流「{n.name}」里消息上的按钮",
                                "文件": f.name, "行": n.line,
                            }
            out.extend(seen.values())
    return out


def remote_names(project):
    """{远程动作名}（.ui 侧的覆盖核对用）。"""
    return {a["动作"] for a in actions_of(project)}


def summary(project):
    """给提示词的一段文字：每个远程动作一行（动作、界面、发送键、页面读的键、行上带的字段）。
    没有 ui/ 目录或没有远程动作 → 空串（提示词里就不带这一节）。"""
    rows = actions_of(project)
    if not rows:
        return ""
    lines = []
    for a in rows:
        bits = [f"动作 {a['动作']}（界面「{a['界面']}」" + (f"，端 {a['端']}" if a["端"] else "") +
                (f"；{a['触发时机']}" if a["触发时机"] else "") + "）"]
        bits.append("发送表单键：" + ("、".join(a["表单"]) if a["表单"] else "（空表单）"))
        if a["带"]:
            bits.append(f"行上带 {a['带']}")
        reads = []
        if a["lists"]:
            reads.append("lists " + "、".join(a["lists"]))
        if a["state"]:
            reads.append("state " + "、".join(a["state"]))
        reads.append("form（回填）")
        bits.append("页面读：" + "；".join(reads))
        lines.append("- " + "，".join(bits))
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    text = summary(sys.argv[1] if len(sys.argv) > 1 else ".")
    print(text if text else "（没有 ui/*.ui 或没有远程动作）")
