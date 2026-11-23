"""缩进式编排脚本动词包。用法：用包 workflow；编排执行 flow.wf。

另有三个读写项目接口约定（work/<项目>/CONTRACT.json）的动词，写在入口脚本里、编排执行前后用：
  设 contract = 读约定 work/{project}/CONTRACT.json        文件不在就是空对象 {}
  存约定 work/{project}/CONTRACT.json arch contract_notes 整项目流程
  合并约定 work/{project}/CONTRACT.json plan contract_notes 改项目流程
「存约定」「合并约定」后面写的是变量名（不带花括号），取出结构化的值原样写成 JSON。
"""
import importlib.util
import re
from pathlib import Path

from tools.dsl import current_engine
from tools.dsl_core import DSLError

PACK_DIR = Path(".")


def _load(name, file):
    spec = importlib.util.spec_from_file_location(name, PACK_DIR / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def register(reg, workspace):
    module = _load("_workflow_parser", "_workflow.py")
    agents = _load("_workflow_agents", "_agents.py")
    contract = _load("_workflow_contract", "_contract.py")

    @reg.verb("执行缩进式任务编排脚本；脚本路径相对工作目录")
    def 编排执行(脚本: str) -> str:
        engine = current_engine()
        root = engine.workdir.resolve()
        path = (root / 脚本).resolve()
        if root not in path.parents or not path.is_file():
            raise DSLError(f"编排脚本不存在或越出工作目录：{脚本}")
        return module.run(engine, path.read_text(encoding="utf-8"), agents.call_agent, name=path.stem,
                          describe=agents.describe,
                          load_format=agents.load_format,
                          check_format=agents.check_format,
                          card_info=agents.card_info)

    def var(engine, name, what, required=True):
        name = (name or "").strip()
        if name and not re.fullmatch(r"[^\W\d]\w*(?:\.\w+)*", name):
            # 写成 {arch} 会先被引擎展开成整段 JSON 再传进来：只认变量名
            raise DSLError(f"{what}后面写变量名（如 arch），不带花括号；收到的是：{name[:40]}…")
        value = engine.lookup(name) if name else None
        if value is None and required:
            raise DSLError(f"{what}的变量 {name or '（空）'} 没有值")
        return value

    @reg.verb("读项目的接口约定 CONTRACT.json；文件不在就是空对象")
    def 读约定(文件: str) -> dict:
        engine = current_engine()
        return contract.read(contract.safe_path(engine.workdir, 文件))

    @reg.verb("把架构（architecture 格式）和裁决写成项目的接口约定 CONTRACT.json；后面写变量名")
    def 存约定(文件: str, 架构: str, 裁决: str = "", 来源: str = "") -> str:
        engine = current_engine()
        arch = var(engine, 架构, "存约定")
        notes = var(engine, 裁决, "存约定", required=False) if 裁决 else []
        path = contract.safe_path(engine.workdir, 文件)
        data = contract.save(path, arch, notes or [], 来源 or "未注明", run=engine.lookup("workflow_trace"))
        return f"约定已写入 {文件}（{len(data['architecture']['modules'])} 个模块，{len(data['contract_notes'])} 条裁决）"

    @reg.verb("把改项目流程的改动方案合并进已有约定再写回；后面写变量名")
    def 合并约定(文件: str, 方案: str, 裁决: str = "", 来源: str = "") -> str:
        engine = current_engine()
        plan = var(engine, 方案, "合并约定")
        notes = var(engine, 裁决, "合并约定", required=False) if 裁决 else None
        path = contract.safe_path(engine.workdir, 文件)
        data = contract.merge(path, plan, notes, 来源 or "改项目流程", run=engine.lookup("workflow_trace"))
        warn = data.get("warnings") or []
        return (f"约定已更新 {文件}（{len(data['architecture']['modules'])} 个模块）"
                + (f"；{len(warn)} 条要人看的：" + "；".join(warn) if warn else ""))
