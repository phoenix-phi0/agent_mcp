"""测试用的「做模块」子进程替身（v3 的 module_cmd）：参数同 `python -m tools.dslagent run --pack dslproj …`。

读任务文件里的「模块 <名>」，把参考实现（环境变量 V3_STUB_SOL）里属于该模块的文件拷进 --project；
V3_STUB_PLAN（JSON 文件）：{模块: 前几轮不做事（留着骨架，验收会不过）}，计数记在 V3_STUB_STATE 目录里；
每次调用把 {模块, 模型环境变量, 任务全文} 追加进 V3_STUB_STATE/calls.jsonl。最后一行打印 v2 风格的结果 JSON。
"""
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path


def main(argv):
    a = dict(zip(argv[1::2], argv[2::2])) if argv and argv[0] == "run" else {}
    project, task = Path(a["--project"]), Path(a["--task-file"]).read_text(encoding="utf-8")
    module = re.search(r"^模块\s+(\S+)", task, re.M).group(1)
    state = Path(os.environ["V3_STUB_STATE"])
    state.mkdir(parents=True, exist_ok=True)
    plan = {}
    if os.environ.get("V3_STUB_PLAN"):
        plan = json.loads(Path(os.environ["V3_STUB_PLAN"]).read_text(encoding="utf-8"))
    cnt = state / f"{module}.count"
    n = int(cnt.read_text()) + 1 if cnt.exists() else 1
    cnt.write_text(str(n))
    with (state / "calls.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"模块": module, "轮": n, "models": os.environ.get("DSLAGENT_MODELS"), "task": task, "t": time.time()}, ensure_ascii=False) + "\n")
    time.sleep(float(os.environ.get("V3_STUB_SLEEP", "0")))
    sol = Path(os.environ["V3_STUB_SOL"])
    if n > int(plan.get(module, 0)):
        sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
        from tools.dslagent.packs.dslproj import project as P
        for g in P.scope_globs(module):
            for src in sol.glob(g):
                if src.is_file():
                    dst = project / src.relative_to(sol)
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(src, dst)
    print("some log line")
    print(json.dumps({"kind": "task", "fixed": True, "calls": 2, "cost": 0.25, "seconds": 1, "stop": ""}, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
