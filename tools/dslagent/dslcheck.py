"""tool 模式（DSLAGENT_SUBTASK=tool）用的 DSL 检查 / 空跑辅助：dslmcp 每次工具调用前用。

- env_mode()：读环境变量 DSLAGENT_SUBTASK（json 缺省 / tool；cbatch 的 dsl_options.subtask 提交时校验后设成它）；check_mode：取值检查。
- check(text, first)：语法 + 白名单（用包 设 如果/否则如果/否则/结束 终止 打印；动词只许 改文件 写文件 搜索代码 读片段 查引用）。
- check_call(text, first)：工具调用版，在 check 之上再禁 终止。
- dry_run(engine, script, vars_)：在项目拷贝里空跑，改文件 / 写文件 没套上算问题。
- clip / record_reads：输出截断、记读 / 搜 / 查动词的结果。
"""
import os
import re
import shutil
import tempfile
from pathlib import Path

from tools.dsl_core import KEYWORDS, ScriptReturn, normalize, split_head, to_text
from tools.dsl_sections import split_sections

MODE_ENV = "DSLAGENT_SUBTASK"
SCRIPT_VERBS = ("改文件", "写文件", "搜索代码", "读片段", "查引用")
SCRIPT_HEADS = {"use", "set", "if", "elif", "else", "end", "halt", "print"}
READ_ONLY_HEADS = {"use", "set", "print"}
HEAD_NAMES = {"use": "用包", "set": "设", "if": "如果", "elif": "否则如果", "else": "否则", "end": "结束", "halt": "终止", "print": "打印"}
HEAD_ORDER = ("use", "set", "if", "elif", "else", "end", "halt", "print")
BANNED = ("派任务", "并行派任务")
ROUND_OUT = 6000
READ_VERBS = ("读片段", "搜索代码", "查引用")      # 读 / 搜 / 查三个动词；规划挂的只读工具也只许这三个
EDIT_VERBS = ("改文件", "写文件")


def _all_verbs():
    from . import plan as DP
    return DP.ALL_VERBS


MODES = ("json", "tool")


def check_mode(value):
    """dsl_options.subtask / DSLAGENT_SUBTASK 的取值检查（空 = json）；不认识报 ValueError。返回规范化后的取值。"""
    v = (value or "").strip().lower() or MODES[0]
    if v not in MODES:
        raise ValueError(f"子任务方式只能是 {' / '.join(MODES)}，收到：{value!r}")
    return v


def env_mode():
    v = (os.environ.get(MODE_ENV) or "").strip().lower()
    return v if v == "tool" else "json"


def check(text, first=True, verbs=SCRIPT_VERBS, heads=SCRIPT_HEADS):
    """语法 + 白名单。first=False 是后面几轮的段（不要求以 用包 开头）。verbs / heads：允许的动词 / 语句头（只读工具传 READ_ONLY_*）。
    返回 (整理后的脚本, 问题列表)。"""
    from . import plan as DP
    script, _ = DP.strip_prose(to_text(text))
    script, _, _ = DP.autoclose(script)
    if not script.strip():
        return script, ["脚本是空的"]
    probs = []
    if re.search(r"^\s*#\s*子脚本", script, re.M):
        probs.append("不能写 #子脚本 段")
    body, _, _, sec_probs = split_sections(script)
    probs += [f"#改法 段：{p}" for p in sec_probs]
    kw = set(KEYWORDS.values())
    depth = 0
    first_line = True
    for i, raw in enumerate(body.splitlines(), 1):
        s = normalize(raw).strip()
        if not s or s.startswith("#"):
            continue
        h, rest = split_head(s)
        where = f"第 {i} 行"
        if first_line:
            first_line = False
            if first and h != "use":
                probs.append(f"{where}：第一行要写 用包 common text code")
        if h in BANNED or (h == "set" and split_head(rest.partition("=")[2].strip())[0] in BANNED):
            probs.append(f"{where}：脚本子任务不能再 派任务 / 并行派任务")
            continue
        if h == "跑测试" or (h == "set" and split_head(rest.partition("=")[2].strip())[0] == "跑测试"):
            probs.append(f"{where}：「跑测试」不在白名单里（子任务不跑测试，由上层验收统一跑；只许 {'、'.join(verbs)}）")
            continue
        if h == "call" or h == "call_bg":
            probs.append(f"{where}：脚本子任务不能用 执行")
            continue
        if h not in kw:
            if h not in verbs:
                probs.append(f"{where}：认不出的语句或白名单外的动词「{s[:40]}」（只许 {'、'.join(verbs)}）")
            continue
        if h not in heads:
            probs.append(f"{where}：语句「{s.split()[0]}」不在白名单里（只许 {' '.join(HEAD_NAMES[x] for x in HEAD_ORDER if x in heads)}）")
            continue
        if h == "use":
            bad = [x for x in re.split(r"[\s,，、]+", rest) if x and x not in ("common", "text", "code")]
            if bad:
                probs.append(f"{where}：只能用包 common text code，不能用 {bad}")
        elif h == "set":
            name, sep, val = rest.partition("=")
            sh, _ = split_head(val.strip())
            if not sep:
                probs.append(f"{where}：设 的写法是 设 名字 = 值")
            elif sh in kw:
                probs.append(f"{where}：「设 x = {val.strip().split()[0]}」不允许（右边只能是值或白名单动词）")
            elif verbs != SCRIPT_VERBS and sh in _all_verbs() and sh not in verbs:
                probs.append(f"{where}：动词「{sh}」不在白名单里（只许 {'、'.join(verbs)}）")
        elif h == "if":
            depth += 1
        elif h in ("elif", "else"):
            if depth == 0:
                probs.append(f"{where}：「{s.split()[0]}」前面没有 如果")
        elif h == "end":
            depth -= 1
            if depth < 0:
                probs.append(f"{where}：多了一个 结束")
                depth = 0
    if depth > 0:
        probs.append(f"有 {depth} 个 如果 没写 结束")
    return script, probs


