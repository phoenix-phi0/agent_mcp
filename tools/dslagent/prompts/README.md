# prompts/（只剩旧路径）

v2 各 agent 的提示词已搬到 `../agents/`（一个 agent 一个 .md，见 `../agents/README.md`）。这里只剩旧路径（`legacy/`）用的文本，不要动：

- `legacy/system.tpl.txt`（占位 `{CHEAT}` `{VERBS}` `{TIPS}` `{SKELETON}`，前三个来自 `agents/shared/` 的 cheat.md / verbs.md / tips.md）、`legacy/skeleton.md`
- `legacy/first_prompt.tpl.txt` `legacy/replan_prompt.tpl.txt` `legacy/task_first_prompt.tpl.txt` `legacy/task_replan_prompt.tpl.txt` `legacy/replan_err.tpl.txt` `legacy/template_note.txt`
- `legacy/lib_system.tpl.txt`（定位.zs / 读改测.zs 共用 system）

加载：`promptfile.text(rel)` 逐字读（文件末尾有没有换行就是提示词末尾有没有换行），`promptfile.tpl(rel, **kw)` 按 `str.format` 填占位（字面花括号写 `{{` `}}`）。
