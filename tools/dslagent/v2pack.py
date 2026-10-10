"""旧路径兼容：资料包 code 搬到了 packs/code.py（接口见 packs/__init__.py）。from tools.dslagent import v2pack 仍可用，
拿到的就是 packs.code 模块本身（改它的常量两边一致）。"""
import sys

from .packs import code as _code

sys.modules[__name__] = _code