def edit_problems(project, script):
    """计划里写死的 #改法 段对着真实文件核对（只读）：文件在不在、old 出现几次（报行号）、@@ 新建 的文件已存在。
    复用 改文件 的匹配代码，按它实际的顺序套用方式在内存里模拟；主体一起交过去，段被用之前已 删文件 的路径按不存在算、
    只给 写文件 用的段允许覆盖。返回问题文本列表。"""
    from .common import _verb_module
    body, secs, _, _ = split_sections(script)
    if not secs:
        return []
    return _verb_module("改文件").核对计划(project, secs, body)


def _dry_cls(base):
    class DryEngine(base):
        """空跑：改文件 / 写文件 没套上的记下来。"""
        edit_fails = None

        def _do_verb(self, name, rest, lineno, assign_to=None):
            out = super()._do_verb(name, rest, lineno, assign_to)
            if name in EDIT_VERBS and assign_to:
                v = self.vars.get(assign_to)
                if isinstance(v, dict) and v.get("ok") != "是":
                    self.edit_fails.append(f"第 {lineno + 1} 行 {name} 没套上：{to_text(v.get('msg'))[:600]}")
            return out
    return DryEngine


def dry_run(engine, script, vars_=None):
    """在项目的一份拷贝里跑一遍。返回问题文本（空＝没问题）。"""
    from tools.mock import MockClient

    from . import plan as DP
    from .engine import AgentEngine
    work = Path(tempfile.mkdtemp(prefix="dsl_check_"))
    try:
        repo = work / "repo"
        shutil.copytree(engine.workdir, repo, ignore=DP.COPY_IGNORE, symlinks=True)
        eng = _dry_cls(AgentEngine)(client=MockClient(default="（空跑不调模型）", offline=True), workdir=repo,
                                    verbose=False, verbs_root=engine.verbs_root)
        eng.edit_fails = []
        eng.vars.update(vars_ or {})
        eng.dry_run = True
        try:
            eng.run("用包 common text code")      # 后面几轮的段不再写 用包
            eng.run(script)
        except ScriptReturn:
            return "脚本里不能用 返回"
        except Exception as e:  # noqa: BLE001
            return f"空跑报错：{type(e).__name__}: {str(e)[:600]}"
        if eng.edit_fails:
            return "空跑时改法没套上（原文要从入参一字不差抄、不带行号前缀、在文件里唯一）：" + "；".join(eng.edit_fails[:4])
        return ""
    finally:
        shutil.rmtree(work, ignore_errors=True)


def clip(text, n=ROUND_OUT):
    text = to_text(text)
    return text if len(text) <= n else text[:n] + f"\n…（超过 {n} 字，后面截掉了）"


def record_reads(sub, rec):
    """子引擎每个读 / 搜 / 查动词的结果、改文件没套上的报错，记进 rec（本轮输出的一部分）。"""
    orig = sub._do_verb

    def wrapped(name, rest, lineno, assign_to=None):
        out = orig(name, rest, lineno, assign_to)
        if name in READ_VERBS + EDIT_VERBS:
            v = sub.vars.get(assign_to) if assign_to else sub._last_result
            if name in EDIT_VERBS:
                if isinstance(v, dict) and v.get("ok") != "是":
                    rec.append(f"[{name} 没套上] {to_text(v.get('msg'))[:800]}")
            else:
                rec.append(f"[{name} {rest.strip()[:80]}]\n{to_text(v.get('text') if isinstance(v, dict) and 'text' in v else v)}")
        return out
    sub._do_verb = wrapped


def check_call(text, first, readonly=False):
    """语法 + 白名单（工具版：不许 终止）。readonly：规划挂的只读工具，只许 读片段 / 搜索代码 / 查引用 + 用包 设 打印，不许 #改法 段。
    返回 (脚本, 问题列表)。"""
    if readonly:
        script, probs = check(text, first=first, verbs=READ_VERBS, heads=READ_ONLY_HEADS)
        if re.search(r"^\s*#\s*改法|^\s*@@\s*(改|新建)", text or "", re.M):
            probs.append("只读工具：不能写 #改法 / @@ 改 / @@ 新建")
        return script, probs
    script, probs = check(text, first=first)
    body = script.split("\n#改法", 1)[0]
    for i, raw in enumerate(body.splitlines(), 1):
        s = normalize(raw).strip()
        if not s or s.startswith("#"):
            continue
        h, rest = split_head(s)
        if h == "halt" or (h == "set" and split_head(rest.partition("=")[2].strip())[0] == "halt"):
            probs.append(f"第 {i} 行：技能里不能写 终止（最终回复用 JSON）")
    return script, probs
