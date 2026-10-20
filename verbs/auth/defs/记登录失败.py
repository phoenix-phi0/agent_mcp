"""记一次登录失败（用户名 + 这次请求的来源地址各计一次连续失败；tools/auth.py 的 LIMITER，连续失败
5 次锁 5 分钟）。自定义登录流程核对密码不对时调，跟 登录被锁 / 清登录失败 配套用。返回 ok。

例如 记登录失败 {username}
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


def 记登录失败(用户名: str) -> str:
    from tools.auth import LIMITER

    LIMITER.fail(_keys(用户名))
    return "ok"
