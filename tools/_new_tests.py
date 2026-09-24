def test_call():
    print("\n[执行：脚本调用]")
    with tempfile.TemporaryDirectory() as d:
        Path(d, "子.zs").write_text("打印 子脚本收到：{参数}", encoding="utf-8")
        Path(d, "无参.zs").write_text("打印 固定内容", encoding="utf-8")
        Path(d, "多参.zs").write_text("打印 {甲}-{乙}", encoding="utf-8")
        Path(d, "生成.zs").write_text("问 结果 = 讲解{词}\n打印 {结果}", encoding="utf-8")
        Path(d, "自调.zs").write_text("执行 自调.zs", encoding="utf-8")

        check("传一个参数",
              run("执行 子.zs 参数=测试值", workdir=d)[0], "子脚本收到：测试值")
        check("省略 .zs 后缀",
              run("执行 子 参数=x", workdir=d)[0], "子脚本收到：x")
        check("无参数", run("执行 无参.zs", workdir=d)[0], "固定内容")
        check("多个参数",
              run("执行 多参.zs 甲=A 乙=B", workdir=d)[0], "A-B")
        check("参数值含空格",
              run("执行 子.zs 参数=動詞 第2回", workdir=d)[0], "子脚本收到：動詞 第2回")
        check("参数来自变量",
              run("设 x = 外部值\n执行 子.zs 参数={x}", workdir=d)[0],
              "子脚本收到：外部值")

        # 作用域隔离：父脚本的变量不会漏进子脚本
        check("作用域隔离",
              run("设 参数 = 父变量\n执行 无参.zs\n打印 {参数}", workdir=d)[0],
              "固定内容\n父变量")

        # 返回值赋给变量时不直接打印
        out, _ = run("设 结果 = 执行 无参.zs\n打印 收到：{结果}", workdir=d)
        check("返回值赋给变量", out, "收到：固定内容")

        # 子脚本里的模型调用走同一个客户端
        mock = MockClient(replies=["讲解内容"])
        out, c = run("执行 生成.zs 词=犬", mock, workdir=d)
        check("子脚本可调模型", out, "讲解内容")
        check("共用客户端", len(c.calls), 1)

        check_error("脚本不存在", "执行 没有.zs", "找不到脚本", workdir=d)
        check_error("越界", "执行 ../外面.zs", "路径越界", workdir=d)
        check_error("递归调用有上限", "执行 自调.zs", "调用层数", workdir=d)


def test_foreach():
    print("\n[逐项]")
    mock = MockClient(replies=["解释一", "解释二"])
    out, c = run("逐项 词 于 犬，猫\n 问 讲解 = 讲解{词}\n结束", mock)
    check("自动加标题并输出结果",
          out, "── 犬 ──\n解释一\n── 猫 ──\n解释二")
    check("每项一次调用", len(c.calls), 2)
    check("提示词插值正确", c.prompts, ["讲解犬", "讲解猫"])

    # 块内自己打印时不重复输出
    mock = MockClient(replies=["A", "B"])
    out, _ = run("逐项 词 于 甲,乙\n 问 x = q{词}\n 打印 自定义{x}\n结束", mock)
    check("块内有打印就不自动输出",
          out, "── 甲 ──\n自定义A\n── 乙 ──\n自定义B")

    check("别名 逐个",
          run("逐个 词 于 甲\n 打印 {词}\n结束")[0], "── 甲 ──\n甲")


