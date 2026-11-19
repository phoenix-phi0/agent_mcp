// 列表页「新建运行」：离线 jsdom，fetch 记下请求，不启动服务、不调模型。
// node trace_start_check.js tools/trace_view.html 入口清单.json 请求输出.json
// 入口清单由 test_trace_start.py 从真的工作目录读出来（GET /api/entries 的回复）；这里按人的操作填一遍，
// 把页面发出的启动请求写到输出文件，Python 再交给真的查看服务去启动，核对控制文件。
const fs = require('fs');
const assert = require('assert');
const { JSDOM } = require('jsdom');
const html = fs.readFileSync(process.argv[2], 'utf8');
const realEntries = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const out = process.argv[4];

const fake = {
  entries: [
    { entry: 'run_a.zs', title: '甲需求', workflow: 'flow_a', nodes: ['设计', '实现'], roles: ['ARCHITECT', 'ENGINEER'] },
    { entry: 'run_b.zs', title: '', workflow: 'flow_b', nodes: ['验收'], roles: ['QA_ENGINEER'] },
  ],
  agents: [{ name: 'ARCHITECT', model: 'cli:claude/sonnet' }, { name: 'ENGINEER', model: 'cli:claude/sonnet' },
    { name: 'ENGINEER_GPT', model: 'cli:codex/gpt' }, { name: 'QA_ENGINEER' }],
};
const wait = () => new Promise(resolve => setTimeout(resolve, 30));

async function page(entries = fake, { readonly = false, reject = null } = {}) {
  const posts = [], errors = [], gets = [];
  const dom = new JSDOM(html.replace('<head>', '<head><meta name="trace-live" content="1">' +
    (readonly ? '' : '<meta name="trace-write" content="1">')), {
    runScripts: 'dangerously', url: 'http://127.0.0.1/',
    beforeParse(w) {
      w.setTimeout = () => 1;
      w.alert = w.confirm = () => { errors.push('不应调用浏览器弹窗'); };
      w.addEventListener('error', event => errors.push(event.message));
      w.fetch = async (url, opts = {}) => {
        let data, status = 200;
        if (opts.method === 'POST') {
          const body = JSON.parse(opts.body);
          posts.push({ url, body });
          assert.equal(opts.headers['Content-Type'], 'application/json');
          if (reject) { status = 400; data = { ok: false, error: reject }; }
          else data = { ok: true, name: '20261119-000000-flow_a.json', status: {} };
        } else {
          gets.push(url);
          if (url === 'api/entries') data = JSON.parse(JSON.stringify(entries));
          else if (url === 'api/runs') data = { runs: [] };
          else { status = 404; data = { error: '没有' }; }
        }
        return { ok: status === 200, status, json: async () => data };
      };
    },
  });
  await wait();
  const w = dom.window, d = w.document;
  const q = sel => d.querySelector('#start-panel ' + sel);
  return {
    w, d, posts, gets, q,
    panel: () => d.querySelector('#start-panel'),
    msg: () => q('#start-msg').textContent,
    async open() { d.querySelector('#new-run').click(); await wait(); },
    click(sel) { const el = q(sel); assert(el, '找不到 ' + sel); el.click(); },
    set(sel, value) {
      const el = q(sel); assert(el, '找不到 ' + sel);
      if (el.type === 'checkbox') el.checked = value; else el.value = value;
      el.dispatchEvent(new w.Event(el.tagName === 'SELECT' || el.type === 'checkbox' ? 'change' : 'input', { bubbles: true }));
    },
    close() { assert.deepStrictEqual(errors, []); w.close(); },
  };
}

