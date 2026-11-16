// 实现步骤的工作目录拉到本地、改完交回去：本地文件夹用 git 记一个基线，交的时候只交和基线比改了的文件。
// - pullInto：把查看服务给的文件（GET api/workfiles）写进本地文件夹，写标记文件，git 提交成基线
// - collectChanges：git status 找出新增、修改、删除的文件，读出内容，组成 submit_files 要的 files
// - markSubmitted：交成功后把当前状态提交成新的基线
// 只依赖 Node 和本机的 git，不碰 vscode 模块，测试里直接用真 git 跑。
"use strict";

const fs = require("fs");
const path = require("path");
const { execFile } = require("child_process");

const MARKER = ".agent-mcp-run.json";
const IDENT = ["-c", "user.name=agent-mcp", "-c", "user.email=agent-mcp@localhost", "-c", "commit.gpgsign=false",
               "-c", "core.autocrlf=false", "-c", "core.quotepath=false"];

function git(cwd, args, opts) {
  return new Promise((resolve, reject) => {
    execFile("git", [...IDENT, ...args], { cwd, maxBuffer: 64 * 1024 * 1024, encoding: "buffer", ...(opts || {}) },
      (err, stdout, stderr) => {
        if (err) {
          const msg = (stderr && stderr.toString("utf8").trim()) || err.message;
          return reject(new Error(err.code === "ENOENT" ? "找不到 git，请先安装 git" : "git " + args[0] + "：" + msg));
        }
        resolve(stdout.toString("utf8"));
      });
  });
}

function readMarker(folder) {
  try {
    const m = JSON.parse(fs.readFileSync(path.join(folder, MARKER), "utf8"));
    return m && typeof m.run === "string" ? m : null;
  } catch (e) {
    return null;
  }
}

// 服务器给的相对路径再核一遍：不能越出本地文件夹，不能写进 .git
function safeTarget(folder, rel) {
  if (typeof rel !== "string" || !rel || rel.includes("\\") || rel.startsWith("/") || rel.includes("\0"))
    throw new Error("服务器给的文件路径不对：" + rel);
  const parts = rel.split("/");
  if (parts.some((p) => p === "" || p === "." || p === "..") || parts[0] === ".git" || rel === MARKER)
    throw new Error("服务器给的文件路径不对：" + rel);
  const target = path.resolve(folder, ...parts);
  if (!target.startsWith(path.resolve(folder) + path.sep)) throw new Error("服务器给的文件路径越界：" + rel);
  return target;
}

async function isDirty(folder) {
  const out = await git(folder, ["status", "--porcelain", "-z", "--untracked-files=all"]);
  return out.split("\0").filter(Boolean).some((e) => e.slice(3) !== MARKER);
}

