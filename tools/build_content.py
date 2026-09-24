"""把秋山 N2N3 词汇教材转成课文 + 题库。

用法：
    py tools/build_content.py <教材目录> <输出目录>
    py tools/build_content.py vocabulary workspace/japanese/content

做三件事：
  1. 清洗 PDF 提取残留的康熙部首字符（⼈ U+2F08 → 人 U+4EBA）
     这些字符看着一样码点不同，不清洗会导致学习者输入匹配不上。
  2. 把 12 个课程文件解析成结构化词条，重新写成干净的课文。
  3. 按词条生成题库 jsonl，供 quiz 包的「挑题」「取答案」使用。

题型：
  词义选择 —— 干扰项从同课其他词的释义里抽，天然合理
  汉字书写 —— 挖掉例句里的汉字词干，答案是汉字
"""

import json
import random
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

# 康熙部首与 CJK 部首补充区，PDF 提取常见残留
RADICAL_RANGE = ("\u2e80", "\u2fdf")

SEED = 20260904


def clean(text: str) -> str:
    """把康熙部首归一成常用汉字，其余字符原样保留。"""
    return "".join(
        unicodedata.normalize("NFKC", ch)
        if RADICAL_RANGE[0] <= ch <= RADICAL_RANGE[1] else ch
        for ch in text
    )


def parse_lesson(path: Path) -> tuple[str, list[dict]]:
    """解析一个课程文件，返回 (标题, 词条列表)。"""
    lines = clean(path.read_text(encoding="utf-8")).splitlines()
    title = lines[0].lstrip("# ").strip() if lines else path.stem

    entries: list[dict] = []
    cur: dict | None = None

    for ln in lines:
        s = ln.strip()
        m = re.match(r"^##\s*(\d+)\.\s*(\S+?)[　\s]+(.+)$", s)
        if m:
            if cur:
                entries.append(cur)
            cur = {
                "序号": int(m.group(1)),
                "词": m.group(2),
                "释义": m.group(3).strip(),
                "近义词": "",
                "例句": [],
                "辨析": "",
            }
            continue
        if cur is None:
            continue
        if s.startswith("近义词："):
            cur["近义词"] = s[4:].strip()
        elif s.startswith("＊"):
            cur["辨析"] = s[1:].strip()
        elif s.startswith("- "):
            cur["例句"].append({"日": s[2:].strip(), "中": ""})
        elif s.startswith("（") and s.endswith("）") and cur["例句"]:
            cur["例句"][-1]["中"] = s.strip("（）")

    if cur:
        entries.append(cur)
    return title, entries


def write_lesson(out: Path, title: str, entries: list[dict]) -> None:
    """写出清洗后的课文，格式跟原教材一致但字符干净。"""
    parts = [f"# {title}", "", f"词汇数：{len(entries)}", "", "---", ""]
    for e in entries:
        parts.append(f"## {e['序号']}. {e['词']}　{e['释义']}")
        parts.append("")
        if e["近义词"]:
            parts += [f"近义词：{e['近义词']}", ""]
        if e["例句"]:
            parts += ["**例句**", ""]
            for ex in e["例句"]:
                parts.append(f"- {ex['日']}")
                if ex["中"]:
                    parts.append(f"  　（{ex['中']}）")
                parts.append("")
        if e["辨析"]:
            parts += [f"＊{e['辨析']}", ""]
        parts += ["---", ""]
    out.write_text("\n".join(parts), encoding="utf-8")


