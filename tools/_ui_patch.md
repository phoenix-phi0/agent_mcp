# UI 引擎增补：会话组件（2026-09-11，已实施）

给 .ui 补上会话式界面缺的四样东西：消息流、动态只读文本、动作到后端的
绑定、跨界面共享状态。对应之前「重构 serve.py 界面」评估里的四个缺口。

**全部为增量改动**：旧 .ui 文件的解析结果和编译产物一字不变（旧进程里
实测编译旧语法，产物与旧版一致；tests/fixture.ui 的 32 条页面断言不受
影响）。旧语法不受影响的原因：新组件全是新关键字/新修饰词，老文件里
不出现；模板里所有新逻辑都包在 `{% if %}` 里。

## 改了哪些文件

| 文件 | 改动 |
| --- | --- |
| tools/ui.py | 新行语句 消息流/显示；修饰词 到（键值）/共享（旗标）；Node 增加 to 字段和 streams()；validate 增加 bad_endpoint 检查；_shared_defaults/_first_stream 新函数；_form_defaults 排除共享字段；render_vue/vue_backend 透传 endpoints，新增六个上下文变量 |
| templates/frontend/widgets.j2 | 控件宏按「共享」把 v-model 指到 shared；新宏 消息流/显示；带「到」的提交动作渲染成普通按钮走 submitTo |
| templates/frontend/layout.j2 | 节点分发加 消息流/显示 两个分支 |
| templates/frontend/app.js.j2 | 条件生成：shared 状态块（含 pushMessages 滚底、getPath）、endpoints 表 + postTo/applyResponse 胶水、submitTo；六个新上下文变量全带 is defined 兜底（见下「兼容守卫」） |
| templates/frontend/style.css.j2 | 条件生成 .stream/.smsg/.dyn 样式 |
| tools/test_dsl.py | 新增三组测试：test_ui_parse / test_ui_validate / test_ui_compile，共 25 项断言；预期总数从 100 变 125 |
| web/demo/ui/会话.ui | 新组件的演示文件（对话 + 练习两个界面） |

## 新语法

    消息流 <名> [标题]          界面/区域/分组 里。
                                数据存共享状态的 <名> 数组，每条消息
                                {who, text, kind}，kind 决定配色
                                （smsg-user / smsg-ok / smsg-no / ...）。

    显示 <名> [绑 路径] <标题>  界面/区域/分组 里。只读动态文本，
                                读共享状态，后端返回值驱动。

    动作 <名> [样式] 到 <端点> <文案>
                                修饰词在文案前面（老规矩）。端点必须以
                                / 开头，否则 validate 报 bad_endpoint。
                                带「到」的提交动作渲染成普通按钮，
                                走 submitTo 而不是 form submit。

    字段 <名> 共享 ...          字段存进跨界面共享状态而不是本界面的
                                表单。同一名字在两个界面都标共享，
                                就是同一份数据。

## 编译期新增的上下文（render_vue）

    has_shared_state / shared_json   有共享字段、消息流或显示时为真
    has_endpoints / endpoints_json   options["endpoints"] 非空时为真
    has_to_actions                   树里有动作带「到」时为真
    first_stream_json                第一条消息流的名字（消息默认去向）

## 生成端约定（app.js）

动作带「到」时，点击 → `POST <端点>`，body 为 `{action, form}`。返回值
按下面的键合并进页面（各自可选）：

    messages: [{who, text, kind}]   追加进消息流；resp.stream 指定流名，
                                    缺省用 first_stream
    state: {...}                    合并进共享状态（驱动「显示」）
    rows: [...]                     替换列表数据

没配端点的动作保持原样打 console.log（骨架行为不变）。

## 兼容守卫（重要）

app.js.j2 / style.css.j2 顶部对六个新上下文变量做了 `is defined` 兜底。
原因：MCP 服务器进程把 tools.ui 等模块缓存在启动时，`tool_call(reset=True)`
实测换不进新代码（白名单持有旧函数引用，动词表同理）。在新旧交替期间，
旧 render_vue 不传新变量，StrictUndefined 会让新模板直接炸——守卫让旧
进程继续编译旧 .ui 且产物不变。**服务器重启后这些 set 全部走真值**，
守卫不掩盖任何新代码的错误（变量由 render_vue 恒定提供）。

## 验证状态

已在旧进程实测：
- 旧语法 .ui 经新模板编译 → 无 UndefinedError，产物与旧版逐字节一致
  （无 shared / endpoints / submitTo，onAction 保持日志骨架）。
- 新 tools/ui.py 已确认落盘（读回校对过语法区）。

需要重启 MCP 服务器后做（新代码只在新进程里生效）：
    run_tests                     预期 125 通过 0 失败（多出 [UI 解析]/[UI 校验]/[UI 编译] 三组）
    ui.check web/demo/ui/会话.ui
    ui.compile web/demo/ui/会话.ui backend=vue
      fields={"输入":"长文本","作答":"文本"}
      options={"title":"会话演示","endpoints":{"send":"/chat",
               "answer":"/drill/answer","next":"/drill/next"}}
    查界面 / 生成界面 两个动词（重启后动词表从磁盘重载，即为新版）

## 已知的后续项

- verbs/web/_verbs.py 的 生成界面 选项表目前只映射到 options_map，
  透传 endpoints 需要把 选项表 整个并进 options（一行改动，重启后生效）。
- serve.py 换用生成界面重构 PAGE：端点返回值按上面的约定补 messages /
  state 键即可接上，无需改生成端。
- test_page.js 的 32 条断言只覆盖旧语法；新组件的页面行为目前靠
  test_ui_compile 的产物断言，jsdom 挂载测试待补。
