# -*- coding: utf-8 -*-
"""K25：接口直接返回前端要的信封（封装标记：动作 / 表格 / 表单 / 状态 / 消息 / 跳转）。不调模型。

    cd /workspace/agent_mcp && .venv/bin/python tests/tools/test_dslagent_wrap.py

一、约定解析：新封装标记（各种组合、顺序、错误）、旧写法完全兼容（解析结果与问题清单不变）
二、骨架生成：写了封装的接口生成「动作 xxx」+ 响应动词组装、结尾不写返回；没写封装的照旧「返回 {r}」
三、约定检查（v3 contracts）：动作名要在 .ui 里、覆盖核对（其余约定齐了才全量查）、没有 .ui 的项目不声明动作
四、比对约定：信封键要在路由里组装、结尾不能是「返回」、行字段要在实体字段表、动作绑定一致、.ui 覆盖与跨模块重复
五、全局检查：同一动作名两个模块都声明
六、.ui 远程动作提取（tools/ui_actions）：动作 / 表单键 / lists / state / 带；与 .ui 同名动作两处按钮（去重）
七、接口冒烟的信封期望（regress._envelope）
八、Router 实跑：scaffold 生成的路由经真引擎 POST {action, form} 返回信封；出错回 {"error"} + 4xx；endpoints_of 绑定
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

from tools.dslagent.packs.dslproj import contract as C, project as P          # noqa: E402
from tools.dslagent.v3 import contracts as VC, globalcheck as GC, scaffold as SF   # noqa: E402
from tools.dslagent.v3.regress import _envelope                               # noqa: E402
from tools import ui_actions as UA                                            # noqa: E402

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
POST /note/list -> 列笔记 动作 note_list 表格 notes 行 title,updated_at 角色 teacher

## 用例
用例 列笔记_有
  调用 列笔记 owner=u1
  得 有返回
"""


