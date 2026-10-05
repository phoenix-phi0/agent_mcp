"""DSL 引擎的离线测试。

运行：
    python -m tools.test_dsl

不需要 API Key，不发网络请求。

界面语言（.ui）的测试在 test_ui.py——两边分开跑，一边坏了另一边的
结果照样看得见。以前混在一个文件里，.ui 改个字段名就把引擎的测试报告
一起弄崩，最后三项从来没跑到过。
"""

import json
import tempfile
from pathlib import Path

from .dsl import DSLEngine, DSLError
from .mock import MockClient

_passed = 0
_failed = 0


def run(script: str, client: MockClient | None = None, workdir=None):
    """执行脚本，返回 (输出, 客户端)。异常会转成字符串。"""
    c = client or MockClient()
    engine = DSLEngine(c, workdir=workdir, verbose=False)
    try:
        return engine.run(script), c
    except Exception as e:
        return f"{type(e).__name__}: {e}", c


def check(name: str, got, want) -> None:
    global _passed, _failed
    if got == want:
        _passed += 1
        print(f"  ✓ {name}")
    else:
        _failed += 1
        print(f"  ✗ {name}\n      期望: {want!r}\n      实际: {got!r}")


def check_error(name: str, script: str, keyword: str = "", workdir=None) -> None:
    global _passed, _failed
    out, _ = run(script, workdir=workdir)
    if "DSLError" in str(out) and keyword in str(out):
        _passed += 1
        print(f"  ✓ {name}")
    else:
        _failed += 1
        print(f"  ✗ {name}\n      期望报错含 {keyword!r}，实际: {out!r}")


# ----------------------------------------------------------------------


def test_basic():
    print("\n[基础语句]")
    check("设与打印", run("设 甲 = 一\n打印 {甲}")[0], "一")
    check("变量套变量", run("设 甲 = 一\n设 乙 = {甲}二\n打印 {乙}")[0], "一二")
    check("未定义变量原样保留", run("打印 {不存在}")[0], "{不存在}")
    check("注释被忽略", run("# 注释\n打印 好")[0], "好")
    check("空行被忽略", run("\n\n打印 好\n\n")[0], "好")


def test_chinese():
    print("\n[中文与全角]")
    check("冒号保留", run("设 甲 = 标题：正文\n打印 {甲}")[0], "标题：正文")
    check("正文全角逗号保留", run("设 甲 = 你好，世界\n打印 {甲}")[0], "你好，世界")
    check("全角等号", run("设 甲 ＝ 一\n打印 {甲}")[0], "一")
    check("关键字紧贴", run("设 甲=一\n打印{甲}")[0], "一")
    check("打印机不误判", run("设 打印机 = 好\n打印 {打印机}")[0], "好")
    check("长关键字优先", run("设置 甲 = 二\n打印 {甲}")[0], "二")
    check("英文关键字混用", run("set a = x\n打印 {a}")[0], "x")


def test_loop():
    print("\n[循环]")
    check("全角逗号分隔", run("遍历 甲 于 A，B\n打印 {甲}\n结束")[0], "A\nB")
    check("半角逗号分隔", run("遍历 甲 于 A,B\n打印 {甲}\n结束")[0], "A\nB")
    check("用等号", run("遍历 甲 = A,B\n打印 {甲}\n结束")[0], "A\nB")
    check("用 in", run("遍历 甲 in A,B\n打印 {甲}\n结束")[0], "A\nB")
    check(
        "嵌套",
        run("遍历 甲 于 1,2\n 遍历 乙 于 A,B\n  打印 {甲}{乙}\n 结束\n结束")[0],
        "1A\n1B\n2A\n2B",
    )
    check("列表来自变量", run("设 表 = X,Y\n遍历 甲 于 {表}\n打印 {甲}\n结束")[0], "X\nY")
    # 「属于」不能被「于」抢先匹配，否则变量名会多出一个「属」字
    check("分隔词属于", run("遍历 甲 属于 A,B\n打印 {甲}\n结束")[0], "A\nB")


