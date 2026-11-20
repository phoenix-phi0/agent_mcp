// 在生成的教师端页面里走选文件、点击和 Enter，拦截请求核对动作及表单。
// node tests/e2e/teacher_assist_upload_run.js [已生成的 web 目录]
const assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { JSDOM } = require("jsdom");

const root = path.resolve(__dirname, "../..");
const python = process.env.PY || path.join(root, ".venv/bin/python");
const read = (web, name) => fs.readFileSync(path.join(web, name), "utf8");

async function main() {
  let project;
  let dom;
  try {
    let web = process.argv[2];
    if (!web) {
      project = fs.mkdtempSync(path.join(os.tmpdir(), "kg-v4-assist-upload-"));
      for (const dir of ["entities", "i18n", "routes", "ui"]) {
        fs.cpSync(path.join(root, "kg_v4", dir), path.join(project, dir), { recursive: true });
      }
      execFileSync(python, ["-m", "gen", "build", project], { cwd: root });
      web = path.join(project, "web");
    }
    const html = read(web, "teacher.html").replace(/<script src="[^"]*"><\/script>/g, "");
    dom = new JSDOM(html, {
      url: "http://localhost/teacher#" + encodeURIComponent("教师助手"),
      runScripts: "outside-only",
    });
    const w = dom.window;
    const requests = [];
    w.fetch = async (url, options = {}) => {
      if (["/teacher_assist/ask", "/teacher_assist/attach"].includes(url)) {
        assert.ok(options.body instanceof w.FormData, "教师助手提交使用 multipart");
        requests.push({ url, body: options.body });
      }
      return { status: 200, json: async () => ({ state: { talk: [] } }) };
    };
    w.eval(read(web, "vue.global.prod.js"));
    w.eval(read(web, "teacher.js"));

    const settle = () => new Promise(resolve => setImmediate(resolve));
    const buttons = () => Array.from(w.document.querySelectorAll(".screen .bar-bottom button"));
    const textarea = () => w.document.querySelector(".screen textarea");
    const enter = () => textarea().dispatchEvent(new w.KeyboardEvent("keydown", {
      key: "Enter", bubbles: true, cancelable: true,
    }));
    function type(text) {
      const input = textarea();
      input.value = text;
      input.dispatchEvent(new w.Event("input", { bubbles: true }));
    }
    async function pick(name) {
      const input = w.document.querySelector(".screen input[type=file]");
      const file = new w.File(["课堂资料"], name, { type: "text/plain" });
      Object.defineProperty(input, "files", { configurable: true, value: [file] });
      input.dispatchEvent(new w.Event("change", { bubbles: true }));
      await settle();
      return file;
    }
    async function checkSubmit(send, action, content, file = null) {
      const count = requests.length;
      send();
      await settle();
      assert.equal(requests.length, count + 1, "每次操作只提交一次");
      const req = requests.at(-1);
      assert.equal(req.url, action === "assist_send" ? "/teacher_assist/ask" : "/teacher_assist/attach");
      const payload = JSON.parse(req.body.get("payload"));
      assert.equal(payload.action, action);
      assert.equal(payload.form.content, content);
      assert.equal(req.body.get("assist_file"), file);
    }

    await settle();
    assert.deepEqual(buttons().map(b => b.textContent.trim()), ["发送"]);
    type("普通问题");
    await checkSubmit(() => buttons()[0].click(), "assist_send", "普通问题");
    const first = await pick("first.txt");
    assert.deepEqual(buttons().map(b => b.textContent.trim()), ["传附件"]);
    type("总结一下");
    await checkSubmit(() => buttons()[0].click(), "assist_attach", "总结一下", first);
    const second = await pick("second.md");
    await checkSubmit(enter, "assist_attach", "", second);
    assert.deepEqual(buttons().map(b => b.textContent.trim()), ["发送"]);
    type("附件第二段讲了什么");
    await checkSubmit(enter, "assist_send", "附件第二段讲了什么");
    console.log("教师助手附件回归通过（点击、Enter、带问题上传、只上传、后续文字）");
  } finally {
    if (dom) dom.window.close();
    if (project) fs.rmSync(project, { recursive: true, force: true });
  }
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
