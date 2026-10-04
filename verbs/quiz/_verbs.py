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
    模型只在需要解释语感这类开放场景才出场。
  · 题库参数既可以传目录（读目录下所有 jsonl），也可以传单个文件。
    按课程筛选用文件名精确匹配，「doushi_01」不会命中「doushi_02」。

## 这个包的动词放在哪

十个内置动词写在下面的 register() 里，共用闭包里的 load / sift / safe /
_judge——拆成单文件的话每个文件都要复制一遍，改一处判题规则要改十处。

但 defs/ 目录照样会被扫。往那儿放 .py 或 .zs 就能加动词，不用碰这个文件：

    verbs/quiz/defs/难题.py       只挑难度为进阶的题
    verbs/quiz/defs/错题复盘.zs   把错题串成一段讲解

扫在最前面，所以同名时下面的内置动词会覆盖 defs/ 里的。想覆盖内置行为
就得改这个文件——这是有意的，判题规则不该被一个随手放进去的文件悄悄换掉。

defs/ 里的动词拿不到这里的闭包函数。需要读题库的话自己写，或者从
上一级 import（那要先把包目录加进 sys.path，因为动词模块是按文件路径
导入的，不走 sys.path）。
"""

import json
import random
import re
import unicodedata
from pathlib import Path

from tools.verbs import scan_verbs

# 学生作答里可能出现的修饰：选C、答案是 C、C. 、（C）
_CHOICE_RE = re.compile(r"[A-Da-dａ-ｄＡ-Ｄ]")
# 送假名：判填空题时允许学生多写词尾
_KANA_TAIL = re.compile(r"[\u3040-\u309f]+$")

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

    def _norm(s: str) -> str:
        """归一化：全角转半角、去空白。"""
        return "".join(unicodedata.normalize("NFKC", s or "").split())

    def _judge_choice(答案: str, 作答: str) -> tuple[bool, str]:
        """选择题：从作答里抓第一个选项字母。

        学生可能写「C」「c」「选C」「C.」「答案是C」，都认。
        """
        m = _CHOICE_RE.search(_norm(作答))
        if not m:
            return False, ""
        picked = unicodedata.normalize("NFKC", m.group()).upper()
        return picked == _norm(答案).upper(), picked

    def _judge_fill(答案: str, 作答: str) -> tuple[bool, str]:
        """填空题：比对汉字，允许学生多写送假名。

        答案「憎」，学生写「憎」「憎む」「憎い」都算对；写「恨」才算错。
        不允许的话，按自然语感写完整词形会被判错——那是题目的问题，
        不是学生的。
        """
        a, b = _norm(答案), _norm(作答)
        if a == b:
            return True, b
        if _KANA_TAIL.sub("", b) == a:
            return True, b
        stem = _KANA_TAIL.sub("", a)
        if stem and stem == _KANA_TAIL.sub("", b):
            return True, b
        return False, b

    def _judge_exact(标准: str, 可接受, 作答: str) -> tuple[bool, str]:
        """接续题：整段精确比对（归一化全半角和空白，句号不计）。

        不能走填空题那套「去掉词尾假名再比」：接续题考的恰恰是词尾——
        答案「書かせられる」，学生写「書かれる」，两个去掉假名都是「書」，
        会被判对。所以只认标准答案和题目里列出的「可接受」写法。
        """
        b = _norm(作答).rstrip("。")
        if not b:
            return False, b
        ok = [标准] + [str(x) for x in (可接受 or [])]
        return any(_norm(a).rstrip("。") == b for a in ok), b

    def _judge(题库: str, 题号: str, 作答: str) -> str:
        q = _find(题库, 题号)
        if q is None:
            return f"[没找到题目] {题号}"

        标准 = str(q.get("答案", ""))
        解析 = str(q.get("解析", ""))

        if str(q.get("题型", "")) == "选择":
            对, 提取 = _judge_choice(标准, 作答)
            你的 = f"你选了 {提取}" if 提取 else "没看出你选的是哪个选项"
        elif str(q.get("题型", "")) == "接续":
            对, 提取 = _judge_exact(标准, q.get("可接受"), 作答)
            你的 = f"你写的是「{提取}」" if 提取 else "没看出你的作答"
        else:
            对, 提取 = _judge_fill(标准, 作答)
            你的 = f"你写的是「{提取}」" if 提取 else "没看出你的作答"

        if 对:
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

    @reg.verb(
        "判一道题，题目由调用方给，不读题库文件——题目已经导进数据库时用。"
        "参数是一个结构：{题型, 答案, 可接受, 作答}。对返回 1，错返回 0。"
        "规则跟「判题」是同一套（选择题抓选项字母，接续题整段比对）。"
    )
    def 判对错(题) -> str:
        """跟 _judge 同一套规则，只是题目从参数来。

        为什么不让调用方先把题写回文件再调「判题」：知识图谱那边题目在
        库里，库在项目目录，题库文件在 workspace——两边的路径限制互不
        相通。规则只写一份，在这里共用，改判题规则不会两边对不上。

        参数坏了直接抛，不返回 0：调用方拿 0 当「答错」记进学习记录，
        一个格式问题会变成一条假的错题。
        """
        if isinstance(题, str):
            try:
                题 = json.loads(题)
            except json.JSONDecodeError:
                raise ValueError(f"判对错的参数不是合法 JSON：{题[:80]}")
        if not isinstance(题, dict):
            raise ValueError("判对错的参数要是一个结构：{题型, 答案, 可接受, 作答}")
        型 = str(题.get("题型", ""))
        标准 = str(题.get("答案", ""))
        作答 = str(题.get("作答", "") or "")
        if not 标准:
            raise ValueError("判对错：没有标准答案")
        # 可接受在库里存的是 JSON 文本，也可能直接是列表
        可接受 = 题.get("可接受") or []
        if isinstance(可接受, str):
            s = 可接受.strip()
            try:
                可接受 = json.loads(s) if s else []
            except json.JSONDecodeError:
                可接受 = [s]
        if not isinstance(可接受, list):
            可接受 = [可接受]
        if 型 == "选择":
            对, _ = _judge_choice(标准, 作答)
        elif 型 == "接续":
            对, _ = _judge_exact(标准, 可接受, 作答)
        else:
            对, _ = _judge_fill(标准, 作答)
        return "1" if 对 else "0"

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
