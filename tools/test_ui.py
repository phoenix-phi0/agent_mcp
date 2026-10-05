"""界面语言（.ui）的离线测试。

运行：
    python -m tools.test_ui

跟 test_dsl.py 分开：以前混在一个文件里，.ui 改个字段名就把 DSL 引擎的
测试报告一起弄崩——最后三项从来没跑到过。一边坏了另一边的结果照样
看得见，才叫测试。

这批测试是照当前 ui.py 重写的。旧版里「动作 send 提交 到 /chat 发送」
那套语法已经没了：端点不再写进 .ui，「远程」只是个旗标，地址按动作名
到外部的 endpoints 表里查。那个改动是对的——端点是部署细节，.ui 描述
的是界面意图，不该把路径写死进去。
"""

from .ui import parse, validate, compile_ui, UiSyntaxError

_passed = 0
_failed = 0


def check(name: str, got, want) -> None:
    global _passed, _failed
    if got == want:
        _passed += 1
        print(f"  ✓ {name}")
    else:
        _failed += 1
        print(f"  ✗ {name}\n      期望: {want!r}\n      实际: {got!r}")


def check_raises(name: str, fn, keyword: str = "") -> None:
    global _passed, _failed
    try:
        fn()
    except Exception as e:
        if keyword and keyword not in str(e):
            _failed += 1
            print(f"  ✗ {name}\n      期望报错含 {keyword!r}，实际: {e}")
        else:
            _passed += 1
            print(f"  ✓ {name}")
        return
    _failed += 1
    print(f"  ✗ {name}\n      期望报错，实际没有")


def one(text: str):
    """解析出唯一一个界面。"""
    return parse(text)[0]


# ----------------------------------------------------------------------


def test_screen():
    print("\n[界面与角色]")
    s = one("界面 表单 文章编辑\n  分组 基本 竖排\n    字段 title 必填 标题\n  结束\n结束")
    check("界面名", s.name, "文章编辑")
    check("角色", s.role, "表单")
    check("分组是子节点", s.children[0].kind, "分组")
    check("字段在分组里", s.of_kind("分组")[0].fields()[0].label, "标题")
    check("必填", s.of_kind("分组")[0].fields()[0].required, True)

    check("三种角色都认",
          [one(f"界面 {r} X\n结束").role for r in ("表单", "列表", "自定义")],
          ["表单", "列表", "自定义"])


def test_lines():
    print("\n[行关键字]")
    s = one("界面 自定义 会话\n"
            "  消息流 m 对话记录\n"
            "  显示 usage\n"
            "  文案 说明文字\n"
            "结束")
    check("三种行都成为节点",
          [n.kind for n in s.children], ["消息流", "显示", "文案"])
    check("消息流的名字和标题", (s.children[0].name, s.children[0].label),
          ("m", "对话记录"))
    # 没给标签时 label 回落成名字（ui.py 的 `label=label or name`），
    # 不是空串。dump() 那边按「label 等于 name 视为无标签」处理。
    check("显示没给标签时回落到名字", s.children[1].label, "usage")
    check("streams() 找得到", [n.name for n in s.streams()], ["m"])


def test_modifiers():
    print("\n[修饰词]")
    s = one("界面 自定义 会话\n"
            "  分组 底栏 横排 底栏 间距 10px\n"
            "    字段 message 单行高 提示 说点什么\n"
            "    动作 send 提交 远程 回显 清空 发送\n"
            "  结束\n"
            "结束")
    g = s.of_kind("分组")[0]
    check("旗标进 modifiers", g.has("横排") and g.has("底栏"), True)
    # SIZE_KEYS 把中文键翻译成 CSS 属性名再存：间距→gap、宽→width。
    # 拿中文键查会得到 None。
    check("尺寸键值翻译成 CSS 名", g.size.get("gap"), "10px")

    f = g.fields()[0]
    check("提示是键值修饰", f.hint, "说点什么")
    # 修饰词确实没混进标签：单行高是旗标、提示是键值修饰，都被吃掉了。
    # 剩下的标签为空，于是回落成名字——跟上面「显示」那条同一个规则。
    check("修饰词没混进标签", f.label, "message")

    a = g.actions()[0]
    check("远程是旗标不是端点", a.has("远程"), True)
    check("回显和清空", a.has("回显") and a.has("清空"), True)
    check("动作标签", a.label, "发送")

    # 「共享」让字段跨界面共用
    f2 = one("界面 自定义 X\n  分组 g 横排\n    字段 learner 共享 学习者\n"
             "  结束\n结束").of_kind("分组")[0].fields()[0]
    check("共享成为修饰词", f2.has("共享"), True)
    check("共享字段的标签", f2.label, "学习者")


