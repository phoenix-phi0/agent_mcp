"""这个用户名（和这次请求的来源地址）是不是因为连续登录失败被锁住了（tools/auth.py 的 LIMITER，
同一用户名或同一来源连续失败 5 次锁 5 分钟）。自定义登录流程（不走 auth 包现成的 登录 动词）在
真的核对密码之前先问一句，锁住了就不用再查库、算哈希。返回 是/否。

    如果 登录被锁 {username} 等于 是
      报错 429 登录失败次数太多，请 5 分钟后再试
    结束

例如 登录被锁 {username}
"""
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def _keys(用户名: str) -> list:
    from tools.http_ctx import current_remote

    name = (用户名 or "").strip().lower()
    keys = [(str(WORKSPACE), "name", name)]
    remote = current_remote()
    if remote:
        keys.append((str(WORKSPACE), "remote", remote))
    return keys


def 登录被锁(用户名: str) -> str:
    from tools.auth import LIMITER

    return "是" if LIMITER.locked(_keys(用户名)) else "否"
