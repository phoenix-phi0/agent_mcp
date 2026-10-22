"""确定性的两个生成：
  gen_skeleton  从冻结的约定生成 entities/<m>.entity（表）、services/<m>.zs（函数头 + 伪代码注释 + 报错 未实现）、routes/<m>.zs（接口头 + 调用）；
                已存在的文件不覆盖。生成后对新文件跑加载检查。
  gen_build     从 top.zs 按依赖分层生成 plan/build.zs（做模块组 …），不调模型。
"""
import json
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


def auth_header(name, contracts):
    """账号模块（有公开函数「核对身份」的模块）的 routes 顶部认证块，由程序生成、全项目只有一份；其他模块返回空串。
    contracts：{模块: 约定}（全项目）。写法与 tools/dsl_http.py 的路由顶层认证声明一致，那边才是真正解析生效的地方。"""
    owner, lines = VC.C.auth_block(contracts)
    if owner != name:
        return ""
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


def route_text(name, c, contracts=None):
    fns = {f["名"]: f for f in c["函数"]}
    header = auth_header(name, contracts if contracts is not None else {name: c})
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


SKELETON_REC = "plan/skeleton.json"           # {模块: 生成骨架时的约定 hash}
PROJECT_ROUTES = "routes/_project.zs"           # 项目级（不属于任何模块）的 routes 文件：目前只放「迁移 只加」


def gen_skeleton(project, top, never_built=None):
    """→ {"新建": [相对路径], "已有": [相对路径], "问题": [加载检查问题]}。约定缺 / 解析不过抛 ValueError。
    任一模块的表带了「学习记录」标注 → 额外生成 routes/_project.zs（顶层「迁移 只加」，模型不写、top.zs 也不写，
    见 tools/migrate.py）。
    重写判据：只看约定 hash，不拿磁盘文件和新骨架比。plan/skeleton.json 记每个模块生成骨架时的约定 hash；
    文件不存在 → 写；never_built(名) 为真（state 里从没通过过）且记录的 hash 与现在的约定 hash 不同（约定在骨架之后被重写过）
    → 该模块三个文件都重写；其余（约定没变，或通过过的模块，或没有记录的老项目）已有文件一律不动——做了一半、没通过、约定没变的模块续跑不会丢进度。"""
    project = Path(project)
    made, kept = [], []
    learner_record = False
    rec_f = project / SKELETON_REC
    try:
        rec = json.loads(rec_f.read_text(encoding="utf-8")) if rec_f.is_file() else {}
    except ValueError:
        rec = {}
    if not isinstance(rec, dict):
        rec = {}
    contracts = {}
    for m in top["模块"]:
        try:
            contracts[m["名"]] = VC.load(project, m["名"])[0]
        except FileNotFoundError:
            raise ValueError(f"缺约定 contracts/{m['名']}.md") from None
    for m in top["模块"]:
        name = m["名"]
        c = contracts[name]
        probs = VC.C.parse(VC.path_of(project, name).read_text(encoding="utf-8"))[1]
        if probs:
            raise ValueError(f"contracts/{name}.md 解析不过：{probs[0]}")
        if any(t.get("学习记录") for t in c["表"]):
            learner_record = True
        chash = VC.C.hash_of(VC.path_of(project, name).read_text(encoding="utf-8"))
        stale = bool(never_built and never_built(name) and rec.get(name) and rec.get(name) != chash)
        rec[name] = chash
        for rel, text in ((f"entities/{name}.entity", entity_text(c)), (f"services/{name}.zs", service_text(name, c)),
                          (f"routes/{name}.zs", route_text(name, c, contracts))):
            if not text.strip():
                continue
            f = project / rel
            if f.exists() and not stale:
                kept.append(rel)
                continue
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(text, encoding="utf-8", newline="\n")
            made.append(rel)
    rec_f.parent.mkdir(parents=True, exist_ok=True)
    rec_f.write_text(json.dumps(rec, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8", newline="\n")
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


REDO_FILE = "plan/redo_failed.zs"

# 检查查出不过的模块 → 记验收 → 按依赖分层重做（同一层并行，直接调 做一个模块，第一轮就带检查查出的原因）。
# 全部重做通过 返回 通过；有模块没过 终止 失败（调用方拿到 {status, reason}）
REDO_TEXT = """# 重做检查查出不过的模块（由「生成分配」生成，程序生成不调模型）：build.zs 里 全量回归 / 接口冒烟 各调一次。
# 先记验收 否，再按依赖分层重做：同一层并行，直接调 做一个模块（不看「已完成」：state 里可能还记着通过，但检查已经说它不过），起始原因 = 检查查出的原因。
# 参数：check failed layers   （check = 全量回归|接口冒烟；failed = 检查结果的 failed 列表；layers = 依赖分层）
用包 common v3 text
遍历 f 于 {failed}
  设 m = 记验收 {f.module} 否 {check}：{f.reason}
结束
遍历 group 于 {layers}
  设 mods = 按正则切分 {group} [,，、\\s]+
  设 jobs = 解析JSON []
  遍历 m 于 {mods}
    遍历 f 于 {failed}
      如果 {f.module} 等于 {m}
        设 job = 解析JSON {"脚本":"做一个模块","参数":{"最多":"3","末次模型":"opus"}}
        设 job.参数.模块 = {m}
        设 job.参数.起始原因 = {check}发现问题：{f.reason}
        设 jobs = 列表加项 {jobs} {job}
      结束
    结束
  结束
  设 res = 并行执行 {jobs} 并发=3
  设 s = 汇总失败 {res}
  如果 {s.count} 大于 0
    终止 {s.status} {check}重做未通过：{s.reason}
  结束
结束
返回 {"status":"通过"}
"""

# 检查 → 有不过的模块 → 交 plan/redo_failed.zs 按依赖分层重做 → 再检查；第 2 次检查仍不过 终止 失败
CHECK_BLOCK = """设 rs = {verb}
如果 {rs.count} 大于 0
  设 r = 执行 plan/redo_failed check={verb} failed={rs.failed} layers={layers}
  如果 {r.status} 不等于 通过
    终止 {r.status} {r.reason}
  结束
  设 rs = {verb}
  如果 {rs.count} 大于 0
    终止 失败 {verb}两轮仍未通过：{rs.failed_text}
  结束
结束
"""


def build_text(top):
    lines = ["# 由「生成分配」按 plan/top.zs 的依赖分层生成（程序生成，不调模型）：一层一行，同一层的模块并行做；上一层全部通过才做下一层",
             "# 各模块组做完后：全量回归 → 接口冒烟，都是只检查的动词；不过的模块交 plan/redo_failed.zs 按依赖分层重做，最多 2 轮，仍不过 终止 失败",
             "用包 common v3 text"]
    lines += ["做模块组 " + ",".join(layer) for layer in VT.layers(top)]
    lines.append("设 layers = 依赖分层")
    lines.append(CHECK_BLOCK.replace("{verb}", "全量回归").rstrip("\n"))
    lines.append(CHECK_BLOCK.replace("{verb}", "接口冒烟").rstrip("\n"))
    lines.append("如果 {rs.notes_text} 不为空")
    lines.append("  设 m = 记验收 _接口冒烟 是 备注：{rs.notes_text}")
    lines.append("结束")
    lines.append("终止 成功 全部模块完成")
    return "\n".join(lines) + "\n"


def gen_build(project, top):
    f = Path(project) / "plan" / "build.zs"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(build_text(top), encoding="utf-8", newline="\n")
    (Path(project) / REDO_FILE).write_text(REDO_TEXT, encoding="utf-8", newline="\n")
    return "plan/build.zs"