def test_condition():
    print("\n[条件分支]")
    check("包含", run("如果 很好 包含 好\n打印 是\n结束")[0], "是")
    check("不包含", run("如果 很好 不包含 坏\n打印 是\n结束")[0], "是")
    check("等于", run("如果 甲 等于 甲\n打印 是\n结束")[0], "是")
    check("不等于", run("如果 甲 不等于 乙\n打印 是\n结束")[0], "是")
    check("为空", run("设 空 =\n如果 {空} 为空\n打印 是\n结束")[0], "是")
    check("不为空", run("如果 x 不为空\n打印 是\n结束")[0], "是")
    check("大于", run("如果 85 大于 60\n打印 是\n结束")[0], "是")
    check("小于", run("如果 5 小于 60\n打印 是\n结束")[0], "是")
    check("不小于（相等）", run("如果 60 不小于 60\n打印 是\n结束")[0], "是")
    check("不大于（相等）", run("如果 60 不大于 60\n打印 是\n结束")[0], "是")
    check("开头是", run("如果 abc 开头是 ab\n打印 是\n结束")[0], "是")
    check("结尾是", run("如果 abc 结尾是 bc\n打印 是\n结束")[0], "是")

    check("数值而非字典序",
          run("如果 3 大于 20\n打印 错\n否则\n打印 对\n结束")[0], "对")
    check("非数字退回文本比较", run("如果 b 大于 a\n打印 是\n结束")[0], "是")

    check("条件为假跳过", run("如果 甲 等于 乙\n打印 不该出现\n结束")[0], "")
    check("否则分支", run("如果 甲 等于 乙\n打印 A\n否则\n打印 B\n结束")[0], "B")
    check("无否则时为真",
          run("如果 甲 等于 甲\n打印 A\n结束\n打印 后续")[0], "A\n后续")
    check("无否则时为假",
          run("如果 甲 等于 乙\n打印 A\n结束\n打印 后续")[0], "后续")

    check("左侧变量",
          run("设 答 = 正确\n如果 {答} 包含 正\n打印 是\n结束")[0], "是")
    check("右侧变量",
          run("设 标 = 正\n如果 正确 包含 {标}\n打印 是\n结束")[0], "是")
    check("两侧都是变量",
          run("设 甲 = x\n设 乙 = x\n如果 {甲} 等于 {乙}\n打印 是\n结束")[0], "是")
    check("未定义变量参与比较",
          run("如果 {没定义} 等于 {没定义}\n打印 是\n结束")[0], "是")
    # 左值里含运算符字样时，按整词分词才不会切错
    check("值里含运算符字样",
          run("设 说明 = 包含关系\n如果 {说明} 等于 包含关系\n打印 是\n结束")[0], "是")

    check("别名 若", run("若 甲 等于 甲\n打印 是\n结束")[0], "是")
    check("别名 if/else",
          run("if 甲 等于 乙\n打印 A\nelse\n打印 B\nend")[0], "B")


