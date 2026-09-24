"""日语教师的本地对话界面。

用法：
    py -m agents.serve            然后打开 http://127.0.0.1:8080
    py -m agents.serve --port 9000

只用 starlette + uvicorn，跟 fs.py 依赖相同，不用额外装东西。
跟 MCP 服务器互不影响，可以同时开着。

两种模式：

  对话模式  走 agent，有上下文，能解释语感、回答开放问题。
            token 消耗随对话增长。

  练习模式  纯状态机 + 题库，一次一题，答完立刻判。
            零模型调用，token 消耗为零，可以一直刷。

练习模式为什么不走 agent：出题只需要课程 ID，判题只需要题号和作答，
两步都跟对话历史无关。让模型参与既慢又可能判错，还要为每轮重发全部历史。
"""

import argparse
import json
import sys
import traceback
from pathlib import Path

import uvicorn
from starlette.applications import Starlette
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route

BASE = Path(__file__).resolve().parent.parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

WORKSPACE = BASE / "workspace" / "japanese"
BANK = "content/n2n3/题库"

# learner_id -> Agent
_agents: dict = {}
# learner_id -> 练习状态 {"课程":..., "考点":..., "题号":..., "对":n, "总":n, "错题":[...]}
_drills: dict = {}


def _teacher(learner: str):
    from agents.japanese import make_teacher, init_workspace
    if learner not in _agents:
        init_workspace()
        _agents[learner] = make_teacher()
    return _agents[learner]


def _verbs():
    """动词表，用于练习模式直接调题库动词。"""
    from tools import make_verbs
    from tools.dsl import DSLEngine
    if "reg" not in _verbs.__dict__:
        reg = make_verbs()
        reg.load_packs(BASE / "verbs", ["common", "quiz", "japanese"],
                       workspace=WORKSPACE)
        _verbs.reg = reg
    return _verbs.reg


def call_verb(name: str, *args) -> str:
    """直接调一个动词，不经过 DSL 引擎。"""
    v = _verbs()
    if not v.has(name):
        return f"[没有动词] {name}"
    params = v.bind(name, [str(a) for a in args])
    kind, impl = v.resolve(name)
    if kind != "python":
        return f"[{name} 不是 Python 动词]"
    return str(impl(**params))


def _reload():
    """清掉模块缓存，让改过的代码生效。"""
    for name in [n for n in list(sys.modules) if n.startswith(("agents", "tools"))]:
        if name != "agents.serve":
            del sys.modules[name]
    _agents.clear()
    _verbs.__dict__.pop("reg", None)


# ----------------------------------------------------------------------
# 练习模式：出题 → 等答 → 判题 → 下一题
# ----------------------------------------------------------------------


def drill_start(learner: str, 课程: str, 考点: str = "") -> dict:
    _drills[learner] = {
        "课程": 课程, "考点": 考点,
        "题号": "", "对": 0, "总": 0, "错题": [],
    }
    return drill_next(learner)


def drill_next(learner: str) -> dict:
    st = _drills.get(learner)
    if not st:
        return {"error": "还没开始练习"}

    题号 = call_verb("挑题号", BANK, "1", st["课程"], st["考点"])
    if not 题号 or 题号.startswith("["):
        return {"error": f"没有匹配的题目：课程={st['课程']} 考点={st['考点'] or '不限'}"}

    st["题号"] = 题号
    题干 = call_verb("取题", BANK, 题号)
    return {"mode": "drill", "question": 题干, "stat": _stat(st)}


def drill_answer(learner: str, 作答: str) -> dict:
    st = _drills.get(learner)
    if not st or not st["题号"]:
        return {"error": "当前没有待答的题"}

    结果 = call_verb("判题", BANK, st["题号"], 作答)
    对了 = 结果.startswith("○")

    st["总"] += 1
    if 对了:
        st["对"] += 1
    else:
        st["错题"].append(st["题号"])
    st["题号"] = ""

    return {"mode": "drill", "verdict": 结果, "correct": 对了, "stat": _stat(st)}


