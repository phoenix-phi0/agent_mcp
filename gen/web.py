# -*- coding: utf-8 -*-
"""生成器的网页界面：左边写 .entity，右边实时看产物。

    pip install flask
    py -m gen --web

## 左边直接编辑文本，不做字段表格

`.entity` 本来就是为人写的——一行一个字段：

    字段 title 文本 必填 唯一 标题

表格化反而要点五六下才填完一行，还要维护「表格状态 ↔ 实体对象 ↔ 文本」
三者的同步，几百行 JS 换来的是更慢的输入。

代价是没有类型下拉，得记住有哪些类型。所以页面上列了一行提示。

## 改动即预览，保存和写盘是另外两回事

改文本 → 防抖 300 毫秒 → 重新解析 → 重新生成 → 右边刷新。

解析失败时右边**保留上一版**，只在底栏报错。编辑到一半语法必然不完整，
每敲一个字就清空的话没法边写边看。

「保存」写回 `.entity` 文件，「写盘」把产物落到 `gen/out/`。两个动作
分开，因为它们改的是不同的东西——试着改改实体看产物变成什么样，多数
时候两个都不点。

## 产物写 gen/out/，不直接进项目

往 `routes/` 里扔文件是会立刻生效的——`dsl_http` 下次扫描就把它当真
接口注册了。生成的东西该先过一遍人眼，确认了再自己复制过去。
"""

from pathlib import Path

from tools.entity import EntitySyntaxError
from tools.entity import parse as parse_entity
from tools.entity import validate

from .core import (DEFAULT_DB, ENTITY_DIR, OUT_DIR, PART_LABELS, PARTS,
                   check, generate, write)
from .preview import render as render_ui
from .templates_ import DEFAULT_SET, TemplateError, sets

# 新建时塞进去的模板。
#
# 空文件没用——人得先知道语法长什么样。放一个带各种写法的例子，照着改
# 比对着空白页想省事。末尾的注释列出可用的类型和旗标。
NEW_ENTITY = '''实体 {name} 中文名
  字段 title 文本 必填 唯一 标题
  字段 body 长文本 正文
  字段 status 枚举 draft,published 必填 默认 draft 状态
  字段 count 整数 必填 默认 0 数量
  字段 created_at 文本 必填 默认 now 创建于
结束

# 类型：文本 长文本 整数 小数 日期 布尔 枚举
# 旗标：必填 唯一 索引
# 关联 别的实体名　默认 值（now 表示交给数据库填）
# 主键 字段名　——不写就是隐式的自增 id
'''

