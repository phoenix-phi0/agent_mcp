"""text 包：通用的字符串动词。跟具体领域无关，判题、判默写这类业务规则拿它们拼。

动词彼此独立，一文件一个放 defs/，这里只扫目录（跟 common 包一样）。

为什么要有这个包：DSL 本身只有「设」「如果 … 等于 …」这些，不会归一化、
不会按正则取东西，业务规则（什么算答对）只好写进 Python。补上这几个小动词，
规则就能写在 .zs 里——改判对规则不碰 Python。保持最小：缺什么补什么。

几个跟 DSL 有关的约定：

  · 参数按空格切，值里有空格就先「设」进变量再 {变量} 传（切在展开之前，
    {变量} 展开出来带空格没事）。
  · 参数进来一律是文本。要列表的参数（稳定打乱、列表加项）收 JSON 文本，
    也收真列表（从 Python 直接调时）。
  · 返回「是」/「否」的（相等），配「如果 {x} 等于 是」用。
"""

from pathlib import Path

from tools.verbs import scan_verbs

# 加载时注入，这里给占位免得静态检查报错
WORKSPACE = Path(".")
PACK_DIR = Path(".")


def register(reg, workspace):
    scan_verbs(reg, PACK_DIR / "defs", workspace, pack_dir=PACK_DIR)