def _stat(st: dict) -> str:
    if not st["总"]:
        return f"{st['课程']}　尚未作答"
    比例 = call_verb("算比例", st["对"], st["总"])
    return f"{st['课程']}　{st['对']}/{st['总']}（{比例}%）"


def drill_stop(learner: str) -> dict:
    st = _drills.pop(learner, None)
    if not st:
        return {"text": "本来就没在练习。"}
    if not st["总"]:
        return {"text": "练习结束，没有作答记录。"}
    比例 = call_verb("算比例", st["对"], st["总"])
    错 = "，".join(st["错题"]) if st["错题"] else "无"
    return {"text": f"练习结束：{st['对']}/{st['总']}（{比例}%）\n错题：{错}"}


# ----------------------------------------------------------------------

PAGE = """<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>JP-E01-π 日语教师</title>
<style>
  :root {
    --bg:#faf9f7; --panel:#fff; --line:#e6e2dc;
    --ink:#2b2825; --dim:#8a827a; --accent:#6b5b95;
    --user:#eef1f8; --tool:#f5f2ed; --ok:#3d7a4e; --no:#a8443c;
  }
  * { box-sizing:border-box; }
  body {
    margin:0; background:var(--bg); color:var(--ink);
    font:15px/1.7 -apple-system,"Hiragino Sans","Noto Sans CJK SC",
         "Microsoft YaHei",sans-serif;
    display:flex; flex-direction:column; height:100vh;
  }
  header {
    padding:12px 20px; border-bottom:1px solid var(--line);
    background:var(--panel); display:flex; align-items:center; gap:12px;
    flex-wrap:wrap;
  }
  header h1 { font-size:15px; margin:0; font-weight:600; }
  header .sp { flex:1; }
  header input, header select {
    padding:4px 8px; border:1px solid var(--line);
    border-radius:5px; font:inherit; font-size:13px;
  }
  header input { width:80px; }
  header button {
    padding:5px 12px; border:1px solid var(--line); background:var(--panel);
    border-radius:5px; cursor:pointer; font:inherit; font-size:13px;
  }
  header button:hover { background:var(--tool); }
  header button.on { background:var(--accent); color:#fff; border-color:var(--accent); }
  #stat { font-size:12px; color:var(--dim); font-variant-numeric:tabular-nums; }

  #log { flex:1; overflow-y:auto; padding:24px 20px; }
  .wrap { max-width:760px; margin:0 auto; }
  .msg { margin-bottom:22px; }
  .who { font-size:12px; color:var(--dim); margin-bottom:5px; }
  .body { white-space:pre-wrap; word-break:break-word; }
  .user .body {
    background:var(--user); padding:10px 14px; border-radius:10px;
    display:inline-block; max-width:100%;
  }
  .ok .body { color:var(--ok); }
  .no .body { color:var(--no); }
  .tools {
    margin-top:10px; font-size:12px; color:var(--dim);
    background:var(--tool); border-radius:8px; padding:8px 12px;
    font-family:ui-monospace,"SF Mono",Menlo,monospace; line-height:1.6;
  }
  .tools summary { cursor:pointer; outline:none; }
  .tools div { margin-top:5px; white-space:pre-wrap; }
  .err { color:var(--no); }

  footer { border-top:1px solid var(--line); background:var(--panel); padding:14px 20px; }
  .row { max-width:760px; margin:0 auto; display:flex; gap:10px; }
  textarea {
    flex:1; resize:none; padding:10px 12px; border:1px solid var(--line);
    border-radius:8px; font:inherit; min-height:46px; max-height:180px;
  }
  textarea:focus { outline:none; border-color:var(--accent); }
  #send {
    padding:0 20px; border:none; background:var(--accent); color:#fff;
    border-radius:8px; cursor:pointer; font:inherit;
  }
  #send:disabled { opacity:.45; cursor:default; }
  .hint { max-width:760px; margin:6px auto 0; font-size:12px; color:var(--dim); }
</style>
</head>
<body>

<header>
  <h1>JP-E01-π</h1>
  <label style="font-size:13px;color:var(--dim)">学习者
    <input id="learner" value="φ-0">
  </label>
  <button id="mode-chat" class="on">对话</button>
  <button id="mode-drill">练习</button>
  <span id="drill-opts" style="display:none">
    <select id="course">
      <option>doushi_01</option><option>doushi_02</option>
      <option>doushi_03</option><option>doushi_04</option>
      <option>fukushi_01</option><option>fukushi_02</option><option>fukushi_03</option>
      <option>keiyoshi_01</option><option>keiyoshi_02</option>
      <option>keiyoshi_03</option><option>keiyoshi_04</option>
      <option>onomatope_01</option>
    </select>
    <select id="kind">
      <option value="">全部考点</option>
      <option value="词义">词义</option>
      <option value="汉字书写">汉字书写</option>
    </select>
  </span>
  <button id="reset">重置</button>
  <span class="sp"></span>
  <span id="stat"></span>
</header>

<div id="log"><div class="wrap" id="wrap"></div></div>

<footer>
  <div class="row">
    <textarea id="input" placeholder="说点什么…（Enter 发送，Shift+Enter 换行）"></textarea>
    <button id="send">发送</button>
  </div>
  <div class="hint" id="hint">出题、批改、复习都来自本地教材。</div>
</footer>

<script>
const wrap=document.getElementById('wrap'), input=document.getElementById('input'),
      send=document.getElementById('send'), stat=document.getElementById('stat'),
      learner=document.getElementById('learner'), hint=document.getElementById('hint'),
      course=document.getElementById('course'), kind=document.getElementById('kind'),
      opts=document.getElementById('drill-opts');
let mode='chat';

function add(who,text,cls){
  const m=document.createElement('div');
  m.className='msg '+(cls||'');
  m.innerHTML='<div class="who"></div><div class="body"></div>';
  m.querySelector('.who').textContent=who;
  m.querySelector('.body').textContent=text;
  wrap.appendChild(m);
  document.getElementById('log').scrollTop=1e9;
  return m;
}
function addTools(msg,calls){
  if(!calls||!calls.length) return;
  const d=document.createElement('details'); d.className='tools';
  d.innerHTML='<summary>'+calls.length+' 次工具调用</summary>';
  for(const c of calls){
    const l=document.createElement('div');
    l.textContent=c.name+'('+c.arguments+')\\n  → '+c.result;
    d.appendChild(l);
  }
  msg.appendChild(d);
}
async function post(url,data){
  const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},
                          body:JSON.stringify(data)});
  return r.json();
}

function setMode(m){
  mode=m;
  document.getElementById('mode-chat').classList.toggle('on',m==='chat');
  document.getElementById('mode-drill').classList.toggle('on',m==='drill');
  opts.style.display = m==='drill' ? '' : 'none';
  input.placeholder = m==='drill'
    ? '写下你的答案…（选择题写 A/B/C/D）'
    : '说点什么…（Enter 发送，Shift+Enter 换行）';
  hint.textContent = m==='drill'
    ? '练习模式：一次一题，答完立刻判，不调用模型。'
    : '对话模式：可以问语感、要求讲解，会消耗 token。';
}

document.getElementById('mode-chat').onclick=()=>{ setMode('chat'); };
document.getElementById('mode-drill').onclick=async()=>{
  setMode('drill');
  const d=await post('/drill/start',
    {learner:learner.value, 课程:course.value, 考点:kind.value});
  show(d);
};
course.onchange=kind.onchange=async()=>{
  if(mode!=='drill') return;
  const d=await post('/drill/start',
    {learner:learner.value, 课程:course.value, 考点:kind.value});
  show(d);
};

function show(d){
  if(d.error){ const m=add('出错',d.error); m.querySelector('.body').classList.add('err'); return; }
  if(d.question) add('题目',d.question);
  if(d.verdict) add('批改',d.verdict, d.correct?'ok':'no');
  if(d.text) add('系统',d.text);
  if(d.stat) stat.textContent=d.stat;
}

async function go(){
  const text=input.value.trim();
  if(!text) return;
  input.value=''; input.style.height='auto';
  add('你',text,'user');
  send.disabled=true;

  try{
    if(mode==='drill'){
      const d=await post('/drill/answer',{learner:learner.value, 作答:text});
      show(d);
      if(!d.error){
        const n=await post('/drill/next',{learner:learner.value});
        show(n);
      }
    }else{
      const pending=add('老师','…');
      const d=await post('/chat',{message:text, learner:learner.value});
      pending.remove();
      if(d.error){ const m=add('出错',d.error); m.querySelector('.body').classList.add('err'); }
      else{
        const m=add('老师',d.reply);
        addTools(m,d.calls);
        stat.textContent=d.usage.toLocaleString()+' token';
      }
    }
  }catch(e){
    const m=add('出错',String(e)); m.querySelector('.body').classList.add('err');
  }
  send.disabled=false; input.focus();
}

send.onclick=go;
input.onkeydown=e=>{ if(e.key==='Enter'&&!e.shiftKey){ e.preventDefault(); go(); } };
input.oninput=()=>{ input.style.height='auto';
  input.style.height=Math.min(input.scrollHeight,180)+'px'; };

document.getElementById('reset').onclick=async()=>{
  const d=await post('/reset',{learner:learner.value});
  wrap.innerHTML=''; stat.textContent='';
  add('系统', d.text || '已重置，代码也重新加载了。');
  setMode('chat');
};

input.focus();
</script>
</body>
</html>
"""


