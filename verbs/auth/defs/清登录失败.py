"""登录成功后清掉这个用户名（和来源地址）的连续失败计数（tools/auth.py 的 LIMITER）。
自定义登录流程核对密码通过之后调，跟 登录被锁 / 记登录失败 配套用。返回 ok。

例如 清登录失败 {username}
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


def 清登录失败(用户名: str) -> str:
    from tools.auth import LIMITER

    LIMITER.ok(_keys(用户名))
    return "ok"