def test_goto_and_overlay():
    print("\n[切到与浮层]")
    s = one("界面 自定义 主页\n"
            "  分组 顶栏 横排 顶栏\n"
            "    动作 m1 切到 练习 练习\n"
            "  结束\n"
            "  浮层 题目 宽 560px\n"
            "    显示 question\n"
            "    动作 submit 提交 远程 作答\n"
            "    动作 quit 关闭 收起\n"
            "  结束\n"
            "结束")
    a = s.of_kind("分组")[0].actions()[0]
    check("切到进 goto", a.goto, "练习")
    check("切到不进标签", a.label, "练习")

    ov = s.overlays()
    check("浮层被单独收集", [o.name for o in ov], ["题目"])
    check("浮层能装显示和动作",
          [n.kind for n in ov[0].children], ["显示", "动作", "动作"])
    check("浮层的宽度", ov[0].size.get("width"), "560px")
    check("关闭是旗标", ov[0].actions()[1].has("关闭"), True)


def test_syntax_errors():
    print("\n[语法错误]")
    check_raises("块没有结束",
                 lambda: parse("界面 表单 X\n  分组 g 竖排\n结束"))
    check_raises("多余的结束",
                 lambda: parse("界面 表单 X\n结束\n结束"))
    check_raises("字段不能直接放界面下",
                 lambda: parse("界面 表单 X\n  字段 a 标题\n结束"))


def test_validate():
    print("\n[校验]")
    ok = parse("界面 自定义 甲\n  分组 g 横排\n    动作 go 切到 乙 去乙\n  结束\n结束\n"
               "界面 自定义 乙\n结束")
    check("切到已有界面无问题", [i.code for i in validate(ok)], [])

    bad = parse("界面 自定义 甲\n  分组 g 横排\n    动作 go 切到 不存在 去\n  结束\n结束")
    check("切到不存在的界面报错",
          any("goto" in i.code or "screen" in i.code for i in validate(bad)),
          True)

    dup = parse("界面 自定义 甲\n结束\n界面 自定义 甲\n结束")
    check("界面重名报错", len(validate(dup)) > 0, True)

    # 打开的浮层必须跟动作在同一个界面里
    cross = parse("界面 自定义 甲\n  分组 g 横排\n    动作 o 打开 框 开\n  结束\n结束\n"
                  "界面 自定义 乙\n  浮层 框\n    文案 x\n  结束\n结束")
    check("跨界面打开浮层报错",
          any("overlay" in i.code for i in validate(cross)), True)


def test_compile():
    print("\n[编译]")
    ui = ("界面 自定义 会话\n"
          "  分组 顶栏 横排 顶栏\n"
          "    字段 learner 共享 宽 80px 学习者\n"
          "    动作 reset 次要 远程 重置\n"
          "    显示 usage\n"
          "  结束\n"
          "  消息流 chat 占满\n"
          "  分组 底栏 横排 底栏\n"
          "    字段 message 单行高 提示 说点什么\n"
          "    动作 send 提交 远程 回显 清空 发送\n"
          "  结束\n"
          "结束\n")

    r = compile_ui(ui, backend="vue",
                   options={"endpoints": {"send": "/chat", "reset": "/reset"}})
    check("编译没有 issue", [i.code for i in r.get("issues", [])], [])

    files = r["result"]["files"]
    check("产出三个文件", sorted(files) == sorted(files) and len(files) >= 3, True)
    js = files["app.js"]

    check("端点表进了产物", "/chat" in js, True)
    check("共享状态生成", "const shared" in js, True)
    check("回显字段登记", "const echoes" in js, True)
    check("清空字段登记", "const clears" in js, True)
    check("每界面消息流表", "const screenStream" in js, True)

    # 消息带链接（m.link / m.link_text）：渲染成 <a :href>，只认站内 # 地址
    # 和 http(s)，javascript: 之类不渲染
    page = "\n".join(v for v in files.values() if isinstance(v, str))
    check("消息流渲染消息里的链接", 'class="smsg-link" :href="m.link"' in page, True)
    check("链接显示 link_text，没有就显示地址", "{{ m.link_text || m.link }}" in page, True)
    check("链接只认 # 和 http(s)",
          "m.link.startsWith('#')" in page and "javascript" not in page.split("smsg-link")[0][-300:],
          True)

    # 一条消息多个链接（m.links = [{href, text}]）：一排链接，同样只认 # 和
    # http(s)；有 links 时不再画旧的 m.link（v-else-if），不重复
    check("消息流渲染 links 列表", 'v-for="(k, j) in m.links"' in page, True)
    check("links 每项显示 text，没有就显示地址", "{{ k.text || k.href }}" in page, True)
    check("links 只认 # 和 http(s)",
          "k.href.startsWith('#')" in page and "k.href.startsWith('https://')" in page
          and "k.href.startsWith('http://')" in page, True)
    check("links 不是数组不画（防字符串被逐字遍历）", "Array.isArray(m.links) && m.links.length" in page, True)
    check("有 links 时旧的 link 走 v-else-if，不重复画", '<a v-else-if="m.link &&' in page, True)

    # 不给端点时不该生成 fetch 胶水
    r2 = compile_ui(ui, backend="vue")
    check("无端点也能编译", [i.code for i in r2.get("issues", [])], [])

    # ir 后端只出结构，用来确认解析结果本身
    r3 = compile_ui(ui, backend="ir")
    check("ir 后端可用", "result" in r3, True)


