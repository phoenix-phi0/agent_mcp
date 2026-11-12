"""配置加载。

配置文件位置，按优先级：

    1. 环境变量 ZHIPU_CONFIG 指定的路径（桌面程序打包后走这条）
    2. 环境变量 JP_DATA_DIR 下的 config.json
    3. 项目根目录（tools/ 的上一级）下的 config.json

优先级：显式参数 > 环境变量 > config.json > 内置默认值

## 模型名：通道:提供方/模型

    api:zhipu/glm-5.3          智谱 HTTP API
    api:anthropic/<模型>        预留，还没接入（调用时报错）
    cli:claude/sonnet          本机 Claude Code（claude -p）；cli:claude 不带模型 = 它自己的默认
    cli:claude/sonnet@low      同上，带努力程度（--effort）：low/medium/high/xhigh/max，
                               不写用 claude 自己的默认；只有 cli:claude 能写
    cli:zcode                  本机 ZCode（zcode -p），不能选模型

兼容写法（照旧能用，python -m tools.config 会标出来）：
裸名 glm-5.3 = api:zhipu/glm-5.3；claude:sonnet = cli:claude/sonnet；
claude = cli:claude；zcode、zcode:随便 = cli:zcode（后半忽略）。

parse_model(名字) 把任何写法规范成 ModelSpec(channel, provider, model, raw)。
各后端支持什么能力写在 BACKENDS 表里（不散落在 if 里），路由按这张表判断：

    能力     api:zhipu   cli:claude / cli:zcode
    带工具   支持        不支持（报错）
    流式     真流式      降级：等整段生成完一次性返回（不报错）

## 模型档位和别名：models.json

config.json 里有 api_key，不能提交 git，所以档位和别名单放一个 models.json：

    {"default": "平衡",
     "tiers":   {"快": "api:zhipu/glm-5.3-flashx",
                 "强": {"model": "cli:claude/opus", "fallback": "api:zhipu/glm-5.3"}},
     "aliases": {"克": "cli:claude/sonnet"}}

档位的值可以是字符串，也可以是对象 {"model": …, "fallback": …}。写了
fallback，这一档遇到主模型没有的能力（带工具）时改用 fallback，并记一条
warning 日志；没写 fallback 就直接报错。fallback 必须写模型名（不能写档位
或别名），它自己也得有那个能力。别名只能是字符串，不支持 fallback；别名
指向档位时继承档位的 fallback。

位置：环境变量 ZHIPU_MODELS 指定的路径 > config.json 同目录下的 models.json
（所以同样认 ZHIPU_CONFIG / JP_DATA_DIR）。不存在就没有档位，不报错；
格式坏了报错并指出文件。键以 "_" 开头的是注释。

查名字（resolve_model）：档位 > models.json 的别名 > config.json 旧的
models 别名表。档位和 models.json 的别名重名直接报错（写哪个算哪个都会让
人困惑）；config.json 的旧别名和它们重名时 models.json 优先。查到的值如果
又是一个档位或别名名，再查一层（「克」→「强」→ glm-5.3），只一层。
返回值是 ModelRef（str 的子类，跟原来一样当字符串用），多带一个 tier：
从哪个档位查到的，路由靠它找 fallback。

不写模型时的默认模型（client.model）：
环境变量 ZHIPU_MODEL > config.json 的 model > models.json 的 default 档位 >
内置默认。config.json 写了 model 就以它为准，default 档位不起作用——
保证加了 models.json 之后不写模型的行为不变。

排查用：python -m tools.config（打印档位表和别名表，每个名字的规范名、
通道、能力和 fallback，以及 cli:claude / cli:zcode 是本机调还是经 WSL 调；
不打印 key）
"""

import json
import os
from pathlib import Path
from typing import NamedTuple

# 项目根目录：tools/ -> mcp/
CODE_ROOT = Path(__file__).resolve().parent.parent

# 打包成 exe 后，代码在临时目录，数据在 exe 旁边，所以要分开
DATA_ROOT = Path(os.environ.get("JP_DATA_DIR") or CODE_ROOT)


