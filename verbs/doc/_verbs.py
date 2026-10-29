"""doc 包：从文档里取纯文本。

    用包 doc

    设 doc = 读文档 uploads/3f2a….pdf
    如果 {doc.error} 不为空
      返回 {"error":"{doc.error}"} 400
    结束
    打印 {doc.kind} {doc.pages} 页，{doc.paragraphs} 段，{doc.chars} 字

返回 {kind, text, pages, paragraphs, chars, error}：

  kind        pdf / docx / md / txt / csv / tsv（按扩展名）
  text        纯文本。docx 的标题段落前面补「# 」（标题 1）「## 」（标题 2）
              ……，表格一行一行拼成「格 | 格」——后面按章节切块（text 包的
              「切章节」）要靠标题认出哪儿是一课
  pages       页数（pdf），别的格式是 0
  paragraphs  非空的段落（行）数
  chars       text 的字数
  error       读不了时的一句人话，读得了是空串。读不了不抛错：这是上传的
              文件不合格（扫描版、加了密、坏了），不是脚本写错了，脚本判
              error 给用户回 400

**扫描版 PDF**（每页都是图片，没有文字层）取不出字：error 说「需要 OCR，
暂不支持」，不返回一堆空页。判法：平均每页取出的字不到 20 个。

依赖：pdf 用 pypdf（`.venv/bin/pip install pypdf`，见 requirements.txt）；
docx 不用第三方库——它就是个 zip，正文在 word/document.xml，标准库的
zipfile + ElementTree 读得了。md / txt 先按 UTF-8（带不带 BOM 都行）读，不行
再按 GB18030（国标，兼容 GBK）读。

csv / tsv 也按文本读（同一套编码规则，Excel 另存的带 BOM 的 UTF-8 也行），
原样返回，不拆列——要统计的接口自己按行、按逗号切。xlsx 不收，让人另存为
csv。空文件不算错：text 是空串、chars 是 0。

路径限制在工作目录内，跟 data 包一样。
"""

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

# 加载时注入
WORKSPACE = Path(".")
PACK_DIR = Path(".")

# 平均每页取出的字少于这个数，就当没有文字层（扫描版）
MIN_CHARS_PER_PAGE = 20

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _result(kind, text="", pages=0, error=""):
    text = text or ""
    paras = [ln for ln in text.splitlines() if ln.strip()]
    return {"kind": kind, "text": text, "pages": pages, "paragraphs": len(paras),
            "chars": len(text), "error": error}


def read_pdf(path: Path) -> dict:
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError:
        return _result("pdf", error="读 PDF 要 pypdf，没装：.venv/bin/pip install pypdf")
    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            # 只有打开口令为空的（只限制打印、复制的）能解开
            try:
                if not reader.decrypt(""):
                    return _result("pdf", error="这个 PDF 加了密码，打不开。去掉密码再传")
            except Exception:
                return _result("pdf", error="这个 PDF 加了密码，打不开。去掉密码再传")
        pages = [(p.extract_text() or "") for p in reader.pages]
    except (PdfReadError, ValueError, KeyError, OSError) as e:
        return _result("pdf", error=f"PDF 读不了（文件坏了？）：{str(e).splitlines()[0][:80]}")
    n = len(pages)
    text = "\n\n".join(t.strip() for t in pages)
    if n and len(re.sub(r"\s", "", text)) < MIN_CHARS_PER_PAGE * n:
        return _result("pdf", pages=n,
                       error=f"这个 PDF 取不出文字（{n} 页几乎没有文字层，多半是扫描版），"
                             f"需要 OCR，暂不支持。换成有文字的 PDF、docx 或 md 再传")
    return _result("pdf", text, pages=n)


def _style_level(p) -> int:
    """段落是不是标题，是第几级（1–6）；不是标题回 0。

    Word 的内置标题样式 ID 是 Heading1…（英文版）或 1、2…（中文版存成数字），
    有的模板叫「标题1」。outlineLvl（大纲级别）也算。
    """
    ppr = p.find(f"{_W}pPr")
    if ppr is None:
        return 0
    st = ppr.find(f"{_W}pStyle")
    if st is not None:
        v = st.get(f"{_W}val") or ""
        m = re.match(r"^(?:heading|标题|title)?\s*([1-6])$", v, re.I)
        if m:
            return int(m.group(1))
        if v.lower() == "title":
            return 1
    ol = ppr.find(f"{_W}outlineLvl")
    if ol is not None:
        try:
            return min(int(ol.get(f"{_W}val") or "9") + 1, 6)
        except ValueError:
            return 0
    return 0


def _para_text(p) -> str:
    out = []
    for el in p.iter():
        if el.tag == f"{_W}t":
            out.append(el.text or "")
        elif el.tag == f"{_W}tab":
            out.append("\t")
        elif el.tag in (f"{_W}br", f"{_W}cr"):
            out.append("\n")
    return "".join(out)


def read_docx(path: Path) -> dict:
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError, OSError):
        return _result("docx", error="docx 读不了：不是有效的 Word 文档（.doc 老格式要先另存为 .docx）")
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as e:
        return _result("docx", error=f"docx 读不了：正文 XML 坏了（{e}）")
    body = root.find(f"{_W}body")
    lines = []
    for el in (body if body is not None else []):
        if el.tag == f"{_W}p":
            t = _para_text(el).strip()
            if not t:
                continue
            lvl = _style_level(el)
            lines.append(("#" * lvl + " " + t) if lvl else t)
        elif el.tag == f"{_W}tbl":
            for tr in el.iter(f"{_W}tr"):
                cells = [" ".join(_para_text(p).strip() for p in tc.iter(f"{_W}p")).strip()
                         for tc in tr.iter(f"{_W}tc")]
                if any(cells):
                    lines.append(" | ".join(cells))
    return _result("docx", "\n\n".join(lines))


def read_text_file(path: Path, kind: str) -> dict:
    data = path.read_bytes()
    if b"\x00" in data[:4096]:
        return _result(kind, error="这是二进制文件，不是纯文本")
    for enc in ("utf-8-sig", "gb18030"):
        try:
            return _result(kind, data.decode(enc).replace("\r\n", "\n").replace("\r", "\n"))
        except UnicodeDecodeError:
            continue
    return _result(kind, error="文字编码认不出来（不是 UTF-8 也不是 GBK），另存为 UTF-8 再传")


def read_document(path: Path) -> dict:
    """按扩展名读一个文档。Python 里直接调也行（测试用）。"""
    path = Path(path)
    kind = path.suffix.lower().lstrip(".")
    if not path.is_file():
        return _result(kind, error=f"文件不在：{path.name}")
    if kind == "pdf":
        return read_pdf(path)
    if kind == "docx":
        return read_docx(path)
    if kind in ("md", "txt", "markdown", "csv", "tsv"):
        return read_text_file(path, "md" if kind == "markdown" else kind)
    return _result(kind, error=f"不支持 .{kind}，只收 pdf、docx、md、txt、csv、tsv")


def register(reg, workspace):
    workspace = Path(workspace).resolve()

    @reg.verb("读文档（pdf、docx、md、txt、csv、tsv）取纯文本，返回 {kind, text, pages, paragraphs, "
              "chars, error}。读不了时 error 是一句人话（扫描版 PDF 说要 OCR）。"
              "例如 设 doc = 读文档 uploads/a.pdf")
    def 读文档(路径: str) -> dict:
        p = (workspace / str(路径 or "")).resolve()
        if p != workspace and workspace not in p.parents:
            raise ValueError(f"路径越界：{路径}")
        return read_document(p)
