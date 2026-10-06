# -*- coding: utf-8 -*-
"""档位 fallback 接住 CLI「这次没跑成」：超时、退出码非 0、排队没轮到。

    cd /home/ysc/mcp && .venv/bin/python tests/dsl/test_model_fallback_runtime.py

做题页「请老师总结」走平衡档（cli:claude/sonnet）。早先 fallback 只接「缺
能力」（带工具），claude 卡住时要等满 180 秒、最后回 500，页面一直转圈。
现在单次超时默认 90 秒，超时/报错/排队等不到都改用档位的 fallback。

不起真的 claude：假程序（CBATCH_CLAUDE 指过去）按环境变量睡一会儿或退出码
非 0。fallback 是 api:zhipu，内层用 MockClient，不发真请求。
"""

import json
import logging
import os
import stat
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="model_fallback_rt_"))
for k in ("ZHIPU_MODEL", "ZHIPU_API_KEY", "ZHIPU_BASE_URL", "ZHIPU_MODELS",
          "DSL_CLAUDE_TIMEOUT", "DSL_CLAUDE_QUEUE_WAIT", "JP_DATA_DIR"):
    os.environ.pop(k, None)
# 一次只跑一个 claude：排队那一节要用；信号量第一次用时按这个建
os.environ["DSL_CLAUDE_MAX_PROCS"] = "1"

FAKE = r'''#!{py}
import json, os, sys, time
if os.environ.get("FAKE_SLEEP"):
    time.sleep(float(os.environ["FAKE_SLEEP"]))
if os.environ.get("FAKE_EXIT"):
    sys.stderr.write("假的出错\n")
    sys.exit(int(os.environ["FAKE_EXIT"]))
print(json.dumps({{"type": "result", "subtype": "success", "is_error": False,
                  "result": "claude答"}}, ensure_ascii=False))
'''
p = TMP / "fake_claude"
p.write_text(FAKE.format(py=sys.executable), encoding="utf-8")
p.chmod(p.stat().st_mode | stat.S_IEXEC)
os.environ["CBATCH_CLAUDE"] = str(p)

d = TMP / "conf"
d.mkdir()
(d / "config.json").write_text(json.dumps(
    {"api_key": "test-not-real", "model": "glm-default"}), encoding="utf-8")
(d / "models.json").write_text(json.dumps({"tiers": {
    "平衡": {"model": "cli:claude/sonnet", "fallback": "api:zhipu/glm-fb"},
    "裸": "cli:claude/sonnet"}}, ensure_ascii=False), encoding="utf-8")
os.environ["ZHIPU_CONFIG"] = str(d / "config.json")

from tools import config, DSLEngine, MockClient  # noqa: E402
from tools import llm_router  # noqa: E402
from tools.llm_router import wrap  # noqa: E402

config.load(reload=True)

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


class Grab(logging.Handler):
    def __init__(self):
        super().__init__(logging.WARNING)
        self.lines = []

    def emit(self, record):
        self.lines.append(record.getMessage())


GRAB = Grab()
logging.getLogger("tools.llm_router").addHandler(GRAB)


def fake(**kw):
    for k in ("FAKE_SLEEP", "FAKE_EXIT", "DSL_CLAUDE_TIMEOUT",
              "DSL_CLAUDE_QUEUE_WAIT"):
        os.environ.pop(k, None)
    for k, v in kw.items():
        os.environ[k] = str(v)
    GRAB.lines.clear()


def ask(mock, model):
    e = DSLEngine(mock, workdir=TMP, verbose=False)
    t = time.time()
    try:
        e.run(f"问 答 = 总结一下 用 {model}")
        return e.vars.get("答"), "", time.time() - t
    except Exception as ex:  # noqa: BLE001
        return None, f"{type(ex).__name__}: {ex}", time.time() - t