def _config_path() -> Path:
    if os.environ.get("ZHIPU_CONFIG"):
        return Path(os.environ["ZHIPU_CONFIG"]).expanduser()
    return DATA_ROOT / "config.json"


def _models_path() -> Path:
    if os.environ.get("ZHIPU_MODELS"):
        return Path(os.environ["ZHIPU_MODELS"]).expanduser()
    return _config_path().parent / "models.json"


CONFIG_PATH = _config_path()
MODELS_PATH = _models_path()

BUILTIN_MODEL = "glm-4.6"

DEFAULTS = {
    "api_key": "",
    "model": BUILTIN_MODEL,
    "timeout": 60,
    "temperature": 0.7,
    "embedding_model": "embedding-3",
    "image_model": "cogview-4",
    "base_url": "https://open.bigmodel.cn/api/paas/v4",
    # 旧的模型别名表，如 {"快": "glm-4-flash"}。继续认，但新写的放 models.json
    "models": {},
}

# 字段名 -> 对应的环境变量名
ENV_MAP = {
    "api_key": "ZHIPU_API_KEY",
    "model": "ZHIPU_MODEL",
    "base_url": "ZHIPU_BASE_URL",
}

_cache: dict | None = None

# ----------------------------------------------------------------------
# 模型名规范化和能力表
# ----------------------------------------------------------------------


class ModelNameError(ValueError):
    """模型名写得不对：未知通道、缺提供方、给不能选模型的后端写了模型……"""


class Backend(NamedTuple):
    label: str            # 给人看的名字
    ready: bool           # False = 预留，还没接入
    caps: dict            # 能力 -> "yes" 支持 / "degraded" 降级可用 / "no" 不支持
    pick_model: bool      # 能不能选模型（cli:zcode 不能）
    needs_model: bool     # 必须写模型（api 的必须，cli:claude 可以不写）


# 能力的中文名。新能力加在这里，再给每个后端填上
CAPS = {"tools": "带工具", "stream": "流式"}

_API = {"tools": "yes", "stream": "yes"}
_CLI = {"tools": "no", "stream": "degraded"}

BACKENDS = {
    ("api", "zhipu"): Backend("智谱 HTTP API", True, _API, True, True),
    ("api", "anthropic"): Backend("Anthropic HTTP API", False, _API, True, True),
    ("cli", "claude"): Backend("本机 Claude Code（claude -p）", True, _CLI,
                               True, False),
    ("cli", "zcode"): Backend("本机 ZCode（zcode -p）", True, _CLI, False, False),
    ("cli", "goose"): Backend("本机 Goose（goose run，Z.AI 账号）", True, _CLI,
                              True, False),
    # codex exec（ChatGPT 账号登录，~/.codex/auth.json）：有系统级沙箱（read-only / workspace-write）
    ("cli", "codex"): Backend("本机 Codex（codex exec，ChatGPT 账号）", True, _CLI,
                              True, False),
}

CHANNELS = ("api", "cli")

# 模型名后面「@努力程度」：只有 claude -p 有 --effort。值是 claude 认的那几个，
# 写错了在解析时就报，不要等到真起 claude 才失败。
EFFORTS = ("low", "medium", "high", "xhigh", "max")
EFFORT_BACKENDS = {("cli", "claude"), ("cli", "codex")}   # codex：-c model_reasoning_effort=…


class ModelSpec(NamedTuple):
    channel: str     # api / cli
    provider: str    # zhipu / anthropic / claude / zcode
    model: str       # 后端里的模型名；"" = 后端自己的默认
    raw: str         # 原来怎么写的
    legacy: bool     # 不是规范写法（裸名或 claude:/zcode 旧前缀）

    @property
    def canonical(self) -> str:
        base = f"{self.channel}:{self.provider}"
        return f"{base}/{self.model}" if self.model else base

    @property
    def backend(self) -> Backend:
        return BACKENDS[(self.channel, self.provider)]

    def cap(self, need: str) -> str:
        """这个模型对某能力的支持："yes" / "degraded" / "no"。"""
        return self.backend.caps.get(need, "no")


