"""改动范围闸（v2 用，与任务类型无关）：只许改 scope 里的目录前缀 / 精确文件 / 通配（带 * ? [ 的 glob）下的文件。

来源（优先级从高到低）：run(scope=…) / 命令行 --scope a/,b/（逗号分隔）；规划计划里可选的 #范围 块；都没有 = 不启用。
  parse(x)                  "a/,b/" 或列表 → 规范化前缀列表（空 = 没有）
  split(raw)                规划回复 → (去掉 #范围 块的回复, 前缀列表|None)；块到下一个 # 开头的行或结尾
  outside(files, scope)     files 里不在范围内的（前缀按目录边界匹配：kg/ 与 kg 等价，不匹配 kgx/）
  gap(files, scope)         一条缺口 {"说明", "文件列表", "越界": True}
  fix_note(files, scope)    补改入参追加的说明
  activate(scope) / guard(rel)  写类动词的统一拦截：v2 开始执行计划前 activate(范围)，写 / 改 / 删文件的动词（经 reason.check）和补改套用（verify.code.apply_edits）
                            先问 guard(相对路径)——范围外返回拦截原因，范围内（或没启用）返回 ""。范围同时写进环境变量 DSLAGENT_SCOPE_GLOBS，
                            子进程（dslmcp 的 tool 模式）从那里读。
范围项写法：`a/`（目录前缀，不写斜杠也行）、`a/b.py`（精确文件）、`routes/graph*`（含 * ? [ 的按 glob 匹配整条相对路径，* 可跨目录）。
"""
import fnmatch
import json
import os
import re

GLOB_CHARS = re.compile(r"[*?\[]")
ENV = "DSLAGENT_SCOPE_GLOBS"
_ACTIVE = {"scope": None}
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
            out.append(p if GLOB_CHARS.search(p) else p.rstrip("/") + "/")
    return list(dict.fromkeys(out))


def split(raw):
    m = BLOCK.search(raw or "")
    if not m:
        return raw, None
    return (raw[:m.start()] + raw[m.end():]), parse(m.group(1)) or None


def inside(rel, scope):
    return any(fnmatch.fnmatchcase(rel, p) if GLOB_CHARS.search(p) else rel == p.rstrip("/") or rel.startswith(p) for p in scope)


def outside(files, scope):
    return [f for f in files if not inside(f, scope)] if scope else []


def gap(files, scope):
    return {"说明": f"越界改动：{'、'.join(files)}（只能改 {'、'.join(scope)} 内的文件；这些文件已恢复成改前内容）",
            "文件列表": list(files), "越界": True}


def fix_note(files, scope):
    return (f"\n\n【改动范围】只能改 {'、'.join(scope)} 内的文件。上一步改了范围外的 {'、'.join(files)}，已恢复成改前内容；"
            f"请只在范围内的文件里完成任务（不要再改范围外的文件）。")


def activate(scope):
    """启用 / 关闭（空）写类动词的范围拦截；同时设 / 清环境变量给子进程。"""
    scope = list(scope or [])
    _ACTIVE["scope"] = scope or None
    if scope:
        os.environ[ENV] = json.dumps(scope, ensure_ascii=False)
    else:
        os.environ.pop(ENV, None)


def current():
    if _ACTIVE["scope"] is not None:
        return _ACTIVE["scope"]
    raw = os.environ.get(ENV)
    if raw:
        try:
            return parse(json.loads(raw))
        except ValueError:
            return None
    return None


def guard(rel):
    """写 / 改 / 删 rel（相对项目根）之前问一下：范围外返回拦截原因，否则 ""。"""
    sc = current()
    rel = str(rel).replace("\\", "/")
    rel = rel[2:] if rel.startswith("./") else rel
    if not sc or inside(rel, sc):
        return ""
    return f"范围拦截：{rel} 不在允许改动的范围内（只能改 {'、'.join(sc)}）"
