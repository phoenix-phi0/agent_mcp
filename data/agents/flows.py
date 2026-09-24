"""流程工具：把预写好的 DSL 脚本作为 agent 可调用的「流程」。

设计意图：
    流程写在 flows/*.zs 里，由人编辑、可版本管理。
    agent 只负责「选哪个流程、传什么参数」，不负责写脚本。
    这样改教学流程时只改文本文件，不动 Python，也不依赖模型即兴发挥。

目录约定：
    mcp/
        flows/               流程脚本（人写，只读）
        verbs/               动词包（人写，会被执行，必须不可外部写入）
        workspace/japanese/  运行时数据（进度、收集的对话、输出）

读写分离：脚本从 mcp/flows 读，流程里的「保存」「追加」写进 workspace。

脚本里用 {参数名} 引用传入的参数，跟普通变量一样。
流程里可以直接使用动词包提供的动词。

关于结果长度：
    run_flow 的返回是要完整转述给使用者的正文，所以不截断（max_result=0）。
    其他几个工具是元信息，给较小的额度。
"""

import json
import re
from pathlib import Path

from .registry import Registry

# 会在脚本内部定义变量的语句（含别名与英文名）
_DEFINING = (
    r"(?:设|设置|设定|变量|问|提问|流式|对话|读取|载入|判定"
    r"|set|ask|stream|chat|load|verdict)"
)
# 循环语句，其循环变量也是脚本内部定义的
_LOOP = r"(?:遍历|循环|每个|逐项|逐个|each|foreach)"
_IN = r"(?:于|在|属于|in)"

# 默认加载的动词包，顺序即优先级
DEFAULT_PACKS = ["common", "quiz", "japanese"]


def scan_params(script: str) -> list[str]:
    """扫描脚本里需要外部传入的参数。

    用到（{X}）但脚本内部没定义的变量才算参数。内部定义包括：
      · 设/问/流式/对话/读取/判定 等赋值语句的左值
      · 遍历/逐项 等循环语句的循环变量
    """
    used = sorted(set(re.findall(r"\{([^{}]+)\}", script)))

    defined = set(re.findall(rf"^\s*{_DEFINING}\s+(\S+?)\s*=", script, re.M))
    for m in re.finditer(rf"^\s*{_LOOP}\s+(\S+?)\s+{_IN}\s", script, re.M):
        defined.add(m.group(1))
    for m in re.finditer(rf"^\s*{_LOOP}\s+(\S+?)\s*=", script, re.M):
        defined.add(m.group(1))

    return [v.strip() for v in used if v.strip() not in defined]