def _providers(channel: str) -> str:
    return "、".join(f"{c}:{p}" for c, p in BACKENDS if c == channel)


def split_effort(model: str) -> tuple:
    """"sonnet@low" → ("sonnet", "low")；没有「@」→ (model, "")。"""
    base, _, effort = model.partition("@")
    return base.strip(), effort.strip()


def _check_effort(raw: str, channel: str, provider: str, model: str) -> None:
    """模型名里的「@努力程度」写得对不对，见 EFFORTS。"""
    if "@" not in model:
        return
    base, effort = split_effort(model)
    if (channel, provider) not in EFFORT_BACKENDS:
        raise ModelNameError(
            f"模型名「{raw}」：只有 cli:claude 能写「@努力程度」，"
            f"{channel}:{provider} 不支持")
    if not base:
        raise ModelNameError(
            f"模型名「{raw}」：「@」前面要写模型，如 cli:claude/sonnet@{effort or 'low'}")
    if effort not in EFFORTS:
        raise ModelNameError(
            f"模型名「{raw}」：努力程度「{effort}」不认识，"
            f"可用 {'、'.join(EFFORTS)}")


def parse_model(name) -> ModelSpec:
    """任何写法的模型名 → ModelSpec。只认名字本身，不查档位和别名
    （先 resolve_model 再 parse）。写错了抛 ModelNameError。

    「@努力程度」留在 model 里（"sonnet@low"），后端调用时再拆，见 split_effort。"""
    spec = _parse_model(name)
    _check_effort(spec.raw, spec.channel, spec.provider, spec.model)
    return spec


def _parse_model(name) -> ModelSpec:
    if not isinstance(name, str) or not name.strip():
        raise ModelNameError(f"模型名不能是空的：{name!r}")
    raw = name.strip()
    head, sep, tail = raw.partition(":")

    if sep and head in CHANNELS:
        provider, slash, model = tail.partition("/")
        provider, model = provider.strip(), model.strip()
        if not provider:
            raise ModelNameError(
                f"模型名「{raw}」缺提供方：规范写法是 通道:提供方/模型，"
                f"如 api:zhipu/glm-5.3、cli:claude/sonnet")
        if (head, provider) not in BACKENDS:
            raise ModelNameError(
                f"模型名「{raw}」：{head} 通道没有提供方「{provider}」"
                f"（可用 {_providers(head)}）")
        b = BACKENDS[(head, provider)]
        if slash and not model:
            raise ModelNameError(f"模型名「{raw}」：「/」后面缺模型名")
        if model and not b.pick_model:
            raise ModelNameError(
                f"模型名「{raw}」：{head}:{provider} 不能选模型（用的是它账号里"
                f"设的模型），去掉「/{model}」写成 {head}:{provider}")
        if not model and b.needs_model:
            raise ModelNameError(
                f"模型名「{raw}」要写模型，如 {head}:{provider}/<模型>")
        return ModelSpec(head, provider, model, raw, False)

    # 旧写法：claude / claude:sonnet / zcode / zcode:随便
    if head == "claude":
        return ModelSpec("cli", "claude", tail.strip(), raw, True)
    if head == "zcode":
        return ModelSpec("cli", "zcode", "", raw, True)
    if sep:
        raise ModelNameError(
            f"模型名「{raw}」：不认识的通道「{head}」。规范写法是 通道:提供方/模型，"
            f"通道只有 api（{_providers('api')}）和 cli（{_providers('cli')}）；"
            f"不带通道的裸名当智谱模型")
    # 裸名：智谱模型
    return ModelSpec("api", "zhipu", raw, raw, True)


