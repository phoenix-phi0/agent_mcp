// 学生端、教师端两个页面（单人模式）的端到端测试：真服务 + kg 真实生成的页面。
//
//     cd tests/e2e && node ends_run.js
//
// 引擎按界面的「端」把 kg 拆成两个页面（gen/project.py 的 split_pages）：学生端 /
// （web/index.html + app.js），教师端 /teacher（web/teacher.html + teacher.js，/教师
// 是别名）。多人模式（登录、交叉登录被拒或送走）在 multiuser_run.js。
//
// 照 kg 搭一份到 /tmp/e2e_ends，导入知识点和课文，gen run 起服务（单人模式、假模型）。
// 端口 8189（ENDS_E2E_PORT 能改）：8197 上跑着常驻的 kg，别的 e2e 用 8186–8188、8191–8199。
//
// 按人的操作顺序：
//   一、HTTP：/ 和 /teacher、/教师 都是 200，各是各的页面（标题分得开）
//   二、学生端：只有学习的页面，没有「管理」那组、没有教师页、没有「教师端」标识；
//       不用登录
//   三、学生端手打 #学情、#教材导入：不进，退回首页并提示在教师端；没调教师接口
//   四、教师端：不用登录，直接落在「学情」；导航只有教师页；「教师端」标识、
//       「打开学生端」；学情、学生管理的接口都 200
//   五、教师端手打 #做题：不进，退回学情并提示在学生端；没调做题接口
//   六、服务端没有 5xx、没有 Traceback

const { execFileSync, spawn } = require("child_process");
const fs = require("fs");
const net = require("net");
const { JSDOM } = require("jsdom");

