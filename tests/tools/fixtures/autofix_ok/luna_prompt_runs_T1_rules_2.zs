用包 common text code
预算 调用 5 秒 360
# 旧写法: if\s+p\s*!=\s*(?:workspace|root)\s+and\s+(?:workspace|root)\s+not\s+in\s+p\.parents
设 res = 写文件 {e1}
如果 {res.ok} 不等于 是
  终止 失败 公共路径模块没建成：{res.msg}
结束
设 logic = 要求：把入参中所有手写的工作目录路径边界判断改为调用 tools.safepath.resolve_in(root, path)，由它保留原样路径并抛出 ValueError("路径越界：<path>")；原来返回「[路径越界] …」的动词要捕获该 ValueError 并保持原文本。HTTP 上传必须在创建目录前验证最终目标相对于 workspace 的边界，越界时返回原来的「[路径越界] {目录}/{name}」。保留其余行为。每项字段名固定为 file（相对路径）、old、new；old 从入参原文一字不差抄、不带行号前缀
设 job.任务 = 任务：将 auth 和 data 的工作目录路径检查统一到 tools.safepath.resolve_in
设 job.入参 = 解析JSON {}
设 job.入参.auth = verbs/auth/_verbs.py:54-72
设 job.入参.data = verbs/data/_verbs.py:34-46
设 job.逻辑 = {logic}
设 job.格式 = edits:列表,说明:文本
设 jobs = 解析JSON []
设 jobs = 列表加项 {jobs} {job}
设 job.任务 = 任务：将 db 和 doc 的工作目录路径检查统一到 tools.safepath.resolve_in
设 job.入参 = 解析JSON {}
设 job.入参.db = verbs/db/_verbs.py:143-166
设 job.入参.doc = verbs/doc/_verbs.py:178-187
设 job.逻辑 = {logic}
设 job.格式 = edits:列表,说明:文本
设 jobs = 列表加项 {jobs} {job}
设 job.任务 = 任务：将 http 上传和 kg 的工作目录路径检查统一到 tools.safepath.resolve_in
设 job.入参 = 解析JSON {}
设 job.入参.http = verbs/http/_verbs.py:180-252
设 job.入参.kg = verbs/kg/_verbs.py:29-38
设 job.逻辑 = {logic}
设 job.格式 = edits:列表,说明:文本
设 jobs = 列表加项 {jobs} {job}
设 job.任务 = 任务：将 quiz 和 common 计数动词的工作目录路径检查统一到 tools.safepath.resolve_in
设 job.入参 = 解析JSON {}
设 job.入参.quiz = verbs/quiz/_verbs.py:56-72
设 job.入参.counter = verbs/common/defs/计数.py:10-20
设 job.逻辑 = {logic}
设 job.格式 = edits:列表,说明:文本
设 jobs = 列表加项 {jobs} {job}
设 job.任务 = 任务：将 probe 两个动词的工作目录路径检查统一到 tools.safepath.resolve_in
设 job.入参 = 解析JSON {}
设 job.入参.total = verbs/probe/defs/总行数.py:9-16
设 job.入参.tail = verbs/probe/defs/末尾行.py:9-19
设 job.逻辑 = {logic}
设 job.格式 = edits:列表,说明:文本
设 jobs = 列表加项 {jobs} {job}
设 rs = 并行派任务 {jobs} 5
遍历 r 于 {rs}
  如果 {r.状态} 不等于 成功
    终止 失败 路径检查迁移子任务失败：{r.原因}
  结束
  设 res = 改文件 {r.结果}
  如果 {res.ok} 不等于 是
    终止 失败 路径检查迁移未能应用：{res.msg}
  结束
结束
终止 成功 已添加公共安全路径模块，并将动词的工作目录边界检查统一迁移。

#改法 e1
@@ 新建 tools/safepath.py
<<<<<<< 内容
"""工作目录路径边界检查。"""

from pathlib import Path


def is_inside(root: str | Path, p: str | Path) -> bool:
    """解析符号链接后，判断 p 是否为 root 本身或位于 root 之下。"""
    resolved_root = Path(root).resolve()
    resolved_path = Path(p)
    if not resolved_path.is_absolute():
        resolved_path = resolved_root / resolved_path
    resolved_path = resolved_path.resolve()
    return resolved_path == resolved_root or resolved_root in resolved_path.parents


def resolve_in(root: str | Path, path: str | Path) -> Path:
    """解析 path 并确保其位于 root 内，越界时保留输入原文报错。"""
    resolved_root = Path(root).resolve()
    original = str(path)
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = resolved_root / candidate
    candidate = candidate.resolve()
    if not is_inside(resolved_root, candidate):
        raise ValueError(f"路径越界：{original}")
    return candidate
>>>>>>> 新文

#清单
新建 tools/safepath.py
改 verbs/auth/_verbs.py:register
改 verbs/data/_verbs.py:register
改 verbs/db/_verbs.py:register
改 verbs/doc/_verbs.py:register
改 verbs/http/_verbs.py:register
改 verbs/kg/_verbs.py:register
改 verbs/quiz/_verbs.py:register
改 verbs/common/defs/计数.py:计数
改 verbs/probe/defs/总行数.py:行数
改 verbs/probe/defs/末尾行.py:末尾行
#范围
verbs/
tools/