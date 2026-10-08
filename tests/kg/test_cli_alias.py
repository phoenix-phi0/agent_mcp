# -*- coding: utf-8 -*-
"""kg 命令行的英文别名：中文写法和英文写法等价。

    cd /home/ysc/mcp && .venv/bin/python tests/kg/test_cli_alias.py

  一、解析：每个子命令、每个选项，中文和英文写法解析到同一个处理函数、同一组
      参数（参数里统一是中文正名）；--x=值 和分开写一样；选项的值不被当选项换
  二、起服务那条路：中英文写法交给 gen run 的参数一模一样；app.pyw 用的
      parse_login 也认 --login / --secure-cookie
  三、帮助：py -m kg --help 和各子命令 --help 两种写法都列出来，不建库不起服务
  四、实测：临时库里用英文写法 create-teacher / passwd / merge（密码走环境变量），
      不碰 kg/app.db
"""

import io
import os
import secrets
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import kg.__main__ as kgmain                                        # noqa: E402
from tests.kg.helpers import make_ws                                # noqa: E402
from tools.auth import verify_password                              # noqa: E402

PY = str(ROOT / ".venv" / "bin" / "python")
passed = failed = 0


def check(ok, msg):
    global passed, failed
    if ok:
        passed += 1
        print(f"  ✓ {msg}")
    else:
        failed += 1
        print(f"  ✗ {msg}")


def kg_cli(*args, env=None):
    e = dict(os.environ)
    e.update(env or {})
    r = subprocess.run([PY, "-m", "kg", *args], cwd=ROOT, env=e,
                       capture_output=True, text=True, timeout=60)
    return r.returncode, r.stdout + r.stderr


def en(argv):
    """把一条中文命令行逐个换成英文别名（测试里造英文写法用）。"""
    table = {**kgmain.COMMANDS, **kgmain.OPTIONS}
    return [table.get(a, a) for a in argv]


