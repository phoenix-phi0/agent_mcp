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
    check("消息流渲染消息里的链接", 'class="smsg-link" :href="hrefOf(m.link)"' in page, True)
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

    # 没有消息流的界面：消息只弹提示条，不往别的界面的流里塞。早先退回
    # 「全局第一条流」，做题页的达标喜报跑进了问老师的对话
    two = ui + ("界面 自定义 做题\n"
                "  动作 answer 远程 作答\n"
                "结束\n")
    r4 = compile_ui(two, backend="vue",
                    options={"endpoints": {"send": "/chat", "reset": "/reset", "answer": "/a"}})
    js4 = r4["result"]["files"]["app.js"]
    check("对照：有流的界面登记了自己的流", '"会话": "chat"' in js4, True)
    check("没流的界面不登记流", '"做题"' not in js4.split("const screenStream")[1].split(";")[0], True)
    check("当前界面没流时不退回全局第一条流",
          'const myStream = () => screenStream[current.value.name] || "";' in js4, True)
    check("没流时 messages 弹提示条", "showNotice(m.text, m.kind)" in js4, True)

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
          'class="cell-link" :href="hrefOf(row.href)" :target="targetOf(row.href)">{{ row.title }}</a>' in page, True)
    check("地址列地址不合格时退回文字", '<template v-else>{{ row.title }}</template>' in page, True)
    check("链接的地址从共享状态取",
          ':href="hrefOf(getPath(shared, \'reading.practice\'))"' in page, True)
    check("链接的「当」和地址检查合在一个 v-if 里",
          'v-if="(params.lesson) && isHref(getPath(shared, \'reading.practice\'))"' in page, True)
    check("没写「当」的链接只查地址",
          'v-if="isHref(getPath(shared, \'reading.back\'))"' in page, True)
    check("次要链接画成文字链接", 'class="link-plain"' in page, True)
    check("isHref 导出给模板用", "go, isHref, hrefOf, targetOf, reset" in js, True)
    check("isHref 只认 # 和 http(s)",
          's.startsWith("#") || s.startsWith("http://") || s.startsWith("https://")' in js, True)
    check("链接的共享路径有初值（读不到也不报错）",
          '"reading": {"practice": "", "back": ""}' in js, True)

    clash = parse("界面 自定义 甲\n  显示 a.b\n  链接 x 绑 a.b 去\n结束")
    check("链接和显示占同一共享路径报冲突",
          any(i.code == "path_conflict" for i in validate(clash)), True)



def test_trigger():
    print("\n[触发]")
    ui = ("界面 自定义 问老师 触发 teacher_send\n"
          "  动作 teacher_state 远程 进入时 隐藏 刷新\n"
          "  消息流 talk 占满\n"
          "  分组 底栏\n"
          "    字段 content 控件 多行\n"
          "    动作 teacher_send 提交 远程 回显 清空 发送\n"
          "  结束\n"
          "结束\n")
    s = one(ui)
    check("「触发」进了 trigger，没进标签、也不是载入", (s.name, s.trigger, s.load), ("问老师", "teacher_send", ""))
    eps = {"teacher_send": "/teacher/send", "teacher_state": "/teacher/state"}
    r = compile_ui(ui, backend="vue", options={"endpoints": eps})
    check("编译没有 issue", [i.code for i in r.get("issues", [])], [])
    js = r["result"]["files"]["app.js"]
    check("触发表按界面名给出", 'const triggers = {"问老师": "teacher_send"};' in js, True)
    check("跑之前用 replaceState 清掉地址参数（不留历史）",
          'history.replaceState(null, "", "#" + encodeURIComponent(name));' in js, True)
    check("「触发」排在「进入时」后面", js.index("await runTrigger(name, loaded)") > js.index("for (const a of acts)"), True)
    # K112：浮层开着（地址有「浮层」）时参数是浮层的，不清——清了刷新浮层就关了
    cut = js.index("async function runTrigger(")
    body = js[cut:js.index("async function runEnter(", cut)]
    check("地址有「浮层」时 runTrigger 不清地址参数",
          body.index('if (!all["浮层"]) {') < body.index("history.replaceState(") < body.index("params.value = {};"), True)
    # K112：载入刚为同样参数发过同一个动作，触发不再发（节点图点一次原先发两遍）
    check("runLoader 把发出的动作名交给 runTrigger、同名不再发",
          ("return loader;" in js, "const loaded = await runLoader(name);" in js,
           "runLoader(route.value).then(loaded => runTrigger(route.value, loaded));" in js,
           "act === loaded) return;" in body), (True, True, True, True))
    r2 = compile_ui(ui, backend="vue", options={"endpoints": {"teacher_state": "/teacher/state"}})
    check("触发的接口不存在：报 missing_endpoint",
          [i.code for i in r2.get("issues", []) if "触发" in i.message], ["missing_endpoint"])
    r3 = compile_ui(ui.replace(" 触发 teacher_send", ""), backend="vue", options={"endpoints": eps})
    check("没写触发：触发表是空的", "const triggers = {};" in r3["result"]["files"]["app.js"], True)


