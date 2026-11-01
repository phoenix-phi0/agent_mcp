// kg_v4 界面多语言（K180）的端到端测试：真服务（gen run --登录）+ 真生成的页面，jsdom 里点。
//
//     cd tests/e2e && node i18n_run.js
//
// 搭环境：拷仓库 kg_v4（自带 i18n/ja.tsv）到 /tmp/e2e_i18n（不带 app.db / web / uploads），
// 建 t1（教师）、s1、s2（学生；口令走环境变量，只进本测试自建的临时库），裁小的内容
// （e2e_walk 口径）经 init_data 灌库；gen run --登录 离线假模型，端口 8185
// （I18N_E2E_PORT 能改；别的 e2e 用 8186–8199）。
//
// jsdom 的两个限制，模拟办法（写明，免得看成 bug）：
//   - 每个页面实例的 localStorage 互不相通：openPage 里预置 zs_i18n 模拟「这个浏览器
//     里存的语言」，不预置就是默认中文。
//   - location.reload() 不真的刷新：切语言成功后重开一个页面实例当「刷新后」。
//     cookie（登录态）在 jar 里全局共享，跟真浏览器一致。
//
// 语言切换的约定（见 app.js 模板 i18n 段注释）：登录后记在账号上（auth_me 的 lang /
// POST /account/lang），没登录记在浏览器 localStorage，默认中文；登录页不显示顶栏，
// 语言切换按钮在登录后的顶栏「中文 / 日本語」。
//
// 顺序：
//   一、登录页语言：默认中文；浏览器存过 ja 时登录页直接日文（tdom 首屏替换）；
//       日文登录页输错密码：报错消息也是日文（后端消息 tmsg）
//   二、学生 s1：登录是中文 → 顶栏点「日本語」→ POST /account/lang + 整页刷新 →
//       刷新后导航、退出登录全日文；换一个浏览器（localStorage 空）也日文——语言记在
//       账号上（me.lang）；做题页提示和「开始」按钮日文；切回「中文」全部恢复
//   三、教师 t1：教师端同样一遍：落学情、「教师端」标识 → 切日本語 →「教師ページ」、
//       学習状況、学生管理页的说明句日文 → 切回中文恢复
//   四、别的用户不受影响：s2 没切过，登录是中文
//   五、接口：POST /account/lang 只认 zh/ja（ko → 400）；服务端无 5xx、无 Traceback

const { execFileSync, spawn } = require("child_process");
const fs = require("fs");
const net = require("net");
const { JSDOM, VirtualConsole } = require("jsdom");

const MCP = process.env.M || require("path").resolve(__dirname, "../..");
const PY = MCP + "/.venv/bin/python";
const PROJ = "/tmp/e2e_i18n/kg_v4";
const PORT = Number(process.env.I18N_E2E_PORT || 8185);
const BASE = `http://127.0.0.1:${PORT}`;
const WEB = PROJ + "/web";
const MOCK = "/tmp/e2e_i18n/mock.json";
const REPLY = "这是老师的回答。";
const PW = "i18n-e2e-临时口令";
const JA = { 提示: "レベルと出題ポイントを選び", 学生说明: "学生アカウントは先生が作成します" };

