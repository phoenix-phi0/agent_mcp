# japanese.py 顶部路径部分的改动

把原来的：

    ROOT = Path(__file__).resolve().parent.parent
    SOUL_PATH = ROOT / "agents" / "souls" / "JP-E01-pi.md"
    WORKSPACE = ROOT / "workspace" / "japanese"

换成：

    import os

    # 代码目录：打包后指向 PyInstaller 的临时解压目录
    CODE_ROOT = Path(__file__).resolve().parent.parent
    # 数据目录：打包后指向 exe 所在目录，开发时两者相同
    DATA_ROOT = Path(os.environ.get("JP_DATA_DIR") or CODE_ROOT)

    # SOUL.md 跟代码走（不需要用户改）
    SOUL_PATH = CODE_ROOT / "agents" / "souls" / "JP-E01-pi.md"
    # 运行时数据跟数据目录走
    WORKSPACE = DATA_ROOT / "workspace" / "japanese"


# flows.py 的改动

make_flow_tools 里原来是：

    root = workspace.parent.parent
    flows = Path(flows_dir).resolve() if flows_dir else (root / "flows").resolve()
    verbs_root = Path(verbs_dir) if verbs_dir else root / "verbs"

改成从环境变量取，回退到原逻辑：

    import os

    root = Path(os.environ.get("JP_DATA_DIR") or workspace.parent.parent)
    flows = Path(flows_dir).resolve() if flows_dir else (root / "flows").resolve()
    verbs_root = Path(verbs_dir) if verbs_dir else root / "verbs"

这样 flows 和 verbs 始终在 exe 旁边，打包后仍然可以直接编辑。
