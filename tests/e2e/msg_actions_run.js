// 消息带按钮（E1）：后端回的消息里有 actions，前端在消息下面画按钮，点了调对应动作。
//
//     cd tests/e2e && node msg_actions_run.js
//
// 测试专用的小项目（/tmp/e2e_msg_actions），不碰 kg、kg_v4：
//   ui/chat.ui       消息流 talk 写了「按钮 draft_confirm,draft_drop」
//   routes/chat.zs   chat_send 回一条带 actions 的草稿消息（确认、放弃、一个白名单外的
//                    secret_op、一个缺 action 的），再回一条不带 actions 的
//                    draft_confirm / draft_drop 把收到的参数原样说回来
//                    secret_op 接口真的存在——白名单外的动作即使有接口也不该被调
//
// 按人的操作顺序：输入、发送 → 草稿消息下只出「确认」「放弃」两个按钮、不带 actions
// 的消息没有按钮 → 点「确认」→ 请求打到 /draft/confirm、带着 carry 里的 draft_id 和
// 有空格的 note、表单里的 content 也在 → 回来的消息进了同一条流。再点「放弃」走另一个
// 动作。全程没有请求打到 /secret。

const { execFileSync, spawn } = require("child_process");
const fs = require("fs");
const { JSDOM } = require("jsdom");

const MCP = process.env.M || require("path").resolve(__dirname, "../..");
const PY = MCP + "/.venv/bin/python";
const PROJ = "/tmp/e2e_msg_actions";
const PORT = 8197;
const BASE = `http://127.0.0.1:${PORT}`;