def main():
    print("零、默认值")
    check(llm_router.DEFAULT_TIMEOUT == 90,
          f"CLI 单次超时默认 90 秒：{llm_router.DEFAULT_TIMEOUT}")

    print("\n一、对照：claude 正常就用 claude，不碰 fallback")
    fake()
    mock = MockClient(replies=["智谱答"])
    got, err, _ = ask(mock, "平衡")
    check(got == "claude答" and not mock.calls and not GRAB.lines,
          f"回的是 claude 的：{got!r} {err}")

    print("\n二、claude 超时 → 改用 fallback，不等满")
    fake(FAKE_SLEEP=5, DSL_CLAUDE_TIMEOUT=1)
    mock = MockClient(replies=["智谱答"])
    got, err, dt = ask(mock, "平衡")
    check(got == "智谱答" and mock.last_model == "glm-fb",
          f"fallback 接住：{got!r}，内层模型 {mock.last_model!r} {err}")
    check(dt < 4, f"超时 1 秒就换，没有等假 claude 睡完 5 秒：{dt:.1f}s")
    line = GRAB.lines[0] if GRAB.lines else ""
    check("cli:claude/sonnet" in line and "api:zhipu/glm-fb" in line
          and "超过" in line, f"记了一条 warning：{line[:90]}")

    print("\n三、claude 退出码非 0 → 改用 fallback")
    fake(FAKE_EXIT=1)
    mock = MockClient(replies=["智谱答"])
    got, err, _ = ask(mock, "平衡")
    check(got == "智谱答" and "假的出错" in "".join(GRAB.lines),
          f"fallback 接住：{got!r}；日志带原因：{''.join(GRAB.lines)[:80]}")

    print("\n四、档位没写 fallback：照旧报错，信息可读")
    fake(FAKE_SLEEP=5, DSL_CLAUDE_TIMEOUT=1)
    mock = MockClient(replies=["智谱答"])
    got, err, dt = ask(mock, "裸")
    check(got is None and "超过 1 秒" in err and not mock.calls and dt < 4,
          f"报超时：{err[:80]}（{dt:.1f}s）")

    print("\n五、claude 进程满了排队等不到 → 改用 fallback")
    fake(FAKE_SLEEP=3, DSL_CLAUDE_TIMEOUT=20, DSL_CLAUDE_QUEUE_WAIT=1)
    first = {}

    def bg():
        first["r"] = ask(MockClient(replies=["智谱答"]), "平衡")

    th = threading.Thread(target=bg)
    th.start()
    time.sleep(0.5)
    mock = MockClient(replies=["智谱答"])
    got, err, dt = ask(mock, "平衡")
    th.join()
    check(first["r"][0] == "claude答", f"先来的那个照常拿到 claude 的：{first['r'][0]!r}")
    check(got == "智谱答" and dt < 2.5,
          f"后来的排队 1 秒没轮到，改用 fallback：{got!r}（{dt:.1f}s）{err}")
    check(any("排队" in x for x in GRAB.lines), f"日志说是排队：{GRAB.lines[:1]}")

    print("\n六、流式：claude 出错也换 fallback（错是在迭代时抛的）")
    fake(FAKE_EXIT=1)
    r = wrap(MockClient(replies=["智谱答"]))
    try:
        got = "".join(r.stream("讲讲", model="平衡"))
    except Exception as ex:  # noqa: BLE001
        got = f"{type(ex).__name__}: {ex}"
    check(got == "智谱答", f"流式拿到 fallback 的：{got!r}")
    fake()
    got = "".join(wrap(MockClient(replies=["智谱答"])).stream("讲讲", model="平衡"))
    check(got == "claude答", f"对照：claude 正常时流式还是 claude 的：{got!r}")

    print("\n七、缺能力（带工具）不受影响：照旧直接用 fallback")
    fake()
    r = wrap(MockClient(replies=["智谱答"]))
    out = r.chat_raw([{"role": "user", "content": "x"}], model="平衡",
                     tools=[{"type": "function", "function": {"name": "f"}}])
    check(r.last_model == "glm-fb", f"带工具走 fallback：{r.last_model!r} {str(out)[:40]}")

    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
