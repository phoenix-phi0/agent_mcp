# -*- coding: utf-8 -*-
"""旧的 Python 判题规则，原样留一份，给 test_rules_equiv.py 做对照。

判对错、拆选项（原在 verbs/quiz/_verbs.py 的 register() 里）和判默写（原是
verbs/japanese/defs/判默写.py）挪进 .zs 之前的实现，取自提交 41703d8，一个字
没改（只是从闭包里拿出来、去掉了 @reg.verb）。业务规则以 .zs 为准，这份只用来
证明挪过去之后结果逐条一样——别在这里改规则。
"""

import hashlib
import json
import random
import re
import unicodedata

# ---------------------------------------------------------------- quiz 包

_CHOICE_RE = re.compile(r"[A-Da-dａ-ｄＡ-Ｄ]")
_KANA_TAIL = re.compile(r"[\u3040-\u309f]+$")


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


_OPTION_RE = re.compile(r"^\s*([A-DＡ-Ｄ])\s*[.．、:：]\s*(.*)$")


def 拆选项(题) -> dict:
    """题库沿用旧格式，选项写在题干里（「A. …」一行一个）。

    不改题库格式去存结构化选项：quiz 包的「挑题」「判题」、老师的流程
    都按现在的格式读，改了要动一串东西。在要画按钮的地方拆一下就够。
    """
    if isinstance(题, str):
        try:
            题 = json.loads(题)
        except json.JSONDecodeError:
            raise ValueError(f"拆选项的参数不是合法 JSON：{题[:80]}")
    if not isinstance(题, dict):
        raise ValueError("拆选项的参数要是一个结构：{题干, 题型, 答案, 选了}")
    stem_all = str(题.get("题干", ""))
    if str(题.get("题型", "")) != "选择":
        return {"stem": stem_all, "options": []}
    答案 = _norm(str(题.get("答案", ""))).upper()
    选了 = _norm(str(题.get("选了", ""))).upper()
    种子 = str(题.get("种子", "") or "")
    stem, options = [], []
    for line in stem_all.splitlines():
        m = _OPTION_RE.match(line)
        if m:
            key = unicodedata.normalize("NFKC", m.group(1)).upper()
            options.append({"key": key, "text": m.group(2).strip(), "state": ""})
        else:
            stem.append(line)
    # 打乱：题库里正确答案的位置是出题人定的，按课练时同一课几道题的
    # 答案字母可能全一样（hb-n4-012 三道都是 A），点同一个位置就全对。
    # 种子由调用方给（学习者+题号+第几次出题），出题和判题用同一个，
    # 顺序对得上；不用 hash()——每个进程的盐不一样。
    orig = {o["key"]: o["key"] for o in options}
    if 种子 and options:
        rnd = random.Random(int(hashlib.sha256(种子.encode("utf-8")).hexdigest(), 16))
        rnd.shuffle(options)
        orig = {}
        for i, o in enumerate(options):
            shown = "ABCDEFGH"[i] if i < 8 else o["key"]
            orig[shown] = o["key"]
            o["key"] = shown
    picked = orig.get(选了, 选了)
    answer_key = next((k for k, v in orig.items() if v == 答案), 答案)
    if 答案 and 选了:
        for o in options:
            o["state"] = ("right" if orig[o["key"]] == 答案
                          else "wrong" if o["key"] == 选了 else "dim")
    return {"stem": "\n".join(stem).strip(), "options": options,
            "picked": picked, "answer_key": answer_key}


# ---------------------------------------------------------------- 判默写

# 去掉的：空白、句号、逗号（NFKC 之后全角的 ．，已经是半角）
_DDROP = re.compile(r"[\s。.、,]+")
# 意思开头的等级前缀「[N4] 」
_DLEVEL = re.compile(r"^\s*\[N[1-5]\]\s*")


def _dnorm(s) -> str:
    s = unicodedata.normalize("NFKC", str(s or ""))
    s = _DDROP.sub("", s)
    # 片假名 ァ..ヶ 挪到平假名（长音符 ー 不动）
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in s)


def _meaning(m) -> str:
    return _DLEVEL.sub("", str(m or "")).strip()


def _show(w: dict) -> str:
    kanji, kana = str(w.get("kanji") or ""), str(w.get("kana") or "")
    head = f"{kanji}【{kana}】" if kanji and kanji != kana else f"{kana} "
    return f"{head}{_meaning(w.get('meaning'))}"


def _dload(x, what):
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
    默写 = _dload(默写, "参数")
    if not isinstance(默写, dict):
        raise ValueError("判默写的参数要是一个结构：{方向, 作答, 词, 候选}")
    方向 = str(默写.get("方向", ""))
    if 方向 not in ("meaning", "reading"):
        raise ValueError(f"判默写：方向要是 meaning 或 reading，给的是「{方向}」")
    词 = _dload(默写.get("词"), "词")
    if not isinstance(词, dict) or not str(词.get("kana") or ""):
        raise ValueError("判默写：没有考的词（词.kana 是空的）")
    候选 = _dload(默写.get("候选") or [], "候选")
    if isinstance(候选, dict):
        候选 = [候选]
    if not isinstance(候选, list):
        raise ValueError("判默写：候选要是一个列表")
    候选 = [c for c in 候选 if isinstance(c, dict)]

    mine = _dnorm(默写.get("作答"))
    out = {"correct": "0", "note": "", "mine": mine}
    if not mine:
        out["note"] = "没有写答案"
        return out

    意思 = _meaning(词.get("meaning"))
    kanji = str(词.get("kanji") or "")

    if 方向 == "meaning":
        if mine in {_dnorm(kanji), _dnorm(词.get("kana"))} - {""}:
            out["correct"] = "1"
            return out
        for c in 候选:
            if mine not in {_dnorm(c.get("kanji")), _dnorm(c.get("kana"))} - {""}:
                continue
            if 意思 and _meaning(c.get("meaning")) == 意思:
                out["correct"] = "1"
                out["note"] = f"「{_show(c)}」意思一样，也算对"
                return out
        for c in 候选:
            if mine in {_dnorm(c.get("kanji")), _dnorm(c.get("kana"))} - {""}:
                out["note"] = f"你写的是另一个词：{_show(c)}"
                return out
        return out

    # reading：只认读音
    if mine == _dnorm(词.get("kana")):
        out["correct"] = "1"
        return out
    for c in 候选:
        if not kanji or str(c.get("kanji") or "") != kanji or mine != _dnorm(c.get("kana")):
            continue
        if 意思 and _meaning(c.get("meaning")) == 意思:
            out["correct"] = "1"
            out["note"] = f"「{kanji}」读【{c.get('kana')}】也对"
        else:
            out["note"] = f"这是另一个读法：{_show(c)}。这里要的是「{意思}」的读法"
        return out
    return out