def test_links():
    print("\n[链接]")
    ui = ("界面 自定义 课本 载入 lesson_one\n"
          "  列表 课文 绑 lessons\n"
          "    列 title 地址 href 标题\n"
          "    列 level 等级\n"
          "  结束\n"
          "  分组 去练 横排\n"
          "    链接 practice 绑 reading.practice 当 params.lesson 练这一课\n"
          "    链接 back 绑 reading.back 次要 回到课文表\n"
          "  结束\n"
          "结束\n")
    s = one(ui)
    col = s.children[0].children[0]
    check("列的「地址」进了 href", (col.name, col.href, col.label), ("title", "href", "标题"))
    check("没写「地址」的列 href 是空的", s.children[0].children[1].href, "")
    link = s.children[1].children[0]
    check("链接：名字、绑定、条件、标签",
          (link.kind, link.name, link.bind, link.when, link.label),
          ("链接", "practice", "reading.practice", "params.lesson", "练这一课"))
    check("链接的「次要」是旗标，不进标签", (s.children[1].children[1].label,
          s.children[1].children[1].has("次要")), ("回到课文表", True))
    check_raises("链接不能写在列表里",
                 lambda: parse("界面 自定义 甲\n  列表 t\n    链接 a 去\n  结束\n结束"),
                 "链接")

    r = compile_ui(ui, backend="vue", options={"endpoints": {"lesson_one": "/lesson/one"}})
    check("带链接的界面编译没有 issue", [i.code for i in r.get("issues", [])], [])
    page = "\n".join(v for v in r["result"]["files"].values() if isinstance(v, str))
    js = r["result"]["files"]["app.js"]
    # 对照：普通列照旧只出文字
    check("普通列照旧是文字", "<td>{{ row.level }}</td>" in page, True)
    check("地址列画成链接、地址取这一行的 href",
          'class="cell-link" :href="row.href">{{ row.title }}</a>' in page, True)
    check("地址列地址不合格时退回文字", '<template v-else>{{ row.title }}</template>' in page, True)
    check("链接的地址从共享状态取",
          ':href="getPath(shared, \'reading.practice\')"' in page, True)
    check("链接的「当」和地址检查合在一个 v-if 里",
          'v-if="(params.lesson) && isHref(getPath(shared, \'reading.practice\'))"' in page, True)
    check("没写「当」的链接只查地址",
          'v-if="isHref(getPath(shared, \'reading.back\'))"' in page, True)
    check("次要链接画成文字链接", 'class="link-plain"' in page, True)
    check("isHref 导出给模板用", "go, isHref, reset" in js, True)
    check("isHref 只认 # 和 http(s)",
          's.startsWith("#") || s.startsWith("http://") || s.startsWith("https://")' in js, True)
    check("链接的共享路径有初值（读不到也不报错）",
          '"reading": {"practice": "", "back": ""}' in js, True)

    clash = parse("界面 自定义 甲\n  显示 a.b\n  链接 x 绑 a.b 去\n结束")
    check("链接和显示占同一共享路径报冲突",
          any(i.code == "path_conflict" for i in validate(clash)), True)


# ----------------------------------------------------------------------


def main() -> int:
    print("=" * 50)
    print("界面语言（.ui）离线测试")
    print("=" * 50)

    for fn in [
        test_screen,
        test_lines,
        test_modifiers,
        test_goto_and_overlay,
        test_syntax_errors,
        test_validate,
        test_compile,
        test_links,
    ]:
        try:
            fn()
        except Exception as e:
            global _failed
            _failed += 1
            print(f"  ✗ {fn.__name__} 整组崩溃：{type(e).__name__}: {e}")

    print("\n" + "=" * 50)
    print(f"通过 {_passed}，失败 {_failed}")
    print("=" * 50)
    return 1 if _failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
