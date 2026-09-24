# -*- coding: utf-8 -*-
"""app2 的 HTTP 层：接口 + 静态挂载。

沿用旧版 agents/serve.py 的全部逻辑，只换两处：
  1. 界面不再是 PAGE 那个 HTML 常量，而是 build.py 从 ui/main.ui 生成的
     web/ 目录，这里静态挂出去。
  2. 接口返回换成前端约定的格式，旧版是每个接口各返回各的字段、前端 JS
     里逐个判断。

练习模式的状态机、动词直调、模块重载一个字没改——它们跟界面无关，重写
只会引入新 bug。

接口返回格式（五个字段都可选）：

    stream    messages 进哪条消息流；有多条流时必须给
    messages  追加的消息，[{"who":…, "text":…, "kind":…, "calls":[…]}]
    state     合并进跨界面状态（「共享」字段、「显示」节点、浮层的「当」读这里）
    rows      替换列表数据
    overlay   控制浮层开关：给浮层名打开，给 null 关闭，不给则保持原状

kind 决定消息配色：user / ok / no / pending，缺省是普通样式。
calls 有值时渲染成折叠面板。

**不要回显用户自己说的话。** .ui 里 send 标了「回显」，前端在发请求之前
就已经把输入插进消息流了——后端再回一条一模一样的，界面上会出现两条。

练习题走浮层，不进消息流。浮层两态靠 state.verdict 区分：

    verdict 为空   答题态：显示题干和输入框
    verdict 有值   批改态：显示批改结果和「下一题」

所以 drill_next 要把 verdict 清空，drill_answer 要把它填上。忘了清空的话
下一题弹出来还是批改态，输入框不见了。
"""

import os
import sys
import traceback
from pathlib import Path

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

DATA_DIR = Path(os.environ.get("JP_DATA_DIR", BASE))
WORKSPACE = DATA_DIR / "workspace" / "japanese"
BANK = "content/n2n3/题库"
WEB = HERE / "web"

# learner_id -> Agent
_agents: dict = {}
# learner_id -> 练习状态
_drills: dict = {}


def _teacher(learner: str):
    from agents.japanese import make_teacher, init_workspace
    if learner not in _agents:
        init_workspace()
        _agents[learner] = make_teacher()
    return _agents[learner]


def _verbs():
    """动词表，用于练习模式直接调题库动词。"""
    from tools import make_verbs
    if "reg" not in _verbs.__dict__:
        reg = make_verbs()
        reg.load_packs(DATA_DIR / "verbs", ["common", "quiz", "japanese"],
                       workspace=WORKSPACE)
        _verbs.reg = reg
    return _verbs.reg


def call_verb(name: str, *args) -> str:
    """直接调一个动词，不经过 DSL 引擎。"""
    v = _verbs()
    if not v.has(name):
        return f"[没有动词] {name}"
    params = v.bind(name, [str(a) for a in args])
    kind, impl = v.resolve(name)
    if kind != "python":
        return f"[{name} 不是 Python 动词]"
    return str(impl(**params))


def _reload():
    """清掉模块缓存，让改过的代码生效。"""
    for name in [n for n in list(sys.modules) if n.startswith(("agents", "tools"))]:
        if not name.startswith("app2"):
            del sys.modules[name]
    _agents.clear()
    _verbs.__dict__.pop("reg", None)


def _learner(d: dict) -> str:
    """学习者 ID 是「共享」字段，在 form 里跟别的字段并列。"""
    form = d.get("form") or {}
    return (form.get("learner") or "φ-0").strip() or "φ-0"


def _field(d: dict, name: str, default: str = "") -> str:
    return ((d.get("form") or {}).get(name) or default).strip()


# ----------------------------------------------------------------------
# 练习模式：出题 → 等答 → 判题 → 下一题
#
# 为什么不走 agent：出题只需要课程 ID，判题只需要题号和作答，两步都跟
# 对话历史无关。让模型参与既慢又可能判错，还要为每轮重发全部历史。
# ----------------------------------------------------------------------