def test_retry():
    print("\n[重试]")
    # 第一次不合格，第二次合格
    mock = MockClient(replies=["没有关键词", "含有 答案 二字"])
    out, c = run("问 甲 = 出题 重试 3 次 直到 包含 答案\n打印 {甲}", mock)
    check("重试后成功", out, "含有 答案 二字")
    check("调用了两次", len(c.calls), 2)

    # 一次就合格，不该重试
    mock = MockClient(replies=["含有 答案"])
    _, c = run("问 甲 = 出题 重试 3 次 直到 包含 答案", mock)
    check("一次合格不重试", len(c.calls), 1)

    # 始终不合格，用完次数후采用最后一次
    mock = MockClient(replies=["坏结果"])
    out, c = run("问 甲 = 出题 重试 2 次 直到 包含 答案\n打印 {甲}", mock)
    check("用完次数后采用最后结果", out.splitlines()[-1], "坏结果")
    check("调用次数等于上限", len(c.calls), 2)

    # 省略「次」字
    mock = MockClient(replies=["x", "含答案"])
    _, c = run("问 甲 = q 重试 2 直到 包含 答案", mock)
    check("可省略「次」", len(c.calls), 2)

    # 其他条件运算符
    mock = MockClient(replies=["", "非空了"])
    _, c = run("问 甲 = q 重试 3 次 直到 不为空", mock)
    check("配合「不为空」", len(c.calls), 2)

    # 没有重试子句时行为不变
    mock = MockClient(replies=["普通"])
    out, c = run("问 甲 = 普通提问\n打印 {甲}", mock)
    check("无重试子句照常", out, "普通")
    check("提示词不含重试文本", c.prompts[0], "普通提问")


def test_verdict():
    print("\n[判定]")
    mock = MockClient(replies=["正确\n解析内容"])
    out, _ = run("判定 判断 = 批改 正确→○答对了 部分正确→△ 否则→✗", mock)
    check("命中第一个分支", out, "○答对了")

    mock = MockClient(replies=["部分正确\n还差一点"])
    out, _ = run("判定 判断 = 批改 正确→○ 部分正确→△部分对 否则→✗", mock)
    check("命中中间分支", out, "△部分对")

    mock = MockClient(replies=["错误\n再想想"])
    out, _ = run("判定 判断 = 批改 正确→○ 部分正确→△ 否则→✗再看看", mock)
    check("落到否则", out, "✗再看看")

    mock = MockClient(replies=["无法归类的回答"])
    out, _ = run("判定 判断 = 批改 正确→○ 部分正确→△ 否则→✗", mock)
    check("都不匹配时走否则", out, "✗")

    mock = MockClient(replies=["通过"])
    out, _ = run("判定 判断 = 批改 通过→PASS", mock)
    check("没有否则分支也可以", out, "PASS")

    mock = MockClient(replies=["正确\n解析"])
    out, _ = run("判定 判断 = 批改 正确→○ 否则→✗\n打印 {判断}", mock)
    check("结果存入变量", out, "○\n正确\n解析")

    mock = MockClient(replies=["正确"])
    _, c = run("设 题 = 1+1\n判定 判断 = 批改{题} 正确→○ 否则→✗", mock)
    check("提示词插值", c.prompts[0], "批改1+1")

    check_error("没有分支", "判定 甲 = 提示词", "至少要有一个分支")


def test_compound_nesting():
    print("\n[复合语句嵌套]")
    mock = MockClient(replies=["A1", "A2", "B1", "B2"])
    out, _ = run(
        "逐项 甲 于 X,Y\n 逐项 乙 于 1,2\n  问 r = {甲}{乙}\n 结束\n结束", mock
    )
    check("逐项套逐项",
          out, "── X ──\n── 1 ──\nA1\n── 2 ──\nA2\n── Y ──\n── 1 ──\nB1\n── 2 ──\nB2")

    mock = MockClient(replies=["合格"])
    out, _ = run(
        "如果 1 小于 2\n 判定 判断 = q 合格→OK 否则→NG\n结束", mock
    )
    check("如果套判定", out, "OK")

    with tempfile.TemporaryDirectory() as d:
        Path(d, "单项.zs").write_text("打印 处理{项}", encoding="utf-8")
        out, _ = run(
            "遍历 项 于 甲,乙\n 执行 单项.zs 项={项}\n结束", workdir=d
        )
        check("循环里调用脚本", out, "处理甲\n处理乙")
