def drill_start(learner: str, 课程: str, 考点: str = "") -> dict:
    # 「全部考点」是下拉里的占位项，对动词来说等于不筛选
    if 考点 == "全部考点":
        考点 = ""
    _drills[learner] = {"课程": 课程, "考点": 考点,
                        "题号": "", "对": 0, "总": 0, "错题": []}
    return drill_next(learner)


def drill_next(learner: str) -> dict:
    st = _drills.get(learner)
    if not st:
        return _notice("还没开始练习", "no")

    题号 = call_verb("挑题号", BANK, "1", st["课程"], st["考点"])
    if not 题号 or 题号.startswith("["):
        return _notice(f"没有匹配的题目：课程={st['课程']} "
                       f"考点={st['考点'] or '不限'}", "no")

    st["题号"] = 题号
    r = _notice(call_verb("取题", BANK, 题号))
    r["messages"][0]["who"] = "题目"
    r["state"] = {"stat": _stat(st)}
    return r


def drill_answer(learner: str, 作答: str) -> dict:
    st = _drills.get(learner)
    if not st or not st["题号"]:
        return _notice("当前没有待答的题", "no")

    结果 = call_verb("判题", BANK, st["题号"], 作答)
    对了 = 结果.startswith("○")

    st["总"] += 1
    if 对了:
        st["对"] += 1
    else:
        st["错题"].append(st["题号"])
    st["题号"] = ""

    r = _notice(结果, "ok" if 对了 else "no")
    r["messages"][0]["who"] = "批改"
    r["state"] = {"stat": _stat(st)}
    return r


def drill_stop(learner: str) -> dict:
    st = _drills.pop(learner, None)
    if not st:
        return _notice("本来就没在练习")
    if not st["总"]:
        r = _notice("练习结束，没有作答记录")
        r["state"] = {"stat": ""}
        return r

    比例 = call_verb("算比例", st["对"], st["总"])
    错 = "，".join(st["错题"]) if st["错题"] else "无"
    r = _notice(f"练习结束：{st['对']}/{st['总']}（{比例}%）\n错题：{错}", "ok")
    r["state"] = {"stat": ""}
    return r
