"""Python 动词：DSL 表达不了的原子能力。

这里放的是查询、算术、外部接口这类操作——用 DSL 写会很别扭，
用 Python 写一行就完事。注册进 VerbRegistry 后，脚本里像内置语句一样调用：

    设 题目 = 挑题 {题库} 3 促音变
    设 正确率 = 算比例 {对} {总}

参数按位置绑定，顺序即函数签名顺序。返回值转成字符串。
"""

import json
import random
from pathlib import Path

from tools import VerbRegistry


def register_python_verbs(reg: VerbRegistry, workspace: Path) -> VerbRegistry:
    """把内置的 Python 动词注册进动词表。"""
    workspace = Path(workspace).resolve()

    def safe(path: str) -> Path:
        p = (workspace / path).resolve()
        if p != workspace and workspace not in p.parents:
            raise ValueError(f"路径越界：{path}")
        return p

    # ------------------------------------------------------------------

    @reg.verb("从 jsonl 题库里挑题，可按考点筛选。返回格式化的题目文本。")
    def 挑题(题库: str, 数量: str = "3", 考点: str = "") -> str:
        f = safe(题库)
        if not f.is_file():
            return f"[题库不存在] {题库}"

        items = []
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                q = json.loads(line)
            except json.JSONDecodeError:
                continue
            if 考点 and 考点 not in str(q.get("考点", "")):
                continue
            items.append(q)

        if not items:
            return f"[没有匹配的题目] 考点={考点 or '不限'}"

        n = min(int(数量 or 3), len(items))
        picked = random.sample(items, n)
        lines = []
        for i, q in enumerate(picked, 1):
            lines.append(f"{i}. [{q.get('id', '')}] {q.get('题干', '')}")
        return "\n".join(lines)

    @reg.verb("取出题目的标准答案，用于批改。多个 id 用逗号分隔。")
    def 取答案(题库: str, 编号: str) -> str:
        f = safe(题库)
        if not f.is_file():
            return f"[题库不存在] {题库}"
        wanted = {x.strip() for x in 编号.replace("，", ",").split(",") if x.strip()}
        out = []
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                q = json.loads(line)
            except json.JSONDecodeError:
                continue
            if q.get("id") in wanted:
                out.append(f"{q['id']}：{q.get('答案', '')}")
        return "\n".join(out) or f"[没找到] {编号}"

    @reg.verb("计算百分比，返回整数。例如 算比例 8 10 → 80")
    def 算比例(分子: str, 分母: str) -> str:
        try:
            a, b = float(分子), float(分母)
        except ValueError:
            return "[参数不是数字]"
        if b == 0:
            return "0"
        return str(round(a / b * 100))

    @reg.verb("统计 jsonl 文件的行数，用于查看已收集多少条数据。")
    def 计数(文件: str) -> str:
        f = safe(文件)
        if not f.is_file():
            return "0"
        return str(sum(1 for ln in f.read_text(encoding="utf-8").splitlines() if ln.strip()))

    @reg.verb("从 JSON 文本里取一个字段，路径用点号分隔。例如 取字段 {进度} hiragana.current_day")
    def 取字段(内容: str, 路径: str) -> str:
        try:
            data = json.loads(内容)
        except json.JSONDecodeError:
            return "[不是合法 JSON]"
        cur = data
        for key in 路径.split("."):
            key = key.strip()
            if isinstance(cur, dict) and key in cur:
                cur = cur[key]
            elif isinstance(cur, list) and key.isdigit() and int(key) < len(cur):
                cur = cur[int(key)]
            else:
                return f"[没有字段] {路径}"
        if isinstance(cur, (dict, list)):
            return json.dumps(cur, ensure_ascii=False)
        return "" if cur is None else str(cur)

    return reg
