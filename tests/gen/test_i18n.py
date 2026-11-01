# -*- coding: utf-8 -*-
"""界面多语言（K180）：gen/project.py 的 i18n_of、build 的 i18n.<lang>.js。

    cd 仓库根 && .venv/bin/python tests/gen/test_i18n.py

一、i18n_of：没有 i18n/ 目录返回 {}；正常 tsv（# 注释、空行、同键同译文重复）；
    一列的坏行、键或译文为空、同名键译文不同、文件名不是小写代号 → ProjectError
二、无 i18n 逐字节不变：kg、kg_v4（去 i18n 副本）走 build、app2 的 main/startup
    走 compile_ui，逐文件 sha256 对照 i18n_golden_sha.txt——i18n 机制必须全包在
    「项目里有 i18n/ 才走」的分支里，别的项目生成物一个字节都不能动
三、带 i18n 的产物（kg_v4 去 i18n 副本 + 迷你 ja.tsv）：i18n.ja.js、日志行、
    两页 script 标签、app.js/teacher.js 的 tmsg/tdom/switchLang/MutationObserver、
    顶栏「中文 / 日本語」切换、css 日文字体
四、顶栏切换的三重条件：kg 副本 + 迷你 ja.tsv（没有 /account/lang 接口）：
    i18n.ja.js 照生成、tmsg 照在、顶栏切换按钮不出——不能炸
"""

import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from gen.project import ProjectError, build, i18n_of      # noqa: E402
from tools.entity import field_table, parse as ent_parse  # noqa: E402
from tools.ui import compile_ui, parse                    # noqa: E402

passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("  ✓ " if ok else "  ✗ ") + msg)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# 迷你词表：注释、空行、同键同译文重复行都要能过；键序跟文件行序一致
MINI_TSV = ("# 迷你词表（测试用；真词表在 kg_v4/i18n/ja.tsv）\n"
            "\n"
            "登录\tログイン\n"
            "用户名\tユーザー名\n"
            "密码\tパスワード\n"
            "退出登录\tログアウト\n"
            "退出登录\tログアウト\n")

MINI_DICT = {"登录": "ログイン", "用户名": "ユーザー名",
             "密码": "パスワード", "退出登录": "ログアウト"}


def write_tsv(root: Path, text: str, name: str = "ja.tsv"):
    d = root / "i18n"
    d.mkdir(exist_ok=True)
    (d / name).write_text(text, encoding="utf-8")


