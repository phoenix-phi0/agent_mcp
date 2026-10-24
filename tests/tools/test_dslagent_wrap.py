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
    check(names == ["列表", "回填", "提交消息", "提交跳转", "状态"], "4+1 个模板都在（按文件名排序）", names)
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
    # 信封解释
    e = T.envelope("提交跳转", {"消息": "已保存", "跳转": "笔记", "键": "notes"}, [{"a": 1}])
    check(e == {"lists": {"notes": [{"a": 1}]}, "messages": [{"who": "系统", "text": "已保存", "kind": "ok"}], "go": "笔记"},
          "信封解释：lists + messages + go", e)
    e2 = T.envelope("回填", {"取": "row"}, {"row": {"x": 1}, "其它": 2})
    check(e2 == {"form": {"x": 1}}, "信封解释：取 <字段>", e2)
    e3 = T.envelope("状态", {"键": "st", "取": "d"}, {"d": 3})
    check(e3 == {"state": {"st": 3}}, "信封解释：state 的值是对象不是 JSON 文本", e3)


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
    check(any("可用模板：列表、回填、提交消息、提交跳转、状态" in x for x in pr5), "报错里列出可用模板中文名", pr5)
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


def main():
    t_tpl()
    t_parse()
    t_compat()
    t_scaffold()
    t_v3check()
    t_compare()
    t_globalcheck()
    t_ui_actions()
    t_inject()
    t_envelope()
    t_router()
    print(f"\n通过 {PASS}，失败 {FAIL}")
    shutil.rmtree(TMP, ignore_errors=True)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
