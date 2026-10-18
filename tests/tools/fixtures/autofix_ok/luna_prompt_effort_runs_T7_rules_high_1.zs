用包 common text code
预算 调用 2 秒 300
# 旧写法: len\(lines\)\s*-\s*n\s*\+\s*1\s*\+\s*i
设 res = 改文件 {e1}
如果 {res.ok} 不等于 是
  设 inp.src = verbs/probe/defs/末尾行.py:9-19
  设 inp.msg = {res.msg}
  设 task = 修正末尾行：按文件真实行号输出末尾行；行数参数去除前后空白，空串用缺省 10，非正数按 1；非整数返回 [行数要是整数] <原参数> 且不抛异常；空文件返回空串；保留路径越界及文件不存在时的返回值
  设 logic = 根据入参原文修改末尾行。改法套用失败信息：{inp.msg}。保留现有路径校验和文件不存在返回值；行数先 strip，空串用 10，再解析整数；解析失败返回 f"[行数要是整数] {原参数}"；非正数按 1；空文件返回空串；输出真实行号，从 max(1, len(lines)-n+1) 开始。edits 每项字段名固定为 file（相对路径）、old、new；old 一字不差抄入参原文且不带行号前缀
  设 fmt = edits:列表,说明:文本
  设 r = 派任务 {task} {inp} {logic} {fmt}
  如果 {r.状态} 不等于 成功
    终止 失败 派任务未能修正末尾行：{r.原因}
  结束
  设 res = 改文件 {r.结果}
  如果 {res.ok} 不等于 是
    终止 失败 修正末尾行未能套用：{res.msg}
  结束
结束
终止 成功 末尾行已修正，保留路径越界和文件不存在时的返回值

#改法 e1
@@ 改 verbs/probe/defs/末尾行.py
<<<<<<< 原文
    lines = p.read_text(encoding="utf-8").splitlines()
    n = max(1, int(行数))
    return "\n".join(f"{len(lines) - n + 1 + i}| {ln}"
                     for i, ln in enumerate(lines[-n:]))
=======
    lines = p.read_text(encoding="utf-8").splitlines()
    raw_n = 行数.strip()
    if not raw_n:
        raw_n = "10"
    try:
        n = max(1, int(raw_n))
    except ValueError:
        return f"[行数要是整数] {行数}"
    if not lines:
        return ""
    start = max(1, len(lines) - n + 1)
    return "\n".join(f"{start + i}| {ln}"
                     for i, ln in enumerate(lines[-n:]))
>>>>>>> 新文

#清单
改 verbs/probe/defs/末尾行.py:末尾行