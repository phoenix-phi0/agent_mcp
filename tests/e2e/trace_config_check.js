// 运行配置面板（#run-config）：离线 jsdom，fetch 记下请求，不启动服务、不调模型。
// node trace_config_check.js tools/trace_view.html 真实记录.json 请求输出.json
// 真实记录由 test_trace_config.py 用 workflow_ctl 真跑出来；这里按人的操作改配置，把发出的请求写到输出文件，
// Python 那边再把请求交给真的查看服务，核对控制文件。
const fs = require('fs');
const assert = require('assert');
const { JSDOM } = require('jsdom');
const html = fs.readFileSync(process.argv[2], 'utf8');
const real = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const out = process.argv[4];

const base = {
  _name: 'cfg.json', workflow: 'test', status: 'waiting', updated: '1',
  script: '实现\n  角色 ENGINEER\n  任务 写代码\n  格式 implementation\n  记录 result\n验收\n  角色 QA_ENGINEER\n  任务 看看\n  记录 check',
  _control: { mode: 'auto', stop_roles: ['ENGINEER*'], confirm_before: ['ENGINEER*'],
    confirm_after: ['实现'], max_attempts: 4, models: {}, roles: {} },
  _agents: [{ name: 'ENGINEER', model: 'cli:claude/sonnet' }, { name: 'ENGINEER_GPT', model: 'cli:codex/gpt' },
    { name: 'QA_ENGINEER', model: 'cli:claude/sonnet' }],
  events: [{ type: 'task', line: 1, seq: 1, step: 1, name: '实现', task: '写代码', role: 'ENGINEER', status: 'ok', result: {} }],
};
const wait = () => new Promise(resolve => setTimeout(resolve, 30));
const clone = x => JSON.parse(JSON.stringify(x));

async function page(trace = base, { readonly = false, reject = null } = {}) {
  const posts = [], errors = [];
  let tick, rev = 0;
  const dom = new JSDOM(html.replace('<head>', '<head><meta name="trace-live" content="1">' +
    (readonly ? '' : '<meta name="trace-write" content="1">')), {
    runScripts: 'dangerously', url: 'http://127.0.0.1/#run=' + encodeURIComponent(trace._name),
    beforeParse(w) {
      w.setTimeout = callback => { tick = callback; return 1; };
      w.alert = w.confirm = () => { errors.push('不应调用浏览器弹窗'); };
      w.addEventListener('error', event => errors.push(event.message));
      w.fetch = async (url, opts = {}) => {
        let data, status = 200;
        if (opts.method === 'POST') {
          const body = JSON.parse(opts.body);
          posts.push({ url, body });
          assert.equal(opts.headers['Content-Type'], 'application/json');
          if (reject) { status = 400; data = { ok: false, error: reject }; } else data = { ok: true };
        } else if (url.startsWith('api/plan?')) { status = 400; data = { error: '没有清单' }; }
        else if (url === 'api/runs') data = { runs: [{ name: trace._name, status: trace.status, controlled: true }] };
        else data = { ...trace, updated: String(++rev) };
        return { ok: status === 200, status, json: async () => data };
      };
    },
  });
  await wait();
  const w = dom.window, d = w.document;
  const q = sel => d.querySelector('#run-config ' + sel);
  return {
    d, posts, q,
    panel: () => d.querySelector('#run-config'),
    msg: () => q('#run-config-msg').textContent,
    click(sel) { const el = q(sel); assert(el, '找不到 ' + sel); el.click(); },
    set(sel, value) {
      const el = q(sel); assert(el, '找不到 ' + sel);
      if (el.type === 'checkbox') el.checked = value; else el.value = value;
      el.dispatchEvent(new w.Event(el.tagName === 'SELECT' || el.type === 'checkbox' ? 'change' : 'input', { bubbles: true }));
    },
    async poll() { tick(); await wait(); },
    close() { assert.deepStrictEqual(errors, []); w.close(); },
  };
}

