# -*- coding: utf-8 -*-
"""认证原语：签名令牌、密码哈希。只用标准库。

路由器用它从 cookie 认人，auth 动词包用它哈希和核对密码。

## 令牌

    base64url({"u": 用户名, "e": 过期时间}) + "." + base64url(HMAC-SHA256)

放在 HttpOnly cookie 里。服务器不存令牌——签名对、没过期就认。代价是
退出登录只能删 cookie，偷走的令牌在过期前一直有效；本机单机用够了，
要能吊销得改成服务器端存会话表。

密钥每个项目一个，第一次用时生成在 `<项目>/.auth_secret`，只有属主能读。
删掉它等于让所有人的登录失效。

## 密码

scrypt（标准库 hashlib），存成 `scrypt$n$r$p$盐$哈希`。参数写进串里，
以后调强度不影响旧密码。核对用 hmac.compare_digest，不按字节短路比较。

## 登录限流

同一个用户名、或同一个来源地址，连续失败 5 次就锁 5 分钟（LIMIT_FAILS、
LIMIT_SECONDS）。计数在内存里，重启就清；多进程部署各算各的。用户名不管
存不存在都计数、锁住时回同一句话，看不出哪个名字是真的。成功一次清掉
这个用户名和这个来源的计数。按来源计数的代价：一个教室共用一个出口地址
时，五次输错会把整间教室锁 5 分钟。
"""

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from pathlib import Path

COOKIE = "zs_auth"
# 用户名不许有空格：它会被当成 {current_user} 传进「查询 … current_user={current_user}」
# 这类按空格切的动词参数里。auth 包的注册、建号和 kg 的命令行建教师共用
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.@\-\u4e00-\u9fff]{1,40}$")
MIN_PASSWORD = 6
TTL = 7 * 24 * 3600            # 令牌有效期：一周
SECRET_FILE = ".auth_secret"

# scrypt 参数。n=2^14 在普通机器上一次大约几十毫秒：对登录无感，对暴力
# 猜测是实打实的成本。
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 14, 8, 1


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


# ----------------------------------------------------------------------
# 密钥
# ----------------------------------------------------------------------


def secret_for(workspace) -> bytes:
    """项目的签名密钥。没有就生成一个，只给属主读写。"""
    p = Path(workspace) / SECRET_FILE
    if p.is_file():
        return bytes.fromhex(p.read_text(encoding="utf-8").strip())
    key = secrets.token_bytes(32)
    p.write_text(key.hex(), encoding="utf-8")
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass                    # Windows 上 chmod 基本无效，不为这个报错
    return key


# ----------------------------------------------------------------------
# 令牌
# ----------------------------------------------------------------------


def make_token(user: str, key: bytes, ttl: int = TTL) -> str:
    payload = _b64(json.dumps({"u": user, "e": int(time.time()) + ttl},
                              ensure_ascii=False).encode())
    sig = _b64(hmac.new(key, payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def read_token(token, key: bytes) -> str:
    """令牌有效就返回用户名，否则返回空串。

    任何毛病都只返回空串、不抛：格式坏了、签名不对、过期了，对调用方都是
    「没登录」，没必要区分——区分了反而是在告诉伪造者差在哪一步。
    """
    if not token or "." not in token:
        return ""
    payload, sig = token.rsplit(".", 1)
    want = _b64(hmac.new(key, payload.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, want):
        return ""
    try:
        data = json.loads(_unb64(payload))
    except (ValueError, json.JSONDecodeError):
        return ""
    if not isinstance(data, dict) or int(data.get("e", 0)) < time.time():
        return ""
    user = data.get("u")
    return user if isinstance(user, str) else ""


# ----------------------------------------------------------------------
# 密码
# ----------------------------------------------------------------------


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N,
                            r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, digest = stored.split("$")
        if algo != "scrypt":
            return False
        got = hashlib.scrypt(password.encode(), salt=_unb64(salt), n=int(n),
                             r=int(r), p=int(p), dklen=len(_unb64(digest)))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(got, _unb64(digest))


# 用户不存在时也算一次哈希再比较，让「没这个人」和「密码错」花的时间差
# 不多——不然量一下响应时间就能枚举出哪些用户名存在。
_DUMMY = None


def dummy_verify(password: str) -> None:
    global _DUMMY
    if _DUMMY is None:
        _DUMMY = hash_password(secrets.token_hex(8))
    verify_password(password, _DUMMY)


# ----------------------------------------------------------------------
# 登录限流
# ----------------------------------------------------------------------

LIMIT_FAILS = 5                # 连续失败几次锁住
LIMIT_SECONDS = 5 * 60         # 锁多久


class LoginLimiter:
    """按键（用户名、来源地址）记连续失败。内存里，线程安全。

    键带上项目目录：同一个进程里起了几个项目（测试就是这样）互不牵连。
    """

    def __init__(self, fails: int = LIMIT_FAILS, seconds: int = LIMIT_SECONDS):
        self.fails = fails
        self.seconds = seconds
        self._lock = threading.Lock()
        self._data = {}         # 键 -> [连续失败次数, 锁到什么时候]

    def locked(self, keys, now: float = None) -> bool:
        now = time.time() if now is None else now
        with self._lock:
            for k in keys:
                rec = self._data.get(k)
                if rec and rec[1] > now:
                    return True
        return False

    def fail(self, keys, now: float = None) -> None:
        now = time.time() if now is None else now
        with self._lock:
            for k in keys:
                rec = self._data.setdefault(k, [0, 0.0])
                if rec[1] and rec[1] <= now:
                    rec[0], rec[1] = 0, 0.0      # 锁过期了，重新数
                rec[0] += 1
                if rec[0] >= self.fails:
                    rec[1] = now + self.seconds

    def ok(self, keys) -> None:
        with self._lock:
            for k in keys:
                self._data.pop(k, None)

    def reset(self) -> None:
        with self._lock:
            self._data.clear()


LIMITER = LoginLimiter()