async def home(request):
    return HTMLResponse(PAGE)


async def chat(request):
    try:
        data = await request.json()
        message = (data.get("message") or "").strip()
        learner = (data.get("learner") or "φ-0").strip() or "φ-0"
        if not message:
            return JSONResponse({"error": "没有内容"})

        agent = _teacher(learner)
        before = len(agent.tool_log)
        reply = agent.send(message)
        new_calls = agent.tool_log[before:]

        bodies = [
            c["result"] for c in new_calls
            if c["name"] == "run_flow" and not c["result"].startswith("[")
        ]
        if bodies:
            reply = "\n\n".join(bodies) + "\n\n———\n" + reply

        return JSONResponse({
            "reply": reply,
            "usage": agent.usage["total"],
            "calls": [
                {"name": c["name"], "arguments": c["arguments"][:120],
                 "result": c["result"][:300]}
                for c in new_calls
            ],
        })
    except Exception:
        return JSONResponse({"error": traceback.format_exc(limit=3)})


async def drill_start_route(request):
    try:
        d = await request.json()
        learner = (d.get("learner") or "φ-0").strip() or "φ-0"
        return JSONResponse(drill_start(learner, d.get("课程", ""), d.get("考点", "")))
    except Exception:
        return JSONResponse({"error": traceback.format_exc(limit=3)})