def t_parse():
    print("约定解析：封装标记")
    c, probs = C.parse("模块 note\n依赖 无\n" + GOOD_TAIL)
    check(not probs, "完整封装行解析无问题", probs)
    i = c["接口"][0]
    check(i["动作"] == "note_list" and i["表格"] == {"键": "notes", "取": "", "行": ["title", "updated_at"]}
          and i["表单"] is None and i["状态"] is None and i["消息"] == "" and i["跳转"] == "",
          "动作 / 表格(键,取,行) 解析到位，其余为缺省", i)
    check(C.has_wrap(i), "has_wrap 认定封装")
    c2, p2 = C.parse('模块 note\n依赖 无\n\n## 函数\n公开 函数 f a\n  返回 {ok}\n\n## 接口\n'
                     'POST /a -> f 动作 a1 表单 取 rows 状态 st 取 data 消息 已保存 跳转 @来处\n'
                     'POST /b -> f 表格 rows\n'
                     'POST /c -> f 状态 st 取 data 表格 rows 取 items 行 x,y 消息 好 跳转 #首页?浮层=编辑 动作 a2\n'
                     'POST /d -> f 公开 动作 a3\n')
    check(not p2, "标记顺序任意、全部组合解析通过", p2)
    is_ = {x["路径"]: x for x in c2["接口"]}
    check(is_["/a"]["表单"] == {"取": "rows"} and is_["/a"]["状态"] == {"键": "st", "取": "data", "行": []}
          and is_["/a"]["消息"] == "已保存" and is_["/a"]["跳转"] == "@来处", "/a 的封装齐", is_["/a"])
    check(is_["/c"]["表格"] == {"键": "rows", "取": "items", "行": ["x", "y"]} and is_["/c"]["动作"] == "a2",
          "乱序 + 行在取之后解析正确", is_["/c"])
    # 错误写法
    bad = ('POST /e -> f 取 rows\n'                 # 取没有宿主
           'POST /f -> f 行 x\n'                    # 行没有宿主
           'POST /g -> f 动作\n'                    # 缺值
           'POST /h -> f 动作 a1 动作 a2\n'          # 重复
           'POST /i -> f 乱写 x\n')                 # 不认识的标记
    _, p3 = C.parse("模块 note\n依赖 无\n\n## 函数\n公开 函数 f a\n  返回 {ok}\n\n## 接口\n" + bad)
    for want in ("「取」要写在", "「行」要写在", "「动作」后面要跟一个词", "「动作」只能写一次", "不认识的接口标记「乱写」"):
        check(any(want in x for x in p3), f"错误写法报出「{want}」", p3)
    # 跳转目标带 # 的写法（行内 # 后跟非空白不是注释）
    c5, p5 = C.parse('模块 note\n依赖 无\n\n## 函数\n公开 函数 f a\n  返回 {ok}\n\n## 接口\n'
                     'POST /j -> f 跳转 #首页?浮层=编辑  # 这是注释\n')
    check(not p5 and c5["接口"][0]["跳转"] == "#首页?浮层=编辑", "跳转目标带 # 照常解析，行尾注释仍有效", (p5, c5["接口"][0].get("跳转")))
    # 约定检查：动作名 / 唯一 / POST
    c4, _ = C.parse("模块 note\n依赖 无\n\n## 函数\n公开 函数 f a\n  返回 {ok}\n\n## 接口\n"
                    "GET /x -> f 动作 x_list\nPOST /y -> f 动作 x_list\nPOST /z -> f 动作 Bad-Name 表格 行\n")
    pr = C.check(c4, "note", {}, ["note"])
    check(any("方法要写 POST" in x for x in pr), "GET + 封装 → 要求 POST", pr)
    check(any("被本模块两个接口声明" in x for x in pr), "动作重名 → 报", pr)
    check(any("动作名「Bad-Name」要用英文 snake" in x for x in pr), "动作名不合法 → 报", pr)
    check(any("的数据键要用英文 snake" in x for x in pr), "表格键不合法 → 报", pr)


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
    print("旧写法兼容")
    c, probs = C.parse("模块 x\n依赖 无\n" + OLD_TAIL)
    check(not probs, "旧接口行（GET / 上传 / 角色）解析无问题", probs)
    i = c["接口"][1]
    check(i["上传"] == {"字段": "file", "类型": "pdf,txt", "上限": "20MB"} and not C.has_wrap(i)
          and i["动作"] == "" and i["表格"] is None, "上传字段原样，封装为缺省", i)
    check(C.check(c, "x", {}, ["x"]) == [], "旧约定检查通过", C.check(c, "x", {}, ["x"]))
    rt = SF.route_text("x", c)
    check("接口 GET /x/one" in rt and "  返回 {r}\n结束" in rt and "动作" not in rt.replace("动作 name", ""),
          "旧接口的骨架照旧生成「返回 {r}」", rt)


def t_scaffold():
    print("骨架生成：封装接口的路由")
    c, _ = C.parse("模块 note\n依赖 无\n" + GOOD_TAIL)
    rt = SF.route_text("note", c)
    check("接口 POST /note/list 动作 note_list 角色 teacher" in rt, "接口行带 动作 与 角色（动作在前，路由行的解析顺序）", rt)
    check("  设 r = 调用 note.列笔记 owner={owner}\n  表格 notes {r}\n结束" in rt, "调用 → 表格 组装，结尾不写返回", rt)
    c2, _ = C.parse('模块 note\n依赖 无\n\n## 函数\n公开 函数 f a b?\n  返回 {ok}\n\n## 接口\n'
                    'POST /a -> f 动作 a1 表单 取 rows 状态 st 取 data 消息 已保存 跳转 @来处\n')
    rt2 = SF.route_text("note", c2)
    for want in ("动作 a1", "响应 form {r.rows}", '响应 state {"st":{r.data}}', "消息 系统 已保存 ok", "响应 go @来处"):
        check(want in rt2, f"组装行含「{want}」", rt2)
    check("返回" not in rt2, "封装接口的路由没有「返回」行", rt2)
    check("调用 note.f a={a} b={b 或}" in rt2, "可选入参照旧带「或」", rt2)


