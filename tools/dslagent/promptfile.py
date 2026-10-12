"""提示词文件加载：从 tools/dslagent/prompts/ 按相对路径读，带缓存；文件缺失 / 不是 UTF-8 / 模板缺占位直接报清楚的错。

text(rel)      文件原文，逐字（不去首尾换行、不改换行符）。
tpl(rel, **kw) 模板：按 str.format 填占位（文件里的字面花括号写 {{ }}）；缺占位报 KeyError 并带文件名。
js(rel)        JSON 文件解析后的对象。
约定和各文件说明见 prompts/README.md。
"""
import json
from pathlib import Path

DIR = Path(__file__).resolve().parent / "prompts"
_cache = {}


def text(rel):
    if rel not in _cache:
        p = DIR / rel
        try:
            raw = p.read_bytes()
        except OSError as e:
            raise FileNotFoundError(f"提示词文件读不到：{p}（prompts/ 下的 {rel}）：{e}") from None
        try:
            _cache[rel] = raw.decode("utf-8")
        except UnicodeDecodeError as e:
            raise ValueError(f"提示词文件不是 UTF-8：{p}：{e}") from None
    return _cache[rel]


def tpl(rel, **kw):
    try:
        return text(rel).format(**kw)
    except KeyError as e:
        raise KeyError(f"提示词模板 {DIR / rel} 里的占位 {e} 没有给值（给了：{'、'.join(sorted(kw))}）") from None
    except (IndexError, ValueError) as e:
        raise ValueError(f"提示词模板 {DIR / rel} 的占位写法不对：{e}（字面花括号写成 {{{{ }}}}）") from None


def js(rel):
    try:
        return json.loads(text(rel))
    except json.JSONDecodeError as e:
        raise ValueError(f"提示词文件 {DIR / rel} 不是合法 JSON：{e}") from None
