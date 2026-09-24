"""common 包：跟具体领域无关的通用动词。

这个文件只做两件事：扫 defs/ 目录，以及定义需要共享辅助函数的动词。

common 的动词彼此独立，所以全部拆成了单文件放在 defs/ 下——加动词就是
加文件，删动词就是删文件，不用在几百行的 register() 里找位置。

需要共享闭包的场合（比如 quiz 包那十个动词共用 load / sift / safe），
直接写在下面的 register() 里，不必硬拆。

目录名用英文、文件名用中文，是有意的：文件名必须跟动词名一致，而动词名
要出现在 .zs 脚本里；目录名只有 Python 和文件系统会碰，中文只会给
sys.path、命令行补全、跨平台编码添麻烦。
"""

from pathlib import Path

from tools.verbs import scan_verbs

# 加载时注入，这里给占位免得静态检查报错
WORKSPACE = Path(".")
PACK_DIR = Path(".")


def register(reg, workspace):
    scan_verbs(reg, PACK_DIR / "defs", workspace, pack_dir=PACK_DIR)
