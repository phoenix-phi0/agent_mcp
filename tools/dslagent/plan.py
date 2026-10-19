"""模型写的计划交给执行前的检查：去掉说明文字、分出子脚本、白名单、补末尾缺的「结束」、假模型空跑。

- strip_prose：去掉代码围栏和首尾的说明文字行。
- split_subs：「#子脚本 名字.zs」分出子脚本（主脚本里用 执行 _plan/名字.zs 调）。
- whitelist_check：语句头、动词、「设 x = 动词」右边、问 的后缀、执行 的目标都要在白名单里。
- autoclose：只差末尾的「结束」时自动补上（plan5 起：模型常漏最后一两个「结束」，补上省一次重写）。
- dry_run：在项目的一份拷贝里用假模型跑一遍：报错、没打印「结论：」（也没「终止」）、同一提示词原样问两次（上一轮结果没带进下一轮）
  都算没过，带着问题回去让模型重写（最多 2 次）。空跑时 派任务 / 并行派任务 不调假模型，直接给结构合法的假结果。
- 脚本末尾的「#改法 名」「#清单」段（tools/dsl_sections，多行字面量）：strip_prose 整段留着、split_subs 归到主脚本、
  autoclose 不看段内、whitelist_check 跳过段内并报段写错的地方；执行和空跑时引擎自己把段拿出来（{名} 交给 改文件）。
"""
import json
import os
import re
import shutil
import signal
from pathlib import Path

from tools.dsl_sections import EDIT_HEAD, LIST_HEAD, split_sections

from .engine import ALLOWED_HEADS, AgentEngine

PKG = Path(__file__).resolve().parent
ROOT = PKG.parents[1]
SUB, LOC = "读改测.zs", "定位.zs"
LIBS = (SUB, LOC)
# 与任务类型无关的动词（common / text 包 + 派任务）；任务类型相关的动词由资料包声明（packs/<名>.VERBS），白名单 = 这里 ∪ 包的 VERBS
BASE_VERBS = frozenset({"匹配", "找全部", "替换", "截取", "相等", "挑行", "按正则切分", "列表加项", "归一化",
                        "解析JSON", "列表长度", "转数字", "取字段", "当前时间", "派任务", "并行派任务"})
# code 包的动词（packs/code.py 的 VERBS 用它；旧路径 / 没传包的 whitelist_check 缺省 = BASE ∪ CODE）
CODE_VERBS = frozenset({"列文件", "搜索代码", "读片段", "运行代码", "改文件", "跑测试", "写文件", "删文件", "改模块名", "查引用"})
ALLOWED_VERBS = BASE_VERBS | CODE_VERBS
# 所有包里的动词名（白名单外的也要认出来，才能判「用了白名单外的动词」）
ALL_VERBS = {p.stem for p in (PKG / "verbs").rglob("defs/*.py") if not p.stem.startswith("_")} | \
            {p.stem for p in (ROOT / "verbs").rglob("defs/*.py") if not p.stem.startswith("_")}
LOC_MARK = "你在帮忙定位"
RCT_MARK = "你在修一个 Python 项目（不能改测试文件）"
DRY_SECONDS = 90
COPY_IGNORE = shutil.ignore_patterns(".*", "__pycache__", "node_modules", "venv", "env", "site-packages",
                                     "build", "dist", "*.pyc")


def _heads():
    from tools.dsl_core import KEYWORDS, split_head
    return split_head, KEYWORDS


def strip_prose(text):
    """去掉代码围栏和首尾的说明文字行。返回 (脚本, 去掉的行数)。"""
    split_head, KW = _heads()
    lines = [l for l in text.replace("\r", "").splitlines() if not l.strip().startswith("```")]

    def is_code(l):
        s = l.strip()
        if not s or s.startswith("#"):
            return True
        h, _ = split_head(s)
        return h in set(KW.values()) or h in ALL_VERBS
    first = next((i for i, l in enumerate(lines) if l.strip() and is_code(l) and not l.strip().startswith("#")), 0)
    last = max((i for i, l in enumerate(lines) if l.strip() and is_code(l)), default=len(lines) - 1)
    sec = next((i for i, l in enumerate(lines) if EDIT_HEAD.match(l) or LIST_HEAD.match(l)), None)
    if sec is not None:
        # #改法 / #清单 段里是代码原文和清单行，不按语句认：一直留到最后一个非空行；
        # 只有段、没写主脚本时从第一个段开始（段里的代码行不能当成「第一行代码」）
        first = min(first, sec)
        last = max(i for i, l in enumerate(lines) if l.strip())
    kept = lines[first:last + 1]
    return "\n".join(kept).strip("\n"), len([l for l in lines if l.strip()]) - len([l for l in kept if l.strip()])