def capability_error(spec: ModelSpec, need: str, extra: str = "") -> str:
    """「某模型不支持某能力」的错误信息：说出规范名、能力、怎么办。"""
    cap = CAPS.get(need, need)
    return (f"模型 {spec.canonical}（{spec.backend.label}）不支持「{cap}」{extra}。"
            f"办法：换一个 api 通道的档位或模型（如 api:zhipu/glm-5.3，智谱），"
            f"或在 models.json 里把这一档写成 "
            f'{{"model": "{spec.canonical}", "fallback": "api:zhipu/…"}}')


class ModelRef(str):
    """resolve_model 的返回值：就是模型名字符串，多记一个 tier（从哪个档位
    查到的，没有就是 None）。路由靠 tier 找档位的 fallback。"""

    tier = None




def _load_models_file(path: Path) -> dict:
    """读 models.json，返回 {"default", "tiers", "aliases", "_found"}。

    不存在返回空表；格式不对抛 ValueError，消息里带文件路径和哪里不对。
    """
    empty = {"default": None, "tiers": {}, "aliases": {}, "fallbacks": {},
             "_found": False}
    if not path.is_file():
        return empty

    def bad(why):
        return ValueError(f"模型档位文件格式错误 {path}: {why}")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise bad(e) from e
    if not isinstance(data, dict):
        raise bad("最外层应该是对象 {…}")

    known = {"default", "tiers", "aliases"}
    extra = [k for k in data if k not in known and not k.startswith("_")]
    if extra:
        raise bad(f"不认识的键 {extra}（可用 default / tiers / aliases，"
                  f"注释用 _ 开头的键）")

    def nonempty(v):
        return isinstance(v, str) and bool(v.strip())

    tables, fallbacks = {}, {}
    for key in ("tiers", "aliases"):
        table = data.get(key) or {}
        if not isinstance(table, dict):
            raise bad(f"{key} 应该是对象 {{名字: 模型}}")
        out = {}
        for name, value in table.items():
            where = f"{key} 里的「{name}」"
            if isinstance(value, dict) and key == "aliases":
                raise bad(f"{where}：别名只能写字符串，不支持 fallback"
                          f"（要 fallback 就让别名指向一个带 fallback 的档位）")
            if isinstance(value, dict):
                unknown = [k for k in value
                           if k not in ("model", "fallback")
                           and not k.startswith("_")]
                if unknown:
                    raise bad(f"{where}：不认识的键 {unknown}"
                              f"（只有 model 和 fallback）")
                if not nonempty(value.get("model")):
                    raise bad(f"{where}：对象写法要有 model（非空字符串），"
                              f'如 {{"model": "cli:claude/opus", '
                              f'"fallback": "api:zhipu/glm-5.3"}}')
                if "fallback" in value and not nonempty(value["fallback"]):
                    raise bad(f"{where}：fallback 得是非空字符串（模型名）")
                if nonempty(value.get("fallback")):
                    fallbacks[name.strip()] = value["fallback"].strip()
                value = value["model"]
            if not nonempty(value) or not name.strip():
                raise bad(f"{where}：名字和模型都得是非空字符串"
                          + ("（档位也可以写对象 {model, fallback}）"
                             if key == "tiers" else ""))
            try:
                parse_model(value)
            except ModelNameError as e:
                raise bad(f"{where}：{e}") from None
            out[name.strip()] = value.strip()
        tables[key] = out

    clash = sorted(set(tables["tiers"]) & set(tables["aliases"]))
    if clash:
        raise bad(f"档位和别名重名：{clash}，改掉其中一个")

    for name, fb in fallbacks.items():
        where = f"tiers 里的「{name}」的 fallback「{fb}」"
        if fb in tables["tiers"] or fb in tables["aliases"]:
            raise bad(f"{where}：要写模型名（如 api:zhipu/glm-5.3），"
                      f"不能写档位或别名")
        try:
            parse_model(fb)
        except ModelNameError as e:
            raise bad(f"{where}：{e}") from None

    default = data.get("default")
    if default is not None:
        if not isinstance(default, str) or default.strip() not in tables["tiers"]:
            raise bad(f"default「{default}」不是 tiers 里的档位"
                      f"（有 {list(tables['tiers'])}）")
        default = default.strip()

    return {"default": default, **tables, "fallbacks": fallbacks,
            "_found": True}