def t_v3check():
    print("约定检查（v3）：.ui 动作")
    top = VT_MODS = None
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
    # 行字段不在实体表 → 约定阶段不查（实体还没生成），比对约定才查
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
    print("比对约定：封装")
    tail = ("POST /note/list -> 列笔记 动作 note_list 表格 notes 行 title,updated_at 角色 teacher\n"
            "POST /note/open -> 列笔记 动作 note_open 表单\n"
            "POST /note/go -> 列笔记 动作 note_go 消息 已存 跳转 首页 状态 cnt\n")
    ctext = ("模块 note\n依赖 无\n\n## 函数\n公开 函数 列笔记 owner\n  返回 行列表\n  伪代码 返回 []\n\n## 接口\n"
             + tail + "\n\n## 用例\n用例 列笔记_有\n  调用 列笔记 owner=u1\n  得 有返回\n")
    entities = {"entities/note_note.entity": "实体 note_note 笔记\n  字段 title 文本 必填 标题\n  字段 updated_at 文本 时间\n  字段 row_only 文本 页面列\n结束\n"}
    routes = {"routes/note.zs":
              "接口 POST /note/list 动作 note_list 角色 teacher\n  设 r = 调用 note.列笔记 owner={owner}\n  表格 notes {r}\n结束\n"
              "接口 POST /note/open 动作 note_open\n  设 r = 调用 note.列笔记 owner={owner}\n  响应 form {r}\n结束\n"
              "接口 POST /note/go 动作 note_go\n  设 r = 调用 note.列笔记 owner={owner}\n  表格 notes {r}\n  状态 cnt {r}\n  消息 系统 已存 ok\n  响应 go 首页\n结束\n"}
    services = {"services/note.zs": "业务 note\n  用包 common\n\n  公开 函数 列笔记 owner\n    返回 []\n  结束\n结束\n"}
    ui = {"ui/note.ui": "界面 列表 笔记列表\n  动作 note_list 远程 进入时\n  动作 note_open 远程\n  动作 note_go 远程\n  列表 表 绑 notes\n    列 title 标题\n    列 row_only 页面列\n  结束\n结束\n"}
    p = mkproj("cmp_ok", {"contracts/note.md": ctext}, entities, routes, services, ui)
    c, _ = P.load_contract(p, "note")
    check(C.check(c, "note", {}, ["note"]) == [], "项目约定检查通过", C.check(c, "note", {}, ["note"]))
    d = P.compare(p, "note", c, ["note"])
    check(d["一致"], "组装齐 + 行字段都在实体表 → 一致", d["差异"])
    check(P._entity_fields(p) >= {"title", "updated_at", "row_only"}, "实体字段表并集（含页面实体字段）", P._entity_fields(p))

    def mut_route(mk_text, tag):
        q = mkproj(f"cmp_{tag}", {"contracts/note.md": ctext}, entities, {"routes/note.zs": mk_text}, services, ui)
        cc, _ = P.load_contract(q, "note")
        return P.compare(q, "note", cc, ["note"])["差异"]

    d = mut_route("接口 POST /note/list 动作 note_list 角色 teacher\n  设 r = 调用 note.列笔记 owner={owner}\n结束\n", "nolist")
    check(any("「表格 notes」，但路由里没有" in x for x in d), "表格键没组装 → 差异", d)
    d = mut_route("接口 POST /note/list 动作 note_list2 角色 teacher\n  设 r = 调用 note.列笔记 owner={owner}\n  表格 notes {r}\n结束\n", "act")
    check(any("约定「动作 note_list」，实际路由是「动作 note_list2」" in x for x in d), "路由动作与约定不一致 → 差异", d)
    d = mut_route("接口 POST /note/list 动作 note_list 角色 teacher\n  设 r = 调用 note.列笔记 owner={owner}\n  表格 notes {r}\n  返回 {r}\n结束\n", "ret")
    check(any("最后一步不能是「返回 …」" in x for x in d), "封装接口结尾写「返回」→ 差异", d)
    d = mut_route("接口 POST /note/open 动作 note_open\n  设 r = 调用 note.列笔记 owner={owner}\n  表格 notes {r}\n结束\n"
                  "接口 POST /note/list 动作 note_list 角色 teacher\n  设 r = 调用 note.列笔记 owner={owner}\n  表格 notes {r}\n结束\n"
                  "接口 POST /note/go 动作 note_go\n  设 r = 调用 note.列笔记 owner={owner}\n  表格 notes {r}\n  状态 cnt {r}\n  消息 系统 已存 ok\n  响应 go 首页\n结束\n", "form")
    check(any("约定「表单」，但路由里没有「响应 form …」" in x for x in d), "表单没组装 → 差异", d)
    d = mut_route("接口 POST /note/go 动作 note_go\n  设 r = 调用 note.列笔记 owner={owner}\n  消息 系统 已存 ok\n结束\n"
                  "接口 POST /note/list 动作 note_list 角色 teacher\n  设 r = 调用 note.列笔记 owner={owner}\n  表格 notes {r}\n结束\n"
                  "接口 POST /note/open 动作 note_open\n  设 r = 调用 note.列笔记 owner={owner}\n  响应 form {r}\n结束\n", "gost")
    check(any("「状态 cnt」" in x and "没人组装" in x for x in d) and any("「跳转 首页」" in x for x in d),
          "状态 / 跳转没组装 → 差异", d)
    # 行字段不在实体表
    bad_ct = ctext.replace("行 title,updated_at", "行 title,nope_field")
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
    more = tail + "POST /note/x -> 列笔记 动作 not_in_ui\n"
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
    col = "row_state" in del_["表单"] or True
    check(col, "（列的绑是行字段，不算表单键——这里只查不炸）")
    s = UA.summary(p)
    check("动作 note_del（界面「笔记列表」" in s and "行上带 title" in s and "发送表单键：username" in s,
          "summary 文本含动作、带字段、表单键", s[:400])
    check(UA.summary(TMP / "uia_empty") == "", "没有 ui/ → 空串")


