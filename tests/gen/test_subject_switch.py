# -*- coding: utf-8 -*-
"""前端 nav 科目切换器：templates/frontend/app.js.j2、style.css.j2。

    cd /workspace/agent_mcp && .venv/bin/python tests/gen/test_subject_switch.py

项目声明了远程动作 subject_switch 且开着 auth_me，才在顶栏渲染科目下拉
（auth_me 响应里的 subjects [{id,name}…] 与 subject）；没声明的项目产物里
一个字都没有。node 行为：refreshMe 读两个键、下拉切换调 subject_switch 后 reload，
失败弹提示并退回原值。
"""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.ui import compile_ui    # noqa: E402

passed = failed = 0


def check(msg, ok):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


UI = ("界面 自定义 首页\n  文案 你好\n结束\n"
      "界面 自定义 设置\n  文案 设置\n结束\n")
NAV = [{"label": "首页", "target": "首页", "group": ["首页"]},
       {"label": "设置", "target": "设置", "group": ["设置"]}]
BASE = {"auth_me": "/auth/me", "auth_logout": "/auth/logout"}
SWITCH = dict(BASE, subject_switch="/subject/switch")


def build(eps, nav=True):
    r = compile_ui(UI, backend="vue", options={"endpoints": eps, **({"nav": NAV} if nav else {})})
    assert not r.get("issues"), r.get("issues")
    f = r["result"]["files"]
    return f["app.js"], f["style.css"]


print("一、编译产物：有/无 subject_switch")
for nav in (True, False):
    tag = "项目 nav" if nav else "引擎 nav"
    js, css = build(SWITCH, nav)
    check(f"[{tag}] 有 subject_switch：下拉、switchSubject、subjects 读取、样式都在",
          'class="nav-subject"' in js and "async function switchSubject" in js
          and "me.subjects.length > 1" in js and "d.subjects" in js and ".nav-subject" in css)
    check(f"[{tag}] 下拉选项显示 name、选中 = me.subject",
          '{{ s.name }}' in js and ':selected="s.id === me.subject"' in js)
    check(f"[{tag}] switchSubject 导出给模板", ", switchSubject," in js)
    js0, css0 = build(BASE, nav)
    check(f"[{tag}] 没声明 subject_switch：产物里没有 subject 相关的任何东西",
          "subject" not in js0.lower() and "nav-subject" not in css0)
    jsn, cssn = build({"subject_switch": "/subject/switch"}, nav)
    check(f"[{tag}] 声明了动作但没开 auth_me（拿不到 subjects）：不渲染",
          "switchSubject" not in jsn and "nav-subject" not in cssn)
js0, css0 = build(BASE)
js1, css1 = build(SWITCH)
check("有无差异很小：开切换器只多出几十行（函数、下拉、读两个键）",
      0 < len(js1.splitlines()) - len(js0.splitlines()) < 40)
check("两个 nav 分支都放了下拉", build(SWITCH, True)[0].count('class="nav-subject"') == 1
      and build(SWITCH, False)[0].count('class="nav-subject"') == 1)

node = shutil.which("node")
if not node:
    print("  - 没有 node，跳过语法和行为检查")
else:
    print("二、node：语法与行为")
    js, _ = build(SWITCH)
    tmp = Path(tempfile.mkdtemp(prefix="k73ui_"))
    try:
        f = tmp / "app_check.js"
        f.write_text(js, encoding="utf-8")
        p = subprocess.run([node, "--check", str(f)], capture_output=True, text=True, timeout=30)
        check(f"产物 node --check 通过 {p.stderr[-120:]}", p.returncode == 0)
        a = js.find("async function refreshMe(fresh) {")
        b = js.find("async function checkEnd(")
        c = js.find("async function switchSubject(ev) {")
        d = js.find("// 登录的人是别的端的", c)
        n0 = js.find("const NOBODY")
        n1 = js.find("\n", n0)
        check("能切出 NOBODY / refreshMe / switchSubject 三段", min(a, b, c, d, n0) > 0)

        def run(me_resp, switch_resp, select_value="2"):
            harness = (
                "const ref = v => ({ value: v });\n"
                "const endpoints = { auth_me: '/m', subject_switch: '/s' };\n"
                "let fetched = null; const calls = []; const notices = []; let reloaded = 0;\n"
                f"globalThis.fetch = async () => ({{ json: async () => ({json.dumps(me_resp)}) }});\n"
                "globalThis.location = { reload: () => { reloaded++; } };\n"
                "const checkEnd = async () => false, guardSide = () => {};\n"
                "const showNotice = (m, k) => notices.push([m, k]);\n"
                f"const postTo = async (u, p) => {{ calls.push([u, p]); const r = {json.dumps(switch_resp)}; if (r === 'throw') throw new Error('x'); return r; }};\n"
                + js[n0:n1] + "\nconst me = ref({ ...NOBODY });\n"
                + js[a:b].rsplit("\n    // 登录的人是别的端的", 1)[0].replace("async function checkEnd(", "")
                + "\n" + js[c:d] +
                "\n(async () => {\n"
                "  const out = {};\n"
                "  await refreshMe();\n"
                "  out.me = me.value;\n"
                f"  const sel = {{ value: '{select_value}' }};\n"
                "  await switchSubject({ target: sel });\n"
                "  out.calls = calls; out.notices = notices; out.reloaded = reloaded; out.sel = sel.value;\n"
                "  console.log(JSON.stringify(out));\n"
                "})();\n")
            p = subprocess.run([node, "-e", harness], capture_output=True, text=True, timeout=30)
            try:
                return json.loads(p.stdout.strip().splitlines()[-1])
            except Exception:
                return {"错误": (p.stdout + p.stderr)[-400:]}

        subs = [{"id": 1, "name": "日语"}, {"id": 2, "name": "英语"}]
        me = {"user": "u", "label": "小明", "subjects": subs, "subject": 1}
        o = run(me, {"ok": True})
        check(f"refreshMe 读 subjects / subject {o.get('错误', '')}",
              o.get("me", {}).get("subjects") == subs and o["me"].get("subject") == 1)
        check("切换：调 subject_switch、参数 subject=<id>（保持原类型）、成功后 reload",
              o.get("calls") == [["/s", {"action": "subject_switch", "form": {"subject": 2}}]]
              and o.get("reloaded") == 1 and o.get("notices") == [])
        o = run(me, {"error": "没有这个科目的权限"})
        check("后端返回 error：弹提示、不 reload、下拉退回当前科目",
              o.get("reloaded") == 0 and o.get("notices") == [["没有这个科目的权限", "no"]]
              and o.get("sel") == "1")
        o = run(me, "throw")
        check("请求抛异常：弹提示、不 reload、下拉退回", o.get("reloaded") == 0
              and len(o.get("notices", [])) == 1 and o.get("sel") == "1")
        o = run({"user": "u", "label": "小明"}, {"ok": True})
        check("auth_me 没有这两个键：subjects 为空数组、subject 为 null（nav 里 length>1 不成立，不渲染）",
              o.get("me", {}).get("subjects") == [] and o["me"].get("subject") is None)
        o = run(me, {"ok": True}, select_value="9")
        check("下拉值不在 subjects 里：什么都不调", o.get("calls") == [] and o.get("reloaded") == 0)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

print(f"\n通过 {passed}，失败 {failed}")
sys.exit(1 if failed else 0)
