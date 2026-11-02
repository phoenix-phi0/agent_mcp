#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""kg_v4 一次性导入：rows_json 数组 → 内部公开函数「写入系列课文并重灌」。

K186。旧 /lesson/import 只收竖线格式，多行代码装不下；本脚本不改任何服务代码：
进程内 gen.project.make_app 拿路由器（不登录模式，同 init_data.py 的前提），
手工构造 Endpoint（src=routes/lesson.zs，svc_module=lesson），router.run 调
lesson.写入系列课文并重灌（contracts/lesson.md「写入系列课文并重灌」，服务实现
services/lesson.zs）。auth_mode=off 时显式 subject 才落到该科目，须传 --subject。

用法（解释器用仓库 .venv）：
  .venv/bin/python kg_v4/setup/import_lesson_rows.py 项目目录 rows_json文件
      --subject 2 --series-code python.core_v1 --series-name "Python 从零入门"
      [--intro ...] [--source ...] [--license ...] [--sort-order 100]

--intro：「写入系列课文并重灌」不接收简介（竖线版 /lesson/import 才有）；
  全部课导入成功（无拒收）后才按 code+subject_id 一条 UPDATE 补上（纯展示字段）。
--sort-order：新系列该函数固定 sort_order=100，本参数不生效，只核对并提示。
--yes：目标是正式数据目录（kg_v4_data）时的确认开关；缺省拒绝，防止误灌正式库。

出参：打印 total/imported/file_rows/rejected/item_links/point_links；
接口失败或 rejected 非空退出码 1，参数/路径错误退出码 2，否则 0。
"""
import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve()


def _find_repo():
    """引擎仓库根（有 gen/project.py 的那层），同 init_data.py 的找法。"""
    for start in (HERE.parent, Path.cwd().resolve()):
        for d in (start, *start.parents):
            if (d / "gen" / "project.py").is_file():
                return d
    sys.exit("找不到引擎仓库（要有 gen/project.py）：请在仓库根目录下执行")


REPO = _find_repo()
sys.path.insert(0, str(REPO))


def main(argv=None):
    ap = argparse.ArgumentParser(description="kg_v4 rows_json 课文导入（写入系列课文并重灌）")
    ap.add_argument("project", help="项目/数据目录（含 routes/ services/ app.db）")
    ap.add_argument("rows_file", help="rows JSON 文件（非空 JSON 数组，一课一字段："
                                      "code/level/title/summary/explain/connection/examples/"
                                      "examples_edited/orig_title/seq/item_codes/point_codes）")
    ap.add_argument("--subject", required=True, help="科目编号（如 2）")
    ap.add_argument("--series-code", required=True, help="系列号（如 python.core_v1）")
    ap.add_argument("--series-name", default="", help="系列名（缺省用系列号）")
    ap.add_argument("--intro", default="", help="系列简介（函数不收，导入成功后单独补写）")
    ap.add_argument("--source", default="", help="来源")
    ap.add_argument("--license", default="", help="许可")
    ap.add_argument("--sort-order", default="", help="排序（新系列固定 100，不生效，仅提示）")
    ap.add_argument("--yes", action="store_true", help="确认对正式数据目录（kg_v4_data）执行；缺省拒绝")
    a = ap.parse_args(argv)

    root = Path(a.project).resolve()
    if not (root / "routes").is_dir() or not (root / "services").is_dir():
        print(f"不是项目目录（缺 routes/ services/）：{root}"); return 2
    if not (root / "app.db").is_file():
        print(f"缺 app.db：{root}"); return 2
    rows_path = Path(a.rows_file)
    if not rows_path.is_file():
        print(f"rows 文件不存在：{rows_path}"); return 2
    try:
        rows = json.loads(rows_path.read_text(encoding="utf-8"))
    except ValueError as e:
        print(f"rows 文件不是合法 JSON：{e}"); return 2
    if not isinstance(rows, list) or not rows:
        print("rows 文件要是非空 JSON 数组"); return 2
    if not str(a.subject).isdigit():
        print("--subject 要是数字"); return 2
    if root.name == "kg_v4_data" and not a.yes:
        print(f"{root} 像正式数据目录；要灌正式库请显式加 --yes"); return 2
    if a.sort_order and a.sort_order != "100":
        print(f"提示：「写入系列课文并重灌」对新系列固定 sort_order=100，"
              f"--sort-order {a.sort_order} 不生效")

    from gen.project import make_app
    from tools.dsl_http import Endpoint

    app, router = make_app(root, real=False, login=False)
    call_line = (
        "设 r = 调用 lesson.写入系列课文并重灌"
        " series_code={series_code} rows_json={rows_json}"
        " series_name={series_name 或} source={source 或} license={license 或}"
        " learner={learner 或} current_role={current_role 或} auth_mode={auth_mode 或}"
        " subject={subject 或}"
    )
    ep = Endpoint("POST", "/setup/import-lesson-rows",
                  [call_line, "返回 {r}"],
                  src=root / "routes" / "lesson.zs", line=1)
    form = {
        "subject": a.subject,
        "series_code": a.series_code,
        "rows_json": json.dumps(rows, ensure_ascii=False),
        "series_name": a.series_name,
        "source": a.source,
        "license": a.license,
    }
    t0 = time.time()
    body_text, status, _auth = router.run(ep, form, user="")
    print(f"调用 lesson.写入系列课文并重灌 subject={a.subject} "
          f"series={a.series_code} -> {status}（{time.time() - t0:.1f}s）")
    if status != 200:
        print(str(body_text)[:400])
        return 1
    if isinstance(body_text, str):
        try:
            resp = json.loads(body_text)
        except ValueError:
            print("响应不是 JSON：", body_text[:200]); return 1
    else:
        resp = body_text  # router.run 直接回 dict
    r = resp.get("r") if isinstance(resp, dict) and isinstance(resp.get("r"), dict) else resp
    if not isinstance(r, dict):
        print("响应结构不对：", body_text[:200]); return 1
    for k in ("total", "imported", "file_rows", "item_links", "point_links"):
        print(f"{k}={r.get(k)}")
    rejected = r.get("rejected") or []
    print("rejected=" + json.dumps(rejected, ensure_ascii=False))
    if rejected:
        print("有拒收，按失败处理（不补写 intro）")
        return 1

    if a.intro:
        con = sqlite3.connect(root / "app.db")
        try:
            cur = con.execute(
                "UPDATE lesson_series SET intro=? WHERE code=? AND subject_id=?",
                (a.intro, a.series_code, int(a.subject)))
            con.commit()
            n = cur.rowcount
        finally:
            con.close()
        print(f"intro 补写（函数不收简介，函数外补展示字段）：更新 {n} 行")
        if n == 0:
            print("intro 补写没命中任何系列行")
            return 1
    print("完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
