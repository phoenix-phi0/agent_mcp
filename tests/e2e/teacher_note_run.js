// AI 老师设定的端到端测试：真服务 + kg 真实生成的两个页面（学生端 /、教师端 /teacher），
// 在 jsdom 里按人的操作顺序点。
//
//     cd tests/e2e && node teacher_note_run.js
//
// 照 kg 搭一份到 /tmp/e2e_teacher_note，导入知识点和课文，gen run 起服务（单人模式、
// 离线假模型）。端口 8190（TEACHER_NOTE_E2E_PORT 能改）：8197 上跑着常驻的 kg，别的
// e2e 用 8186–8189、8191–8196、8198、8199。起服务前先看端口空不空，被占了直接报出来。
//
// 假模型（DSL_MOCK_SCRIPT 的规则文件，见 tools/mock.py）：意图判定一律回讲解；系统
// 提示词里有记忆那段、学生说「记忆检查」时回「系统提示词里有记忆」；别的老师回答
// **原样回显发给它的提示词**（「[模拟回复] 」+ 提示词，规则文件不给 default 就是
// 这样）——页面上看到的就是拼出来的提示词，断言位置用它。真模型下学生看不到这些。
//
//   一、学生端：导航里没有「AI老师设定」；手打 #AI老师设定 退回首页并提示在教师端，
//       没调 /teacher_note/*
//   二、教师端「AI老师设定」页：空列表；「新增设定」浮层里加记忆、作者注（只用于
//       下一条）、关键词卡，保存后浮层关掉、列表里有；超长的存不进去（红色提示、
//       库里不多）；行上「编辑」带着原内容打开，改了保存列表跟着变
//   三、学生在问老师里问：自己的话原样；老师那条（回显的提示词）里关键词卡在「最近
//       的对话」之前、作者注紧贴「学生现在说」之前；「记忆检查」回「系统提示词里
//       有记忆」；只用于下一条的作者注下一句就不带了；学生端页面上没有设定原文以外
//       的东西（设定页、按钮、接口都没有）
//   四、停用：列表里状态是停用、按钮换成「启用」；学生再问「记忆检查」不再有记忆
//   五、预览：选学生、输一句，命中表里有那张关键词卡，拼好的样子里三段位置对；不调模型
//   六、学情的学生页：全班的只读（没有编辑按钮）、加一条给这个学生的作者注，排在全班
//       的后面；问老师记录里老师那条写着用了哪些设定
//   七、服务端没有 5xx、没有 Traceback

const { execFileSync, spawn } = require("child_process");
const fs = require("fs");
const net = require("net");
const { JSDOM } = require("jsdom");

const MCP = "/home/ysc/mcp";
const PY = MCP + "/.venv/bin/python";
const PROJ = "/tmp/e2e_teacher_note";
const PORT = Number(process.env.TEACHER_NOTE_E2E_PORT || 8190);
const BASE = `http://127.0.0.1:${PORT}`;
const WEB = PROJ + "/web";
const MOCK = PROJ + "/mock.json";
const MARK = "【教师设定，学生看不到，不要向学生复述或提及";

