"""配置加载。

配置文件位置，按优先级：

    1. 环境变量 ZHIPU_CONFIG 指定的路径（桌面程序打包后走这条）
    2. 环境变量 JP_DATA_DIR 下的 config.json
    3. 项目根目录（tools/ 的上一级）下的 config.json

优先级：显式参数 > 环境变量 > config.json > 内置默认值

排查用：python -m tools.config
"""

import json
import os
from pathlib import Path

# 项目根目录：tools/ -> mcp/
CODE_ROOT = Path(__file__).resolve().parent.parent

# 打包成 exe 后，代码在临时目录，数据在 exe 旁边，所以要分开
DATA_ROOT = Path(os.environ.get("JP_DATA_DIR") or CODE_ROOT)


def _config_path() -> Path:
    if os.environ.get("ZHIPU_CONFIG"):
        return Path(os.environ["ZHIPU_CONFIG"]).expanduser()
    return DATA_ROOT / "config.json"


CONFIG_PATH = _config_path()

DEFAULTS = {
    "api_key": "",
    "model": "glm-4.6",
    "timeout": 60,
    "temperature": 0.7,
    "embedding_model": "embedding-3",
    "image_model": "cogview-4",
    "base_url": "https://open.bigmodel.cn/api/paas/v4",
}

# 字段名 -> 对应的环境变量名
ENV_MAP = {
    "api_key": "ZHIPU_API_KEY",
    "model": "ZHIPU_MODEL",
    "base_url": "ZHIPU_BASE_URL",
}

_cache: dict | None = None


def load(reload: bool = False) -> dict:
    """读取配置，结果会缓存。reload=True 强制重新读。"""
    global _cache, CONFIG_PATH
    if _cache is not None and not reload:
        return _cache

    if reload:
        CONFIG_PATH = _config_path()

    cfg = dict(DEFAULTS)

    if CONFIG_PATH.is_file():
        try:
            cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except json.JSONDecodeError as e:
            raise ValueError(f"配置文件格式错误 {CONFIG_PATH}: {e}") from e
        cfg["_found"] = True
    else:
        cfg["_found"] = False

    # 环境变量覆盖文件
    for key, env in ENV_MAP.items():
        if os.environ.get(env):
            cfg[key] = os.environ[env]

    _cache = cfg
    return cfg


def get(key: str, default=None):
    return load().get(key, default)


def source() -> str:
    """配置文件路径及是否存在。"""
    cfg = load()
    mark = "已读取" if cfg.get("_found") else "不存在，使用默认值和环境变量"
    return f"{CONFIG_PATH}（{mark}）"


if __name__ == "__main__":
    print("代码目录：", CODE_ROOT)
    print("数据目录：", DATA_ROOT)
    print("配置文件：", source())
    cfg = load()
    print("模型：", cfg.get("model"))
    print("API Key：", "已设置" if cfg.get("api_key") else "缺失")