def test_dynamic_select():
    print("\n[下拉：选项来自、改时]")
    ui = ("界面 自定义 教材\n"
          "  动作 lesson_list 远程 进入时 隐藏 刷新\n"
          "  分组 顶栏 横排\n"
          "    字段 series 控件 下拉 选项来自 series_options 改时 lesson_list 宽 150px 系列\n"
          "    字段 lesson_level 控件 下拉 宽 90px 等级\n"
          "    动作 lesson_list 提交 远程 搜索\n"
          "  结束\n"
          "结束\n")
    s = one(ui)
    f = s.children[1].children[0]
    check("「选项来自」「改时」进了各自的属性，没进标签",
          (f.name, f.widget, f.source, f.on_change, f.label),
          ("series", "下拉", "series_options", "lesson_list", "系列"))
    plain = s.children[1].children[1]
    check("没写的字段两样都是空的", (plain.source, plain.on_change), ("", ""))
    eps = {"lesson_list": "/lesson/list"}
    r = compile_ui(ui, backend="vue", fields={"series": "文本", "lesson_level": "文本"},
                   options={"endpoints": eps, "options_map": {"lesson_level": ["全部", "N5"]}})
    check("编译没有 issue", [i.code for i in r.get("issues", [])], [])
    js = r["result"]["files"]["app.js"]
    check("选项从 lists 的那个键取（rowsOf），每行 value / label",
          '<option v-for="o in rowsOf(\'series_options\')" :key="o.value" :value="o.value">{{ o.label || o.value }}</option>' in js, True)
    check("改了就提交那个动作",
          '@change="typeof submitTo === \'function\' && submitTo(\'lesson_list\')"' in js, True)
    check("对照：普通下拉照旧是编译时的枚举选项、不挂 change",
          '<option value="N5">N5</option>' in js and js.count("@change=\"typeof submitTo") == 1, True)
    r2 = compile_ui(ui, backend="vue", fields={"series": "文本", "lesson_level": "文本"},
                    options={"endpoints": {"other": "/x"}})
    check("改时的接口不存在：报 missing_endpoint",
          [i.code for i in r2.get("issues", []) if "改时" in i.message], ["missing_endpoint"])


