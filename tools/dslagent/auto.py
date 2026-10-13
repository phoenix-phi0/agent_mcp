"""engine=auto 的判定（cbatch 用）：这个任务交 dsl 还是 claude。不依赖 legacy/。"""
import re
from pathlib import Path

from .common import _defs, _verb_module, detect_test_cmd

# auto 判定：提示词里像「有失败的测试 / 报错栈」的说法
FAIL_SIGNAL = re.compile(r"Traceback \(most recent call last\)|失败的测试|测试[^。\n]{0,12}(失败|没过|不通过|报错)|"
                         r"failing tests?|tests? (?:fail|failed|failing)\b|^FAILED\b|^FAIL:|^ERROR: test|AssertionError",
                         re.I | re.M)

# 能力检查：任务文本里明显超出 dsl 动词能力的需求（动词只能读写项目内文件、跑项目测试、跑≤30 行不联网的只读 Python）。
# 宁可漏判（漏了还有短分类的 needs、早退回兜着），不要误判：词都写得窄，plan15–21 的场景文本上不该命中。
CAPABILITY_GAPS = [
    ("装依赖", re.compile(r"\b(?:pip3?|npm|yarn|pnpm|conda|apt(?:-get)?|brew)\s+(?:install|add|i)\b|"
                       r"安装(?:新的?|第三方)?(?:依赖|库|包|模块)|装(?:上|一?个)?(?:新的?|第三方)?(?:依赖|库|包)|"
                       r"(?:加|添加)(?:新的?|第三方)?依赖", re.I)),
    ("联网", re.compile(r"联网|上网|从网(?:上|络)|网上(?:抓|下载|查|获取)|在线(?:抓|获取|查询|拉取)|抓取网页|爬取|爬虫|"
                      r"\b(?:curl|wget)\b|https?://(?!localhost|127\.0\.0\.1)", re.I)),
    ("任意 shell 命令", re.compile(r"(?:shell|bash|sh)\s*脚本|部署脚本|\.sh\b|执行(?:这个|该)?(?:shell|bash)?\s*(?:命令|脚本)并|"
                               r"(?:并|然后)(?:执行|运行)(?:它|这个脚本|部署)|systemctl|crontab|docker\b|定时任务", re.I)),
    ("改仓库外文件", re.compile(r"仓库外|项目外|项目之外|另一个仓库|其他仓库|跨仓库|(?:两|多)个仓库|/etc/|~/\.")),
    ("浏览器/GUI", re.compile(r"浏览器|网页上点|截图|\bGUI\b|selenium|playwright", re.I)),
    ("交互式调试", re.compile(r"交互式(?:调试|地)|调试器|单步调试|断点调试|\bpdb\b|\bgdb\b", re.I)),
]


def capability_gaps(text):
    """任务文本里命中的超能力需求：["装依赖（pip install）", …]，没有就空列表。"""
    out = []
    for name, rx in CAPABILITY_GAPS:
        m = rx.search(text or "")
        if m:
            out.append(f"{name}（「{m.group(0).strip()[:20]}」）")
    return out


def test_state(project, test_cmd, timeout=120):
    """跑一次测试：{runnable, failing, rc, summary}。runnable＝确实跑到了测试（unittest「Ran N tests」N>0，
    或 pytest 的 N passed/failed/error、收集出错）；failing＝能跑且没全过。"""
    _defs()
    m = _verb_module("跑测试")
    rc, text = m.run_raw(Path(project).resolve(), test_cmd, timeout)
    ran = re.search(r"^Ran (\d+) tests?", text, re.M)
    runnable = bool(ran and int(ran.group(1)) > 0) or \
        bool(re.search(r"\b\d+ (passed|failed|errors?)\b|errors? during collection", text))
    return {"runnable": runnable, "failing": runnable and rc not in (0, None), "rc": rc,
            "summary": m.summarize(Path(project).resolve(), rc, text)["summary"]}


