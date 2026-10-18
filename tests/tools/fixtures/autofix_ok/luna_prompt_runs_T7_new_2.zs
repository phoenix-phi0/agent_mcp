用包 common text code
预算 调用 4 秒 300

设 res = 改文件 {e1}
如果 {res.ok} 等于 是
  终止 成功 已修正末尾行的行号和行数参数处理：{res.msg}
结束

设 inp.src = verbs/probe/defs/末尾行.py:9-19
设 inp.reason = {res.msg}
设 desc = 修正末尾行：输出真实行号；输入行数忽略首尾空白，空串用缺省值 10，非整数返回指定错误，保留路径越界和文件不存在的返回值
设 logic = edits 每项字段名固定为 file、old、new；old 从入参原文一字不差抄写且不带行号前缀；仅修改末尾行函数；读取并去除行数参数首尾空白，空串用 10，整数解析失败返回 [行数要是整数] 加原参数，非正数按 1 处理；按文件真实行号标记所选末尾行，文件不足时输出全部行，空文件返回空串；保留现有路径越界和文件不存在返回值；不改测试文件；当前静态改法未能套用的原因：{inp.reason}
设 r = 派任务 {desc} {inp} {logic} edits:列表,note:文本
如果 {r.状态} 不等于 成功
  终止 失败 无法生成替代改法：{r.原因}
结束
设 res = 改文件 {r.结果}
如果 {res.ok} 不等于 是
  终止 失败 替代改法未能套用：{res.msg}
结束
终止 成功 已修正末尾行的行号和行数参数处理：{r.结果.note}

#改法 e1
@@ 改 verbs/probe/defs/末尾行.py
<<<<<<< 原文
    lines = p.read_text(encoding="utf-8").splitlines()
    n = max(1, int(行数))
    return "\n".join(f"{len(lines) - n + 1 + i}| {ln}"
                     for i, ln in enumerate(lines[-n:]))
=======
    lines = p.read_text(encoding="utf-8").splitlines()
    原参数 = 行数
    参数 = 行数.strip()
    if not 参数:
        参数 = "10"
    try:
        n = int(参数)
    except ValueError:
        return f"[行数要是整数] {原参数}"
    n = max(1, n)
    起始 = max(0, len(lines) - n)
    return "\n".join(f"{起始 + i + 1}| {ln}"
                     for i, ln in enumerate(lines[起始:]))
>>>>>>> 新文

#清单
改 verbs/probe/defs/末尾行.py:末尾行