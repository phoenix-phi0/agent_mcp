// 把查看服务给的页面（tools/trace_view.html，服务端已经加了 trace-live / trace-write 标记）改成能放进
// VS Code Webview 的样子：
// - 加内容安全策略：只允许页面自带的内联脚本和样式，不许连任何外部地址（字体链接去掉）；
// - 在页面脚本之前放一段桥接脚本：换掉 fetch，请求交给插件去发（Webview 里不能直接请求查看服务），
//   装好 window.TRACE_HOST（页面靠它进实时模式、显示「在编辑器里打开」），按 VS Code 的深浅色设 data-theme，
//   地址设成 #run=名字 直接进那次运行的页面。
"use strict";

function bridgeScript(initialRun, theme) {
  // JSON.stringify 之后再把 < 换掉，名字里就算有 </script> 也关不掉这段脚本
  const run = JSON.stringify(initialRun || "").replace(/</g, "\\u003c");
  const th = JSON.stringify(theme === "light" ? "light" : "dark");
  return `<script>
(function () {
  var vscode = acquireVsCodeApi();
  var seq = 0, pending = {};
  window.addEventListener("message", function (e) {
    var m = e.data || {};
    if (m.type === "fetch-result" && pending[m.id]) {
      var p = pending[m.id]; delete pending[m.id];
      if (m.error) { p.reject(new TypeError(m.error)); return; }
      p.resolve({ ok: m.status >= 200 && m.status < 300, status: m.status,
                  json: function () { return Promise.resolve().then(function () { return JSON.parse(m.body); }); },
                  text: function () { return Promise.resolve(m.body); } });
    } else if (m.type === "theme") {
      document.documentElement.setAttribute("data-theme", m.kind === "light" ? "light" : "dark");
    } else if (m.type === "open-run" && m.name) {
      location.hash = "#run=" + encodeURIComponent(m.name);
    }
  });
  window.fetch = function (url, opts) {
    opts = opts || {};
    var id = ++seq;
    return new Promise(function (resolve, reject) {
      pending[id] = { resolve: resolve, reject: reject };
      var headers = {};
      var h = opts.headers || {};
      Object.keys(h).forEach(function (k) { headers[k] = String(h[k]); });
      vscode.postMessage({ type: "fetch", id: id, url: String(url), method: opts.method || "GET", headers: headers,
                           body: opts.body == null ? null : String(opts.body) });
    });
  };
  window.TRACE_HOST = {
    openScript: function (line, workflow, script, run) {
      vscode.postMessage({ type: "open-script", line: line, workflow: workflow, script: script, run: run });
    },
    pullWorkdir: function (run) { vscode.postMessage({ type: "pull-workdir", run: String(run || "") }); },
    submitChanges: function (run) { vscode.postMessage({ type: "submit-changes", run: String(run || "") }); }
  };
  // 页面里换了运行（下拉框改 hash；「← 运行列表」用 pushState，不触发 hashchange）：告诉插件，好改标签页标题
  function tellView() {
    var m = location.hash.match(/^#run=(.+)$/);
    vscode.postMessage({ type: "view", run: m ? decodeURIComponent(m[1]) : null });
  }
  window.addEventListener("hashchange", tellView);
  var push = history.pushState;
  history.pushState = function () { var r = push.apply(history, arguments); tellView(); return r; };
  document.documentElement.setAttribute("data-theme", ${th});
  var run = ${run};
  if (run) history.replaceState(null, "", "#run=" + encodeURIComponent(run));
})();
</script>`;
}

function buildWebviewHtml(page, opts) {
  opts = opts || {};
  let html = String(page);
  if (!/<head>/.test(html)) throw new Error("查看服务返回的不像查看器页面（没有 <head>）");
  // 外部字体：Webview 里不连外网，去掉，用系统字体
  html = html.replace(/<link[^>]+fonts\.(googleapis|gstatic)\.com[^>]*>\s*/g, "");
  const csp = `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; ` +
    `style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:; font-src data:;">`;
  // 页面自己的标记（trace-live 等）由服务端加在 <head> 后面，这里插在最前：策略和桥接都在页面脚本之前
  return html.replace("<head>", () => "<head>\n" + csp + "\n" + bridgeScript(opts.run, opts.theme));
}

module.exports = { buildWebviewHtml, bridgeScript };
