"""kg 包：知识图谱的导出。

    用包 kg db

    设 结果 = 导出图谱 app.db content/export.jsonl
    打印 {结果}

**导入不在这儿**——在 kg/routes/kg_import2.zs 和 word_import.zs，用 DSL 写的。

早先导入是 Python 动词，理由是引擎缺两样：遍历拿不到下标（逐条报错说不出
第几条）、可选字段缺了会留成 {项.after} 字面量写进库。两样都补上之后
（「序号 i」和「{名 或}」），导入就是「读 JSONL + 遍历 + 写库」，DSL 能
表达，那几个动词也就删了——同一件事两条路，迟早行为不一致。

导出还留着：它要按学习顺序排（递归查最长路径）、先写临时文件再改名，
这些跟「一条条处理」不是一类事，放 SQL 和 Python 里更合适。

查询走 db 包的「查询」，SQL 在项目的 queries/kg_*.sql。
"""

import json
from pathlib import Path

# 加载时注入
WORKSPACE = Path(".")
PACK_DIR = Path(".")


def register(reg, workspace):
    workspace = Path(workspace).resolve()
    project_root = PACK_DIR.parent.parent

    def safe(path: str) -> Path:
        """限制在工作目录内。路径来自脚本，而脚本可能是模型写的。"""
        p = (workspace / path).resolve()
        if p != workspace and workspace not in p.parents:
            raise ValueError(f"路径越界：{path}")
        return p

    def queries_dir() -> Path:
        # 跟 db 包同一个规则：workspace 下有 queries/ 就用它，没有退回项目根
        local = workspace / "queries"
        return local if local.is_dir() else (project_root / "queries").resolve()

    @reg.verb("把库里的知识图谱导出成文件，格式跟导入的一样，能直接再导入。"
              "按学习顺序排；「解锁」按前置倒推补回来。格式不给就看扩展名"
              "（.jsonl 走 JSONL）。例如 导出图谱 app.db content/export.json")
    def 导出图谱(库: str, 文件: str, 格式: str = "") -> str:
        from tools.kg_dag import KgError, export_file, format_export

        try:
            return format_export(export_file(safe(库), queries_dir(),
                                             safe(文件), 格式))
        except (KgError, ValueError, OSError) as e:
            return f"[出错] {e}"

    @reg.verb("同「导出图谱」，返回结构化结果（JSON），给接口用。")
    def 导出图谱JSON(库: str, 文件: str, 格式: str = "") -> str:
        from tools.kg_dag import KgError, export_file, format_export

        try:
            r = export_file(safe(库), queries_dir(), safe(文件), 格式)
        except (KgError, ValueError, OSError) as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)
        r["text"] = format_export(r)
        return json.dumps(r, ensure_ascii=False)
