# -*- coding: utf-8 -*-
"""GSBatch 续接判定：Drools 与本地实现的一致性对照。

跑法：python3 tests/test_gsbatch_rules.py
需要：~/opt 的 JDK（build.sh 先跑过）+ ~/.m2 的 Drools。
引擎起不来时跳过 Drools 侧（打 SKIP），本地侧照常跑。

案例全部来自 tools/gsbatch.py::_run_one 的真实分支，改任何一边
（decide.drl / GsbatchDecide / _decide_local / gsbatch 的正则）都要重跑。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.gsbatch_rules import decide_local, decide_drools  # noqa: E402

# (说明, 事实)。seconds_left 已减掉候选退避（≤0 = 续了也来不及）
CASES = [
    ("瞬时错误第 1 次：续，退 30",
     dict(why=None, rc=1, err_text="stream decode error", retries=0,
          has_session=True, cancelled=False, seconds_left=500)),
    ("瞬时错误第 2 次：续，退 60",
     dict(why=None, rc=1, err_text="connection reset by peer", retries=1,
          has_session=True, cancelled=False, seconds_left=500)),
    ("瞬时错误退避表打满后取最后一个",
     dict(why=None, rc=1, err_text="timeout", retries=9,
          has_session=True, cancelled=False, seconds_left=500)),
    ("429 限流：不续（非瞬时）",
     dict(why=None, rc=1, err_text="429 too many requests", retries=0,
          has_session=True, cancelled=False, seconds_left=500)),
    ("额度不足：不续",
     dict(why=None, rc=1, err_text="insufficient balance 余额不足", retries=0,
          has_session=True, cancelled=False, seconds_left=500)),
    ("鉴权失败：不续",
     dict(why=None, rc=1, err_text="unauthorized: invalid api key", retries=0,
          has_session=True, cancelled=False, seconds_left=500)),
    ("上下文超长：不续",
     dict(why=None, rc=1, err_text="prompt is too long: maximum context length",
          retries=0, has_session=True, cancelled=False, seconds_left=500)),
    ("正常完成：不续",
     dict(why=None, rc=0, err_text="", retries=0,
          has_session=True, cancelled=False, seconds_left=500)),
    ("流卡住：续（卡流不过滤正则）",
     dict(why="stall", rc=-9, err_text="", retries=0,
          has_session=True, cancelled=False, seconds_left=500)),
    ("流卡住但重试用完：停",
     dict(why="stall", rc=-9, err_text="", retries=3,
          has_session=True, cancelled=False, seconds_left=500)),
    ("没有会话 id：停（优先于取消/上限）",
     dict(why=None, rc=1, err_text="network error", retries=9,
          has_session=False, cancelled=True, seconds_left=500)),
    ("已取消：停",
     dict(why=None, rc=1, err_text="connection reset", retries=0,
          has_session=True, cancelled=True, seconds_left=500)),
    ("剩余时间不够：停",
     dict(why=None, rc=1, err_text="connection reset", retries=1,
          has_session=True, cancelled=False, seconds_left=10 - 60)),
    ("超时：不续（reason 为空那支）",
     dict(why="timeout", rc=-9, err_text="", retries=0,
          has_session=True, cancelled=False, seconds_left=0)),
    ("亚秒退避（测试环境用）：续，退 0.2",
     dict(why=None, rc=1, err_text="connection reset", retries=0,
          has_session=True, cancelled=False, seconds_left=500 - 0.2,
          backoff=(0.2, 0.4), resume_max=3)),
    ("非零退出但没有错误文字：不续（退出码本身不像瞬时错误）",
     dict(why=None, rc=137, err_text="", retries=0,
          has_session=True, cancelled=False, seconds_left=500)),
]

FAIL, SKIP_DROOLS = [], False

for name, fact in CASES:
    local = decide_local(**fact)
    try:
        drools = decide_drools(**fact)
    except Exception as e:                      # noqa: BLE001
        print(f"SKIP（Drools 起不来：{e}）")
        SKIP_DROOLS = True
        break
    ok = (local["resume"] == drools["resume"]
          and local["wait"] == drools["wait"]
          and local["gave_up"] == drools["gave_up"])
    tag = "✓" if ok else "✗"
    print(f"{tag} {name}  local={local} drools={drools}" if not ok else f"{tag} {name}")
    if not ok:
        FAIL.append(name)

print()
if SKIP_DROOLS:
    print("Drools 不可用，只验证了本地实现")
    sys.exit(2)
if FAIL:
    print("两边判定不一致：", FAIL)
    sys.exit(1)
print(f"全部同判（{len(CASES)} 案）")