def test_audience():
    print("\n[界面的「端」：多人模式下按角色分端]")
    ui = ("界面 自定义 做题 端 学生\n"
          "  文案 学生的页\n"
          "结束\n"
          "界面 表单 登录\n"
          "  分组 主体\n"
          "    字段 username 用户名\n"
          "  结束\n"
          "结束\n"
          "界面 自定义 学情 侧 管理 端 教师 载入 report_one\n"
          "  文案 教师的页\n"
          "结束\n")
    from tools.ui import parse, dump
    screens = parse(ui)
    check("「端 教师」进 audience，不进名字，侧和载入照旧",
          [(s.name, s.audience, s.side) for s in screens] + [screens[2].load],
          [("做题", "学生", ""), ("登录", "", ""), ("学情", "教师", "管理"), "report_one"])
    check("dump 里有「端=」", "端=教师" in dump(screens), True)
    eps = {"auth_me": "/auth/me", "auth_logout": "/auth/logout", "report_one": "/report/one"}
    r = compile_ui(ui, backend="vue", fields={"username": "文本"}, options={"endpoints": eps})
    check("编译没有 issue", [i.code for i in r.get("issues", [])], [])
    js = r["result"]["files"]["app.js"]
    check("screens 里带 audience（没写的不带）",
          '{"name": "学情", "role": "自定义", "side": "管理", "audience": "教师"}' in js
          and '{"name": "登录", "role": "表单", "side": ""}' in js, True)
    check("导航按 visible 过滤：左边一组、管理那组，整组看不到就不画",
          ".filter(s => !AUTH_SCREENS.includes(s.name)).filter(visible)" in js
          and "screens.filter(s => s.side === '管理').filter(visible)" in js
          and "screens.some(s => s.side === '管理' && visible(s))" in js, True)
    check("visible 认 role / role_label；首页、直接打地址都按它；先认人再进第一个界面",
          "s.audience !== m.role && s.audience !== m.roleLabel" in js
          and "!hiddenScreen(s.name)" in js and "meReady.then(() => { if (!leaving) onRoute(); })" in js, True)
    check("顶栏的标识和按角色的 class", 'class="nav-badge"' in js and "'nav-role-' + me.role" in js, True)
    # 没有 auth_me 的项目：visible 恒真，照旧直接进第一个界面
    r2 = compile_ui(ui, backend="vue", fields={"username": "文本"},
                    options={"endpoints": {"report_one": "/report/one"}})
    js2 = r2["result"]["files"]["app.js"]
    check("没有 auth_me：visible 恒真、不等认人", "const visible = () => true;" in js2
          and "meReady" not in js2 and "me.badge" not in js2, True)
    check("没拆页面：PAGE 是不分端的主页面", 'const PAGE = {"end": "", "main": true, "role": "", "badge": "", '
          '"ends": {}, "home": null, "elsewhere": {}};' in js2, True)
    # 按端拆出来的页面（gen/project.py 的 split_pages 传进来的 page）
    page = {"end": "教师", "main": False, "role": "teacher", "badge": "教师端",
            "ends": {"学生": "/", "教师": "/teacher"}, "home": {"path": "/", "label": "打开学生端"},
            "elsewhere": {"做题": "学生"}}
    r3 = compile_ui(ui, backend="vue", fields={"username": "文本"},
                    options={"endpoints": eps, "page": page, "title": "日语学习·教师端"})
    js3 = r3["result"]["files"]["app.js"]
    check("page 进了 PAGE", '"elsewhere": {"做题": "学生"}' in js3 and '"badge": "教师端"' in js3, True)
    check("别的端的界面：地址打了不进（hiddenScreen 认 elsewhere），登录的人不是这一端就送走或拒",
          "s ? !visible(s) : elsewhere(name)" in js3 and "checkEnd(fresh)" in js3
          and "leaveTo(there)" in js3 and "这里打不开，已回到首页" in js3, True)
    check("顶栏：页面的标识、代号 class、「打开学生端」；登录页上方标出是哪一端",
          "PAGE.badge || me.badge" in js3 and "'nav-role-' + PAGE.role" in js3
          and 'class="nav-home"' in js3 and 'class="page-end"' in js3, True)
    check("标题", "<title>日语学习·教师端</title>" in r3["result"]["files"]["index.html"], True)
    r4 = compile_ui(ui, backend="vue", fields={"username": "文本"},
                    options={"endpoints": {"report_one": "/report/one"}, "page": page})
    js4 = r4["result"]["files"]["app.js"]
    check("没有 auth_me 也守地址：一打开就 guardSide", "\n    guardSide();\n" in js4
          and "elsewhere(name)" in js4 and "checkEnd" not in js4, True)