def load(reload: bool = False) -> dict:
    """读取配置，结果会缓存。reload=True 强制重新读。"""
    global _cache, CONFIG_PATH, MODELS_PATH
    if _cache is not None and not reload:
        return _cache

    if reload:
        CONFIG_PATH = _config_path()
        MODELS_PATH = _models_path()

    cfg = dict(DEFAULTS)
    file_cfg = {}

    if CONFIG_PATH.is_file():
        try:
            file_cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ValueError(f"配置文件格式错误 {CONFIG_PATH}: {e}") from e
        cfg.update(file_cfg)
        cfg["_found"] = True
    else:
        cfg["_found"] = False

    # 环境变量覆盖文件
    for key, env in ENV_MAP.items():
        if os.environ.get(env):
            cfg[key] = os.environ[env]

    mf = _load_models_file(MODELS_PATH)
    cfg["tiers"] = mf["tiers"]
    # 档位名 → fallback 模型名，只有写了 fallback 的档位才在里面
    cfg["tier_fallbacks"] = mf["fallbacks"]
    cfg["default_tier"] = mf["default"]
    legacy = cfg.get("models") if isinstance(cfg.get("models"), dict) else {}
    # 合并后的别名表：models.json 盖掉 config.json 的同名旧别名
    cfg["aliases"] = {**legacy, **mf["aliases"]}
    cfg["_alias_from"] = {**{k: "config.json" for k in legacy},
                          **{k: "models.json" for k in mf["aliases"]}}
    cfg["_models_found"] = mf["_found"]

    # 默认模型从哪来：环境变量 > config.json > default 档位 > 内置
    if os.environ.get("ZHIPU_MODEL"):
        cfg["_model_from"] = "环境变量 ZHIPU_MODEL"
    elif file_cfg.get("model"):
        cfg["_model_from"] = "config.json 的 model"
    elif mf["default"]:
        cfg["model"] = mf["default"]
        cfg["_model_from"] = f"models.json 的 default 档位「{mf['default']}」"
    else:
        cfg["_model_from"] = "内置默认"

    _cache = cfg
    # 默认模型也可以写档位名或别名（ZHIPU_MODEL=强），这里换成真名
    cfg["model"] = resolve_model(cfg["model"]) or BUILTIN_MODEL
    return cfg


def get(key: str, default=None):
    return load().get(key, default)


def model_names() -> dict:
    """所有可用的名字 → 直接指向的值。档位优先于别名。"""
    cfg = load()
    return {**cfg.get("aliases", {}), **cfg.get("tiers", {})}


def resolve_model(name) -> str | None:
    """模型名、档位名或别名转真名；不认识的原样返回；空返回 None。

    None 的意思是「没指定」，调用方用自己的默认模型。
    查到的值又是档位名或别名时再查一层（别名指向档位）。
    """
    # 传进来的已经是解析过的 ModelRef（引擎解析一次、路由再解析一次）时，
    # 档位记号不能丢
    tier = getattr(name, "tier", None)
    name = (name or "").strip() if isinstance(name, str) else name
    if not name:
        return None
    cfg = load()
    tiers = cfg.get("tiers", {})
    names = model_names()
    value = names.get(name, name)
    if name in tiers:
        tier = name
    if value != name:
        if value in tiers and tier is None:
            tier = value
        value = names.get(value, value)
    ref = ModelRef(value)
    ref.tier = tier
    return ref


def resolve_spec(name):
    """名字（模型、档位、别名）→ (ModelSpec, 档位名或 None, fallback 的
    ModelSpec 或 None)。空 → None。路由用这个，不再自己判断前缀。"""
    ref = resolve_model(name)
    if ref is None:
        return None
    fb = load().get("tier_fallbacks", {}).get(ref.tier) if ref.tier else None
    return parse_model(ref), ref.tier, (parse_model(fb) if fb else None)


