// AI 老师设定第四种「传达」的端到端测试：真服务 + kg 真实生成的两个页面（学生端 /、
// 教师端 /teacher），在 jsdom 里按人的操作顺序点。
//
//     cd tests/e2e && node teacher_relay_run.js
//
// 照 kg 搭一份到 /tmp/e2e_teacher_relay，导入知识点和课文，gen run 起服务（单人模式、
// 离线假模型）。端口：TEACHER_RELAY_E2E_PORT 指定，不指定就在 8186–8199 里挑第一个
// 空着的（跳过 8197：那上面跑着常驻的 kg）；别的 e2e 各占一个固定端口，run_all 里是
// 一个接一个跑的。
//
// 假模型（DSL_MOCK_SCRIPT 的规则文件，见 tools/mock.py）：意图判定一律讲解；传达判定
// （系统提示词里有「传达检查员」，走「问JSON」）里有「小测」的回「传达到了」、有
// 「读书会」的回「没传达到」；别的老师回答**原样回显发给它的提示词**——页面上看到的
// 就是拼出来的提示词，断言传达段用它。真模型下学生看到的是 AI 自然说出来的话。
//
//   一、教师端「AI老师设定」页：传达区域空；「新增传达」浮层，要点空存不进去（红色
//       提示、库里没有）；存一条立即的全班传达，浮层关、列表里有，完成情况 0/总 0
//   二、学生在问老师里问：老师那条（回显的提示词）里传达段在「学生现在说」之前、时机是
//       立即；学生端页面上没有传达设定（没调 /teacher_relay/*）；后台判定成已传达；
//       再问一句不再带
//   三、教师端：完成情况「已传达 1/总 1」；各学生的状态表 me 已传达、有 AI 原话；
//       「看那条回复」开浮层，里面是学生那句和老师回复全文；关掉回到原地址
//   四、行上「编辑」带着原内容（要点、紧急程度）打开
//   五、预览：新加一条顺便的传达，预览里写着这次带哪条、拼好的样子里传达段的位置
//   六、学情的学生页：传达表里全班的只读（没有编辑按钮，有「看那条回复」）；「给这个
//       学生加一条传达」存成个人的；学生问一句（判没传达到）后状态变成待传达（已带入
//       1 轮）
//   七、服务端没有 5xx、没有 Traceback

const { execFileSync, spawn } = require("child_process");
const fs = require("fs");
const net = require("net");
const { JSDOM } = require("jsdom");

