# -*- coding: utf-8 -*-
"""给 tools/ui.py 和 templates/frontend/app.js.j2 打三处补丁。

    cd mcp
    py data/patch_ui.py

改的是会话组件那批新增里的三个问题，都在容器里复现并验证过，
打完补丁后原有的 32 项页面测试仍然全过。
"""

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent


def patch(path: Path, old: str, new: str, label: str) -> bool:
    text = path.read_text(encoding="utf-8")
    if new.strip()[:40] in text:
        print(f"  跳过（已打过）：{label}")
        return True
    if old not in text:
        print(f"  找不到锚点：{label}")
        return False
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"  已改：{label}")
    return True


def main() -> int:
    ui = BASE / "tools" / "ui.py"
    tpl = BASE / "templates" / "frontend" / "app.js.j2"
    ok = True

    # --- 1. 消息流的默认值也走 _put_path ---
    # 之前 setdefault 只认平铺的键：「消息流 chat 绑 session.messages」会建出
    # 字面量键 "session.messages"，而「显示 note 绑 session.note」建的是嵌套
    # {"session": {"note": ""}}。同一份 shared 里两种结构并存，模板按路径取
    # 就找不着——跟之前修过的「绑 a.b 写进 undefined」是同一类。
    ok &= patch(ui,
        '''            elif n.kind == "消息流":
                shared.setdefault(n.bind or n.name, [])''',
        '''            elif n.kind == "消息流":
                _put_path(shared, n.bind or n.name, [])''',
        "消息流默认值走 _put_path")

    # --- 2. validate 增加共享路径冲突和消息流歧义检查 ---
    ok &= patch(ui,
        '''                    line=node.line, code="bad_endpoint"))
    return issues''',
        '''                    line=node.line, code="bad_endpoint"))
    issues.extend(_check_state_paths(screens))
    return issues


def _check_state_paths(screens) -> list:
    """跨界面状态的路径冲突，以及消息流路由的歧义。

    共享状态是所有界面合用一份，路径撞车在单个界面里看不出来，必须整棵树
    一起查。这几样 bind() 也管不到：消息流和显示不算字段，fields() 不返回。
    """
    issues, owner, streams = [], {}, []
    for screen in screens:
        for node in screen.walk():
            if node.kind == "消息流":
                streams.append(node)
            shared_node = (node.kind in ("消息流", "显示")
                           or (node.kind == "字段" and node.has("共享")))
            if not shared_node:
                continue
            path = node.bind or node.name
            prev = owner.get(path)
            if prev is not None and prev.kind != node.kind:
                issues.append(Issue(
                    f"共享路径「{path}」被「{prev.kind}」和「{node.kind}」同时占用"
                    f"（另一处在第 {prev.line} 行）",
                    line=node.line, code="path_conflict"))
            owner.setdefault(path, node)

    # 后端返回的 messages 不带 stream 字段时会落到第一条流上。一条流时这是
    # 合理的默认；多条流时就成了靠声明顺序决定的隐式路由，值得说一声。
    if len(streams) > 1 and any(a.to for s in screens for a in s.actions()):
        names = "、".join(n.bind or n.name for n in streams)
        first = streams[0].bind or streams[0].name
        issues.append(Issue(
            f"有 {len(streams)} 个消息流（{names}），后端返回的 messages 不带 "
            f"stream 字段时会一律落到第一个「{first}」上",
            line=streams[1].line, code="ambiguous_stream"))
    return issues''',
        "validate 加共享路径冲突 / 消息流歧义检查")

    # --- 3. app.js.j2 声明 endpoints ---
    # 模板里 endpoints 被引用三次，一次都没声明过。onAction 里是裸引用，
    # 只要点带「到」的动作就 ReferenceError；submitTo 里的 typeof 守卫更糟，
    # 它不报错，只是永远走 fallback，看着像"后端没接上"。
    ok &= patch(tpl,
        '''const blank = <%= form_defaults_json %>;''',
        '''const blank = <%= form_defaults_json %>;
<% if has_endpoints %>
// 动作名 -> 后端端点。这个常量之前漏了声明，onAction 里裸引用直接
// ReferenceError；submitTo 里的 typeof 守卫不报错，但会永远走 fallback。
const endpoints = <%= endpoints_json %>;
<% endif %>''',
        "app.js.j2 声明 endpoints")

    ok &= patch(tpl,
        '''      const ep = (typeof endpoints !== "undefined") ? endpoints[name] : null;''',
        '''      const ep = <% if has_endpoints %>endpoints[name]<% else %>null<% endif %>;''',
        "submitTo 去掉 typeof 守卫")

    if ok:
        print("\n全部完成。验证：")
        print("  py -c \"import sys;sys.path.insert(0,'.');"
              "from tools.ui import parse,validate;"
              "print([str(i) for i in validate(parse(open('data/tests/fixture.ui',"
              "encoding='utf-8').read()))])\"")
        print("  py data/tests/gen.py && cd data/tests && node test_page.js")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
