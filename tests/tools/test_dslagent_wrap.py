# -*- coding: utf-8 -*-
"""K26：接口返回封装改成「模板 + 参数」（约定行「模板 <中文名> 键=值 …」，模板集中在 tools/dslagent/templates/iface/）。不调模型。

    cd /workspace/agent_mcp && .venv/bin/python tests/tools/test_dslagent_wrap.py

一、模板库（tools/dslagent/iftpl）：清单生成、参数校验各错误、渲染（当 块）、信封解释
二、约定解析：模板行（参数、乱序、混写）、K25 旧封装标记现在要报、旧写法（无模板）完全兼容；
    只有「动作」没有「模板」要报（K27a：前端动作的接口要用模板组装返回），动作+模板不报
三、骨架生成：各模板渲染出的路由、结尾不写返回；没写模板的照旧「返回 {r}」
四、约定检查（v3 contracts）：动作名要在 .ui 里、覆盖核对（其余约定齐了才全量查）、没有 .ui 的项目不声明动作
五、比对约定：路由体要和模板渲染出的一致、结尾不能是「返回」、行字段要在实体字段表、动作绑定一致、.ui 覆盖与跨模块重复
六、全局检查：同一动作名两个模块都声明
七、.ui 远程动作提取（tools/ui_actions）：动作 / 表单键 / lists / state / 带；与 .ui 同名动作两处按钮（去重）
八、清单注入：写约定 / 复核约定的输入里有模板清单（planning.user_text / review_user）
九、Router 实跑：scaffold 生成的路由经真引擎 POST {action, form} 返回信封；消息文字带空格走「设」变量原样到前端；
    出错回 {"error"} + 4xx；endpoints_of 绑定
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="dslagent_wrap_"))
os.environ["DSLAGENT_TMP"] = str(TMP / "tmp")
os.environ["DSLAGENT_DATASET"] = str(TMP / "dataset")
os.environ["DSLAGENT_STATE"] = str(TMP / "state")

from tools.dslagent import iftpl as T                              # noqa: E402
from tools.dslagent.packs.dslproj import contract as C, project as P   # noqa: E402
from tools.dslagent.v3 import contracts as VC, globalcheck as GC, scaffold as SF   # noqa: E402
from tools.dslagent.v3 import planning as PL                       # noqa: E402
from tools.dslagent.v3.regress import _envelope                    # noqa: E402
from tools import ui_actions as UA                                 # noqa: E402

PASS = FAIL = 0


def check(cond, msg, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✓ " + msg)
    else:
        FAIL += 1
        print("  ✗ " + msg + (f"\n      {str(extra)[:1500]}" if extra != "" else ""))


def mkproj(name, contracts=None, entities=None, routes=None, services=None, ui=None):
    p = TMP / name
    shutil.rmtree(p, ignore_errors=True)
    for d, files in (("contracts", contracts), ("entities", entities), ("routes", routes),
                     ("services", services), ("ui", ui)):
        for rel, text in (files or {}).items():
            f = p / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(text, encoding="utf-8")
    return p


GOOD_TAIL = """

## 函数
公开 函数 列笔记 owner
  返回 行列表，每行 {title, updated_at}
  伪代码 返回 []

## 接口
POST /note/list -> 列笔记 动作 note_list 模板 列表 键=notes 行=title,updated_at 角色 teacher

## 用例
用例 列笔记_有
  调用 列笔记 owner=u1
  得 有返回
