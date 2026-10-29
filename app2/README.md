# app2 —— 桌面程序的新版

跟 `agents/app.py` + `agents/serve.py` 并存，不碰它们。确认这版能跑之后再考虑替换。

## 跟旧版的区别

界面不再是手写的 HTML 字符串，而是从 `ui/*.ui` 生成。

```
ui/main.ui     ──┐
ui/startup.ui  ──┴─→ build.py ─→ web/index.html + app.js + style.css
                                 startup_html.py（内联单文件）
```

两种打包方式，用在不同场景：

| 场景 | 形态 | 大小 | 为什么 |
| --- | --- | --- | --- |
| 主窗口 | 三个文件 + 本地 Vue | 7 KB + 164 KB | 本来就起了 uvicorn，有服务器就不必内联 |
| 启动自检失败 | 内联单文件 | 169 KB | 那时候服务器还没起来，只能给字符串 |

Vue 放本地不走 CDN：桌面程序不该因为断网白屏。

## 目录

```
app2/
  README.md          本文件
  build.py           生成界面，打包前跑一次
  app.py             入口，跟旧版几乎一样
  serve.py           HTTP 接口 + 静态挂载
  ui/
    main.ui          主界面描述
    startup.ui       启动自检窗口描述
  assets/
    vue.global.prod.js   自己下载放这里
  web/               build.py 的产物，别手改
  startup_html.py    build.py 的产物，别手改
```

## 跑起来

```
下载 https://unpkg.com/vue@3/dist/vue.global.prod.js 放进 assets/
py build.py
py app.py
```

`build.py` 要能 import 到 `tools/`，所以从项目根目录跑，或者让 app2 在
`mcp/` 下面。

## 改界面

改 `ui/main.ui`，重跑 `py build.py`，重启程序。不用碰任何 Python 代码。

## 接口约定

`.ui` 里标了「远程」的动作会往 `endpoints` 里对应的地址 POST：

```json
{"action": "send", "form": {...}}
```

返回这四个字段会被前端消化：

| 字段 | 效果 |
| --- | --- |
| `state` | 合并进跨界面状态（「共享」字段和「显示」节点读这里） |
| `messages` | 追加到消息流，`[{"who":…, "text":…, "kind":…}]` |
| `rows` | 替换列表数据 |
| `stream` | 指定 messages 进哪条流，不给就进第一条 |

`kind` 决定消息配色：`user` / `ok` / `no` / `pending`，缺省是普通样式。
`calls` 有值时渲染成折叠面板。
`actions`（`[{label, action, carry, kind}]`）是消息下面的一排按钮，只有 `.ui` 里那条消息流写了
`按钮 a,b` 白名单才画、且只画白名单里的动作（见 `tools/ui.py` 里「按钮」的说明）。

**不要回显用户自己说的话。** `.ui` 里 send 和 submit 标了「回显」，前端在
发请求之前就已经把输入插进消息流了——后端再回一条一模一样的，界面上会
出现两条。这跟「流程正文不要依赖模型转述」是同一类错误：两个方案各自都
对，叠加就出两遍。

## 现状

| 部分 | 状态 |
| --- | --- |
| 对话模式 | 已接 agent，`chat` 路由调 `agent.send()`，工具调用折叠显示，token 累计进 `usage` |
| 练习模式 | 状态机原样沿用旧版，出题/判题/下一题/结束都通，零模型调用 |
| 重置 | 结算练习 + 清两条消息流 + 重载 `agents`/`tools` 模块 |
| 共享字段 | `learner` 跨界面共用，改一处两边都变 |

两处旧版没有、这版才需要处理的：

- **首次提交时自动开局**。旧版靠切模式时触发 `drill/start`，而 `.ui` 的界面
  切换是纯前端的、不发请求，所以挪到了 `drill/answer` 和 `drill/next` 里判断。
- **「全部考点」要在后端转空串**。旧版下拉的 value 直接是 `""`，`.ui` 的下拉
  选项是文本，占位项会原样传过来。

## 还没做

- 主界面只有对话和练习，没有流程选择、教材浏览——旧版也没有，不算退化
- 错题只存在内存里，练习结束就没了，没写进 `progress.json`
- 界面上的学习者 ID 只决定用哪个 Agent 实例，跟 SOUL.md 里的身份确认流程还没打通
