# -*- coding: utf-8 -*-
"""`.ui` 编辑器：左边写，右边实时看。

    pip install flask
    py -m tools.ui_editor
    py -m tools.ui_editor --port 8100 --dir app2/ui

## 为什么是 Web 不是桌面 GUI

三样东西现成：Flask（dsl_http 那边已经在用）、`compile_ui`（产物就是
最终要的 HTML）、`app.pyw` 那套开窗方式（起服务 + Edge app 模式，看着
跟桌面程序没区别）。

tkinter 要用它自己的控件画预览，跟最终的 Vue 产物长得不一样——那种
「预览」只是示意。PyQt 的 QWebEngineView 能真渲染，但依赖几百 MB。

Web 这条的预览就是真产物，一个 iframe 的事。

## 预览不连真后端

`.ui` 里的动作有「远程」修饰，正常会往后端发请求。预览时那些请求被拦
在前端——点按钮只把表单内容回显成一条消息，不发出去。

理由：编辑器是用来调界面的，点一下就往真库里写东西不合适。而且多数
时候后端根本没起。

代价是「点了之后会发生什么」看不到。要看那个得跑真服务。

## 存盘

改的是 `--dir` 指向的目录（默认 `app2/ui/`）里的 `.ui` 文件。存之前
先备份一份到同名的 `.bak`——编辑器里一个手滑就覆盖掉手写了半天的界面
太容易了。

不做版本历史：那是 git 的事。
"""

import argparse
import json
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import ui_entity                                  # noqa: E402
from tools.entity import EntitySyntaxError                    # noqa: E402
from tools.entity import parse as parse_entity                # noqa: E402
from tools.entity import field_table, options_map             # noqa: E402
from tools.ui import UiSyntaxError, compile_ui                # noqa: E402
from tools.ui import parse as parse_ui                        # noqa: E402

DEFAULT_DIR = ROOT / "app2" / "ui"
DEFAULT_PORT = 8100

# 预览时不挡住生成的 issue 码。跟 build.py 的 BLOCKING 相反——这里尽量
# 让人看到东西，哪怕不完整：编辑到一半的界面必然有各种问题，每次都白屏
# 的话就没法边写边看了。
PREVIEW_SOFT = {"missing_endpoint", "multi_stream", "unknown_endpoint"}


class Workspace:
    """编辑器操作的那个目录。

    .ui 和 .entity 都从这里读——它们本来就该放一起，字段定义和用它的
    界面隔着几层目录的话，改一个要翻半天。
    """

    def __init__(self, path: Path):
        self.dir = Path(path).resolve()

    def files(self) -> list:
        if not self.dir.is_dir():
            return []
        return sorted(p.name for p in self.dir.glob("*.ui"))

    def entity_files(self) -> list:
        if not self.dir.is_dir():
            return []
        return sorted(p.name for p in self.dir.glob("*.entity"))

    def _safe(self, name: str) -> Path:
        """只认目录里的文件名，不认路径。

        名字来自浏览器，带上 ../ 就能跳出去——这个服务虽然只监听本机，
        但没理由留这个口子。
        """
        if "/" in name or "\\" in name or ".." in name:
            raise ValueError(f"文件名不能含路径：{name}")
        p = (self.dir / name).resolve()
        if p.parent != self.dir:
            raise ValueError(f"越界：{name}")
        return p

    def read(self, name: str) -> str:
        p = self._safe(name)
        return p.read_text(encoding="utf-8") if p.is_file() else ""

    def write(self, name: str, text: str) -> str:
        p = self._safe(name)
        if p.is_file():
            # 存之前备份。编辑器里一个手滑就覆盖掉手写了半天的界面，
            # 太容易了；.bak 至少能救回上一版。版本历史是 git 的事。
            p.with_suffix(p.suffix + ".bak").write_text(
                p.read_text(encoding="utf-8"), encoding="utf-8")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return f"已存 {name}（旧的在 {p.name}.bak）"

    def entities(self) -> tuple:
        """读目录下所有 .entity，返回 (实体列表, 出错信息)。"""
        out, errs = [], []
        for name in self.entity_files():
            try:
                out.extend(parse_entity(self.read(name)))
            except EntitySyntaxError as e:
                errs.append(f"{name}：{e}")
        return out, errs