def test_nesting():
    print("\n[嵌套]")
    check(
        "if 套 if（内层真）",
        run("如果 1 小于 2\n 如果 3 小于 4\n  打印 内真\n 否则\n  打印 内假\n 结束\n结束")[0],
        "内真",
    )
    check(
        "if 套 if（内层假）",
        run("如果 1 小于 2\n 如果 5 小于 4\n  打印 内真\n 否则\n  打印 内假\n 结束\n结束")[0],
        "内假",
    )
    check(
        "外层假时整块跳过",
        run("如果 9 小于 2\n 如果 3 小于 4\n  打印 不该出现\n 否则\n  打印 也不该\n 结束\n结束")[0],
        "",
    )
    check(
        "内层否则不被外层认领",
        run("如果 1 小于 2\n 如果 5 小于 4\n  打印 A\n 否则\n  打印 B\n 结束\n 打印 C\n否则\n 打印 D\n结束")[0],
        "B\nC",
    )
    check(
        "each 套 if",
        run("遍历 词 于 甲,乙\n 如果 {词} 等于 乙\n  打印 {词}★\n 否则\n  打印 {词}\n 结束\n结束")[0],
        "甲\n乙★",
    )
    check(
        "if 套 each",
        run("如果 1 小于 2\n 遍历 数 于 1,2\n  打印 {数}\n 结束\n否则\n 打印 不该出现\n结束")[0],
        "1\n2",
    )
    check(
        "if 假时内层循环不执行",
        run("如果 9 小于 2\n 遍历 数 于 1,2\n  打印 {数}\n 结束\n结束")[0],
        "",
    )
    check(
        "三层混合",
        run("遍历 甲 于 A,B\n 如果 {甲} 等于 A\n  遍历 乙 于 1,2\n   打印 {甲}{乙}\n  结束\n 否则\n  打印 {甲}跳过\n 结束\n结束")[0],
        "A1\nA2\nB跳过",
    )
    check(
        "块后语句继续执行",
        run("如果 1 小于 2\n 打印 A\n结束\n遍历 甲 于 X\n 打印 {甲}\n结束\n打印 尾")[0],
        "A\nX\n尾",
    )


def test_model_calls():
    print("\n[模型调用]")
    mock = MockClient(rules={"介绍": "这是介绍"})
    out, c = run("问 甲 = 请介绍杭州\n打印 {甲}", mock)
    check("规则匹配回复", out, "这是介绍")
    check("记录了一次调用", len(c.calls), 1)
    check("提示词正确", c.prompts[0], "请介绍杭州")

    mock = MockClient(replies=["一", "二"])
    out, _ = run("问 a = x\n问 b = y\n打印 {a}{b}", mock)
    check("按顺序返回", out, "一二")

    mock = MockClient()
    out, c = run("模型 glm-4.6\n问 a = x", mock)
    # 「模型」只管本脚本：传给这次调用，不改共用的 client.model
    check("模型被切换", c.last_model, "glm-4.6")
    check("共用客户端的模型没被改", c.model, "mock-model")

    mock = MockClient()
    run("系统 你是助手\n问 a = x", mock)
    check("系统提示词传入", mock.calls[0]["system"], "你是助手")

    mock = MockClient()
    run("温度 0.3\n问 a = x", mock)
    check("温度传入", mock.calls[0]["temperature"], 0.3)

    mock = MockClient()
    run("如果 9 小于 2\n 问 a = 不该发\n结束", mock)
    check("假分支不调模型", len(mock.calls), 0)


def test_chat_history():
    print("\n[多轮对话]")
    mock = MockClient(replies=["回复一", "回复二"])
    out, c = run("系统 S\n对话 a = 第一句\n对话 b = 第二句\n打印 {a}|{b}", mock)
    check("两次回复", out, "回复一|回复二")
    check("第一次带 system", c.calls[0]["turns"], 2)
    check("第二次累积历史", c.calls[1]["turns"], 4)

    mock = MockClient()
    _, c = run("对话 a = 1\n重置\n对话 b = 2", mock)
    check("重置后历史清空", c.calls[1]["turns"], 1)


def test_stream():
    print("\n[流式]")
    mock = MockClient(replies=["流式内容"])
    out, c = run("流式 甲 = 写点什么\n打印 {甲}", mock)
    check("拼回完整文本", out, "流式内容")
    check("记录为 stream", c.calls[0]["type"], "stream")