def _stat(st: dict) -> str:
    if not st["总"]:
        return f"{st['课程']}　尚未作答"
    比例 = call_verb("算比例", st["对"], st["总"])
    return f"{st['课程']}　{st['对']}/{st['总']}（{比例}%）"


def _notice(text: str, kind: str = "") -> dict:
    """提示类消息进消息流，不弹浮层。"""
    msg = {"who": "系统", "text": text}
    if kind:
        msg["kind"] = kind
    return {"stream": "drill", "messages": [msg]}


def drill_start(learner: str, 课程: str, 考点: str = "") -> dict:
    # 「全部考点」是下拉里的占位项，对动词来说等于不筛选
    if 考点 == "全部考点":
        考点 = ""
    _drills[learner] = {"课程": 课程, "考点": 考点,
                        "题号": "", "对": 0, "总": 0, "错题": []}
    return drill_next(learner)


def drill_next(learner: str) -> dict:
    """出下一题，弹浮层并回到答题态。"""
    st = _drills.get(learner)
    if not st:
        return _notice("还没开始练习，先选课程再点「开始练习」", "no")

    题号 = call_verb("挑题号", BANK, "1", st["课程"], st["考点"])
    if not 题号 or 题号.startswith("["):
        r = _notice(f"没有匹配的题目：课程={st['课程']} "
                    f"考点={st['考点'] or '不限'}", "no")
        r["overlay"] = None
        return r

    st["题号"] = 题号
    return {
        "overlay": "题目",
        # verdict 清空 = 回到答题态，输入框重新出现
        "state": {"question": call_verb("取题", BANK, 题号),
                  "verdict": "", "stat": _stat(st)},
    }


def drill_answer(learner: str, 作答: str) -> dict:
    """判一道题。结果留在浮层里，不进消息流。"""
    st = _drills.get(learner)
    if not st or not st["题号"]:
        return _notice("当前没有待答的题", "no")

    结果 = call_verb("判题", BANK, st["题号"], 作答)
    对了 = 结果.startswith("○")

    st["总"] += 1
    if 对了:
        st["对"] += 1
    else:
        st["错题"].append(st["题号"])
    st["题号"] = ""

    # 不给 overlay，浮层保持打开；verdict 有值 = 切到批改态
    return {"state": {"verdict": 结果, "stat": _stat(st)}}


def drill_stop(learner: str) -> dict:
    """结束练习，关浮层，结算进消息流。"""
    st = _drills.pop(learner, None)
    if not st:
        r = _notice("本来就没在练习")
        r["overlay"] = None
        return r

    if not st["总"]:
        r = _notice("练习结束，没有作答记录")
        r["overlay"] = None
        r["state"] = {"stat": "", "question": "", "verdict": ""}
        return r

    比例 = call_verb("算比例", st["对"], st["总"])
    错 = "，".join(st["错题"]) if st["错题"] else "无"
    r = _notice(f"练习结束：{st['对']}/{st['总']}（{比例}%）\n错题：{错}", "ok")
    r["overlay"] = None
    r["state"] = {"stat": "", "question": "", "verdict": ""}
    return r


# ----------------------------------------------------------------------
# 路由
# ----------------------------------------------------------------------


def _fail(exc: str) -> JSONResponse:
    return JSONResponse({"messages": [{"who": "出错", "text": exc, "kind": "no"}]})