def split_subs(script):
    """「#子脚本 名字.zs」分出子脚本。返回 (主脚本, {名字.zs: 内容})。
    「#改法」「#清单」段不管写在哪个子脚本后面，都归到主脚本末尾（{名} 在主脚本里用）。"""
    main, subs, cur, secs, in_sec = [], {}, None, [], False
    for l in script.splitlines():
        m = re.match(r"^\s*#\s*子脚本\s+(\S+?)(?:\.zs)?\s*$", l)
        if m:
            cur, in_sec = m.group(1) + ".zs", False
            subs[cur] = []
            continue
        if EDIT_HEAD.match(l) or LIST_HEAD.match(l):
            in_sec = True
        (secs if in_sec else subs[cur] if cur else main).append(l)
    return "\n".join(main + secs), {k: "\n".join(v) for k, v in subs.items()}


def whitelist_check(script, subs, libs=LIBS, verbs=(), packs=(), only=None):
    """静态白名单：每行的语句头、动词、「设 x = 动词」右边、问 的后缀、执行 的目标。返回问题列表。
    verbs / packs：资料包额外放开的动词和 用包 可写的包名（缺省不放开，其它包行为不变）。
    only = (动词集合, 用包集合)：白名单整体由资料包给（packs.verbs_of / use_of），不再叠加 code 缺省；v2 用它。"""
    allowed = set(only[0]) if only else ALLOWED_VERBS | set(verbs)
    use_ok = tuple(only[1]) if only else ("common", "text", "code") + tuple(packs)
    split_head, KW = _heads()
    from tools.dsl_core import normalize
    probs = []
    for name, body in [("主脚本", script)] + [(f"子脚本 {k}", v) for k, v in subs.items()]:
        body, _, _, sec_probs = split_sections(body)
        probs += [f"{name}：{x}" for x in sec_probs]
        for i, raw in enumerate(body.splitlines(), 1):
            s = normalize(raw).strip()
            if not s or s.startswith("#"):
                continue
            h, rest = split_head(s)
            where = f"{name}第 {i} 行"
            if h in ALL_VERBS:
                if h not in allowed:
                    probs.append(f"{where}：动词「{h}」不在白名单里")
                continue
            if h not in ALLOWED_HEADS:
                probs.append(f"{where}：语句「{s.split()[0]}」不在白名单里" if h in set(KW.values())
                             else f"{where}：认不出的语句「{s[:40]}」（不是关键字也不是白名单动词）")
                continue
            if h == "use":
                bad = [x for x in re.split(r"[\s,，、]+", rest) if x and x not in use_ok]
                if bad:
                    probs.append(f"{where}：只能用包 {' '.join(use_ok)}，不能用 {bad}")
            if h == "set":
                _, _, val = rest.partition("=")
                sh, srest = split_head(val.strip())
                if sh in ALL_VERBS and sh not in allowed:
                    probs.append(f"{where}：动词「{sh}」不在白名单里")
                elif sh in set(KW.values()) and sh not in ("call", "compute"):
                    probs.append(f"{where}：「设 x = {val.strip().split()[0]}」不允许（右边只能是值、白名单动词、计算、执行）")
                if sh == "call":
                    rest = srest
                    h = "call"
            if h == "call":
                tgt = rest.split()[0] if rest.split() else ""
                tgt = tgt if tgt.endswith(".zs") else tgt + ".zs"
                if tgt not in libs and (not tgt.startswith("_plan/") or tgt[len("_plan/"):] not in subs):
                    probs.append(f"{where}：执行 只能调本计划里写的子脚本（_plan/名字.zs）或 {' / '.join(libs)}，没有 {tgt}")
            if h in ("ask", "ask_json"):
                if re.search(r"\s附\s+\S+", s) or re.search(r"\s带工具\s", s):
                    probs.append(f"{where}：问/问JSON 不许带「附」「带工具」")
                m = re.search(r"\s用\s+(\S+)\s*$", s)
                if m and m.group(1) not in ("平衡", "{decide_model}"):
                    probs.append(f"{where}：模型固定平衡档，不要写「用 {m.group(1)}」")
    return probs