def _canon(value) -> str:
    """规范名；写错了就原样（只用于比较和显示）。"""
    try:
        return parse_model(value).canonical
    except ModelNameError:
        return str(value)


def describe_model(value: str) -> str:
    """python -m tools.config 用：规范名、通道、能力、旧写法提示。"""
    try:
        spec = parse_model(value)
    except ModelNameError as e:
        return f"✗ {e}"
    b = spec.backend
    tools = {"yes": "能", "degraded": "降级", "no": "不能"}[spec.cap("tools")]
    stream = {"yes": "真", "degraded": "降级（一次性返回）",
              "no": "不支持"}[spec.cap("stream")]
    parts = [spec.canonical, spec.channel.upper(), f"带工具：{tools}",
             f"流式：{stream}"]
    if not b.ready:
        parts.append(f"{spec.channel}:{spec.provider} 还没接入")
    note = ""
    if spec.legacy and spec.raw != spec.canonical:
        bare = spec.channel == "api"
        note = (f"  （{'裸名' if bare else '旧写法'}，"
                f"{'等于' if bare else '建议改成'} {spec.canonical}）")
        if spec.provider == "zcode" and ":" in spec.raw:
            note = f"  （旧写法，后半忽略，建议改成 {spec.canonical}）"
    return " · ".join(parts) + note


def source() -> str:
    """配置文件路径及是否存在。"""
    cfg = load()
    mark = "已读取" if cfg.get("_found") else "不存在，使用默认值和环境变量"
    return f"{CONFIG_PATH}（{mark}）"


def models_source() -> str:
    cfg = load()
    mark = "已读取" if cfg.get("_models_found") else "不存在，没有档位"
    return f"{MODELS_PATH}（{mark}）"


if __name__ == "__main__":
    print("代码目录：", CODE_ROOT)
    print("数据目录：", DATA_ROOT)
    print("配置文件：", source())
    print("档位文件：", models_source())
    cfg = load()
    print(f"默认模型： {cfg.get('model')}（来自{cfg.get('_model_from')}）")
    default = cfg.get("default_tier")
    if default and cfg.get("_model_from", "").startswith("config.json") \
            and _canon(resolve_model(default)) != _canon(cfg.get("model")):
        print(f"  注意：default 档位「{default}」= {resolve_model(default)}，"
              f"但 config.json 写了 model，以 config.json 为准")
    print(f"  默认模型 = {describe_model(cfg.get('model'))}")
    tiers = cfg.get("tiers") or {}
    fallbacks = cfg.get("tier_fallbacks") or {}
    print("档位：" if tiers else "档位：(无)")
    for name, value in tiers.items():
        mark = "  ← default" if name == default else ""
        print(f"  {name} → {value}{mark}")
        print(f"      {describe_model(resolve_model(name))}")
        if name in fallbacks:
            print(f"      fallback（主模型缺能力时改用）："
                  f"{describe_model(fallbacks[name])}")
    aliases = cfg.get("aliases") or {}
    print("别名：" if aliases else "别名：(无)")
    for name, value in aliases.items():
        real = resolve_model(name)
        via = f"（= {real}）" if real != value else ""
        if name in tiers:
            via += "  ← 跟档位重名，不生效"
        print(f"  {name} → {value}{via}  [{cfg['_alias_from'].get(name)}]")
        print(f"      {describe_model(real)}")
        if real.tier in fallbacks:
            print(f"      fallback（继承档位「{real.tier}」）："
                  f"{describe_model(fallbacks[real.tier])}")
    from tools import llm_router
    mode, mode_from = llm_router.via_wsl_setting()
    mode = {True: "true", False: "false"}.get(mode, mode)
    print(f"CLI 调用方式（cli_via_wsl = {mode}，来自{mode_from}；"
          f"{'是' if llm_router.is_windows() else '不是'} Windows）：")
    for name, backend in llm_router._BACKENDS.items():
        print(f"  {name}：{backend.describe()}")
    print("API Key：", "已设置" if cfg.get("api_key") else "缺失")