async def drill_answer_route(request):
    try:
        d = await request.json()
        learner = (d.get("learner") or "φ-0").strip() or "φ-0"
        return JSONResponse(drill_answer(learner, d.get("作答", "")))
    except Exception:
        return JSONResponse({"error": traceback.format_exc(limit=3)})


async def drill_next_route(request):
    try:
        d = await request.json()
        learner = (d.get("learner") or "φ-0").strip() or "φ-0"
        return JSONResponse(drill_next(learner))
    except Exception:
        return JSONResponse({"error": traceback.format_exc(limit=3)})


async def reset(request):
    d = await request.json()
    learner = (d.get("learner") or "φ-0").strip() or "φ-0"
    summary = drill_stop(learner)
    _reload()
    _agents.pop(learner, None)
    return JSONResponse({"ok": True, "text": summary.get("text")})


app = Starlette(routes=[
    Route("/", home),
    Route("/chat", chat, methods=["POST"]),
    Route("/drill/start", drill_start_route, methods=["POST"]),
    Route("/drill/answer", drill_answer_route, methods=["POST"]),
    Route("/drill/next", drill_next_route, methods=["POST"]),
    Route("/reset", reset, methods=["POST"]),
])


def main():
    p = argparse.ArgumentParser(description="日语教师对话界面")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8080)
    args = p.parse_args()
    print(f"打开 http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