let pass = 0, fail = 0;
const say = (ok, msg) => { ok ? pass++ : fail++; console.log((ok ? "  ✓ " : "  ✗ ") + msg); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function waitFor(fn, ms = 4000) {
  const t = Date.now();
  while (Date.now() - t < ms) {
    try { if (fn()) return true; } catch (e) { /* 还没渲染 */ }
    await sleep(30);
  }
  return false;
}
const py = args => execFileSync(PY, args, { cwd: MCP, encoding: "utf8" });

const UI = `界面 自定义 助手
  消息流 talk 占满 按钮 draft_confirm,draft_drop
  分组 底 底栏
    字段 content 控件 多行 单行高
    动作 chat_send 提交 远程 发送
  结束
结束
`;

const ROUTES = `接口 POST /chat/send 动作 chat_send
  设 acts = [{"label":"确认","action":"draft_confirm","carry":{"draft_id":7,"note":"甲 乙"},"kind":"primary"},{"label":"越权","action":"secret_op","carry":{"x":1}},{"label":"缺动作"},{"label":"放弃","action":"draft_drop","carry":{"draft_id":7},"kind":"danger"}]
  设 m.who = 助手
  设 m.text = 草稿：{content}
  设 m.actions = 解析JSON {acts}
  设 n.who = 助手
  设 n.text = 这条没有按钮
  响应 messages {m}
  响应 messages {n}
结束

接口 POST /draft/confirm 动作 draft_confirm
  设 m.who = 系统
  设 m.text = 已确认 id={draft_id} note={note 或} content={content 或}
  设 m.kind = ok
  响应 messages {m}
结束

接口 POST /draft/drop 动作 draft_drop
  设 m.who = 系统
  设 m.text = 已放弃 id={draft_id} note={note 或}
  响应 messages {m}
结束

接口 POST /secret 动作 secret_op
  设 m.who = 系统
  设 m.text = 不该被调
  响应 messages {m}
结束
`;

let server = null;
(async () => {
  fs.rmSync(PROJ, { recursive: true, force: true });
  py(["-m", "gen", "init", PROJ, "--空"]);
  fs.writeFileSync(PROJ + "/entities/chat.entity",
    "实体 chat 对话\n  字段 content 文本 内容\n结束\n");
  fs.mkdirSync(PROJ + "/ui", { recursive: true });
  fs.mkdirSync(PROJ + "/routes", { recursive: true });
  fs.writeFileSync(PROJ + "/ui/chat.ui", UI);
  fs.writeFileSync(PROJ + "/routes/chat.zs", ROUTES);

  server = spawn(PY, ["-m", "gen", "run", PROJ, "--port", String(PORT), "--不开浏览器"],
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
  const html = fs.readFileSync(web + "/index.html", "utf8")
    .replace(/<script src="[^"]*"><\/script>/g, "");
  const dom = new JSDOM(html, { url: BASE + "/", runScripts: "outside-only" });
  const w = dom.window;
  w.fetch = async (u, o) => {
    const url = new URL(u, BASE);
    let body = null;
    try { body = JSON.parse(o && o.body); } catch (e) { /* 不是 JSON */ }
    const r = await fetch(url, { ...o, signal: undefined });
    calls.push({ path: url.pathname, status: r.status, body });
    return r;
  };
  w.console.log = () => {};
  w.eval(fs.readFileSync(web + "/vue.global.prod.js", "utf8"));
  w.eval(fs.readFileSync(web + "/app.js", "utf8"));

  const $ = s => w.document.querySelector(s);
  const $$ = s => [...w.document.querySelectorAll(s)];
  const btn = t => $$("button").find(b => b.textContent.trim() === t);
  const msgs = () => $$(".smsg").map(m => ({
    text: (m.querySelector(".body") || {}).textContent || "",
    buttons: [...m.querySelectorAll(".smsg-actions button")].map(b => b.textContent.trim()),
    card: m.classList.contains("smsg-card"),
  }));
  const type = (el, v) => { el.value = v; el.dispatchEvent(new w.Event("input")); };

  console.log("一、发一句，后端回一条带 actions 的草稿消息");
  await waitFor(() => $("textarea"));
  type($("textarea"), "出三道题 关于て形");
  btn("发送").click();
  say(await waitFor(() => msgs().some(m => m.text.startsWith("草稿："))), "草稿消息进了消息流");
  const draft = msgs().find(m => m.text.startsWith("草稿："));
  say(draft && JSON.stringify(draft.buttons) === JSON.stringify(["确认", "放弃"]),
      `只画白名单里的两个按钮（越权的 secret_op、缺 action 的不画）：${JSON.stringify(draft && draft.buttons)}`);
  say(draft && draft.card, "带按钮的消息加了 smsg-card");
  const plain = msgs().find(m => m.text === "这条没有按钮");
  const plainEl = $$(".smsg").find(el => (el.querySelector(".body") || {}).textContent === "这条没有按钮");
  say(plain && plain.buttons.length === 0 && !plain.card && plainEl && !plainEl.querySelector(".smsg-actions"),
      "不带 actions 的消息：没有按钮区、不加卡片样式");
  const b1 = $$(".smsg-actions button").find(b => b.textContent.trim() === "确认");
  const b2 = $$(".smsg-actions button").find(b => b.textContent.trim() === "放弃");
  say(b1 && b1.classList.contains("btn-primary") && b2 && b2.classList.contains("btn-danger"),
      `kind 落到样式：确认 ${b1 && b1.className}，放弃 ${b2 && b2.className}`);

  console.log("二、点「确认」：调 draft_confirm，参数是 carry + 表单");
  calls.length = 0;
  b1.click();
  say(await waitFor(() => msgs().some(m => m.text.startsWith("已确认"))), "确认的返回进了同一条消息流");
  const c1 = calls.find(c => c.path === "/draft/confirm");
  say(!!c1 && c1.status === 200, `请求打到 /draft/confirm：${JSON.stringify(calls.map(c => c.path))}`);
  say(c1 && c1.body && c1.body.action === "draft_confirm" && c1.body.form.draft_id === 7
      && c1.body.form.note === "甲 乙" && c1.body.form.content === "出三道题 关于て形",
      `请求体：${JSON.stringify(c1 && c1.body)}`);
  const ok = msgs().find(m => m.text.startsWith("已确认"));
  say(ok && ok.text === "已确认 id=7 note=甲 乙 content=出三道题 关于て形",
      `后端收到的参数（带空格的 note 不错位）：${ok && ok.text}`);

  console.log("三、点「放弃」：调另一个动作");
  calls.length = 0;
  $$(".smsg-actions button").find(b => b.textContent.trim() === "放弃").click();
  say(await waitFor(() => msgs().some(m => m.text.startsWith("已放弃"))), "放弃的返回进了消息流");
  say(calls.length === 1 && calls[0].path === "/draft/drop" && calls[0].body.form.draft_id === 7
      && !("note" in calls[0].body.form),
      `只发了一个 /draft/drop，带 draft_id=7（这次 carry 里没有 note）：${JSON.stringify(calls.map(c => [c.path, c.body && c.body.form]))}`);

  console.log("四、白名单外的动作");
  say(!$$("button").some(b => b.textContent.trim() === "越权"), "「越权」按钮根本没画出来");
  say(!calls.some(c => c.path === "/secret"), "全程没有请求打到 /secret（接口其实存在）");
  // 对照：/secret 接口是真的，直接打得通——上面没打到不是因为它不存在
  const direct = await fetch(BASE + "/secret", { method: "POST", headers: { "Content-Type": "application/json" },
                                                 body: JSON.stringify({ action: "secret_op", form: {} }) });
  say(direct.status === 200, `对照：/secret 直接打是通的（${direct.status}）`);

  console.log("五、服务端");
  say(!/Traceback/.test(log), "服务日志里没有 Traceback");

  console.log(`\n${"=".repeat(50)}\n通过 ${pass}，失败 ${fail}`);
  if (fail) console.log("\n服务日志最后几行：\n" + log.split("\n").slice(-12).join("\n"));
  stop(fail ? 1 : 0);
})().catch(e => {
  // 测试台炸了也要把服务停掉，不然它占着端口，下一次跑连的是这个旧服务
  console.log("测试台自己炸了：", e);
  if (server) server.kill();
  process.exit(2);
});