def test_side_poll_row_remote():
    print("\n[侧、每隔、列表行上的远程动作、打开浮层留着参数]")
    ui = ("界面 自定义 教材\n"
          "  文案 学生的页\n"
          "结束\n"
          "界面 自定义 教材导入 侧 管理 载入 import_load\n"
          "  动作 import_poll 远程 隐藏 每隔 2 当 params.job&&shared.job.running 轮询\n"
          "  列表 块表 绑 chunks\n"
          "    列 title 标题\n"
          "    动作 chunk_retry 远程 带 chunk_id 当 row.state==='出错' 重试\n"
          "  结束\n"
          "  动作 ask_delete 危险 打开 确认删除 删除\n"
          "  浮层 确认删除\n"
          "    动作 job_delete 远程 关闭 危险 确认删除\n"
          "  结束\n"
          "结束\n")
    from tools.ui import parse
    screens = parse(ui)
    check("「侧 管理」进 side，不进名字", (screens[1].name, screens[1].side, screens[1].load),
          ("教材导入", "管理", "import_load"))
    check("没写侧的是空", screens[0].side, "")
    poll = screens[1].children[0]
    check("「每隔 2」进 every，「当」照旧", (poll.every, poll.when, poll.label, poll.has("隐藏")),
          (2, "params.job&&shared.job.running", "轮询", True))
    eps = {"import_poll": "/import/poll", "chunk_retry": "/c/r", "job_delete": "/j/d",
           "import_load": "/import/load"}
    r = compile_ui(ui, backend="vue", fields={"title": "文本"}, options={"endpoints": eps})
    check("编译没有 issue", [i.code for i in r.get("issues", [])], [])
    js = r["result"]["files"]["app.js"]
    check("导航：没写侧的在左，管理那组推到右边、带组名",
          'screens.filter(s => !s.side)' in js and 'class="nav-side" style="margin-left:auto"' in js
          and '<span class="nav-side-h">管理</span>' in js
          and "screens.filter(s => s.side === '管理')" in js, True)
    check("每隔：一个跟着「当」的 <zs-poll>，组件和 pollOnce 都生成了",
          '<zs-poll action="import_poll" :every="2" v-if="params.job&&shared.job.running"></zs-poll>' in js
          and '_app.component("ZsPoll"' in js and "async function pollOnce(name)" in js, True)
    check("隐藏的动作不画按钮", "submitTo('import_poll')" in js, False)
    check("行上的远程动作：onRowRemote 带这一行的 chunk_id，「当」里能用 row",
          "onRowRemote('chunk_retry', row, 'chunk_id')" in js and 'v-if="row.state===\'出错\'"' in js
          and "async function onRowRemote(name, row, carry)" in js, True)
    check("界面上的「打开」浮层留着地址参数（keep）", "showOverlay('确认删除', null, true)" in js, True)
    check("返回的 go 可以带参数（#界面?参数）", 'resp.go.startsWith("#")' in js, True)
    plain = compile_ui("界面 自定义 甲\n  文案 x\n结束\n界面 自定义 乙\n  文案 y\n结束\n",
                       backend="vue", fields={})["result"]["files"]["app.js"]
    check("对照：没有侧、每隔、行上远程的项目一行相关代码都不生成",
          ("nav-side" in plain, "ZsPoll" in plain, "onRowRemote" in plain), (False, False, False))
    bad = compile_ui("界面 自定义 甲\n  动作 x 每隔 3 刷新\n结束\n", backend="vue", fields={},
                     options={"endpoints": {"x": "/x"}})
    check("每隔配的不是远程动作：报 every_not_remote",
          [i.code for i in bad.get("issues", [])], ["every_not_remote"])
    bad2 = compile_ui("界面 自定义 甲\n  动作 x 远程 每隔 3 刷新\n结束\n", backend="vue", fields={},
                      options={"endpoints": {"y": "/y"}})
    check("每隔的接口不存在：报 missing_endpoint",
          [i.code for i in bad2.get("issues", []) if "每隔" in i.message], ["missing_endpoint"])


def test_order_narrow():
    print("\n[界面「序」、窄屏样式]")
    from tools.ui import dump
    ss = parse("界面 自定义 问老师 端 学生 序 1 侧 看看\n  文案 a\n结束\n"
               "界面 自定义 做题\n  文案 b\n结束\n")
    check("「序 1」进 order，不进名字，跟端、侧一起写互不干扰",
          (ss[0].name, ss[0].order, ss[0].audience, ss[0].side), ("问老师", 1, "学生", "看看"))
    check("没写序的是 None（不是 0：序 0 是合法的）", (ss[1].order, one("界面 自定义 甲 序 0\n  文案 a\n结束\n").order),
          (None, 0))
    check("dump 带「序=1」", "序=1" in dump(ss), True)
    act = one("界面 自定义 甲\n  动作 go 提交 序 1\n结束\n").children[0]
    check("「序」只认界面上的：写在动作上不进 order", act.order, None)
    check_raises("序不是非负整数：解析报错、说清写的是什么",
                 lambda: parse("界面 自定义 甲 序 一\n  文案 a\n结束\n"), "「序」要写非负整数")
    check_raises("负数也报", lambda: parse("界面 自定义 甲 序 -1\n  文案 a\n结束\n"), "序")
    css = compile_ui("界面 自定义 甲\n  文案 x\n结束\n", backend="vue",
                     fields={})["result"]["files"]["style.css"]
    check("样式表有窄屏那段 @media", "@media (max-width:640px)" in css, True)
    narrow = css[css.index("@media (max-width:640px)"):]
    check("窄屏：导航不换行横滚、横排里的区域占整行（堆叠）、表格横滚、网格单列",
          all(x in narrow for x in ("flex-wrap:nowrap; overflow-x:auto",
                                    "> .region", "flex:1 1 100% !important",
                                    ".table-wrap { overflow-x:auto", "grid-template-columns:1fr !important")),
          True)
    check("宽屏规则没动：@media 前面 nav、.row 还是原样",
          ("nav {\n  display:flex; gap:8px; align-items:center;\n  padding:12px 20px 0;" in css,
           ".row { display:flex; gap:12px; align-items:flex-start; }" in css), (True, True))