PAGE = """<!doctype html>
<html lang="zh"><head><meta charset="utf-8"><title>实体生成器</title>
<style>
 *{box-sizing:border-box}
 body{margin:0;font-family:system-ui,"Microsoft YaHei";background:#111;
      color:#ddd;height:100vh;display:flex;flex-direction:column}
 header{padding:10px 14px;border-bottom:1px solid #333;display:flex;
        gap:12px;align-items:center;flex-wrap:wrap}
 select,button,input{font:inherit;background:#1c1c1c;color:#ddd;
        border:1px solid #444;border-radius:6px;padding:6px 10px}
 button{cursor:pointer} button:hover{border-color:#666}
 button:disabled{opacity:.4;cursor:default}
 button.go{background:#2a3f2a;border-color:#4a6a4a}
 label{display:inline-flex;gap:5px;align-items:center;cursor:pointer;
       user-select:none;font-size:13px}
 label input{margin:0}
 .picks{display:flex;gap:14px;align-items:center}
 .gap{flex:1} .meta{color:#888;font-size:12px}
 .warn{color:#fc6} .err{color:#f77} .ok{color:#7c7}

 main{flex:1;display:flex;min-height:0}
 .pane{flex:1;display:flex;flex-direction:column;min-width:0}
 .pane+.pane{border-left:1px solid #333}
 .pane h3{margin:0;padding:0 14px;font-size:12px;font-weight:normal;
          color:#888;background:#151515;border-bottom:1px solid #262626;
          display:flex;align-items:center;gap:2px;min-height:30px}
 .t{padding:6px 10px;cursor:pointer;border-bottom:2px solid transparent}
 .t:hover{color:#bbb}
 .t.on{color:#ddd;border-bottom-color:#5a7a5a}
 .hidden{display:none !important}
 iframe{flex:1;border:0;background:#fff}
 textarea{flex:1;background:#0d0d0d;color:#ddd;border:0;padding:12px 14px;
          font-family:Consolas,monospace;font-size:13px;line-height:1.7;
          resize:none;outline:none;tab-size:2}
 .out{flex:1;overflow:auto}

 .file{border-bottom:1px solid #222}
 .fh{display:flex;gap:10px;align-items:center;padding:6px 14px;
     background:#171717;cursor:pointer}
 .fh:hover{background:#1d1d1d}
 .path{font-family:Consolas,monospace;font-size:12.5px}
 .size{color:#666;font-size:11px}
 pre{margin:0;padding:9px 14px 14px;background:#0d0d0d;
     font-family:Consolas,monospace;font-size:12px;line-height:1.5;
     white-space:pre-wrap;overflow-x:auto}
 .pad{padding:16px;line-height:1.9;font-size:12px;color:#888}
 code{background:#222;padding:1px 5px;border-radius:4px;
      font-family:Consolas,monospace}
 #bar{padding:7px 14px;border-top:1px solid #333;background:#151515;
      font-size:12px;white-space:pre-wrap;max-height:110px;overflow:auto}
</style></head><body>

<header>
 <select id="file" onchange="load()"></select>
 <button onclick="saveEntity()">保存</button>
 <button onclick="newEntity()" title="新建一个 .entity">新建</button>

 <!-- 勾选框由后端给的 PARTS 渲染，不在这儿写死。
      先前这三个名字前后端各写一遍，后端把 sql 改成 queries 之后这边
      没跟上——后端收到不认识的名字就静默过滤掉，表现成「SQL 不生成」
      而且不报错。一处定义就没这问题了。 -->
 <span class="picks" id="picks"></span>

 <select id="tpl" title="用哪套模板" onchange="run()"></select>
 <input id="db" value="__DB__" size="8" title="接口里用哪个库"
        onchange="run()">
 <button class="go" onclick="dump()">写盘</button>
 <span class="gap"></span>
 <span id="msg" class="meta"></span>
</header>

<main>
 <div class="pane">
  <h3>实体定义　<span style="color:#666">类型：文本 长文本 整数 小数
    日期 布尔 枚举　｜　旗标：必填 唯一 索引　｜　关联 X　默认 X　主键 a b</span></h3>
  <textarea id="src" spellcheck="false"
    placeholder="实体 article 文章
  字段 title 文本 必填 唯一 标题
  字段 views 整数 必填 默认 0 阅读数
结束"></textarea>
 </div>

 <div class="pane">
  <h3>
   <span class="t on" id="t-text" onclick="view('text')">产物</span>
   <span class="t" id="t-view" onclick="view('view')">界面预览</span>
   <span style="color:#666">　改左边就重新生成，写盘才落到 __OUT__</span>
  </h3>
  <div class="out" id="out"><p class="pad">左边写点东西。</p></div>
  <!-- 预览跟产物列表挤在同一块区域，靠显示/隐藏切换。
       并排三栏太挤，而且多数时候看的是文本——预览是偶尔确认一下
       长什么样。 -->
  <iframe id="view" class="hidden" title="界面预览"></iframe>
 </div>
</main>

<div id="bar" class="meta">（还没有内容）</div>

<script>
const $ = id => document.getElementById(id);
let timer = null, 产物 = [], 预览 = "";

async function api(p, b){
  const r = await fetch(p, {method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify(b||{})});
  return r.json();
}
function say(t,c){ const b=$("bar"); b.className=c||"meta"; b.textContent=t; }
function flash(t){ $("msg").textContent=t;
  setTimeout(()=>$("msg").textContent="", 5000); }
function esc(s){ return String(s).replace(/[&<>]/g,
  c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c])); }
function picks(){
  return [...document.querySelectorAll(".picks input:checked")]
    .map(x => x.value);
}

async function boot(){
  const d = await api("/api/files");
  $("file").innerHTML = d.files.map(f=>`<option>${f}</option>`).join("")
    || '<option value="">没有 .entity</option>';
  $("tpl").innerHTML = (d.sets||[]).map(s=>`<option>${s}</option>`).join("")
    || '<option value="">没有模板集</option>';

  // 勾选框照后端给的 PARTS 渲染。ui 默认不勾——它是「起点」而不是
  // 成品，多数时候人已经有界面了，只想重新生成后端。
  $("picks").innerHTML = (d.parts||[]).map(p =>
    `<label><input type="checkbox" value="${p}"`
    + `${p === "ui" ? "" : " checked"} onchange="run()"> `
    + `${d.labels[p] || p}</label>`).join("");

  if (d.files.length) load(); else say("实体目录里没有 .entity 文件","warn");
}

async function load(){
  const d = await api("/api/read", {name:$("file").value});
  if (d.error) return say(d.error,"err");
  $("src").value = d.text;
  run();
}

async function run(){
  const parts = picks();
  if (!parts.length){ 产物=[]; return say("至少勾一样","warn"); }

  const d = await api("/api/preview",
    {text:$("src").value, parts:parts, db:$("db").value,
     tpl:$("tpl").value});

  if (d.error){
    // 解析失败时**保留上一版产物**，不清空右边。编辑到一半语法必然
    // 不完整，每敲一个字就清空的话没法边写边看。
    return say(d.error, "err");
  }

  产物 = d.files;
  预览 = d.preview || "";
  // 正看着预览的话立刻刷新，否则等切过去再填
  if (!$("view").classList.contains("hidden")) $("view").srcdoc = 预览;

  $("out").innerHTML = d.files.map((f,i)=>`
    <div class="file">
      <div class="fh" onclick="toggle(${i})">
        <span class="path">${esc(f.path)}</span>
        <span class="size">${f.lines} 行</span>
        <span class="gap"></span>
        <span class="meta" id="t-${i}">展开</span>
      </div>
      <pre id="b-${i}" style="display:none">${esc(f.text)}</pre>
    </div>`).join("") || '<p class="pad">没有产物。</p>';

  const 行 = [`${d.entities} 个实体，${d.files.length} 个文件`];
  if (d.check.length) 行.push("自检：", ...d.check.map(x=>"  "+x));
  say(行.join("\\n"), d.check.length ? "err" : "ok");
}

function toggle(i){
  const b=$("b-"+i), t=$("t-"+i);
  const 开 = b.style.display === "none";
  b.style.display = 开 ? "block" : "none";
  t.textContent = 开 ? "收起" : "展开";
}

function view(which){
  const 看预览 = which === "view";
  $("out").classList.toggle("hidden", 看预览);
  $("view").classList.toggle("hidden", !看预览);
  $("t-text").classList.toggle("on", !看预览);
  $("t-view").classList.toggle("on", 看预览);

  // 切到预览时才填 iframe。生成时就填的话，每敲一个字都要跑一遍
  // compile_ui 加重建 Vue，而多数时候人看的是文本。
  if (看预览) $("view").srcdoc = 预览 || "";
}

async function saveEntity(){
  const d = await api("/api/save",
    {name:$("file").value, text:$("src").value});
  flash(d.message);
}

async function newEntity(){
  const 名 = prompt("新实体的英文名（也是表名）：", "article");
  if (!名) return;
  const d = await api("/api/new", {name:名});
  if (d.error) return say(d.error, "err");

  // 重新拉文件列表，选中新建的那个
  const f = await api("/api/files");
  $("file").innerHTML = f.files.map(x=>`<option>${x}</option>`).join("");
  $("file").value = d.file;
  load();
  flash(`建了 ${d.file}`);
}

async function dump(){
  if (!产物.length) return say("没东西可写","warn");
  const d = await api("/api/write", {files:产物});
  say(d.messages.join("\\n"), "ok");
  flash(`写了 ${产物.length} 个`);
}

$("src").addEventListener("input", ()=>{
  // 防抖：每敲一个字都解析加生成会卡，300 毫秒察觉不到
  clearTimeout(timer);
  timer = setTimeout(run, 300);
});

boot();
</script></body></html>"""