const cases = {
  async readonly_no_button() {
    const p = await page(fake, { readonly: true });
    assert(p.d.querySelector('#new-run').hidden, '只读页面没有「新建运行」');
    assert(!p.gets.includes('api/entries'), '只读页面不去拉入口'); p.close();
  },
  async form_and_candidates() {
    const p = await page();
    assert(!p.d.querySelector('#new-run').hidden);
    assert(p.panel().hidden, '没点之前不展开');
    await p.open();
    assert(p.gets.includes('api/entries'));
    assert.deepStrictEqual(Array.from(p.q('[data-start-field="entry"]').options).map(x => x.value), ['run_a.zs', 'run_b.zs']);
    assert(p.panel().textContent.includes('甲需求'));
    assert.deepStrictEqual(Array.from(p.d.querySelectorAll('#start-panel [data-start-rule="confirm_after"]')).map(x => x.value),
      ['设计', '实现', 'ARCHITECT', 'ENGINEER']);
    assert.deepStrictEqual(Array.from(p.d.querySelectorAll('#start-panel [data-start-role][data-start-kind="card"]')).map(x => x.getAttribute('data-start-role')),
      ['ARCHITECT', 'ENGINEER']);
    assert.equal(p.q('[data-start-field="mode"]').value, 'auto');
    assert.equal(p.q('[data-start-field="max_attempts"]').value, '4');
    p.close();
  },
  async start_two_step() {
    const p = await page();
    await p.open();
    p.set('[data-start-rule="confirm_after"][value="设计"]', true);
    p.set('[data-start-extra="confirm_before"]', 'ENGINEER*');
    p.set('[data-start-field="max_attempts"]', '6');
    p.set('[data-start-role="ENGINEER"][data-start-kind="card"]', 'ENGINEER_GPT');
    p.set('[data-start-role="ARCHITECT"][data-start-kind="model"]', 'platform:claude-sonnet-5-5');
    p.click('[data-start="go"]'); await wait();
    assert.equal(p.posts.length, 0, '第一下只是确认');
    assert(p.q('[data-start="go-yes"]').textContent.includes('会真的调模型'));
    p.click('[data-start="go-yes"]'); await wait();
    assert.deepStrictEqual(p.posts, [{ url: 'api/start', body: { entry: 'run_a.zs', mode: 'auto', max_attempts: 6,
      confirm_before: ['ENGINEER*'], confirm_after: ['设计'],
      models: { ARCHITECT: 'platform:claude-sonnet-5-5' }, roles: { ENGINEER: 'ENGINEER_GPT' } } }]);
    assert.equal(p.w.location.hash, '#run=' + encodeURIComponent('20261119-000000-flow_a.json'), '启动后跳到这次运行');
    assert(p.panel().hidden);
    p.close();
  },
  async minimal_body() {
    const p = await page();
    await p.open();
    p.click('[data-start="go"]'); p.click('[data-start="go-yes"]'); await wait();
    assert.deepStrictEqual(p.posts[0].body, { entry: 'run_a.zs', mode: 'auto', max_attempts: 4 }, '没填的不发');
    p.close();
  },
  async change_entry_keeps_mode() {
    const p = await page();
    await p.open();
    p.set('[data-start-field="mode"]', 'step');
    p.set('[data-start-field="max_attempts"]', '7');
    p.set('[data-start-field="entry"]', 'run_b.zs');
    assert.deepStrictEqual(Array.from(p.d.querySelectorAll('#start-panel [data-start-role][data-start-kind="card"]')).map(x => x.getAttribute('data-start-role')),
      ['QA_ENGINEER'], '换入口后角色跟着换');
    assert.equal(p.q('[data-start-field="mode"]').value, 'step');
    assert.equal(p.q('[data-start-field="max_attempts"]').value, '7');
    p.click('[data-start="go"]'); p.click('[data-start="go-yes"]'); await wait();
    assert.deepStrictEqual(p.posts[0].body, { entry: 'run_b.zs', mode: 'step', max_attempts: 7 });
    p.close();
  },
  async edit_after_confirm_resets() {
    const p = await page();
    await p.open();
    p.click('[data-start="go"]');
    p.set('[data-start-field="max_attempts"]', '5');
    assert(!p.q('[data-start="go-yes"]'), '确认之后又改了内容，要重新点启动');
    p.close();
  },
  async bad_inputs() {
    const p = await page();
    await p.open();
    p.set('[data-start-role="ENGINEER"][data-start-kind="model"]', 'haiku');
    p.click('[data-start="go"]'); await wait();
    assert.equal(p.posts.length, 0); assert(p.msg().includes('要写全')); assert(!p.q('[data-start="go-yes"]'));
    p.set('[data-start-role="ENGINEER"][data-start-kind="model"]', '');
    p.set('[data-start-field="max_attempts"]', '0');
    p.click('[data-start="go"]');
    assert(p.msg().includes('1–50'));
    p.close();
  },
  async server_rejects() {
    const p = await page(fake, { reject: '入口脚本跑完了，没有执行编排' });
    await p.open();
    p.set('[data-start-field="max_attempts"]', '3');
    p.click('[data-start="go"]'); p.click('[data-start="go-yes"]'); await wait();
    assert(p.msg().includes('没有执行编排'));
    assert(!p.q('[data-start="go"]').disabled, '失败后能再点');
    assert.equal(p.q('[data-start-field="max_attempts"]').value, '3', '失败不丢已填内容');
    assert.equal(p.w.location.hash, '', '失败不跳走');
    p.close();
  },
  async empty_and_close() {
    const p = await page({ entries: [], agents: [] });
    await p.open();
    assert(p.panel().textContent.includes('没有能启动的入口脚本'));
    assert(!p.q('[data-start="go"]'));
    p.click('[data-start="close"]'); assert(p.panel().hidden);
    p.close();
  },
  async real_entries() {
    // 真的入口清单：选 run_project.zs，逐步模式，按人的操作填，请求交给 Python 去真启动
    const p = await page(realEntries);
    await p.open();
    p.set('[data-start-field="entry"]', 'run_project.zs');
    p.set('[data-start-field="mode"]', 'step');
    p.set('[data-start-rule="confirm_after"][value="架构设计"]', true);
    p.set('[data-start-field="max_attempts"]', '3');
    p.set('[data-start-role="ENGINEER"][data-start-kind="card"]', 'ENGINEER_GPT');
    p.set('[data-start-role="QA_ENGINEER"][data-start-kind="model"]', 'cli:claude/haiku');
    p.click('[data-start="go"]'); p.click('[data-start="go-yes"]'); await wait();
    assert.equal(p.posts.length, 1);
    fs.writeFileSync(out, JSON.stringify(p.posts[0].body));
    p.close();
  },
};

async function main() {
  let passed = 0;
  for (const [name, fn] of Object.entries(cases)) {
    try { await fn(); } catch (e) { console.error('✗', name); throw e; }
    passed++;
  }
  console.log(`trace start jsdom: ${passed} passed`);
}
main().catch(error => { console.error(error.stack); process.exit(1); });
