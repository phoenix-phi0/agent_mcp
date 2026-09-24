# -*- coding: utf-8 -*-
"""`.ui` 编辑器：左边写，右边实时看界面。

    py gen/edit.pyw              双击也行
    py -m gen --edit             从命令行起，带控制台看报错

改的是 `gen/out/ui/` 下的东西——生成器出骨架，这儿接着改，改完再复制
进项目。

## 跟生成器分开入口，但放同一个包

生成器是「实体 → 骨架」，编辑器是「骨架 → 成品」。工作节奏完全不同：
生成是偶尔点一下，编辑是一直在敲，所以两个页面、两个入口。

但它们共用 `preview.py`（编译成可预览的 HTML）、共用产物目录、共用
实体定义——分成两个包的话那些都要跨包 import，不如放一起。

## 字段表从 entities/ 读

`.ui` 里的 `全部字段 article` 要展开，得知道实体长什么样。不从编辑
目录找——生成出来的 `.ui` 在 `gen/out/ui/`，那儿不会有 `.entity`。
"""

from pathlib import Path

from .core import ENTITY_DIR, OUT_DIR
from .preview import render

UI_DIR = OUT_DIR / "ui"

# 新建时塞进去的模板。
#
# 空文件预览是白的，看不出哪儿写错了。给一个最小的能跑的界面，照着改
# 比对着空白页想省事。
NEW_UI = '''界面 表单 新界面
  分组 主体 竖排 间距 12px
    字段 name 文本 名字
    字段 note 长文本 备注
  结束

  分组 底栏 横排 底栏
    动作 save 提交 远程 保存
  结束
结束

# 角色：表单 列表 对话 自定义
# 块：分组 列表 浮层
# 行：字段 列 动作 文案 消息流 显示 全部字段
# 用实体的字段：全部字段 article　或　字段 article.title
'''

PAGE = """<!doctype html>
<html lang="zh"><head><meta charset="utf-8"><title>.ui 编辑器</title>
<style>
 *{box-sizing:border-box}
 body{margin:0;font-family:system-ui,"Microsoft YaHei";background:#111;
      color:#ddd;height:100vh;display:flex;flex-direction:column}
 header{padding:9px 14px;border-bottom:1px solid #333;display:flex;
        gap:10px;align-items:center;flex-wrap:wrap}
 select,button,input{font:inherit;background:#1c1c1c;color:#ddd;
        border:1px solid #444;border-radius:6px;padding:6px 10px}
 button{cursor:pointer} button:hover{border-color:#666}
 .gap{flex:1} .meta{color:#888;font-size:12px}
 .warn{color:#fc6} .err{color:#f77} .ok{color:#7c7}

 main{flex:1;display:flex;min-height:0}
 .pane{flex:1;display:flex;flex-direction:column;min-width:0}
 .pane+.pane{border-left:1px solid #333}
 .pane h3{margin:0;padding:6px 14px;font-size:12px;font-weight:normal;
          color:#888;background:#151515;border-bottom:1px solid #262626}
 textarea{flex:1;background:#0d0d0d;color:#ddd;border:0;padding:12px 14px;
          font-family:Consolas,monospace;font-size:13px;line-height:1.7;
          resize:none;outline:none;tab-size:2}
 iframe{flex:1;border:0;background:#fff}
 #bar{padding:7px 14px;border-top:1px solid #333;background:#151515;
      font-size:12px;white-space:pre-wrap;max-height:120px;overflow:auto}
</style></head><body>

<header>
 <select id="file" onchange="load()"></select>
 <button onclick="save()">保存</button>
 <button onclick="newFile()" title="新建一个 .ui">新建</button>
 <span class="meta">Ctrl+S</span>
 <span class="gap"></span>
 <span id="msg" class="meta"></span>
</header>

<main>
 <div class="pane">
  <h3>.ui 源码</h3>
  <textarea id="src" spellcheck="false"
    placeholder="界面 表单 文章编辑
  分组 主体 竖排
    全部字段 article
  结束
结束"></textarea>
 </div>
 <div class="pane">
  <h3>界面预览　<span style="color:#666">改左边就重新渲染</span></h3>
  <iframe id="view" title="预览"></iframe>
 </div>
</main>

<div id="bar" class="meta">（还没有内容）</div>

<script>
const $ = id => document.getElementById(id);
let timer = null;

async function api(p,b){
  const r = await fetch(p,{method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify(b||{})});
  return r.json();
}
function say(t,c){ const b=$("bar"); b.className=c||"meta"; b.textContent=t; }
function flash(t){ $("msg").textContent=t;
  setTimeout(()=>$("msg").textContent="",4000); }

async function boot(){
  const d = await api("/api/files");
  $("file").innerHTML = d.files.map(f=>`<option>${f}</option>`).join("")
    || '<option value="">没有 .ui 文件</option>';
  if (d.error) say(d.error,"err");
  else if (!d.files.length)
    say("目录里没有 .ui。先跑一次生成器：py -m gen --all --write","warn");
  else load();
}

async function load(){
  const d = await api("/api/read",{name:$("file").value});
  if (d.error) return say(d.error,"err");
  $("src").value = d.text;
  preview();
}

async function save(){
  const d = await api("/api/save",
    {name:$("file").value, text:$("src").value});
  flash(d.message);
}

async function refreshList(选中){
  const d = await api("/api/files");
  $("file").innerHTML = d.files.map(f=>`<option>${f}</option>`).join("")
    || '<option value="">没有 .ui 文件</option>';
  if (选中) $("file").value = 选中;
  return d.files;
}

async function newFile(){
  const 名 = prompt("新界面文件的名字（不用带 .ui）：", "新界面");
  if (!名) return;
  const d = await api("/api/new", {name:名});
  if (d.error) return say(d.error,"err");
  await refreshList(d.file);
  load();
  flash(`建了 ${d.file}`);
}

async function preview(){
  const d = await api("/api/preview",{text:$("src").value});

  if (d.error){
    // 解析失败时**保留上一版预览**，不清空 iframe。编辑到一半语法
    // 必然不完整，每敲一个字就白屏的话没法边写边看。
    return say(d.error,"err");
  }
  $("view").srcdoc = d.html || "";
  say(d.issues.length ? d.issues.join("\\n") : "没有问题",
      d.issues.length ? "warn" : "ok");
}

$("src").addEventListener("input", ()=>{
  // 防抖：每敲一个字都编译加重建 Vue 会卡，300 毫秒察觉不到
  clearTimeout(timer);
  timer = setTimeout(preview, 300);
});

document.addEventListener("keydown", e=>{
  if ((e.ctrlKey||e.metaKey) && e.key === "s"){ e.preventDefault(); save(); }
});

boot();
</script></body></html>"""


