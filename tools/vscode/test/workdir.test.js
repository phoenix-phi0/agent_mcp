// lib/workdir.js 的测试：用真 git 在临时目录里跑。
// 拉到空文件夹记基线 → 改、加、删 → 找出改动 → 交了以后基线前移；拉过的文件夹再拉（同步、删服务器上没了的）；
// 不空的文件夹、别的运行、有没交改动的都不拉；服务器给的路径越界不写。
"use strict";
const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const os = require("os");
const path = require("path");
const W = require("../lib/workdir");

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "amwd-"));
test.after(() => fs.rmSync(tmp, { recursive: true, force: true }));
const wf = (files, extra) => Object.assign({ step: 6, attempt: 1, phase: "before", cwd: "work/demo", files, skipped: [] }, extra || {});
const read = (d, rel) => fs.readFileSync(path.join(d, rel), "utf8");

test("拉到空文件夹：写文件和标记，git 记成基线，标记不进 git", async () => {
  const d = path.join(tmp, "a");
  const r = await W.pullInto(d, wf([{ path: "user.py", content: "x = 1\n" }, { path: "pkg/m.py", content: "y\n" }]),
    { run: "r1.json", server: "https://h/trace" });
  assert.strictEqual(r.written, 2);
  assert.strictEqual(read(d, "pkg/m.py"), "y\n");
  const m = W.readMarker(d);
  assert.deepStrictEqual([m.run, m.cwd, m.step, m.server], ["r1.json", "work/demo", 6, "https://h/trace"]);
  assert.deepStrictEqual(await W.collectChanges(d), [], "刚拉下来没有改动");
  const tracked = (await W.git(d, ["ls-files"])).trim().split("\n");
  assert.deepStrictEqual(tracked.sort(), ["pkg/m.py", "user.py"], "标记文件不进 git");
});

test("找改动：修改、新增（含子目录）、删除；内容是全文，删除的是 null", async () => {
  const d = path.join(tmp, "a");
  fs.writeFileSync(path.join(d, "user.py"), "x = 2\n");
  fs.mkdirSync(path.join(d, "tests"));
  fs.writeFileSync(path.join(d, "tests/test_u.py"), "def test(): pass\n");
  fs.unlinkSync(path.join(d, "pkg/m.py"));
  const ch = await W.collectChanges(d);
  assert.deepStrictEqual(ch, [
    { path: "pkg/m.py", content: null, action: "删除" },
    { path: "tests/test_u.py", content: "def test(): pass\n", action: "新增" },
    { path: "user.py", content: "x = 2\n", action: "修改" },
  ]);
  assert.deepStrictEqual(await W.collectChanges(d), ch, "再看一次结果一样（不会因为暂存变掉）");
});

test("交了以后：基线前移，没有改动了；标记里记下交的哪一步", async () => {
  const d = path.join(tmp, "a");
  await W.markSubmitted(d, "已交 第 6 步", { submitted_step: 6 });
  assert.deepStrictEqual(await W.collectChanges(d), []);
  assert.strictEqual(W.readMarker(d).submitted_step, 6);
  assert.match(await W.git(d, ["log", "-1", "--format=%s"]), /已交 第 6 步/);
});

test("二进制文件交不了", async () => {
  const d = path.join(tmp, "a");
  fs.writeFileSync(path.join(d, "b.bin"), Buffer.from([0, 1, 2]));
  await assert.rejects(W.collectChanges(d), /二进制文件交不了：b\.bin/);
  fs.unlinkSync(path.join(d, "b.bin"));
});

test("拉过的文件夹再拉：同步成服务器的样子（服务器上没了的删掉，跳过的不动）", async () => {
  const d = path.join(tmp, "a");
  fs.writeFileSync(path.join(d, "big.dat"), "local");
  await W.markSubmitted(d, "加个大文件");
  const r = await W.pullInto(d, wf([{ path: "user.py", content: "x = 3\n" }], { step: 8, skipped: [{ path: "big.dat", reason: "超过 1024 KB" }] }),
    { run: "r1.json" });
  assert.deepStrictEqual([r.written, r.removed], [1, 1], "改了 user.py，删掉服务器上没了的 tests/test_u.py");
  assert.ok(!fs.existsSync(path.join(d, "tests/test_u.py")));
  assert.strictEqual(read(d, "big.dat"), "local", "服务器跳过的文件不动");
  assert.strictEqual(W.readMarker(d).step, 8);
  assert.deepStrictEqual(await W.collectChanges(d), []);
});

test("不拉：有没交的改动、别的运行、不空的文件夹", async () => {
  const d = path.join(tmp, "a");
  fs.writeFileSync(path.join(d, "user.py"), "dirty\n");
  await assert.rejects(W.pullInto(d, wf([]), { run: "r1.json" }), /还有没交的改动/);
  await assert.rejects(W.pullInto(d, wf([]), { run: "r2.json" }), /另一次运行/);
  const e = path.join(tmp, "notempty");
  fs.mkdirSync(e);
  fs.writeFileSync(path.join(e, "x"), "1");
  await assert.rejects(W.pullInto(e, wf([]), { run: "r1.json" }), /空文件夹/);
});

test("服务器给的路径越界、写进 .git、写标记文件：都不写", async () => {
  for (const bad of ["../x", "/etc/x", "a\\b", ".git/config", "a//b", W.MARKER]) {
    const d = path.join(tmp, "bad" + Math.random().toString(36).slice(2));
    await assert.rejects(W.pullInto(d, wf([{ path: bad, content: "x" }]), { run: "r1.json" }), /路径/, bad);
  }
  assert.ok(!fs.existsSync(path.join(tmp, "x")));
});