def make_flow_tools(
    workspace: Path,
    client=None,
    flows_dir: Path | None = None,
    verbs_dir: Path | None = None,
    packs: list[str] | None = None,
    max_calls: int = 20,
) -> Registry:
    """把流程脚本包装成 agent 工具。

    flows_dir / verbs_dir 默认都取 mcp/ 下的同名目录，
    也就是 workspace 的上两级。workspace 只作为运行时数据目录。
    """
    reg = Registry()
    workspace = Path(workspace).resolve()

    # workspace = mcp/workspace/japanese，上两级就是 mcp/
    root = workspace.parent.parent
    flows = Path(flows_dir).resolve() if flows_dir else (root / "flows").resolve()
    verbs_root = Path(verbs_dir) if verbs_dir else root / "verbs"
    pack_names = packs if packs is not None else DEFAULT_PACKS

    flows.mkdir(parents=True, exist_ok=True)

    _cache: dict = {}

    def _verbs():
        """动词表，加载一次后缓存。改了动词包要重启或清缓存。"""
        if "reg" not in _cache:
            from tools import make_verbs
            v = make_verbs()
            v.load_packs(verbs_root, pack_names, workspace=workspace)
            _cache["reg"] = v
        return _cache["reg"]

    def _client(real: bool):
        from tools import MockClient
        if not real:
            return MockClient()
        if client is not None:
            return client
        from tools import ZhipuClient
        return ZhipuClient()

    def _read_flow(name: str) -> str:
        f = flows / (name if name.endswith(".zs") else f"{name}.zs")
        p = f.resolve()
        if p.parent != flows and flows not in p.parents:
            raise ValueError(f"路径越界：{name}")
        if not p.is_file():
            available = ", ".join(sorted(x.stem for x in flows.glob("*.zs")))
            raise FileNotFoundError(
                f"没有名为 {name} 的流程。可用：{available or '(无)'}"
            )
        return p.read_text(encoding="utf-8")

    def _needed(script: str) -> list[str]:
        """参数 = 用到但未定义的变量，再去掉动词名（动词不是变量）。"""
        v = _verbs()
        return [p for p in scan_params(script) if not v.has(p)]

    def _run(name: str, params: str, real: bool) -> str:
        from tools import DSLEngine, DSLError

        try:
            script = _read_flow(name)
        except (ValueError, FileNotFoundError) as e:
            return f"[错误] {e}"

        try:
            vars_ = json.loads(params) if params.strip() else {}
        except json.JSONDecodeError as e:
            return f"[参数不是合法 JSON] {e}。正确形式：{{\"课程\": \"動詞第1回\"}}"
        if not isinstance(vars_, dict):
            return '[参数必须是 JSON 对象，例如 {"课程": "動詞第1回"}]'

        need = _needed(script)
        missing = [p for p in need if p not in vars_]
        if missing:
            return (
                f"[缺少参数] {name} 需要：{', '.join(need)}；"
                f"这次没传：{', '.join(missing)}"
            )

        heavy = sum(
            1 for ln in script.splitlines()
            if ln.strip().startswith(
                ("问", "流式", "对话", "判定", "ask", "stream", "chat", "verdict")
            )
        )
        if heavy > max_calls:
            return f"[已拒绝] 流程含约 {heavy} 处模型调用，超过上限 {max_calls}。"

        c = _client(real)
        engine = DSLEngine(
            c, workdir=workspace, verbose=False, verbs=_verbs()
        )
        engine.vars.update({k: str(v) for k, v in vars_.items()})

        try:
            out = engine.run(script)
        except DSLError as e:
            return f"[流程出错] {e}"
        except Exception as e:
            return f"[执行失败] {type(e).__name__}: {e}"

        used = len(getattr(c, "calls", []))
        tail = f"\n[模型调用 {used} 次]" if used else ""
        return (out or "(无输出)") + tail

    # ------------------------------------------------------------------

    @reg.tool(
        "列出所有可用的流程、说明和各自需要的参数。",
        max_result=800,
    )
    def list_flows() -> str:
        items = []
        for f in sorted(flows.glob("*.zs")):
            script = f.read_text(encoding="utf-8")
            first = ""
            for line in script.splitlines():
                if line.strip().startswith("#"):
                    first = line.strip().lstrip("#").strip()
                    break
            need = _needed(script)
            items.append(
                f"  {f.stem} — {first or '(无说明)'}｜参数：{', '.join(need) or '无'}"
            )
        if not items:
            return f"可用流程：\n  (无)\n[目录] {flows}"
        return "可用流程：\n" + "\n".join(items)

    @reg.tool(
        "查看某个流程的脚本内容和它需要哪些参数。"
        "只想知道参数名的话，list_flows 里已经带了，不必调这个。",
        max_result=1500,
        name="流程名，不含 .zs 后缀",
    )
    def show_flow(name: str) -> str:
        try:
            script = _read_flow(name)
        except (ValueError, FileNotFoundError) as e:
            return f"[错误] {e}"
        return f"{script}\n---\n需要传入的参数：{', '.join(_needed(script)) or '(无)'}"

    @reg.tool(
        "执行一个预定义流程，返回完整结果。"
        "结果通常是要呈现给使用者的正文，请完整转述，不要只做摘要。",
        max_result=0,          # 不截断：正文要完整交给使用者
        name="流程名，不含 .zs 后缀",
        params='JSON 对象形式的参数，例如 {"课程": "動詞第1回", "级别": "N5"}',
    )
    def run_flow(name: str, params: str = "{}") -> str:
        return _run(name, params, real=True)

    @reg.tool(
        "试跑一个流程，用假客户端，只检查参数是否齐全、脚本是否报错，不消耗额度。",
        max_result=1000,
        name="流程名",
        params="JSON 对象形式的参数",
    )
    def check_flow(name: str, params: str = "{}") -> str:
        return _run(name, params, real=False)

    @reg.tool(
        "列出流程脚本里可以使用的动词及其参数，按包分组。",
        max_result=1000,
    )
    def list_verbs() -> str:
        v = _verbs()
        out = f"已加载的包：{', '.join(v.packs) or '(无)'}\n\n" + v.describe()
        if v.warnings:
            out += "\n\n[警告]\n" + "\n".join("  " + w for w in v.warnings)
        return out

    return reg