def autoclose(script):
    """按缩进找「文件（或某个 #子脚本 段）末尾还没闭合的块」：块开头入栈、结束 出栈；
    中途某行缩进 ≤ 栈顶块开头的缩进（又不是 结束/否则）＝块在中间就没闭合 → 不动，交回模型。
    只有末尾剩下没闭合的块时，在该段末尾按缩进补上相应个数的「结束」。返回 (新脚本, 补了几个, 说明)。"""
    from tools.dsl_core import BLOCK_OPENERS, normalize, split_head
    lines = script.splitlines()
    # #改法 / #清单 段换成空行再看结构（段里的代码原文不是语句），行号不变
    bare = split_sections(script)[0].split("\n")
    sections, cur = [], [0, []]
    for i, l in enumerate(lines):
        if re.match(r"^\s*#\s*子脚本\s+\S+", l):
            sections.append(cur)
            cur = [i + 1, []]
            continue
        cur[1].append((i, bare[i] if i < len(bare) else ""))
    sections.append(cur)
    inserts, total, notes = {}, 0, []
    for start, body in sections:
        stack, bad = [], False
        last_idx = start - 1
        for i, raw in body:
            s = raw.strip()
            if not s or s.startswith("#"):
                continue
            last_idx = i
            ind = len(raw) - len(raw.lstrip())
            h, _ = split_head(normalize(s))
            if h == "end":
                if stack:
                    stack.pop()
                continue
            if h in ("else", "elif"):
                continue
            if stack and ind <= stack[-1][0]:
                bad = True
                break
            if h in BLOCK_OPENERS:
                stack.append((ind, i + 1, s.split()[0]))
        if bad or not stack:
            continue
        add = [" " * ind + "结束" for ind, _, _ in reversed(stack)]
        inserts[last_idx] = add
        total += len(add)
        notes.append("、".join(f"第 {ln} 行的「{w}」" for _, ln, w in stack))
    if not total:
        return script, 0, ""
    out = []
    for i, l in enumerate(lines):
        out.append(l)
        out.extend(inserts.get(i, []))
    return "\n".join(out), total, "；".join(notes)


# ------------------------------------------------------------ 假模型（空跑）

class _Repeat(Exception):
    pass


class _Alarm(Exception):
    pass


EDIT_FIELD = re.compile(r"edit|change|patch|修改|改法", re.I)


def _real_edit(repo, prompt, k):
    """从提示词里提到的源码文件（没有就取第一个）挑一行唯一的 def/class 行，给一条能成功应用的正常 edit。"""
    from .common import src_files
    srcs = src_files(repo)
    cands = [f for f in dict.fromkeys(re.findall(r"[\w./-]+\.py", prompt)) if f in srcs] or srcs
    for rel in cands:
        f = repo / rel
        if not f.is_file() or f.name == "__init__.py":
            continue
        txt = f.read_text(encoding="utf-8", errors="replace")
        for line in txt.splitlines():
            if re.match(r"\s*(def|class)\s", line) and txt.count(line) == 1:
                return {"file": rel, "old": line, "new": line + f"\n# 模拟修改{k}"}
    return {"file": (srcs or ["x.py"])[0], "old": "模拟原文", "new": "模拟"}


