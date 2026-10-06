// 导航和带参数路由的端到端测试：真服务 + 真实生成的页面。
//
//     cd tests/e2e && node route_run.js
//
// 两个实体（笔记、待办）+ 认证 +「私有」模板。测：
//   导航：能切到另一个实体、正确高亮、登录页上不显示
//   参数：点编辑后地址带 id；「刷新」后表单载回来；改完能保存
//   坏参数：id=999 提示没有这条；别人的编辑链接 404、表单保持空
//   登录回跳：没登录时打开编辑链接，登录完回到那一条、表单已填好
//
// 「刷新」= 同一个地址、同一份 cookie，新开一个页面——浏览器刷新就是这样：
// 内存里的表单全没了，只剩地址和 cookie。

const { execFileSync, spawn } = require("child_process");
const fs = require("fs");
const { JSDOM } = require("jsdom");

const MCP = "/home/ysc/mcp";
const PY = MCP + "/.venv/bin/python";
const PROJ = "/tmp/e2e_route";
const PORT = 8193;
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

// 所有页面共用一个 cookie 罐——同一个浏览器
let jar = "";
const calls = [];
const WEB = PROJ + "/web";

function openPage(hash) {
  const html = fs.readFileSync(WEB + "/index.html", "utf8")
    .replace(/<script src="[^"]*"><\/script>/g, "");
  const dom = new JSDOM(html, { url: BASE + "/" + (hash || ""), runScripts: "outside-only" });
  const w = dom.window;
  w.fetch = async (u, o = {}) => {
    const url = new URL(u, BASE);
    const headers = Object.assign({}, o.headers || {});
    if (jar) headers["Cookie"] = `zs_auth=${jar}`;
    // 页面传的 signal 是 jsdom 的 AbortSignal，Node 的 fetch 不认（报不是 AbortSignal 的实例），去掉
    const r = await fetch(url, { ...o, headers, signal: undefined });
    for (const c of (r.headers.getSetCookie ? r.headers.getSetCookie() : [])) {
      const m = /^zs_auth=([^;]*)/.exec(c);
      if (m) jar = (!m[1] || /Max-Age=0|expires=Thu, 01 Jan 1970/i.test(c)) ? "" : m[1];
    }
    calls.push({ path: url.pathname, status: r.status });
    return r;
  };
  w.console.log = () => {};
  w.eval(fs.readFileSync(WEB + "/vue.global.prod.js", "utf8"));
  w.eval(fs.readFileSync(WEB + "/app.js", "utf8"));
  const $ = s => w.document.querySelector(s);
  const $$ = s => [...w.document.querySelectorAll(s)];
  return {
    w, $, $$,
    btn: t => $$("button").find(b => b.textContent.trim() === t),
    navLink: t => $$("nav.app-nav a").find(a => a.textContent.trim() === t),
    activeNav: () => ($("nav.app-nav a.active") || {}).textContent,
    hash: () => decodeURIComponent(w.location.hash),
    toast: () => ($(".toast") || {}).textContent || "",
    type: (el, v) => { el.value = v; el.dispatchEvent(new w.Event("input")); },
    close: () => w.close(),
  };
}

async function login(p, user, pw, register = false) {
  if (register) {
    p.btn("没有账号？注册").click();
    await waitFor(() => p.hash() === "#注册");
  }
  p.type(p.$('input[type=text]'), user);
  p.type(p.$('input[type=password]'), pw);
  p.btn(register ? "注册" : "登录").click();
}