const MCP = "/home/ysc/mcp";
const PY = MCP + "/.venv/bin/python";
const PROJ = "/tmp/e2e_teacher_relay";
const WEB = PROJ + "/web";
const MOCK = PROJ + "/mock.json";
const RELAY = "【老师要你转达给学生｜传达";
let PORT, BASE;

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
async function pickPort() {
  if (process.env.TEACHER_RELAY_E2E_PORT) return Number(process.env.TEACHER_RELAY_E2E_PORT);
  for (let p = 8186; p <= 8199; p++) {
    if (p === 8197) continue;
    if (await portFree(p)) return p;
  }
  return 0;
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
  const field = (root, lbl) => $$(root + " label.field").find(l => (l.querySelector(".lbl") || {}).textContent
    && l.querySelector(".lbl").textContent.replace("*", "").trim() === lbl);
  const inOverlay = lbl => field(".overlay", lbl);
  const inScreen = lbl => field(".screen", lbl);
  const pg = {
    w, $, $$,
    nav: t => $$("nav a").find(a => a.textContent.trim() === t),
    pages: () => $$("nav > a").map(a => a.textContent.trim()),
    btn: t => $$("button").find(b => b.textContent.trim() === t),
    obtn: t => $$(".overlay button").find(b => b.textContent.trim() === t),
    hash: () => decodeURIComponent(w.location.hash),
    toast: () => ($(".toast") || {}).textContent || "",
    overlay: () => $(".overlay"),
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
const RELAY_HEAD = "编号|紧急程度|口吻|要点|必须准确的信息|截止日期|完成情况|状态|更新时间|写的人";
const STATE_HEAD = "编号|要点|学生|状态|AI原话";
const STUDENT_RELAY_HEAD = "编号|范围|紧急程度|要点|必须准确的信息|截止日期|状态|AI原话";
const URG = "紧急程度（不选是尽快。顺便：话题沾边才说；尽快：一两轮内；立即：下一条就说）";
const VOICE = "口吻（不选是以老师名义）";
const ROUNDS = "几轮没传达到就升级为立即（0或不填是3）";
const rowBtn = (row, t) => row && row.buttons.find(b => b.textContent.trim() === t);

(async () => {
  PORT = await pickPort();
  if (!PORT || !(await portFree(PORT))) {
    console.log(`8186–8199 里没有空着的端口（或指定的 ${PORT} 被占了），不去连别人的服务`);
    process.exit(1);
  }
  BASE = `http://127.0.0.1:${PORT}`;
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
  fs.writeFileSync(MOCK, JSON.stringify({
    rules: [
      { when: ["意图分类器"], reply: '{"intent":"讲解","keywords":[],"level":"","kind":"","grade":"否"}' },
      { when: ["传达检查员", "读书会"], reply: '{"delivered":"否","accurate":"无","quote":"","reason":"没提到"}' },
      { when: ["传达检查员", "小测"], reply: '{"delivered":"是","accurate":"是","quote":"对了，老师让我提醒你下周三有小测。","reason":"说到了"}' },
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
    console.log(`一、教师端「AI老师设定」页（端口 ${PORT}）`);
    let t = openPage("#" + encodeURIComponent("AI老师设定"), "/teacher");
    say(await waitFor(() => t.screen().includes("还没有全班的传达")), "传达区域：还没有全班的传达");
    const addRelay = async (fill) => {
      t.btn("新增传达").click();
      await waitFor(() => t.overlay());
      fill();
      calls.length = 0;
      t.obtn("保存").click();
      await waitFor(() => calls.some(c => c.path === "/teacher_relay/save"));
    };
    await addRelay(() => { t.set("要点", ""); });
    say(await waitFor(() => t.toast().includes("要点不能为空")), `要点空：提示「${t.toast()}」`);
    say(db("SELECT count(*) n FROM teacher_relay")[0].n === 0, "库里没有");
    if (t.overlay()) t.obtn("取消").click();
    await waitFor(() => !t.overlay());
    await addRelay(() => {
      t.set("要点", "下周三有小测，范围第1到5课，记得复习");
      t.set(URG, "立即");
      t.set("必须准确的信息", "10月14日；第1到5课");
    });
    say(await waitFor(() => !t.overlay() && (t.table(RELAY_HEAD) || []).length === 1), "存了：浮层关了，列表里一行");
    let relays = db("SELECT * FROM teacher_relay ORDER BY id");
    say(relays.length === 1 && relays[0].relay_urgency === "立即" && relays[0].relay_voice === "以老师名义"
        && relays[0].relay_facts === "10月14日；第1到5课" && relays[0].relay_rounds === 3 && relays[0].relay_student === "",
        `库里：立即、以老师名义（默认）、必须准确的信息、3 轮、全班：${JSON.stringify(relays[0])}`);
    let row = t.table(RELAY_HEAD)[0];
    say(row.cells[1] === "立即" && row.cells[6] === "已传达 0/总 0" && row.cells[7] === "启用",
        `列表：${row.cells.join(" | ")}`);

    console.log("二、学生问老师");
    const studentFrom = calls.length;
    let s = openPage("#" + encodeURIComponent("问老师"));
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
    let r = await ask("て形怎么用");
    say(r.includes(RELAY) && r.includes("下周三有小测") && /【转达结束】\s*学生现在说：【て形怎么用】/.test(r),
        "老师那条（回显的提示词）里有传达段，紧贴在学生那句之前");
    say(r.includes("时机：立即") && r.includes("「对了，") && r.includes("「老师让我提醒你"),
        "立即：末尾用「对了」过渡；口吻以老师名义");
    say(!s.nav("AI老师设定") && !s.btn("新增传达") && !calls.slice(studentFrom).some(c => c.path.startsWith("/teacher_relay/")),
        "学生端没有传达设定的页面、按钮，没调 /teacher_relay/*");
    say(await waitFor(() => (db("SELECT status FROM relay_state")[0] || {}).status === "已传达", 8000),
        "后台判定：已传达");
    const st0 = db("SELECT * FROM relay_state")[0];
    const msgId = db("SELECT max(id) m FROM chat_message WHERE role = 'teacher'")[0].m;
    say(st0.message_id === msgId && st0.excerpt === "对了，老师让我提醒你下周三有小测。", `记了那条回复和摘录：${JSON.stringify(st0)}`);
    r = await ask("那ている呢");
    // 回显的提示词里「最近的对话」带着上一条回复（里面有传达段），只看学生那句前面
    say(r.startsWith("[模拟回复]") && !/【转达结束】\s*学生现在说：【那ている呢】/.test(r)
        && db("SELECT count(*) n FROM relay_use")[0].n === 1, "再问一句：不再带传达");

    console.log("三、教师端看完成情况");
    t.close();
    t = openPage("#" + encodeURIComponent("AI老师设定"), "/teacher");
    say(await waitFor(() => ((t.table(RELAY_HEAD) || [])[0] || { cells: [] }).cells[6] === "已传达 1/总 1"),
        "完成情况：已传达 1/总 1");
    say(await waitFor(() => (t.table(STATE_HEAD) || []).length === 1), "各学生的状态表：一行");
    let srow = t.table(STATE_HEAD)[0];
    say(srow.cells[2] === "me" && srow.cells[3].startsWith("已传达（") && srow.cells[4] === "对了，老师让我提醒你下周三有小测。",
        `me：${srow.cells.join(" | ")}`);
    const before = t.hash();
    rowBtn(srow, "看那条回复").click();
    say(await waitFor(() => t.overlay() && t.get("AI老师的回复").includes(RELAY) && t.get("学生问") === "て形怎么用"
        && t.get("传达的那句") === "对了，老师让我提醒你下周三有小测。" && t.hash().includes(`message_id=${msgId}`)),
        `「看那条回复」：浮层里是学生那句、老师回复全文、传达的那句，地址 ${t.hash()}`);
    // 带着地址刷新：浮层的「载入」把那条拉回来
    const t2 = openPage("#" + encodeURIComponent("AI老师设定") + `?浮层=${encodeURIComponent("传达记录")}&message_id=${msgId}`, "/teacher");
    say(await waitFor(() => t2.overlay() && t2.get("学生问") === "て形怎么用" && t2.get("AI老师的回复").includes(RELAY)),
        "带着地址打开：「载入」把那条问老师记录拉回来");
    t2.close();
    t.obtn("返回").click();
    say(await waitFor(() => !t.overlay() && t.hash() === before), `关掉回到 ${t.hash()}`);

    console.log("四、编辑");
    rowBtn(t.table(RELAY_HEAD)[0], "编辑").click();
    say(await waitFor(() => t.overlay() && t.get("要点") === "下周三有小测，范围第1到5课，记得复习"
        && t.get(URG) === "立即"
        && t.get(ROUNDS) === "3" && t.hash().includes(`relay_id=${relays[0].id}`)),
        `编辑：浮层带着原内容，地址 ${t.hash()}`);
    t.obtn("取消").click();
    await waitFor(() => !t.overlay());

    console.log("五、预览");
    await addRelay(() => {
      t.set("要点", "周六有读书会，想来的可以报名");
      t.set(URG, "顺便");
      t.set(VOICE, "AI自己的口吻");
      t.set("话题关键词", "读书，本");
      t.set("截止日期（当天升级为立即，过了没传达到就不再带）", "2099-12-31");
    });
    say(await waitFor(() => !t.overlay() && (t.table(RELAY_HEAD) || []).length === 2), "又存了一条顺便的");
    relays = db("SELECT * FROM teacher_relay ORDER BY id");
    say(relays[1].relay_keywords === "读书,本" && relays[1].relay_due === "2099-12-31" && relays[1].relay_voice === "AI自己的口吻",
        `关键词规整、截止日期、口吻：${JSON.stringify([relays[1].relay_keywords, relays[1].relay_due, relays[1].relay_voice])}`);
    await waitFor(() => [...t.inScreen("学生").querySelectorAll("option")].some(o => o.value === "me"));
    t.set("学生", "me", t.inScreen);
    t.set("示例提问", "有什么好书推荐", t.inScreen);
    calls.length = 0;
    t.btn("预览").click();
    say(await waitFor(() => t.texts().some(x => x.includes(`传达#${relays[1].id}`))), "预览：这次带的传达是读书会那条");
    const lay = t.texts().find(x => x.includes("【系统提示词】")) || "";
    say(lay.indexOf("【老师要你转达的话】") > 0 && lay.indexOf("【老师要你转达的话】") < lay.indexOf("【发给模型的提示词】")
        && lay.indexOf("最近的对话") < lay.indexOf(RELAY) && lay.indexOf(RELAY) < lay.indexOf("学生现在说：【有什么好书推荐】")
        && lay.includes("不急，顺便说") && lay.includes("读书,本") && lay.includes("用你自己的口吻说"),
        "拼好的样子：系统提示词里有说明，传达段在最近的对话之后、学生那句之前，顺便、关键词、AI口吻");
    say(db("SELECT count(*) n FROM relay_use")[0].n === 1, "预览不写库");

    console.log("六、学情的学生页");
    t.w.location.hash = "#" + encodeURIComponent("学情") + "?student=me";
    say(await waitFor(() => (t.table(STUDENT_RELAY_HEAD) || []).length === 2), "传达表：两条全班的");
    let rows = t.table(STUDENT_RELAY_HEAD);
    say(rows.every(x => x.cells[1] === "全班" && !rowBtn(x, "编辑") && !rowBtn(x, "删除")), "全班的只读：没有编辑、删除");
    say(rowBtn(rows[0], "看那条回复") && !rowBtn(rows[1], "看那条回复") && rows[0].cells[6].startsWith("已传达（")
        && rows[1].cells[6] === "待传达（已带入 0 轮）",
        `状态：${rows.map(x => x.cells[6]).join(" / ")}；传达到的才有「看那条回复」`);
    t.btn("给这个学生加一条传达").click();
    say(await waitFor(() => t.overlay() && t.get(VOICE) === "以老师名义" && t.get(ROUNDS) === "3"),
        "加一条：空表单带默认值（以老师名义、3 轮）");
    t.set("要点", "这个学生下周的读书会要做发表");
    t.set(URG, "立即");
    t.obtn("保存").click();
    say(await waitFor(() => !t.overlay() && (t.table(STUDENT_RELAY_HEAD) || []).length === 3), "存了：表里三条");
    rows = t.table(STUDENT_RELAY_HEAD);
    const mine = rows.find(x => x.cells[1] === "个人");
    say(mine && rowBtn(mine, "编辑") && rowBtn(mine, "停用") && rowBtn(mine, "删除"), "个人的那条有编辑、停用、删除");
    say(db("SELECT relay_student FROM teacher_relay ORDER BY id DESC LIMIT 1")[0].relay_student === "me", "库里记的是给 me 的");
    r = await ask("再问一句");
    say(r.includes("这个学生下周的读书会要做发表") && !r.includes("周六有读书会"), "学生下一句带的是个人的立即那条（只带一条）");
    const pid = db("SELECT max(id) m FROM teacher_relay")[0].m;
    say(await waitFor(() => (db(`SELECT miss_n FROM relay_state WHERE relay_id = ${pid}`)[0] || {}).miss_n === 1, 8000),
        "后台判定：没传达到（读书会那条规则）");
    // 刷新这个学生的页面（同一个页面里来回切地址，表单里的 student 没变，「载入」不重拉）
    t.close();
    t = openPage("#" + encodeURIComponent("学情") + "?student=me", "/teacher");
    say(await waitFor(() => ((t.table(STUDENT_RELAY_HEAD) || []).find(x => x.cells[1] === "个人") || { cells: [] }).cells[6]
        === "待传达（已带入 1 轮）"), "个人的那条：待传达（已带入 1 轮）");
    say(await waitFor(() => (t.table("谁|内容|时间|用了的设定") || []).some(x => x.cells[3].includes(`传达#${pid}（未传达）`))),
        "问老师记录：老师那条写着「传达#…（未传达）」");

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