def make_questions(lesson: str, entries: list[dict]) -> list[dict]:
    """给一课的词条生成题目。"""
    questions = []
    meanings = [e["释义"] for e in entries]

    for e in entries:
        wid = f"{lesson}-{e['序号']:02d}"

        # 词义选择：干扰项来自同课其他词
        pool = [m for m in meanings if m != e["释义"]]
        if len(pool) >= 3:
            opts = random.sample(pool, 3) + [e["释义"]]
            random.shuffle(opts)
            questions.append({
                "id": f"{wid}-意味",
                "课程": lesson,
                "考点": "词义",
                "难度": "基础",
                "题型": "选择",
                "题干": f"「{e['词']}」的意思是？\n"
                        + "\n".join(f"{chr(65+i)}. {o}" for i, o in enumerate(opts)),
                "答案": chr(65 + opts.index(e["释义"])),
                "解析": f"{e['词']}：{e['释义']}"
                        + (f"。{e['辨析']}" if e["辨析"] else ""),
            })

        # 汉字书写：挖掉例句里的汉字词干
        stem = re.sub(r"[\u3040-\u309f]+$", "", e["词"])
        if not stem:                       # 纯假名词，跳过
            continue
        for ex in e["例句"]:
            if not ex["中"] or stem not in ex["日"]:
                continue
            blank = "＿" * len(stem)
            questions.append({
                "id": f"{wid}-漢字",
                "课程": lesson,
                "考点": "汉字书写",
                "难度": "进阶",
                "题型": "填空",
                "题干": f"填入正确的汉字（{len(stem)}字）：\n"
                        f"{ex['日'].replace(stem, blank, 1)}\n（{ex['中']}）",
                "答案": stem,
                "解析": f"{e['词']}（{e['释义']}）　原句：{ex['日']}",
            })
            break                          # 每词一道，避免题量膨胀

    return questions


def build(src: Path, dst: Path) -> str:
    random.seed(SEED)
    src, dst = Path(src), Path(dst)
    if not src.is_dir():
        return f"教材目录不存在：{src}"

    lessons_dir = dst / "n2n3"
    lessons_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(p for p in src.glob("*.md") if p.name != "INDEX.md")
    if not files:
        return f"{src} 下没有课程文件"

    index_rows, all_questions, report = [], [], []

    for f in files:
        title, entries = parse_lesson(f)
        if not entries:
            report.append(f"  {f.name}：解析不出词条，跳过")
            continue

        write_lesson(lessons_dir / f.name, title, entries)
        qs = make_questions(f.stem, entries)
        all_questions += qs

        index_rows.append((f.stem, title, len(entries), len(qs)))
        report.append(f"  {f.name:18} {len(entries):3}词 → {len(qs):3}题")

    # 题库
    bank = lessons_dir / "题库.jsonl"
    bank.write_text(
        "\n".join(json.dumps(q, ensure_ascii=False) for q in all_questions) + "\n",
        encoding="utf-8",
    )

    # 课程索引
    idx = ["# N2N3 核心词汇", "", "| 课程ID | 名称 | 词汇数 | 题目数 |",
           "|---|---|---|---|"]
    for stem, title, nw, nq in index_rows:
        idx.append(f"| {stem} | {title} | {nw} | {nq} |")
    idx += ["", f"题库：`n2n3/题库.jsonl`（共 {len(all_questions)} 题）", ""]
    (lessons_dir / "INDEX.md").write_text("\n".join(idx), encoding="utf-8")

    # 系列索引
    series = dst / "SERIES.md"
    series.write_text(
        "# 课程系列\n\n"
        "| 系列ID | 名称 | 说明 |\n"
        "|---|---|---|\n"
        "| n2n3 | N2N3 核心词汇 | 秋山词汇课，动词/形容词/副词/拟声词，共 360 词 |\n",
        encoding="utf-8",
    )

    kinds = Counter(q["考点"] for q in all_questions)
    return (
        "\n".join(report)
        + f"\n\n课文写入 {lessons_dir}"
        + f"\n题库 {bank.name}：{len(all_questions)} 题　"
        + "，".join(f"{k} {v}" for k, v in kinds.items())
        + f"\n索引 {lessons_dir / 'INDEX.md'} 与 {series}"
    )


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    print(build(Path(sys.argv[1]), Path(sys.argv[2])))
