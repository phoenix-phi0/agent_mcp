# newproj.zs —— 新建项目固定模板：实体 → 生成增删改查 → 定制 sql → routes/custom.zs → ui/custom.ui。
# 变量 task = 需求原文（v2 执行和空跑都会设）；项目目录 = 引擎工作目录。提示词正文在本包 prompts/*.md（读原文 pack:xxx.md）。
# 每步检查不过，带报错重写 1 次；custom.zs / custom.ui 检查不过先撤回再重写。不含覆盖 gen 路由文件的分支。
用包 common text code newproj
预算 调用 8 秒 900

设 pEnt = 读原文 pack:sys_ent.md
设 pSql = 读原文 pack:sys_sql.md
设 pZs = 读原文 pack:sys_zs.md
设 pUi = 读原文 pack:sys_ui.md
如果 {pEnt.ok} 不等于 是
  终止 失败 读不到提示词：{pEnt.msg}
结束
如果 {pSql.ok} 不等于 是
  终止 失败 读不到提示词：{pSql.msg}
结束
如果 {pZs.ok} 不等于 是
  终止 失败 读不到提示词：{pZs.msg}
结束
如果 {pUi.ok} 不等于 是
  终止 失败 读不到提示词：{pUi.msg}
结束

# 一、实体：模型写 → 校验（含 private 只在需求提到登录/账号/只看自己时才许选）→ 不过带报错重写 1 次
设 err = 无
设 ok = 否
当 {ok} 不等于 是 最多 2 次
  问JSON ent = {pEnt.text} 需求：{task} 上次的报错：{err} 格式 模板:default|full|private 实体文本:文本
  设 v = 校验实体 {ent.实体文本} {ent.模板} {task}
  如果 {v.ok} 等于 是
    设 ok = 是
  否则
    设 err = {v.errors}
  结束
结束
如果 {ok} 不等于 是
  终止 失败 实体两次都没过：{err}
结束
设 ef.file = entities/app.entity
设 ef.content = {ent.实体文本}
设 w = 写文件 {ef}
如果 {w.ok} 不等于 是
  终止 失败 写不了实体文件：{w.msg}
结束

# 二、生成增删改查（private 会先加登录注册）→ 检查项目
设 gp.项目目录 = .
设 gp.模板 = {ent.模板}
设 g = 生成增删改查 {gp}
如果 {g.ok} 不等于 是
  终止 失败 生成增删改查不过：{g.msg}
结束
设 b = 检查项目
如果 {b.ok} 不等于 是
  终止 失败 gen 生成的项目检查不过：{b.msg}
结束

# 三、定制 sql：分隔块 → 逐条预编译 → 不过带报错重写 1 次
设 sum = 项目摘要
设 err = 无
设 ok = 否
当 {ok} 不等于 是 最多 2 次
  问 sqlTxt = {pSql.text} 需求：{task} 实体：{ent.实体文本} 已有：{sum.text} 上次的报错：{err}
  设 sqlf = 拆分隔块 {sqlTxt} queries/
  设 c = 预编译sql {sqlf} {ent.实体文本}
  如果 {c.ok} 等于 是
    设 ok = 是
  否则
    设 err = {c.msg}
  结束
结束
如果 {ok} 不等于 是
  终止 失败 定制 sql 两次都没过：{err}
结束
设 w = 写文件 {sqlf}
如果 {w.ok} 不等于 是
  终止 失败 写不了 sql：{w.msg}
结束

# 四、routes/custom.zs（输入含第三步 sql 原文）→ 检查项目 → 不过撤回并带报错重写 1 次
设 sum = 项目摘要
设 err = 无
设 ok = 否
当 {ok} 不等于 是 最多 2 次
  问 zsTxt = {pZs.text} 需求：{task} 第3步sql：{sqlTxt} gen已有接口：{sum.text} 上次的报错：{err}
  设 zsf = 拆分隔块 {zsTxt} routes/custom.zs
  设 bk = 留底
  设 w = 写文件 {zsf}
  设 b = 检查项目
  如果 {b.ok} 等于 是
    设 ok = 是
  否则
    设 err = {b.msg}
    设 u = 撤回 {bk.id}
  结束
结束
如果 {ok} 不等于 是
  终止 失败 custom.zs 两次都没过：{err}
结束

# 五、ui/custom.ui → 检查项目 → 不过撤回并带报错重写 1 次
设 sum = 项目摘要
设 err = 无
设 ok = 否
当 {ok} 不等于 是 最多 2 次
  问 uiTxt = {pUi.text} 需求：{task} 第4步zs：{zsTxt} 已有：{sum.text} 上次的报错：{err}
  设 uif = 拆分隔块 {uiTxt} ui/custom.ui
  设 bk = 留底
  设 w = 写文件 {uif}
  设 b = 检查项目
  如果 {b.ok} 等于 是
    设 ok = 是
  否则
    设 err = {b.msg}
    设 u = 撤回 {bk.id}
  结束
结束
如果 {ok} 不等于 是
  终止 失败 custom.ui 两次都没过：{err}
结束

打印 结论：修好 项目已生成
终止 成功 完成
