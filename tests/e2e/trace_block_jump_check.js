// 块内跳转的流程图：遍历里的「如果」分支第一句就是跳转时，回环从判断框画出去，标「共 N 次 · 每项最多 M」。
// 用法：node trace_block_jump_check.js <过程记录 JSON（read_trace 的结果）>，输出一行 JSON。
"use strict";
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");
const VIEW = fs.readFileSync(path.join(__dirname, "../../tools/trace_view.html"), "utf8")
  .replace("<head>", '<head>\n<meta name="trace-live" content="1">');
const T = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const errors = [];
const dom = new JSDOM(VIEW, {
  url: "http://127.0.0.1:1/#run=" + encodeURIComponent(T._name), runScripts: "dangerously", pretendToBeVisual: true,
  beforeParse(w) {
    w.scrollTo = () => {};
    w.addEventListener("error", (e) => errors.push(String(e.message)));
    w.fetch = async (u) => ({ ok: true, status: 200, json: async () =>
      (u === "api/runs" ? { dir: "runs", runs: [{ name: T._name, status: T.status }] } : u.startsWith("api/run?") ? T : {}) });
  },
});
setTimeout(() => {
  const d = dom.window.document;
  const svg = d.querySelector("#flow svg");
  const loops = svg ? [...svg.querySelectorAll('[aria-label^="跳转"]')].map((g) => g.textContent) : [];
  const jump = svg && svg.querySelector('[aria-label^="跳转"]');
  let detail = "";
  if (jump) { jump.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true })); detail = (d.getElementById("detail") || d.body).textContent; }
  console.log(JSON.stringify({ errors, loops, perItem: /每项最多 2 次/.test(detail), order: /第 1 项第 2 次/.test(detail) }));
  dom.window.close();
}, 600);