// 把 workfiles 的结果写进 folder。folder 要么是空的，要么是以前拉过同一次运行、没有没交的改动。
// 返回 { written, removed, base }。
async function pullInto(folder, wf, meta) {
  fs.mkdirSync(folder, { recursive: true });
  const marker = readMarker(folder);
  const entries = fs.readdirSync(folder).filter((n) => n !== ".git" && n !== MARKER);
  if (marker) {
    if (marker.run !== meta.run) throw new Error(`这个文件夹拉的是另一次运行（${marker.run}），换个空文件夹`);
    if (fs.existsSync(path.join(folder, ".git")) && await isDirty(folder))
      throw new Error("这个文件夹里还有没交的改动：先交掉，或者自己处理掉（git stash / 丢弃）再重新拉");
  } else if (entries.length) {
    throw new Error("请选一个空文件夹（或者以前拉过这次运行的文件夹）");
  }
  if (!fs.existsSync(path.join(folder, ".git"))) await git(folder, ["init", "-q"]);
  // 标记文件不进 git：它记的是这个文件夹对应哪次运行，不是代码
  const exclude = path.join(folder, ".git", "info", "exclude");
  fs.mkdirSync(path.dirname(exclude), { recursive: true });
  const ex = fs.existsSync(exclude) ? fs.readFileSync(exclude, "utf8") : "";
  if (!ex.split(/\r?\n/).includes(MARKER)) fs.appendFileSync(exclude, (ex && !ex.endsWith("\n") ? "\n" : "") + MARKER + "\n");

  const want = new Map();
  for (const f of wf.files || []) want.set(f.path, f.content);
  const skipped = new Set((wf.skipped || []).map((s) => s.path));
  // 服务器上已经没有的文件（本地以前拉过、git 跟踪着的）删掉；服务器跳过的（二进制、太大）不动
  let removed = 0;
  if (marker) {
    const tracked = (await git(folder, ["ls-files", "-z"])).split("\0").filter(Boolean);
    for (const rel of tracked) {
      if (!want.has(rel) && !skipped.has(rel)) {
        try { fs.unlinkSync(safeTarget(folder, rel)); removed++; } catch (e) { /* 已经没了 */ }
      }
    }
  }
  let written = 0;
  for (const [rel, content] of want) {
    const target = safeTarget(folder, rel);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    const now = fs.existsSync(target) ? fs.readFileSync(target, "utf8") : null;
    if (now !== content) { fs.writeFileSync(target, content, "utf8"); written++; }
  }
  const info = { run: meta.run, cwd: wf.cwd, step: wf.step, attempt: wf.attempt, phase: wf.phase,
                 server: meta.server || "", pulled_at: new Date().toISOString() };
  fs.writeFileSync(path.join(folder, MARKER), JSON.stringify(info, null, 2) + "\n", "utf8");
  await git(folder, ["add", "-A"]);
  await git(folder, ["commit", "-q", "--allow-empty", "-m", `拉取 ${meta.run.replace(/\.json$/, "")} 第 ${wf.step} 步的工作目录（${wf.cwd}）`]);
  const base = (await git(folder, ["rev-parse", "HEAD"])).trim();
  return { written, removed, base, skipped: wf.skipped || [] };
}

// 和基线（HEAD）比：新增、修改的读出全文，删除的 content 为 null。返回 [{path, content, action}]。
async function collectChanges(folder) {
  if (!fs.existsSync(path.join(folder, ".git"))) throw new Error("这个文件夹不是拉下来的工作目录（没有 .git）");
  await git(folder, ["add", "-A", "--intent-to-add"]).catch(() => {});
  const out = await git(folder, ["status", "--porcelain", "-z", "--untracked-files=all", "--no-renames"]);
  const files = [];
  for (const e of out.split("\0").filter(Boolean)) {
    const code = e.slice(0, 2), rel = e.slice(3);
    if (rel === MARKER) continue;
    const full = path.join(folder, ...rel.split("/"));
    if (code.includes("D") || !fs.existsSync(full)) {
      files.push({ path: rel, content: null, action: "删除" });
      continue;
    }
    if (fs.statSync(full).isDirectory()) continue;
    const buf = fs.readFileSync(full);
    if (buf.includes(0)) throw new Error("二进制文件交不了：" + rel);
    const added = code.includes("A") || code === "??";
    files.push({ path: rel, content: buf.toString("utf8"), action: added ? "新增" : "修改" });
  }
  files.sort((a, b) => (a.path < b.path ? -1 : a.path > b.path ? 1 : 0));
  return files;
}

async function markSubmitted(folder, message, info) {
  const m = readMarker(folder) || {};
  fs.writeFileSync(path.join(folder, MARKER), JSON.stringify(Object.assign(m, info || {}), null, 2) + "\n", "utf8");
  await git(folder, ["add", "-A"]);
  await git(folder, ["commit", "-q", "--allow-empty", "-m", message]);
}

module.exports = { MARKER, readMarker, pullInto, collectChanges, markSubmitted, safeTarget, git };
