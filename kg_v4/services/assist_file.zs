业务 assist_file
  依赖 subject
  用包 db common text doc data

  函数 本科目 learner current_role auth_mode subject need?
    设 r = 调用 subject.解析科目 learner={learner} current_role={current_role} auth_mode={auth_mode} subject={subject} need={need}
    返回 {"subject_id": {r.subject_id}}
  结束

  函数 本人附件 current_user file_id subject_id
    设 ok = 匹配 {file_id} ^[1-9]\d*$
    如果 {ok.matched} 不等于 是
      报错 400 file_id 不合法
    结束
    设 row = 查一行 app.db assist_file_by_id file_id={file_id} teacher={current_user} subject_id={subject_id}
    如果 {row.id} 为空
      报错 404 没有这个附件
    结束
    返回 {row}
  结束

  函数 附件标签 name ext pages chars rows
    如果 {ext} 等于 pdf
      设 info = {ext} · {pages} 页 · {chars} 字
    否则如果 {ext} 等于 csv
      设 info = {ext} · {rows} 行 · {chars} 字
    否则
      设 info = {ext} · {chars} 字
    结束
    设 label = 附件：{name}（{info}）
    返回 {"label": "{label}", "info": "{info}"}
  结束

  函数 判类型 file_name file_path file_ext
    设 raw = {file_ext}
    如果 {raw} 为空
      设 hd = 匹配 {file_name} \.
      如果 {hd.matched} 等于 是
        设 raw = 替换 {file_name} ^.*\.
      结束
    结束
    如果 {raw} 为空
      设 hp = 匹配 {file_path} \.
      如果 {hp.matched} 等于 是
        设 raw = 替换 {file_path} ^.*\.
      结束
    结束
    设 raw = 替换 {raw} ^\.+
    设 ext = {raw}
    遍历 k 于 txt，md，csv，pdf，docx，xlsx，xls，png，jpg，jpeg，gif，webp，bmp
      设 mm = 匹配 {raw} (?i)^{k}$
      如果 {mm.matched} 等于 是
        设 ext = {k}
      结束
    结束
    如果 {ext} 等于 txt 或 {ext} 等于 md 或 {ext} 等于 csv 或 {ext} 等于 pdf 或 {ext} 等于 docx
      设 err = {zz 或}
    否则如果 {ext} 等于 xlsx 或 {ext} 等于 xls
      设 w2 = 不支持
      设 err = {w2} Excel 文件，请在 Excel 里另存为 csv（逗号分隔）再上传
    否则如果 {ext} 等于 png 或 {ext} 等于 jpg 或 {ext} 等于 jpeg 或 {ext} 等于 gif 或 {ext} 等于 webp 或 {ext} 等于 bmp
      设 w3 = 本期不支持图片，可以把文字贴进对话里，或者传
      设 err = {w3} PDF
    否则
      设 w1 = 只支持
      设 err = {w1} txt、md、csv、pdf、docx 文件
    结束
    返回 {"ext": "{ext}", "error": "{err}"}
  结束

  函数 取格 row n
    设 cell = {row}
    如果 {n} 大于 0
      设 pre = ^
      重复 {n} 次
        设 pre = {pre}[^,]*,
      结束
      设 pm = 匹配 {row} {pre}
      如果 {pm.matched} 等于 是
        设 cell = 替换 {row} {pre}
      否则
        设 cell = {zz 或}
      结束
    结束
    设 cell = 替换 {cell} ,.*$
    设 cell = 替换 {cell} ^\s+|\s+$
    返回 {"v": "{cell}"}
  结束

  函数 csv统计 file_path text
    设 nlo = {"n": "\n"}
    设 nl = {nlo.n}
    设 lines = 按正则切分 {text} \r?\n
    设 hdr = {zz 或}
    设 data = []
    遍历 ln 于 {lines}
      设 t1 = 替换 {ln} ^\s+|\s+$
      如果 {t1} 不为空
        如果 {hdr} 为空
          设 hdr = 替换 {ln} ^\ufeff
        否则
          设 data = 列表加项 {data} {ln}
        结束
      结束
    结束
    设 rowcnt = 列表长度 {data}
    设 parts = 按正则切分 {hdr} ,
    设 ncols = 列表长度 {parts}
    设 shown = {ncols}
    如果 {ncols} 大于 30
      设 shown = 30
    结束
    设 names = {zz 或}
    设 colstats = {zz 或}
    重复 {shown} 次 计数 c
      设 c0 = 计算 {c} - 1
      设 nm = 调用 取格 row={hdr} n={c0}
      设 cname = {nm.v}
      如果 {c} 等于 1
        设 names = {cname}
      否则
        设 names = {names}、{cname}
      结束
      设 numeric = 1
      设 cnt = 0
      设 miss = 0
      设 tot = 0
      设 minv = 0
      设 maxv = 0
      设 mintxt = {zz 或}
      设 maxtxt = {zz 或}
      遍历 ln2 于 {data}
        设 cv = 调用 取格 row={ln2} n={c0}
        设 cell = {cv.v}
        如果 {cell} 为空
          设 miss = 计算 {miss} + 1
        否则
          设 nm1 = 匹配 {cell} ^-?\d+(\.\d+)?$
          如果 {nm1.matched} 等于 是
            设 num = 转数字 {cell}
            设 cnt = 计算 {cnt} + 1
            设 tot = 计算 {tot} + {num}
            如果 {cnt} 等于 1
              设 minv = {num}
              设 maxv = {num}
              设 mintxt = {cell}
              设 maxtxt = {cell}
            否则
              如果 {num} 小于 {minv}
                设 minv = {num}
                设 mintxt = {cell}
              结束
              如果 {num} 大于 {maxv}
                设 maxv = {num}
                设 maxtxt = {cell}
              结束
            结束
          否则
            设 numeric = 0
          结束
        结束
      结束
      如果 {numeric} 等于 1 且 {cnt} 大于 0
        设 cents = 计算 取整(四舍五入({tot} * 100 / {cnt}))
        设 sg = {zz 或}
        如果 {cents} 小于 0
          设 sg = -
          设 cents = 计算 绝对值({cents})
        结束
        设 ip = 计算 {cents} // 100
        设 fp2 = 计算 {cents} % 100
        如果 {fp2} 小于 10
          设 fp2 = 0{fp2}
        结束
        设 mean = {sg}{ip}.{fp2}
        设 mn = {mintxt}
        设 dm = 匹配 {mn} \.
        如果 {dm.matched} 等于 是
          设 mn = 替换 {mn} 0+$
          设 mn = 替换 {mn} \.$
        结束
        设 mx2 = {maxtxt}
        设 dm2 = 匹配 {mx2} \.
        如果 {dm2.matched} 等于 是
          设 mx2 = 替换 {mx2} 0+$
          设 mx2 = 替换 {mx2} \.$
        结束
        设 line = {cname}：均值 {mean}，最低 {mn}，最高 {mx2}，缺失 {miss}
      否则
        设 line = {cname}：文本列，缺失 {miss}
      结束
      如果 {colstats} 为空
        设 colstats = {line}
      否则
        设 colstats = {colstats}{nl}{line}
      结束
    结束
    设 gong = 共
    设 stats = {gong} {rowcnt} 行，{ncols} 列：{names}
    设 stats = {stats}{nl}{colstats}
    如果 {ncols} 大于 30
      设 extra = 计算 {ncols} - 30
      设 stats = {stats}{nl}（另有 {extra} 列未列出）
    结束
    如果 {rowcnt} 等于 0
      设 stats = 只有表头，没有数据行：{names}
    结束
    返回 {"rows": {rowcnt}, "stats": "{stats}"}
  结束

  公开 函数 存附件 current_user file_path file_name? file_size? file_ext? current_role? auth_mode? subject?
    设 sr = 调用 本科目 learner={current_user} current_role={current_role} auth_mode={auth_mode} subject={subject} need=write
    设 subject_id = {sr.subject_id}
    如果 {current_user} 为空
      报错 400 current_user 不能为空
    结束
    设 fp = 替换 {file_path} ^\s+|\s+$
    如果 {fp} 为空
      报错 400 文件路径不能为空
    结束
    设 jt = 调用 判类型 file_name={file_name} file_path={fp} file_ext={file_ext}
    如果 {jt.error} 不为空
      报错 400 {jt.error}
    结束
    设 ext = {jt.ext}
    设 sizev = 0
    设 sm = 匹配 {file_size} ^\d+$
    如果 {sm.matched} 等于 是
      设 sizev = 转数字 {file_size}
      如果 {sizev} 大于 10485760
        报错 400 附件不能超过 10MB
      结束
    结束
    设 name = {file_name}
    如果 {name} 为空
      设 name = 替换 {fp} ^.*/
    结束
    设 now = 当前时间
    设 ex = 查一行 app.db assist_file_by_path teacher={current_user} subject_id={subject_id} path={fp}
    如果 {ex.id} 不为空
      事务 app.db
        设 n1 = 写库 app.db assist_file_detach_all teacher={current_user} subject_id={subject_id}
        设 n2 = 写库 app.db assist_file_attach id={ex.id} now={now}
      结束
      设 lb0 = 调用 附件标签 name={ex.name} ext={ex.ext} pages={ex.pages} chars={ex.chars} rows={ex.rows}
      返回 {"ok": 1, "file_id": {ex.id}, "name": "{ex.name}", "ext": "{ex.ext}", "pages": {ex.pages}, "chars": {ex.chars}, "rows": {ex.rows}, "label": "{lb0.label}", "info": "{lb0.info}", "reused": 1}
    结束
    设 cnt = 查一值 app.db assist_file_count teacher={current_user} subject_id={subject_id}
    如果 {cnt} 不小于 20
      报错 409 每个科目最多保留 20 个附件，请先删掉不用的附件
    结束
    设 dd = 读文档 {fp}
    如果 {dd.error} 不为空
      报错 400 {dd.error}
    结束
    设 body0 = {dd.text}
    设 t2 = 替换 {body0} \s+
    如果 {t2} 为空
      报错 400 文件里没有可读的文字
    结束
    设 body = 截取 {body0} 1 50000
    设 pages = 0
    如果 {ext} 等于 pdf
      设 pages = {dd.pages 或 0}
    结束
    设 chars = {dd.chars 或 0}
    设 rowcnt = 0
    设 stats = {zz 或}
    如果 {ext} 等于 csv
      设 cs = 调用 csv统计 file_path={fp} text={body0}
      设 rowcnt = {cs.rows}
      设 stats = {cs.stats}
    结束
    设 rec = {"teacher": "{current_user}", "subject_id": "{subject_id}", "name": "{name}", "ext": "{ext}", "size": "{sizev}", "path": "{fp}", "pages": "{pages}", "chars": "{chars}", "text": "{body}", "stats": "{stats}", "rows": "{rowcnt}", "now": "{now}"}
    事务 app.db
      设 n1 = 写库 app.db assist_file_detach_all teacher={current_user} subject_id={subject_id}
      设 n2 = 写库表 app.db assist_file_insert {rec}
    结束
    设 fid = 查一值 app.db assist_file_latest_id teacher={current_user} subject_id={subject_id} path={fp}
    设 lb = 调用 附件标签 name={name} ext={ext} pages={pages} chars={chars} rows={rowcnt}
    返回 {"ok": 1, "file_id": {fid}, "name": "{name}", "ext": "{ext}", "pages": {pages}, "chars": {chars}, "rows": {rowcnt}, "label": "{lb.label}", "info": "{lb.info}", "reused": 0}
  结束

  公开 函数 取当前附件 current_user current_role? auth_mode? subject?
    设 sr = 调用 本科目 learner={current_user} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 row = 查一行 app.db assist_file_current teacher={current_user} subject_id={sr.subject_id}
    如果 {row.id} 为空
      返回 {"file_id": "", "name": "", "ext": "", "pages": "", "chars": "", "rows": "", "label": ""}
    结束
    设 lb = 调用 附件标签 name={row.name} ext={row.ext} pages={row.pages} chars={row.chars} rows={row.rows}
    返回 {"file_id": {row.id}, "name": "{row.name}", "ext": "{row.ext}", "pages": {row.pages}, "chars": {row.chars}, "rows": {row.rows}, "label": "{lb.label}"}
  结束

  公开 函数 挂上附件 current_user file_id current_role? auth_mode? subject?
    设 sr = 调用 本科目 learner={current_user} current_role={current_role} auth_mode={auth_mode} subject={subject} need=write
    设 row = 调用 本人附件 current_user={current_user} file_id={file_id} subject_id={sr.subject_id}
    设 now = 当前时间
    事务 app.db
      设 n1 = 写库 app.db assist_file_detach_all teacher={current_user} subject_id={sr.subject_id}
      设 n2 = 写库 app.db assist_file_attach id={row.id} now={now}
    结束
    设 lb = 调用 附件标签 name={row.name} ext={row.ext} pages={row.pages} chars={row.chars} rows={row.rows}
    返回 {"ok": 1, "file_id": {row.id}, "label": "{lb.label}"}
  结束

  公开 函数 移除附件 current_user file_id? current_role? auth_mode? subject?
    设 sr = 调用 本科目 learner={current_user} current_role={current_role} auth_mode={auth_mode} subject={subject} need=write
    设 dropped = 0
    如果 {file_id} 为空
      设 dropped = 查一值 app.db assist_file_attached_count teacher={current_user} subject_id={sr.subject_id}
      设 n1 = 写库 app.db assist_file_detach_all teacher={current_user} subject_id={sr.subject_id}
    否则
      设 row = 调用 本人附件 current_user={current_user} file_id={file_id} subject_id={sr.subject_id}
      如果 {row.attached} 等于 1
        设 dropped = 1
      结束
      设 n1 = 写库 app.db assist_file_detach_one id={row.id}
    结束
    返回 {"ok": 1, "dropped": {dropped}}
  结束

  公开 函数 删除附件 current_user file_id current_role? auth_mode? subject?
    设 sr = 调用 本科目 learner={current_user} current_role={current_role} auth_mode={auth_mode} subject={subject} need=write
    设 row = 调用 本人附件 current_user={current_user} file_id={file_id} subject_id={sr.subject_id}
    设 n1 = 写库 app.db assist_file_delete id={row.id}
    返回 {"ok": 1, "file_id": {row.id}}
  结束

  公开 函数 列附件 current_user current_role? auth_mode? subject?
    设 sr = 调用 本科目 learner={current_user} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 rs = 查询 app.db assist_file_list teacher={current_user} subject_id={sr.subject_id}
    设 total = 列表长度 {rs}
    设 files = []
    遍历 it 于 {rs}
      设 lb = 调用 附件标签 name={it.name} ext={it.ext} pages={it.pages} chars={it.chars} rows={it.rows}
      设 at = 截取 {it.created_at} 1 16
      设 item = {"att_id": {it.id}, "att_name": "{it.name}", "att_info": "{lb.info}", "att_at": "{at}", "att_on": {it.attached}}
      设 files = 列表加项 {files} {item}
    结束
    返回 {"total": {total}, "limit": 20, "files": {files}}
  结束

  公开 函数 取附件文本 current_user file_id question? max_chars? current_role? auth_mode? subject?
    设 sr = 调用 本科目 learner={current_user} current_role={current_role} auth_mode={auth_mode} subject={subject}
    设 row = 调用 本人附件 current_user={current_user} file_id={file_id} subject_id={sr.subject_id}
    设 src = {row.text}
    设 n = 转数字 {row.chars 或 0}
    设 mx = 6000
    如果 {max_chars} 不为空
      设 mq = 匹配 {max_chars} ^\d+$
      如果 {mq.matched} 不等于 是
        报错 400 max_chars 不合法
      结束
      设 mx = 转数字 {max_chars}
      如果 {mx} 小于 500 或 {mx} 大于 6000
        报错 400 max_chars 不合法
      结束
    结束
    设 nlo = {"n": "\n"}
    设 nl = {nlo.n}
    设 now = 当前时间
    设 mode = full
    设 tr = 0
    设 outtext = {src}
    如果 {row.ext} 等于 csv
      设 mode = csv
      设 lines = 按正则切分 {src} \r?\n
      设 got = 0
      设 hdrdone = 0
      设 used = 0
      设 stop = 0
      设 outtext = {zz 或}
      遍历 ln 于 {lines}
        设 t1 = 替换 {ln} ^\s+|\s+$
        如果 {t1} 不为空 且 {stop} 等于 0
          设 ll = 找全部 {ln} (?s).
          设 len1 = 列表长度 {ll}
          如果 {hdrdone} 等于 0
            设 outtext = {ln}
            设 used = {len1}
            设 hdrdone = 1
          否则
            设 add = 计算 {used} + {len1} + 1
            如果 {got} 不小于 200 或 {add} 大于 {mx}
              设 stop = 1
            否则
              设 outtext = {outtext}{nl}{ln}
              设 used = {add}
              设 got = 计算 {got} + 1
            结束
          结束
        结束
      结束
      如果 {stop} 等于 1
        设 tr = 1
        设 outtext = {outtext}{nl}（共 {row.rows} 行，只给了前 {got} 行；统计见上面，是按全部行算的）
      结束
    否则如果 {n} 不大于 {mx}
      设 outtext = {src}
    否则
      设 found = 0
      如果 {question} 不为空
        设 sep = (?:[\s，。、？！；：,.?!;:“”‘’（）()「」『』【】\[\]])+
        设 parts = 按正则切分 {question} {sep}
        设 seen = |
        设 kws = []
        设 kn = 0
        遍历 p 于 {parts}
          设 pl = 找全部 {p} (?s).
          设 plen = 列表长度 {pl}
          如果 {plen} 不小于 2 且 {plen} 不大于 20 且 {kn} 小于 8 且 {seen} 不包含 |{p}|
            设 kws = 列表加项 {kws} {p}
            设 seen = {seen}{p}|
            设 kn = 计算 {kn} + 1
          结束
        结束
        设 segs = 按正则切分 {src} \n\s*\n
        设 sl = 列表长度 {segs}
        如果 {sl} 小于 2
          设 segs = 按正则切分 {src} \r?\n
        结束
        设 used = 0
        设 stopk = 0
        设 hits = 0
        设 kbody = {zz 或}
        遍历 sg 于 {segs}
          设 s1 = 替换 {sg} ^\s+|\s+$
          如果 {s1} 不为空 且 {stopk} 等于 0
            设 hit = 0
            遍历 kw 于 {kws}
              如果 {sg} 包含 {kw}
                设 hit = 1
              结束
            结束
            如果 {hit} 等于 1
              设 pl2 = 找全部 {sg} (?s).
              设 plen2 = 列表长度 {pl2}
              设 add = 计算 {used} + {plen2}
              如果 {hits} 大于 0
                设 add = 计算 {add} + 2
              结束
              设 piece = {sg}
              设 okp = 1
              如果 {add} 大于 {mx}
                设 remain = 计算 {mx} - {used}
                如果 {hits} 大于 0
                  设 remain = 计算 {remain} - 2
                结束
                设 stopk = 1
                如果 {remain} 大于 0
                  设 piece = 截取 {sg} 1 {remain}
                  设 add = {mx}
                否则
                  设 okp = 0
                结束
              结束
              如果 {okp} 等于 1
                如果 {hits} 等于 0
                  设 kbody = {piece}
                否则
                  设 kbody = {kbody}{nl}{nl}{piece}
                结束
                设 used = {add}
                设 hits = 计算 {hits} + 1
              结束
            结束
          结束
        结束
        如果 {hits} 大于 0
          如果 {n} 大于 50000
            设 pf = （按问题里的关键词从前50000字里摘了{hits} 段，全文 {n} 字）
          否则
            设 pf = （按问题里的关键词摘了{hits} 段，全文 {n} 字）
          结束
          设 outtext = {pf}{nl}{kbody}
          设 mode = keyword
          设 tr = 1
          设 found = {hits}
        结束
      结束
      如果 {found} 等于 0
        设 mode = headtail
        设 tr = 1
        如果 {n} 大于 50000
          设 hl = 计算 {mx} - 60
          设 head = 截取 {src} 1 {hl}
          设 tailtxt = （只给了开头；全文{n} 字，系统只保存了前 50000 字，结尾没有保存）
          设 outtext = {head}{nl}{tailtxt}
        否则
          设 tl = 计算 取整({mx} / 4)
          如果 {tl} 大于 1500
            设 tl = 1500
          结束
          设 hl = 计算 {mx} - {tl} - 20
          设 head = 截取 {src} 1 {hl}
          设 sa = 找全部 {src} (?s).
          设 slen = 列表长度 {sa}
          设 ts = 计算 {slen} - {tl} + 1
          设 tail = 截取 {src} {ts}
          设 outtext = {head}{nl}（中间省略，全文 {n} 字）{nl}{tail}
        结束
      结束
    结束
    设 n3 = 写库 app.db assist_file_touch id={row.id} now={now}
    返回 {"file_id": {row.id}, "name": "{row.name}", "ext": "{row.ext}", "chars": {n}, "pages": {row.pages}, "rows": {row.rows}, "text": "{outtext}", "stats": "{row.stats}", "mode": "{mode}", "truncated": {tr}}
  结束
结束
