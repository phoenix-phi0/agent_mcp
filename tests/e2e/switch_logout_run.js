// 「认证 换端 先退出」（K177）的端到端测试：真服务（gen run --登录）+ kg 真实生成的页面，在 jsdom 里点。
//
//     cd tests/e2e && node switch_logout_run.js
//
// 照 kg 搭一份到 /tmp/e2e_switch_logout，routes/auth.zs 顶部加一行「认证 换端
// 先退出」，建教师 t1（命令行，密码走环境变量）、学生 s1（走 /student/create，
// 跟教师在「学生管理」页建账号同一个接口），起服务带 --登录。
// 端口 8185（SWITCH_LOGOUT_E2E_PORT 能改）：8197 上跑着常驻的 kg，别的 e2e
// 用 8186-8190、8191-8199。
//
// 按人的操作顺序：
//   一、教师在教师端登录：顶栏链接是「退出并打开学生端」，href=/，没有 target
//       （不再开新标签页）
//   二、退出接口故意失败（fetch 打桩回 500）：点链接弹「退出没成功，请稍后再试」，
//       留在原页，没跳走、cookie 还在
//   三、撤桩再点：先调 /auth/logout（200），然后本标签页跳去 /；cookie 删了
//   四、打开 /：落在登录页；学生 s1 登录进学生端；主页面没有换端链接
//   五、服务端没有 5xx、没有 Traceback

const { execFileSync, spawn } = require("child_process");
const fs = require("fs");
const net = require("net");
const { JSDOM, VirtualConsole } = require("jsdom");

const MCP = process.env.M || require("path").resolve(__dirname, "../..");
const PY = MCP + "/.venv/bin/python";
const PROJ = "/tmp/e2e_switch_logout";
const PORT = Number(process.env.SWITCH_LOGOUT_E2E_PORT || 8185);
const BASE = `http://127.0.0.1:${PORT}`;
const WEB = PROJ + "/web";
const TEACHER_PW = "teach-e2e-sw";

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
function portFree(port) {
  return new Promise(res => {
    const s = net.connect(port, "127.0.0.1");
    s.on("connect", () => { s.destroy(); res(false); });
    s.on("error", () => res(true));
  });
}

// 浏览器的 cookie：一个 jar，所有页面共用（跟真浏览器一样，换页不丢登录）
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

// path：/ 是学生端，/teacher 是教师端。页面要换到别的地址（location.href = "/"）
// 时 jsdom 不真的跳，只报一条「Not implemented: navigation」：记在 pg.left 里
function openPage(hash, path = "/") {
  const name = path === "/" ? "index" : path.slice(1);
  const html = fs.readFileSync(WEB + `/${name}.html`, "utf8")
    .replace(/<script src="[^"]*"><\/script>/g, "");
  const left = [];
  const vc = new VirtualConsole();
  vc.on("jsdomError", e => { if (/navigation/i.test(e.message)) left.push(e.message); });
  const dom = new JSDOM(html, { url: BASE + path + (hash || ""), runScripts: "outside-only", virtualConsole: vc });
  const w = dom.window;
  w.fetch = browserFetch;
  w.console.log = () => {};
  w.console.warn = () => {};
  w.Element.prototype.scrollIntoView = function () {};
  w.eval(fs.readFileSync(WEB + "/vue.global.prod.js", "utf8"));
  w.eval(fs.readFileSync(WEB + (path === "/" ? "/app.js" : `/${name}.js`), "utf8"));
  const $ = s => w.document.querySelector(s);
  const $$ = s => [...w.document.querySelectorAll(s)];
  const pg = {
    w, $, $$, left,
    nav: t => $$("nav a").find(a => a.textContent.trim() === t),
    navText: () => ($("nav") || {}).textContent || "",
    hash: () => decodeURIComponent(w.location.hash),
    toast: () => ($(".toast") || {}).textContent || "",
    type: (el, v) => { el.value = v; el.dispatchEvent(new w.Event("input")); },
    // 按标签找输入框（标签后面的必填星号不算）
    field: lbl => {
      const l = $$("label.field").find(x => (x.querySelector(".lbl") || {}).textContent.replace("*", "").trim() === lbl);
      return l && l.querySelector("input, textarea, select");
    },
    btn: t => $$("button").find(b => b.textContent.trim() === t),
    close: () => w.close(),
  };
  return pg;
}

