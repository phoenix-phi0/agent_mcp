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
设 pRule = 读原文 pack:sys_frule.md
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
如果 {pRule.ok} 不等于 是
  终止 失败 读不到提示词：{pRule.msg}
结束

# 一、功能清单：模型写 → 校验清单 → 不过带报错重写 1 次
设 err = 无
设 ok = 否
当 {ok} 不等于 是 最多 2 次
  问 invTxt = {pPlan.text} 需求：{task} 上次的报错：{err}
  设 cl = 校验清单 {invTxt} {task}
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
打印 功能清单：{cl.数量} 个功能，模板 {cl.模板}，角色 {cl.角色}

# 二、实体：同旧模板，输入多一份功能清单
设 err = 无
设 ok = 否
当 {ok} 不等于 是 最多 2 次
  问JSON ent = {pEnt.text} 需求：{task} 功能清单：{cl.功能} 角色：{cl.角色} 上次的报错：{err} 格式 模板:default|full|private 实体文本:文本
  设 v = 校验实体 {ent.实体文本} {ent.模板} {task} {cl.角色模板}
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
设 gp.角色 = {cl.角色}
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
设 partial =
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

  # 4.2 zs → routes/<功能>.zs 或 routes/<功能>_*.zs（可多文件）＋回复里追加的 queries/<功能>_*.sql（先预编译，通过才写盘）
  # 写盘后：检查项目 → 校验角色（清单标了角色的接口要带「角色 x」）→ 核对规则（模型逐条判）。
  # 语法／角色不过：撤回本次写的再重写（最多 2 次）；规则核对有「否」：撤回重写 1 次（与语法重写分开计）；仍有未实现：不判失败，记未实现规则。
  设 k = 0
  设 kk = 0
  设 unimpl = []
  设 zsFail = 否
  如果 {f.接口} 等于 []
    打印 功能记录 {fn} zs 跳过 0
    打印 功能记录 {fn} 核对 跳过 0
  否则
    设 rr = 0
    设 zsDone = 否
    设 rerr = 无
    当 {zsDone} 不等于 是 最多 2 次
      设 rr = 计算 {rr} + 1
      设 err = {rerr}
      设 ok = 否
      当 {ok} 不等于 是 最多 2 次
        设 k = 计算 {k} + 1
        设 sum = 项目摘要 {sp}
        问 zsTxt = {pZs.text} 需求：{task} 实体：{ent.实体文本} 本功能：{f} 本功能规则：{f.规则} 项目角色：{cl.角色} 本功能sql：{sqlTxt} 全项目名字摘要：{sum.text} 上次的报错：{err}
        设 zsf = 拆分隔块 {zsTxt} routes/{fn}.zs|routes/{fn}_*.zs 是
        如果 {zsf.ok} 不等于 是
          设 err = {zsf.msg}
        否则
          设 zsq = 拆分隔块 {zsTxt} queries/{fn}_*.sql 是 是
          设 c = 预编译sql {zsq} {ent.实体文本}
          如果 {zsq.ok} 不等于 是
            设 err = {zsq.msg}
          否则如果 {c.ok} 不等于 是
            设 err = {c.msg}
          否则
            设 bk = 留底
            设 w = 写文件 {zsq}
            设 w = 写文件 {zsf}
            设 b = 检查项目
            如果 {b.ok} 不等于 是
              设 err = {b.msg}
              设 u = 撤回 {bk.id}
            否则
              设 rc = 校验角色 {f}
              如果 {rc.ok} 等于 是
                设 ok = 是
              否则
                设 err = {rc.msg}
                设 u = 撤回 {bk.id}
              结束
            结束
          结束
        结束
      结束
      如果 {ok} 不等于 是
        如果 {rr} 大于 1
          # 规则重写这一轮语法两次都不过：放回上一版（它通过了检查），不判功能失败
          设 w = 写文件 {zsq1}
          设 w = 写文件 {zsf1}
          设 unimpl = {unimpl1}
        否则
          设 zsFail = 是
        结束
        设 zsDone = 是
      否则
        如果 {f.规则} 等于 []
          设 zsDone = 是
        否则
          设 kk = 计算 {kk} + 1
          问 chk = {pRule.text} 规则：{f.规则} 本功能sql：{sqlTxt} zs全文：{zsTxt}
          设 cr = 核对规则 {chk} {f}
          如果 {cr.ok} 等于 是
            设 zsDone = 是
          否则
            如果 {rr} 小于 2
              设 zsq1 = {zsq}
              设 zsf1 = {zsf}
              设 unimpl1 = {cr.未实现列表}
              设 rerr = 以下业务规则没有实现，请补全（其余规则别丢）：{cr.未实现}
              设 u = 撤回 {bk.id}
            否则
              设 unimpl = {cr.未实现列表}
              设 zsDone = 是
            结束
          结束
        结束
      结束
    结束
    如果 {zsFail} 等于 是
      设 u = 撤回 {bkF.id}
      设 fails = {fails} {fn}
      打印 功能记录 {fn} zs 失败 {k}
      打印 功能失败 {fn} zs {err}
      继续
    结束
    打印 功能记录 {fn} zs 通过 {k}
    如果 {f.规则} 等于 []
      打印 功能记录 {fn} 核对 跳过 0
    否则
      如果 {unimpl} 等于 []
        打印 功能记录 {fn} 核对 通过 {kk}
      否则
        打印 功能记录 {fn} 核对 失败 {kk}
        打印 功能未实现 {fn} {unimpl}
        设 partial = {partial} {fn}
      结束
    结束
  结束

  # 4.3 ui → ui/<功能>.ui 或 ui/<功能>_*.ui（可多文件；写盘后 检查项目 把 gen 对 .ui 的解析失败也当不过）
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
      设 uif = 拆分隔块 {uiTxt} ui/{fn}.ui|ui/{fn}_*.ui 是
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
  终止 失败 部分成功：失败的功能：{fails}；规则没全部实现的功能：{partial}
结束
如果 {partial} 不为空
  终止 失败 部分成功：规则没全部实现的功能：{partial}
结束
打印 结论：修好 项目已生成
终止 成功 完成：{cl.数量} 个功能全部生成