(async () => {
  fs.rmSync(PROJ, { recursive: true, force: true });
  py(["-m", "gen", "init", PROJ, "--空"]);
  py(["-m", "gen", "auth", PROJ]);
  fs.writeFileSync(PROJ + "/entities/note.entity",
    "实体 note 笔记\n  字段 title 文本 必填 标题\n  字段 pinned 布尔 必填 默认 否 置顶\n" +
    "  字段 owner 文本 必填 索引 归属\n结束\n");
  fs.writeFileSync(PROJ + "/entities/todo.entity",
    "实体 todo 待办\n  字段 task 文本 必填 事项\n  字段 owner 文本 必填 索引 归属\n结束\n");
  py(["-m", "gen", "gen", PROJ, "--模板", "private"]);

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

  console.log("一、导航");
  let p = openPage("");
  await waitFor(() => p.hash() === "#登录");
  say(!p.$("nav.app-nav"), "登录页上不显示导航");
  await login(p, "alice", "alicepass", true);
  say(await waitFor(() => p.hash() === "#笔记列表"), `注册完到了 ${p.hash()}`);
  say(!!p.navLink("笔记") && !!p.navLink("待办") && !!p.btn("退出登录"),
      "导航里有 笔记、待办、退出登录");
  say(p.activeNav() === "笔记", `高亮的是「${p.activeNav()}」`);

  p.btn("新建").click();
  await waitFor(() => p.hash() === "#笔记列表?浮层=笔记" && p.$(".overlay"));
  say(p.activeNav() === "笔记", "新建浮层开着时，高亮仍是笔记");
  p.type(p.$('.overlay input[type=text]'), "第一 条");
  p.$('.overlay input[type=checkbox]').click();
  p.btn("保存").click();
  await waitFor(() => p.toast().includes("已新建"));
  const noteId = db("SELECT id FROM note")[0].id;
  // 编辑浮层的地址。界面名和参数分开编码，跟前端 go() 的写法一致
  const editHash = "#" + encodeURIComponent("笔记列表") + "?" +
    new URLSearchParams({ "浮层": "笔记", id: noteId });

  calls.length = 0;
  p.navLink("待办").click();
  say(await waitFor(() => p.hash() === "#待办列表"), `点导航「待办」到了 ${p.hash()}`);
  say(p.activeNav() === "待办", `高亮换成「${p.activeNav()}」`);
  say(await waitFor(() => calls.some(c => c.path === "/todo/list")), "进入待办列表时拉了数据");
  p.navLink("笔记").click();
  say(await waitFor(() => p.hash() === "#笔记列表" &&
                   (p.$("tbody td") || {}).textContent === "第一 条"),
      "点导航「笔记」回来，列表里有刚建的那条");

  console.log("二、点编辑，地址带上浮层和 id");
  p.btn("编辑").click();
  say(await waitFor(() => p.hash() === `#笔记列表?浮层=笔记&id=${noteId}`), `地址：${p.hash()}`);
  say(p.activeNav() === "笔记", "编辑浮层开着时，高亮仍是笔记");
  const url = p.w.location.hash;
  say(url === editHash, "前端写出来的地址跟测试里拼的一致（下面按它开页面）");
  p.close();

  console.log("三、刷新编辑界面");
  calls.length = 0;
  p = openPage(url);
  say(await waitFor(() => calls.some(c => c.path === "/note/one" && c.status === 200)),
      "刷新后调了 /note/one 把记录拉回来");
  say(await waitFor(() => p.$('input[type=text]').value === "第一 条"), `表单标题：「${p.$('input[type=text]').value}」`);
  say(p.$('input[type=checkbox]').checked, "勾选框按库里的 1 显示为勾上");
  p.type(p.$('input[type=text]'), "刷新后 改的");
  p.btn("保存").click();
  say(await waitFor(() => p.toast().includes("已保存")), `保存：「${p.toast()}」`);
  say(db("SELECT title FROM note")[0].title === "刷新后 改的", "库里改了");
  p.close();

  console.log("四、坏参数");
  p = openPage("#" + encodeURIComponent("笔记列表") + "?" +
               new URLSearchParams({ "浮层": "笔记", id: 999 }));
  say(await waitFor(() => p.toast().includes("没有这条记录")), `id=999：「${p.toast()}」`);
  say(p.$('input[type=text]').value === "", "表单是空的，没残留别的记录");
  p.close();

  console.log("五、别人的编辑链接");
  p = openPage("");
  await waitFor(() => p.btn("退出登录"));
  p.btn("退出登录").click();
  await waitFor(() => p.hash() === "#登录");
  await login(p, "bob", "bobpass1", true);
  await waitFor(() => p.hash() === "#笔记列表");
  p.close();
  p = openPage(url);
  say(await waitFor(() => p.toast().includes("没有这条记录")), `bob 打开 alice 的链接：「${p.toast()}」`);
  say(p.$('input[type=text]').value === "", "bob 看不到内容");
  p.btn("保存").click();
  await sleep(300);
  say(db("SELECT title FROM note")[0].title === "刷新后 改的", "bob 在那个界面点保存，alice 的记录没被改");

  console.log("六、没登录时打开编辑链接");
  await waitFor(() => p.btn("退出登录"));
  p.btn("退出登录").click();
  await waitFor(() => p.hash() === "#登录");
  p.close();
  p = openPage(url);
  say(await waitFor(() => p.hash() === "#登录"), "被弹到登录页");
  await login(p, "alice", "alicepass");
  say(await waitFor(() => p.hash() === `#笔记列表?浮层=笔记&id=${noteId}`),
      `登录完回到了那一条（连浮层和参数）：${p.hash()}`);
  say(await waitFor(() => p.$('input[type=text]').value === "刷新后 改的"),
      `表单已填好：「${p.$('input[type=text]').value}」`);

  console.log("七、服务端");
  say(!/Traceback/.test(log), "服务日志里没有 Traceback");
  say(!calls.some(c => c.status >= 500), "没有 5xx");

  console.log(`\n${"=".repeat(50)}\n通过 ${pass}，失败 ${fail}`);
  if (fail) console.log("\n服务日志最后几行：\n" + log.split("\n").slice(-15).join("\n"));
  stop(fail ? 1 : 0);
})().catch(e => { console.log("测试台自己炸了：", e); process.exit(2); });
