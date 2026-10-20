"""核对一个明文密码是不是和存的哈希对得上（tools/auth.py 的 verify_password：hmac.compare_digest
比较，不按字节短路）。返回 是/否。业务层自己校验密码（比如自定义登录流程、改密码前核对旧密码）时用。

例如 核对密码 {old_password} {行.password_hash}
"""
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 核对密码(明文: str, 哈希: str) -> bool:
    from tools.auth import verify_password

    return verify_password(明文, 哈希)