def make_app(ui_dir: Path = UI_DIR, entity_dir: Path = ENTITY_DIR):
    from flask import Flask, jsonify, request
    from tools.entity import EntitySyntaxError
    from tools.entity import parse as parse_entity

    app = Flask(__name__)
    app.json.ensure_ascii = False
    ui_dir = Path(ui_dir).resolve()
    entity_dir = Path(entity_dir)

    def body() -> dict:
        return request.get_json(silent=True) or {}

    def safe(name: str) -> Path:
        """只认目录里的文件名，不认路径。

        名字来自浏览器。这个服务只监听本机，但没理由留这个口子。
        """
        if not name or "/" in name or "\\" in name or ".." in name:
            raise ValueError(f"文件名不对：{name}")
        p = (ui_dir / name).resolve()
        if p.parent != ui_dir:
            raise ValueError(f"越界：{name}")
        return p

    def 实体():
        """读实体定义，给「全部字段」展开用。

        一个文件解析失败不影响别的——编辑时多半正有一个写到一半，不该
        因此让整个字段表消失。
        """
        out = []
        if not entity_dir.is_dir():
            return out
        for f in sorted(entity_dir.glob("*.entity")):
            try:
                out.extend(parse_entity(f.read_text(encoding="utf-8")))
            except (EntitySyntaxError, OSError):
                continue
        return out

    @app.get("/")
    def index():
        return PAGE

    @app.post("/api/files")
    def api_files():
        if not ui_dir.is_dir():
            return jsonify({"files": [], "error": f"没有 {ui_dir}"})
        return jsonify({"files": sorted(p.name for p in ui_dir.glob("*.ui"))})

    @app.post("/api/read")
    def api_read():
        try:
            return jsonify({"text": safe(body().get("name", ""))
                            .read_text(encoding="utf-8")})
        except (ValueError, OSError) as e:
            return jsonify({"text": "", "error": str(e)}), 400

    @app.post("/api/save")
    def api_save():
        d = body()
        try:
            p = safe(d.get("name", ""))
            # 存之前备份。手改了半天的界面被一次误存冲掉太容易了。
            if p.is_file():
                p.with_suffix(".ui.bak").write_text(
                    p.read_text(encoding="utf-8"), encoding="utf-8")
            p.write_text(d.get("text", ""), encoding="utf-8")
            return jsonify({"message": f"已存 {p.name}（旧的在 .bak）"})
        except (ValueError, OSError) as e:
            return jsonify({"message": f"存不了：{e}"}), 400

    @app.post("/api/new")
    def api_new():
        """新建一个 .ui，塞个能渲染的模板进去。

        空文件预览是白的，看不出哪儿写错了。模板给一个最小的能跑的
        界面，照着改比对着空白页想省事。
        """
        名 = (body().get("name") or "").strip()
        if not 名:
            return jsonify({"error": "没给名字"})
        if not 名.endswith(".ui"):
            名 += ".ui"

        try:
            p = safe(名)
        except ValueError as e:
            return jsonify({"error": str(e)})
        if p.is_file():
            return jsonify({"error": f"{p.name} 已经有了"})

        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(NEW_UI, encoding="utf-8")
        return jsonify({"file": p.name})

    @app.post("/api/preview")
    def api_preview():
        return jsonify(render(body().get("text", ""), 实体()))

    return app


def serve(ui_dir: Path = UI_DIR, entity_dir: Path = ENTITY_DIR,
          host: str = "127.0.0.1", port: int = 8110) -> int:
    ui_dir = Path(ui_dir)
    if not ui_dir.is_dir():
        print(f"目录不存在：{ui_dir}")
        print("先跑一次生成器：py -m gen --all --write")
        return 1

    files = sorted(p.name for p in ui_dir.glob("*.ui"))
    print(f"编辑目录 {ui_dir}")
    print(f"  {'、'.join(files) or '（没有 .ui 文件）'}")

    try:
        app = make_app(ui_dir, Path(entity_dir))
    except ImportError:
        print("\n缺 flask：pip install flask")
        return 1

    print(f"\n打开 http://{host}:{port}")
    app.run(host=host, port=port, threaded=True, debug=False)
    return 0