def fake_handler_factory(repo, stats):
    """假模型：枚举轮换；文本字段带调用序号（每次不同）；列表字段若名字像 edits，
    给 [一条缺 file 键的 edit, 一条正常 edit]（改文件因此整体失败，msg 每次不同）。
    同一提示词原样出现 ≥2 次 → 判计划有问题（上一轮结果没喂回 / 这一问没有新信息）。"""
    n = {"i": 0}
    seen = {}

    def handler(prompt, system=None):
        n["i"] += 1
        k = n["i"]
        seen[prompt] = seen.get(prompt, []) + [k]
        if len(seen[prompt]) >= 2:
            stats["repeat"] = True
            a, b = seen[prompt][0], seen[prompt][-1]
            raise _Repeat(f"计划有问题：第 {b} 次模型调用的提示词和第 {a} 次一字不差（空跑里假模型每次给的改法不同、改文件的 msg 也不同）。"
                          f"说明上一轮的结果——改文件失败的原因 {{res.msg}}、跑测试的摘要 {{t.summary}}——没有带进这一轮的提示词，"
                          f"或者这一问根本没有新信息。改法：每轮 设 last = 【上轮】{{res.msg}}｜{{t.summary}}，下一轮提示词里嵌 {{last}}；"
                          f"让模型给 edits 时写明字段名固定为 file、old、new。提示词开头：{prompt[:120]}")
        if prompt.startswith(("【定位】", "【读改测】")):      # 旧路径的 定位/读改测：格式说明在系统提示里，按开头标记补回来解析
            from .legacy import prompts as LP
            prompt = prompt + (LP.lib_tail(prompt) or "")
        if "输出格式：只输出一个 JSON 对象" not in prompt:
            return f"（模拟回复 {k}）"
        if LOC_MARK in prompt:
            # 定位.zs 内部的问：第 1 轮运行看看（顺带换关键词），之后读这些（给真实文件），让空跑走到「找到」的分支
            m = re.search(r"第 (\d+)/(\d+) 轮", prompt)
            i = int(m.group(1)) if m else 1
            if i == 1 and (not m or int(m.group(2)) > 1):
                return json.dumps({"action": "运行看看", "code": f"print('模拟{k}')", "kw": f"模拟关键词{k}",
                                   "reason": f"模拟文本{k}"}, ensure_ascii=False)
            ed = _real_edit(repo, prompt, k)
            return json.dumps({"action": "读这些", "segs": ed["file"], "reason": f"模拟文本{k}"}, ensure_ascii=False)
        tail = prompt.rsplit("输出格式：只输出一个 JSON 对象", 1)[1]
        obj = {}
        for name, desc in re.findall(r"^- (\w+)：(.+)$", tail, re.M):
            is_edit = desc.startswith("列表") and EDIT_FIELD.search(name)
            if "可选" in desc and k % 2 == 0 and not is_edit:
                continue
            opts = re.findall(r'"([^"]+)"', desc.split("之一")[0]) if desc.startswith("只能是") else None
            if opts:
                obj[name] = opts[(k - 1) % len(opts)]
            elif desc.startswith("数字"):
                obj[name] = 1
            elif desc.startswith("是否"):
                obj[name] = k % 2 == 1
            elif is_edit:
                obj[name] = [{"old": f"模拟原文{k}", "new": f"模拟新文{k}"}, _real_edit(repo, prompt, k)]
            elif desc.startswith("列表"):
                obj[name] = []
            else:
                obj[name] = f"print('模拟{k}')" if re.search(r"code|py|代码|script", name, re.I) else f"模拟文本{k}"
        return json.dumps(obj, ensure_ascii=False)
    return handler


def dry_run(project, work, script, subs, desc, scripts_for, model, engine_cls=None):
    """在项目的一份拷贝里（work/repo）用假模型跑一遍。返回 (问题文本或空, 假模型调用数, 输出)。
    状态目录临时切到 work/，不弄脏真跑的笔记状态。engine_cls：引擎类（缺省 AgentEngine；v2 传带测试闸门的子类）。"""
    from tools.mock import MockClient
    shutil.rmtree(work, ignore_errors=True)
    shutil.copytree(project, work / "repo", ignore=COPY_IGNORE, symlinks=True)
    plan_dir = work / "plan"
    write_subs(plan_dir, subs)
    st = {}
    mock = MockClient(handler=fake_handler_factory(work / "repo", st), offline=True)
    eng = (engine_cls or AgentEngine)(client=mock, workdir=work / "repo", verbose=False, verbs_root=PKG / "verbs",
                                      scripts=scripts_for(plan_dir, subs))
    eng.model = model
    eng.dry_run = True
    eng.vars["task"] = desc
    old_state = os.environ.get("DSLAGENT_STATE")
    os.environ["DSLAGENT_STATE"] = str(work / "state")

    def on_alarm(*_):
        raise _Alarm()
    old = signal.signal(signal.SIGALRM, on_alarm)
    signal.alarm(DRY_SECONDS)
    err = ""
    try:
        eng.run(script)
    except _Alarm:
        err = f"空跑超过 {DRY_SECONDS} 秒没跑完（循环太多或动作太慢）"
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        if st.get("repeat") and "计划有问题" in err:
            err = "重复请求——" + err[err.index("计划有问题"):]
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)
        if old_state is None:
            os.environ.pop("DSLAGENT_STATE", None)
        else:
            os.environ["DSLAGENT_STATE"] = old_state
    out = "\n".join(eng.output)
    if not err and eng.halted is None and not re.search(r"结论[:：]", out):
        err = "空跑跑完了，但没有打印「结论：…」这一行（最后要打印 结论：修好/没修好/需要更多信息）"
    return err, len(mock.calls), out


def write_subs(plan_dir, subs):
    Path(plan_dir).mkdir(parents=True, exist_ok=True)
    for k, v in subs.items():
        (Path(plan_dir) / k).write_text(v, encoding="utf-8")
