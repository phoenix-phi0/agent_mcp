"""改需求 <节号> <内容>：改需求文件里对应那一节的正文，并在文末「变更记录」追加（日期、计划序号、节号、一句话）。
节号不存在 终止 失败。需求文件路径取 ctx.req_path（没有就 终止 失败——改需求必须知道写回哪个文件）。
计划序号取当前最新一份 plan/changes/<序号>.zs（修改.zs 流程里这一步正在执行的就是它）。
内容里的 \\n（两个字符）当换行解码，多段正文；内容本身不能有 ASCII 空格（DSL 调用一行按空格分词，要空格用中文标点）。
例如 改需求 3 新增退出按钮，放在页面底部
"""
import sys
import time
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def _plan_no(project):
    from tools.dslagent.v3 import change_plan as CP
    p = CP.latest_plan_path(project)
    return p.stem if p else "?"


def _find_section(lines, sec, SECTION_RE):
    start, end = None, len(lines)
    for i, l in enumerate(lines):
        m = SECTION_RE.match(l.strip())
        if not m:
            continue
        num = m.group(1)
        if start is None:
            if num == sec:
                start = i
            continue
        if not (num == sec or num.startswith(sec + ".")):
            end = i
            break
    return start, end


def 改需求(节号: str, 内容: str) -> dict:
    sys.path.insert(0, str(Path(__file__).parent))
    import _v3ctx as X
    from tools.dslagent.v3 import change_plan as CP
    c = X.ctx()
    sec = (节号 or "").strip()
    if not c.req_path:
        X.fail("修改计划里有「改需求」，但没有需求文件路径（ctx.req_path 没设置）")
    rp = Path(c.req_path)
    text = rp.read_text(encoding="utf-8") if rp.is_file() else ""
    lines = text.replace("\r\n", "\n").split("\n")
    start, end = _find_section(lines, sec, CP.SECTION_RE)
    if start is None:
        X.fail(f"需求文件里找不到第 {sec} 节")
    body = (内容 or "").replace("\\n", "\n").rstrip("\n")
    new_lines = lines[:start + 1] + ([body] if body else []) + lines[end:]
    new_text = "\n".join(new_lines).rstrip("\n")
    date = time.strftime("%Y-%m-%d")
    plan_no = _plan_no(c.project)
    summary = (内容 or "").replace("\\n", " ").strip()[:60]
    if "## 变更记录" not in new_text:
        new_text += "\n\n## 变更记录"
    new_text += f"\n- {date} 计划 {plan_no}：改第 {sec} 节 — {summary}\n"
    rp.write_text(new_text, encoding="utf-8", newline="\n")
    c.log("修改计划", 事件="改需求", 节=sec, 路径=str(rp))
    return {"节": sec}
