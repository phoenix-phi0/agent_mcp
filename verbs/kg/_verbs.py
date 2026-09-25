"""kg 包：知识图谱（有向无环图）。

    用包 kg db

    设 报告 = 导入图谱 app.db content/kg.json
    打印 {报告}

    设 前置 = 查询 app.db kg_ancestors code=noun
    遍历 行 于 {前置}
      打印 {行.name}（隔 {行.dist} 层）
    结束

导入只有这一个动词；查询走 db 包的「查询」，SQL 在项目的 queries/kg_*.sql。

为什么导入不直接用 .zs 写，见 tools/kg_dag.py 的文档：逐条报错要行号，
缺字段会原样留成 {项.xxx} 字面量写进库。
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

    @reg.verb("把知识图谱文件（JSON 数组或 JSONL）导入库。先节点后边；"
              "加边时会成环的拒掉，逐条报原因。重复导入不会多出行。"
              "例如 导入图谱 app.db content/kg.json")
    def 导入图谱(库: str, 文件: str) -> str:
        from tools.kg_dag import KgError, format_report, import_file

        try:
            report = import_file(safe(库), queries_dir(), safe(文件))
        except (KgError, ValueError) as e:
            return f"[出错] {e}"
        return format_report(report)

    @reg.verb("同「导入图谱」，但返回结构化的报告（JSON），给接口用。")
    def 导入图谱JSON(库: str, 文件: str) -> str:
        from tools.kg_dag import KgError, format_report, import_file

        try:
            report = import_file(safe(库), queries_dir(), safe(文件))
        except (KgError, ValueError) as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)
        report["text"] = format_report(report)
        return json.dumps(report, ensure_ascii=False)

    @reg.verb("批量导入单词（JSONL 或 JSON 数组）。按「汉字+假名」认同一个词，"
              "重复导入是更新不是新增；知识点不存在的不挂，词照样导。"
              "例如 导入单词 app.db content/words.jsonl")
    def 导入单词(库: str, 文件: str) -> str:
        from tools.word_import import WordError, format_report, import_words

        try:
            return format_report(import_words(safe(库), queries_dir(), safe(文件)))
        except (WordError, ValueError) as e:
            return f"[出错] {e}"

    @reg.verb("同「导入单词」，返回结构化报告（JSON），给接口用。")
    def 导入单词JSON(库: str, 文件: str) -> str:
        from tools.word_import import WordError, format_report, import_words

        try:
            r = import_words(safe(库), queries_dir(), safe(文件))
        except (WordError, ValueError) as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)
        r["text"] = format_report(r)
        return json.dumps(r, ensure_ascii=False)

    @reg.verb("算出整张图的节点和边，节点带好坐标，给「节点图」控件用。"
              "布局跟 py -m kg svg 画的静态图一致：按依赖深度分层、同层按"
              "主前置分簇、对照关系排到相邻、一行超过 8 个折行。"
              "例如 设 图 = 图数据 app.db")
    def 图数据(库: str) -> dict:
        """节点带 x / y，前端就不跑 dagre 了（见 templates/frontend/graph.j2）。

        dagre 是通用布局，不知道中文标签多宽，也不知道「同层按主前置分簇」
        「对照关系挨着放」这些跟语言有关的讲究——那些是 tools/kg_svg.py 里
        一点点调出来的。既然那套算法在，直接复用，两边看起来就一样。
        """
        from tools.kg_svg import BOX_H, BOX_W, layout, load

        nodes = load(safe(库))
        if not nodes:
            return {"nodes": [], "edges": []}
        pos, _, _, _ = layout(nodes)

        out_nodes, out_edges = [], []
        for n in nodes:
            x, y = pos[n["id"]]
            out_nodes.append({
                "id": n["id"], "label": n["label"],
                # 坐标转成左上角：SVG 里是中心点，而 Vue Flow 要左上角
                "x": round(x - BOX_W / 2), "y": round(y - BOX_H / 2),
            })
            for p in n["prereq"]:
                out_edges.append({"from": p, "to": n["id"]})
        return {"nodes": out_nodes, "edges": out_edges}

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
