"""判一道单词默写。参数是一个结构：{方向, 作答, 词, 候选}。

    方向  meaning = 看中文写日语，reading = 看汉字写读音
    作答  学习者写的
    词    这道考的词 {kanji, kana, meaning}
    候选  库里跟它沾边的别的词（同意思、同汉字、同读音的），{kanji, kana,
          meaning} 的列表，由调用方查好给（kg 的 queries/dictation_near.sql）

返回 {correct: "1"/"0", note, mine}。note 是给人看的一句补充（同义词也算对、
写的是同读音的另一个词、这是另一个读法……），没有就空；mine 是归一以后的作答。

比较前两边都归一：NFKC（全角字母数字、半角片假名统一）、去掉空白和句号逗号、
片假名换成平假名——「アウ」「あう」「ｱｳ」是同一个答案。不认罗马字。

看中文写日语：写这个词的汉字或假名都对；意思文本（去掉开头的 [N4] 等级）
完全相同的别的词，写它的汉字或假名也对（同义词，题面只给了意思，人没法知道
要的是哪一个）。写成同读音不同意思的词（会う 写成 合う）判错，note 里说写的
是哪个词。

看汉字写读音：等于这个词的假名才对；同一个汉字的别的读音，意思也一样的也对，
意思不一样的判错，note 里说「这是另一个读法」。

为什么候选由调用方给、不在这里查库：动词包拿不到项目的库路径限制以外的东西，
规则也跟库无关——这里只管「怎么算一样」，测试直接喂结构就能测全。

参数坏了直接抛，不返回 0：调用方拿 0 当「答错」记进作答记录，一个格式问题
会变成一条假的错词。
"""

import json
import re
import unicodedata

# 去掉的：空白、句号、逗号（NFKC 之后全角的 ．，已经是半角）
_DROP = re.compile(r"[\s。.、,]+")
# 意思开头的等级前缀「[N4] 」
_LEVEL = re.compile(r"^\s*\[N[1-5]\]\s*")


def _norm(s) -> str:
    s = unicodedata.normalize("NFKC", str(s or ""))
    s = _DROP.sub("", s)
    # 片假名 ァ..ヶ 挪到平假名（长音符 ー 不动）
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in s)


def _meaning(m) -> str:
    return _LEVEL.sub("", str(m or "")).strip()


def _show(w: dict) -> str:
    kanji, kana = str(w.get("kanji") or ""), str(w.get("kana") or "")
    head = f"{kanji}【{kana}】" if kanji and kanji != kana else f"{kana} "
    return f"{head}{_meaning(w.get('meaning'))}"


def _load(x, what):
    if isinstance(x, str):
        s = x.strip()
        if not s:
            return [] if what == "候选" else {}
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            raise ValueError(f"判默写的{what}不是合法 JSON：{s[:80]}")
    return x


def 判默写(默写) -> dict:
    默写 = _load(默写, "参数")
    if not isinstance(默写, dict):
        raise ValueError("判默写的参数要是一个结构：{方向, 作答, 词, 候选}")
    方向 = str(默写.get("方向", ""))
    if 方向 not in ("meaning", "reading"):
        raise ValueError(f"判默写：方向要是 meaning 或 reading，给的是「{方向}」")
    词 = _load(默写.get("词"), "词")
    if not isinstance(词, dict) or not str(词.get("kana") or ""):
        raise ValueError("判默写：没有考的词（词.kana 是空的）")
    候选 = _load(默写.get("候选") or [], "候选")
    if isinstance(候选, dict):
        候选 = [候选]
    if not isinstance(候选, list):
        raise ValueError("判默写：候选要是一个列表")
    候选 = [c for c in 候选 if isinstance(c, dict)]

    mine = _norm(默写.get("作答"))
    out = {"correct": "0", "note": "", "mine": mine}
    if not mine:
        out["note"] = "没有写答案"
        return out

    意思 = _meaning(词.get("meaning"))
    kanji = str(词.get("kanji") or "")

    if 方向 == "meaning":
        if mine in {_norm(kanji), _norm(词.get("kana"))} - {""}:
            out["correct"] = "1"
            return out
        for c in 候选:
            if mine not in {_norm(c.get("kanji")), _norm(c.get("kana"))} - {""}:
                continue
            if 意思 and _meaning(c.get("meaning")) == 意思:
                out["correct"] = "1"
                out["note"] = f"「{_show(c)}」意思一样，也算对"
                return out
        for c in 候选:
            if mine in {_norm(c.get("kanji")), _norm(c.get("kana"))} - {""}:
                out["note"] = f"你写的是另一个词：{_show(c)}"
                return out
        return out

    # reading：只认读音
    if mine == _norm(词.get("kana")):
        out["correct"] = "1"
        return out
    for c in 候选:
        if not kanji or str(c.get("kanji") or "") != kanji or mine != _norm(c.get("kana")):
            continue
        if 意思 and _meaning(c.get("meaning")) == 意思:
            out["correct"] = "1"
            out["note"] = f"「{kanji}」读【{c.get('kana')}】也对"
        else:
            out["note"] = f"这是另一个读法：{_show(c)}。这里要的是「{意思}」的读法"
        return out
    return out
