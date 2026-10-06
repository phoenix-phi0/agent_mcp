"""按种子稳定地打乱一个列表，返回新列表（原列表不动）。同一个种子、同样长的列表，顺序永远一样。例如 稳定打乱 {选项} {种子}

种子是任意文本，取它 UTF-8 的 sha256 当随机数种子。不用 hash()：每个进程
的盐不一样，出题和判题在两个请求里，算出来的顺序会对不上。

种子为空就不打乱，原样返回一份。列表收 JSON 数组文本或真列表。

打乱只看列表的长度，跟元素是什么无关：两个一样长的列表用同一个种子，
挪动的位置一样。
"""

import hashlib
import random

from tools.verbs import as_list


def 稳定打乱(列表="", 种子: str = "") -> list:
    items = as_list(列表)
    seed = str(种子 or "")
    if seed:
        random.Random(int(hashlib.sha256(seed.encode("utf-8")).hexdigest(), 16)).shuffle(items)
    return items
