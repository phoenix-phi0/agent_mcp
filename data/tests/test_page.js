/**
 * 页面测试：把生成的 app.js 在 jsdom 里真挂起来，检查渲染出的 DOM 和
 * 交互是否符合 .ui 里写的意图。
 *
 * 为什么不读文本就算了：v-if / v-model / v-for 只有真挂载才生效。
 * 「勾上推荐后短链字段会不会出现」「点编辑跳不跳回表单」这类事，
 * 静态看生成的字符串永远看不出来。
 *
 * 用法
 * ----
 *   cd data/tests
 *   npm install vue@3 jsdom          # 只需一次
 *   py ../../fs_gen.py               # 或用 tool_call 生成，把三个文件放这个目录
 *   node test_page.js
 *
 * 期望：通过 32，失败 0。
 *
 * 断言基于 fixture.ui + 下面这套字段表和选项，改了任何一个都要同步改断言。
 *
 * 两个踩过的坑（都在测试脚本这边，不是应用的问题）
 * ----------------------------------------------
 * 1. tick() 等太短会误判。hash 路由要多一轮，20ms 不够，60ms 稳。
 *    第一次撞上时我先单独写 probe 确认应用切界面本来是好的，
 *    才回头改测试——不然容易误判成生成器有 bug。
 * 2. 点击事件必须带 cancelable: true。@click.prevent 对不可取消的
 *    事件行为不同，少了这个 handler 不执行，界面切不过去。
 */
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const DIR = __dirname;
const dom = new JSDOM(`<!doctype html><html><body><div id="app"></div></body></html>`, {
  url: "http://localhost/",
  pretendToBeVisual: true,
});

// Vue 运行时会摸 window 上的一堆全局，逐个转到 node 的 global。
// 少一个就报 "XXX is not defined"，SVGElement 是最容易漏的那个。
for (const k of ["window","document","location","navigator","SVGElement","HTMLElement",
                 "Element","Node","Event","MouseEvent","CustomEvent","getComputedStyle",
                 "requestAnimationFrame","cancelAnimationFrame"]) {
  global[k] = dom.window[k];
}

const Vue = require("vue/dist/vue.cjs.js");
dom.window.Vue = Vue;
global.Vue = Vue;

// 收集 console.log，用来验证 onSubmit / onAction / onRow 有没有被调到
const logs = [];
const realLog = console.log;
dom.window.console = {
  log: (...a) => logs.push(a),
  warn: () => {},
  error: (...a) => realLog("ERR", ...a),
};

let pass = 0, fail = 0;
function check(name, actual, expected) {
  const good = JSON.stringify(actual) === JSON.stringify(expected);
  good ? pass++ : fail++;
  realLog(`  ${good ? "OK  " : "FAIL"} ${name}` +
    (good ? "" : `\n         期望 ${JSON.stringify(expected)}\n         实际 ${JSON.stringify(actual)}`));
}
function ok(name, cond, extra = "") {
  cond ? pass++ : fail++;
  realLog(`  ${cond ? "OK  " : "FAIL"} ${name}${cond ? "" : "  " + extra}`);
}

const appPath = path.join(DIR, "app.js");
if (!fs.existsSync(appPath)) {
  realLog(`找不到 ${appPath}\n先生成三个文件放到这个目录，再跑本测试。`);
  process.exit(1);
}
const code = fs.readFileSync(appPath, "utf-8");
try {
  new Function("Vue", "window", "document", "location", "console", code)(
    Vue, dom.window, dom.window.document, dom.window.location, dom.window.console);
} catch (e) {
  realLog("挂载失败:", e.message);
  process.exit(1);
}

const $ = (sel) => dom.window.document.querySelector(sel);
const $$ = (sel) => [...dom.window.document.querySelectorAll(sel)];
const tick = () => new Promise((r) => setTimeout(r, 60));
const click = (el) => el.dispatchEvent(
  new dom.window.MouseEvent("click", { bubbles: true, cancelable: true }));