def test_file_io():
    print("\n[文件读写]")
    with tempfile.TemporaryDirectory() as d:
        out, _ = run("设 甲 = 内容\n保存 测试.txt {甲}", workdir=d)
        check("保存提示", out, "[已保存 测试.txt]")
        check("文件内容", (Path(d) / "测试.txt").read_text(encoding="utf-8"), "内容")

        out, _ = run("读取 甲 = 测试.txt\n打印 {甲}", workdir=d)
        check("读回来", out, "内容")

        run("保存 子目录/深/文件.txt 内容", workdir=d)
        check("自动建目录", (Path(d) / "子目录/深/文件.txt").is_file(), True)

        check("保存显示相对路径",
              run("保存 甲/乙.txt x", workdir=d)[0], "[已保存 甲/乙.txt]")

        run("设 甲 = 一\n设 乙 = 二\n保存 换行.txt {甲}\\n{乙}", workdir=d)
        check(
            "转义换行",
            (Path(d) / "换行.txt").read_text(encoding="utf-8"),
            "一\n二",
        )


def test_append():
    print("\n[追加]")
    with tempfile.TemporaryDirectory() as d:
        out, _ = run("追加 日志.txt 第一条", workdir=d)
        check("追加提示", out, "[已追加 日志.txt]")
        check("文件不存在时自动创建",
              (Path(d) / "日志.txt").read_text(encoding="utf-8"), "第一条\n")

        run("追加 日志.txt 第二条\n追加 日志.txt 第三条", workdir=d)
        check(
            "多次追加不覆盖",
            (Path(d) / "日志.txt").read_text(encoding="utf-8"),
            "第一条\n第二条\n第三条\n",
        )

        run("保存 混合.txt 起始\n追加 混合.txt 后续", workdir=d)
        check(
            "保存后再追加",
            (Path(d) / "混合.txt").read_text(encoding="utf-8"),
            "起始后续\n",
        )

        run("追加 深/子/日志.jsonl {\"a\":1}", workdir=d)
        check("追加自动建目录", (Path(d) / "深/子/日志.jsonl").is_file(), True)

        run("设 名 = 小李\n追加 变量.txt 学习者：{名}", workdir=d)
        check(
            "追加支持变量插值",
            (Path(d) / "变量.txt").read_text(encoding="utf-8"),
            "学习者：小李\n",
        )

        run("追加 转义.txt 甲\\n乙", workdir=d)
        check(
            "追加支持转义换行",
            (Path(d) / "转义.txt").read_text(encoding="utf-8"),
            "甲\n乙\n",
        )

        run(
            "遍历 词 于 犬，猫\n  追加 词表.jsonl {\"word\":\"{词}\"}\n结束",
            workdir=d,
        )
        check(
            "循环内追加",
            (Path(d) / "词表.jsonl").read_text(encoding="utf-8"),
            '{"word":"犬"}\n{"word":"猫"}\n',
        )

        run(
            "遍历 分 于 90,50\n 如果 {分} 不小于 60\n  追加 及格.txt {分}\n 结束\n结束",
            workdir=d,
        )
        check(
            "条件内追加",
            (Path(d) / "及格.txt").read_text(encoding="utf-8"),
            "90\n",
        )

        check("别名 续写", run("续写 别名.txt x", workdir=d)[0], "[已追加 别名.txt]")
        check("别名 append", run("append 别名2.txt x", workdir=d)[0],
              "[已追加 别名2.txt]")


def test_path_safety():
    print("\n[路径安全]")
    with tempfile.TemporaryDirectory() as d:
        check_error("保存越界", "保存 ../外面.txt x", "路径越界", workdir=d)
        check_error("追加越界", "追加 ../外面.txt x", "路径越界", workdir=d)
        check_error("读取越界", "读取 甲 = ../外面.txt", "路径越界", workdir=d)
        check_error("读取不存在", "读取 甲 = 没有.txt", "文件不存在", workdir=d)


