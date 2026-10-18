# newproj_split.zs —— 新建项目「按功能分次生成」模板：功能清单 → 实体 → 生成增删改查 → 逐个功能（sql → routes/<功能>.zs → ui/<功能>.ui）→ 整体检查。
# 旧 newproj.zs 不动（整层一次写完）；本模板每次只写一个功能的一个文件，输入只带该功能清单项 + 实体 + 全项目名字摘要。
# 变量 task = 需求原文；项目目录 = 引擎工作目录。「遍历 … 序号」是现成的循环，不需要新语法；预算按功能数放宽（4 + 功能数×6，见 校验清单）。
# 每个文件单独检查、单独重写 1 次；某功能的某个文件两次都不过 → 撤回该功能已写的文件、记入失败列表、继续下一个功能。
# 打印「功能记录 名 步骤 通过|失败|跳过 尝试次数」，v2.run_newproj 解析进 result.json 的 v2.功能。
用包 common text code newproj
预算 调用 4 秒 3600

设 pPlan = 读原文 pack:sys_plan.md
设 pEnt = 读原文 pack:sys_ent.md
设 pSql = 读原文 pack:sys_fsql.md
设 pZs = 读原文 pack:sys_fzs.md
设 pUi = 读原文 pack:sys_fui.md
如果 {pPlan.ok} 不等于 是
  终止 失败 读不到提示词：{pPlan.msg}
结束
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

# 一、功能清单：模型写 → 校验清单 → 不过带报错重写 1 次
设 err = 无
设 ok = 否
当 {ok} 不等于 是 最多 2 次
  问 invTxt = {pPlan.text} 需求：{task} 上次的报错：{err}
  设 cl = 校验清单 {invTxt}
  如果 {cl.ok} 等于 是
    设 ok = 是
  否则
    设 err = {cl.errors}
  结束
结束
如果 {ok} 不等于 是
  终止 失败 功能清单两次都没过：{err}
结束
预算 调用 {cl.调用上限} 秒 3600
打印 功能清单：{cl.数量} 个功能，模板 {cl.模板}

# 二、实体：同旧模板，输入多一份功能清单
设 err = 无
设 ok = 否
当 {ok} 不等于 是 最多 2 次
  问JSON ent = {pEnt.text} 需求：{task} 功能清单：{cl.功能} 上次的报错：{err} 格式 模板:default|full|private 实体文本:文本
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

# 三、生成增删改查 → 检查项目
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

# 四、逐个功能：sql → zs → ui；任一文件两次不过 → 撤回该功能所有已写文件，记失败，继续下一个功能
设 fails =
设 sp.含参数 = 是
遍历 f 于 {cl.功能} 序号 i
  设 fn = {f.名}
  设 bkF = 留底

  # 4.1 sql → queries/<功能>_*.sql（拆分隔块 + 预编译sql，通过才写盘）
  设 sqlTxt = 无
  设 k = 0
  如果 {f.sql} 等于 []
    打印 功能记录 {fn} sql 跳过 0
  否则
    设 sum = 项目摘要 {sp}
    设 err = 无
    设 ok = 否
    当 {ok} 不等于 是 最多 2 次
      设 k = 计算 {k} + 1
      问 sqlTxt = {pSql.text} 需求：{task} 实体：{ent.实体文本} 本功能：{f} 全项目名字摘要：{sum.text} 上次的报错：{err}
      设 sqlf = 拆分隔块 {sqlTxt} queries/{fn} 是
      如果 {sqlf.ok} 不等于 是
        设 err = {sqlf.msg}
      否则
        设 c = 预编译sql {sqlf} {ent.实体文本}
        如果 {c.ok} 等于 是
          设 ok = 是
        否则
          设 err = {c.msg}
        结束
      结束
    结束
    如果 {ok} 不等于 是
      设 u = 撤回 {bkF.id}
      设 fails = {fails} {fn}
      打印 功能记录 {fn} sql 失败 {k}
      打印 功能失败 {fn} sql {err}
      继续
    结束
    设 w = 写文件 {sqlf}
    打印 功能记录 {fn} sql 通过 {k}
  结束

  # 4.2 zs → routes/<功能>.zs（写盘后检查项目，不过撤回再重写）
  设 k = 0
  如果 {f.接口} 等于 []
    打印 功能记录 {fn} zs 跳过 0
  否则
    设 err = 无
    设 ok = 否
    当 {ok} 不等于 是 最多 2 次
      设 k = 计算 {k} + 1
      设 sum = 项目摘要 {sp}
      问 zsTxt = {pZs.text} 需求：{task} 实体：{ent.实体文本} 本功能：{f} 本功能sql：{sqlTxt} 全项目名字摘要：{sum.text} 上次的报错：{err}
      设 zsf = 拆分隔块 {zsTxt} routes/{fn}.zs 是
      如果 {zsf.ok} 不等于 是
        设 err = {zsf.msg}
      否则
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
    结束
    如果 {ok} 不等于 是
      设 u = 撤回 {bkF.id}
      设 fails = {fails} {fn}
      打印 功能记录 {fn} zs 失败 {k}
      打印 功能失败 {fn} zs {err}
      继续
    结束
    打印 功能记录 {fn} zs 通过 {k}
  结束

  # 4.3 ui → ui/<功能>.ui（同 zs）
  设 k = 0
  如果 {f.界面} 等于 []
    打印 功能记录 {fn} ui 跳过 0
  否则
    设 err = 无
    设 ok = 否
    当 {ok} 不等于 是 最多 2 次
      设 k = 计算 {k} + 1
      设 sum = 项目摘要 {sp}
      问 uiTxt = {pUi.text} 需求：{task} 实体：{ent.实体文本} 本功能：{f} 全项目名字摘要：{sum.text} 上次的报错：{err}
      设 uif = 拆分隔块 {uiTxt} ui/{fn}.ui 是
      如果 {uif.ok} 不等于 是
        设 err = {uif.msg}
      否则
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
    结束
    如果 {ok} 不等于 是
      设 u = 撤回 {bkF.id}
      设 fails = {fails} {fn}
      打印 功能记录 {fn} ui 失败 {k}
      打印 功能失败 {fn} ui {err}
      继续
    结束
    打印 功能记录 {fn} ui 通过 {k}
  结束
结束

# 五、整体检查（重复路由、sql 引用、ui 动作对应接口等）
设 b = 检查项目
如果 {b.ok} 不等于 是
  终止 失败 整体检查不过：{b.msg}
结束
如果 {fails} 不为空
  终止 失败 部分成功：失败的功能：{fails}
结束
打印 结论：修好 项目已生成
终止 成功 完成：{cl.数量} 个功能全部生成
