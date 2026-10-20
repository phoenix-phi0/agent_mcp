"""把明文密码算成可以存进库里的哈希串（scrypt，tools/auth.py 的算法，同一套参数、同一个格式
`scrypt$n$r$p$盐$哈希`）。业务层自己造账号（不走 auth 包现成的 建用户 / 注册用户）时用，比如按名单批量
建学生号、或者一个模块要自己管一张带密码的表。

    设 哈希 = 哈希密码 {password}
    设 n = 写库 app.db xxx_user_insert username={username} password_hash={哈希}

例如 哈希密码 {password}
"""
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 哈希密码(明文: str) -> str:
    from tools.auth import hash_password

    return hash_password(明文)
