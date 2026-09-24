# flows.py 的改动（三处）

## 一、签名：flows_dir 改成可选的绝对目录

def make_flow_tools(
    workspace: Path,
    client=None,
    flows_dir: Path | None = None,
    verbs_dir: Path | None = None,
    packs: list[str] | None = None,
    max_calls: int = 20,
) -> Registry:
    """把流程脚本包装成 agent 工具。

    flows_dir 默认取 mcp/flows（脚本由人维护，跟 verbs 放在一起）；
    workspace 仍是运行时数据目录，脚本里的保存/追加写在那里。
    """
    reg = Registry()
    workspace = Path(workspace).resolve()

    # mcp/ = workspace 的上两级
    root = workspace.parent.parent
    flows = Path(flows_dir) if flows_dir else root / "flows"
    verbs_root = Path(verbs_dir) if verbs_dir else root / "verbs"
    pack_names = packs if packs is not None else DEFAULT_PACKS

    if not flows.is_dir():
        flows.mkdir(parents=True, exist_ok=True)


## 二、_verbs() 里的 verbs_root 用上面算好的变量

    def _verbs():
        if "reg" not in _cache:
            from tools import make_verbs
            v = make_verbs()
            v.load_packs(verbs_root, pack_names, workspace=workspace)
            _cache["reg"] = v
        return _cache["reg"]


## 三、其余不变

_read_flow、_run、四个工具都不用改——它们用的都是 flows 这个变量。
引擎的 workdir 仍是 workspace，所以流程里的「保存」「追加」写进运行时目录，
读的却是 mcp/flows 下的脚本，两者分开。


# japanese.py 的改动（一处）

init_workspace() 里删掉建 flows 目录那行：

    (ws / "flows").mkdir(parents=True, exist_ok=True)      ← 删掉

flows 现在在 mcp/flows，不属于 workspace。


# fs.py 的改动（一处，可选）

顶部常量加一行，方便别处引用：

    FLOWS = BASE / "flows"