def decide_auto(prompt, project, test_cmd=None, timeout=120):
    """engine=auto 的判定，返回 {engine: dsl|claude, kind?: bugfix|task, reason, test_cmd, initial?, items?, needs?, uncertain?}。
    规则拿不准的两种情况（3 的「有失败没说法」、4 的「抽不出产物」）照旧给 engine=claude，另带 uncertain=bugfix|task，
    cbatch 见到它会再做一次短分类（cbatch.decide）。规则：
    0. 任务文本命中能力检查（capability_gaps：装依赖/联网/任意 shell/改仓库外文件/浏览器/交互式调试）→ claude，needs 列出命中项；
    1. 没给 project → claude（dsl 会直接改 project 里的文件，不替调用方猜目录）；
    2. 测试命令（给的或探测的）没有、跑不起来、或没跑到任何测试 → claude（dsl 两条路径都靠测试验收）；
    3. 初始有失败：给了 test_cmd 或提示词里有失败测试 / Traceback 的说法 → dsl 修 bug；没有 → claude（不像修 bug 的任务）；
    4. 初始全过：提示词里有失败测试 / Traceback 的说法 → claude（说有 bug 但测试没覆盖到，不是 dsl 能验收的）；
       否则用完成前核对的抽取器（reason.done_items）从任务文本里抽明确产物（新建/删除的路径、函数/类名、JSON 键、
       行数约束、import 等），抽到 ≥1 个 → dsl 任务路径；一个都抽不到 → claude（开放式任务）。"""
    gaps = capability_gaps(prompt)
    if gaps:
        return {"engine": "claude", "reason": "能力检查：任务需要 dsl 动词做不到的事——" + "、".join(gaps),
                "test_cmd": test_cmd, "needs": gaps}
    if not project:
        return {"engine": "claude", "reason": "没给 project", "test_cmd": test_cmd}
    hit = FAIL_SIGNAL.search(prompt or "")
    cmd = test_cmd or detect_test_cmd(project)
    if not cmd:
        return {"engine": "claude", "reason": "项目里探测不到测试（没有 tests/、test_*.py 或 pytest 配置），dsl 没法验收",
                "test_cmd": None}
    st = test_state(project, cmd, timeout)
    if not st["runnable"]:
        return {"engine": "claude", "reason": f"测试命令没跑到任何测试（{cmd}）：{st['summary'][:200]}",
                "test_cmd": cmd, "initial": st}
    if st["failing"]:
        if test_cmd or hit:
            why = "给了 test_cmd" if test_cmd else f"提示词里有「{hit.group(0)[:30]}」"
            return {"engine": "dsl", "kind": "bugfix", "reason": f"{why}，测试能跑且初始有失败 → 修 bug 路径",
                    "test_cmd": cmd, "initial": st}
        return {"engine": "claude", "reason": "初始有失败测试，但没给 test_cmd、提示词里也没有失败测试/Traceback，不像修 bug 任务",
                "test_cmd": cmd, "initial": st, "uncertain": "bugfix"}
    if hit:
        return {"engine": "claude", "reason": f"提示词里有「{hit.group(0)[:30]}」，但初始测试全过（测试没覆盖到这个问题）",
                "test_cmd": cmd, "initial": st}
    from . import reason as R
    items = R.done_items(prompt, R.all_files(project))
    if not items:
        return {"engine": "claude", "reason": "初始测试全过，任务文本里抽不出明确产物（路径/标识符/JSON 键/行数约束等），按开放式任务交 claude",
                "test_cmd": cmd, "initial": st, "items": [], "uncertain": "task"}
    desc = "；".join(_item_text(it) for it in items[:4]) + (f" 等 {len(items)} 项" if len(items) > 4 else "")
    return {"engine": "dsl", "kind": "task", "reason": f"初始测试全过，任务文本里抽到明确产物：{desc} → 任务路径",
            "test_cmd": cmd, "initial": st, "items": items}


def _item_text(it):
    k = it["kind"]
    return {"exists": lambda: f"新建 {it['path']}", "absent": lambda: f"删除 {it['path']}",
            "unchanged": lambda: f"不改 {it['path']}", "def": lambda: f"定义 {it['name']}",
            "forbid": lambda: f"{it['dir']} 下不出现 {it['name']}", "keys": lambda: f"{it['path']} 键 {','.join(it['keys'][:4])}",
            "lines": lambda: f"{it['path']} ≤{it['max']} 行", "import": lambda: f"from {it['mod']} import {it['name']}"}.get(
        k, lambda: k)()
