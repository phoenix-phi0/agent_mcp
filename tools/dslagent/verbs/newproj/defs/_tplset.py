"""模板集名单与提示词里的模板清单——来自 gen/templates/*/set.json（gen.templates_），不在这里写死。
gen 导不进来（极端情况）时退回老名单。"""
import re
import sys
from pathlib import Path

FALLBACK = ("default", "full", "private")
MARK = re.compile(r"《模板清单(?::(名|提示))?》")


def _gen():
    try:
        import gen.templates_ as T
    except ImportError:
        root = str(Path(__file__).resolve().parents[5])
        if root not in sys.path:
            sys.path.insert(0, root)
        import gen.templates_ as T
    return T


def names():
    try:
        return tuple(_gen().sets()) or FALLBACK
    except Exception:  # noqa: BLE001  清单坏了也别让提示词/校验跟着崩
        return FALLBACK


def menu(kind: str = "名") -> str:
    """kind=名：`default / full / private`；kind=提示：`default/full（一般选它）/private（…）`（用清单里的「提示」）。"""
    if kind != "提示":
        return " / ".join(names())
    T = _gen()
    out = []
    for n in names():
        try:
            hint = str(T.describe(n).get("提示") or "")
        except Exception:  # noqa: BLE001
            hint = ""
        out.append(f"{n}（{hint}）" if hint else n)
    return "/".join(out)


def fill(text: str) -> str:
    """把提示词里的《模板清单》《模板清单:提示》换成当前清单。"""
    return MARK.sub(lambda m: menu(m.group(1) or "名"), text)
