"""workflow_demo 测试共用的假模型回复：每条都符合 workflow_demo/formats/ 里对应的格式。

流程（10 次调用）：约定 v1 → 审查需修改 → 约定 v2（修改版）→ 审查通过 → 分配两项 →
实现两项 → QA 需修改（修边界条件）→ 修改 → QA 通过。
"""


def contract(v):
    return {"contract": {
        "goal": f"用户接口 {v}", "constraints": ["Python3"],
        "interfaces": [{"name": "create_user", "input": {"username": "str，必填"},
                        "output": {"user_id": "int"},
                        "errors": [{"code": "INVALID_USERNAME", "when": "用户名不合法"}]}],
        "invariants": ["用户名唯一"], "acceptance": ["create_user 返回 user_id"],
        "risks": [], "open_questions": []}}


def revision(v):
    r = contract(v)
    r["changes"] = [{"issue": "缺错误码", "action": "已修改", "detail": "补了 INVALID_USERNAME"}]
    return r


def review(decide):
    issues = [] if decide == "通过" else [
        {"location": "create_user.errors", "problem": "缺错误码", "suggestion": "补上", "severity": "一般"}]
    return {"decide": decide, "summary": f"审查结论：{decide}", "issues": issues}


def assignment(*contents):
    return {"tasks": [{"content": c, "agent": "ENGINEER"} for c in contents]}


def impl(what, fix_for=None):
    r = {"status": "完成", "summary": f"完成{what}",
         "changes": [{"target": f"{what}.py", "action": "新增", "detail": what}],
         "error_handling": [], "verification": {"executed": True, "method": "python -m pytest",
                                                 "result": "3 passed"},
         "open_issues": [], "need_architect": []}
    if fix_for:
        r["fix_for"] = fix_for
    return r


def acceptance(decide, task=None):
    r = {"decide": decide, "summary": f"验收：{decide}",
         "checked": [{"item": "create_user", "result": "满足" if decide == "通过" else "不满足",
                      "evidence": "跑了测试"}],
         "not_verified": []}
    if task:
        r["task"] = task
    return r


REPLIES = [
    contract("v1"), review("需修改"), revision("v2"),
    review("通过"),
    assignment("实现接口", "补充测试"),
    impl("接口"), impl("测试"),
    acceptance("需修改", "修边界条件"), impl("边界", fix_for="修边界条件"),
    acceptance("通过"),
]
