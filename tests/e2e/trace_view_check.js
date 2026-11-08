// 用 jsdom 打开 tools/trace_view.html（离线模式），把一份过程记录当示例载入，
// 输出渲染结果给 tests/tools/test_trace_view.py 断言。
//   node trace_view_check.js <trace_view.html> <trace.json> [选中的行号]
// 输出一行 JSON：summary、note、flow（SVG 文本）、classes（各节点 class）、detail、bars（耗时条段数）
const fs = require("fs");
const { JSDOM } = require("jsdom");

const [html, tracePath, line] = process.argv.slice(2);
const trace = fs.readFileSync(tracePath, "utf-8");
const page = fs.readFileSync(html, "utf-8").replace(
  '<script type="application/json" id="sample-real">null</script>',
  () => '<script type="application/json" id="sample-real">' + trace.replace(/<\//g, "<\\/") + "</script>");
const errors = [];
const dom = new JSDOM(page, {
  runScripts: "dangerously", url: "file:///trace_view.html", pretendToBeVisual: true,
  beforeParse(w) { w.addEventListener("error", (e) => errors.push(String(e.message || e.error))); },
});
const doc = dom.window.document;
setTimeout(() => {
  if (line) {
    const g = doc.querySelector('#flow .node[data-line="' + line + '"]');
    if (g) g.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
  }
  const out = {
    errors,
    summary: doc.getElementById("summary").textContent,
    note: doc.getElementById("note").hidden ? "" : doc.getElementById("note").textContent,
    flow: doc.getElementById("flow").textContent,
    classes: Array.from(doc.querySelectorAll("#flow .node")).map((g) => [g.getAttribute("data-line"), g.getAttribute("class")]),
    head: doc.getElementById("d-head").textContent,
    detail: doc.getElementById("detail").textContent,
    bars: doc.querySelectorAll("#bars button").length,
  };
  process.stdout.write(JSON.stringify(out));
  dom.window.close();
}, 300);
