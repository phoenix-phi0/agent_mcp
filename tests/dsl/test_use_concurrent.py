# -*- coding: utf-8 -*-
"""几个线程共用一张动词表，同时「用包」：每个包只加载一次，不报重复注册。

    cd /home/ysc/mcp && .venv/bin/python tests/dsl/test_use_concurrent.py

HTTP 接口就是这样跑的：动词表按包组合缓存（packs.registry），所有请求
共用；每个接口脚本开头的「用包 db」往这张表里加载。早先「查过没加载」
和「加载」之间没有锁，两个请求同时到，db 被加载两遍，每个动词一条「被
重复注册」——这些警告进了脚本输出，又被路由器塞进 messages，出现在做题
页的消息流里（tests/e2e/quiz_run.js 时有时无地撞上）。

一次竞争窗口很窄，所以多来几轮：每轮一张新表、八个线程用 Barrier 一起起跑。
"""

import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools import packs                 # noqa: E402
from tools.dsl import DSLEngine         # noqa: E402
from tools.mock import MockClient       # noqa: E402

ROUNDS, THREADS = 30, 8


def main():
    ws = Path(tempfile.mkdtemp(prefix="use_race_"))
    bad_out, bad_packs, errors = [], [], []

    for r in range(ROUNDS):
        reg = packs.registry(["common", "http"], ws, cache=False)
        gate = threading.Barrier(THREADS)
        outs = [None] * THREADS

        def go(i):
            try:
                eng = DSLEngine(MockClient(), workdir=ws, verbose=False,
                                verbs=reg, verbs_root=packs.verbs_root())
                gate.wait()
                outs[i] = eng.run("用包 db quiz\n设 x = 1")
            except Exception as e:          # noqa: BLE001
                errors.append(f"第 {r} 轮线程 {i}：{e!r}")

        ts = [threading.Thread(target=go, args=(i,)) for i in range(THREADS)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        bad_out += [o for o in outs if o and "重复注册" in o]
        loaded = list(reg.packs)
        if loaded.count("db") != 1 or loaded.count("quiz") != 1:
            bad_packs.append(list(reg.packs))

    ok = not errors and not bad_out and not bad_packs
    print(("  ✓ " if not errors else "  ✗ ") + f"{ROUNDS}×{THREADS} 次并发「用包」没有出错：{errors[:2]}")
    print(("  ✓ " if not bad_out else "  ✗ ") + f"脚本输出里没有「重复注册」：{bad_out[:1]}")
    print(("  ✓ " if not bad_packs else "  ✗ ") + f"每个包只加载一次：{bad_packs[:1]}")
    n_ok = 3 - (bool(errors) + bool(bad_out) + bool(bad_packs))
    print(f"\n{'=' * 50}\n通过 {n_ok}，失败 {3 - n_ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