def render(text: str, ws: Workspace) -> dict:
    """把一段 .ui 编译成可预览的 HTML。

    返回 {"html": ..., "issues": [...], "error": ...}。

    解析失败时 html 是 None 而 error 有内容——前端据此决定是换掉 iframe
    还是保留上一版。编辑到一半语法必然不完整，每次都白屏没法用。
    """
    entities, ent_errs = ws.entities()

    try:
        screens = parse_ui(text)
    except UiSyntaxError as e:
        return {"html": None, "issues": [], "error": f"语法错误：{e}"}
    except Exception as e:
        return {"html": None, "issues": [],
                "error": f"{type(e).__name__}: {e}"}

    issues = [f"[实体] {x}" for x in ent_errs]
    if entities:
        issues += [str(i) for i in ui_entity.expand(screens, entities)]

    fields = field_table(entities) if entities else None
    opts = options_map(entities) if entities else {}

    try:
        r = compile_ui(screens, backend="vue", fields=fields,
                       options={"title": "预览", "options_map": opts,
                                "inline": True, "preview": True})
    except Exception:
        return {"html": None, "issues": issues,
                "error": traceback.format_exc(limit=3)}

    issues += [str(i) for i in r.get("issues", [])]
    files = r["result"]["files"]
    html = files.get("index.html", "")

    # inline 没生效时（模板不支持 preview/inline 选项）自己拼一份：
    # 预览必须是单个自包含的 HTML，iframe 里加载不了分开的 css/js。
    if "app.js" in files and "<script>" not in html:
        html = _inline(html, files)
    return {"html": html, "issues": issues, "error": None}


def _inline(html: str, files: dict) -> str:
    """把 style.css 和 app.js 塞进 HTML 里。

    预览走 iframe 的 srcdoc，那里没有服务器，外链的相对路径取不到。
    """
    css = files.get("style.css", "")
    js = files.get("app.js", "")
    if css:
        html = html.replace("</head>", f"<style>{css}</style></head>")
    if js:
        html = html.replace("</body>", f"<script>{js}</script></body>")
    return html


def scaffold(entity_name: str, kind: str, ws: Workspace) -> str:
    """按实体生成一段 .ui 文本，插进编辑器当起点。

    一次性的：生成完就是普通的手写内容，不存在「重新生成冲掉手改」——
    那是代码生成器的老问题，而这里生成器只是个输入辅助。

    字段全给出来不预先排除——删比想起来加容易。
    """
    entities, _ = ws.entities()
    e = next((x for x in entities if x.name == entity_name), None)
    if e is None:
        有 = "、".join(x.name for x in entities) or "无"
        return f"# 没有实体「{entity_name}」。这里有：{有}\n"

    label = e.label or e.name
    if kind == "列表":
        # 列表只列前几个短字段——全列出来横向就爆了。长文本尤其不该进
        # 表格，一行正文能顶十行高。
        cols = [f for f in e.fields if f.type != "长文本"][:4]
        rows = "\n".join(f"    列 {f.name} {f.label or f.name}" for f in cols)
        return (f"界面 列表 {label}列表\n"
                f"  列表 {e.name}s\n"
                f"{rows}\n"
                f"    动作 edit 切到 {label}编辑 编辑\n"
                f"  结束\n"
                f"结束\n")

    return (f"界面 表单 {label}编辑\n"
            f"  分组 主体 竖排 间距 12px\n"
            f"    全部字段 {e.name}\n"
            f"  结束\n"
            f"  分组 底栏 横排 底栏\n"
            f"    动作 save 提交 远程 保存\n"
            f"  结束\n"
            f"结束\n")


