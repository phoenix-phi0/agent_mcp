# -*- coding: utf-8 -*-
"""把「到 <端点>」换成「远程」旗标，端点全部移到调用方。

    cd mcp
    py data/patch_ui2.py

先打 patch_ui.py 再打这个。

为什么
------
`.ui` 是界面描述，跟渲染目标无关——这条边界是整套设计的地基，模板、
后端、Qt/终端目标能共用一份描述全靠它。`到 /api/chat` 把后端地址写进了
界面描述，等于把它绑死在一个 HTTP 后端上：Qt 目标勉强能翻译成请求，
终端目标就没法解释了；而且地址是部署细节，换个环境就要改 .ui。

改成：`.ui` 只说「这个动作要发出去」（`远程` 旗标），发到哪由调用方的
endpoints 字典给，动作名就是键。那个字典本来就存在，现在成了唯一来源。

    动作 send 提交 远程 发送
    options={"endpoints": {"send": "/api/chat"}}

代价是两处要对齐，所以新增 missing_endpoint 检查：标了远程却不在
endpoints 里的动作会被报出来。不传 endpoints 时不检查（只解析、只出
ir/text 的场景没必要）。
"""

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent


def patch(path: Path, old: str, new: str, label: str) -> bool:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        marker = (new.strip()[:40] if new.strip() else None)
        if marker and marker in text:
            print(f"  跳过（已打过）：{label}")
            return True
        print(f"  找不到锚点：{label}")
        return False
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"  已改：{label}")
    return True


def main() -> int:
    ui = BASE / "tools" / "ui.py"
    ok = True

    # --- 1. 「到」退出带参修饰，「远程」进旗标 ---
    ok &= patch(ui,
        'KEYED_MODIFIERS = {"绑", "控件", "当", "到"}',
        'KEYED_MODIFIERS = {"绑", "控件", "当"}',
        "「到」退出 KEYED_MODIFIERS")

    ok &= patch(ui,
        '''    "共享",                          # field: lives in cross-screen state
}''',
        '''    "共享",                          # field: lives in cross-screen state
    "远程",                          # action: fires a request; the address
                                     # is the caller's business, not the .ui's
}''',
        "「远程」加进 FLAG_MODIFIERS")

    ok &= patch(ui,
        '''    if "到" in keyed:
        node.to = keyed["到"]
''', '', "_apply_keyed 去掉「到」")

    # --- 2. 校验换向：不再查地址格式，改查端点有没有配 ---
    ok &= patch(ui,
        '''            if node.to is not None and not str(node.to).startswith("/"):
                issues.append(Issue(
                    f"动作「{node.name}」的「到」要是以 / 开头的路径，现在是「{node.to}」",
                    line=node.line, code="bad_endpoint"))
''', '', "去掉 bad_endpoint 检查")

    ok &= patch(ui,
        'def validate(screens, require_bind: bool = False) -> list:',
        'def validate(screens, require_bind: bool = False, endpoints=None) -> list:',
        "validate 收 endpoints")

    ok &= patch(ui,
        '''    issues.extend(_check_state_paths(screens))
    return issues''',
        '''    issues.extend(_check_state_paths(screens))
    if endpoints is not None:
        issues.extend(_check_endpoints(screens, endpoints))
    return issues''',
        "validate 调 _check_endpoints")

    ok &= patch(ui,
        'def _check_state_paths(screens) -> list:',
        '''def _check_endpoints(screens, endpoints) -> list:
    """「远程」动作要在 endpoints 里有对应的项。

    .ui 只说「这个动作要发出去」，地址由调用方给——地址是部署细节，写进
    .ui 就等于把界面描述绑死在一个后端上。代价是两处要对齐，查一遍。
    """
    issues = []
    for screen in screens:
        for a in screen.actions():
            if a.has("远程") and a.name not in (endpoints or {}):
                issues.append(Issue(
                    f"动作「{a.name}」标了远程，但 endpoints 里没有它",
                    line=a.line, code="missing_endpoint"))
    return issues


def _check_state_paths(screens) -> list:''',
        "新增 _check_endpoints")

    # --- 3. 消息流歧义检查改看「远程」 ---
    ok &= patch(ui,
        'if len(streams) > 1 and any(a.to for s in screens for a in s.actions()):',
        'if len(streams) > 1 and any(a.has("远程") for s in screens for a in s.actions()):',
        "歧义检查改看「远程」")

    # --- 4. render_vue 的 has_to_actions ---
    ok &= patch(ui,
        'has_to = any(a.to for s in screens for a in s.actions())',
        'has_remote = any(a.has("远程") for s in screens for a in s.actions())',
        "has_to → has_remote")

    ok &= patch(ui,
        '"has_to_actions": has_to,',
        '"has_to_actions": has_remote,',
        "上下文变量改名")

    # --- 5. compile_ui 把 endpoints 传给 validate ---
    ok &= patch(ui,
        '    issues.extend(validate(screens, require_bind=require_bind))',
        '''    issues.extend(validate(screens, require_bind=require_bind,
                           endpoints=(options or {}).get("endpoints")))''',
        "compile_ui 传 endpoints")

    if ok:
        print("""
全部完成。Node.to 字段保留着没删（to_dict 里也还在），旧的 ir 产物
结构不变；它现在恒为 None，将来确认没人读了再摘。

要改的 .ui 写法：
    旧   动作 send 提交 到 /api/chat 发送
    新   动作 send 提交 远程 发送
         options={"endpoints": {"send": "/api/chat"}}

验证：
  py data/tests/gen.py && cd data/tests && node test_page.js""")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