"""


def t_tpl():
    print("模板库：清单 / 校验 / 渲染 / 信封")
    names = T.names()
    check(names == ["列表", "回填", "回复消息", "提交消息", "提交跳转", "提交跳转动态", "状态", "页面状态"],
          "5+3 个模板都在（按中文名排序）", names)
    ls = T.listing()
    for want in ("- 模板 列表：", "- 模板 回填：", "- 模板 提交消息：", "- 模板 提交跳转：", "- 模板 状态：",
                 "键 必填", "例子：POST /notes/list -> 列笔记 动作 note_list 模板 列表 键=notes 行=title,content,created_at"):
        check(want in ls, f"清单含「{want[:40]}」", ls[:200])
    check(T.validate("列表", {"键": "notes", "行": "title,content"}) == [], "列表：键+行 合法", T.validate("列表", {"键": "notes"}))
    check(T.validate("回填", {}) == [], "回填：无参合法")
    check(T.validate("提交跳转", {"消息": "已保存", "跳转": "#首页?浮层=编辑"}) == [], "提交跳转：go 值带 # 和 ? 合法",
          T.validate("提交跳转", {"消息": "已保存", "跳转": "#首页?浮层=编辑"}))
    check(T.validate("提交跳转", {"消息": "x", "跳转": "首页"}) == [], "go：界面名 合法")
    check(T.validate("提交跳转", {"消息": "x", "跳转": "@来处"}) == [], "go：@来处 合法")
    check("不合法" in T.validate("提交跳转", {"消息": "x", "跳转": "首页?a=b"})[0], "go：界面名?参数 不合语法（? 只跟 # 用）→ 报")
    # 校验错误
    check(len(T.validate("不存在", {})) == 1 and "不认识的封装模板" in T.validate("不存在", {})[0], "未知模板 → 报")
    check("缺必填参数 键" in T.validate("列表", {})[0], "缺必填参数 → 报")
    check("缺必填参数 消息、跳转" in T.validate("提交跳转", {})[0], "缺多个必填参数 → 都列出", T.validate("提交跳转", {}))
    check("没有参数「坏」" in T.validate("列表", {"键": "a", "坏": "x"})[0], "多余参数 → 报")
    check("不合法" in T.validate("列表", {"键": "Bad-Key"})[0], "snake 不合法 → 报")
    check("不合法" in T.validate("列表", {"键": "a", "行": "a,,b"})[0], "snake_list 不合法 → 报")
    check("不合法" in T.validate("提交跳转", {"消息": "x", "跳转": "a b"})[0], "go 不合法（空格到不了这里，防手拼）→ 报")
    check("不合法" in T.validate("提交消息", {"消息": ""})[0], "空值 → 报")
    # 渲染：缺省块 / 当 块 / 占位符
    check(T.render("列表", {"键": "notes"}) == ["  表格 notes {r}"], "列表缺省块", T.render("列表", {"键": "notes"}))
    check(T.render("列表", {"键": "notes", "取": "rows"}) == ["  表格 notes {r.rows}"], "列表 当取 块")
    check(T.render("回填", {"取": "row"}) == ["  响应 form {r.row}"], "回填 当取 块")
    check(T.render("提交消息", {"消息": "已保存"}) == ["  设 _msg = 已保存", "  消息 系统 {_msg} ok"],
          "提交消息：先设变量再传（值含空格也不会被切）", T.render("提交消息", {"消息": "已保存"}))
    check(T.render("提交跳转", {"消息": "已保存", "跳转": "笔记", "键": "notes"}) ==
          ["  设 _msg = 已保存", "  表格 notes {r}", "  消息 系统 {_msg} ok", "  响应 go 笔记"],
          "提交跳转 当键：刷新列表 + 消息 + go", T.render("提交跳转", {"消息": "已保存", "跳转": "笔记", "键": "notes"}))
    check(T.render("状态", {"键": "st", "取": "d"}) == ['  响应 state {"st":{r.d}}'], "状态 当取 块")
    check(all("返回" not in l for l in T.render("提交跳转", {"消息": "x", "跳转": "首页"})), "渲染出的路由体没有「返回」行")
    # K28b 新模板：页面状态 / 回复消息 / 提交跳转动态
    check(T.render("页面状态", {}) == ["  响应 state {r}"], "页面状态缺省块：整体铺进 state", T.render("页面状态", {}))
    check(T.render("页面状态", {"取": "page"}) == ["  响应 state {r.page}"], "页面状态 当取 块")
    check(T.validate("页面状态", {"去处": "做题"}) == [], "页面状态：去处 go 值 界面名 合法", T.validate("页面状态", {"去处": "做题"}))
    check(T.validate("页面状态", {"去处": "#做题"}) == [] and T.validate("页面状态", {"去处": "@来处"}) == [],
          "页面状态：去处 #界面 / @来处 合法（做题页「开始」回 #做题 清地址参数）", "")
    check("不合法" in T.validate("页面状态", {"去处": "做题?a=b"})[0], "页面状态：去处 非法 go 值 → 报（选 go 不选 free 的理由：静态校验）", "")
    check(T.render("页面状态", {"表单": "form"}) == ["  响应 state {r}", "  响应 form {r.form}"], "页面状态 当表单 块")
    check(T.render("页面状态", {"去处": "#做题"}) == ["  响应 state {r}", "  响应 go #做题"], "页面状态 当去处 块")
    check(T.render("页面状态", {"取": "page", "表单": "form"}) ==
          ["  响应 state {r.page}", "  响应 form {r.form}"], "页面状态 当取,表单 块：state 铺取的字段 + form 回填")
    check(T.render("页面状态", {"取": "page", "去处": "@来处"}) ==
          ["  响应 state {r.page}", "  响应 go @来处"], "页面状态 当取,去处 块")
    check(T.render("页面状态", {"表单": "form", "去处": "#做题"}) ==
          ["  响应 state {r}", "  响应 form {r.form}", "  响应 go #做题"], "页面状态 当表单,去处 块")
    check(T.render("页面状态", {"取": "page", "表单": "form", "去处": "做题"}) ==
          ["  响应 state {r.page}", "  响应 form {r.form}", "  响应 go 做题"], "页面状态 当取,表单,去处 块：三个可同时出现")
    check(T.render("回复消息", {"谁": "老师", "取": "reply"}) == ["  消息 老师 {r.reply} ok"], "回复消息 当谁,取 块")
    check(T.render("回复消息", {}) == ["  消息 老师 {r} ok"], "回复消息缺省块")
    check(T.validate("提交跳转动态", {"消息": "已建任务", "跳转": "#教材导入?job={r.task_id}"}) == [],
          "提交跳转动态：跳转 free 约束，{r.task_id} 引用合法", T.validate("提交跳转动态", {"消息": "x", "跳转": "#a?job={r.task_id}"}))
    check(T.render("提交跳转动态", {"消息": "已建任务", "跳转": "#教材导入?job={r.task_id}"}) ==
          ["  设 _msg = 已建任务", "  消息 系统 {_msg} ok", "  响应 go #教材导入?job={r.task_id}"],
          "提交跳转动态：跳转引用原样进路由（运行时展开）", "")
    # 信封解释
    e = T.envelope("提交跳转", {"消息": "已保存", "跳转": "笔记", "键": "notes"}, [{"a": 1}])
    check(e == {"lists": {"notes": [{"a": 1}]}, "messages": [{"who": "系统", "text": "已保存", "kind": "ok"}], "go": "笔记"},
          "信封解释：lists + messages + go", e)
    e2 = T.envelope("回填", {"取": "row"}, {"row": {"x": 1}, "其它": 2})
    check(e2 == {"form": {"x": 1}}, "信封解释：取 <字段>", e2)
    e3 = T.envelope("状态", {"键": "st", "取": "d"}, {"d": 3})
    check(e3 == {"state": {"st": 3}}, "信封解释：state 的值是对象不是 JSON 文本", e3)
    e4 = T.envelope("页面状态", {}, {"scope": {"done": 1}, "rows": [2]})
    check(e4 == {"state": {"scope": {"done": 1}, "rows": [2]}}, "信封解释：页面状态整体铺进 state", e4)
    e5 = T.envelope("页面状态", {"取": "page"}, {"page": {"a": 1}})
    check(e5 == {"state": {"a": 1}}, "信封解释：页面状态 取 <字段> 后铺它", e5)
    e6 = T.envelope("回复消息", {"谁": "老师", "取": "reply"}, {"reply": "你好", "ok": 1})
    check(e6 == {"messages": [{"who": "老师", "text": "你好", "kind": "ok"}]}, "信封解释：回复消息取字段进 messages", e6)
    e7 = T.envelope("提交跳转动态", {"消息": "已建任务", "跳转": "#教材导入?job={r.task_id}"}, {"task_id": "job_42"})
    check(e7 == {"messages": [{"who": "系统", "text": "已建任务", "kind": "ok"}], "go": "#教材导入?job=job_42"},
          "信封解释：动态 go 的 {r.字段} 按运行时展开记期望（Router 实测会展开）", e7)
    e8 = T.envelope("提交跳转动态", {"消息": "x", "跳转": "#a?job={r.nope}"}, {})
    check(e8["go"] == "#a?job={r.nope}", "信封解释：go 引用取不到保持原样（与引擎一致）", e8)
    e9 = T.envelope("页面状态", {"表单": "form"}, {"form": {"pick_level": "n3"}, "stat": {"done": 1}})
    check(e9 == {"state": {"form": {"pick_level": "n3"}, "stat": {"done": 1}}, "form": {"pick_level": "n3"}},
          "信封解释：页面状态 表单=form → 整页铺 state + form 回填该字段", e9)
    e10 = T.envelope("页面状态", {"表单": "form", "去处": "#做题"}, {"form": {"a": 1}})
    check(e10 == {"state": {"form": {"a": 1}}, "form": {"a": 1}, "go": "#做题"}, "信封解释：表单+去处 → state/form/go 三键齐", e10)
    e11 = T.envelope("页面状态", {"取": "page", "表单": "form", "去处": "@来处"}, {"page": {"x": 1}, "form": {"y": 2}})
    check(e11 == {"state": {"x": 1}, "form": {"y": 2}, "go": "@来处"}, "信封解释：取+表单+去处 全给 → 各键各取各的", e11)


def t_parse():
    print("约定解析：模板行")
    c, probs = C.parse("模块 note\n依赖 无\n" + GOOD_TAIL)
    check(not probs, "模板行解析无问题", probs)
    i = c["接口"][0]
    check(i["动作"] == "note_list" and i["模板"] == {"名": "列表", "参数": {"键": "notes", "行": "title,updated_at"}},
          "动作 / 模板(名,参数) 解析到位", i)
    check(C.has_wrap(i), "has_wrap 认定封装")
    c2, p2 = C.parse('模块 note\n依赖 无\n\n## 函数\n公开 函数 f a\n  返回 {ok}\n\n## 接口\n'
                     'POST /a -> f 动作 a1 模板 回填 取=rows 角色 student\n'
                     'POST /b -> f 模板 状态 键=st 取=data\n'
                     'POST /c -> f 公开 模板 提交消息 消息=好 上传 file 类型 pdf 上限 20MB\n'
                     'POST /d -> f 模板 提交跳转 消息=好 跳转=@来处 动作 a2\n')
    check(not p2, "模板与 上传/公开/角色/动作 乱序混写解析通过", p2)
    is_ = {x["路径"]: x for x in c2["接口"]}
    check(is_["/a"]["模板"] == {"名": "回填", "参数": {"取": "rows"}}, "回填+取+角色 解析正确", is_["/a"])
    check(is_["/b"]["模板"]["参数"] == {"键": "st", "取": "data"}, "状态模板参数保序", is_["/b"])
    check(is_["/c"]["模板"]["参数"] == {"消息": "好"} and is_["/c"]["上传"]["字段"] == "file", "模板和上传互不干扰", is_["/c"])
    check(is_["/d"]["动作"] == "a2" and is_["/d"]["模板"]["参数"]["跳转"] == "@来处", "模板后面的 动作 仍能解析", is_["/d"])
    # 错误写法
    bad = ('POST /e -> f 模板\n'                          # 缺模板名
           'POST /f -> f 模板 列表 键=a 模板 回填\n'       # 模板重复
           'POST /g -> f 模板 列表 键=a 键=b\n'           # 参数重复
           'POST /h -> f 表格 rows\n'                     # K25 的封装标记现在不认识了
           'POST /i -> f 消息 已保存\n'                   # 同上
           'POST /j -> f 模板 列表 键=a 取\n')            # 「取」没有 =，当普通标记 → 不认识
    _, p3 = C.parse("模块 note\n依赖 无\n\n## 函数\n公开 函数 f a\n  返回 {ok}\n\n## 接口\n" + bad)
    for want in ("「模板」后面要跟模板中文名", "「模板」只能写一次", "模板参数「键」重复",
                 "不认识的接口标记「表格」", "不认识的接口标记「消息」", "不认识的接口标记「取」"):
        check(any(want in x for x in p3), f"错误写法报出「{want}」", p3)
    # K27a：只有「动作」没有「模板」→ 报（前端动作的接口要用模板组装返回，报错里列出可用模板）；动作+模板 → 不报；
    # 都没有 → 旧行为（t_compat）
    c5, p5 = C.parse("模块 note\n依赖 无\n\n## 函数\n公开 函数 f a\n  返回 {ok}\n\n## 接口\n"
                     "POST /k -> f 动作 a9\nGET /m -> f 动作 a10\n")
    check(not p5, "只有动作没有模板解析无问题", p5)
    pr5 = C.check(c5, "note", {}, ["note"])
    check(any("接口 /k " in x and "没有「模板」" in x and "要用模板组装返回" in x for x in pr5),
          "POST + 只有动作 → 报「要用模板组装返回」", pr5)
    check(any("可用模板：列表、回填、回复消息、提交消息、提交跳转、提交跳转动态、状态、页面状态" in x for x in pr5),
          "报错里列出可用模板中文名", pr5)
    check(any("接口 /m " in x and "方法要写 POST" in x and "动作 a10" in x for x in pr5), "GET + 只有动作 → 也要求 POST", pr5)
    c6, _ = C.parse("模块 note\n依赖 无\n\n## 函数\n公开 函数 f a\n  返回 {ok}\n\n## 接口\n"
                    "POST /k -> f 动作 a9 模板 回填\n")
    pr6 = C.check(c6, "note", {}, ["note"])
    check(all("a9" not in x for x in pr6), "动作+模板 → 不报", pr6)
    # 只有动作的约定过不了检查，不再为它生成「只绑动作」的路由（route_body 总是按模板渲染，渲染不出就炸出来）
    try:
        SF.route_text("note", c5)
        check(False, "只有动作没有模板 → 骨架炸 ValueError（兼容分支已不可达）", "没有抛")
    except ValueError as e:
        check("模板" in str(e), "只有动作没有模板 → 骨架炸 ValueError（兼容分支已不可达）", e)
    # 约定检查：参数校验各错误、动作名 / 唯一 / POST
    c4, _ = C.parse("模块 note\n依赖 无\n\n## 函数\n公开 函数 f a\n  返回 {ok}\n\n## 接口\n"
                    "GET /x -> f 模板 列表 键=rows\n"
                    "POST /y -> f 模板 列表\n"
                    "POST /z -> f 模板 乱来 键=a\n"
                    "POST /w -> f 模板 列表 键=a 坏=x\n"
                    "POST /v -> f 模板 列表 键=Bad 行=x,,y\n")
    pr = C.check(c4, "note", {}, ["note"])
    check(any("方法要写 POST" in x for x in pr), "GET + 模板 → 要求 POST", pr)
    check(any("缺必填参数 键" in x for x in pr), "缺必填参数 → 报", pr)
    check(any("不认识的封装模板「乱来」" in x for x in pr), "未知模板 → 报", pr)
    check(any("没有参数「坏」" in x for x in pr), "多余参数 → 报", pr)
    check(any("键=Bad" in x and "不合法" in x for x in pr), "键不合法 → 报", pr)
    check(any("行=x,,y" in x for x in pr), "行不合法 → 报", pr)


OLD_TAIL = """