PAGE = """<!doctype html>
<html lang="zh"><head><meta charset="utf-8"><title>.ui 编辑器</title>
<style>
 *{box-sizing:border-box}
 body{margin:0;font-family:system-ui,"Microsoft YaHei";background:#111;color:#ddd;
      height:100vh;display:flex;flex-direction:column}
 header{padding:8px 12px;border-bottom:1px solid #333;display:flex;gap:8px;
        align-items:center;flex-wrap:wrap}
 select,button,input{font:inherit;background:#1c1c1c;color:#ddd;border:1px solid #444;
        border-radius:6px;padding:5px 9px}
 button{cursor:pointer} button:hover{border-color:#666}
 main{flex:1;display:flex;min-height:0}
 .pane{flex:1;display:flex;flex-direction:column;min-width:0}
 .pane+.pane{border-left:1px solid #333}
 textarea{flex:1;background:#0d0d0d;color:#ddd;border:0;padding:12px;
          font-family:Consolas,monospace;font-size:13px;line-height:1.6;resize:none;
          outline:none;tab-size:2}
 iframe{flex:1;border:0;background:#fff}
 #issues{max-height:140px;overflow:auto;padding:6px 12px;border-top:1px solid #333;
         font-size:12px;background:#151515}
 .err{color:#f77} .warn{color:#fc6} .ok{color:#7c7}
 .meta{color:#888;font-size:12px}
</style></head><body>

<header>
 <select id="file" onchange="load()"></select>
 <button onclick="save()">保存</button>
 <span class="meta">Ctrl+S 也行</span>
 <span style="flex:1"></span>
 <select id="ent"></select>
 <select id="kind"><option>表单</option><option>列表</option></select>
 <button onclick="gen()">插入骨架</button>
 <span id="msg" class="meta"></span>
</header>

<main>
 <div class="pane"><textarea id="src" spellcheck="false"
   placeholder="在这儿写 .ui，右边实时预览"></textarea></div>
 <div class="pane"><iframe id="view"></iframe></div>
</main>

<div id="issues" class="meta">（还没有内容）</div>

<script>
const $ = id => document.getElementById(id);
let timer = null, lastGood = "";

async function api(path, body) {
  const r = await fetch(path, {method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body || {})});
  return r.json();
}

async function boot() {
  const d = await api("/api/files");
  $("file").innerHTML = d.files.map(f => `<option>${f}</option>`).join("");
  $("ent").innerHTML = d.entities.map(e =>
    `<option value="${e.name}">${e.label || e.name}（${e.fields} 字段）</option>`
  ).join("") || '<option value="">没有实体</option>';
  if (d.files.length) load();
}

async function load() {
  const d = await api("/api/read", {name: $("file").value});
  $("src").value = d.text;
  preview();
}

async function save() {
  const d = await api("/api/write",
    {name: $("file").value, text: $("src").value});
  $("msg").textContent = d.message;
  setTimeout(() => $("msg").textContent = "", 4000);
}

async function gen() {
  const d = await api("/api/scaffold",
    {entity: $("ent").value, kind: $("kind").value});
  // 插在光标处而不是末尾——骨架多半是要接着已有内容往下写的
  const t = $("src"), at = t.selectionStart;
  t.value = t.value.slice(0, at) + d.text + t.value.slice(at);
  t.selectionStart = t.selectionEnd = at + d.text.length;
  t.focus();
  preview();
}

async function preview() {
  const d = await api("/api/preview", {text: $("src").value});
  const box = $("issues");

  if (d.error) {
    // 解析失败时保留上一版预览，不白屏——编辑到一半语法必然不完整，
    // 每敲一个字就清空的话没法边写边看
    box.className = "err";
    box.textContent = d.error;
    return;
  }
  $("view").srcdoc = d.html || "";
  lastGood = d.html || "";

  if (!d.issues.length) {
    box.className = "ok";
    box.textContent = "没有问题";
  } else {
    box.className = "warn";
    box.textContent = d.issues.join("\\n");
  }
}

$("src").addEventListener("input", () => {
  // 防抖：每敲一个字都编译一次会让输入卡顿，而 300 毫秒的延迟
  // 察觉不到
  clearTimeout(timer);
  timer = setTimeout(preview, 300);
});

document.addEventListener("keydown", e => {
  if ((e.ctrlKey || e.metaKey) && e.key === "s") { e.preventDefault(); save(); }
});

boot();
</script></body></html>"""


def make_app(ws: Workspace):
    from flask import Flask, jsonify, request

    app = Flask(__name__)
    app.json.ensure_ascii = False

    @app.get("/")
    def index():
        return PAGE

    @app.post("/api/files")
    def api_files():
        entities, _ = ws.entities()
        return jsonify({
            "files": ws.files(),
            "entities": [{"name": e.name, "label": e.label,
                          "fields": len(e.fields)} for e in entities],
        })

    @app.post("/api/read")
    def api_read():
        name = (request.get_json(silent=True) or {}).get("name", "")
        try:
            return jsonify({"text": ws.read(name)})
        except ValueError as e:
            return jsonify({"text": "", "error": str(e)}), 400

    @app.post("/api/write")
    def api_write():
        d = request.get_json(silent=True) or {}
        try:
            return jsonify({"message": ws.write(d.get("name", ""),
                                                d.get("text", ""))})
        except (ValueError, OSError) as e:
            return jsonify({"message": f"存不了：{e}"}), 400

    @app.post("/api/preview")
    def api_preview():
        text = (request.get_json(silent=True) or {}).get("text", "")
        return jsonify(render(text, ws))

    @app.post("/api/scaffold")
    def api_scaffold():
        d = request.get_json(silent=True) or {}
        return jsonify({"text": scaffold(d.get("entity", ""),
                                         d.get("kind", "表单"), ws)})

    return app


def main() -> int:
    p = argparse.ArgumentParser(description=".ui 编辑器")
    p.add_argument("--dir", default=str(DEFAULT_DIR),
                   help="放 .ui 和 .entity 的目录")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = p.parse_args()

    ws = Workspace(Path(args.dir))
    if not ws.dir.is_dir():
        print(f"目录不存在：{ws.dir}")
        return 1

    print(f"目录 {ws.dir}")
    print(f"  .ui      {'、'.join(ws.files()) or '（无）'}")
    print(f"  .entity  {'、'.join(ws.entity_files()) or '（无）'}")

    try:
        app = make_app(ws)
    except ImportError:
        print("缺 flask：pip install flask")
        return 1

    print(f"\n打开 http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, threaded=True, debug=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