def test_errors():
    print("\n[错误处理]")
    check_error("缺少结束", "遍历 甲 于 1\n打印 x", "没有对应")
    check_error("多余结束", "打印 x\n结束", "多余")
    check_error("未知语句", "跳舞 一下", "未知语句")
    check_error("缺等号", "问 没有等号", "语法应为")
    check_error("非法变量名", "设 1甲 = x", "非法变量名")
    check_error("循环语法错", "遍历 甲甲甲\n打印 x\n结束", "循环语法")

    out, _ = run("遍历 甲 于 1\n打印 x")
    check("错误带行号", "第 1 行" in str(out), True)


def test_condition_errors():
    print("\n[条件错误处理]")
    check_error("看不懂的条件", "如果 甲 神秘运算 乙\n打印 x\n结束", "看不懂的条件")
    check_error("如果后面没条件", "如果\n打印 x\n结束", "要跟条件")
    check_error("孤立的否则", "否则\n打印 x\n结束", "没有对应的「如果」")
    check_error("重复的否则",
                "如果 1 小于 2\n打印 A\n否则\n打印 B\n否则\n打印 C\n结束",
                "多个「否则」")
    check_error("循环里写否则",
                "遍历 甲 于 1\n打印 x\n否则\n打印 y\n结束",
                "循环里不能直接写")
    check_error("如果缺少结束", "如果 1 小于 2\n打印 x", "没有对应的「结束」")

    out, _ = run("打印 好\n如果 甲 神秘运算 乙\n打印 x\n结束")
    check("条件错误带行号", "第 2 行" in str(out), True)


# ----------------------------------------------------------------------
# 结构化变量：读JSON / 读JSONL / 点号路径 / 遍历列表


def test_structured():
    print("\n[结构化变量]")
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "进度.json").write_text(json.dumps({
            "learner": "φ-0",
            "hiragana": {"day": 5, "mastered": ["あ", "い"]},
            "空表": [],
        }, ensure_ascii=False), encoding="utf-8")

        check("读JSON 取顶层字段",
              run("读JSON p = 进度.json\n打印 {p.learner}", workdir=d)[0], "φ-0")
        check("多层路径",
              run("读JSON p = 进度.json\n打印 {p.hiragana.day}", workdir=d)[0], "5")
        check("数组下标",
              run("读JSON p = 进度.json\n打印 {p.hiragana.mastered.0}",
                  workdir=d)[0], "あ")
        check("负数下标",
              run("读JSON p = 进度.json\n打印 {p.hiragana.mastered.-1}",
                  workdir=d)[0], "い")
        check("路径取不到原样保留",
              run("读JSON p = 进度.json\n打印 {p.没有.字段}", workdir=d)[0],
              "{p.没有.字段}")
        # 数字从 JSON 出来是 int，要能参与数值比较
        check("结构里的数字能比大小",
              run("读JSON p = 进度.json\n如果 {p.hiragana.day} 大于 3\n"
                  "打印 是\n结束", workdir=d)[0], "是")
        # 空数组转文本是 "[]"，不该被当成有内容
        check("空列表算为空",
              run("读JSON p = 进度.json\n如果 {p.空表} 为空\n打印 是\n结束",
                  workdir=d)[0], "是")

        rows = [{"id": "q1", "题干": "第一题"}, {"id": "q2", "题干": "第二题"}]
        (Path(d) / "题库.jsonl").write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
            encoding="utf-8")

        check("读JSONL 遍历对象列表",
              run("读JSONL 库 = 题库.jsonl\n遍历 题 于 {库}\n"
                  "打印 {题.id}:{题.题干}\n结束", workdir=d)[0],
              "q1:第一题\nq2:第二题")
        # 整个右侧是变量引用时保留结构，否则列表身份会丢
        check("设 之后仍是列表",
              run("读JSONL 库 = 题库.jsonl\n设 别名 = {库}\n"
                  "遍历 题 于 {别名}\n打印 {题.id}\n结束", workdir=d)[0], "q1\nq2")

        # 坏行跳过而不是整个失败
        (Path(d) / "坏.jsonl").write_text(
            '{"id":"a"}\n这不是JSON\n{"id":"b"}\n', encoding="utf-8")
        out, _ = run("读JSONL 库 = 坏.jsonl\n遍历 r 于 {库}\n打印 {r.id}\n结束",
                     workdir=d)
        check("坏行跳过但提示", "第 2 行不是合法 JSON" in out and "a\nb" in out, True)

        (Path(d) / "坏格式.json").write_text("{不是json}", encoding="utf-8")
        check_error("JSON 格式错报错", "读JSON p = 坏格式.json",
                    "不是合法 JSON", workdir=d)