## 函数
公开 函数 f a
  返回 {ok}
  伪代码 返回 {"ok": 1}

公开 函数 收 a file_path
  返回 {ok}
  伪代码 返回 {"ok": 1}

## 接口
GET /x/one -> f
POST /x/up -> 收 上传 file 类型 pdf,txt 上限 20MB 角色 teacher

## 用例
用例 f_有
  调用 f a=1
  得 有返回

用例 收_有
  调用 收 a=1 file_path=doc.md
  得 有返回
"""


def t_compat():
    print("旧写法兼容（没写模板的接口行为不变）")
    c, probs = C.parse("模块 x\n依赖 无\n" + OLD_TAIL)
    check(not probs, "旧接口行（GET / 上传 / 角色）解析无问题", probs)
    i = c["接口"][1]
    check(i["上传"] == {"字段": "file", "类型": "pdf,txt", "上限": "20MB"} and not C.has_wrap(i)
          and i["动作"] == "" and i["模板"] is None, "上传字段原样，模板为缺省", i)
    check(C.check(c, "x", {}, ["x"]) == [], "旧约定检查通过", C.check(c, "x", {}, ["x"]))
    rt = SF.route_text("x", c)
    check("接口 GET /x/one" in rt and "  返回 {r}\n结束" in rt and "动作" not in rt.replace("动作 name", ""),
          "旧接口的骨架照旧生成「返回 {r}」", rt)


def t_scaffold():
    print("骨架生成：模板接口的路由")
    c, _ = C.parse("模块 note\n依赖 无\n" + GOOD_TAIL)
    rt = SF.route_text("note", c)
    check("接口 POST /note/list 动作 note_list 角色 teacher" in rt, "接口行带 动作 与 角色（动作在前，路由行的解析顺序）", rt)
    check("  设 r = 调用 note.列笔记 owner={owner}\n  表格 notes {r}\n结束" in rt, "调用 → 表格 组装，结尾不写返回", rt)
    c2, _ = C.parse('模块 note\n依赖 无\n\n## 函数\n公开 函数 f a b?\n  返回 {ok}\n\n## 接口\n'
                    'POST /a -> f 动作 a1 模板 提交跳转 消息=已保存 跳转=@来处\n'
                    'POST /b -> f 动作 a2 模板 回填 取=rows\n'
                    'POST /c -> f 动作 a3 模板 状态 键=st 取=data\n')
    rt2 = SF.route_text("note", c2)
    for want in ("动作 a1", "  设 _msg = 已保存", "  消息 系统 {_msg} ok", "  响应 go @来处",
                 "  响应 form {r.rows}", '  响应 state {"st":{r.data}}', "调用 note.f a={a} b={b 或}"):
        check(want in rt2, f"组装行含「{want}」", rt2)
    check(rt2.count("返回") == 0, "模板接口的路由没有「返回」行", rt2)
    # 渲染失败（约定检查漏网时骨架要炸出来，不能静默生成错路由）
    c3, _ = C.parse('模块 note\n依赖 无\n\n## 函数\n公开 函数 f a\n  返回 {ok}\n\n## 接口\nPOST /a -> f 模板 回填 取=rows\n')
    c3["接口"][0]["模板"]["名"] = "不存在"
    try:
        SF.route_text("note", c3)
        check(False, "未知模板渲染 → 抛 ValueError", "没有抛")
    except ValueError as e:
        check("不认识的封装模板" in str(e), "未知模板渲染 → 抛 ValueError", e)


def t_fixed_renamed():
    print("K28b：「传 定值」「参数 改名」：解析 / 校验 / 调用行 / 比对")
    TAIL = ("## 函数\n"
            "公开 函数 设置学生停用 username disabled\n  返回 {ok}\n  伪代码 返回 {\"ok\": 1}\n\n"
            "公开 函数 重置学生密码 username new_password\n  返回 {ok}\n  伪代码 返回 {\"ok\": 1}\n\n"
            "公开 函数 开始练习 learner mode? level?\n  返回 {ok}\n  伪代码 返回 {\"ok\": 1}\n\n"
            "## 接口\n"
            "POST /students/disable -> 设置学生停用 动作 student_disable 模板 列表 键=students 传 disabled=1 角色 teacher\n"
            "POST /students/reset -> 重置学生密码 动作 student_reset 模板 提交消息 消息=已重置 参数 reset_user=username\n"
            "POST /quiz/start -> 开始练习 动作 quiz_start 模板 页面状态 传 mode=lesson 参数 pick_level=level\n"
            "POST /students/opt -> 设置学生停用 动作 student_opt 模板 列表 键=students 传 disabled=1 参数 user=username\n\n"
            "## 用例\n"
            "用例 停用_有\n  调用 设置学生停用 username=u1 disabled=1\n  得 有返回\n"
            "用例 重置_有\n  调用 重置学生密码 username=u1 new_password=x\n  得 有返回\n"
            "用例 开始_有\n  调用 开始练习 learner=u1 mode=lesson\n  得 有返回\n")
    ctext = "模块 account\n依赖 无\n\n" + TAIL
    c, probs = C.parse(ctext)
    check(not probs, "传/参数与 模板/动作/角色 混写解析无问题", probs)
    is_ = {x["路径"]: x for x in c["接口"]}
    check(is_["/students/disable"]["传"] == {"disabled": "1"} and is_["/students/disable"]["参数"] == {},
          "传 解析成 入参→定值（没写 参数 是空）", is_["/students/disable"])
    check(is_["/students/reset"]["参数"] == {"reset_user": "username"}, "参数 解析成 前端键→入参", is_["/students/reset"])
    check(is_["/quiz/start"]["传"] == {"mode": "lesson"} and is_["/quiz/start"]["参数"] == {"pick_level": "level"},
          "可选入参也能「传」/改名", is_["/quiz/start"])
    pr = C.check(c, "account", {}, ["account"])
    check(pr == [], "入参都在函数头 → 约定检查通过", pr)
    fns = {f["名"]: f for f in c["函数"]}
    b1 = C.route_body("account", is_["/students/disable"], fns["设置学生停用"])
    check(b1[0] == "  设 r = 调用 account.设置学生停用 username={username} disabled=1", "定值参数写进调用行（字面值）", b1)
    b2 = C.route_body("account", is_["/students/reset"], fns["重置学生密码"])
    check(b2[0] == "  设 r = 调用 account.重置学生密码 username={reset_user} new_password={new_password}",
          "改名参数写 函数入参={前端键}，其余照旧 p={p}", b2)
    b3 = C.route_body("account", is_["/quiz/start"], fns["开始练习"])
    check(b3[0] == "  设 r = 调用 account.开始练习 learner={learner} mode=lesson level={pick_level 或}",
          "可选入参改名写 {前端键 或}；定值不带 或", b3)
    check(C.form_args(is_["/students/reset"], {"username": "u1", "new_password": "x"}) ==
          {"reset_user": "u1", "new_password": "x"}, "冒烟表单：改名键替换函数入参名", "")
    check(C.form_args(is_["/students/disable"], {"username": "u1", "disabled": "1"}) == {"username": "u1"},
          "冒烟表单：定值入参不发（前端没有这个键）", "")
    check(C.form_args(is_["/students/opt"], {"username": "u1", "disabled": "1"}) == {"user": "u1"},
          "冒烟表单：改名 + 定值一起生效", "")

    def parse_bad(line):
        bad = ("## 函数\n公开 函数 设置学生停用 username disabled\n  返回 {ok}\n\n## 接口\n" + line +
               "\n\n## 用例\n用例 停用_有\n  调用 设置学生停用 username=u1 disabled=1\n  得 有返回\n")
        return C.parse("模块 account\n依赖 无\n\n" + bad)

    _, p1 = parse_bad("POST /b -> 设置学生停用 动作 b1 模板 列表 键=students 传\n")
    check(any("「传」后面要跟 入参=定值" in x for x in p1), "传 后面没跟 入参=定值 → 报", p1)
    _, p2 = parse_bad("POST /b -> 设置学生停用 动作 b2 模板 列表 键=students 传 disabled=\n")
    check(any("「传 disabled=」缺定值" in x and "不能带空格" in x for x in p2), "定值为空 → 报（说明定值不能带空格）", p2)
    _, p3 = parse_bad("POST /b -> 设置学生停用 动作 b3 模板 列表 键=students 传 disabled=1 传 disabled=2\n")
    check(any("「传」只能写一次" in x for x in p3), "传 重复 → 报", p3)
    _, p4 = parse_bad("POST /b -> 设置学生停用 动作 b4 模板 列表 键=students 传 disabled=1 disabled=2\n")
    check(any("「传」的入参「disabled」重复" in x for x in p4), "同一入参传两次 → 报", p4)
    _, p5 = parse_bad("POST /b -> 设置学生停用 动作 b5 模板 列表 键=students 参数\n")
    check(any("「参数」后面要跟 前端键=函数入参" in x for x in p5), "参数 后面没跟 前端键=函数入参 → 报", p5)
    _, p6 = parse_bad("POST /b -> 设置学生停用 动作 b6 模板 列表 键=students 参数 Reset_User=username\n")
    check(any("前端键「Reset_User」要用英文 snake" in x for x in p6), "前端键不是 snake → 报", p6)
    _, p7 = parse_bad("POST /b -> 设置学生停用 动作 b7 模板 列表 键=students 参数 a=username b=username\n")
    check(any("入参「username」已经被「参数」映射过" in x for x in p7), "同一入参映射两个前端键 → 报", p7)
    _, p8 = parse_bad("POST /b -> 设置学生停用 动作 b8 模板 列表 键=students 传 disabled=1 参数 x=disabled\n")
    check(any("「传 disabled=1」和「参数 x=disabled」撞了同一个入参「disabled」" in x and "二选一" in x for x in p8),
          "同一入参既传又改名（解析层）→ 报", p8)
    _, p8b = parse_bad("POST /b -> 设置学生停用 动作 b8 模板 列表 键=students 参数 x=disabled 传 disabled=1\n")
    check(any("「传 disabled=1」和「参数 x=disabled」撞了同一个入参「disabled」" in x for x in p8b),
          "同一入参既传又改名（先参数后传，顺序不限）→ 报", p8b)
    _, p9 = parse_bad("POST /b -> 设置学生停用 动作 b9 模板 列表 键=students 传 disabled=1 参数 disabled=username\n")
    check(any("前端键「disabled」和「传」的入参重名" in x for x in p9), "前端键撞「传」的入参名 → 报", p9)
    _, p9b = parse_bad("POST /b -> 设置学生停用 动作 b9 模板 列表 键=students 参数 disabled=username 传 disabled=1\n")
    check(any("前端键「disabled」和「传」的入参重名" in x for x in p9b), "前端键撞「传」的入参名（先参数后传）→ 报", p9b)
    check(C.route_call_args(is_["/students/disable"], {"username": "u1", "disabled": "0"}) ==
          {"username": "u1", "disabled": "1"}, "直接调用取参：定值入参用约定字面值（路由语义）", "")
    check(C.route_call_args(is_["/students/reset"], {"username": "u1"}) == {"username": "u1"},
          "直接调用取参：没写「传」原样", "")

    def check_bad(line, fnhead="公开 函数 设置学生停用 username disabled\n  返回 {ok}\n\n"):
        bad = ("## 函数\n" + fnhead + "## 接口\n" + line +
               "\n\n## 用例\n用例 停用_有\n  调用 设置学生停用 username=u1 disabled=1\n  得 有返回\n")
        cc, pp = C.parse("模块 account\n依赖 无\n\n" + bad)
        return C.check(cc, "account", {}, ["account"])

    pr1 = check_bad("POST /b -> 设置学生停用 动作 b1 模板 列表 键=students 传 nope=1")
    check(any("「传 nope=1」的 nope 不是函数「设置学生停用」的入参" in x for x in pr1), "传 的入参不在函数头 → 报", pr1)
    pr2 = check_bad("POST /b -> 设置学生停用 动作 b2 模板 列表 键=students 参数 other=nope")
    check(any("「参数 other=nope」的 nope 不是函数「设置学生停用」的入参" in x for x in pr2), "参数 的入参不在函数头 → 报", pr2)
    pr2b = check_bad("POST /b -> 双停用 动作 b2b 模板 列表 键=students 参数 user=username",
                     fnhead="公开 函数 双停用 username user disabled\n  返回 {ok}\n\n")
    check(any("前端键「user」和函数入参「user」重名" in x for x in pr2b), "前端键撞别的函数入参 → 报（一个表单键喂两个入参）", pr2b)
    pr3 = check_bad("POST /b -> 设置学生停用 传 disabled=1")
    check(any("「传 …」「参数 …」只对声明了「模板」的封装接口有意义" in x for x in pr3), "没写模板的接口传/改名 → 报", pr3)
    pr4 = check_bad("POST /b -> 收文件 动作 b4 模板 提交消息 消息=收了 上传 file 传 file_path=x",
                    fnhead="公开 函数 收文件 file_path\n  返回 {ok}\n\n")
    check(any("「file_path」由「上传 file」的存盘路径传入" in x for x in pr4), "上传存盘路径被 传 改写 → 报", pr4)
    # 骨架 + 比对：生成的调用行带定值/改名；手改回旧写法比对要报
    entities = {"entities/account_user.entity":
                "实体 account_user 学生\n  字段 username 文本 必填 用户名\n  字段 disabled 整数 停用\n  字段 extra 文本 页面列\n结束\n"}
    services = {"services/account.zs": "业务 account\n  用包 common\n\n"
                                        "  公开 函数 设置学生停用 username disabled\n    返回 []\n  结束\n\n"
                                        "  公开 函数 重置学生密码 username new_password\n    返回 []\n  结束\n\n"
                                        "  公开 函数 开始练习 learner mode? level?\n    返回 []\n  结束\n结束\n"}
    ui = {"ui/account.ui": "界面 列表 学生管理\n  动作 student_disable 远程 进入时\n  动作 student_reset 远程\n"
                           "  动作 quiz_start 远程\n  动作 student_opt 远程\n  列表 表 绑 students\n"
                           "    列 username 用户名\n    列 extra 页面列\n  结束\n结束\n"}
    rt = SF.route_text("account", c)
    check("调用 account.设置学生停用 username={username} disabled=1" in rt, "骨架调用行带定值", rt)
    check("调用 account.重置学生密码 username={reset_user} new_password={new_password}" in rt, "骨架调用行带改名", rt)
    p2_ = mkproj("fr_ok", {"contracts/account.md": ctext}, entities, {"routes/account.zs": rt}, services, ui)
    cc, _ = P.load_contract(p2_, "account")
    d = P.compare(p2_, "account", cc, ["account"])
    check(d["一致"], "比对：路由与渲染逐行一致（定值/改名共用 route_body，自动跟随）", d["差异"])
    hand1 = rt.replace("username={username} disabled=1", "username={username} disabled={disabled}")
    q = mkproj("fr_fix", {"contracts/account.md": ctext}, entities, {"routes/account.zs": hand1}, services, ui)
    cc2, _ = P.load_contract(q, "account")
    d2 = P.compare(q, "account", cc2, ["account"])
    check(not d2["一致"], "比对：定值被手改回引用 → 差异", d2["差异"])
    hand2 = rt.replace("username={reset_user} new_password={new_password}", "username={username} new_password={new_password}")
    q = mkproj("fr_ren", {"contracts/account.md": ctext}, entities, {"routes/account.zs": hand2}, services, ui)
    cc3, _ = P.load_contract(q, "account")
    d3 = P.compare(q, "account", cc3, ["account"])
    check(not d3["一致"], "比对：改名被手改回旧键 → 差异", d3["差异"])


def t_v3check():
    print("约定检查（v3）：.ui 动作")
    from tools.dslagent.v3 import top as VT
    top = VT.load("项目 demo\n模块 note\n")
    # 项目没有 .ui 却声明动作
    p = mkproj("v3_noui", {"contracts/note.md": "模块 note\n依赖 无\n" + GOOD_TAIL})
    probs = VC.check((p / "contracts" / "note.md").read_text(encoding="utf-8"), "note", top, p)
    check(any("没有 ui/*.ui" in x and "note_list" in x for x in probs), "没有 .ui 的项目声明动作 → 报", probs)
    # 有 .ui：声明的动作必须在 .ui 里；覆盖在其余约定齐了才全量查
    ui = {"ui/note.ui": "界面 列表 笔记列表\n  动作 note_list 远程 进入时\n  列表 表 绑 notes\n    列 title 标题\n  结束\n结束\n"}
    p2 = mkproj("v3_ui", {"contracts/note.md": "模块 note\n依赖 无\n" + GOOD_TAIL}, ui=ui)
    ctext = (p2 / "contracts" / "note.md").read_text(encoding="utf-8")
    probs2 = VC.check(ctext, "note", top, p2)
    check(probs2 == [], "声明的动作在 .ui 里、其余模块没写完（不查覆盖）→ 无问题", probs2)
    # 改一个 .ui 没有的动作名 → 报
    bad = GOOD_TAIL.replace("动作 note_list", "动作 note_lst")
    p3 = mkproj("v3_ui_bad", {"contracts/note.md": "模块 note\n依赖 无\n" + bad}, ui=ui)
    probs3 = VC.check((p3 / "contracts" / "note.md").read_text(encoding="utf-8"), "note", top, p3)
    check(any("ui/*.ui 里没有这个远程动作" in x for x in probs3), "声明的动作 .ui 里没有 → 报", probs3)
    # 覆盖：其余模块的约定都在盘上时，缺的 .ui 动作要报
    top2 = VT.load("项目 demo\n模块 note\n模块 memo\n")
    (p2 / "contracts" / "memo.md").write_text("模块 memo\n依赖 无\n\n## 函数\n公开 函数 g a\n  返回 {ok}\n\n## 用例\n用例 g_有\n  调用 g a=1\n  得 有返回\n",
                                              encoding="utf-8")
    (p2 / "ui" / "memo.ui").write_text("界面 列表 便签\n  动作 memo_list 远程 进入时\n  列表 表 绑 memos\n    列 name 名\n  结束\n结束\n",
                                       encoding="utf-8")
    probs4 = VC.check(ctext, "note", top2, p2)
    check(any("「memo_list」还没有任何接口声明" in x for x in probs4), "其余约定齐了，.ui 动作没人声明 → 报", probs4)


def t_compare():
    print("比对约定：路由体按模板逐行比")
    tail = ("POST /note/list -> 列笔记 动作 note_list 模板 列表 键=notes 行=title,updated_at 角色 teacher\n"
            "POST /note/open -> 列笔记 动作 note_open 模板 回填\n"
            "POST /note/go -> 列笔记 动作 note_go 模板 提交跳转 消息=已存 跳转=首页 键=notes\n")
    ctext = ("模块 note\n依赖 无\n\n## 函数\n公开 函数 列笔记 owner\n  返回 行列表\n  伪代码 返回 []\n\n## 接口\n"
             + tail + "\n\n## 用例\n用例 列笔记_有\n  调用 列笔记 owner=u1\n  得 有返回\n")
    entities = {"entities/note_note.entity": "实体 note_note 笔记\n  字段 title 文本 必填 标题\n  字段 updated_at 文本 时间\n  字段 row_only 文本 页面列\n结束\n"}
    routes = {"routes/note.zs":
              "接口 POST /note/list 动作 note_list 角色 teacher\n  设 r = 调用 note.列笔记 owner={owner}\n  表格 notes {r}\n结束\n"
              "接口 POST /note/open 动作 note_open\n  设 r = 调用 note.列笔记 owner={owner}\n  响应 form {r}\n结束\n"
              "接口 POST /note/go 动作 note_go\n  设 r = 调用 note.列笔记 owner={owner}\n  设 _msg = 已存\n  表格 notes {r}\n"
              "  消息 系统 {_msg} ok\n  响应 go 首页\n结束\n"}
    services = {"services/note.zs": "业务 note\n  用包 common\n\n  公开 函数 列笔记 owner\n    返回 []\n  结束\n结束\n"}
    ui = {"ui/note.ui": "界面 列表 笔记列表\n  动作 note_list 远程 进入时\n  动作 note_open 远程\n  动作 note_go 远程\n  列表 表 绑 notes\n    列 title 标题\n    列 row_only 页面列\n  结束\n结束\n"}
    p = mkproj("cmp_ok", {"contracts/note.md": ctext}, entities, routes, services, ui)
    c, _ = P.load_contract(p, "note")
    check(C.check(c, "note", {}, ["note"]) == [], "项目约定检查通过", C.check(c, "note", {}, ["note"]))
    d = P.compare(p, "note", c, ["note"])
    check(d["一致"], "路由体和模板渲染一致 + 行字段都在实体表 → 一致", d["差异"])
    check(P._entity_fields(p) >= {"title", "updated_at", "row_only"}, "实体字段表并集（含页面实体字段）", P._entity_fields(p))

    def mut_route(mk_text, tag):
        q = mkproj(f"cmp_{tag}", {"contracts/note.md": ctext}, entities, {"routes/note.zs": mk_text}, services, ui)
        cc, _ = P.load_contract(q, "note")
        return P.compare(q, "note", cc, ["note"])["差异"]

    d = mut_route("接口 POST /note/list 动作 note_list 角色 teacher\n  设 r = 调用 note.列笔记 owner={owner}\n结束\n", "nolist")
    check(any("路由体和约定「模板 列表" in x for x in d), "少了组装行 → 路由体不一致", d)
    d = mut_route("接口 POST /note/list 动作 note_list2 角色 teacher\n  设 r = 调用 note.列笔记 owner={owner}\n  表格 notes {r}\n结束\n", "act")
    check(any("约定「动作 note_list」，实际路由是「动作 note_list2」" in x for x in d), "路由动作与约定不一致 → 差异", d)
    d = mut_route("接口 POST /note/list 动作 note_list 角色 teacher\n  设 r = 调用 note.列笔记 owner={owner}\n  表格 notes {r}\n  返回 {r}\n结束\n", "ret")
    check(any("最后一步不能是「返回 …」" in x for x in d), "封装接口结尾写「返回」→ 差异", d)
    d = mut_route("接口 POST /note/list 动作 note_list 角色 teacher\n  设 r = 调用 note.列笔记 owner={owner}\n  表格 notes {r}\n  表格 notes {r}\n结束\n", "dup")
    check(any("路由体和约定" in x for x in d), "多一行组装 → 路由体不一致（比 K25 的逐标记查更严）", d)
    d = mut_route("接口 POST /note/open 动作 note_open\n  设 r = 调用 note.列笔记 owner={owner}\n  表格 notes {r}\n结束\n"
                  "接口 POST /note/list 动作 note_list 角色 teacher\n  设 r = 调用 note.列笔记 owner={owner}\n  表格 notes {r}\n结束\n"
                  "接口 POST /note/go 动作 note_go\n  设 r = 调用 note.列笔记 owner={owner}\n  设 _msg = 已存\n  表格 notes {r}\n"
                  "  消息 系统 {_msg} ok\n  响应 go 首页\n结束\n", "form")
    check(any("路由体和约定「模板 回填」" in x for x in d), "回填被换掉 → 路由体不一致", d)
    # 行字段不在实体表
    bad_ct = ctext.replace("行=title,updated_at", "行=title,nope_field")
    q = mkproj("cmp_row", {"contracts/note.md": bad_ct}, entities, routes, services, ui)
    cc, _ = P.load_contract(q, "note")
    d = P.compare(q, "note", cc, ["note"])["差异"]
    check(any("nope_field" in x and "不在任何实体字段表里" in x for x in d), "行字段不在实体字段表 → 差异", d)
    # .ui 覆盖：.ui 多一个没人声明的动作；约定声明 .ui 没有的动作
    ui3 = dict(ui)
    ui3["ui/extra.ui"] = "界面 列表 另一页\n  动作 ghost_action 远程\n  结束\n"
    q = mkproj("cmp_ghost", {"contracts/note.md": ctext}, entities, routes, services, ui3)
    cc, _ = P.load_contract(q, "note")
    d = P.compare(q, "note", cc, ["note"])["差异"]
    check(any("「ghost_action」没有任何接口声明" in x for x in d), ".ui 动作没人声明 → 差异", d)
    more = tail + "POST /note/x -> 列笔记 动作 not_in_ui 模板 回填\n"
    extra_ct = ("模块 note\n依赖 无\n\n## 函数\n公开 函数 列笔记 owner\n  返回 行列表\n  伪代码 返回 []\n\n## 接口\n"
                + more + "\n\n## 用例\n用例 列笔记_有\n  调用 列笔记 owner=u1\n  得 有返回\n")
    q = mkproj("cmp_extra", {"contracts/note.md": extra_ct}, entities, routes, services, ui)
    cc, _ = P.load_contract(q, "note")
    d = P.compare(q, "note", cc, ["note"])["差异"]
    check(any("声明了「动作 not_in_ui」，但项目 ui/*.ui 里没有" in x for x in d), "声明 .ui 没有的动作 → 差异", d)
    # 跨模块重复：另一个模块的约定声明同一个动作
    q = mkproj("cmp_dup", {"contracts/note.md": ctext, "contracts/memo.md": "模块 memo\n依赖 无\n\n## 函数\n公开 函数 g a\n  返回 {ok}\n\n## 接口\nPOST /m/x -> g 动作 note_list\n\n## 用例\n用例 g_有\n  调用 g a=1\n  得 有返回\n"},
               entities, routes, services, ui)
    cc, _ = P.load_contract(q, "note")
    d = P.compare(q, "note", cc, ["note", "memo"])["差异"]
    check(any("被 2 个接口声明" in x for x in d), "动作被两个模块声明 → 差异", d)


def t_globalcheck():
    print("全局检查：跨模块动作重复")
    from tools.dslagent.v3 import top as VT
    top = VT.load("项目 demo\n模块 note\n模块 memo\n")
    p = mkproj("gc", {"contracts/note.md": "模块 note\n依赖 无\n" + GOOD_TAIL,
                      "contracts/memo.md": "模块 memo\n依赖 无\n\n## 函数\n公开 函数 g a\n  返回 {ok}\n\n## 接口\nPOST /m/x -> g 动作 note_list\n\n## 用例\n用例 g_有\n  调用 g a=1\n  得 有返回\n"})
    g = GC.check(p, top)
    check(any("动作「note_list」在模块 memo、note 里都声明了" in x for x in g["按模块"]["note"])
          and any("动作「note_list」在模块 memo、note 里都声明了" in x for x in g["按模块"]["memo"]),
          "同一动作两个模块声明 → 双方都有问题", g)


def t_ui_actions():
    print(".ui 远程动作提取")
    ui = {"ui/a.ui": "# 注释行\n界面 列表 笔记列表 端 学生\n"
                     "  动作 note_list 远程 进入时 隐藏 刷新\n"
                     "  分组 编辑 横排\n"
                     "    字段 title 标题\n"
                     "    字段 tag 绑 tag_key 标签\n"
                     "    动作 note_save 远程 清空 保存\n"
                     "  结束\n"
                     "  列表 表 绑 notes\n"
                     "    列 title 标题\n"
                     "    列 state_name 绑 row_state 状态\n"
                     "    动作 note_del 远程 带 title 当 row.row_state==='x' 删除\n"
                     "  结束\n"
                     "  分组 筛选 横排\n"
                     "    字段 kw 共享 关键词\n"
                     "  结束\n"
                     "结束\n"
                     "界面 表单 登录\n"
                     "  分组 主体 竖排\n"
                     "    字段 username 用户名\n"
                     "  结束\n"
                     "  动作 auth_login 提交 远程 登录\n"
                     "结束\n",
           "ui/b.ui": "界面 自定义 同名页\n  分组 底 横排\n    动作 note_save 远程 再存一次\n  结束\n结束\n"}
    p = mkproj("uia", ui=ui)
    rows = UA.actions_of(p)
    names = UA.remote_names(p)
    check(names == {"note_list", "note_save", "note_del", "auth_login"}, "远程动作名集合（跨文件去重）", names)
    lst = next(a for a in rows if a["动作"] == "note_list")
    check(lst["界面"] == "笔记列表" and lst["端"] == "学生" and "进入时" in lst["触发时机"],
          "动作带界面 / 端 / 触发时机", lst)
    check(lst["表单"] == ["title", "tag_key", "kw"] and lst["lists"] == ["notes"] and "kw" in lst["state"],
          "表单键（绑指回的用绑）、lists 键、共享字段进 state", lst)
    del_ = next(a for a in rows if a["动作"] == "note_del")
    check(del_["带"] == "title", "行上「带」提取", del_)
    s = UA.summary(p)
    check("动作 note_del（界面「笔记列表」" in s and "行上带 title" in s and "发送表单键：username" in s,
          "summary 文本含动作、带字段、表单键", s[:400])
    check(UA.summary(TMP / "uia_empty") == "", "没有 ui/ → 空串")


class _Ctx:
    """planning.user_text / review_user 够用的小 ctx（项目 + top.zs）。"""

    def __init__(self, project):
        self.project = project
        self._top = project / "plan" / "top.zs"

    def top_path(self):
        return self._top


def t_inject():
    print("清单注入：写约定 / 复核约定的输入")
    from tools.dslagent.v3 import top as VT
    p = mkproj("inject", ui={"ui/note.ui": "界面 列表 笔记列表\n  动作 note_list 远程 进入时\n  结束\n"})
    (p / "plan").mkdir()
    (p / "plan" / "top.zs").write_text("项目 demo\n模块 note\n", encoding="utf-8")
    ctx = _Ctx(p)
    u = PL.user_text(ctx, "约定", "需求", "note")
    check("【接口封装模板" in u and "- 模板 提交跳转：" in u and "模板 <中文名> 键=值" in u, "写约定的输入带模板清单", u[-600:])
    check("只能用清单里的模板" in u, "写约定的输入带「只能从清单里选」的规则", u[-600:])
    r = PL.review_user(ctx, "note", "模块 note\n依赖 无\n", "需求")
    check("【接口封装模板" in r and "- 模板 回填：" in r, "复核约定的输入带模板清单", r[-400:])


def t_envelope():
    print("接口冒烟的信封期望（regress._envelope）")
    iface = {"方法": "POST", "路径": "/x", "动作": "a", "模板": {"名": "列表", "参数": {"键": "rows", "行": "a,b"}}}
    e = _envelope(iface, [{"a": 1}])
    check(e == {"lists": {"rows": [{"a": 1}]}}, "列表模板的信封", e)
    iface2 = {"方法": "POST", "路径": "/x", "动作": "a", "模板": {"名": "提交跳转", "参数": {"消息": "已保存", "跳转": "@来处"}}}
    e2 = _envelope(iface2, {"ok": 1})
    check(e2 == {"messages": [{"who": "系统", "text": "已保存", "kind": "ok"}], "go": "@来处"}, "提交跳转的信封", e2)
    iface3 = {"方法": "POST", "路径": "/x", "动作": "a", "模板": None}
    check(_envelope(iface3, {"ok": 1}) == {}, "没写模板 → 空信封（走裸返回比对）")


def t_router():
    print("Router 实跑：scaffold 生成的模板路由返回信封")
    from tools.dsl_http import Router, endpoints_of
    ctext = ("模块 note\n依赖 无\n\n## 函数\n公开 函数 列笔记 owner\n  返回 行列表\n  伪代码 返回 []\n"
             "公开 函数 存笔记 owner title\n  返回 {ok}\n  报错 400 标题不能为空\n  伪代码 title 为空 报错 400 标题不能为空\n"
             "  伪代码 返回 {\"ok\": 1}\n\n## 接口\n"
             "POST /note/list -> 列笔记 动作 note_list 模板 列表 键=notes 行=title,updated_at 公开\n"
             "POST /note/save -> 存笔记 动作 note_save 模板 提交跳转 消息=已保存 跳转=笔记 公开\n"
             "POST /note/open -> 列笔记 动作 note_open 模板 回填 公开\n\n## 用例\n"
             "用例 列笔记_有\n  调用 列笔记 owner=u1\n  得 有返回\n"
             "用例 存笔记_好\n  调用 存笔记 owner=u1 title=x\n  得 ok=1\n"
             "用例 存笔记_空\n  调用 存笔记 owner=u1 title=空\n  报错 400\n")
    svc = ("业务 note\n  用包 common\n\n"
           "  公开 函数 列笔记 owner\n    返回 [{\"title\": \"t1\", \"updated_at\": \"2026-01-01 09:00:00\"}]\n  结束\n\n"
           "  公开 函数 存笔记 owner title\n    如果 {title} 为空\n      报错 400 标题不能为空\n    结束\n    返回 {\"ok\": 1}\n  结束\n结束\n")
    c, probs = C.parse(ctext)
    check(not probs, "Router 用约定解析通过", probs)
    routes_text = SF.route_text("note", c, {"note": c})
    check("动作 note_list" in routes_text and "表格 notes {r}" in routes_text and "响应 go 笔记" in routes_text,
          "骨架路由带动作与模板组装", routes_text[:400])
    # 消息文字带空格：模板用「设」变量兜住——手工把值换成带空格的，引擎不该切错
    (TMP / "router_space").mkdir()
    (TMP / "router_space" / "note.zs").write_text(routes_text.replace("设 _msg = 已保存", "设 _msg = 已保存 成功"),
                                                  encoding="utf-8")
    routes_text = (TMP / "router_space" / "note.zs").read_text(encoding="utf-8")
    p = mkproj("router", {"routes/note.zs": routes_text}, services={"services/note.zs": svc})
    (p / "sessions").mkdir()
    eps = endpoints_of(p / "routes")
    check(eps == {"note_list": "/note/list", "note_save": "/note/save", "note_open": "/note/open"},
          "endpoints_of：动作 → 路径（编译期绑定）", eps)
    r = Router(p / "routes", p, p / "sessions", real=False, login=False)
    cl = r.app().test_client()
    resp = cl.post("/note/list", json={"action": "note_list", "form": {"owner": "u1"}})
    check(resp.status_code == 200 and resp.get_json() == {"lists": {"notes": [{"title": "t1", "updated_at": "2026-01-01 09:00:00"}]}},
          "POST {action, form} → lists 信封", (resp.status_code, resp.get_data(as_text=True)[:200]))
    resp = cl.post("/note/save", json={"action": "note_save", "form": {"owner": "u1", "title": "x"}})
    check(resp.status_code == 200 and resp.get_json() == {"messages": [{"who": "系统", "text": "已保存 成功", "kind": "ok"}],
                                                          "go": "笔记"},
          "提交跳转信封；消息文字带空格经「设」变量原样到前端", (resp.status_code, resp.get_json()))
    resp = cl.post("/note/open", json={"action": "note_open", "form": {"owner": "u1"}})
    check(resp.status_code == 200 and resp.get_json() == {"form": [{"title": "t1", "updated_at": "2026-01-01 09:00:00"}]},
          "回填信封", (resp.status_code, resp.get_json()))
    # 出错：业务报错 → {"error"} + 4xx（模板接口的出错路径）
    c2, _ = C.parse(ctext.replace("POST /note/open -> 列笔记 动作 note_open 模板 回填 公开",
                                  "POST /note/open -> 存笔记 动作 note_open 模板 回填 公开"))
    routes_text2 = SF.route_text("note", c2, {"note": c2})
    (p / "routes" / "note.zs").write_text(routes_text2, encoding="utf-8")
    r2 = Router(p / "routes", p, p / "sessions", real=False, login=False)
    resp = r2.app().test_client().post("/note/open", json={"action": "note_open", "form": {"owner": "u1", "title": ""}})
    check(resp.status_code == 400 and resp.get_json() == {"error": "标题不能为空"},
          "模板接口出错 → error + 4xx（出错走 error，不用写进模板）", (resp.status_code, resp.get_json()))


def t_router_new():
    print("Router 实跑：页面状态铺 state / 回复消息进 messages / 动态 go 展开 / 传定值+参数改名")
    from tools.dsl_http import Router
    ctext = ("模块 account\n依赖 无\n\n## 函数\n"
             "公开 函数 停用 username disabled\n  返回 {ok}\n  伪代码 返回 {\"ok\": 1}\n"
             "公开 函数 页面数据 learner\n  返回 {stat, rows}\n  伪代码 返回 {\"stat\": {\"done\": 1}}\n"
             "公开 函数 问老师 learner message\n  返回 {reply}\n  伪代码 返回 {\"reply\": \"回答\"}\n"
             "公开 函数 建任务 series_code\n  返回 {task_id}\n  伪代码 返回 {\"task_id\": \"job_1\"}\n"
             "公开 函数 开始练习 learner\n  返回 {stat, form}\n  伪代码 返回 {\"stat\": {\"done\": 0}, \"form\": {\"pick_level\": \"n3\"}}\n\n## 接口\n"
             "POST /acc/disable -> 停用 动作 acc_disable 模板 列表 键=students 传 disabled=1 参数 reset_user=username 公开\n"
             "POST /acc/page -> 页面数据 动作 acc_page 模板 页面状态 公开\n"
             "POST /acc/ask -> 问老师 动作 acc_ask 模板 回复消息 谁=老师 取=reply 公开\n"
             "POST /acc/task -> 建任务 动作 acc_task 模板 提交跳转动态 消息=已建任务 跳转=#教材导入?job={r.task_id} 公开\n"
             "POST /acc/start -> 开始练习 动作 acc_start 模板 页面状态 表单=form 去处=#做题 公开\n\n## 用例\n"
             "用例 停用_有\n  调用 停用 username=u1 disabled=1\n  得 有返回\n"
             "用例 页面_有\n  调用 页面数据 learner=u1\n  得 有返回\n"
             "用例 问_有\n  调用 问老师 learner=u1 message=hi\n  得 有返回\n"
             "用例 任务_有\n  调用 建任务 series_code=s1\n  得 有返回\n"
             "用例 开始_有\n  调用 开始练习 learner=u1\n  得 有返回\n")
    svc = ("业务 account\n  用包 common\n\n"
           "  公开 函数 停用 username disabled\n    返回 [{\"who\": \"{username}\", \"flag\": \"{disabled}\"}]\n  结束\n\n"
           "  公开 函数 页面数据 learner\n    返回 {\"stat\": {\"done\": 1}, \"rows\": [\"a\"]}\n  结束\n\n"
           "  公开 函数 问老师 learner message\n    返回 {\"reply\": \"回答\"}\n  结束\n\n"
           "  公开 函数 建任务 series_code\n    返回 {\"task_id\": \"job_1\"}\n  结束\n\n"
           "  公开 函数 开始练习 learner\n    返回 {\"stat\": {\"done\": 0}, \"form\": {\"pick_level\": \"n3\"}}\n  结束\n结束\n")
    c, probs = C.parse(ctext)
    check(not probs, "Router 用约定（含 传/参数 与三个新模板）解析通过", probs)
    routes_text = SF.route_text("account", c, {"account": c})
    p = mkproj("router_new", {"routes/account.zs": routes_text}, services={"services/account.zs": svc})
    (p / "sessions").mkdir()
    r = Router(p / "routes", p, p / "sessions", real=False, login=False)
    cl = r.app().test_client()
    # 传 定值 + 参数 改名：表单发前端键 reset_user；disabled 在表单里伪造 9 也不管用（路由里是字面 1）
    resp = cl.post("/acc/disable", json={"action": "acc_disable", "form": {"reset_user": "u1", "disabled": "9", "username": "hacker"}})
    check(resp.status_code == 200 and resp.get_json() == {"lists": {"students": [{"who": "u1", "flag": "1"}]}},
          "改名键 reset_user 的值传给函数入参 username；disabled 用字面 1（表单伪造 9 无效）", (resp.status_code, resp.get_json()))
    resp = cl.post("/acc/page", json={"action": "acc_page", "form": {"learner": "u1"}})
    check(resp.status_code == 200 and resp.get_json() == {"state": {"stat": {"done": 1}, "rows": ["a"]}},
          "页面状态：函数结果整体铺进 state", (resp.status_code, resp.get_json()))
    resp = cl.post("/acc/ask", json={"action": "acc_ask", "form": {"learner": "u1", "message": "你好"}})
    check(resp.status_code == 200 and resp.get_json() == {"messages": [{"who": "老师", "text": "回答", "kind": "ok"}]},
          "回复消息：函数结果字段进 messages（who=老师）", (resp.status_code, resp.get_json()))
    resp = cl.post("/acc/task", json={"action": "acc_task", "form": {"series_code": "s1"}})
    check(resp.status_code == 200 and resp.get_json() == {"go": "#教材导入?job=job_1",
                                                          "messages": [{"who": "系统", "text": "已建任务", "kind": "ok"}]},
          "提交跳转动态：go 里的 {r.task_id} 运行时展开成真实值（K27b §5.3 待验证点，实测展开）",
          (resp.status_code, resp.get_json()))
    resp = cl.post("/acc/start", json={"action": "acc_start", "form": {"learner": "u1"}})
    check(resp.status_code == 200 and resp.get_json() == {"state": {"stat": {"done": 0}, "form": {"pick_level": "n3"}},
                                                          "form": {"pick_level": "n3"}, "go": "#做题"},
          "页面状态 表单+去处：Router 实跑 state/form/go 前端信封三键齐（go 清地址参数，刷新不再触发「载入」）",
          (resp.status_code, resp.get_json()))


def main():
    t_tpl()
    t_parse()
    t_compat()
    t_scaffold()
    t_fixed_renamed()
    t_v3check()
    t_compare()
    t_globalcheck()
    t_ui_actions()
    t_inject()
    t_envelope()
    t_router()
    t_router_new()
    print(f"\n通过 {PASS}，失败 {FAIL}")
    shutil.rmtree(TMP, ignore_errors=True)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
