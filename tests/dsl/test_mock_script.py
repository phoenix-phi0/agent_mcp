# -*- coding: utf-8 -*-
"""假模型客户端：离线、脚本化回复；「解析JSON」动词。

    cd /home/ysc/mcp && .venv/bin/python tests/dsl/test_mock_script.py

  一、离线（offline=True）：「用 快」「用 平衡」也交给假客户端，不去起
      claude -p；记下的 model 是解析过的名字，tier 是档位。对照：不离线的
      假客户端照旧按通道分派（cli:claude 走 CLI 后端）
  二、规则：列表写法（几个词都出现才命中，系统提示词也算）、按顺序取第一条、
      default；旧的 {关键词: 回复} 照旧
  三、规则文件：from_file、DSL_MOCK_SCRIPT（from_env）；gen run 不带 --real
      的路由器用的是离线的、读环境变量的假客户端；client_factory 能换掉它
  四、解析JSON：正常、带围栏和废话、坏的给空字典、不是结构的给空字典
"""

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools import DSLEngine, config, packs          # noqa: E402
from tools.mock import MockClient                   # noqa: E402
from tools.llm_router import wrap                   # noqa: E402
from tools.dsl_http import Router                   # noqa: E402

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


TMP = Path(tempfile.mkdtemp(prefix="mock_script_"))


def engine(mock):
    return DSLEngine(mock, workdir=TMP, verbose=False,
                     verbs=packs.registry(("common",), TMP),
                     verbs_root=packs.verbs_root())


def main():
    print("一、离线")
    m = MockClient(replies=["甲", "乙"], offline=True)
    out = engine(m).run("问 a = 你好 用 快\n问 b = 再见 用 平衡\n打印 {a}{b}")
    check(out.strip() == "甲乙", f"两句都由假客户端回答：{out.strip()}")
    check([c["tier"] for c in m.calls] == ["快", "平衡"], f"记下了档位：{[c['tier'] for c in m.calls]}")
    check([c["model"] for c in m.calls] == [str(config.resolve_model("快")), str(config.resolve_model("平衡"))],
          f"记下了解析过的模型名：{[c['model'] for c in m.calls]}")
    check(all(isinstance(c["model"], str) and type(c["model"]) is str for c in m.calls),
          "model 存成普通字符串（能 JSON 化）")
    # 对照：不离线的假客户端遇到 cli 通道照旧交给 CLI 后端（只看分派，不真调）
    cli = "cli:claude/haiku"
    b_on, _ = wrap(MockClient())._pick(config.resolve_model(cli))
    b_off, _ = wrap(MockClient(offline=True))._pick(config.resolve_model(cli))
    check(b_on is not None and b_off is None, "不离线的照旧分派到 CLI，离线的不分派")

    print("二、规则")
    m = MockClient(rules=[{"when": ["分类", "出题"], "reply": "A"},
                          {"when": "分类", "reply": "B"}], default="D")
    check(m.chat("给我出题", system="你是分类器") == "A", "几个词都出现（含系统提示词）命中第一条")
    check(m.chat("讲讲", system="你是分类器") == "B", "第一条不全中，落到第二条")
    check(m.chat("讲讲") == "D", "都不中给 default")
    check(MockClient(rules={"诗": "两行诗"}).chat("写首诗") == "两行诗", "旧的字典写法照旧")
    check(MockClient().chat("x").startswith("[模拟回复]"), "什么都不给还是老样子")

    print("三、规则文件和路由器")
    f = TMP / "mock.json"
    f.write_text(json.dumps({"rules": [{"when": ["你好"], "reply": "嗨"}], "default": "嗯"},
                            ensure_ascii=False), encoding="utf-8")
    m = MockClient.from_file(f)
    check(m.chat("你好呀") == "嗨" and m.chat("别的") == "嗯", "from_file 读规则和 default")
    os.environ["DSL_MOCK_SCRIPT"] = str(f)
    try:
        r = Router(TMP / "routes", TMP, TMP / "sessions", real=False)
        c = r._client()
        check(c.offline is True and c.chat("你好") == "嗨", "mock 模式的路由器：离线、按 DSL_MOCK_SCRIPT 回")
    finally:
        del os.environ["DSL_MOCK_SCRIPT"]
    c = Router(TMP / "routes", TMP, TMP / "sessions", real=False)._client()
    check(c.offline is True and c.chat("你好").startswith("[模拟回复]"), "没设环境变量：离线的默认假回复")
    mine = MockClient(default="测试的")
    r.client_factory = lambda: mine
    check(r._client() is mine, "client_factory 换得掉")

    print("四、解析JSON")
    e = engine(MockClient())
    e.vars["好"] = '{"intent":"出题","keywords":["ために"]}'
    e.vars["围栏"] = '好的，结果如下：\n```json\n{"intent":"讲解"}\n```'
    e.vars["坏"] = "这不是 JSON"
    e.vars["数"] = "42"
    out = e.run("用包 common\n设 a = 解析JSON {好}\n设 b = 解析JSON {围栏}\n"
                "设 c = 解析JSON {坏}\n设 d = 解析JSON {数}\n"
                "打印 {a.intent}|{a.keywords}|{b.intent}|[{c.intent 或 兜底}]|[{d.intent 或 兜底}]")
    check(out.strip() == '出题|["ために"]|讲解|[兜底]|[兜底]', f"结果：{out.strip()}")
    check(e.vars["a"] == {"intent": "出题", "keywords": ["ために"]} and e.vars["c"] == {},
          "拿到的是结构；坏的是空字典")

    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
