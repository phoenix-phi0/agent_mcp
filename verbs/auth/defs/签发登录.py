"""要求路由器给这个用户名签发登录 cookie（跟 auth 包的 登录 / 注册用户 动词最后一步一样，
走 tools/http_ctx.request_auth；cookie 本身——签名密钥、HttpOnly/SameSite——由路由器统一设，
动词这里只提出「登录成功了」这个要求）。自定义登录流程（核对密码、查限流都自己写）核对通过后
调这一个动词收尾。不在请求里（比如跑用例、接口冒烟直接调用业务函数）时安静地什么也不做。

例如 签发登录 {username}
"""
from pathlib import Path

WORKSPACE = Path(".")
PACK_DIR = Path(".")


def 签发登录(用户名: str) -> str:
    from tools.http_ctx import request_auth

    request_auth({"login": 用户名})
    return "ok"
