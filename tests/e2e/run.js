// 真前端连真后端的端到端测试：增删改查，新建和编辑都在浮层里。
//
//     cd tests/e2e && node run.js
//
// 每次从零建一个项目（/tmp/e2e_demo）：init → gen（full 模板）→ run 起真服务。
// 然后拿 web/ 下**真实生成的**页面、脚本、Vue 在 jsdom 里跑，fetch 直接打到
// 真服务，按人的操作顺序点。每一步之后再去真数据库里查。
//
// 浮层开关在地址里（#笔记列表?浮层=笔记&id=1）。除了增删改查本身，还专门
// 测几件浮层带来的事：开关浮层不重拉列表、后退键关浮层、编辑过一条之后再
// 点新建表单是空的。

const { execFileSync, spawn } = require("child_process");
const fs = require("fs");
const { JSDOM } = require("jsdom");

const MCP = "/home/ysc/mcp";
const PY = MCP + "/.venv/bin/python";
const PROJ = "/tmp/e2e_demo";
const PORT = 8198;
const BASE = `http://127.0.0.1:${PORT}`;

let pass = 0, fail = 0;
const say = (ok, msg) => { ok ? pass++ : fail++; console.log((ok ? "  ✓ " : "  ✗ ") + msg); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function waitFor(fn, ms = 3000) {
  const t = Date.now();
  while (Date.now() - t < ms) {
    try { if (fn()) return true; } catch (e) { /* 还没渲染出来 */ }
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

(async () => {
  fs.rmSync(PROJ, { recursive: true, force: true });
  py(["-m", "gen", "init", PROJ]);
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
  const html = fs.readFileSync(web + "/index.html", "utf8")
    .replace(/<script src="[^"]*"><\/script>/g, "");
  const dom = new JSDOM(html, { url: BASE + "/", runScripts: "outside-only" });
  const w = dom.window;
  const calls = [];
  w.fetch = async (u, o) => {
    const url = new URL(u, BASE);
    const r = await fetch(url, o);
    calls.push({ path: url.pathname, status: r.status });
    return r;
  };
  w.console.log = () => {};
  w.eval(fs.readFileSync(web + "/vue.global.prod.js", "utf8"));
  w.eval(fs.readFileSync(web + "/app.js", "utf8"));

  const $ = s => w.document.querySelector(s);
  const $$ = s => [...w.document.querySelectorAll(s)];
  const btn = t => $$("button").find(b => b.textContent.trim() === t);
  const hash = () => decodeURIComponent(w.location.hash);
  const toast = () => ($(".toast") || {}).textContent || "";
  const type = (el, v) => { el.value = v; el.dispatchEvent(new w.Event("input")); };
  const ov = s => $(".overlay " + s);
  const overlayOpen = () => !!$(".overlay");
  const listCalls = p => calls.filter(c => c.path === p).length;

  console.log("一、打开页面（库是空的）");
  say(await waitFor(() => listCalls("/note/list") === 1), "进入时向真服务拉了笔记列表");
  say($$("tbody tr").length === 0, `列表 ${$$("tbody tr").length} 行`);

  console.log("二、新建（浮层）");
  btn("新建").click();
  say(await waitFor(() => hash() === "#笔记列表?浮层=笔记" && overlayOpen()),
      `浮层打开，地址：${hash()}`);
  say(!!btn("保存") && !btn("删除"), "新建模式：只有保存，没有删除");
  say(!$(".overlay").textContent.includes("创建于"), "表单里没有「创建于」");
  type(ov('input[type=text]'), "第一 条");
  type(ov("textarea"), "有 空格 的正文");
  ov('input[type=checkbox]').click();
  btn("保存").click();
  say(await waitFor(() => toast().includes("已新建")), `提示：「${toast()}」`);
  say(await waitFor(() => !overlayOpen() && hash() === "#笔记列表"), `保存后浮层关了：${hash()}`);
  say(await waitFor(() => $$("tbody tr").length === 1), "列表里已经有它（新建接口返回的）");
  say(listCalls("/note/list") === 1, `开关浮层没有重拉列表（拉了 ${listCalls("/note/list")} 次）`);
  let rows = db("select * from note");
  say(rows.length === 1 && rows[0].title === "第一 条" && rows[0].body === "有 空格 的正文",
      `库里：${JSON.stringify(rows[0] || null)}`);
  say(rows[0] && rows[0].pinned === 1 && rows[0].created_at, "置顶是 1，创建时间由数据库填了");
  say(($("td.cell-bool") || {}).textContent === "✓", "列表里置顶显示成勾");

  console.log("三、编辑（浮层，地址带 id）");
  const id = rows[0].id;
  calls.length = 0;
  btn("编辑").click();
  say(await waitFor(() => hash() === `#笔记列表?浮层=笔记&id=${id}` && overlayOpen()),
      `地址：${hash()}`);
  say(!!btn("删除"), "编辑模式：有删除");
  say(ov('input[type=checkbox]').checked, "勾选框显示为勾上");
  say(ov('input[type=text]').value === "第一 条", `标题带过来了：「${ov('input[type=text]').value}」`);
  await sleep(200);
  say(!calls.some(c => c.path === "/note/one"), "表单已经是这一条，没有多余地调 /note/one");
  type(ov('input[type=text]'), "改过 的标题");
  ov('input[type=checkbox]').click();
  btn("保存").click();
  say(await waitFor(() => toast().includes("已保存")), `提示：「${toast()}」`);
  say(await waitFor(() => !overlayOpen()), "保存后浮层关了");
  rows = db("select * from note");
  say(rows.length === 1 && rows[0].title === "改过 的标题" && rows[0].pinned === 0,
      `库里：title=${rows[0] && rows[0].title} pinned=${rows[0] && rows[0].pinned}`);

  console.log("四、后退键关浮层");
  calls.length = 0;
  btn("编辑").click();
  await waitFor(() => overlayOpen());
  w.history.back();
  say(await waitFor(() => !overlayOpen() && hash() === "#笔记列表"), `后退后浮层关了：${hash()}`);
  await sleep(200);
  say(!calls.some(c => c.path === "/note/list"), "后退关浮层也没有重拉列表");

  console.log("五、编辑过之后点新建，表单是空的");
  btn("编辑").click();
  await waitFor(() => overlayOpen() && ov('input[type=text]').value === "改过 的标题");
  btn("取消").click();
  await waitFor(() => !overlayOpen());
  btn("新建").click();
  await waitFor(() => overlayOpen());
  say(ov('input[type=text]').value === "" && !ov('input[type=checkbox]').checked,
      `新建浮层是空的：「${ov('input[type=text]').value}」`);
  say(!btn("删除"), "而且是新建模式");
  type(ov('input[type=text]'), "第二条");
  btn("保存").click();
  await waitFor(() => toast().includes("已新建"));
  say(db("select count(*) n from note")[0].n === 2, "新建出第二条，没有改掉第一条");
  say(db("select title from note where id=" + id)[0].title === "改过 的标题", "第一条原样");

  console.log("六、删除");
  await waitFor(() => !overlayOpen() && $$("tbody tr").length === 2);
  const firstEdit = $$("tbody tr").find(tr => tr.textContent.includes("改过 的标题"))
    .querySelector("button");
  firstEdit.click();
  await waitFor(() => overlayOpen() && btn("删除"));
  btn("删除").click();
  say(await waitFor(() => toast().includes("已删除")), `提示：「${toast()}」`);
  say(await waitFor(() => !overlayOpen() && $$("tbody tr").length === 1), "浮层关了，列表剩一行");
  say(db("select count(*) n from note")[0].n === 1, "库里剩一条");

  console.log("七、第二个实体");
  calls.length = 0;
  const navTodo = $$("nav.app-nav a").find(a => a.textContent.trim() === "待办");
  navTodo.click();
  say(await waitFor(() => calls.some(c => c.path === "/todo/list")), "点导航进入待办，拉了列表");
  btn("新建").click();
  await waitFor(() => overlayOpen());
  const tInputs = $$(".overlay input[type=text]");
  type(tInputs[0], "买 菜");
  type(tInputs[1], "明天");
  btn("保存").click();
  say(await waitFor(() => toast().includes("已新建")), `提示：「${toast()}」`);
  rows = db("select * from todo");
  say(rows.length === 1 && rows[0].task === "买 菜" && rows[0].done === 0 && rows[0].due === "明天",
      `库里：${JSON.stringify(rows[0] || null)}`);
  say(await waitFor(() => ($("tbody td") || {}).textContent === "买 菜"), "待办列表里有它");

  console.log("八、切回笔记列表，不能还显示待办");
  $$("nav.app-nav a").find(a => a.textContent.trim() === "笔记").click();
  await waitFor(() => hash() === "#笔记列表");
  await sleep(300);
  say($$("tbody tr").length === 1 && !w.document.body.textContent.includes("买 菜"),
      `笔记列表 ${$$("tbody tr").length} 行，没有待办的数据`);

  console.log("九、服务端");
  say(!/Traceback/.test(log), "服务日志里没有 Traceback");
  say(!calls.some(c => c.status >= 500), "没有 5xx");

  console.log(`\n${"=".repeat(50)}\n通过 ${pass}，失败 ${fail}`);
  if (fail) console.log("\n服务日志最后几行：\n" + log.split("\n").slice(-15).join("\n"));
  stop(fail ? 1 : 0);
})().catch(e => { console.log("测试台自己炸了：", e); process.exit(2); });