async def chat(request):
    """「动作 send 提交 远程 回显 清空 发送」打到这。

    不回传用户说的那句：前端标了「回显」，发请求之前就已经插进消息流了。
    """
    try:
        d = await request.json()
        message = _field(d, "message")
        if not message:
            return JSONResponse({"stream": "chat",
                                 "messages": [{"who": "系统", "text": "没有内容",
                                               "kind": "no"}]})

        agent = _teacher(_learner(d))
        before = len(agent.tool_log)
        reply = agent.send(message)
        new_calls = agent.tool_log[before:]

        # 流程正文直接呈现，不依赖模型转述
        bodies = [c["result"] for c in new_calls
                  if c["name"] == "run_flow" and not c["result"].startswith("[")]
        if bodies:
            reply = "\n\n".join(bodies) + "\n\n———\n" + reply

        return JSONResponse({
            "stream": "chat",
            "messages": [
                {"who": "老师", "text": reply,
                 "calls": [{"name": c["name"],
                            "arguments": c["arguments"][:120],
                            "result": c["result"][:300]} for c in new_calls]},
            ],
            "state": {"usage": f"{agent.usage['total']:,} token"},
        })
    except Exception:
        return _fail(traceback.format_exc(limit=3))


async def drill_start_route(request):
    """「动作 start 提交 远程 开始练习」。按顶栏当前选择开一局并弹出第一题。"""
    try:
        d = await request.json()
        return JSONResponse(drill_start(_learner(d), _field(d, "course"),
                                        _field(d, "kind")))
    except Exception:
        return _fail(traceback.format_exc(limit=3))


async def drill_answer_route(request):
    """「动作 submit 提交 远程 清空 作答」。判完留在浮层里，不自动出下一题。"""
    try:
        d = await request.json()
        learner = _learner(d)
        # 还没开局就点了作答：按顶栏当前选择开一局
        if learner not in _drills:
            return JSONResponse(drill_start(learner, _field(d, "course"),
                                            _field(d, "kind")))
        return JSONResponse(drill_answer(learner, _field(d, "answer")))
    except Exception:
        return _fail(traceback.format_exc(limit=3))


async def drill_next_route(request):
    """「动作 next 提交 远程 下一题」。没开局的话按当前选择开一局。"""
    try:
        d = await request.json()
        learner = _learner(d)
        if learner not in _drills:
            return JSONResponse(drill_start(learner, _field(d, "course"),
                                            _field(d, "kind")))
        return JSONResponse(drill_next(learner))
    except Exception:
        return _fail(traceback.format_exc(limit=3))


async def drill_stop_route(request):
    """「动作 stop 危险 远程 结束练习」。"""
    try:
        d = await request.json()
        return JSONResponse(drill_stop(_learner(d)))
    except Exception:
        return _fail(traceback.format_exc(limit=3))


async def reset(request):
    """「动作 reset 次要 远程 重置」。清空两条消息流并重载代码。"""
    try:
        d = await request.json()
        learner = _learner(d)
        summary = drill_stop(learner)
        _reload()
        _agents.pop(learner, None)
        text = summary.get("messages", [{}])[0].get("text", "")
        return JSONResponse({
            "stream": "chat",
            "overlay": None,
            "state": {"chat": [], "drill": [], "usage": "", "stat": "",
                      "question": "", "verdict": ""},
            "messages": [{"who": "系统",
                          "text": "已重置，代码也重新加载了。"
                                  + (f"\n{text}" if "练习结束" in text else ""),
                          "kind": "ok"}],
        })
    except Exception:
        return _fail(traceback.format_exc(limit=3))


routes = [
    Route("/chat", chat, methods=["POST"]),
    Route("/drill/start", drill_start_route, methods=["POST"]),
    Route("/drill/answer", drill_answer_route, methods=["POST"]),
    Route("/drill/next", drill_next_route, methods=["POST"]),
    Route("/drill/stop", drill_stop_route, methods=["POST"]),
    Route("/reset", reset, methods=["POST"]),
]

# 静态挂载放最后：挂在 "/" 上会吃掉所有未匹配的路径，
# 放前面就轮不到上面那些接口了。
if WEB.is_dir():
    routes.append(Mount("/", app=StaticFiles(directory=str(WEB), html=True)))

app = Starlette(routes=routes)


def main():
    import argparse
    import uvicorn
    p = argparse.ArgumentParser(description="日语教师对话界面（app2）")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8080)
    args = p.parse_args()
    if not WEB.is_dir():
        print(f"界面还没生成，先跑：py {HERE / 'build.py'}")
        return
    print(f"打开 http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