def main():
    print("一、解析")
    cases = [
        ["建教师", "t1"],
        ["建教师", "t1", "--显示名", "王老师", "--密码环境变量", "PW", "--库", "/x/a.db"],
        ["改密", "t1"],
        ["改密", "t1", "--密码环境变量", "PW", "--库", "/x/a.db"],
        ["并入", "me", "s1"],
        ["并入", "me", "s1", "--库", "/x/a.db"],
        ["setup"],
        ["import"],
        [],
        ["--登录", "--安全cookie", "--不开浏览器", "--标题", "T", "--入口", "首页",
         "--port", "8200", "--host", "127.0.0.1", "--mock"],
    ]
    for zh in cases:
        z, e = kgmain.parse(zh), kgmain.parse(en(zh))
        check(z == e and z[1] == zh[1:] if zh and not zh[0].startswith("-") else z == e,
              f"{' '.join(zh) or '（空）'}  ≡  {' '.join(en(zh)) or '（空）'} → {z[0].__name__}")
    for zh, want in (("建教师", kgmain.make_teacher), ("改密", kgmain.change_password),
                     ("并入", kgmain.merge_me)):
        check(kgmain.parse([zh, "u"])[0] is want and kgmain.parse([kgmain.COMMANDS[zh], "u"])[0] is want,
              f"{zh} / {kgmain.COMMANDS[zh]} → {want.__name__}")
    check(kgmain.parse([])[0] is kgmain.serve and kgmain.parse(["--login"])[0] is kgmain.serve,
          "不写子命令 → serve")
    # 每个选项都覆盖到
    seen = {a for c in cases for a in c if a.startswith("--")}
    check(set(kgmain.OPTIONS) <= seen, "对照表里每个选项都在上面测过")

    check(kgmain.parse(["create-teacher", "t1", "--db=/x/a.db", "--display-name=王"])
          == (kgmain.make_teacher, ["t1", "--库", "/x/a.db", "--显示名", "王"]),
          "--db=x 和 --db x 一样（拆开、换成中文）")
    check(kgmain.parse(["--标题=T"])[1] == ["--标题", "T"], "--标题=T 也拆开")
    check(kgmain.parse(["--title", "--db", "--port", "8200"])[1] == ["--标题", "--db", "--port", "8200"],
          "选项的值原样：--title --db 里的 --db 是标题，不换")
    check(kgmain.parse(["passwd", "merge"])[1] == ["merge"] and kgmain.parse(["并入", "me", "passwd"])[1] == ["me", "passwd"],
          "子命令只认开头那个：用户名叫 merge / passwd 不被换")
    check(kgmain.parse(["改密", "u", "--help"]) == (kgmain.show_help, ["改密"])
          and kgmain.parse(["passwd", "-h"]) == (kgmain.show_help, ["改密"]),
          "改密 --help / passwd -h → 同一份帮助")

    print("二、起服务那条路")
    import gen.project
    got = []
    old_main, old_setup = gen.project.main, kgmain.setup
    gen.project.main = lambda argv: got.append(argv) or 0
    kgmain.setup = lambda quiet=False: 0
    try:
        zh = ["--登录", "--安全cookie", "--不开浏览器", "--标题", "T", "--入口", "首页", "--port", "8200", "--mock"]
        for argv in (zh, en(zh)):
            with redirect_stdout(io.StringIO()):
                kgmain.main(argv)
        check(len(got) == 2 and got[0] == got[1], f"中英文交给 gen run 的参数一样：{got[0][2:]}")
        check("--登录" in got[0] and "--不开浏览器" in got[0] and "--real" not in got[0],
              "gen run 收到的是中文正名（gen 那边只认中文）")
        got.clear()
        with redirect_stdout(io.StringIO()):
            kgmain.main(["--title=别的"])
        check(got[0].count("--标题") == 1 and got[0][-1] == "别的", "--title=别的 不再补默认标题")
    finally:
        gen.project.main, kgmain.setup = old_main, old_setup
    for zh in (["--登录"], ["--安全cookie"], ["--登录", "--安全cookie", "--port", "1"]):
        check(kgmain.parse_login(zh, {}) == kgmain.parse_login(en(zh), {}),
              f"parse_login {zh} ≡ {en(zh)}")

    print("三、帮助")
    db = ROOT / "kg" / "app.db"
    before = db.stat().st_mtime if db.exists() else None
    code, out = kg_cli("--help")
    check(code == 0 and all(f"{z} / {e}" in out for z, e in {**kgmain.COMMANDS, **kgmain.OPTIONS}.items()
                            if z not in ("--显示名", "--库", "--密码环境变量")),
          "py -m kg --help：子命令和起服务的选项都是「中文 / 英文」")
    for zh, en_ in kgmain.COMMANDS.items():
        c1, o1 = kg_cli(zh, "--help")
        c2, o2 = kg_cli(en_, "-h")
        check(c1 == c2 == 0 and o1 == o2 and f"{zh} " in o1 and f"{en_} " in o1 and "--库 / --db" in o1,
              f"{zh} --help ≡ {en_} -h，两种写法都在")
    check((db.stat().st_mtime if db.exists() else None) == before, "看帮助没动 kg/app.db")

    print("四、临时库实测英文写法")
    ws = make_ws(Path(tempfile.mkdtemp(prefix="cli_alias_")), with_content=False)
    tmpdb = ws / "app.db"
    pw1, pw2 = secrets.token_urlsafe(12), secrets.token_urlsafe(12)
    env = {"KG_ALIAS_PW": pw1}
    code, out = kg_cli("create-teacher", "t_en", "--display-name", "英文老师",
                       "--password-env", "KG_ALIAS_PW", "--db", str(tmpdb), env=env)
    con = sqlite3.connect(tmpdb)
    row = con.execute("SELECT password_hash, display_name, role FROM user WHERE username='t_en'").fetchone()
    check(code == 0 and row and row[1] == "英文老师" and row[2] == "teacher" and verify_password(pw1, row[0]),
          "create-teacher --display-name --password-env --db：建好、显示名对、密码对")
    code, out = kg_cli("create-teacher", "t_en", "--password-env", "KG_ALIAS_PW", f"--db={tmpdb}", env=env)
    check(code == 1 and "已经有了" in out, "再建一次（--db=路径 写法）：重名拒绝")
    code, out = kg_cli("passwd", "t_en", "--password-env", "KG_ALIAS_PW", "--db", str(tmpdb),
                       env={"KG_ALIAS_PW": pw2})
    row = con.execute("SELECT password_hash FROM user WHERE username='t_en'").fetchone()
    check(code == 0 and verify_password(pw2, row[0]) and not verify_password(pw1, row[0]),
          "passwd --password-env --db：新密码能用、旧的不行")
    code, out = kg_cli("passwd", "nobody", "--password-env", "KG_ALIAS_PW", "--db", str(tmpdb), env=env)
    check(code == 1 and "没有 nobody" in out, "passwd 不存在的账号：拒绝")
    con.execute("CREATE TABLE alias_note(learner TEXT, body TEXT)")
    con.executemany("INSERT INTO alias_note VALUES (?, ?)", [("me", "a"), ("me", "b")])
    con.commit()
    code, out = kg_cli("merge", "me", "t_en", "--db", str(tmpdb))
    n = con.execute("SELECT count(*) FROM alias_note WHERE learner='t_en'").fetchone()[0]
    check(code == 0 and n == 2 and list(ws.glob("app.db.merge_*.bak")), "merge me t_en --db：记录归过去、先备份")
    code, out = kg_cli("merge", "me", "t_en", "--db", str(tmpdb))
    check(code == 0 and "没有学习记录" in out, "再 merge 一次：me 没东西了")
    con.close()
    check(pw1 not in out and pw2 not in out, "输出里没有密码")
    check((db.stat().st_mtime if db.exists() else None) == before, "全程没动 kg/app.db")

    print(f"\n{'=' * 50}\n通过 {passed}，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
