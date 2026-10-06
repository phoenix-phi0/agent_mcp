# 教材系列：新教材的格式和导入

kg 的知识点（node）、条目（item）、题目、学习记录是**跨系列共享**的。一套新
教材进来，只是多一组「课」，每课**映射到已有的知识点**——不新建知识点、不新建
条目。换了系列，做过的题、掌握得分照旧算数；变的只是教材页列哪些课、「第N课」
怎么认、老师按哪套课讲、按课练出哪些题。

现在只有一个系列：hanabira（hanabira.org 的语法库，CC BY 4.0），它的课还在老
位置 `content/lessons.jsonl` + `content/item_lessons.jsonl`，照旧能导。

## 一、目录约定

```
content/series.jsonl                 每个系列一行：名称、来源、许可、排序
content/series/<code>/lessons.jsonl  这个系列的课，一行一课，映射写在行里
content/series/_example/lessons.jsonl  格式示例（2 课），只给测试和看格式用
```

`<code>` 是系列编号：小写字母、数字、下划线、连字符（会拼进文件路径，别的字符
导入时直接拒绝）。下划线开头的目录（`_example`）不进正式导入（`py -m kg` 只导
不以下划线开头的系列）。

### series.jsonl 的一行

```json
{"code": "hanabira", "label": "hanabira 语法", "description": "…", "source": "hanabira.org", "license": "CC BY 4.0", "sort": 0}
```

| 键 | 必填 | 说明 |
|---|---|---|
| code | 是 | 系列编号，跟目录名一样 |
| label | 是 | 显示名：教材页下拉、抬头、老师提示词里用 |
| description | | 一句简介 |
| source | | 来源（网站、书名） |
| license | | 许可（CC BY 4.0 之类）。署名写进 `content/NOTICE.md` |
| sort | | 排序，小的在前，默认 0。**小于 0 的不进教材页的下拉**（测试、示例用） |

每次导入（不管导哪个系列）都按编号 upsert 这个文件。新系列要出现在下拉里，必须
在这里有一行、sort ≥ 0。

## 二、lessons.jsonl 的一行（一课）

```json
{"code": "mnn-001", "series": "mnn", "level": "N5", "seq": 1,
 "title": "…", "summary": "…", "explanation": "…", "formation": "…",
 "examples": "[{\"jp\": \"…\", \"zh\": \"…\"}]",
 "items": ["te-kara"], "points": ["f-desire"]}
```

（实际文件一行一课，上面为了好看折了行。）

| 键 | 必填 | 说明 |
|---|---|---|
| code | 是 | 课号，**全库唯一**。约定 `<系列前缀>-NNN`，如 `mnn-001`；前缀是第一个连字符之前那段，问老师时说出课号（「讲一下 mnn-001」）就认得出。跟别的系列撞号会让整个导入失败回滚 |
| series | | 不写就是正在导入的系列；写了必须一致，不一致这一行拒收 |
| level | 是 | 等级 N5–N1（教材页按它筛） |
| seq | | 课序（整数）。线性教材填：抬头显示「第{seq}课」，问老师说「第3课」就在当前系列里按课序找。不填就按 hanabira 的规矩（课号末尾三位数，「N5 第46课」） |
| title | 是 | 标题 |
| summary | 是 | 一句话 |
| explanation | 是 | 讲解正文 |
| formation | | 接续 |
| examples | | 例句，JSON **文本**：`[{"jp": …, "zh": …}]` |
| items | | 这课讲的**已有条目**编号（`content/items.jsonl` 的 code），数组，先后就是 rank |
| points | | 这课讲的**已有知识点**编号（`content/kg.jsonl` 的 id），数组。对不上具体条目、只知道讲哪个知识点时用 |

items 和 points 至少写一样，否则这课是「孤课」（报告里 orphans 会数到它）：
没有题可出，老师也不知道它讲的是哪个点。

## 三、映射规则

- **只引用已有的 item / node，绝不新建。** 新教材讲到图里没有的语法，先在
  `kg.jsonl` / `items.jsonl` 里把知识点、条目加好（那是另一件事），再映射。
- 一行课的 items、points 里**只要有一个编号库里没有，整行拒收**：这课不进库，
  它的映射也不进。别的行照常导入。拒收的进报告，修好文件重导即可。
- 映射到条目（items）→ 写进 `item_lesson`（rank = 列出的顺序）；映射到知识点
  （points）→ 写进 `lesson_point`。
- 按课练（做题页 `#做题?lesson=<code>`）的题：hanabira 的课用题库里按课号打了标
  的题；别的系列的课用映射——items 里条目的题，加上 points 里知识点下所有条目
  的题。都没有题时做题页说「这一课映射的知识点下还没有题」。
- 做题、复习、得分、掌握都按知识点算，跨系列共享，不因系列不同而分开。

## 四、怎么导入

条目、知识点要先在库里（`py -m kg import` 或启动时会先导图）。然后：

```bash
# 起着服务时（端口按实际）
curl -s -X POST http://127.0.0.1:8190/lesson/import \
     -H 'Content-Type: application/json' -d '{"form": {"series": "mnn"}}'
```

或者 `py -m kg import`：先导 hanabira，再导 `content/series/` 下每个不以下划线
开头、有 lessons.jsonl 的系列。

导入**按系列清空重灌**：只删这个系列的 lesson、item_lesson、lesson_point 行再
重灌，别的系列一行不动；学习记录（attempt、mastery、score、对话、偏好）一律不碰。
整个导入一个事务：课文文件有坏行（缺编号、编号重复、撞了别的系列的编号）就全部
回滚，库里保持原样。

## 五、看报告

导入返回一个 JSON：

| 键 | 说明 |
|---|---|
| series | 导的哪个系列 |
| lessons | 导入了几课 |
| links | 映射到条目的条数（item_lesson） |
| points | 映射到知识点的条数（lesson_point） |
| rejected | 拒收了几行 |
| rejected_rows | 拒收清单：`[{file, row, code, reason}]`，row 是文件里第几行（从 1 数），reason 如「条目 te-karaa 不存在」 |
| orphans | 这个系列里没映射到任何条目、知识点的课 |
| failed | 老格式（hanabira 的 item_lessons.jsonl）没挂上的挂接行数，也在 rejected_rows 里 |
| note | 同样的内容写成一句话（`py -m kg import` 打印它） |

rejected 不是 0 就去 rejected_rows 里看是哪一行、哪个编号，改文件重导。

## 六、学习者怎么用

教材页顶栏「系列」下拉（只列 sort ≥ 0 的系列，只有一个也显示）选一套，选了就记
进这个学习者的偏好（`learner_pref`），课文表、「第N课」、老师的教材目录和推荐
的课都按它；问老师找课时先在当前系列里找，找不到才去别的系列，并在回复和链接里
标出系列名。