const cases = {
  async readonly_hidden() {
    const p = await page(base, { readonly: true });
    assert(p.panel().hidden, '只读页面不出配置编辑'); p.close();
  },
  async done_hidden() {
    const t = clone(base); t.status = 'done';
    const p = await page(t); assert(p.panel().hidden, '跑完的运行不出配置编辑'); p.close();
  },
  async no_control_hidden() {
    const t = clone(base); delete t._control;
    const p = await page(t); assert(p.panel().hidden, '不受控的运行不出配置编辑'); p.close();
  },
  async summary_and_candidates() {
    const p = await page();
    const text = p.panel().textContent;
    for (const s of ['开始前确认：ENGINEER*', '结束后确认：实现', '最多尝试：4 次', '按角色覆盖：无']) assert(text.includes(s), s);
    p.click('[data-cfg="open"]');
    const names = Array.from(p.d.querySelectorAll('#run-config [data-cfg-rule="confirm_before"]')).map(x => x.value);
    assert.deepStrictEqual(names, ['实现', '验收', 'ENGINEER', 'QA_ENGINEER'], '候选是流程里的节点名和角色');
    assert.equal(p.q('[data-cfg-extra="confirm_before"]').value, 'ENGINEER*', '不在候选里的规则放进「其他」');
    assert(p.q('[data-cfg-rule="confirm_after"][value="实现"]').checked);
    const cards = Array.from(p.q('[data-cfg-role="ENGINEER"][data-cfg-kind="card"]').options).map(x => x.value);
    assert.deepStrictEqual(cards, ['', 'ENGINEER', 'ENGINEER_GPT', 'QA_ENGINEER']);
    p.close();
  },
  async edit_and_save() {
    const p = await page();
    p.click('[data-cfg="open"]');
    p.set('[data-cfg-rule="confirm_after"][value="实现"]', false);
    p.set('[data-cfg-rule="confirm_after"][value="QA_ENGINEER"]', true);
    p.set('[data-cfg-extra="confirm_before"]', 'ENGINEER*, 验*');
    p.set('[data-cfg-field="max_attempts"]', '6');
    p.set('[data-cfg-role="ENGINEER"][data-cfg-kind="card"]', 'ENGINEER_GPT');
    p.set('[data-cfg-role="QA_ENGINEER"][data-cfg-kind="model"]', 'platform:claude-sonnet-5-5');
    await p.poll();     // 轮询不冲掉正在改的内容
    assert.equal(p.q('[data-cfg-field="max_attempts"]').value, '6');
    assert.equal(p.q('[data-cfg-role="ENGINEER"][data-cfg-kind="card"]').value, 'ENGINEER_GPT');
    p.click('[data-cfg="save"]'); await wait();
    assert.deepStrictEqual(p.posts, [{ url: 'api/configure', body: { name: 'cfg.json',
      confirm_before: ['ENGINEER*', '验*'], confirm_after: ['QA_ENGINEER'], max_attempts: 6,
      models: { QA_ENGINEER: 'platform:claude-sonnet-5-5' }, roles: { ENGINEER: 'ENGINEER_GPT' } } }]);
    assert(p.msg().includes('配置已保存'));
    assert(!p.q('[data-cfg="save"]'), '保存后收起');
    p.close();
  },
  async only_changed_keys() {
    const p = await page();
    p.click('[data-cfg="open"]');
    p.set('[data-cfg-field="max_attempts"]', '2');
    p.click('[data-cfg="save"]'); await wait();
    assert.deepStrictEqual(p.posts[0].body, { name: 'cfg.json', max_attempts: 2 }, '没动的键不发');
    p.close();
  },
  async no_change() {
    const p = await page();
    p.click('[data-cfg="open"]'); p.click('[data-cfg="save"]'); await wait();
    assert.equal(p.posts.length, 0); assert(p.msg().includes('没有改动')); p.close();
  },
  async bad_inputs() {
    const p = await page();
    p.click('[data-cfg="open"]');
    p.set('[data-cfg-role="ENGINEER"][data-cfg-kind="model"]', 'haiku');
    p.click('[data-cfg="save"]'); await wait();
    assert.equal(p.posts.length, 0); assert(p.msg().includes('要写全'));
    p.set('[data-cfg-role="ENGINEER"][data-cfg-kind="model"]', '');
    p.set('[data-cfg-field="max_attempts"]', '');
    p.click('[data-cfg="save"]'); await wait();
    assert.equal(p.posts.length, 0); assert(p.msg().includes('不能清空'));
    p.set('[data-cfg-field="max_attempts"]', '80');
    p.click('[data-cfg="save"]'); await wait();
    assert.equal(p.posts.length, 0); assert(p.msg().includes('1–50'));
    p.close();
  },
  async server_rejects() {
    const p = await page(base, { reject: '没有这张角色卡：NOPE' });
    p.click('[data-cfg="open"]');
    p.set('[data-cfg-field="max_attempts"]', '3');
    p.click('[data-cfg="save"]'); await wait();
    assert(p.msg().includes('没有这张角色卡'));
    assert(!p.q('[data-cfg="save"]').disabled, '失败后能再改');
    assert.equal(p.q('[data-cfg-field="max_attempts"]').value, '3', '失败不丢已填内容');
    p.close();
  },
  async clear_override() {
    const t = clone(base); t._control.roles = { ENGINEER: 'ENGINEER_GPT' }; t._control.models = { QA_ENGINEER: 'cli:x/y' };
    const p = await page(t);
    assert(p.panel().textContent.includes('ENGINEER 换卡 ENGINEER_GPT'));
    p.click('[data-cfg="open"]');
    p.set('[data-cfg-role="ENGINEER"][data-cfg-kind="card"]', '');
    p.set('[data-cfg-role="QA_ENGINEER"][data-cfg-kind="model"]', '');
    p.click('[data-cfg="save"]'); await wait();
    assert.deepStrictEqual(p.posts[0].body, { name: 'cfg.json', models: {}, roles: {} }, '清掉覆盖发空对象');
    p.close();
  },
  async cancel_restores() {
    const p = await page();
    p.click('[data-cfg="open"]'); p.set('[data-cfg-field="max_attempts"]', '9');
    p.click('[data-cfg="cancel"]'); await wait();
    assert.equal(p.posts.length, 0); assert(p.q('[data-cfg="open"]'));
    p.click('[data-cfg="open"]'); assert.equal(p.q('[data-cfg-field="max_attempts"]').value, '4');
    p.close();
  },
  async real_trace() {
    // 真跑出来的记录：按人的操作改一遍，请求交给 Python 去打真的服务
    const p = await page(real);
    assert(!p.panel().hidden);
    p.click('[data-cfg="open"]');
    const roles = Array.from(p.d.querySelectorAll('#run-config [data-cfg-role][data-cfg-kind="card"]')).map(x => x.getAttribute('data-cfg-role'));
    assert(roles.length >= 2, '真记录里有角色');
    const node = p.q('[data-cfg-rule="confirm_before"]').value;
    p.set(`[data-cfg-rule="confirm_before"][value="${node}"]`, true);
    p.set('[data-cfg-field="max_attempts"]', '5');
    p.set(`[data-cfg-role="${roles[1]}"][data-cfg-kind="model"]`, 'cli:claude/haiku');
    p.set(`[data-cfg-role="${roles[0]}"][data-cfg-kind="card"]`, 'ENGINEER_GPT');
    p.click('[data-cfg="save"]'); await wait();
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
  console.log(`trace config jsdom: ${passed} passed`);
}
main().catch(error => { console.error(error.stack); process.exit(1); });
