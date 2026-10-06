"""quiz 包：题库操作动词。

题库是一个目录，每课一个 jsonl 文件：

    content/n2n3/题库/
        doushi_01.jsonl
        doushi_02.jsonl

每行一题：

    {"id":"doushi_01-01-意味","课程":"doushi_01","考点":"词义","难度":"基础",
     "题型":"选择","题干":"...","答案":"C","解析":"..."}

设计要点：

  · 挑题只返回题干和题号，答案留在题库里，用取答案单独取。
    这样出题时不可能泄露答案。
  · 判题不调模型——选择题比对选项字母，填空题比对汉字，都是确定性的。
    模型只在需要解释语感这类开放场景才出场。判对规则写在 defs/判作答.zs
    里（DSL，配 text 包的字符串动词），这里的判题动词都调它。
  · 题库参数既可以传目录（读目录下所有 jsonl），也可以传单个文件。
    按课程筛选用文件名精确匹配，「doushi_01」不会命中「doushi_02」。

## 这个包的动词放在哪

读题库文件的八个动词（挑题、判题、取答案……）写在下面的 register() 里，共用
闭包里的 load / sift / safe——拆成单文件的话每个文件都要复制一遍。

**判对规则不在这里**，在 defs/ 的 .zs 里，改规则不碰 Python：

    defs/判作答.zs   判一道题，返回 {correct, mine}：选择题抓选项字母、接续题
                     整段比对、填空题允许多写送假名。判题 / 批量判题 / 错题号
                     从这里调它（_judge），判对错.zs 也调它——规则只写一份
    defs/判对错.zs   判一道题，题目由调用方给（知识图谱那边题目在库里），回 1 / 0
    defs/拆选项.zs   把选择题题干拆成题面和选项按钮，按种子稳定打乱

defs/ 扫在最前面，下面的内置动词同名时会覆盖 defs/ 里的。往 defs/ 放 .py 或
.zs 就能加动词，不用碰这个文件。

defs/ 里的动词拿不到这里的闭包函数。需要读题库的话自己写，或者从
上一级 import（那要先把包目录加进 sys.path，因为动词模块是按文件路径
导入的，不走 sys.path）。
"""

import json
import random
from pathlib import Path

from tools.verbs import scan_verbs

# 加载时注入
WORKSPACE = Path(".")
PACK_DIR = Path(".")


