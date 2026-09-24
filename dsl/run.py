# -*- coding: utf-8 -*-
"""干净的 DSL 环境：跑脚本、试动词、写测试，不牵扯日语教学那一套。

    py run.py scripts/hello.zs          用假客户端跑，不花额度
    py run.py scripts/hello.zs --real   走真实模型
    py run.py -e "打印 你好"             直接跑一行
    py run.py --verbs                   看有哪些动词
    py run.py --help-dsl                看语法

起 HTTP 服务器是另一个入口：py serve_http.py

跟主项目的关系：

    引擎（tools/dsl.py、tools/verbs.py）是共用的，不复制一份。
    两份引擎意味着语法改一处要改两边，行为不一致的 bug 极难查。

    不共用的是环境：这里自带假客户端，不读 config.json，工作目录是
    dsl/work/。想试语法、写新动词、跑回归，在这儿做不会污染教学那边
    的数据。

动词包用主项目的 verbs/——这个环境隔离的是数据，不是代码。没必要为了
试语法再养一套 common。
"""

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORK = HERE / "work"

# 往上找到含 tools/dsl.py 的目录，把它加进 path。
# 这样这个文件夹放在项目里哪一层都能跑。
for base in [HERE, *HERE.parents]:
    if (base / "tools" / "dsl.py").is_file():
        if str(base) not in sys.path:
            sys.path.insert(0, str(base))
        PROJECT = base
        break
else:
    print("找不到 tools/dsl.py。把这个目录放到项目里，或者指定 PYTHONPATH。")
    raise SystemExit(1)

from tools.dsl import DSLEngine, DSLError, to_text          # noqa: E402
from tools import packs                                      # noqa: E402

from client import make_client                               # noqa: E402

# 这个环境默认挂哪些包。脚本自己写「用包」会在这个基础上追加，
# 而且那样才有严格模式——写错的动词名会报错而不是当成文本。
PACKS = ["common", "data"]


def run_script(text: str, real: bool, verbose: bool, show_calls: bool) -> int:
    WORK.mkdir(exist_ok=True)
    client = make_client(real)

    engine = DSLEngine(
        client,
        workdir=WORK,
        verbose=verbose,
        verbs=packs.registry(PACKS, WORK),
        verbs_root=packs.verbs_root(),
    )
    try:
        out = engine.run(text)
    except DSLError as e:
        print(f"\n脚本出错：{e}")
        return 1
    except Exception as e:                      # 动词里抛的异常
        print(f"\n执行失败：{type(e).__name__}: {e}")
        return 1

    if not verbose and out:
        print(out)

    # 脚本用「返回」结束时，返回的东西不在 output 里——不显示的话
    # 看起来就像脚本什么都没干
    if engine.returned is not None:
        value, status = engine.returned
        body = (json.dumps(value, ensure_ascii=False, indent=2)
                if isinstance(value, (dict, list)) else to_text(value))
        print(f"\n--- 返回（状态码 {status}）---")
        print(body)

    if engine.verbs and engine.verbs.warnings:
        print("\n[动词加载警告]")
        for w in engine.verbs.warnings:
            print("  " + w)

    calls = getattr(client, "calls", [])
    if show_calls and calls:
        print(f"\n--- 模型调用 {len(calls)} 次 ---")
        for c in calls:
            prompt = (c.get("prompt") or "")[:70].replace("\n", " ")
            print(f"  {c['type']}: {prompt}")
    elif calls:
        print(f"\n[模型调用 {len(calls)} 次]")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="干净的 DSL 环境")
    p.add_argument("script", nargs="?", help="要跑的 .zs 文件")
    p.add_argument("-e", "--eval", help="直接跑一段脚本文本")
    p.add_argument("--real", action="store_true",
                   help="走真实模型（默认用假客户端，不花额度）")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="边跑边打印，看得到执行顺序")
    p.add_argument("--calls", action="store_true", help="列出每次模型调用的提示词")
    p.add_argument("--verbs", action="store_true", help="列出已加载的动词")
    p.add_argument("--help-dsl", action="store_true", help="打印 DSL 语法说明")
    args = p.parse_args()

    if args.help_dsl:
        from tools import dsl
        print(dsl.__doc__)
        return 0

    if args.verbs:
        WORK.mkdir(exist_ok=True)
        print(packs.describe(workspace=WORK))
        return 0

    if args.eval:
        return run_script(args.eval, args.real, args.verbose, args.calls)

    if args.script:
        path = Path(args.script)
        if not path.is_absolute():
            # 相对路径先按当前目录找，再按 scripts/ 找——多数时候想跑的
            # 就是 scripts/ 里那几个
            for cand in (Path.cwd() / path, HERE / path, HERE / "scripts" / path):
                if cand.is_file():
                    path = cand
                    break
        if not path.is_file():
            print(f"找不到脚本：{args.script}")
            return 1
        return run_script(path.read_text(encoding="utf-8"),
                          args.real, args.verbose, args.calls)

    p.print_help()
    print("\n示例脚本：")
    for f in sorted((HERE / "scripts").glob("*.zs")):
        first = next((l.strip().lstrip("#").strip()
                      for l in f.read_text(encoding="utf-8").splitlines()
                      if l.strip().startswith("#")), "")
        print(f"  {f.name:20} {first}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