def proj_copy(tmp: Path, name: str, src: str) -> Path:
    proj = tmp / name
    proj.mkdir()
    for d in ("ui", "routes", "entities", "queries"):
        shutil.copytree(ROOT / src / d, proj / d)
    assert not (proj / "i18n").exists(), "拷的四个目录不该带出 i18n/"
    return proj


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="test_i18n_"))
    try:
        print("一、i18n_of")
        check(i18n_of(tmp / "nope") == {}, "没有 i18n/ 目录：返回 {}")
        p = tmp / "ok"
        p.mkdir()
        write_tsv(p, MINI_TSV)
        check(i18n_of(p) == {"ja": MINI_DICT},
              f"注释、空行跳过，同键同译文重复行没事：{list(i18n_of(p))}")
        pn = tmp / "only_notes"
        pn.mkdir()
        write_tsv(pn, "# 只有注释\n\n")
        check(i18n_of(pn) == {}, "全注释的 tsv：等于没开")

        def bad(text, name="ja.tsv"):
            d = tmp / "bad"
            if (d / "i18n").is_dir():
                shutil.rmtree(d / "i18n")
            d.mkdir(exist_ok=True)
            write_tsv(d, text, name)
            try:
                i18n_of(d)
                return ""
            except ProjectError as e:
                return str(e)

        e = bad("登录\n")
        check("第 1 行" in e and "两列" in e, f"一列的坏行：{e}")
        e = bad("登录\t\n")
        check("两列" in e, f"译文为空：{e}")
        e = bad("登录\tログイン\n登录\tラログイン\n")
        check("「登录」的译文跟前面不一样" in e, f"同名键不同译文：{e}")
        e = bad("登录\tログイン\n", name="JA.tsv")
        check("小写语言代号" in e, f"文件名大写：{e}")

        print("二、无 i18n 逐字节不变")
        golden = {}
        gl = Path(__file__).parent / "i18n_golden_sha.txt"
        for line in gl.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            name, _, h = line.partition(": ")
            golden[name.strip()] = h.strip()
        got = {}
        for src in ("kg", "kg_v4"):
            # 目录名与源同名：build 不传 title 时标题取目录名，要进 <title>
            proj = proj_copy(tmp, src, src)
            build(proj)
            n_i18n = sorted(f.name for f in (proj / "web").glob("i18n.*"))
            check(not n_i18n, f"{src} 副本没有 i18n.*.js：{n_i18n}")
            for f in sorted((proj / "web").rglob("*")):
                if f.is_file() and f.name != "vue.global.prod.js":
                    got[f"{src}/{f.relative_to(proj / 'web')}"] = sha(f.read_bytes())
        a2 = ROOT / "app2"
        ents = ent_parse((a2 / "ui" / "表单.entity").read_text(encoding="utf-8"))
        fields = field_table(ents)
        for uiname, title in (("main.ui", "agent"), ("startup.ui", "startup")):
            screens = parse((a2 / "ui" / uiname).read_text(encoding="utf-8"))
            r = compile_ui(screens, backend="vue", fields=fields, require_bind=True,
                           options={"title": title, "options_map": {},
                                    "endpoints": {}})
            for fn, text in sorted(r["result"]["files"].items()):
                got[f"app2ui/{uiname}/{fn}"] = sha(text.encode("utf-8"))
        diff = {k: (golden.get(k), v) for k, v in got.items() if golden.get(k) != v}
        extra = [k for k in golden if k not in got]
        check(not diff and not extra,
              f"无 i18n 生成物逐字节一致（{len(golden) - len(diff)} 份）"
              + (f"；不同：{sorted(diff)}；golden 有而没生成：{extra}"
                 if diff or extra else ""))

        print("三、带 i18n 的产物")
        proj = proj_copy(tmp, "kgv4_ja", "kg_v4")
        write_tsv(proj, MINI_TSV)
        lines = build(proj)
        web = proj / "web"
        check((web / "i18n.ja.js").read_text(encoding="utf-8")
              == 'window.I18N=window.I18N||{};window.I18N["ja"]='
              + json.dumps(MINI_DICT, ensure_ascii=False) + ";\n",
              "i18n.ja.js：window.I18N[\"ja\"]=…（按语言分键，多语言不互覆）")
        check(any("界面多语言 ja：4 条 → web/i18n.ja.js" in x for x in lines),
              f"日志行：{[x for x in lines if '多语言' in x]}")
        for html in ("index.html", "teacher.html"):
            t = (web / html).read_text(encoding="utf-8")
            check('<script src="./i18n.ja.js"></script>' in t, f"{html} 引 i18n.ja.js")
        for js in ("app.js", "teacher.js"):
            t = (web / js).read_text(encoding="utf-8")
            check(all(s in t for s in ("zs_i18n", "function tmsg(", "function tdom(",
                                       "function switchLang(", "MutationObserver",
                                       'class="nav-lang"', "switchLang('ja')")),
                  f"{js}：tmsg/tdom/switchLang/Observer/顶栏切换")
        for css in ("style.css", "teacher.css"):
            t = (web / css).read_text(encoding="utf-8")
            check('html[lang="ja"]' in t and ".nav-lang" in t,
                  f"{css}：日文字体栈 + 切换按钮样式")

        print("四、顶栏切换的三重条件")
        proj = proj_copy(tmp, "kg_ja", "kg")
        write_tsv(proj, MINI_TSV)
        build(proj)
        t = (proj / "web" / "app.js").read_text(encoding="utf-8")
        check((proj / "web" / "i18n.ja.js").is_file() and "function tmsg(" in t,
              "kg + 词典：i18n.ja.js 和 tmsg 照生成")
        check("nav-lang" not in t and "switchLang('ja')" not in t,
              "没有 /account/lang 接口：顶栏切换按钮不出")
        check('<script src="./i18n.ja.js"></script>'
              in (proj / "web" / "index.html").read_text(encoding="utf-8"),
              "index.html 照样引词典")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