def test_state_lists_sync():
    print("\n[页面状态里的列表同步进 lists]")
    ui = ("界面 自定义 学情 载入 report_home\n"
          "  文案 当 lists.class_rows&&!lists.class_rows.length 还没有学生\n"
          "  列表 全班表 绑 class_rows 当 lists.class_rows&&lists.class_rows.length\n"
          "    列 label 学生\n"
          "  结束\n"
          "结束\n")
    r = compile_ui(ui, backend="vue", options={"endpoints": {"report_home": "/report/home"}})
    check("编译没有 issue", [i.code for i in r.get("issues", [])], [])
    js = r["result"]["files"]["app.js"]
    check("表格外层的 v-if 直接读 lists（所以 state 里的列表必须同步进 lists）",
          '<section class="table-wrap" v-if="lists.class_rows&&lists.class_rows.length">' in js, True)
    i_sync = js.find("if (Array.isArray(v)) lists.value[k] = v;")
    i_lists = js.find("if (resp.lists && typeof resp.lists")
    check("applyResponse 把 state 顶层的数组键同步进 lists", i_sync > 0, True)
    check("同步在 resp.lists 之前：两边都给时 lists 那份算数", 0 < i_sync < i_lists, True)

    import shutil, subprocess
    node = shutil.which("node")
    a, b = js.find("function applyResponse(resp) {"), js.find("function followGo(")
    if not node or a < 0 or b < a:
        print("  - 没有 node，跳过行为检查")
        return
    harness = (
        "const shared={value:{}}, lists={value:{}}, current={value:{name:'学情'}};\n"
        "const myStream=()=>'', fillForm=()=>{}, showNotice=()=>{}, followGo=()=>{}, showOverlay=()=>{}, closeOverlay=()=>{};\n"
        + js[a:b] +
        "\napplyResponse({state:{class_rows:[{label:'小明'}], empty:[], text:'x', nested:{k:[1]}}});\n"
        "const first = JSON.stringify(lists.value);\n"
        "applyResponse({state:{class_rows:[{label:'旧'}]}, lists:{class_rows:[{label:'新'}]}});\n"
        "console.log(JSON.stringify({first, second: lists.value.class_rows}));\n")
    p = subprocess.run([node, "-e", harness], capture_output=True, text=True, timeout=30)
    import json as _json
    try:
        got = _json.loads(p.stdout.strip().splitlines()[-1])
    except Exception:
        got = {"错误": (p.stdout + p.stderr)[-300:]}
    check("state 里的数组（含空数组）同步，标量和嵌套里的不同步",
          got.get("first"), '{"class_rows":[{"label":"小明"}],"empty":[]}')
    check("响应同时带 lists 时 lists 覆盖 state 同名键", got.get("second"), [{"label": "新"}])


