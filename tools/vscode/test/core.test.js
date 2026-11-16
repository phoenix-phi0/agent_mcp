// lib/core.js 的单元测试：node --test test/*.test.js
"use strict";
const test = require("node:test");
const assert = require("node:assert");
const core = require("../lib/core");

const TOKEN = "pPIAHbZeIaLzKRUHw5ZMbKmWvjgMhd45";

test("查看器链接：拆出地址和口令", () => {
  assert.deepStrictEqual(core.parseViewerLink(`https://ali-demo.yscinternet.top/trace/${TOKEN}/`),
    { base: "https://ali-demo.yscinternet.top/trace", token: TOKEN });
  // 运行页的地址（带 #run=）、不带最后的 /、带查询串都认
  assert.deepStrictEqual(core.parseViewerLink(`https://ali-demo.yscinternet.top/trace/${TOKEN}#run=a.json`),
    { base: "https://ali-demo.yscinternet.top/trace", token: TOKEN });
  assert.deepStrictEqual(core.parseViewerLink(`  https://h.example/${TOKEN}/?x=1  `), { base: "https://h.example", token: TOKEN });
  // 本机服务不带口令
  assert.deepStrictEqual(core.parseViewerLink("http://127.0.0.1:8765/"), { base: "http://127.0.0.1:8765", token: "" });
  // 短的那段不当口令
  assert.deepStrictEqual(core.parseViewerLink("https://h.example/trace"), { base: "https://h.example/trace", token: "" });
});

test("查看器链接：不合法的报错", () => {
  assert.throws(() => core.parseViewerLink("ali-demo.yscinternet.top/trace"), /不是有效的地址/);
  assert.throws(() => core.parseViewerLink("ftp://h.example/"), /http/);
  assert.throws(() => core.parseViewerLink(""), /不是有效的地址/);
});

test("根地址：带不带口令都以 / 结尾", () => {
  assert.strictEqual(core.rootUrl("https://h.example/trace", TOKEN), `https://h.example/trace/${TOKEN}/`);
  assert.strictEqual(core.rootUrl("https://h.example/trace/", ""), "https://h.example/trace/");
  assert.strictEqual(core.rootUrl("http://127.0.0.1:8765", ""), "http://127.0.0.1:8765/");
});

test("页面请求：只放行查看器用到的读写接口", () => {
  for (const ok of [["api/runs", "GET"], ["api/run?name=a.json", "GET"], ["api/plan?name=x%20y.json", "GET"],
    ["api/approve", "POST"], ["api/reject", "POST"], ["api/edit_plan", "POST"], ["api/pause", "POST"], ["api/submit", "post"]]) {
    assert.strictEqual(core.checkPageRequest(ok[0], ok[1]), null, ok.join(" "));
  }
  for (const bad of [["https://evil.example/api/runs", "GET"], ["/api/runs", "GET"], ["api/../../etc/passwd", "GET"],
    ["api/runs", "POST"], ["api/approve", "GET"], ["api/approve?x=1", "POST"], ["api/delete", "POST"],
    ["api/runs", "DELETE"], ["", "GET"], ["api/run#x", "GET"]]) {
    assert.notStrictEqual(core.checkPageRequest(bad[0], bad[1]), null, bad.join(" "));
  }
});

const RUNS = [
  { name: "a.json", status: "running", alive: true, current: { step: 3, name: "任务实现", role: "ENGINEER_GO" } },
  { name: "b.json", status: "waiting", waiting_step: 4, current: { step: 4, name: "任务研讨", role: "ARCHITECT_GLM" } },
  { name: "c.json", status: "done" },
  { name: "d.json", status: "error" },
  { name: "e.json", status: "running", alive: false },
  { name: "f.json", status: "aborted" },
];

test("分组：等确认、运行中、出错中止中断、完成，顺序固定", () => {
  const g = core.groupRuns(RUNS);
  assert.deepStrictEqual(g.map((x) => [x.key, x.runs.map((r) => r.name)]),
    [["waiting", ["b.json"]], ["running", ["a.json"]], ["bad", ["d.json", "e.json", "f.json"]], ["done", ["c.json"]]]);
  assert.deepStrictEqual(core.groupRuns([]).map((x) => x.runs.length), [0, 0, 0, 0]);
});

test("状态文字和图标", () => {
  assert.deepStrictEqual(RUNS.map((r) => core.runState(r)[1]), ["运行中", "暂停在第 4 步", "完成", "出错", "已中断", "已中止"]);
  assert.strictEqual(core.runState(RUNS[0])[2], "sync~spin");
  assert.strictEqual(core.runState(RUNS[1])[2], "debug-pause");
  assert.strictEqual(core.describe(RUNS[1]), "暂停在第 4 步　任务研讨 · ARCHITECT_GLM");
  assert.strictEqual(core.describe(RUNS[2]), "完成");
});

test("新停下来等确认的：第一轮不算，之后只报新出现的", () => {
  let st = core.newlyWaiting(null, RUNS);
  assert.deepStrictEqual(st.fresh, []);
  // 同一次运行还停在第 4 步：不再报
  st = core.newlyWaiting(st.keys, RUNS);
  assert.deepStrictEqual(st.fresh, []);
  // a 停在第 5 步、b 往下走到第 6 步又停：两个都报
  const next = [Object.assign({}, RUNS[0], { status: "waiting", waiting_step: 5 }), Object.assign({}, RUNS[1], { waiting_step: 6 })];
  st = core.newlyWaiting(st.keys, next);
  assert.deepStrictEqual(st.fresh.map((r) => r.name + "#" + r.waiting_step), ["a.json#5", "b.json#6"]);
  // 都不停了：没有新的，记下的清空
  st = core.newlyWaiting(st.keys, [RUNS[2]]);
  assert.deepStrictEqual([st.fresh.length, st.keys.size], [0, 0]);
});
