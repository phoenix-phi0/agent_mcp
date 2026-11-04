# Python 术语和代码输出默写

`questions.json` 为 UTF-8 单一双语题库；每题有稳定 id、point_code、type、prompt_zh/ja、answer、accepted、explain_zh/ja 和 difficulty。输出题的 code 为独立、无需输入的程序；answer 保留标准输出末尾换行。等级编码入门/基础/进阶，日文显示入門/基礎/応用。每个知识点各 2 题术语、2 题输出，总计 136 题；难度分布为入门 52 题、基础 48 题、进阶 36 题。

术语判题：先去除首尾 Unicode 空白，然后大小写敏感地与 accepted 中每一项比较；括号或限定名仅在该题 accepted 显式列出时接受，不做通用括号或大小写归一化。运算符和关键字照字面匹配。输出判题：将 CRLF 和 CR 转成 LF；逐行删除行末空格和制表符，然后删除末尾所有 LF；其余字符（含大小写、行内空格、引号及前导空白）原样比较。输出题本库不含空输出；服务端不能用术语的全局 trim 判断输出。显示答案时应保留原始文本。

离线校验：`/workspace/agent_mcp/.venv/bin/python content/python_v1/dictation/check_dictation.py`。每段代码都用 `python3 -I` 在独立进程中执行，空标准输入，比较实际 stdout UTF-8 字节与原始 answer；退出非零、stderr 非空或超时均失败。脚本检查题号、覆盖率、双语字段、解析长度和题面重复、可接受答案及代码一致性；语言译义仍需人工审校。题目代码只限仓库审查过的可信内容，不要用该校验器执行不可信代码。