# ----------------------------------------------------------------------
# 对话历史：读 / 存 / 修剪


def test_history_file():
    print("\n[对话历史存取]")
    with tempfile.TemporaryDirectory() as d:
        # 文件不存在时不报错——第一次跑本来就没有历史
        mock = MockClient(replies=["回复"])
        out, c = run("读历史 没有的.json\n对话 a = 问题", mock, workdir=d)
        check("读不存在的历史不报错", "DSLError" in str(out), False)
        check("空历史下只有一轮", c.calls[0]["turns"], 1)

        mock = MockClient(replies=["一", "二"])
        run("系统 S\n对话 a = 甲\n对话 b = 乙\n存历史 h.json", mock, workdir=d)
        saved = json.loads((Path(d) / "h.json").read_text(encoding="utf-8"))
        check("存下 system 加两轮", len(saved), 5)
        check("第一条是 system", saved[0]["role"], "system")

        # 读回来接着聊：新的一轮要能看到之前的历史
        mock = MockClient(replies=["三"])
        _, c = run("读历史 h.json\n对话 c = 丙", mock, workdir=d)
        check("读回历史后累积", c.calls[0]["turns"], 6)

        # 存的历史里没有 system 时，这次设的 system 要能加进去
        (Path(d) / "无系统.json").write_text(
            json.dumps([{"role": "user", "content": "旧"},
                        {"role": "assistant", "content": "旧回"}]),
            encoding="utf-8")
        mock = MockClient(replies=["新"])
        _, c = run("系统 新人设\n读历史 无系统.json\n对话 a = 新问", mock, workdir=d)
        check("补上缺失的 system", c.calls[0]["turns"], 4)

        # 坏数据跳过而不是整个作废
        (Path(d) / "半坏.json").write_text(
            json.dumps([{"role": "user", "content": "好的"},
                        {"没有role": 1},
                        {"role": "assistant", "content": "也好"}]),
            encoding="utf-8")
        mock = MockClient(replies=["x"])
        _, c = run("读历史 半坏.json\n对话 a = q", mock, workdir=d)
        check("坏消息被滤掉", c.calls[0]["turns"], 3)

        check_error("历史不是列表时报错", "读历史 进度.json", "不是消息列表",
                    workdir=d) if (Path(d) / "进度.json").is_file() else None


def test_history_trim():
    print("\n[历史修剪]")
    with tempfile.TemporaryDirectory() as d:
        base = "系统 S\n" + "".join(
            f"对话 v{i} = 第{i}句\n" for i in range(1, 6))

        # 五轮 = system + 10 条
        mock = MockClient(replies=[f"回{i}" for i in range(1, 6)])
        run(base + "存历史 h.json", mock, workdir=d)
        saved = json.loads((Path(d) / "h.json").read_text(encoding="utf-8"))
        check("修剪前 11 条", len(saved), 11)

        # 按条数：system 单独保住，不算进预算
        mock = MockClient(replies=[f"回{i}" for i in range(1, 6)])
        run(base + "修剪历史 4\n存历史 h.json", mock, workdir=d)
        saved = json.loads((Path(d) / "h.json").read_text(encoding="utf-8"))
        check("留 4 条加 system", len(saved), 5)
        check("system 还在", saved[0]["role"], "system")
        check("留的是最近的", saved[-1]["content"], "回5")

        # 按字数：至少保一条，否则挂了大文件历史会被清空
        mock = MockClient(replies=[f"回{i}" for i in range(1, 6)])
        run(base + "修剪历史 1字\n存历史 h.json", mock, workdir=d)
        saved = json.loads((Path(d) / "h.json").read_text(encoding="utf-8"))
        check("字数极小仍保一条", len(saved), 2)

        # 两个上限都很松时不该动
        mock = MockClient(replies=[f"回{i}" for i in range(1, 6)])
        run(base + "修剪历史 99 9999字\n存历史 h.json", mock, workdir=d)
        saved = json.loads((Path(d) / "h.json").read_text(encoding="utf-8"))
        check("上限宽松时不动", len(saved), 11)

        # 不给参数按默认条数
        mock = MockClient(replies=[f"回{i}" for i in range(1, 6)])
        out, _ = run(base + "修剪历史", mock, workdir=d)
        check("默认不报错", "DSLError" in str(out), False)

        check_error("参数写错报错", "修剪历史 abc", "看不懂的修剪参数", workdir=d)


