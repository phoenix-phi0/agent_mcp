"""基础动词：跟任何领域都无关的那些。

加动词就是在这个文件里写个带 @reg.verb 的函数，重跑脚本即可生效。
参数按位置绑定，值里不能有空格——要传含空格的内容，先用「设」存进变量
再用 {变量} 传。
"""

import json
import re
from pathlib import Path


def register(reg, workspace):
    workspace = Path(workspace).resolve()

    def safe(path: str) -> Path:
        p = (workspace / path).resolve()
        if p != workspace and workspace not in p.parents:
            raise ValueError(f"路径越界：{path}")
        return p

    # ---------- 算术 ----------

    @reg.verb("两数相加。例如 相加 3 1 → 4")
    def 相加(甲: str, 乙: str) -> str:
        try:
            s = float(甲) + float(乙)
        except ValueError:
            return "[参数不是数字]"
        return str(int(s)) if s == int(s) else str(s)

    @reg.verb("两数相减。例如 相减 10 3 → 7")
    def 相减(甲: str, 乙: str) -> str:
        try:
            s = float(甲) - float(乙)
        except ValueError:
            return "[参数不是数字]"
        return str(int(s)) if s == int(s) else str(s)

    @reg.verb("计算百分比，返回整数。例如 算比例 8 10 → 80")
    def 算比例(分子: str, 分母: str) -> str:
        try:
            a, b = float(分子), float(分母)
        except ValueError:
            return "[参数不是数字]"
        return "0" if b == 0 else str(round(a / b * 100))

    # ---------- 文本 ----------

    @reg.verb("统计逗号分隔列表里有多少项。例如 列表长度 甲,乙,丙 → 3")
    def 列表长度(列表: str) -> str:
        return str(len([x for x in re.split(r"[,，]", 列表) if x.strip()]))

    @reg.verb("取列表里的第 N 项，从 1 开始。例如 取第 甲,乙,丙 2 → 乙")
    def 取第(列表: str, 序号: str) -> str:
        items = [x.strip() for x in re.split(r"[,，]", 列表) if x.strip()]
        try:
            i = int(序号)
        except ValueError:
            return "[序号要是数字]"
        return items[i - 1] if 1 <= i <= len(items) else ""

    @reg.verb("统计文本长度（字符数）。")
    def 字数(文本: str) -> str:
        return str(len(文本))

    @reg.verb("取文本的前 N 个字符。")
    def 截取(文本: str, 长度: str) -> str:
        try:
            n = int(长度)
        except ValueError:
            return 文本
        return 文本[:n]

    # ---------- JSON ----------

    @reg.verb("从 JSON 文本里取字段，路径用点号分隔。例如 取字段 {数据} a.b.0")
    def 取字段(内容: str, 路径: str) -> str:
        try:
            cur = json.loads(内容)
        except json.JSONDecodeError:
            return "[不是合法 JSON]"
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

    # ---------- 文件 ----------

    @reg.verb("统计文件的非空行数。")
    def 计数(文件: str) -> str:
        f = safe(文件)
        if not f.is_file():
            return "0"
        return str(sum(1 for ln in f.read_text(encoding="utf-8").splitlines()
                       if ln.strip()))

    @reg.verb("列出工作目录下的文件名，逗号分隔。")
    def 列文件(子目录: str = ".") -> str:
        d = safe(子目录)
        if not d.is_dir():
            return ""
        return ",".join(sorted(p.name for p in d.iterdir() if p.is_file()))

    # ---------- 调试 ----------

    @reg.verb("原样返回参数，用来确认插值结果。")
    def 回显(内容: str) -> str:
        return 内容

    @reg.verb("返回当前工作目录，排查路径问题用。")
    def 工作目录() -> str:
        return str(workspace)