(async () => {
  await tick();

  realLog("\n【1. 初始渲染 — 应停在第一个界面「文章编辑」】");
  ok("应用挂载了", $("#app").children.length > 0);
  check("导航两项", $$("nav a").map(a => a.textContent), ["文章编辑", "文章列表"]);
  check("当前高亮", $$("nav a.active").map(a => a.textContent), ["文章编辑"]);

  realLog("\n【2. 布局 — 对照 布局横排 / 区域竖排 / 区域占满 / 分组网格】");
  ok("布局是 row", !!$(".layout.row"));
  check("两个区域的 class", $$(".region").map(r => r.className),
        ["region col", "region col grow"]);
  check("区域标题", $$(".region-h").map(r => r.textContent), ["侧栏", "主区"]);
  check("分组标题和 class",
        $$(".group").map(g => [g.className, g.querySelector("h3").textContent]),
        [["group col", "发布设置"], ["group grid", "基本信息"]]);

  realLog("\n【3. 控件 — 对照类型契约表】");
  check("枚举 status → 三个 radio",
        $$('input[type=radio]').map(i => i.value),
        ["draft", "published", "archived"]);
  ok("日期 published_at → input[type=date]", !!$('input[type=date]'));
  ok("布尔 featured → checkbox", !!$('input[type=checkbox]'));
  ok("长文本 body → textarea", !!$('textarea'));
  ok("文本 title → input[type=text]", $$('input[type=text]').length >= 1);

  realLog("\n【4. 必填 — status 和 title 标了必填】");
  const starred = $$(".field").filter(f => f.querySelector(".req"))
                              .map(f => f.querySelector(".lbl").textContent.replace("*",""));
  check("带红星的字段", starred, ["发布状态", "标题"]);
  ok("title 输入框有 required", $('input[type=text]').hasAttribute("required"));

  realLog("\n【5. 条件显示 — 「字段 slug 当 form.featured 短链」】");
  const slugVisible = () => $$(".lbl").some(l => l.textContent === "短链");
  ok("初始不显示短链（featured=false）", !slugVisible());

  const cb = $('input[type=checkbox]');
  cb.checked = true;
  cb.dispatchEvent(new dom.window.Event("change"));
  await tick();
  ok("勾上推荐后短链出现", slugVisible(), "→ v-if 没生效");

  cb.checked = false;
  cb.dispatchEvent(new dom.window.Event("change"));
  await tick();
  ok("取消后短链消失", !slugVisible());

  realLog("\n【6. 动作 — save 提交 / delete 危险】");
  check("按钮文字", $$("button").map(b => b.textContent), ["保存", "删除"]);
  check("按钮样式", $$("button").map(b => b.className),
        ["btn btn-primary", "btn btn-danger"]);
  check("保存是 submit 型", $$("button").map(b => b.getAttribute("type")),
        ["submit", "button"]);

  realLog("\n【7. 双向绑定 — 填表单，值要进 form】");
  const titleInput = $('input[type=text]');
  titleInput.value = "测试标题";
  titleInput.dispatchEvent(new dom.window.Event("input"));
  await tick();
  logs.length = 0;
  $("form").dispatchEvent(new dom.window.Event("submit"));
  await tick();
  const submitted = logs.find(l => l[0] === "submit");
  ok("提交拿到 form", !!submitted, "→ onSubmit 没触发");
  if (submitted) {
    check("form.title 收到输入", submitted[2].title, "测试标题");
    check("提交时带上界面名", submitted[1], "文章编辑");
  }

  realLog("\n【8. 切到列表界面】");
  click($$("nav a")[1]);
  await tick();
  check("表头", $$("th").map(t => t.textContent), ["标题", "状态", "发布时间", ""]);
  check("两行数据", $$("tbody tr").length, 2);
  check("第一行四个单元格", $$("tbody tr")[0].querySelectorAll("td").length, 4);
  check("行数据", [...$$("tbody tr")[0].querySelectorAll("td")].slice(0,3).map(t => t.textContent),
        ["第一篇", "published", "2026-01-15"]);
  check("文案", $(".copy") && $(".copy").textContent, "点编辑跳回表单");

  realLog("\n【9. 交互 — 点编辑应跳回表单并带上那行数据】");
  // 这条依赖界面角色识别。角色解析错位那个 bug 就卡在这里：
  // screens.find(s => s.role === "表单") 返回 undefined，跳转静默失败。
  click($$("tbody tr")[0].querySelector("button"));
  await tick();
  check("跳回了表单界面", $$("nav a.active").map(a => a.textContent), ["文章编辑"]);
  const titleNow = $('input[type=text]');
  check("标题被填成那行的值", titleNow && titleNow.value, "第一篇");
  check("状态 radio 选中 published",
        $$('input[type=radio]').filter(r => r.checked).map(r => r.value), ["published"]);

  realLog("\n【10. 界面状态隔离】");
  ok("回填覆盖了之前手输的值", titleNow.value === "第一篇");

  realLog(`\n${"=".repeat(50)}\n通过 ${pass}，失败 ${fail}\n${"=".repeat(50)}`);
  process.exit(fail ? 1 : 0);
})();
