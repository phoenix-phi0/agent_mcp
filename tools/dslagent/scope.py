"""改动范围闸（v2 用，与任务类型无关）：只许改 scope 里的目录前缀下的文件。

来源（优先级从高到低）：run(scope=…) / 命令行 --scope a/,b/（逗号分隔）；规划计划里可选的 #范围 块；都没有 = 不启用。
  parse(x)                  "a/,b/" 或列表 → 规范化前缀列表（空 = 没有）
  split(raw)                规划回复 → (去掉 #范围 块的回复, 前缀列表|None)；块到下一个 # 开头的行或结尾
  outside(files, scope)     files 里不在范围内的（前缀按目录边界匹配：kg/ 与 kg 等价，不匹配 kgx/）
  gap(files, scope)         一条缺口 {"说明", "文件列表", "越界": True}
  fix_note(files, scope)    补改入参追加的说明
"""
import re

BLOCK = re.compile(r"^#范围[ \t]*\n(.*?)(?=^#\S|\Z)", re.S | re.M)


def parse(x):
    if not x:
        return []
    items = x if isinstance(x, (list, tuple)) else re.split(r"[,，\n]", str(x))
    out = []
    for it in items:
        p = str(it).strip().strip("`'\"").lstrip("-* ").strip().replace("\\", "/")
        p = p[2:] if p.startswith("./") else p
        if p and p not in (".", "/"):
            out.append(p.rstrip("/") + "/")
    return list(dict.fromkeys(out))


def split(raw):
    m = BLOCK.search(raw or "")
    if not m:
        return raw, None
    return (raw[:m.start()] + raw[m.end():]), parse(m.group(1)) or None


def inside(rel, scope):
    return any(rel == p.rstrip("/") or rel.startswith(p) for p in scope)


def outside(files, scope):
    return [f for f in files if not inside(f, scope)] if scope else []


def gap(files, scope):
    return {"说明": f"越界改动：{'、'.join(files)}（只能改 {'、'.join(scope)} 内的文件；这些文件已恢复成改前内容）",
            "文件列表": list(files), "越界": True}


def fix_note(files, scope):
    return (f"\n\n【改动范围】只能改 {'、'.join(scope)} 内的文件。上一步改了范围外的 {'、'.join(files)}，已恢复成改前内容；"
            f"请只在范围内的文件里完成任务（不要再改范围外的文件）。")
