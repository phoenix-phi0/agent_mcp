"""日语教师 agent（JP-E01-π）。

目录结构：

    mcp/
        flows/*.zs                           教学流程（人写，只读）
        verbs/                               动词包（人写，会被执行）
        agents/souls/JP-E01-pi.md            身份与教学原则
        workspace/japanese/                  运行时数据
            memory/<learner_id>/progress.json    学习者进度
            content/SERIES.md                    系列索引
            content/n2n3/                        课文
            content/n2n3/题库/                   按课分文件的 jsonl
            japanese_training_data.jsonl         对话收集

用法：

    from agents.japanese import make_teacher

    teacher = make_teacher()
    print(teacher.send("你好"))
    print(teacher.send("是"))            # 确认默认学习者 φ-0
"""

from pathlib import Path

from .base import Agent
from .builtin import make_file_tools
from .flows import make_flow_tools
from .registry import Registry

# agents/ 的上一级就是项目根 mcp/
ROOT = Path(__file__).resolve().parent.parent
SOUL_PATH = ROOT / "agents" / "souls" / "JP-E01-pi.md"
WORKSPACE = ROOT / "workspace" / "japanese"

# 补充给模型的运行期说明，SOUL.md 里没有的部分放这里
RUNTIME_NOTE = """## 运行期说明
- 今天的日期由用户或系统告知；若未告知，写入时用 `unknown` 占位，不要编造。
- 写 progress.json 前先 read_file 取回原内容，在其基础上修改后整体 write_file，
  不要凭记忆重写，以免丢字段。同一轮里刚读过就直接用，不必重读。
- japanese_training_data.jsonl 必须用 append_file 追加，不能用 write_file，
  否则会覆盖历史数据。
- 追加前先用 jsonl_contains 检查 conversation_id 是否已存在，存在则跳过。
- 文件较长时用 read_file 的 start_line / end_line 分段读，不要整个读进来。

## 课程 ID
当前教材是「N2N3 核心词汇」，课程 ID 就是课文的文件名，只有这 12 个：

    doushi_01  doushi_02  doushi_03  doushi_04         動詞
    fukushi_01  fukushi_02  fukushi_03                 副詞
    keiyoshi_01  keiyoshi_02  keiyoshi_03  keiyoshi_04 形容詞
    onomatope_01                                       オノマトペ

**所有流程的「课程」参数都用这个 ID，不要用中文课名。**
学习者说「第2回」「て形」这类说法时，先对照上面的列表确认对应哪个 ID；
对不上就直接问学习者，或读 content/n2n3/INDEX.md，不要猜一个名字去调流程。

题号形如 `doushi_02-05-意味`，由挑题时返回，批改和复习都用它。

## 教学流程（用预写好的流程实现，不要自己凭空生成教学内容）
教学动作都通过 run_flow 调用。下面已经列出每个流程的名字和参数，
**直接调用即可，不需要先 list_flows 或 show_flow**——那两个工具只在
调用报错、或你怀疑流程有变动时才用。

- 讲解一课    run_flow("讲解", {"课程": "doushi_02"})
- 出练习题    run_flow("出题", {"课程": "doushi_02", "数量": "3", "考点": "词义"})
- 批改答案    run_flow("批改", {"题号": "doushi_02-05-意味", "学生作答": "C"})
- 复习错题    run_flow("复习", {"题号": "doushi_02-05-意味", "级别": "N2"})
- 词汇讲解    run_flow("词汇扩展", {"词表": "教わる，習う", "级别": "N2"})

考点只有两种：`词义`（选择题）和 `汉字书写`（填空题）。不填则不限。
参数值都用字符串。多个值的参数（词表、题号）用逗号分隔写在一个字符串里。

**流程调用失败时不要反复翻目录。** 看报错说的缺什么、路径不对在哪，
直接改参数重试一次；再不行就问学习者，或读 content/n2n3/INDEX.md。

**run_flow 返回的正文会自动完整呈现给学习者，你不要重复它。**
你的回复只写一两句衔接或引导就够了，例如「看完告诉我，我出几道题检验」
或「哪个词觉得难记，说一声我们单独看」。
不要复述、总结或改写正文内容——那会让学习者看到两遍。

出题和批改是两步：先 run_flow("出题") 拿到题目和题号，等学习者作答后再
run_flow("批改")。出题时不要把答案一起给出去——题库里的答案只有批改时才取。

自由对话（/chat）不调流程，这时正常回应即可。

## 反馈原则
肯定要针对具体表现——答对了哪道题、哪个词掌握了。学习者只是表达了
学习意愿、还没有任何作答时，不要说「你的学习态度很好」这类空泛的夸奖。
"""


def make_teacher(
    client=None,
    workspace: Path | str = WORKSPACE,
    soul: Path | str = SOUL_PATH,
    verbose: bool = False,
    with_flows: bool = True,
) -> Agent:
    """组装日语教师 agent。"""
    workspace = Path(workspace)
    tools: Registry = make_file_tools(workspace)

    agent = Agent(
        soul=soul,
        workspace=workspace,
        tools=tools,
        client=client,
        extra_system=RUNTIME_NOTE,
        max_rounds=10,
        verbose=verbose,
    )

    if with_flows:
        # 流程工具共用 agent 的客户端，避免重复读配置、重复建连接
        tools.merge(make_flow_tools(workspace, client=agent.client))
        # 工具表变了，系统提示词要重新生成
        agent.messages[0]["content"] = agent.system_prompt

    return agent


def init_workspace(workspace: Path | str = WORKSPACE) -> str:
    """建好运行时目录骨架。

    只建空目录，不写任何示例内容——教材由 tools/build_content.py 生成，
    示例数据会误导模型（曾经的 content/verb/INDEX.md 就让它按中文课名
    去调流程，撞满了轮数上限）。

    flows 和 verbs 不在这里建——它们是人维护的源文件，位于 mcp/ 下。
    """
    ws = Path(workspace)
    (ws / "memory").mkdir(parents=True, exist_ok=True)
    (ws / "content").mkdir(parents=True, exist_ok=True)

    content = ws / "content"
    if not (content / "SERIES.md").is_file():
        return (
            f"工作目录已就绪：{ws}\n"
            f"但 {content} 下没有教材，先跑：\n"
            f"  py tools/build_content.py <教材目录> {content}"
        )

    return f"工作目录已就绪：{ws}"


if __name__ == "__main__":
    print(init_workspace())
    t = make_teacher(verbose=True)
    print(t.dump_state())