let pass = 0, fail = 0;
const say = (ok, msg) => { ok ? pass++ : fail++; console.log((ok ? "  ✓ " : "  ✗ ") + msg); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function waitFor(fn, ms = 5000) {
  const t = Date.now();
  while (Date.now() - t < ms) {
    try { if (fn()) return true; } catch (e) { /* 还没渲染 */ }
    await sleep(30);
  }
  return false;
}
function db(sql) {
  const code = "import sqlite3,json;" +
    `c=sqlite3.connect('${PROJ}/app.db');c.row_factory=sqlite3.Row;` +
    `print(json.dumps([dict(r) for r in c.execute(${JSON.stringify(sql)})],ensure_ascii=False))`;
  return JSON.parse(execFileSync(PY, ["-c", code], { encoding: "utf8" }));
}
function portFree(port) {
  return new Promise(res => {
    const s = net.connect(port, "127.0.0.1");
    s.on("connect", () => { s.destroy(); res(false); });
    s.on("error", () => res(true));
  });
}

const calls = [];
// path：/ 是学生端，/teacher 是教师端
function openPage(hash, path = "/") {
  const name = path === "/" ? "index" : path.slice(1);
  const html = fs.readFileSync(WEB + `/${name}.html`, "utf8")
    .replace(/<script src="[^"]*"><\/script>/g, "");
  const dom = new JSDOM(html, { url: BASE + path + (hash || ""), runScripts: "outside-only" });
  const w = dom.window;
  w.fetch = async (u, o = {}) => {
    const url = new URL(u, BASE);
    const r = await fetch(url, { ...o, signal: undefined });
    calls.push({ path: url.pathname, status: r.status, body: o.body ? JSON.parse(o.body) : null });
    return r;
  };
  w.console.log = () => {};
  w.console.warn = () => {};
  w.Element.prototype.scrollIntoView = function () {};
  w.eval(fs.readFileSync(WEB + "/vue.global.prod.js", "utf8"));
  w.eval(fs.readFileSync(WEB + (path === "/" ? "/app.js" : `/${name}.js`), "utf8"));
  const $ = s => w.document.querySelector(s);
  const $$ = s => [...w.document.querySelectorAll(s)];
  const inOverlay = lbl => $$(".overlay label.field").find(l => (l.querySelector(".lbl") || {}).textContent
    && l.querySelector(".lbl").textContent.replace("*", "").trim() === lbl);
  const inScreen = lbl => $$(".screen label.field").find(l => (l.querySelector(".lbl") || {}).textContent
    && l.querySelector(".lbl").textContent.replace("*", "").trim() === lbl);
  const pg = {
    w, $, $$,
    nav: t => $$("nav a").find(a => a.textContent.trim() === t),
    pages: () => $$("nav > a").map(a => a.textContent.trim()),
    btn: t => $$("button").find(b => b.textContent.trim() === t),
    obtn: t => $$(".overlay button").find(b => b.textContent.trim() === t),
    hash: () => decodeURIComponent(w.location.hash),
    toast: () => ($(".toast") || {}).textContent || "",
    overlay: () => $(".overlay"),
    // 浮层里的字段：文本框、多行、下拉按值设；开关点一下
    set: (lbl, v, where = inOverlay) => {
      const el = where(lbl).querySelector("input,textarea,select");
      if (el.type === "checkbox") { if (el.checked !== v) el.click(); return; }
      el.value = v;
      el.dispatchEvent(new w.Event(el.tagName === "SELECT" ? "change" : "input"));
    },
    get: (lbl, where = inOverlay) => {
      const el = where(lbl).querySelector("input,textarea,select");
      return el.type === "checkbox" ? el.checked : el.value;
    },
    inScreen,
    box: () => $(".screen textarea"),
    enter: el => el.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Enter", bubbles: true })),
    // 表头是 head（列名用 | 连起来）的那张表：每行 {cells, buttons}
    table: head => {
      const t = $$(".screen table").find(t =>
        [...t.querySelectorAll("th")].map(th => th.textContent.trim()).filter(Boolean).join("|") === head);
      return t ? [...t.querySelectorAll("tbody tr")].map(tr => ({
        cells: [...tr.querySelectorAll("td")].map(td => td.textContent.trim()),
        buttons: [...tr.querySelectorAll("button")],
      })) : null;
    },
    texts: () => $$(".screen .dyn-v").map(e => e.textContent),
    screen: () => ($(".screen") || {}).textContent || "",
    msgs: () => $$(".stream .smsg").map(m => ({
      who: (m.querySelector(".who") || {}).textContent || "",
      text: (m.querySelector(".body") || {}).textContent || "",
    })),
    teacher: () => pg.msgs().filter(m => m.who === "老师"),
    close: () => w.close(),
  };
  return pg;
}
const NOTE_HEAD = "编号|种类|关键词|内容|状态|更新时间|写的人";
const STUDENT_NOTE_HEAD = "编号|范围|种类|关键词|内容|状态|更新时间|写的人";
const rowBtn = (row, t) => row && row.buttons.find(b => b.textContent.trim() === t);

(async () => {
  if (!(await portFree(PORT))) {
    console.log(`端口 ${PORT} 已经被占用，不去连别人的服务。先停掉它再跑`);
    process.exit(1);
  }
  fs.rmSync(PROJ, { recursive: true, force: true });
  execFileSync(PY, ["-c", [
    "import sys, shutil, pathlib",
    "sys.path.insert(0, '.')",
    "from tests.kg.helpers import make_ws, client",
    `ws = pathlib.Path('${PROJ}'); ws.mkdir()`,
    "make_ws(ws)",
    "shutil.copytree('kg/ui', ws / 'ui')",
    "c = client(ws)",
    "assert c.post('/kg/import2', json={'form': {}}).status_code == 200",
    "assert c.post('/lesson/import', json={'form': {}}).status_code == 200",
  ].join("\n")], { cwd: MCP, encoding: "utf8" });
  // 不给 default：没命中规则的回答原样回显提示词
  fs.writeFileSync(MOCK, JSON.stringify({
    rules: [
      { when: ["意图分类器"], reply: '{"intent":"讲解","keywords":[],"level":"","kind":"","grade":"否"}' },
      { when: ["学生现在说：【记忆检查】", "｜记忆：这个学生和全班的常驻情况】"], reply: "系统提示词里有记忆" },
    ],
  }));

  const server = spawn(PY, ["-m", "gen", "run", PROJ, "--port", String(PORT), "--不开浏览器", "--标题", "日语学习"],
                       { cwd: MCP, stdio: ["ignore", "pipe", "pipe"],
                         env: Object.assign({}, process.env, { DSL_MOCK_SCRIPT: MOCK }) });
  let log = "";
  server.stdout.on("data", d => { log += d; });
  server.stderr.on("data", d => { log += d; });
  const stop = code => { server.kill(); process.exit(code); };
  let up = false;
  for (let i = 0; i < 150 && !up; i++) {
    try { up = (await fetch(BASE + "/")).ok; } catch (e) { /* 还没起来 */ }
    if (!up) await sleep(100);
  }
  if (!up) { console.log("服务没起来：\n" + log); stop(1); }

  try {
    console.log("一、学生端没有入口");
    let s = openPage("");
    say(await waitFor(() => s.pages().length > 0) && !s.nav("AI老师设定"), `导航里没有「AI老师设定」：${s.pages().join("|")}`);
    calls.length = 0;
    s.w.location.hash = "#" + encodeURIComponent("AI老师设定");
    say(await waitFor(() => s.hash() === "#知识图谱" && s.toast().includes("「AI老师设定」在教师端（/teacher）")),
        `手打 #AI老师设定：退回 ${s.hash()}，提示「${s.toast()}」`);
    await sleep(150);
    say(!calls.some(c => c.path.startsWith("/teacher_note/")), "没调 /teacher_note/*");
    s.close();

    console.log("二、教师端「AI老师设定」页");
    let t = openPage("", "/teacher");
    say(await waitFor(() => t.pages().join("|") === "学情|学生管理|AI老师设定|教材导入"),
        `教师端导航：${t.pages().join("|")}`);
    t.nav("AI老师设定").click();
    say(await waitFor(() => t.hash() === "#AI老师设定" && t.screen().includes("还没有全班的设定")), "进来：还没有全班的设定");
    const add = async (kind, content, keywords, once) => {
      t.btn("新增设定").click();
      await waitFor(() => t.overlay());
      t.set("种类", kind);
      t.set("关键词", keywords || "");
      t.set("内容", content);
      if (once) t.set("只用于下一条回复（只对作者注有效）", true);
      calls.length = 0;
      t.obtn("保存").click();
      await waitFor(() => calls.some(c => c.path === "/teacher_note/save"));
    };
    await add("记忆", "全班这周重点是て形。");
    say(await waitFor(() => !t.overlay() && (t.table(NOTE_HEAD) || []).length === 1), "存了一条记忆：浮层关了，列表里一行");
    await add("作者注", "下一条回答先夸一句。", "", true);
    await waitFor(() => (t.table(NOTE_HEAD) || []).length === 2);
    await add("关键词卡", "提到ばかり时，强调和たばかり的区别。", "～ばかり，たばかり");
    say(await waitFor(() => (t.table(NOTE_HEAD) || []).length === 3), "又存了作者注、关键词卡：三行");
    let notes = db("SELECT * FROM teacher_note ORDER BY id");
    say(notes.map(n => n.note_kind).join(",") === "记忆,作者注,关键词卡" && notes.every(n => n.note_student === "")
        && notes[1].note_once === 1 && notes[2].note_keywords === "～ばかり,たばかり" && notes.every(n => n.note_enabled === 1),
        `库里：三条全班的、作者注只用于下一条、关键词规整过：${JSON.stringify(notes.map(n => [n.note_kind, n.note_once, n.note_keywords]))}`);
    const rowsNow = t.table(NOTE_HEAD);
    say(rowsNow[1].cells[4] === "只用于下一条·已有 0 个学生用过" && rowsNow[0].cells[4] === "启用",
        `状态列：${rowsNow.map(r => r.cells[4]).join(" / ")}`);
    // 超长的存不进去
    await add("记忆", "长".repeat(401));
    say(await waitFor(() => t.toast().includes("400 字")), `超长：提示「${t.toast()}」`);
    say(db("SELECT count(*) n FROM teacher_note")[0].n === 3 && (t.table(NOTE_HEAD) || []).length === 3, "库里、列表里都没多");
    if (t.overlay()) t.obtn("取消").click();
    await waitFor(() => !t.overlay());
    // 编辑
    rowBtn(t.table(NOTE_HEAD)[0], "编辑").click();
    say(await waitFor(() => t.overlay() && t.get("内容") === "全班这周重点是て形。" && t.get("种类") === "记忆"
        && t.hash().includes(`note_id=${notes[0].id}`)),
        `编辑：浮层带着原内容打开，地址 ${t.hash()}`);
    t.set("内容", "全班这周重点是て形和た形。");
    t.obtn("保存").click();
    say(await waitFor(() => !t.overlay() && t.table(NOTE_HEAD)[0].cells[3] === "全班这周重点是て形和た形。"),
        "改了保存：浮层关了，列表跟着变");
    say(db("SELECT count(*) n FROM teacher_note")[0].n === 3, "是改，不是新增");
    rowBtn(t.table(NOTE_HEAD)[1], "编辑").click();
    say(await waitFor(() => t.overlay() && t.get("只用于下一条回复（只对作者注有效）") === true),
        "编辑作者注：「只用于下一条」的开关是开着的");
    t.obtn("取消").click();
    await waitFor(() => !t.overlay());

    console.log("三、学生问老师");
    const studentFrom = calls.length;
    s = openPage("#" + encodeURIComponent("问老师"));
    // 等「进入时」拉完历史再问：历史回来会整条替换消息流
    await waitFor(() => s.box() && calls.slice(studentFrom).some(c => c.path === "/teacher/state"));
    await sleep(100);
    const ask = async text => {
      const before = s.teacher().length;
      s.box().value = text;
      s.box().dispatchEvent(new s.w.Event("input"));
      s.enter(s.box());
      await waitFor(() => s.teacher().length === before + 1, 8000);
      return (s.teacher()[before] || {}).text || "";
    };
    let r = await ask("～ばかり怎么用");
    say(s.msgs().some(m => m.who === "你" && m.text === "～ばかり怎么用"),
        `自己的话原样出现：${JSON.stringify(s.msgs().filter(m => m.who !== "老师"))}`);
    const at = k => r.indexOf(k);
    say(at(MARK + "｜关键词卡") >= 0 && at(MARK + "｜关键词卡") < at("最近的对话"), "关键词卡在「最近的对话」之前");
    say(at("最近的对话") < at(MARK + "｜作者注") && at("下一条回答先夸一句") > at(MARK + "｜作者注")
        && /【教师设定结束】\s*学生现在说：【～ばかり怎么用】/.test(r),
        "作者注在「最近的对话」之后、紧贴「学生现在说」之前");
    say(r.includes("学生提到了「ばかり」"), "关键词卡写明命中的是 ばかり");
    r = await ask("记忆检查");
    say(r === "系统提示词里有记忆", `记忆在系统提示词里：${r}`);
    r = await ask("第三句");
    say(r.startsWith("[模拟回复]") && !r.includes("下一条回答先夸一句") && !r.includes(MARK + "｜作者注"),
        "只用于下一条的作者注：用过一次，下一句不带了");
    const uses = db("SELECT note_ids FROM chat_note_use ORDER BY id").map(u => u.note_ids);
    say(uses[0] === `${notes[0].id},${notes[1].id},${notes[2].id}` && !uses.slice(1).some(u => u.split(",").includes(String(notes[1].id))),
        `使用记录：第一句用了三条，之后没有那条作者注：${JSON.stringify(uses)}`);
    say(!s.nav("AI老师设定") && !s.btn("新增设定") && !s.btn("预览")
        && !calls.slice(studentFrom).some(c => c.path.startsWith("/teacher_note/")), "学生端页面上没有设定页、按钮，没调设定接口");

    console.log("四、停用");
    t.close();
    t = openPage("#" + encodeURIComponent("AI老师设定"), "/teacher");
    await waitFor(() => (t.table(NOTE_HEAD) || []).length === 3);
    rowBtn(t.table(NOTE_HEAD)[0], "停用").click();
    say(await waitFor(() => t.table(NOTE_HEAD)[0].cells[4] === "停用" && rowBtn(t.table(NOTE_HEAD)[0], "启用")
        && !rowBtn(t.table(NOTE_HEAD)[0], "停用")), "停用：状态是停用，按钮换成「启用」");
    r = await ask("记忆检查");
    say(r.startsWith("[模拟回复]") && !r.includes("て形和た形"), "学生再问：不再有记忆");
    rowBtn(t.table(NOTE_HEAD)[0], "启用").click();
    say(await waitFor(() => t.table(NOTE_HEAD)[0].cells[4] === "启用"), "再启用");

    console.log("五、预览");
    say(await waitFor(() => [...t.inScreen("学生").querySelectorAll("option")].some(o => o.value === "me")),
        "学生下拉里有 me");
    t.set("学生", "me", t.inScreen);
    t.set("示例提问", "たばかり是什么意思", t.inScreen);
    calls.length = 0;
    t.btn("预览").click();
    say(await waitFor(() => (t.table("编号|命中的关键词|内容|放进去了吗") || []).length === 1),
        "命中表里一行");
    const hit = (t.table("编号|命中的关键词|内容|放进去了吗") || [{ cells: [] }])[0].cells;
    // 关键词按存的顺序比：「～ばかり」去掉 ～ 是 ばかり，たばかり 里就有
    say(hit[0] === String(notes[2].id) && hit[1] === "ばかり" && hit[3] === "放进去了", `命中：${hit.join(" | ")}`);
    const lay = t.texts().find(x => x.includes("【系统提示词】")) || "";
    const li = k => lay.indexOf(k);
    say(li("【系统提示词】") < li("て形和た形") && li("て形和た形") < li("【发给模型的提示词】")
        && li("【发给模型的提示词】") < li(MARK + "｜关键词卡") && li(MARK + "｜关键词卡") < li("最近的对话")
        && li("最近的对话") < li("学生现在说：【たばかり是什么意思】") && !lay.includes(MARK + "｜作者注"),
        "拼好的样子：记忆在系统提示词里、关键词卡在最近的对话之前；一次性的作者注 me 已用过，不出现");
    say(calls.filter(c => c.path.startsWith("/teacher_note/preview")).length === 1, "调了一次预览接口");

    console.log("六、学情的学生页");
    t.w.location.hash = "#" + encodeURIComponent("学情") + "?student=me";
    say(await waitFor(() => (t.table(STUDENT_NOTE_HEAD) || []).length === 3), "学生页：AI老师设定那张表里三条全班的");
    let srows = t.table(STUDENT_NOTE_HEAD);
    say(srows.every(x => x.cells[1] === "全班" && x.buttons.length === 0), "全班的只读：没有按钮");
    t.btn("给这个学生加一条").click();
    await waitFor(() => t.overlay());
    say(t.hash().includes("student=me") && t.hash().includes("浮层="), `浮层打开，地址里 student 还在：${t.hash()}`);
    t.set("种类", "作者注");
    t.set("内容", "这个学生多用敬语。");
    t.obtn("保存").click();
    say(await waitFor(() => !t.overlay() && (t.table(STUDENT_NOTE_HEAD) || []).length === 4), "存了：表里四条");
    srows = t.table(STUDENT_NOTE_HEAD);
    const mine = srows.find(x => x.cells[1] === "个人");
    say(mine && mine.cells[2] === "作者注" && rowBtn(mine, "编辑") && rowBtn(mine, "停用") && rowBtn(mine, "删除"),
        "个人的那条有编辑、停用、删除");
    say(srows.findIndex(x => x.cells[1] === "个人") > srows.findIndex(x => x.cells[2] === "作者注" && x.cells[1] === "全班"),
        "排在全班的作者注后面");
    say(db("SELECT note_student FROM teacher_note ORDER BY id DESC LIMIT 1")[0].note_student === "me", "库里记的是给 me 的");
    // 行上「编辑」：地址里的 student 留着，保存后回到这个学生的页面
    rowBtn(mine, "编辑").click();
    say(await waitFor(() => t.overlay() && t.get("内容") === "这个学生多用敬语。"
        && t.hash().includes("student=me") && t.hash().includes("note_id=")),
        `编辑个人的那条：浮层带着原内容，地址 ${t.hash()}`);
    t.set("内容", "这个学生多用敬语，句子短一点。");
    t.obtn("保存").click();
    say(await waitFor(() => !t.overlay() && t.hash() === "#学情?student=me"
        && (t.table(STUDENT_NOTE_HEAD) || []).some(x => x.cells[4] === "这个学生多用敬语，句子短一点。")),
        `保存后回到这个学生的页面：${t.hash()}`);
    say(db("SELECT count(*) n FROM teacher_note WHERE note_student = 'me'")[0].n === 1, "是改，不是新增");
    r = await ask("再问一句");
    say(r.includes("这个学生多用敬语") && r.includes("（只对这个学生）"), "学生下一句的作者注里有给他的这条");
    t.w.location.hash = "#" + encodeURIComponent("学情");
    await waitFor(() => !t.hash().includes("student"));
    t.w.location.hash = "#" + encodeURIComponent("学情") + "?student=me";
    say(await waitFor(() => (t.table("谁|内容|时间|用了的设定") || []).some(x => x.cells[3].includes(`作者注#${notes[1].id}`))),
        "问老师记录：老师那条写着用了哪些设定");
    const chat = t.table("谁|内容|时间|用了的设定") || [];
    say(chat.filter(x => x.cells[0] === "学生").every(x => x.cells[3] === ""), "学生那条没有");

    console.log("七、服务端");
    say(!/Traceback/.test(log), "服务日志里没有 Traceback");
    say(!calls.some(c => c.status >= 500), "没有 5xx");
    s.close();
    t.close();
  } catch (e) {
    say(false, "跑挂了：" + (e && e.stack || e));
  }

  console.log(`\n${"=".repeat(50)}\n通过 ${pass}，失败 ${fail}`);
  if (fail) console.log("---- 服务日志（末尾）----\n" + log.slice(-2000));
  stop(fail ? 1 : 0);
})();