def register(reg, workspace):
    workspace = Path(workspace).resolve()

    # 先扫 defs/，下面的内置动词同名时会覆盖它
    scan_verbs(reg, PACK_DIR / "defs", workspace, pack_dir=PACK_DIR)

    def safe(path: str) -> Path:
        """路径限制在工作目录内。

        动词是被脚本调用的，脚本内容可能来自模型，不做这层检查就等于把
        整个磁盘暴露给生成出来的路径。
        """
        p = (workspace / path).resolve()
        if p != workspace and workspace not in p.parents:
            raise ValueError(f"路径越界：{path}")
        return p

    def _files(题库: str) -> list[Path]:
        p = safe(题库)
        if p.is_dir():
            return sorted(p.glob("*.jsonl"))
        return [p] if p.is_file() else []

    def load(题库: str, 课程: str = ""):
        """读题库。课程非空时只读对应的文件，省得全部读进来。

        读不到返回 None——调用方据此区分「题库不存在」和「没有匹配的题」，
        两种情况给学习者的提示完全不同。
        """
        files = _files(题库)
        if not files:
            return None
        if 课程:
            matched = [f for f in files if f.stem == 课程]
            files = matched or files

        items = []
        for f in files:
            for line in f.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return items

    def sift(items, 课程="", 考点="", 难度=""):
        """按字段筛。课程用精确匹配——用 in 的话 doushi_0 会命中四个课程。"""
        if 课程:
            items = [q for q in items if str(q.get("课程", "")) == 课程]
        if 考点:
            items = [q for q in items if 考点 in str(q.get("考点", ""))]
        if 难度:
            items = [q for q in items if 难度 in str(q.get("难度", ""))]
        return items

    def _course_of(题号: str) -> str:
        """题号形如 doushi_01-05-意味，第一段就是课程名。"""
        return 题号.split("-")[0] if "-" in 题号 else ""

    def _ids(题号: str) -> list[str]:
        return [x.strip() for x in 题号.replace("，", ",").split(",") if x.strip()]

    def _find(题库: str, 题号: str):
        items = load(题库, _course_of(题号))
        if items is None:
            return None
        return next((q for q in items if q.get("id") == 题号), None)

    def _pick(题库: str, 数量: str, 课程: str, 考点: str, 难度: str = ""):
        """挑题和挑题号共用的抽样。返回 (题目列表, 错误信息)。"""
        items = load(题库, 课程)
        if items is None:
            return None, f"[题库不存在] {题库}"
        items = sift(items, 课程, 考点, 难度)
        if not items:
            return None, (f"[没有匹配的题目] 课程={课程 or '不限'} "
                          f"考点={考点 or '不限'}")
        try:
            n = min(int(数量 or 3), len(items))
        except ValueError:
            n = min(3, len(items))
        return random.sample(items, n), ""

    # ------------------------------------------------------------------
    # 判题：不调模型
    # ------------------------------------------------------------------

    def judge(题: dict) -> dict:
        """调 defs/判作答.zs：{correct, mine}。规则在那边，这里不重写一遍。"""
        from tools.dsl import invoke_verb
        return invoke_verb(reg, "判作答", 题, workdir=workspace,
                           verbs_root=PACK_DIR.parent)

    def _judge(题库: str, 题号: str, 作答: str) -> str:
        q = _find(题库, 题号)
        if q is None:
            return f"[没找到题目] {题号}"

        标准 = str(q.get("答案", ""))
        解析 = str(q.get("解析", ""))
        if not 标准:
            return f"[题目没有答案] {题号}"

        r = judge({"题型": str(q.get("题型", "")), "答案": 标准,
                   "可接受": q.get("可接受"), "作答": 作答})
        提取 = str(r.get("mine") or "")
        if str(q.get("题型", "")) == "选择":
            你的 = f"你选了 {提取}" if 提取 else "没看出你选的是哪个选项"
        else:
            你的 = f"你写的是「{提取}」" if 提取 else "没看出你的作答"

        if r.get("correct") == "1":
            return f"○ 答对了\n{解析}"
        return f"✗ 再看看\n{你的}，正确答案是 {标准}。\n{解析}"

    # ------------------------------------------------------------------

    @reg.verb(
        "对照题库判断作答是否正确，返回判定符号、正误说明和解析。"
        "不调用模型，选择题比对选项字母，填空题比对汉字（允许多写送假名）。"
    )
    def 判题(题库: str, 题号: str, 作答: str) -> str:
        return _judge(题库, 题号, 作答)

    @reg.verb(
        "批量判题。题号和作答一一对应，都用逗号分隔。"
        "返回每题的判定，末尾附正确率。不调用模型。"
    )
    def 批量判题(题库: str, 题号: str, 作答: str) -> str:
        ids = _ids(题号)
        if not ids:
            return "[没有给题号]"
        # 作答不过滤空项：学生可能跳过某题，位置必须对齐。
        # 过滤掉空的会让后面的答案整体前移，全判错。
        answers = [x.strip() for x in 作答.replace("，", ",").split(",")]
        answers += [""] * (len(ids) - len(answers))

        lines, 对数 = [], 0
        for i, (wid, ans) in enumerate(zip(ids, answers), 1):
            结果 = _judge(题库, wid, ans)
            if 结果.startswith("○"):
                对数 += 1
            lines.append(f"第{i}题　[{wid}]\n{结果}")

        比例 = round(对数 / len(ids) * 100)
        lines.append(f"\n正确 {对数}/{len(ids)}（{比例}%）")
        return "\n\n".join(lines)

    @reg.verb("判断作答后返回答错的题号，逗号分隔；全对则返回空。用于记录错题。")
    def 错题号(题库: str, 题号: str, 作答: str) -> str:
        ids = _ids(题号)
        answers = [x.strip() for x in 作答.replace("，", ",").split(",")]
        answers += [""] * (len(ids) - len(answers))
        return ",".join(wid for wid, ans in zip(ids, answers)
                        if not _judge(题库, wid, ans).startswith("○"))

    # ------------------------------------------------------------------
    # 取题与查询
    # ------------------------------------------------------------------

    @reg.verb("从题库随机挑题，可按课程和考点筛选。只返回题干和题号，不含答案。")
    def 挑题(题库: str, 数量: str = "3", 课程: str = "", 考点: str = "") -> str:
        picked, err = _pick(题库, 数量, 课程, 考点)
        if err:
            return err
        # 题号一起返回：批改时要靠它去取标准答案
        return "\n\n".join(
            f"第{i}题　[{q.get('id', '')}]\n{q.get('题干', '')}"
            for i, q in enumerate(picked, 1))

    @reg.verb("挑题并只返回题号，逗号分隔。配合「取题」和「判题」使用。")
    def 挑题号(题库: str, 数量: str = "3", 课程: str = "", 考点: str = "") -> str:
        picked, err = _pick(题库, 数量, 课程, 考点)
        # 出错返回空串而不是错误信息：这个动词的结果通常直接拿去遍历或
        # 判空，掺进一句中文错误会被当成题号用
        return "" if err else ",".join(q.get("id", "") for q in picked)

    @reg.verb("按题号取出题干，用于重出错题。多个题号用逗号分隔。")
    def 取题(题库: str, 题号: str) -> str:
        wanted = _ids(题号)
        if not wanted:
            return "[没有给题号]"
        items = load(题库, _course_of(wanted[0]))
        if items is None:
            return f"[题库不存在] {题库}"
        found = {q.get("id"): q for q in items}
        blocks = []
        for i, wid in enumerate(wanted, 1):
            q = found.get(wid)
            blocks.append(f"第{i}题　[{wid}]\n{q.get('题干', '')}" if q
                          else f"第{i}题　[{wid}] [没找到]")
        return "\n\n".join(blocks)

    @reg.verb("按题号取标准答案和解析。多个题号用逗号分隔。只在批改环节调用。")
    def 取答案(题库: str, 题号: str) -> str:
        wanted = _ids(题号)
        if not wanted:
            return "[没有给题号]"
        items = load(题库, _course_of(wanted[0]))
        if items is None:
            return f"[题库不存在] {题库}"
        found = {q.get("id"): q for q in items}
        return "\n".join(
            f"{wid}｜答案：{found[wid].get('答案', '')}｜{found[wid].get('解析', '')}"
            if wid in found else f"{wid}｜[没找到]"
            for wid in wanted)

    @reg.verb("列出题库里有哪些课程，附各自题目数。")
    def 列课程(题库: str) -> str:
        files = _files(题库)
        if not files:
            return f"[题库不存在] {题库}"
        # 数行数而不是解析 JSON：只要个数目，解析几百行是白费
        rows = []
        for f in files:
            n = sum(1 for ln in f.read_text(encoding="utf-8").splitlines()
                    if ln.strip())
            rows.append(f"{f.stem}（{n}题）")
        return "，".join(rows)

    @reg.verb("列出题库里有哪些考点，附各自题目数。可按课程筛选。")
    def 列考点(题库: str, 课程: str = "") -> str:
        items = load(题库, 课程)
        if items is None:
            return f"[题库不存在] {题库}"
        counts: dict[str, int] = {}
        for q in sift(items, 课程):
            k = str(q.get("考点", "")).strip() or "(未标注)"
            counts[k] = counts.get(k, 0) + 1
        return "，".join(f"{k}（{v}题）" for k, v in sorted(counts.items())) or "(无)"

    @reg.verb("统计题库里有多少道题，可按课程和考点筛选。")
    def 题目数(题库: str, 课程: str = "", 考点: str = "") -> str:
        items = load(题库, 课程)
        if items is None:
            return "0"
        return str(len(sift(items, 课程, 考点)))