const MCP = "/home/ysc/mcp";
const PY = MCP + "/.venv/bin/python";
const PROJ = "/tmp/e2e_ends";
const PORT = Number(process.env.ENDS_E2E_PORT || 8189);
const BASE = `http://127.0.0.1:${PORT}`;
const WEB = PROJ + "/web";

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
    calls.push({ path: url.pathname, status: r.status });
    return r;
  };
  w.console.log = () => {};
  w.console.warn = () => {};
  w.Element.prototype.scrollIntoView = function () {};
  w.eval(fs.readFileSync(WEB + "/vue.global.prod.js", "utf8"));
  w.eval(fs.readFileSync(WEB + (path === "/" ? "/app.js" : `/${name}.js`), "utf8"));
  const $ = s => w.document.querySelector(s);
  const $$ = s => [...w.document.querySelectorAll(s)];
  return {
    w, $, $$,
    nav: t => $$("nav a").find(a => a.textContent.trim() === t),
    pages: () => $$("nav > a").map(a => a.textContent.trim()),
    active: () => ((($("nav a.active") || {}).textContent) || "").trim(),
    hash: () => decodeURIComponent(w.location.hash),
    toast: () => ($(".toast") || {}).textContent || "",
    screen: () => ($(".screen") || {}).textContent || "",
    close: () => w.close(),
  };
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
    "shutil.copytree('kg/ui', ws / 'ui')",
    "c = client(ws)",
    "assert c.post('/kg/import2', json={'form': {}}).status_code == 200",
    "assert c.post('/lesson/import', json={'form': {}}).status_code == 200",
  ].join("\n")], { cwd: MCP, encoding: "utf8" });

  const server = spawn(PY, ["-m", "gen", "run", PROJ, "--port", String(PORT), "--不开浏览器", "--标题", "日语学习"],
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

  try {
    console.log("一、两个地址");
    say(log.includes("不用登录（单人模式）") && log.includes("教师端：/teacher"), "启动日志：单人模式，教师端在 /teacher");
    const get = async path => { const r = await fetch(BASE + path); return [r.status, await r.text()]; };
    let [st, body] = await get("/");
    say(st === 200 && body.includes("<title>日语学习</title>") && body.includes('src="./app.js"'), `/：学生端 ${st}`);
    for (const path of ["/teacher", "/" + encodeURIComponent("教师")]) {
      [st, body] = await get(path);
      say(st === 200 && body.includes("<title>日语学习·教师端</title>") && body.includes('src="./teacher.js"'),
          `${decodeURIComponent(path)}：教师端 ${st}`);
    }

    console.log("二、学生端");
    let p = openPage("");
    say(await waitFor(() => p.pages().join("|") === "知识图谱|学习进度|做题|默写|问老师|教材"),
        `只有学习的页面：${p.pages().join("|")}`);
    say(!p.$("nav .nav-side") && !p.nav("学情") && !p.nav("学生管理") && !p.nav("教材导入")
        && !p.$("nav").textContent.includes("管理"), "没有「管理」那组、没有教师页");
    say(!p.$("nav .nav-badge") && !p.$("nav .nav-home") && !p.$("nav").className.includes("nav-role"),
        "没有「教师端」标识，也没有「打开学生端」");
    say(p.hash() !== "#登录" && p.active() === "知识图谱", `不用登录，落在知识图谱：${p.active()}`);

    console.log("三、学生端手打教师页");
    for (const page of ["学情", "教材导入"]) {
      calls.length = 0;
      p.w.location.hash = "#" + encodeURIComponent(page);
      say(await waitFor(() => p.hash() === "#知识图谱" && p.toast().includes(`「${page}」在教师端（/teacher）`)),
          `#${page}：退回 ${p.hash()}，提示「${p.toast()}」`);
      await sleep(150);
      say(!calls.some(c => c.path.startsWith("/report/") || c.path.startsWith("/import/") || c.path.startsWith("/student/")),
          `没调教师端的接口：${JSON.stringify(calls)}`);
    }
    p.close();
    // 新开一页直接带着教师页的地址
    calls.length = 0;
    p = openPage("#" + encodeURIComponent("学生管理"));
    say(await waitFor(() => p.hash() === "#知识图谱" && p.toast().includes("「学生管理」在教师端")),
        `新开 #学生管理：退回 ${p.hash()}，提示「${p.toast()}」`);
    await sleep(150);
    say(!calls.some(c => c.path.startsWith("/student/")), "没调学生管理的接口");
    p.close();

    console.log("四、教师端");
    calls.length = 0;
    p = openPage("", "/teacher");
    say(await waitFor(() => p.active() === "学情" && p.screen().includes("还没有学生")),
        `不用登录，落在学情：${p.active()} ${p.hash()}`);
    say(p.pages().join("|") === "学情|学生管理|教材导入", `导航只有教师页：${p.pages().join("|")}`);
    say(!["知识图谱", "做题", "默写", "问老师", "教材", "学习进度"].some(t => p.nav(t)), "没有学生的学习页");
    say((p.$("nav .nav-badge") || {}).textContent === "教师端" && p.$("nav").classList.contains("nav-role-teacher"),
        "顶栏「教师端」标识，整条换色");
    const home = p.$("nav .nav-home a");
    say(home && home.textContent.trim() === "打开学生端" && home.getAttribute("href") === "/"
        && home.getAttribute("target") === "_blank", "「打开学生端」：新标签页开 /");
    say(p.w.document.title === "日语学习·教师端", `标题：${p.w.document.title}`);
    say(await waitFor(() => calls.some(c => c.path === "/report/home" && c.status === 200)),
        `学情接口 200（单人模式不要登录）：${JSON.stringify(calls)}`);
    p.nav("学生管理").click();
    say(await waitFor(() => p.hash() === "#学生管理" && calls.some(c => c.path === "/student/home" && c.status === 200)),
        "学生管理：接口 200");

    console.log("五、教师端手打学生页");
    for (const page of ["做题", "知识图谱"]) {
      calls.length = 0;
      p.w.location.hash = "#" + encodeURIComponent(page);
      say(await waitFor(() => p.hash() === "#学情" && p.toast().includes(`「${page}」在学生端（/）`)),
          `#${page}：退回 ${p.hash()}，提示「${p.toast()}」`);
      await sleep(150);
      say(!calls.some(c => c.path.startsWith("/quiz/") || c.path.startsWith("/node/")), `没调学生端的接口：${JSON.stringify(calls)}`);
    }
    p.close();

    console.log("六、服务端");
    say(!/Traceback/.test(log), "服务日志里没有 Traceback");
    say(!calls.some(c => c.status >= 500), "没有 5xx");
  } catch (e) {
    say(false, "跑挂了：" + (e && e.stack || e));
  }

  console.log(`\n${"=".repeat(50)}\n通过 ${pass}，失败 ${fail}`);
  if (fail) console.log("---- 服务日志（末尾）----\n" + log.slice(-2000));
  stop(fail ? 1 : 0);
})();