def make_app(entity_dir: Path = ENTITY_DIR, out_dir: Path = OUT_DIR):
    from flask import Flask, jsonify, request

    app = Flask(__name__)
    app.json.ensure_ascii = False
    entity_dir = Path(entity_dir)

    def body() -> dict:
        return request.get_json(silent=True) or {}

    def safe(name: str) -> Path:
        """只认实体目录里的文件名，不认路径。

        名字来自浏览器。这个服务只监听本机，但没理由留这个口子。
        """
        if not name or "/" in name or "\\" in name or ".." in name:
            raise ValueError(f"文件名不对：{name}")
        p = (entity_dir / name).resolve()
        if p.parent != entity_dir.resolve():
            raise ValueError(f"越界：{name}")
        return p

    @app.get("/")
    def index():
        return (PAGE.replace("__DB__", DEFAULT_DB)
                    .replace("__OUT__", str(out_dir)))

    @app.post("/api/files")
    def api_files():
        if not entity_dir.is_dir():
            return jsonify({"files": [], "sets": sets(),
                            "error": f"没有 {entity_dir}"})
        return jsonify({
            "files": sorted(p.name for p in entity_dir.glob("*.entity")),
            "sets": sets(),
            "parts": list(PARTS),
            "labels": PART_LABELS,
        })

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
            # 存之前备份。实体定义改坏了，配套的产物全跟着错，而这个
            # 文件通常是手写了很久的。
            if p.is_file():
                p.with_suffix(".entity.bak").write_text(
                    p.read_text(encoding="utf-8"), encoding="utf-8")
            p.write_text(d.get("text", ""), encoding="utf-8")
            return jsonify({"message": f"已存 {p.name}（旧的在 .bak）"})
        except (ValueError, OSError) as e:
            return jsonify({"message": f"存不了：{e}"}), 400

    @app.post("/api/new")
    def api_new():
        """新建一个 .entity，塞个能跑的模板进去。

        空文件没用——人得先知道语法长什么样。模板里放一个字段加注释，
        照着改比对着空白页想省事。
        """
        名 = (body().get("name") or "").strip()
        if not 名.isidentifier() or not 名.isascii():
            return jsonify({"error": f"实体名要是字母开头的 ASCII 标识符：{名}"})

        try:
            p = safe(f"{名}.entity")
        except ValueError as e:
            return jsonify({"error": str(e)})
        if p.is_file():
            return jsonify({"error": f"{p.name} 已经有了"})

        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(NEW_ENTITY.format(name=名), encoding="utf-8")
        return jsonify({"file": p.name})

    @app.post("/api/preview")
    def api_preview():
        """文本进、产物出。不落盘。"""
        d = body()
        text = d.get("text", "")
        parts = [p for p in d.get("parts", PARTS) if p in PARTS]
        db = d.get("db") or DEFAULT_DB

        try:
            entities = parse_entity(text)
        except EntitySyntaxError as e:
            return jsonify({"error": f"语法错误：{e}"})
        except Exception as e:
            return jsonify({"error": f"{type(e).__name__}: {e}"})

        if not entities:
            return jsonify({"entities": 0, "files": [], "check": []})

        problems = validate(entities)
        if problems:
            # 校验没过就不生成——基于坏定义生成出来的东西没意义，
            # 而且会盖住真正的问题
            return jsonify({"error": "实体定义有问题：\n  "
                                     + "\n  ".join(problems)})

        tpl = d.get("tpl") or DEFAULT_SET
        files, notes = {}, []
        try:
            for e in entities:
                files.update(generate(e, db, parts, tpl))
                notes += [f"{e.name}：{x}" for x in check(e, db, tpl)]
        except TemplateError as ex:
            return jsonify({"error": f"模板出错：{ex}"})

        # 生成的 .ui 顺带编译一份，给「界面预览」那个标签用。
        # 有几个实体就有几份 .ui，预览只取第一份——并排显示几套界面
        # 反而看不清，要看别的就把那个实体挪到最前面。
        html, 预览问题 = "", []
        ui文件 = [v for k, v in sorted(files.items())
                 if k.startswith("ui/")]
        if ui文件:
            r = render_ui(ui文件[0], entities)
            html = r["html"] or ""
            if r["error"]:
                预览问题 = [f"预览：{r['error']}"]
            else:
                预览问题 = [f"预览：{x}" for x in r["issues"]]

        return jsonify({
            "entities": len(entities),
            "check": notes + 预览问题,
            "preview": html,
            "files": [{"path": k, "text": v, "lines": len(v.splitlines())}
                      for k, v in sorted(files.items())],
        })

    @app.post("/api/write")
    def api_write():
        files = {f["path"]: f["text"] for f in body().get("files", [])}
        if not files:
            return jsonify({"messages": ["没给文件"]}), 400
        return jsonify({"messages": write(files, out_dir)})

    return app


def serve(entity_dir: Path = ENTITY_DIR, host: str = "127.0.0.1",
          port: int = 8100) -> int:
    try:
        app = make_app(Path(entity_dir))
    except ImportError:
        print("缺 flask：pip install flask")
        return 1

    print(f"实体目录 {entity_dir}")
    print(f"产物写到 {OUT_DIR}")
    print(f"\n打开 http://{host}:{port}")
    app.run(host=host, port=port, threaded=True, debug=False)
    return 0
