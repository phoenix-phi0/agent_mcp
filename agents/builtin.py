"""内置工具：限定在某个工作目录内的文件读写。

    reg = make_file_tools(Path("workspace/japanese"))

结果长度：每个工具都设了字符上限，超出会截断并提示模型。
read_file 支持按行分段读取，避免整个大文件进上下文。
"""

from pathlib import Path

from .registry import Registry


def make_file_tools(
    workspace: Path,
    max_bytes: int = 200_000,
    max_result: int = 1500,
) -> Registry:
    """创建一组限定在 workspace 内的文件工具。"""
    workspace = Path(workspace).resolve()
    workspace.mkdir(parents=True, exist_ok=True)

    reg = Registry(max_result=max_result)

    def safe(path: str) -> Path:
        p = (workspace / path).resolve()
        if p != workspace and workspace not in p.parents:
            raise ValueError(f"路径越界，只能访问工作目录内：{path}")
        return p

    @reg.tool(
        "读取一个文本文件。文件很长时可以用 start_line / end_line 分段读，"
        "只需要开头几行时把 end_line 设小一点，避免整个文件进入对话。",
        max_result=1500,
        truncate_hint="需要后面的内容就用 start_line 继续读",
        path="相对于工作目录的文件路径，例如 memory/φ-0/progress.json",
        start_line="从第几行开始读，默认第 1 行",
        end_line="读到第几行为止，0 表示读到结尾",
    )
    def read_file(path: str, start_line: int = 1, end_line: int = 0) -> str:
        f = safe(path)
        if not f.is_file():
            return f"[文件不存在] {path}"
        if f.stat().st_size > max_bytes:
            return f"[文件过大] {path} 超过 {max_bytes} 字节，请分段读取"

        lines = f.read_text(encoding="utf-8").splitlines()
        total = len(lines)
        start = max(1, start_line)
        end = total if end_line <= 0 else min(end_line, total)
        chunk = "\n".join(lines[start - 1:end])

        if start > 1 or end < total:
            chunk += f"\n[以上是第 {start}-{end} 行，全文共 {total} 行]"
        return chunk

    @reg.tool(
        "查看文件大小和行数，读大文件前可以先看这个决定怎么分段。",
        max_result=300,
        path="相对于工作目录的文件路径",
    )
    def file_info(path: str) -> str:
        f = safe(path)
        if not f.is_file():
            return f"[文件不存在] {path}"
        text = f.read_text(encoding="utf-8", errors="replace")
        return f"{path}：{len(text)} 字，{len(text.splitlines())} 行"

    @reg.tool(
        "写入一个文本文件，会覆盖原有内容。父目录自动创建。",
        max_result=200,
        path="相对于工作目录的文件路径",
        content="要写入的完整内容",
    )
    def write_file(path: str, content: str) -> str:
        f = safe(path)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content, encoding="utf-8")
        return f"[已写入] {path}（{len(content)} 字）"

    @reg.tool(
        "在文本文件末尾追加内容，不覆盖原有内容。适合写 jsonl 日志。",
        max_result=200,
        path="相对于工作目录的文件路径",
        content="要追加的内容，会自动补一个换行",
    )
    def append_file(path: str, content: str) -> str:
        f = safe(path)
        f.parent.mkdir(parents=True, exist_ok=True)
        with f.open("a", encoding="utf-8") as fh:
            fh.write(content.rstrip("\n") + "\n")
        return f"[已追加] {path}"

    @reg.tool(
        "列出某个目录下的文件和子目录。",
        max_result=800,
        path="相对于工作目录的路径，默认为工作目录本身",
    )
    def list_dir(path: str = ".") -> str:
        d = safe(path)
        if not d.is_dir():
            return f"[不是目录] {path}"
        items = []
        for p in sorted(d.iterdir(), key=lambda x: (x.is_file(), x.name)):
            items.append(f"{p.name}/" if p.is_dir() else p.name)
        return "\n".join(items) or "(空目录)"

    @reg.tool(
        "检查某个字符串是否已经出现在 jsonl 文件里，用于去重。"
        "只返回是/否，不会把文件内容读进来。",
        max_result=100,
        path="jsonl 文件路径",
        keyword="要查找的字符串，例如 conversation_id",
    )
    def jsonl_contains(path: str, keyword: str) -> str:
        f = safe(path)
        if not f.is_file():
            return "否（文件不存在）"
        for line in f.read_text(encoding="utf-8").splitlines():
            if keyword in line:
                return "是"
        return "否"

    return reg