let pass = 0, fail = 0;
const say = (ok, msg) => { ok ? pass++ : fail++; console.log((ok ? "  ✓ " : "  ✗ ") + msg); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function waitFor(fn, ms = 8000) {
  const t = Date.now();
  while (Date.now() - t < ms) {
    try { if (fn()) return true; } catch (e) { /* 还没渲染 */ }
    await sleep(30);
  }
  return false;
}
function portFree(port) {
  return new Promise(res => {
    const s = net.connect(port, "127.0.0.1");
    s.on("connect", () => { s.destroy(); res(false); });
    s.on("error", () => res(true));
  });
}

// 浏览器的 cookie：一个 jar，所有页面共用（换页、开新页面实例不丢登录）。
// 模拟「换一个浏览器」就把 jar 清空重新登录。
let jar = "";
const calls = [];
async function browserFetch(u, o = {}) {
  const url = new URL(u, BASE);
  const headers = Object.assign({}, o.headers || {});
  if (jar) headers["Cookie"] = `zs_auth=${jar}`;
  const r = await fetch(url, { ...o, headers, signal: undefined });
  const sets = r.headers.getSetCookie ? r.headers.getSetCookie() : [];
  for (const c of sets) {
    const m = /^zs_auth=([^;]*)/.exec(c);
    if (!m) continue;
    jar = (!m[1] || /Max-Age=0|expires=Thu, 01 Jan 1970/i.test(c)) ? "" : m[1];
  }
  calls.push({ path: url.pathname, status: r.status });
  return r;
}

// path：/ 是学生端，/teacher 是教师端。locale：预置 localStorage 里的 zs_i18n
//（模拟这个浏览器之前选过的语言）；不传 = localStorage 空 = 默认中文。
// 页面 html 里的 <script src> 全剥掉，i18n.ja.js 由这里按 head 里的顺序先 eval，
// 再 Vue、再 app.js——跟浏览器里的加载顺序一致。i18n.ja.js 是服务启动时 build
// 出来的，这里每次现读（脚本刚启动时 web/ 还不存在）。
function openPage(hash, path = "/", locale = null) {
  const name = path === "/" ? "index" : path.slice(1);
  const html = fs.readFileSync(WEB + `/${name}.html`, "utf8")
    .replace(/<script src="[^"]*"><\/script>/g, "");
  const left = [];
  const vc = new VirtualConsole();
  vc.on("jsdomError", e => { if (/navigation/i.test(e.message)) left.push(e.message); });
  const dom = new JSDOM(html, { url: BASE + path + (hash || ""), runScripts: "outside-only", virtualConsole: vc });
  const w = dom.window;
  if (locale) w.localStorage.setItem("zs_i18n", locale);
  w.fetch = browserFetch;
  w.console.log = () => {};
  w.console.warn = () => {};
  w.Element.prototype.scrollIntoView = function () {};
  let i18nSrc = "";
  try { i18nSrc = fs.readFileSync(WEB + "/i18n.ja.js", "utf8"); } catch (e) { /* 服务还没 build 出来 */ }
  w.eval(i18nSrc);
  w.eval(fs.readFileSync(WEB + "/vue.global.prod.js", "utf8"));
  w.eval(fs.readFileSync(WEB + (path === "/" ? "/app.js" : `/${name}.js`), "utf8"));
  const $ = s => w.document.querySelector(s);
  const $$ = s => [...w.document.querySelectorAll(s)];
  const pg = {
    w, $, $$, left,
    btn: t => $$("button").find(b => b.textContent.trim() === t),
    nav: t => $$("nav a").find(a => a.textContent.trim() === t),
    navText: () => (($("nav") || {}).textContent || ""),
    pages: () => $$("nav > a").map(a => a.textContent.trim()),
    langBtns: () => $$(".nav-lang a").map(a => a.textContent.trim()),
    langBtn: t => $$(".nav-lang a").find(a => a.textContent.trim() === t),
    hash: () => decodeURIComponent(w.location.hash),
    toast: () => ($(".toast") || {}).textContent || "",
    screen: () => ($(".screen") || {}).textContent || "",
    type: (el, v) => { el.value = v; el.dispatchEvent(new w.Event("input")); },
    field: lbl => {
      const l = $$("label.field").find(x => (x.querySelector(".lbl") || {}).textContent.replace("*", "").trim() === lbl);
      return l && l.querySelector("input, textarea, select");
    },
    // 不真关：jsdom 的 close() 会拆掉 window，残留的 refreshMe 回调醒来碰 document
    // 会炸；测试进程退出时一起回收
    close: () => {},
  };
  return pg;
}

async function typeLogin(p, user, pw, userLbl = "用户名", loginBtn = "登录") {
  await waitFor(() => p.hash() === "#登录" && p.field(userLbl));
  p.type(p.field(userLbl), user);
  p.type(p.$('input[type=password]'), pw);
  p.btn(loginBtn).click();
  return waitFor(() => jar);
}

(async () => {
  if (!(await portFree(PORT))) {
    console.log(`端口 ${PORT} 已经被占用，不去连别人的服务。先停掉它再跑`);
    process.exit(1);
  }
  fs.rmSync("/tmp/e2e_i18n", { recursive: true, force: true });
  execFileSync(PY, ["-c", [
    "import sys, os, shutil, pathlib, subprocess, sqlite3, time",
    "sys.path.insert(0, '.')",
    "from pathlib import Path",
    "ws = pathlib.Path('/tmp/e2e_i18n'); ws.mkdir()",
    "proj = ws / 'kg_v4'",
    "shutil.copytree('kg_v4', proj, ignore=shutil.ignore_patterns('app.db', 'web', 'uploads', 'sessions', '.auth_secret', '__pycache__'))",
    "assert (proj / 'i18n' / 'ja.tsv').is_file(), 'kg_v4 自带的 i18n/ja.tsv 得在'",
    "content = ws / 'content'",
    "shutil.copytree('kg/content', content, ignore=shutil.ignore_patterns('translate', 'series'))",
    "for f in ('words.jsonl', 'words_jlpt.jsonl'):",
    "    p = content / f",
    "    p.write_text('\\n'.join(p.read_text(encoding='utf-8').splitlines()[:100]) + '\\n', encoding='utf-8')",
    "quiz = ws / 'quiz_empty'; quiz.mkdir()",
    "from gen.project import ensure_db",
    "print(ensure_db(proj))",
    "from tools.auth import hash_password",
    "con = sqlite3.connect(proj / 'app.db')",
    "now = time.strftime('%Y-%m-%d %H:%M:%S')",
    "for u, role in (('t1', 'teacher'), ('s1', 'student'), ('s2', 'student')):",
    "    con.execute('INSERT INTO account_user(username,password_hash,display_name,role,disabled,created_at) VALUES(?,?,?,?,0,?)',",
    "                (u, hash_password(os.environ['E2E_I18N_PW']), u, role, now))",
    "con.commit(); con.close()",
    "subprocess.run([sys.executable, 'kg_v4/setup/init_data.py', str(proj), '--content', str(content), '--quiz', str(quiz)], check=True)",
  ].join("\n")], { cwd: MCP, encoding: "utf8", env: Object.assign({}, process.env, { E2E_I18N_PW: PW }) });

  fs.writeFileSync(MOCK, JSON.stringify({ rules: [], default: REPLY }));
  const server = spawn(PY, ["-m", "gen", "run", PROJ, "--登录", "--port", String(PORT),
                            "--不开浏览器", "--host", "127.0.0.1"],
                       { cwd: MCP, stdio: ["ignore", "pipe", "pipe"],
                         env: Object.assign({}, process.env, { DSL_MOCK_SCRIPT: MOCK }) });
  let log = "";
  server.stdout.on("data", d => { log += d; });
  server.stderr.on("data", d => { log += d; });
  const stop = code => {
    try { server.kill("SIGTERM"); } catch (e) { /* 已经退了 */ }
    process.exit(code);
  };
  let up = false;
  for (let i = 0; i < 200 && !up; i++) {
    try { up = (await fetch(BASE + "/")).ok; } catch (e) { /* 还没起来 */ }
    if (!up) await sleep(100);
  }
  if (!up) { console.log("服务没起来：\n" + log); stop(1); }

  try {
    say(/界面多语言 ja：\d+ 条/.test(log), "启动日志：多人模式 + 界面多语言 ja 已编译（" + (log.match(/界面多语言 ja：\d+ 条/) || ["没找到"])[0] + "）");
    const navText = p => p.navText();

    console.log("一、登录页语言");
    let p = openPage("");
    await waitFor(() => p.hash() === "#登录");
    say(await waitFor(() => !!p.field("用户名")) && !p.field("ユーザー名"),
        "默认中文：登录页是「用户名/密码」");
    say(!p.$("nav"), "登录页不显示顶栏（切换按钮在登录后的顶栏；登录页语言跟浏览器 localStorage，默认中文）");
    p.close();
    p = openPage("", "/", "ja");
    say(await waitFor(() => !!p.field("ユーザー名")), "浏览器存过 ja：登录页直接日文");
    p.type(p.field("ユーザー名"), "s1");
    p.type(p.$('input[type=password]'), "wrong-pass");
    p.btn("ログイン").click();
    say(await waitFor(() => p.toast().includes("ユーザー名かパスワードが違います")),
        `日文登录页输错密码：消息也日文：「${p.toast()}」`);
    p.close();

    console.log("二、学生 s1");
    p = openPage("");
    await typeLogin(p, "s1", PW);
    say(await waitFor(() => navText(p).includes("知识图谱")), "登录：中文界面（这个账号还没切过）");
    say(await waitFor(() => p.langBtns().join("/") === "中文/日本語"),
        `顶栏「中文 / 日本語」：${p.langBtns().join("/")}`);
    calls.length = 0;
    p.langBtn("日本語").click();
    say(await waitFor(() => calls.some(c => c.path === "/account/lang" && c.status === 200)),
        "点日本語：POST /account/lang 200");
    say(await waitFor(() => p.left.length > 0), "然后整页刷新（location.reload）");
    p.close();
    p = openPage("", "/", "ja");
    say(await waitFor(() => ["知識マップ", "練習", "書き取り", "先生に質問", "学習進度"].every(t => navText(p).includes(t))
                      && !navText(p).includes("知识图谱")),
        `刷新后导航日文：${navText(p).slice(0, 50)}…`);
    say(await waitFor(() => navText(p).includes("ログアウト"))
          && p.w.document.documentElement.lang === "ja",
        "退出登录也日文，html lang=ja");
    p.w.location.hash = "#" + encodeURIComponent("做题");
    say(await waitFor(() => p.screen().includes(JA.提示)), "做题页提示日文");
    say(await waitFor(() => !!p.btn("スタート")), "「开始」按钮 →「スタート」");
    // 换一个浏览器：localStorage 空、只有账号。语言记在账号上（me.lang），照样日文
    p.close();
    p = openPage("");
    say(await waitFor(() => navText(p).includes("知識マップ") && !navText(p).includes("知识图谱")),
        "换一个浏览器（localStorage 空）打开：也日文——语言记在账号上");
    calls.length = 0;
    p.langBtn("中文").click();
    say(await waitFor(() => calls.some(c => c.path === "/account/lang" && c.status === 200)),
        "切回中文：POST /account/lang lang=zh");
    p.close();
    p = openPage("", "/", "zh");
    say(await waitFor(() => navText(p).includes("知识图谱") && !navText(p).includes("知識マップ")),
        "切回中文：界面恢复");
    p.close();

    console.log("三、教师 t1");
    jar = "";
    p = openPage("", "/teacher");
    await typeLogin(p, "t1", PW);
    say(await waitFor(() => (p.$("nav a.active") || { textContent: "" }).textContent.trim() === "学情"),
        "教师登录：落在学情（中文）");
    say(await waitFor(() => (p.$(".nav-badge") || { textContent: "" }).textContent.trim() === "教师端"),
        "「教师端」标识");
    calls.length = 0;
    p.langBtn("日本語").click();
    say(await waitFor(() => calls.some(c => c.path === "/account/lang" && c.status === 200) && p.left.length > 0),
        "点日本語：POST + 刷新");
    p.close();
    p = openPage("", "/teacher", "ja");
    say(await waitFor(() => (p.$(".nav-badge") || { textContent: "" }).textContent.trim() === "教師ページ"),
        "刷新后「教師ページ」");
    say(await waitFor(() => navText(p).includes("学習状況") && navText(p).includes("ログアウト")
                      && !navText(p).includes("学情") && !navText(p).includes("退出登录")),
        "导航「学習状況」、退出「ログアウト」");
    p.nav("学生管理").click();
    say(await waitFor(() => p.screen().includes(JA.学生说明)), "学生管理页的说明句日文");
    calls.length = 0;
    p.langBtn("中文").click();
    say(await waitFor(() => calls.some(c => c.path === "/account/lang" && c.status === 200)),
        "教师切回中文");
    p.close();
    p = openPage("", "/teacher", "zh");
    say(await waitFor(() => (p.$(".nav-badge") || { textContent: "" }).textContent.trim() === "教师端"
                      && navText(p).includes("学情")),
        "教师端恢复中文");
    p.close();

    console.log("四、别的用户不受影响");
    jar = "";
    p = openPage("");
    await typeLogin(p, "s2", PW);
    say(await waitFor(() => navText(p).includes("知识图谱") && !navText(p).includes("知識マップ")),
        "s2（没切过）：默认中文");
    say(p.w.document.documentElement.lang === "zh-CN", "html lang=zh-CN");
    p.close();

    console.log("五、接口与服务端");
    const r = await fetch(BASE + "/account/lang", { method: "POST",
      headers: { "Content-Type": "application/json", Cookie: `zs_auth=${jar}` },
      body: JSON.stringify({ action: "account_lang", form: { lang: "ko" } }) });
    say(r.status === 400, `POST /account/lang lang=ko：400（只认 zh/ja）：${r.status}`);
    const r2 = await fetch(BASE + "/account/lang", { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "account_lang", form: { lang: "ja" } }) });
    say(r2.status === 401, `没登录调 /account/lang：401：${r2.status}`);
    say(!calls.some(c => c.status >= 500), "没有 5xx");
    say(!/Traceback/.test(log), "服务日志里没有 Traceback");
  } catch (e) {
    say(false, "跑挂了：" + (e && e.stack || e));
  }

  console.log(`\n${"=".repeat(50)}\n通过 ${pass}，失败 ${fail}`);
  if (fail) console.log("---- 服务日志（末尾）----\n" + log.slice(-2500));
  stop(fail ? 1 : 0);
})();
