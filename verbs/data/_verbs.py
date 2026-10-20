"""data 包：读写各种数据格式，以及目录浏览。

`读JSON` 和 `读JSONL` 是引擎内置语句，不在这里——读文件是基础能力，
不该依赖某个包是否加载，而且它们已经是保留字了。

这个包放**扩展格式**（CSV、YAML、纯文本行）、**写回文件**、**目录浏览**，
以及几个结构操作。不是每个脚本都要，按需 `用包 data`。

这些动词返回真正的对象和列表，不是逗号串——脚本里直接遍历，不用约定
分隔符。前提是引擎打了「动词返回结构」那个补丁，否则会被 str() 压平。

    用包 data

    设 文件表 = 列文件 content/n2n3/题库 .jsonl
    遍历 名 于 {文件表}
      打印 {名}
    结束

    设 行表 = 读CSV 数据/成绩.csv
    遍历 行 于 {行表}
      打印 {行.姓名}　{行.分数}
    结束
"""

import csv
import json
from pathlib import Path

# 加载时注入
WORKSPACE = Path(".")
PACK_DIR = Path(".")


def register(reg, workspace):
    workspace = Path(workspace).resolve()

    def safe(path: str) -> Path:
        """路径限制在工作目录内。

        动词被脚本调用，脚本内容可能来自模型，不做这层检查就等于把整个
        磁盘暴露给生成出来的路径。
        """
        p = (workspace / path).resolve()
        if p != workspace and workspace not in p.parents:
            raise ValueError(f"路径越界：{path}")
        return p

    def _as_data(内容, default=None):
        """参数可能是结构，也可能是 JSON 文本——引擎传参时会把结构转成
        文本，所以这里要试着解析回来。"""
        if not isinstance(内容, str):
            return 内容
        try:
            return json.loads(内容)
        except json.JSONDecodeError:
            return default if default is not None else 内容

    # ------------------------------------------------------------------
    # 目录
    # ------------------------------------------------------------------

    @reg.verb("列出目录下的文件名，返回列表。可按后缀筛。例如 列文件 题库 .jsonl")
    def 列文件(目录: str = ".", 后缀: str = "") -> list:
        d = safe(目录)
        if not d.is_dir():
            return []
        # 只返回文件名不带路径：拼回去用 {目录}/{名} 更直观，
        # 而且遍历时打印出来短
        names = sorted(p.name for p in d.iterdir() if p.is_file())
        if not 后缀:
            return names
        # 后缀带不带点都认——写 .jsonl 和 jsonl 是同一个意思
        suf = 后缀 if 后缀.startswith(".") else f".{后缀}"
        return [n for n in names if n.endswith(suf)]

    @reg.verb("列出目录下的子目录名，返回列表。")
    def 列目录(目录: str = ".") -> list:
        d = safe(目录)
        if not d.is_dir():
            return []
        return sorted(p.name for p in d.iterdir() if p.is_dir())

    @reg.verb("递归列出目录下所有文件的相对路径，返回列表。可按后缀筛。")
    def 遍历文件(目录: str = ".", 后缀: str = "") -> list:
        d = safe(目录)
        if not d.is_dir():
            return []
        suf = ("" if not 后缀
               else (后缀 if 后缀.startswith(".") else f".{后缀}"))
        # 返回相对于所给目录的路径，不是绝对路径也不是相对 workspace 的——
        # 这样 {目录}/{路径} 拼起来就是能用的路径，跟「列文件」一致
        out = []
        for p in sorted(d.rglob("*")):
            if p.is_file() and (not suf or p.name.endswith(suf)):
                out.append(p.relative_to(d).as_posix())
        return out

    @reg.verb("判断文件或目录存不存在，返回「是」或「否」。")
    def 存在(路径: str) -> bool:
        try:
            return safe(路径).exists()
        except ValueError:
            return False

    # ------------------------------------------------------------------
    # 读
    # ------------------------------------------------------------------

    @reg.verb("读 CSV，返回对象列表，首行当表头。例如 读CSV 数据/成绩.csv")
    def 读CSV(文件: str, 分隔符: str = ",") -> list:
        f = safe(文件)
        if not f.is_file():
            return []
        # utf-8-sig 吃掉 Excel 导出的 BOM，否则第一个表头会带个看不见的字符
        # newline="" 是 csv 模块的要求：不这么写，字段里的换行会被拆成两行
        with f.open(encoding="utf-8-sig", newline="") as fh:
            return list(csv.DictReader(fh, delimiter=分隔符 or ","))

    @reg.verb("读纯文本的每一行，返回列表。空行跳过。")
    def 读文本行(文件: str) -> list:
        f = safe(文件)
        if not f.is_file():
            return []
        return [ln.strip() for ln in f.read_text(encoding="utf-8").splitlines()
                if ln.strip()]

    @reg.verb("读 YAML，返回对象或列表。需要 pyyaml。")
    def 读YAML(文件: str):
        try:
            import yaml
        except ImportError:
            return "[需要先装 pyyaml：pip install pyyaml]"
        f = safe(文件)
        if not f.is_file():
            return f"[文件不存在] {文件}"
        # safe_load 而不是 load：后者能构造任意 Python 对象，
        # 读不受信任的文件等于执行任意代码
        return yaml.safe_load(f.read_text(encoding="utf-8"))

    # ------------------------------------------------------------------
    # 写
    # ------------------------------------------------------------------

    @reg.verb("把结构写成 JSON 文件，带缩进。")
    def 写JSON(文件: str, 内容) -> str:
        f = safe(文件)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(
            json.dumps(_as_data(内容), ensure_ascii=False, indent=2),
            encoding="utf-8")
        return f"[已写入 {文件}]"

    @reg.verb("把对象列表写成 jsonl，每行一条。")
    def 写JSONL(文件: str, 内容) -> str:
        rows = _as_data(内容)
        if not isinstance(rows, list):
            return "[内容不是列表]"
        f = safe(文件)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
            encoding="utf-8")
        return f"[已写入 {文件}，{len(rows)} 条]"

    @reg.verb("删掉工作目录里的一个文件（不删目录）。不在也不报错，返回「是」（删了）或「否」。"
              "例如 删文件 uploads/a.pdf")
    def 删文件(文件: str) -> bool:
        f = safe(文件)
        if f.is_dir():
            raise ValueError(f"删文件：{文件} 是目录，只删文件")
        if not f.is_file():
            return False
        f.unlink()
        return True

    # ------------------------------------------------------------------
    # 结构操作
    # ------------------------------------------------------------------

    @reg.verb("从对象列表里挑出某个字段的值，返回列表。例如 取列 {行表} 姓名")
    def 取列(列表, 字段: str) -> list:
        rows = _as_data(列表, [])
        if not isinstance(rows, list):
            return []
        return [r.get(字段) for r in rows if isinstance(r, dict) and 字段 in r]

    @reg.verb("按字段值筛选对象列表。例如 筛选 {行表} 班级 三班")
    def 筛选(列表, 字段: str, 值: str) -> list:
        rows = _as_data(列表, [])
        if not isinstance(rows, list):
            return []
        return [r for r in rows
                if isinstance(r, dict) and str(r.get(字段, "")) == 值]

    @reg.verb("统计列表或对象里有多少项。")
    def 条数(内容) -> str:
        data = _as_data(内容, [])
        return str(len(data)) if isinstance(data, (list, dict)) else "0"
