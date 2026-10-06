// 登录流程的端到端测试：真服务 + 真实生成的页面，在 jsdom 里点。
//
//     cd tests/e2e && node auth_run.js
//
// 从零建项目：gen auth + 一个带 owner 的实体 + 「私有」模板，起服务。
// 然后像人一样：打开 → 被弹到登录 → 去注册 → 回到原来的界面 → 建数据
// → 退出 → 换个人注册 → 看不到前一个人的数据。每一步到真库里核对。
//
// Node 的 fetch 不存 cookie，这里自己当浏览器：收到 Set-Cookie 就记下，
// 之后的请求带上；Max-Age=0 就删掉。HttpOnly 的意思是页面脚本读不到，
// 浏览器本身照样收发——这里模拟的是浏览器那一层。

const { execFileSync, spawn } = require("child_process");
const fs = require("fs");
const { JSDOM } = require("jsdom");

const MCP = "/home/ysc/mcp";
const PY = MCP + "/.venv/bin/python";
const PROJ = "/tmp/e2e_auth";
// 端口可配：8197 常年跑着 kg 的常驻服务，早先写死 8197 时这一组总是起不来。
// 默认 8187（别的 e2e 用 8188-8199），AUTH_E2E_PORT 能改
const PORT = Number(process.env.AUTH_E2E_PORT || 8187);
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

(async () => {
  // ---- 建项目 ----
  fs.rmSync(PROJ, { recursive: true, force: true });
  py(["-m", "gen", "init", PROJ, "--空"]);
  py(["-m", "gen", "auth", PROJ]);
  fs.writeFileSync(PROJ + "/entities/note.entity",
    "实体 note 笔记\n  字段 title 文本 必填 标题\n  字段 body 长文本 正文\n" +
    "  字段 owner 文本 必填 索引 归属\n结束\n");
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

  // ---- 页面 + 自己当浏览器管 cookie ----
  const web = PROJ + "/web";
  const html = fs.readFileSync(web + "/index.html", "utf8")
    .replace(/<script src="[^"]*"><\/script>/g, "");
  const dom = new JSDOM(html, { url: BASE + "/", runScripts: "outside-only" });
  const w = dom.window;
  const calls = [];
  let jar = "", lastSetCookie = "";
  w.fetch = async (u, o = {}) => {
    const url = new URL(u, BASE);
    const headers = Object.assign({}, o.headers || {});
    if (jar) headers["Cookie"] = `zs_auth=${jar}`;
    // 页面传的 signal 是 jsdom 的 AbortSignal，Node 的 fetch 不认（报不是 AbortSignal 的实例），去掉
    const r = await fetch(url, { ...o, headers, signal: undefined });
    const sets = r.headers.getSetCookie ? r.headers.getSetCookie() : [];
    for (const c of sets) {
      const m = /^zs_auth=([^;]*)/.exec(c);
      if (!m) continue;
      lastSetCookie = c;
      jar = (!m[1] || /Max-Age=0|expires=Thu, 01 Jan 1970/i.test(c)) ? "" : m[1];
    }
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

  console.log("一、打开页面，没登录");
  say(await waitFor(() => hash() === "#登录"), `被弹到登录页：${hash()}`);
  say(calls.some(c => c.path === "/note/list" && c.status === 401),
      "是因为列表进入时的刷新拿到了 401");
  const pw = $('input[type=password]');
  say(!!pw, "密码框是 password 类型");

  console.log("二、去注册（密码带空格）");
  btn("没有账号？注册").click();
  say(await waitFor(() => hash() === "#注册"), `到了注册页：${hash()}`);
  type($('input[type=text]'), "alice");
  type($('input[type=password]'), "pass word 1");
  btn("注册").click();
  say(await waitFor(() => hash() === "#笔记列表"), `注册完回到了原来的界面：${hash()}`);
  say(jar !== "" && /HttpOnly/i.test(lastSetCookie) && /SameSite=Lax/i.test(lastSetCookie),
      "拿到了 cookie，HttpOnly + SameSite=Lax");
  say(await waitFor(() => calls.filter(c => c.path === "/note/list" && c.status === 200).length > 0),
      "回来后列表重新拉了一次，这回是 200");
  const h = db("SELECT password_hash FROM user WHERE username='alice'")[0].password_hash;
  say(h.startsWith("scrypt$") && !h.includes("pass word"), "库里是哈希");

  console.log("三、建一条");
  btn("新建").click();
  await waitFor(() => hash() === "#笔记列表?浮层=笔记" && $(".overlay"));
  say(!w.document.body.textContent.includes("归属"), "表单和列表里都没有 owner（归属）");
  type($('.overlay input[type=text]'), "alice 的 第一条");
  btn("保存").click();
  say(await waitFor(() => toast().includes("已新建")), `提示：「${toast()}」`);
  let rows = db("SELECT title, owner FROM note");
  say(rows.length === 1 && rows[0].owner === "alice", `库里归属是 alice：${JSON.stringify(rows)}`);
  say(await waitFor(() => !$(".overlay") &&
                   ($("tbody td") || {}).textContent === "alice 的 第一条"),
      "浮层关了，列表里有它");

  console.log("四、退出");
  btn("退出登录").click();
  say(await waitFor(() => hash() === "#登录"), `回到登录页：${hash()}`);
  say(jar === "", "cookie 删掉了");

  console.log("五、登录失败");
  type($('input[type=text]'), "alice");
  type($('input[type=password]'), "错的密码");
  btn("登录").click();
  say(await waitFor(() => toast().includes("用户名或密码不对")), `提示：「${toast()}」`);
  say(hash() === "#登录" && jar === "", "还在登录页，没拿到 cookie");

  console.log("六、换个人");
  btn("没有账号？注册").click();
  await waitFor(() => hash() === "#注册");
  type($('input[type=text]'), "bob");
  type($('input[type=password]'), "bobpass");
  btn("注册").click();
  say(await waitFor(() => hash() === "#笔记列表"), `bob 注册完进了列表：${hash()}`);
  await sleep(300);
  say($$("tbody tr").length === 0 && !w.document.body.textContent.includes("alice 的"),
      `bob 看不到 alice 的：${$$("tbody tr").length} 行`);

  console.log("七、服务端");
  say(!/Traceback/.test(log), "服务日志里没有 Traceback");
  say(!calls.some(c => c.status >= 500), "没有 5xx");

  console.log(`\n${"=".repeat(50)}\n通过 ${pass}，失败 ${fail}`);
  if (fail) console.log("\n服务日志最后几行：\n" + log.split("\n").slice(-15).join("\n"));
  stop(fail ? 1 : 0);
})().catch(e => { console.log("测试台自己炸了：", e); process.exit(2); });
