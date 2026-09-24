# -*- coding: utf-8 -*-
"""在干净环境里起一个真的 HTTP 服务器。

    pip install flask
    py serve_http.py                跑起来，端口看 routes/ 里的「服务」声明
    py serve_http.py --port 9000    精确指定，不做自动查找
    py serve_http.py --list         只看有哪些接口

跟主项目的 `py -m tools.dsl_http` 的区别：

    路由     dsl/routes/ 而不是 mcp/routes/
    工作目录 dsl/work/ 而不是项目根——脚本读写文件都限制在这里面
    会话     dsl/work/sessions/

引擎和动词包仍然共用主项目的。这个环境隔离的是**数据**，不是代码：
试接口不该弄脏教学那边的 sessions，但没必要为此再养一套动词。

跑起来之后另开一个窗口：

    curl -X POST localhost:8091/hello -H "Content-Type: application/json" -d "{\\"name\\":\\"世界\\"}"
    curl -X POST localhost:8091/count -H "Content-Type: application/json" -d "{\\"learner\\":\\"a\\"}"

/count 连发几次能看到计数在涨——那验证的是会话真的存住了。
"""

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

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

from tools.dsl import DSLError                          # noqa: E402
from tools.dsl_http import Router, resolve_port         # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="干净环境的 HTTP 服务器")
    p.add_argument("--host", default="127.0.0.1")
    # 默认 None：要能区分「用户显式给了」和「没给」，才能让脚本里的
    # 「服务」声明在没给时生效
    p.add_argument("--port", type=int, default=None,
                   help="精确指定端口，不做自动查找")
    p.add_argument("--real", action="store_true",
                   help="走真实模型。默认假客户端，不消耗额度")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="把脚本的执行过程打到控制台")
    p.add_argument("--list", action="store_true", help="只列接口，不启动")
    args = p.parse_args()

    work = HERE / "work"
    work.mkdir(exist_ok=True)

    try:
        router = Router(HERE / "routes", work, work / "sessions",
                        real=args.real, verbose=args.verbose)
    except DSLError as e:
        print(f"路由加载失败：{e}")
        return 1

    print(router.describe())
    if args.list:
        return 0
    if not router.table:
        print(f"\n{HERE / 'routes'} 下没有接口块，先写一个 .zs")
        return 1

    try:
        app = router.app()
    except ImportError:
        print("\n缺 flask：pip install flask")
        return 1

    port, 来源 = resolve_port(args.host, args.port, router.ports)
    if port is None:
        print(f"\n{来源}")
        return 1

    print(f"\n监听 http://{args.host}:{port}（{来源}）"
          + ("" if args.real else "，假客户端，模型调用返回固定内容"))
    print("按 Ctrl+C 停止\n")
    # threaded=True 是重点：模型调用要等几秒，单线程的话第二个请求只能
    # 干等。debug 关掉——自动重载会把路由表读两遍。
    app.run(host=args.host, port=port, threaded=True, debug=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