# ----------------------------------------------------------------------
# 挂载文件


def test_attach():
    print("\n[挂载文件]")
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "课文.md").write_text("这是课文正文", encoding="utf-8")
        (Path(d) / "补充.md").write_text("这是补充材料", encoding="utf-8")

        mock = MockClient(replies=["好"])
        run("问 a = 请讲解 附 课文.md", mock, workdir=d)
        prompt = mock.prompts[0]
        check("文件内容进了提示词", "这是课文正文" in prompt, True)
        check("指令在文件后面", prompt.rstrip().endswith("请讲解"), True)
        check("带上文件名标记", "课文.md" in prompt, True)

        mock = MockClient(replies=["好"])
        run("问 a = 比较 附 课文.md,补充.md", mock, workdir=d)
        check("多个文件都挂上",
              "这是课文正文" in mock.prompts[0]
              and "这是补充材料" in mock.prompts[0], True)

        mock = MockClient(replies=["好"])
        run("系统 你是老师 附 课文.md\n问 a = x", mock, workdir=d)
        check("系统提示词也能挂", "这是课文正文" in mock.calls[0]["system"], True)

        # 读不到直接报错，不静默跳过——否则模型基于空上下文编答案
        check_error("挂载不存在的文件", "问 a = x 附 没有.md",
                    "挂载的文件不存在", workdir=d)


# ----------------------------------------------------------------------
# 问JSON 与带工具：MockClient 没有这两个方法，本地补两个替身


class JsonClient(MockClient):
    """chat_json 的替身，直接返回预设的对象。"""

    def __init__(self, obj):
        super().__init__()
        self.obj = obj
        self.json_prompts: list[str] = []

    def chat_json(self, prompt, system=None, temperature=None, **kw):
        self.json_prompts.append(prompt)
        if isinstance(self.obj, Exception):
            raise self.obj
        return self.obj


class ToolClient(MockClient):
    """chat_raw 的替身，按脚本依次返回带不带 tool_calls 的消息。"""

    def __init__(self, script: list[dict]):
        super().__init__()
        self.script = list(script)
        self.rounds = 0
        self.sent: list[list[dict]] = []
        self.tools_seen: list[dict] = []

    def chat_raw(self, messages, **kw):
        self.rounds += 1
        self.sent.append(list(messages))
        if kw.get("tools"):
            self.tools_seen = kw["tools"]
        msg = self.script[min(self.rounds - 1, len(self.script) - 1)]
        return {"choices": [{"message": msg}]}


