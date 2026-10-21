"""确定性的两个生成：
  gen_skeleton  从冻结的约定生成 entities/<m>.entity（表）、services/<m>.zs（函数头 + 伪代码注释 + 报错 未实现）、routes/<m>.zs（接口头 + 调用）；
                已存在的文件不覆盖。生成后对新文件跑加载检查。
  gen_build     从 top.zs 按依赖分层生成 plan/build.zs（做模块组 …），不调模型。
"""
from pathlib import Path

from .. import loadcheck
from . import contracts as VC
from . import top as VT

TYPE_MAP = {"文本": "文本", "长文本": "长文本", "整数": "整数", "小数": "小数", "日期": "日期", "布尔": "布尔"}
OPTIONAL_HINTS = ("可空", "可选", "允许为空", "可以为空")


def entity_text(c):
    out = []
    for t in c["表"]:
        fields = []
        for f in t["字段"]:
            if f["名"] == "id" or "主键" in f["说明"]:
                continue
            typ = TYPE_MAP.get(f["类型"], "文本")
            req = "" if any(h in f["说明"] for h in OPTIONAL_HINTS) else " 必填"
            label = (f["说明"].split() or [f["名"]])[0]
            fields.append(f"  字段 {f['名']} {typ}{req} {label}")
        if not fields:
            fields = ["  字段 note 文本 备注"]
        out.append(f"实体 {t['名']} {t['名']}\n" + "\n".join(fields) + "\n结束\n")
    return "\n".join(out)


def service_text(name, c):
    lines = [f"业务 {name}"]
    if c["依赖"]:
        lines.append("  依赖 " + " ".join(c["依赖"]))
    pkgs = "common db text" + (" doc" if any(i.get("上传") for i in c["接口"]) else "")
    lines += [f"  用包 {pkgs}", ""]
    for f in c["函数"]:
        lines.append("  " + VC.C.head_text(f))
        if f["返回"]:
            lines.append(f"    # 返回 {f['返回']}")
        for e in f["报错"]:
            lines.append(f"    # 报错 {e['码']} {e['文字']}".rstrip())
        for p in f["伪代码"]:
            lines.append(f"    # {p['文字']}")
        lines += ["    报错 未实现", "  结束", ""]
    lines.append("结束")
    return "\n".join(lines) + "\n"


def auth_header(c):
    """约定头部的「认证 …」声明原样搬到 routes 文件顶层（写法与 tools/dsl_http.py 的路由顶层认证声明一致，
    那边才是真正解析生效的地方）。没有「认证」声明的模块返回空串。"""
    a = c["认证"]
    if not (a["必须"] or a["可选"]):
        return ""
    lines = ["认证 必须" if a["必须"] else "认证 可选"]
    if a["核对"]:
        lines.append("认证 核对 " + " ".join(a["核对"]))
    if a["身份"]:
        var, default = a["身份"]
        lines.append(f"认证 身份 {var} 默认 {default}")
    for code, label in a["角色"].items():
        line = f"认证 角色 {code} {label}"
        if code in a["拒绝"]:
            line += f" 拒绝 {a['拒绝'][code]}"
        lines.append(line)
    return "\n".join(lines) + "\n\n"


# file_name/file_size/file_ext 入参 -> 「上传信息」返回里的字段名；只有函数声明了才取
UPLOAD_INFO_FIELDS = {"file_name": "name", "file_size": "size", "file_ext": "ext"}


def _upload_lines(i, req, opt):
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


def route_text(name, c):
    fns = {f["名"]: f for f in c["函数"]}
    header = auth_header(c)
    out = [header] if header else []
    for i in c["接口"]:
        f = fns[i["函数"]]
        req, opt, _ = VC.C.params(f)
        pre = _upload_lines(i, req, opt) if i["上传"] else []
        args = [f"{p}={{{p}}}" for p in req] + [f"{p}={{{p} 或}}" for p in opt]
        tag = " 公开" if i["公开"] else (f" 角色 {i['角色']}" if i["角色"] else "")
        body = "".join(l + "\n" for l in pre)
        out.append(f"接口 {i['方法']} {i['路径']}{tag}\n{body}  设 r = 调用 {name}.{i['函数']}{(' ' + ' '.join(args)) if args else ''}\n  返回 {{r}}\n结束\n")
    return "\n".join(out)


PROJECT_ROUTES = "routes/_project.zs"           # 项目级（不属于任何模块）的 routes 文件：目前只放「迁移 只加」


def gen_skeleton(project, top, never_built=None, only=None):
    """→ {"新建": [相对路径], "已有": [相对路径], "问题": [加载检查问题]}。约定缺 / 解析不过抛 ValueError。
    任一模块的表带了「学习记录」标注 → 额外生成 routes/_project.zs（顶层「迁移 只加」，模型不写、top.zs 也不写，
    见 tools/migrate.py）。
    never_built(名) 为真的模块（state 里从没通过过，文件只可能是旧约定生成的骨架）：已有文件内容和现在的约定生成的不同就重写——
    约定在骨架之后被重写过（续跑 / 约定重做），不重写的话表结构会停在旧约定上，用例造数据必然失败。通过过的模块（改约定的修改流程）不动。"""
    project = Path(project)
    made, kept = [], []
    learner_record = False
    for m in top["模块"]:
        name = m["名"]
        if only is not None and name not in only:
            continue
        try:
            c, _ = VC.load(project, name)
        except FileNotFoundError:
            raise ValueError(f"缺约定 contracts/{name}.md") from None
        probs = VC.C.parse(VC.path_of(project, name).read_text(encoding="utf-8"))[1]
        if probs:
            raise ValueError(f"contracts/{name}.md 解析不过：{probs[0]}")
        if any(t.get("学习记录") for t in c["表"]):
            learner_record = True
        for rel, text in ((f"entities/{name}.entity", entity_text(c)), (f"services/{name}.zs", service_text(name, c)),
                          (f"routes/{name}.zs", route_text(name, c))):
            if not text.strip():
                continue
            f = project / rel
            if f.exists():
                if not (never_built and never_built(name)) or f.read_text(encoding="utf-8") == text:
                    kept.append(rel)
                    continue
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(text, encoding="utf-8", newline="\n")
            made.append(rel)
    if learner_record:
        f = project / PROJECT_ROUTES
        if f.exists():
            kept.append(PROJECT_ROUTES)
        else:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("迁移 只加\n", encoding="utf-8", newline="\n")
            made.append(PROJECT_ROUTES)
    probs = []
    if made:
        probs = [p for p in loadcheck.check_project(project) if any(r in p for r in made)]
    return {"新建": made, "已有": kept, "问题": probs}


def build_text(top):
    lines = ["# 由「生成分配」按 plan/top.zs 的依赖分层生成（程序生成，不调模型）：一层一行，同一层的模块并行做；上一层全部通过才做下一层",
             "用包 v3"]
    lines += ["做模块组 " + ",".join(layer) for layer in VT.layers(top)]
    # 各模块组都做完之后：全量回归（所有模块重新验收一遍）→ 接口冒烟（真起 Router 核对直接调用和走 HTTP 一致）
    lines.append("全量回归")
    lines.append("接口冒烟")
    lines.append("终止 成功 全部模块完成")
    return "\n".join(lines) + "\n"


def gen_build(project, top):
    f = Path(project) / "plan" / "build.zs"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(build_text(top), encoding="utf-8", newline="\n")
    return "plan/build.zs"