async function typeLogin(p, user, pw) {
  await waitFor(() => p.hash() === "#登录" && p.field("用户名"));
  p.type(p.field("用户名"), user);
  p.type(p.$('input[type=password]'), pw);
  p.btn("登录").click();
}
async function login(p, user, pw) {
  await typeLogin(p, user, pw);
  return waitFor(() => p.hash() !== "#登录" && jar);
}

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
    "p = ws / 'routes' / 'auth.zs'",
    "t = p.read_text(encoding='utf-8')",
    "anchor = '认证 角色 student 学生 拒绝 教师账号不参与学习，请用学生账号'",
    "assert anchor in t",
    "p.write_text(t.replace(anchor, anchor + chr(10) + '认证 换端 先退出'), encoding='utf-8')",
    "shutil.copytree('kg/ui', ws / 'ui')",
    "c = client(ws)",
    "assert c.post('/kg/import2', json={'form': {}}).status_code == 200",
    "r = c.post('/student/create', json={'form': {'username': 's1', 'display_name': '小一', 'password': 's1-pass'}})",
    "assert r.status_code == 200, r.get_json()",
  ].join("\n")], { cwd: MCP, encoding: "utf8" });
  // 教师只能命令行建。密码从环境变量读，不进命令行
  execFileSync(PY, ["-m", "kg", "建教师", "t1", "--显示名", "王老师", "--库", PROJ + "/app.db",
                    "--密码环境变量", "E2E_TEACHER_PW"],
               { cwd: MCP, encoding: "utf8", env: Object.assign({}, process.env, { E2E_TEACHER_PW: TEACHER_PW }) });

  const server = spawn(PY, ["-m", "gen", "run", PROJ, "--port", String(PORT), "--不开浏览器", "--登录"],
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
  say(log.includes("要求登录（多人模式）"), "启动日志说了是多人模式");

  try {
    console.log("一、教师端登录，链接换文案、本标签页");
    let p = openPage("", "/teacher");
    say(await login(p, "t1", TEACHER_PW), "教师在教师端登录");
    const home = () => p.$("nav .nav-home a");
    say(await waitFor(() => home() && home().textContent.trim() === "退出并打开学生端"),
        `链接是「退出并打开学生端」：${home() && home().textContent.trim()}`);
    say(home() && home().getAttribute("href") === "/" && home().getAttribute("target") === null,
        `href=/、没有 target（本标签页）：${home() && home().getAttribute("target")}`);
    say(await waitFor(() => p.navText().includes("王老师")), "顶栏有「王老师」");

    console.log("二、退出接口失败：弹提示、留在原页");
    const realFetch = p.w.fetch;
    p.w.fetch = async (u, o = {}) => {
      const url = new URL(u, BASE);
      if (url.pathname === "/auth/logout") return { ok: false, status: 500 };
      return realFetch(u, o);
    };
    const leftBefore = p.left.length;
    home().click();
    say(await waitFor(() => p.toast().includes("退出没成功，请稍后再试")), `提示：${p.toast()}`);
    say(p.left.length === leftBefore, "留在原页，没跳走");
    say(!!jar, "cookie 还在（没退出）");
    p.w.fetch = realFetch;

    console.log("三、退出成功：先调接口，再本标签页去 /");
    calls.length = 0;
    home().click();
    say(await waitFor(() => p.left.length > leftBefore), "本标签页跳走了");
    say(calls.some(c => c.path === "/auth/logout" && c.status === 200),
        `先调了 /auth/logout 200：${JSON.stringify(calls)}`);
    say(jar === "", "cookie 删了（真的退出了）");
    p.close();

    console.log("四、/ 是登录页，学生登录进学生端");
    p = openPage("");
    say(await waitFor(() => p.hash() === "#登录"), `打开 / 落在登录页：${p.hash()}`);
    await typeLogin(p, "s1", "s1-pass");
    say(await waitFor(() => p.hash() !== "#登录" && jar), "学生 s1 登录成功");
    say(await waitFor(() => p.navText().includes("小一")), "顶栏是「小一」");
    say(!p.$("nav .nav-home"), "学生端（主页面）没有换端链接");
    say(["知识图谱", "做题", "默写", "问老师", "教材", "学习进度"].every(t => p.nav(t)),
        "学习的页面都在");
    p.close();

    console.log("五、服务端");
    say(!/Traceback/.test(log), "服务日志里没有 Traceback");
    say(!calls.some(c => c.status >= 500), `没有 5xx：${JSON.stringify(calls.filter(c => c.status >= 500))}`);
  } catch (e) {
    say(false, "跑挂了：" + (e && e.stack || e));
  }

  console.log(`\n${"=".repeat(50)}\n通过 ${pass}，失败 ${fail}`);
  if (fail) console.log("---- 服务日志（末尾）----\n" + log.slice(-2000));
  stop(fail ? 1 : 0);
})();