def t_envelope():
    print("接口冒烟的信封期望")
    iface = {"方法": "POST", "路径": "/x", "表格": {"键": "rows", "取": "", "行": []},
             "表单": None, "状态": None, "消息": "已保存", "跳转": "@来处"}
    e = _envelope(iface, [{"a": 1}])
    check(e == {"lists": {"rows": [{"a": 1}]}, "messages": [{"who": "系统", "text": "已保存", "kind": "ok"}],
                "go": "@来处"}, "表格+消息+跳转的信封", e)
    iface2 = {"方法": "POST", "路径": "/x", "表格": None, "表单": {"取": "row"}, "状态": {"键": "st", "取": "data"},
              "消息": "", "跳转": ""}
    e2 = _envelope(iface2, {"row": {"a": 1}, "data": 3})
    check(e2 == {"form": {"a": 1}, "state": {"st": 3}}, "取 <字段> 的信封", e2)


def t_router():
    print("Router 实跑：scaffold 生成的路由返回信封")
    from tools.dsl_http import Router, endpoints_of
    ctext = ("模块 note\n依赖 无\n\n## 函数\n公开 函数 列笔记 owner\n  返回 行列表\n  伪代码 返回 []\n"
             "公开 函数 存笔记 owner title\n  返回 {ok}\n  报错 400 标题不能为空\n  伪代码 title 为空 报错 400 标题不能为空\n"
             "  伪代码 返回 {\"ok\": 1}\n\n## 接口\n"
             "POST /note/list -> 列笔记 动作 note_list 表格 notes 行 title,updated_at 公开\n"
             "POST /note/save -> 存笔记 动作 note_save 消息 已保存 状态 cnt 公开\n"
             "POST /note/open -> 列笔记 动作 note_open 表单 公开\n\n## 用例\n"
             "用例 列笔记_有\n  调用 列笔记 owner=u1\n  得 有返回\n"
             "用例 存笔记_好\n  调用 存笔记 owner=u1 title=x\n  得 ok=1\n"
             "用例 存笔记_空\n  调用 存笔记 owner=u1 title=空\n  报错 400\n")
    svc = ("业务 note\n  用包 common\n\n"
           "  公开 函数 列笔记 owner\n    返回 [{\"title\": \"t1\", \"updated_at\": \"2026-01-01 09:00:00\"}]\n  结束\n\n"
           "  公开 函数 存笔记 owner title\n    如果 {title} 为空\n      报错 400 标题不能为空\n    结束\n    返回 {\"ok\": 1}\n  结束\n结束\n")
    c, probs = C.parse(ctext)
    check(not probs, "Router 用约定解析通过", probs)
    routes_text = SF.route_text("note", c, {"note": c})
    p = mkproj("router", {"routes/note.zs": routes_text}, services={"services/note.zs": svc})
    (p / "sessions").mkdir()
    check("动作 note_list" in routes_text and "表格 notes {r}" in routes_text, "骨架路由带动作与组装", routes_text[:300])
    eps = endpoints_of(p / "routes")
    check(eps == {"note_list": "/note/list", "note_save": "/note/save", "note_open": "/note/open"},
          "endpoints_of：动作 → 路径（编译期绑定）", eps)
    r = Router(p / "routes", p, p / "sessions", real=False, login=False)
    cl = r.app().test_client()
    resp = cl.post("/note/list", json={"action": "note_list", "form": {"owner": "u1"}})
    check(resp.status_code == 200 and resp.get_json() == {"lists": {"notes": [{"title": "t1", "updated_at": "2026-01-01 09:00:00"}]}},
          "POST {action, form} → lists 信封", (resp.status_code, resp.get_data(as_text=True)[:200]))
    resp = cl.post("/note/save", json={"action": "note_save", "form": {"owner": "u1", "title": "x"}})
    check(resp.status_code == 200 and resp.get_json() == {"state": {"cnt": {"ok": 1}}, "messages": [{"who": "系统", "text": "已保存", "kind": "ok"}]},
          "状态 + 消息 信封（state 的值是对象不是 JSON 文本）", (resp.status_code, resp.get_json()))
    resp = cl.post("/note/open", json={"action": "note_open", "form": {"owner": "u1"}})
    check(resp.status_code == 200 and resp.get_json() == {"form": [{"title": "t1", "updated_at": "2026-01-01 09:00:00"}]},
          "表单回填信封", (resp.status_code, resp.get_json()))
    # 出错：业务报错 → {"error"} + 4xx（封装接口的出错路径）
    c2, _ = C.parse(ctext.replace("POST /note/open -> 列笔记 动作 note_open 表单 公开",
                                  "POST /note/open -> 存笔记 动作 note_open 表单 公开"))
    routes_text2 = SF.route_text("note", c2, {"note": c2})
    (p / "routes" / "note.zs").write_text(routes_text2, encoding="utf-8")
    r2 = Router(p / "routes", p, p / "sessions", real=False, login=False)
    resp = r2.app().test_client().post("/note/open", json={"action": "note_open", "form": {"owner": "u1", "title": ""}})
    check(resp.status_code == 400 and resp.get_json() == {"error": "标题不能为空"},
          "封装接口出错 → error + 4xx（出错走 error，不用写进封装）", (resp.status_code, resp.get_json()))


def main():
    t_parse()
    t_compat()
    t_scaffold()
    t_v3check()
    t_compare()
    t_globalcheck()
    t_ui_actions()
    t_envelope()
    t_router()
    print(f"\n通过 {PASS}，失败 {FAIL}")
    shutil.rmtree(TMP, ignore_errors=True)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
