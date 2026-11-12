"""缩进式编排脚本动词包。用法：用包 workflow；编排执行 flow.wf。"""
import importlib.util
from pathlib import Path

from tools.dsl import current_engine
from tools.dsl_core import DSLError

PACK_DIR = Path(".")


def register(reg, workspace):
    spec = importlib.util.spec_from_file_location("_workflow_parser", PACK_DIR / "_workflow.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    agent_spec = importlib.util.spec_from_file_location("_workflow_agents", PACK_DIR / "_agents.py")
    agents = importlib.util.module_from_spec(agent_spec)
    agent_spec.loader.exec_module(agents)

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
