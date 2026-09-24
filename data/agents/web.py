"""网页生成 agent（WEB-G01）。

跟日语教师同一套装配方式，两处不同：

1. workspace 就是 data/。生成物要落在 data/web/<项目>/ 下，
   那是唯一对外可写、且不在 sys.path 里的目录——生成的代码再脏也
   只是文本，要跑得人手动挪出去。
2. flows_dir 必须显式传。make_flow_tools 默认取 workspace 的上两级
   （workspace/japanese → mcp/），而这里 workspace 是 data/，
   上两级会跑到项目根外面去。

工具按批次放开（见 批次 字典）。第一批只给三个只读 + 执行的工具，
agent 还不能自己写脚本，build.zs 由人放进去。这样能单独验证引擎那条
路径通不通，不掺杂模型写脚本的变量。

用法：

    from agents.web import make_builder

    b = make_builder()                 # 第一批
    b = make_builder(批次="二")        # 放开写文件
"""

from pathlib import Path

from .base import Agent
from .builtin import make_file_tools
from .flows import make_flow_tools
from .registry import Registry

ROOT = Path(__file__).resolve().parent.parent
SOUL_PATH = ROOT / "agents" / "souls" / "WEB-G01.md"
WORKSPACE = ROOT / "data"
FLOWS = ROOT / "flows"
VERBS = ROOT / "verbs"

# 动词包：web 包提供建页面/建接口等，common 提供算术和取字段
PACKS = ["common", "web"]

# 逐批放开工具。理由见模块开头。
批次 = {
    "一": ["list_verbs", "check_flow", "run_flow"],
    "二": ["list_verbs", "check_flow", "run_flow",
           "read_file", "write_file", "list_dir"],
    "三": ["list_verbs", "check_flow", "run_flow",
           "read_file", "write_file", "list_dir",
           "list_flows", "show_flow"],
}

RUNTIME_NOTE = """## 运行期说明

**产物一律经由脚本写出，你不要直接写产物文件。**
你可以 write_file 的只有 build.zs 这一类脚本；.js / .py / .html
由脚本里的「保存」语句生成。如果你发现自己在手写 HTML，说明走错路了。

**空跑必做。** check_flow 用假客户端，「问」返回 [模拟回复] 前缀的占位
文本，能验证变量插值和保存路径，不消耗额度。空跑不过就不要 run_flow。

**动词名写错不会报错。** 未注册的动词会原样透传，
`设 页面 = 建页面 /about About {标题} {正文}` 会得到字面字符串
「建页面 /about About ...」并被当成页面内容保存下去。所以：
- 写脚本前先 list_verbs 确认动词名和参数个数；
- 空跑后检查输出里有没有中文动词名残留，有就是名字写错了。

**动词参数按位置绑定，值里不能有空格。** 标题、正文这类内容必然含空格，
必须先用「设」存进变量再以 {变量} 传入：

    设 标题 = 关于我们
    问 正文 = 用两句话介绍一家做户外装备的小公司
    设 页面 = 建页面 /about About {标题} {正文}
    保存 web/blog/frontend/pages/About.js {页面}

**所有保存路径都在 web/<项目名>/ 下**，不要用 ../。

**run_flow 返回的正文会完整呈现给使用者，不要复述。**
你的回复只写生成了什么、怎么跑起来、哪些是占位数据。
"""


def 只留(reg: Registry, 名字: list[str]) -> Registry:
    """从注册表里挑出指定的几个工具，返回新表。

    Registry 只有 schemas(only=...) 能限定给模型看的子集，但 call()
    仍然什么都能调，不算真的收窄。这里直接建一张新表。
    """
    新 = Registry(max_result=reg.default_max_result)
    缺 = [n for n in 名字 if n not in reg.names()]
    if 缺:
        raise KeyError(f"注册表里没有这些工具：{', '.join(缺)}")
    for n in 名字:
        新._fns[n] = reg._fns[n]
        新._schemas[n] = reg._schemas[n]
        新._limits[n] = reg._limits[n]
        新._hints[n] = reg._hints[n]
    return 新


def make_builder(
    client=None,
    workspace: Path | str = WORKSPACE,
    soul: Path | str = SOUL_PATH,
    批次名: str = "一",
    verbose: bool = False,
) -> Agent:
    """组装网页生成 agent。"""
    workspace = Path(workspace)
    if 批次名 not in 批次:
        raise KeyError(f"没有批次「{批次名}」，可用：{', '.join(批次)}")

    全部: Registry = make_file_tools(workspace)

    # 先建一个空客户端占位的 agent 拿不到 client，所以流程工具这里先不并入，
    # 跟 japanese.py 一样等 agent 建好后再 merge。
    agent = Agent(
        soul=soul,
        workspace=workspace,
        tools=Registry(),
        client=client,
        extra_system=RUNTIME_NOTE,
        max_rounds=10,
        verbose=verbose,
    )

    全部.merge(make_flow_tools(
        workspace,
        client=agent.client,
        flows_dir=FLOWS,      # 必须显式传，理由见模块开头
        verbs_dir=VERBS,
        packs=PACKS,
    ))

    agent.tools = 只留(全部, 批次[批次名])
    agent.messages[0]["content"] = agent.system_prompt
    return agent


def init_workspace(workspace: Path | str = WORKSPACE) -> str:
    """建好生成物的根目录。"""
    ws = Path(workspace)
    (ws / "web").mkdir(parents=True, exist_ok=True)
    return f"工作目录已就绪：{ws / 'web'}"


if __name__ == "__main__":
    print(init_workspace())
    b = make_builder(verbose=True)
    print(b.dump_state())
