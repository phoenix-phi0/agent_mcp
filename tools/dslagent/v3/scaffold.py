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
    lines += ["  用包 common db", ""]
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


def route_text(name, c):
    fns = {f["名"]: f for f in c["函数"]}
    out = []
    for i in c["接口"]:
        f = fns[i["函数"]]
        req, opt, _ = VC.C.params(f)
        args = [f"{p}={{{p}}}" for p in req] + [f"{p}={{{p} 或}}" for p in opt]
        out.append(f"接口 {i['方法']} {i['路径']}\n  设 r = 调用 {name}.{i['函数']}{(' ' + ' '.join(args)) if args else ''}\n  返回 {{r}}\n结束\n")
    return "\n".join(out)


def gen_skeleton(project, top):
    """→ {"新建": [相对路径], "已有": [相对路径], "问题": [加载检查问题]}。约定缺 / 解析不过抛 ValueError。"""
    project = Path(project)
    made, kept = [], []
    for m in top["模块"]:
        name = m["名"]
        try:
            c, _ = VC.load(project, name)
        except FileNotFoundError:
            raise ValueError(f"缺约定 contracts/{name}.md") from None
        probs = VC.C.parse(VC.path_of(project, name).read_text(encoding="utf-8"))[1]
        if probs:
            raise ValueError(f"contracts/{name}.md 解析不过：{probs[0]}")
        for rel, text in ((f"entities/{name}.entity", entity_text(c)), (f"services/{name}.zs", service_text(name, c)),
                          (f"routes/{name}.zs", route_text(name, c))):
            if not text.strip():
                continue
            f = project / rel
            if f.exists():
                kept.append(rel)
                continue
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(text, encoding="utf-8", newline="\n")
            made.append(rel)
    probs = []
    if made:
        probs = [p for p in loadcheck.check_project(project) if any(r in p for r in made)]
    return {"新建": made, "已有": kept, "问题": probs}


def build_text(top):
    lines = ["# 由「生成分配」按 plan/top.zs 的依赖分层生成（程序生成，不调模型）：一层一行，同一层的模块并行做；上一层全部通过才做下一层",
             "用包 v3"]
    lines += ["做模块组 " + ",".join(layer) for layer in VT.layers(top)]
    lines.append("终止 成功 全部模块完成")
    return "\n".join(lines) + "\n"


def gen_build(project, top):
    f = Path(project) / "plan" / "build.zs"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(build_text(top), encoding="utf-8", newline="\n")
    return "plan/build.zs"