def test_msg_actions():
    print("\n[消息流「按钮」：消息带按钮（E1）]")
    from tools.ui import dump
    ui = ("界面 自定义 助手\n"
          "  消息流 talk 占满 按钮 draft_confirm,draft_drop\n"
          "  分组 底 底栏\n"
          "    字段 content 控件 多行\n"
          "    动作 send 提交 远程 发送\n"
          "  结束\n"
          "结束\n"
          "界面 自定义 别处\n"
          "  消息流 chat 占满\n"
          "结束\n")
    ss = parse(ui)
    st = ss[0].children[0]
    check("「按钮 a,b」进 buttons，不进名字、标签；占满照旧",
          (st.kind, st.name, st.label, st.buttons, st.has("占满")),
          ("消息流", "talk", "talk", "draft_confirm,draft_drop", True))
    check("dump 带「按钮=…」", "按钮=draft_confirm,draft_drop" in dump(ss), True)
    eps = {"send": "/send", "draft_confirm": "/d/ok", "draft_drop": "/d/drop"}
    r = compile_ui(ui, backend="vue", fields={"content": "文本"}, options={"endpoints": eps})
    # 两个界面各一条流会出 ambiguous_stream 那条提示（不挡编译），跟按钮无关，排除
    check("编译没有 issue（白名单里的动作不用另写「动作 … 远程」）",
          [i.code for i in r.get("issues", []) if i.code != "ambiguous_stream"], [])
    js = r["result"]["files"]["app.js"]
    css = r["result"]["files"]["style.css"]
    check("白名单按消息流名生成：只有写了按钮的 talk，没写的 chat 不在表里",
          'const streamActions = {"talk": ["draft_confirm", "draft_drop"]};' in js, True)
    check("talk 的消息下画按钮：v-for 过 msgActions、点了 onMsgAction，标签走 {{ }} 转义",
          ("msgActions('talk', m)" in js, "@click=\"onMsgAction('talk', a)\"" in js,
           "{{ a.label || a.action }}" in js, 'class="smsg-actions"' in js), (True, True, True, True))
    check("kind：primary / danger / 其余普通按钮；请求中锁住",
          ":class=\"a.kind === 'primary' ? 'btn-primary' : (a.kind === 'danger' ? 'btn-danger' : 'btn-ghost')\"" in js
          and ':disabled="busy"' in js, True)
    check("带按钮的消息加 smsg-card；样式表有 .smsg-card / .smsg-actions",
          ("'smsg-card'" in js, ".smsg-card {" in css, ".smsg-actions {" in css), (True, True, True))
    check("没写按钮的 chat 流照旧：不调 msgActions",
          "msgActions('chat'" in js, False)
    check("onMsgAction 生成、导出给模板", "async function onMsgAction(stream, a)" in js
          and ", msgActions, onMsgAction" in js, True)

    plain_ui = "界面 自定义 甲\n  消息流 chat 占满\n  动作 send 提交 远程 发\n结束\n"
    plain = compile_ui(plain_ui, backend="vue", options={"endpoints": {"send": "/s"}})["result"]["files"]
    check("对照：没写「按钮」的项目一行相关代码、一条相关样式都不生成",
          ("msgActions" in plain["app.js"], "onMsgAction" in plain["app.js"],
           "streamActions" in plain["app.js"], "smsg-card" in plain["style.css"],
           "smsg-actions" in plain["style.css"]), (False, False, False, False, False))
    check("对照：没写按钮的消息流还是原来那行 :class",
          ":class=\"'smsg-' + (m.kind || 'text')\">\n<span class=\"who\">" in plain["app.js"], True)

    miss = compile_ui(ui, backend="vue", fields={"content": "文本"},
                      options={"endpoints": {"send": "/send", "draft_confirm": "/d/ok"}})
    check("白名单里的动作没有接口：报 missing_endpoint，点名是哪个",
          [(i.code, "draft_drop" in i.message) for i in miss["issues"] if i.code != "ambiguous_stream"],
          [("missing_endpoint", True)])
    empty = compile_ui("界面 自定义 甲\n  消息流 chat 按钮 a,,b\n结束\n", backend="vue",
                       options={"endpoints": {"a": "/a", "b": "/b"}})
    check("白名单里有空名字（a,,b）：报 empty_button", [i.code for i in empty["issues"]], ["empty_button"])
    bare = compile_ui("界面 自定义 甲\n  消息流 chat 占满 按钮\n结束\n", backend="vue")
    check("行尾只写「按钮」没写动作（被当成标签）：报 empty_button",
          [i.code for i in bare["issues"]], ["empty_button"])
    blank = compile_ui("界面 自定义 甲\n  消息流 chat 按钮 ,\n结束\n", backend="vue")
    bjs = blank["result"]["files"]["app.js"]
    check("白名单全是空名（按钮 ,）：报 empty_button，模板和函数两边都不生成（不会调到不存在的 msgActions）",
          ([i.code for i in blank["issues"]], "msgActions" in bjs), (["empty_button"], False))
    wrong = compile_ui("界面 自定义 甲\n  显示 x 按钮 a 标题\n结束\n", backend="vue",
                       options={"endpoints": {"a": "/a"}})
    check("「按钮」写在消息流以外：报 buttons_not_stream",
          [i.code for i in wrong["issues"]], ["buttons_not_stream"])
    from gen.project import BLOCKING
    check("这几种都挡住 gen build", {"missing_endpoint", "empty_button", "buttons_not_stream"} <= BLOCKING, True)

    # 行为：把生成的 msgActions / onMsgAction 抠出来在 node 里跑
    import shutil, subprocess, json as _json
    node = shutil.which("node")
    a = js.find("const streamActions")
    b = js.find("\n    }\n", js.find("async function onMsgAction"))
    if not node or a < 0 or b < a:
        print("  - 没有 node，跳过行为检查")
        return
    harness = (
        "const posted=[], applied=[], pushed=[];\n"
        "const endpoints={send:'/send', draft_confirm:'/d/ok', draft_drop:'/d/drop', evil:'/evil'};\n"
        "const current={value:{name:'助手'}}, route={value:'助手'}, inflight={value:{}};\n"
        "const form={value:{content:'草稿说明', draft_id:'表单里的'}}, params={value:{subject:'s1', '浮层':'x'}};\n"
        "async function postTo(url, body){ posted.push([url, body]); return {messages:[{who:'助手', text:'已确认'}]}; }\n"
        "function applyResponse(r){ applied.push(r); }\n"
        "function pushMessages(s, arr){ pushed.push([s, arr]); }\n"
        "function showNotice(){}\n"
        + js[a:b + 6] +
        "\n(async () => {\n"
        "  const m = {who:'助手', text:'草稿', actions:[\n"
        "    {label:'确认', action:'draft_confirm', carry:{draft_id:7, n:[1,2]}, kind:'primary'},\n"
        "    {label:'越权', action:'evil'}, {label:'坏的'}, null,\n"
        "    {label:'放弃', action:'draft_drop', carry:{draft_id:7}, kind:'danger'}]};\n"
        "  const shown = msgActions('talk', m).map(x => x.action);\n"
        "  const other = msgActions('chat', m).length;\n"
        "  const none = msgActions('talk', {who:'a', text:'b'}).length;\n"
        "  await onMsgAction('talk', m.actions[0]);\n"
        "  await onMsgAction('talk', {label:'越权', action:'evil'});\n"
        "  await onMsgAction('chat', m.actions[4]);\n"
        "  console.log(JSON.stringify({shown, other, none, posted, applied: applied.length, left: inflight.value}));\n"
        "})();\n")
    p = subprocess.run([node, "-e", harness], capture_output=True, text=True, timeout=30)
    try:
        got = _json.loads(p.stdout.strip().splitlines()[-1])
    except Exception:
        got = {"错误": (p.stdout + p.stderr)[-400:]}
    check("只画白名单里的动作（越权的、没 action 的、null 都滤掉），顺序照后端给的",
          got.get("shown"), ["draft_confirm", "draft_drop"])
    check("别的流（没写按钮）、没有 actions 的消息：一个都不画",
          (got.get("other"), got.get("none")), (0, 0))
    check("点「确认」：发到 draft_confirm 的接口，form = 表单 + 地址参数（去掉浮层）+ carry（carry 盖掉同名键）",
          got.get("posted"),
          [["/d/ok", {"action": "draft_confirm",
                      "form": {"content": "草稿说明", "draft_id": 7, "subject": "s1", "n": [1, 2]}}]])
    check("白名单外的动作（evil，接口其实存在）、别的流上的点击：都不发请求；返回交给 applyResponse 一次、锁放开",
          (len(got.get("posted") or []), got.get("applied"), got.get("left")), (1, 1, {}))


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
        test_trigger,
        test_dynamic_select,
        test_side_poll_row_remote,
        test_audience,
        test_order_narrow,
        test_state_lists_sync,
        test_msg_actions,
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
