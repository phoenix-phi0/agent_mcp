// 显式主键（编号由人填，不是自增 id）的实体，在浮层里新建、编辑。
//
//     cd tests/e2e && node pk_run.js
//
// 两件事是自增主键测不到的：
//
//   新建时用户正在填主键——模式要按地址区分，不能按「表单里有没有主键」，
//   否则一填编号，按钮就错跳成「更新」「删除」。
//
//   编辑时主键也是个输入框——把 B1 的编号改成 B2 再保存，更新语句按主键找
//   记录，会不会悄悄改到 B2 头上。

const { execFileSync, spawn } = require("child_process");
const fs = require("fs");
const { JSDOM } = require("jsdom");

const MCP = process.env.M || require("path").resolve(__dirname, "../..");
const PY = MCP + "/.venv/bin/python";
const PROJ = "/tmp/e2e_pk";
const PORT = 8192;
const BASE = `http://127.0.0.1:${PORT}`;

let pass = 0, fail = 0;
const say = (ok, msg) => { ok ? pass++ : fail++; console.log((ok ? "  ✓ " : "  ✗ ") + msg); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function waitFor(fn, ms = 3000) {
  const t = Date.now();
  while (Date.now() - t < ms) {
    try { if (fn()) return true; } catch (e) { /* 还没渲染 */ }
    await sleep(30);
  }
  return false;
}
const py = args => execFileSync(PY, args, { cwd: MCP, encoding: "utf8" });
function db(sql) {
  const code = "import sqlite3,json;" +
    `c=sqlite3.connect('${PROJ}/app.db');c.row_factory=sqlite3.Row;` +
    `print(json.dumps([dict(r) for r in c.execute(${JSON.stringify(sql)})],ensure_ascii=False))`;
  return JSON.parse(execFileSync(PY, ["-c", code], { encoding: "utf8" }));
}
const books = () => Object.fromEntries(db("SELECT code, title FROM book").map(r => [r.code, r.title]));

(async () => {
  fs.rmSync(PROJ, { recursive: true, force: true });
  py(["-m", "gen", "init", PROJ, "--空"]);
  fs.writeFileSync(PROJ + "/entities/book.entity",
    "实体 book 书\n  字段 code 文本 必填 编号\n  字段 title 文本 必填 书名\n  主键 code\n结束\n");
  py(["-m", "gen", "gen", PROJ]);

  const server = spawn(PY, ["-m", "gen", "run", PROJ, "--port", String(PORT), "--不开浏览器"],
                       { cwd: MCP, stdio: ["ignore", "pipe", "pipe"] });
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

  const web = PROJ + "/web";
  const calls = [];
  function openPage(hash) {
    const html = fs.readFileSync(web + "/index.html", "utf8")
      .replace(/<script src="[^"]*"><\/script>/g, "");
    const dom = new JSDOM(html, { url: BASE + "/" + (hash || ""), runScripts: "outside-only" });
    const w = dom.window;
    w.fetch = async (u, o) => {
      const url = new URL(u, BASE);
      // 页面传的 signal 是 jsdom 的 AbortSignal，Node 的 fetch 不认（报不是 AbortSignal 的实例），去掉
      const r = await fetch(url, { ...o, signal: undefined });
      calls.push({ path: url.pathname, status: r.status });
      return r;
    };
    w.console.log = () => {};
    w.eval(fs.readFileSync(web + "/vue.global.prod.js", "utf8"));
    w.eval(fs.readFileSync(web + "/app.js", "utf8"));
    return w;
  }
  let w = openPage("");
  const $ = s => w.document.querySelector(s);
  const $$ = s => [...w.document.querySelectorAll(s)];
  const btn = t => $$("button").find(b => b.textContent.trim() === t);
  const btns = t => $$("button").filter(b => b.textContent.trim() === t).length;
  const hash = () => decodeURIComponent(w.location.hash);
  const toast = () => ($(".toast") || {}).textContent || "";
  const type = (el, v) => { el.value = v; el.dispatchEvent(new w.Event("input")); };
  const inputs = () => $$(".overlay input[type=text]");
  const overlayOpen = () => !!$(".overlay");

  async function create(code, title) {
    btn("新建").click();
    await waitFor(() => overlayOpen());
    type(inputs()[0], code);
    await sleep(50);
    const mode = { saves: btns("保存"), del: !!btn("删除") };
    type(inputs()[1], title);
    btn("保存").click();
    await waitFor(() => toast().includes("已新建") && !overlayOpen());
    await sleep(100);
    return mode;
  }

  console.log("一、新建时填了编号，模式不能错跳");
  await waitFor(() => calls.some(c => c.path === "/book/list"));
  const mode = await create("B1", "第一本");
  say(mode.saves === 1 && !mode.del, `填了编号之后仍是新建模式：保存 ${mode.saves} 个，删除 ${mode.del ? "有" : "无"}`);
  await create("B2", "第二本");
  say(JSON.stringify(books()) === JSON.stringify({ B1: "第一本", B2: "第二本" }),
      `库里两本：${JSON.stringify(books())}`);

  console.log("二、编辑 B1，地址带编号");
  const rowOf = code => $$("tbody tr").find(tr => tr.textContent.includes(code));
  await waitFor(() => rowOf("B1"));
  rowOf("B1").querySelector("button").click();
  say(await waitFor(() => hash() === "#书列表?浮层=书&code=B1"), `地址：${hash()}`);
  say(!!btn("删除"), "编辑模式");
  type(inputs()[1], "第一本（改）");
  btn("保存").click();
  await waitFor(() => toast().includes("已保存"));
  say(books().B1 === "第一本（改）", `正常改书名：${JSON.stringify(books())}`);

  console.log("三、编辑 B1 时把编号改成 B2");
  await waitFor(() => !overlayOpen() && rowOf("B1"));
  calls.length = 0;
  rowOf("B1").querySelector("button").click();
  await waitFor(() => overlayOpen() && inputs()[0].value === "B1");
  say(inputs()[0].readOnly, "编辑时编号框是只读的");
  say(!inputs()[1].readOnly, "书名框照常可写");
  // 只读挡得住人，挡不住脚本——这里用脚本硬改，确认提交时仍以地址为准
  type(inputs()[0], "B2");
  type(inputs()[1], "改到 B1 上");
  btn("保存").click();
  await sleep(500);
  const now = books();
  say(now.B2 === "第二本", `B2 没被改掉：${JSON.stringify(now)}`);
  say(now.B1 === "改到 B1 上", "改动落在地址指的 B1 上");
  console.log(`      （实际：保存回了 ${(calls.find(c => c.path === "/book/update") || {}).status}，库里 ${JSON.stringify(now)}）`);

  console.log("四、刷新编辑浮层（地址里是编号）");
  const url = "#" + encodeURIComponent("书列表") + "?" + new URLSearchParams({ "浮层": "书", code: "B2" });
  w.close();
  calls.length = 0;
  w = openPage(url);
  say(await waitFor(() => calls.some(c => c.path === "/book/one" && c.status === 200)),
      "按编号把记录拉回来");
  say(await waitFor(() => inputs()[1] && inputs()[1].value === books().B2), `书名：「${inputs()[1] && inputs()[1].value}」`);

  console.log("五、服务端");
  say(!/Traceback/.test(log), "服务日志里没有 Traceback");

  console.log(`\n${"=".repeat(50)}\n通过 ${pass}，失败 ${fail}`);
  if (fail) console.log("\n服务日志最后几行：\n" + log.split("\n").slice(-12).join("\n"));
  stop(fail ? 1 : 0);
})().catch(e => { console.log("测试台自己炸了：", e); process.exit(2); });