def test_ask_json():
    print("\n[问JSON]")
    c = JsonClient({"意图": "出题", "课程": "doushi_02", "数量": "3"})
    out, _ = run("问JSON d = 提取意图\n打印 {d.意图}|{d.课程}|{d.数量}", c)
    check("取到结构字段", out, "出题|doushi_02|3")
    check("提示词传进去", c.json_prompts[0], "提取意图")

    c = JsonClient({"意图": "出题"})
    check("结果能用于条件判断",
          run("问JSON d = x\n如果 {d.意图} 等于 出题\n打印 命中\n结束", c)[0],
          "命中")

    # 解析失败要报错，不能静默给空对象——那样条件判断会一路走到「否则」
    c = JsonClient(ValueError("模型没有返回合法 JSON。最后一次回复：胡说"))
    out, _ = run("问JSON d = x\n打印 {d.意图}", c)
    check("解析失败报错", "DSLError" in out and "合法 JSON" in out, True)


def test_tools():
    print("\n[带工具]")
    from .verbs import VerbRegistry
    from .dsl import RESERVED

    reg = VerbRegistry(reserved=RESERVED)

    @reg.verb("统计题库里有多少题")
    def 题目数(题库: str, 课程: str = "") -> str:
        return f"{课程 or '全部'}:57"

    # 第一轮返回 tool_calls，第二轮给最终答复
    c = ToolClient([
        {"role": "assistant", "content": "",
         "reasoning_content": "这段不该被回传",
         "tool_calls": [{"id": "c1", "type": "function", "function": {
             "name": "题目数",
             "arguments": '{"题库":"content/题库","课程":"doushi_01"}'}}]},
        {"role": "assistant", "content": "一共 57 道题"},
    ])
    engine = DSLEngine(c, verbose=False, verbs=reg)
    out = engine.run("问 a = 有多少题 带工具 题目数 最多 3 轮\n打印 {a}")

    check("拿到最终答复", out.splitlines()[-1], "一共 57 道题")
    check("跑了两轮", c.rounds, 2)
    check("工具调用被打印", "[工具] 题目数" in out, True)
    check("schema 里有动词名", c.tools_seen[0]["function"]["name"], "题目数")
    # 有默认值的参数不进 required，模型才知道可以不给
    check("必填只有题库",
          c.tools_seen[0]["function"]["parameters"]["required"], ["题库"])
    # 第二轮的消息里应该有 tool 结果，且没有 reasoning_content
    second = c.sent[1]
    check("工具结果回传", any(m.get("role") == "tool"
                              and m.get("content") == "doushi_01:57"
                              for m in second), True)
    check("思考过程没回传",
          any("reasoning_content" in m for m in second), False)

    # 参数按名字绑定：模型给的顺序跟签名不一致也要对
    c = ToolClient([
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "c1", "type": "function", "function": {
                "name": "题目数",
                "arguments": '{"课程":"doushi_03","题库":"x"}'}}]},
        {"role": "assistant", "content": "好"},
    ])
    out = DSLEngine(c, verbose=False, verbs=reg).run(
        "问 a = q 带工具 题目数")
    check("按名字绑定不受顺序影响", "doushi_03:57" in out, True)

    # 点名不存在的动词要报错
    engine = DSLEngine(ToolClient([{"role": "assistant", "content": "x"}]),
                       verbose=False, verbs=reg)
    try:
        engine.run("问 a = q 带工具 不存在的动词")
        check("未知工具报错", False, True)
    except DSLError as e:
        check("未知工具报错", "无法当工具用" in str(e), True)


# ----------------------------------------------------------------------


def main() -> int:
    print("=" * 50)
    print("DSL 引擎离线测试")
    print("=" * 50)

    for fn in [
        test_basic,
        test_chinese,
        test_loop,
        test_condition,
        test_nesting,
        test_model_calls,
        test_chat_history,
        test_stream,
        test_file_io,
        test_append,
        test_path_safety,
        test_errors,
        test_condition_errors,
        test_structured,
        test_history_file,
        test_history_trim,
        test_attach,
        test_ask_json,
        test_tools,
    ]:
        fn()

    print("\n" + "=" * 50)
    print(f"通过 {_passed}，失败 {_failed}")
    print("=" * 50)
    return 1 if _failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
