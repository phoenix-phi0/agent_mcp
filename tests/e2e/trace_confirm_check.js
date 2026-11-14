// 离线 jsdom：fetch 记录请求；不启动服务、不调用模型。
// node trace_confirm_check.js tools/trace_view.html
const fs = require('fs');
const assert = require('assert');
const { JSDOM } = require('jsdom');
const html = fs.readFileSync(process.argv[2], 'utf8');
const schema = { type: 'object', required: ['summary'],
  properties: { summary: { type: 'string', minLength: 1 } } };
const base = {
  _name: 'confirm.json', workflow: 'test', status: 'waiting', updated: '1',
  script: '实现\n  角色 ENGINEER\n  任务 写代码\n  格式 implementation\n  记录 result',
  _control: { mode: 'auto', stop_roles: [], confirm_before: ['ENGINEER*'],
    confirm_after: ['实现'], max_attempts: 4, models: {}, roles: {} },
  _agents: [{ name: 'ENGINEER' }, { name: 'ENGINEER_GPT', model: 'cli:test/gpt' }],
  pending: { phase: 'after', line: 1, step: 1, name: '实现', role: 'ENGINEER',
    attempt: 2, max_attempts: 4, schema, result: { summary: '模型结果' },
    notes: [{ text: '历次意见' }], item: { index: 2, total: 3 } },
  events: [
    { type: 'task', line: 1, seq: 1, step: 1, name: '实现', task: '写代码', role: 'ENGINEER',
      status: 'rejected', attempt: 1, result: { summary: '旧结果' }, reject: { text: '缺验收' } },
    { type: 'task', line: 1, seq: 2, step: 1, name: '实现', task: '写代码', role: 'ENGINEER',
      status: 'review', attempt: 2, result: { summary: '模型结果' }, item: { index: 2, total: 3 } },
  ],
};
const wait = () => new Promise(resolve => setTimeout(resolve, 30));
async function page(readonly = false, trace = base, plan = null) {
  const posts = [], errors = [];
  let tick, rev = 0;
  const dom = new JSDOM(html.replace('<head>', '<head><meta name="trace-live" content="1">' +
    (readonly ? '' : '<meta name="trace-write" content="1">')), {
    runScripts: 'dangerously', url: 'http://127.0.0.1/',
    beforeParse(w) {
      // 手动触发真实的下一轮轮询，不等待 1.5 秒，也不改变页面代码。
      w.setTimeout = callback => { tick = callback; return 1; };
      w.alert = w.confirm = () => { errors.push('不应调用浏览器弹窗'); };
      w.addEventListener('error', event => errors.push(event.message));
      w.fetch = async (url, opts = {}) => {
        let data, status = 200;
        if (opts.method === 'POST') {
          const body = JSON.parse(opts.body);
          posts.push({ url, body });
          assert.equal(opts.headers['Content-Type'], 'application/json');
          if (body.tasks?.some(item => item.content === '预算拒绝') || body.result?.tasks?.[0]?.content === '预算拒绝') {
            status = 400; data = { ok: false, error: '改后合计 14，预算 12：服务端拒绝' };
          } else if (body.tasks?.some(item => item.content === '已跑拒绝')) {
            status = 400; data = { ok: false, error: '第 5 项已经跑过，不能改' };
          } else if (body.result?.summary === '服务端拒绝') {
            status = 400;
            data = { ok: false, error: '结果不符合格式', errors: ['summary: invalid field'] };
          } else data = { ok: true };
        } else if (url.startsWith('api/plan?')) {
          if (plan === null) { status = 400; data = { error: '没有清单' }; }
          else data = JSON.parse(JSON.stringify(plan));
        } else if (url === 'api/runs') {
          data = { runs: [{ name: trace._name, status: 'waiting', controlled: true }] };
        } else data = { ...trace, updated: String(++rev) };
        return { ok: status === 200, status, json: async () => data };
      };
    },
  });
  await wait();
  const w = dom.window, d = w.document;
  return {
    d, posts, errors,
    act: name => d.querySelector(`[data-act="${name}"]`),
    input: () => d.querySelector('#act [data-ps="summary"]'),
    click(el) { assert(el, '按钮存在'); el.click(); },
    type(el, value) {
      assert(el, '输入存在'); el.value = value;
      el.dispatchEvent(new w.Event(el.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true }));
    },
    async poll() { tick(); await wait(); },
    close() { assert.deepStrictEqual(errors, []); w.close(); },
  };
}
const cases = {
  async markers(p) {
    const node = p.d.querySelector('#flow .node.review');
    assert(node.textContent.includes('待确认'));
    assert(!node.classList.contains('waiting'));
    for (const text of ['被打回', '缺验收', '第 2 / 3 项', '历次意见', '模型结果',
      '等你确认（第 2 次尝试，最多 4 次）']) {
      assert(p.d.querySelector('#detail').textContent.includes(text), text);
    }
    assert(p.d.querySelector('#summary').textContent.includes(
      '开始前确认：ENGINEER*；结束后确认：实现；最多尝试 4 次'));
    assert.equal(p.d.querySelector('#detail').lastElementChild.id, 'act');
  },
  async approve(p) {
    p.click(p.act('approve')); await wait();
    assert.deepStrictEqual(p.posts, [{ url: 'api/approve', body: { name: 'confirm.json', attempt: 2 } }]);
  },
  async revise_client_validation(p) {
    p.click(p.act('revise')); assert.equal(p.input().value, '模型结果');
    p.type(p.input(), ''); p.click(p.act('approve-revised'));
    assert.equal(p.posts.length, 0); assert(p.input().classList.contains('bad'));
  },
  async revise_server_validation_and_submit(p) {
    p.click(p.act('revise')); p.type(p.input(), '服务端拒绝');
    p.click(p.act('approve-revised')); await wait();
    assert(p.input().classList.contains('bad'));
    assert(p.d.querySelector('#act-msg').textContent.includes('summary: invalid field'));
    p.type(p.input(), '人工修改'); p.click(p.act('approve-revised')); await wait();
    assert.deepStrictEqual(p.posts[1], { url: 'api/approve', body: {
      name: 'confirm.json', attempt: 2, result: { summary: '人工修改' } } });
  },
  async reject_empty(p) {
    p.click(p.act('reject')); p.click(p.act('reject-yes'));
    assert.equal(p.posts.length, 0);
    p.type(p.d.querySelector('#act-note'), '   '); p.click(p.act('reject-yes'));
    assert.equal(p.posts.length, 0); assert(p.d.querySelector('#act-msg').textContent.includes('打回要写意见'));
  },
  async reject_request(p) {
    p.click(p.act('reject'));
    assert.deepStrictEqual(Array.from(p.d.querySelector('#act-card').options).map(x => x.value), ['', 'ENGINEER', 'ENGINEER_GPT']);
    p.type(p.d.querySelector('#act-note'), '补验收');
    p.type(p.d.querySelector('#act-card'), 'ENGINEER_GPT');
    p.type(p.d.querySelector('#act-model'), 'cli:test/gpt');
    await p.poll(); assert.equal(p.d.querySelector('#act-note').value, '补验收');
    p.click(p.act('reject-yes')); await wait();
    assert.deepStrictEqual(p.posts[0], { url: 'api/reject', body: {
      name: 'confirm.json', attempt: 2, note: '补验收', role: 'ENGINEER_GPT', model: 'cli:test/gpt' } });
  },
  async poll_keeps_draft(p) {
    p.click(p.act('revise')); p.type(p.input(), '尚未提交');
    const input = p.input(); await p.poll();
    assert.strictEqual(p.input(), input); assert.equal(p.input().value, '尚未提交');
    assert.equal(p.posts.length, 0);
  },
  async json_validation(p) {
    p.click(p.act('revise')); p.click(p.d.querySelector('[data-mode="json"]'));
    const ta = () => p.d.querySelector('#act-json');
    assert.deepStrictEqual(JSON.parse(ta().value), { summary: '模型结果' });
    p.type(ta(), '{'); p.click(p.act('approve-revised')); assert.equal(p.posts.length, 0);
    p.type(ta(), '{"summary":"JSON 修改"}'); await p.poll();
    assert.equal(ta().value, '{"summary":"JSON 修改"}');
    p.click(p.act('approve-revised')); await wait();
    assert.deepStrictEqual(p.posts[0].body.result, { summary: 'JSON 修改' });
  },
  async abort_confirmation(p) {
    p.click(p.act('abort')); assert(p.act('abort-yes')); assert.equal(p.posts.length, 0);
    p.click(p.act('abort-no')); assert(!p.act('abort-yes'));
    p.click(p.act('abort')); p.click(p.act('abort-yes')); await wait();
    assert.deepStrictEqual(p.posts, [{ url: 'api/abort', body: { name: 'confirm.json' } }]);
  },
};
function assignment() {
  const t = JSON.parse(JSON.stringify(base));
  delete t.pending.item;
  delete t.pending.schema;
  t._agents = [{ name: 'ENGINEER', cost: 1.125 }, { name: 'ENGINEER_GPT', cost: 3 }, { name: 'OUTSIDE', cost: 9 }];
  t.pending.plan = { path: 'tasks', agent_field: 'agent', content_field: 'content',
    roster: ['ENGINEER', 'ENGINEER_GPT'], nodes: ['实现'], budget: 3 };
  t.pending.result = { summary: '保留其他字段', tasks: [
    { agent: 'ENGINEER', content: '第一项', reason: '保留' }, { agent: 'ENGINEER', content: '第二项' }] };
  return t;
}
const planCases = {
  async unchanged(p) {
    p.click(p.act('approve')); await wait();
    assert.deepStrictEqual(p.posts[0].body, { name: 'confirm.json', attempt: 2 });
  },
  async role_result(p) {
    p.type(p.d.querySelector('[data-plan-field="agent"]'), 'ENGINEER_GPT');
    p.click(p.act('approve')); await wait();
    const expected = assignment().pending.result; expected.tasks[0].agent = 'ENGINEER_GPT';
    assert.deepStrictEqual(p.posts[0].body, { name: 'confirm.json', attempt: 2, result: expected });
  },
  async controls_reset(p) {
    const after = p.d.querySelector('[data-plan-field="confirm_after"]');
    const model = p.d.querySelector('[data-plan-field="model"]');
    p.type(after, 'true'); p.type(after, ''); p.type(model, 'cli:test/gpt'); p.type(model, '');
    p.click(p.act('approve')); await wait();
    assert.deepStrictEqual(p.posts[0].body, { name: 'confirm.json', attempt: 2 });
  },
  async json_preserves_controls(p) {
    p.type(p.d.querySelector('[data-plan-field="confirm_after"]'), 'false');
    p.type(p.d.querySelector('[data-plan-field="content"]'), '表格全文');
    p.click(p.act('revise'));
    const expected = assignment().pending.result; expected.tasks[0].content = '表格全文';
    assert.deepStrictEqual(JSON.parse(p.d.querySelector('#act-json').value), expected);
    expected.summary = '整份修改'; p.type(p.d.querySelector('#act-json'), JSON.stringify(expected));
    p.click(p.act('approve-revised')); await wait();
    assert.deepStrictEqual(p.posts[0].body, { name: 'confirm.json', attempt: 2, result: expected,
      item_controls: [{ confirm_after: false }, null] });
  },
  async roster_and_cost(p) {
    const cards = p.d.querySelectorAll('[data-plan-field="agent"]');
    assert.equal(cards.length, 2);
    assert.deepStrictEqual(Array.from(cards[0].options).map(o => o.value), ['ENGINEER', 'ENGINEER_GPT']);
    const total = () => p.d.querySelector('#plan-total');
    assert(total().textContent.includes('2.25 / 3'));
    p.type(cards[0], 'ENGINEER_GPT'); assert(total().textContent.includes('4.125 / 3')); assert(total().classList.contains('bad'));
    p.type(cards[0], 'ENGINEER'); assert(!total().classList.contains('bad'));
    p.click(p.act('approve')); await wait();
    assert.deepStrictEqual(p.posts[0].body, { name: 'confirm.json', attempt: 2 });
  },
  async defaults_and_controls(p) {
    const before = p.d.querySelector('[data-plan-field="confirm_before"]');
    const after = p.d.querySelector('[data-plan-field="confirm_after"]');
    assert.deepStrictEqual(Array.from(before.options).map(o => o.textContent), ['默认（要）', '要', '不要']);
    assert.equal(after.options[0].textContent, '默认（要）');
    p.type(before, 'false');
    p.type(p.d.querySelector('[data-plan-field="model"]'), 'cli:test/gpt');
    p.click(p.act('approve')); await wait();
    assert.deepStrictEqual(p.posts[0].body, { name: 'confirm.json', attempt: 2,
      item_controls: [{ model: 'cli:test/gpt', confirm_before: false }, null] });
  },
  async content_and_poll(p) {
    const content = p.d.querySelector('[data-plan-field="content"]');
    p.type(content, '新全文\n\ud800'); await p.poll();
    assert.strictEqual(p.d.querySelector('[data-plan-field="content"]'), content);
    assert.equal(content.value, '新全文\n\ud800');
    p.click(p.act('approve')); await wait();
    const expected = assignment().pending.result; expected.tasks[0].content = '新全文\n\ud800';
    assert.deepStrictEqual(p.posts[0].body, { name: 'confirm.json', attempt: 2, result: expected });
  },
  async server_error(p) {
    p.type(p.d.querySelector('[data-plan-field="content"]'), '预算拒绝');
    p.click(p.act('approve')); await wait();
    assert.equal(p.d.querySelector('#act-msg').textContent, '改后合计 14，预算 12：服务端拒绝');
  },
};
async function revisedLengthChecks() {
  let passed = 0;
  for (const mode of ['form', 'json']) for (const change of ['add', 'delete', 'same']) {
    for (const submit of ['approve', 'approve-revised']) {
      const trace = assignment();
      trace.pending.schema = { type: 'object', required: ['tasks'], properties: {
        summary: { type: 'string' }, tasks: { type: 'array', items: {
          type: 'object', properties: { agent: { type: 'string' }, content: { type: 'string' }, reason: { type: 'string' } }
        } }
      } };
      const p = await page(false, trace);
      try {
        p.type(p.d.querySelector('[data-plan-index="1"][data-plan-field="confirm_after"]'), 'true');
        p.click(p.act('revise'));
        const expected = JSON.parse(JSON.stringify(trace.pending.result));
        if (mode === 'json') {
          p.click(p.d.querySelector('[data-mode="json"]'));
          if (change === 'delete') expected.tasks.splice(0, 1);
          if (change === 'add') expected.tasks.push({ agent: 'ENGINEER', content: '新增' });
          if (change === 'same') expected.summary = '只改摘要';
          p.type(p.d.querySelector('#act-json'), JSON.stringify(expected));
        } else {
          if (change === 'delete') {
            p.click(p.d.querySelector('[data-del=\'["tasks",0]\']'));
            expected.tasks.splice(0, 1);
          } else if (change === 'add') {
            p.click(p.d.querySelector('[data-add=\'["tasks"]\']'));
            p.type(p.d.querySelector('[data-p=\'["tasks",2,"agent"]\']'), 'ENGINEER');
            p.type(p.d.querySelector('[data-p=\'["tasks",2,"content"]\']'), '新增');
            p.type(p.d.querySelector('[data-p=\'["tasks",2,"reason"]\']'), '新增说明');
            expected.tasks.push({ agent: 'ENGINEER', content: '新增', reason: '新增说明' });
          } else {
            p.type(p.d.querySelector('#act-form [data-ps="summary"]'), '只改摘要');
            expected.summary = '只改摘要';
          }
        }
        p.click(p.act(submit)); await wait();
        assert.equal(p.posts.length, 1);
        assert.deepStrictEqual(p.posts[0].body.result, expected);
        if (change === 'same') {
          assert.deepStrictEqual(p.posts[0].body.item_controls, [null, { confirm_after: true }]);
          assert.equal(p.posts[0].body.item_controls.length, expected.tasks.length);
        } else {
          assert(!Object.hasOwn(p.posts[0].body, 'item_controls'));
          assert(p.d.querySelector('#act').textContent.includes('清单项数变了，逐项设置已清空，需要的话通过后在遍历清单里重新设置'));
        }
        passed++;
      } finally { p.close(); }
    }
  }
  return passed;
}
function traversal() {
  return { record: 'assignment', editable: true, why_not: null, budget: 12, total: 5,
    roster: [{ name: 'ENGINEER', cost: 1 }, { name: 'ENGINEER_GPT', cost: 3 }],
    rows: ['done', 'held', 'tried', 'waiting', 'todo'].map((state, i) => ({
      index: i + 1, state, item: { agent: 'ENGINEER', content: '任务' + i, reason: '保留' },
      cost: 1, control: i === 0 ? { model: 'cli:actual', confirm_after: true } : null,
      confirm_before: false, confirm_after: i === 0,
    })) };
}
async function traversalChecks() {
  let passed = 0;
  const check = async (test, options = {}) => {
    const plan = options.plan === undefined ? traversal() : options.plan;
    const p = await page(!!options.readonly, options.trace || base, plan);
    try { await test(p, plan); passed++; } finally { p.close(); }
  };
  await check(async p => {
    const rows = p.d.querySelectorAll('#run-plan tbody tr');
    assert.equal(rows.length, 5);
    ['完成', '待确认', '试过', '停着', '未跑'].forEach((label, i) => {
      assert(rows[i].textContent.includes(label));
      assert(rows[i].querySelector('.plan-state').classList.contains(traversal().rows[i].state));
    });
    for (let i = 0; i < 3; i++) assert.equal(rows[i].querySelectorAll('input, select, textarea').length, 0);
    assert.equal(rows[4].querySelectorAll('input, select, textarea').length, 5);
    assert(rows[0].textContent.includes('cli:actual'));
    assert(rows[0].textContent.includes('要'));
    assert.deepStrictEqual(Array.from(rows[4].querySelector('[data-plan-field="agent"]').options).map(o => o.value), ['ENGINEER', 'ENGINEER_GPT']);
  });
  await check(async (p, plan) => {
    const input = p.d.querySelector('#run-plan [data-plan-index="4"][data-plan-field="content"]');
    p.type(input, '编辑全文\n\ud800');
    p.type(p.d.querySelector('#run-plan [data-plan-index="4"][data-plan-field="agent"]'), 'ENGINEER_GPT');
    p.type(p.d.querySelector('#run-plan [data-plan-index="4"][data-plan-field="confirm_after"]'), 'false');
    p.type(p.d.querySelector('#run-plan [data-plan-index="4"][data-plan-field="model"]'), 'cli:edit');
    plan.rows[4].item.content = '服务器刷新';
    await p.poll(); assert.strictEqual(p.d.querySelector('#run-plan [data-plan-index="4"][data-plan-field="content"]'), input);
    assert.equal(input.value, '编辑全文\n\ud800');
    p.click(p.d.querySelector('[data-run-plan="save"]')); await wait();
    const tasks = traversal().rows.map(row => row.item);
    tasks[4] = { agent: 'ENGINEER_GPT', content: '编辑全文\n\ud800', reason: '保留' };
    assert.deepStrictEqual(p.posts[0], { url: 'api/edit_plan', body: {
      name: 'confirm.json', record: 'assignment', tasks,
      item_controls: [traversal().rows[0].control, null, null, null, { confirm_after: false, model: 'cli:edit' }],
    } });
  });
  await check(async (p, plan) => {
    plan.rows[4].item.content = '最新清单'; await p.poll();
    assert.equal(p.d.querySelector('#run-plan [data-plan-index="4"][data-plan-field="content"]').value, '最新清单');
  });
  await check(async p => {
    assert.equal(p.d.querySelectorAll('#run-plan input, #run-plan select, #run-plan textarea').length, 0);
    assert(p.d.querySelector('#run-plan').textContent.includes('后台还在跑'));
    assert(!p.d.querySelector('[data-run-plan="save"]'));
    p.click(p.d.querySelector('[data-run-plan="pause"]')); await wait();
    assert.deepStrictEqual(p.posts[0], { url: 'api/pause', body: { name: 'confirm.json' } });
  }, { plan: { ...traversal(), editable: false, why_not: '后台还在跑' } });
  await check(async p => {
    p.type(p.d.querySelector('#run-plan [data-plan-index="4"][data-plan-field="content"]'), '预算拒绝');
    p.click(p.d.querySelector('[data-run-plan="save"]')); await wait();
    assert.equal(p.d.querySelector('#run-plan-msg').textContent, '改后合计 14，预算 12：服务端拒绝');
    await p.poll(); assert.equal(p.d.querySelector('#run-plan-msg').textContent, '改后合计 14，预算 12：服务端拒绝');
  });
  await check(async p => {
    p.type(p.d.querySelector('#run-plan [data-plan-index="4"][data-plan-field="content"]'), '已跑拒绝');
    p.click(p.d.querySelector('[data-run-plan="save"]')); await wait();
    assert.equal(p.d.querySelector('#run-plan-msg').textContent, '第 5 项已经跑过，不能改');
  });
  await check(async p => {
    p.type(p.d.querySelector('#run-plan [data-plan-index="4"][data-plan-field="confirm_before"]'), 'true');
    p.click(p.d.querySelector('[data-run-plan="save"]')); await wait();
    assert.deepStrictEqual(p.posts[0].body, { name: 'confirm.json', record: 'assignment',
      item_controls: [traversal().rows[0].control, null, null, null, { confirm_before: true }] });
  });
  await check(async p => {
    p.click(p.d.querySelector('[data-run-plan="save"]')); await wait();
    assert.deepStrictEqual(p.posts[0].body, { name: 'confirm.json', record: 'assignment' });
  });
  for (const editable of [true, false]) await check(async p => {
    assert.equal(p.d.querySelectorAll('#run-plan button, #run-plan input, #run-plan select, #run-plan textarea').length, 0);
    assert.equal(p.d.querySelectorAll('#run-plan tbody tr').length, 5);
  }, { readonly: true, plan: { ...traversal(), editable } });
  for (const plan of [null, {}, { rows: [] }]) await check(async p => {
    assert(p.d.querySelector('#run-plan').hidden);
  }, { plan });
  return passed;
}
async function traversalRegressionChecks() {
  // Python 入口传入真实离线运行及 GET plan；单独运行此脚本也覆盖相同页面分支。
  const fixtures = process.argv[3] ? JSON.parse(fs.readFileSync(process.argv[3], 'utf8')) :
    [false, true].map(globalAfter => ({
      trace: { ...base, script: '遍历 x 于 assignment.tasks\n  实施\n    角色 x.who\n    任务 x.task',
        _control: { mode: 'auto', confirm_before: ['ENGINEER_GPT'],
          confirm_after: globalAfter ? ['实施'] : [], roles: { ENGINEER: 'ENGINEER_GPT' } } },
      plan: { ...traversal(), rows: [0, 1].map((i) => ({ index: i + 1, state: 'todo',
        item: { who: 'ENGINEER', task: '原文' + i, reason: '保留' }, cost: 1,
        control: i === 0 ? { confirm_after: !globalAfter, model: 'cli:keep' } : { confirm_before: false },
        confirm_before: i === 0, confirm_after: i === 0 ? !globalAfter : globalAfter })) },
      globalAfter,
    }));
  const requests = [];
  for (const fixture of fixtures) {
    const { trace, plan, globalAfter } = fixture;
    let p = await page(false, trace, plan);
    const field = (key, index = 0) => p.d.querySelector(`#run-plan [data-plan-index="${index}"][data-plan-field="${key}"]`);
    try {
      assert.equal(field('content').value, plan.rows[0].item.task);
      assert.equal(field('agent').value, plan.rows[0].item.who);
      assert.equal(field('confirm_before').options[0].textContent, '默认（要）');
      assert.equal(field('confirm_after').value, String(!globalAfter));
      assert.equal(field('confirm_after').options[0].textContent, `默认（${globalAfter ? '要' : '不要'}）`);
      assert.equal(field('confirm_after', 1).value, '');
      assert.equal(field('confirm_before', 1).value, 'false');
      p.type(field('confirm_after'), '');
      p.click(p.d.querySelector('[data-run-plan="save"]')); await wait();
      const controls = plan.rows.map(row => {
        const control = Object.fromEntries(Object.entries(row.control || {}).filter(([, value]) => value != null));
        return Object.keys(control).length ? control : null;
      });
      delete controls[0].confirm_after;
      if (!Object.keys(controls[0]).length) controls[0] = null;
      assert.deepStrictEqual(p.posts[0], { url: 'api/edit_plan', body: {
        name: trace._name, record: plan.record, item_controls: controls } });
      requests.push(p.posts[0].body);
    } finally { p.close(); }
    // 保持只读行展示的是有效覆盖，而不是“默认”值。
    const readonlyPlan = JSON.parse(JSON.stringify(plan)); readonlyPlan.rows[0].state = 'done';
    p = await page(true, trace, readonlyPlan);
    try {
      const cells = p.d.querySelector('#run-plan tbody tr').cells;
      assert.equal(cells[cells.length - 1].textContent, globalAfter ? '不要' : '要');
    } finally { p.close(); }
    p = await page(false, trace, plan);
    try {
      const nextRole = plan.roster.find(card => card.name !== plan.rows[0].item.who);
      p.type(field('agent'), nextRole.name);
      assert.equal(p.d.querySelector('#run-plan tbody tr [data-plan-cost]').textContent, String(nextRole.cost));
      const total = nextRole.cost + plan.rows.slice(1).reduce((sum, row) => sum + row.cost, 0);
      assert(p.d.querySelector('#run-plan-total').textContent.includes(`${total} / `));
      assert.equal(field('confirm_after').options[0].textContent, `默认（${globalAfter ? '要' : '不要'}）`);
      // 仅按原角色匹配时，换卡应更新默认文案；长期映射、节点规则和 step 各自继续生效。
      const originalOnly = trace._control.confirm_before?.[0] === 'ENGINEER';
      assert.equal(field('confirm_before').options[0].textContent, `默认（${originalOnly ? '不要' : '要'}）`);
      p.type(field('content'), '修改全文\n保留原文其余字段');
      p.click(p.d.querySelector('[data-run-plan="save"]')); await wait();
      const tasks = plan.rows.map(row => ({ ...row.item }));
      tasks[0].who = nextRole.name; tasks[0].task = '修改全文\n保留原文其余字段';
      assert.deepStrictEqual(p.posts[0], { url: 'api/edit_plan', body: {
        name: trace._name, record: plan.record, tasks } });
      assert(!('agent' in p.posts[0].body.tasks[0]));
      assert(!('content' in p.posts[0].body.tasks[0]));
      requests.push(p.posts[0].body);
    } finally { p.close(); }
  }
  if (process.argv[4]) fs.writeFileSync(process.argv[4], JSON.stringify(requests));
  return fixtures.length * 3;
}
async function main() {
  let passed = await revisedLengthChecks();
  if (process.argv[5]) {
    const trace = JSON.parse(fs.readFileSync(process.argv[5], 'utf8'));
    const p = await page(false, trace);
    try {
      p.type(p.d.querySelector('[data-plan-index="1"][data-plan-field="confirm_after"]'), 'true');
      p.click(p.act('revise'));
      if (!p.d.querySelector('#act-json')) p.click(p.d.querySelector('[data-mode="json"]'));
      const expected = JSON.parse(p.d.querySelector('#act-json').value);
      expected.tasks.splice(0, 1);
      p.type(p.d.querySelector('#act-json'), JSON.stringify(expected));
      p.click(p.act('approve-revised')); await wait();
      assert.equal(p.posts.length, 1);
      assert.deepStrictEqual(p.posts[0].body.result, expected);
      assert(!Object.hasOwn(p.posts[0].body, 'item_controls'));
      assert(p.d.querySelector('#act').textContent.includes('清单项数变了，逐项设置已清空，需要的话通过后在遍历清单里重新设置'));
      fs.writeFileSync(process.argv[6], JSON.stringify(p.posts[0].body));
      passed++;
    } finally { p.close(); }
  }
  passed += await traversalChecks();
  passed += await traversalRegressionChecks();
  for (const [name, test] of Object.entries(cases)) {
    const p = await page();
    try { await test(p); passed++; } catch (error) { error.message = name + ': ' + error.message; throw error; }
    finally { p.close(); }
  }
  let p = await page(true);
  assert(p.d.querySelector('#act').textContent.includes('模型结果'));
  assert.equal(p.d.querySelectorAll('#act button, #act input, #act textarea, #act select').length, 0);
  p.close(); passed++;
  const limit = JSON.parse(JSON.stringify(base)); limit.pending.max_attempts = 2;
  p = await page(false, limit); assert(p.act('reject').disabled); assert(p.act('approve')); p.close(); passed++;
  const legacy = JSON.parse(JSON.stringify(base));
  delete legacy._control.confirm_before; delete legacy._control.confirm_after; delete legacy._control.max_attempts;
  p = await page(false, legacy); assert(!p.d.querySelector('#summary').textContent.includes('最多尝试')); p.close(); passed++;
  for (const [name, test] of Object.entries(planCases)) {
    p = await page(false, assignment());
    try { await test(p); passed++; } catch (error) { error.message = name + ': ' + error.message; throw error; }
    finally { p.close(); }
  }
  p = await page(true, assignment());
  assert.equal(p.d.querySelectorAll('#act table tbody tr').length, 2);
  assert.equal(p.d.querySelectorAll('#act input, #act textarea, #act select, #act button').length, 0);
  p.close(); passed++;
  const rules = assignment(); rules._control = { mode: 'step', confirm_before: [], confirm_after: [] };
  p = await page(false, rules);
  assert.equal(p.d.querySelector('[data-plan-field="confirm_before"]').options[0].textContent, '默认（要）');
  assert.equal(p.d.querySelector('[data-plan-field="confirm_after"]').options[0].textContent, '默认（不要）');
  p.close(); passed++;
  const empty = assignment(); empty.pending.result.tasks = [];
  p = await page(false, empty); assert(p.d.querySelector('#plan-total').textContent.includes('0 / 3')); p.close(); passed++;
  const unknown = assignment(); delete unknown._agents[0].cost; unknown.pending.plan.budget = null;
  p = await page(false, unknown);
  assert(p.d.querySelector('#plan-total').textContent.includes('未知 / 未设置'));
  assert(!p.d.querySelector('#plan-total').classList.contains('bad')); p.close(); passed++;
  const nested = assignment(); nested.pending.plan.path = 'data.list';
  nested.pending.plan.agent_field = 'who'; nested.pending.plan.content_field = 'task';
  nested.pending.result = { data: { list: [{ who: 'ENGINEER', task: '原文' }] } };
  nested._control = { mode: 'auto', roles: { ENGINEER: 'ENGINEER_GPT' }, confirm_before: ['ENGINEER_GPT'], confirm_after: ['实*'] };
  p = await page(false, nested);
  assert.equal(p.d.querySelector('[data-plan-field="confirm_before"]').options[0].textContent, '默认（要）');
  assert.equal(p.d.querySelector('[data-plan-field="confirm_after"]').options[0].textContent, '默认（要）');
  p.type(p.d.querySelector('[data-plan-field="content"]'), '新文');
  p.click(p.act('approve')); await wait();
  assert.deepStrictEqual(p.posts[0].body.result, { data: { list: [{ who: 'ENGINEER', task: '新文' }] } }); p.close(); passed++;
  const item = assignment(); item.pending.item = { index: 1, total: 2 };
  p = await page(false, item); assert.equal(p.d.querySelectorAll('.plan-table').length, 0); p.close(); passed++;
  for (const [cost, expected] of [[0.0625, '0.062'], [0.1875, '0.188'], [1.2345, '1.234']]) {
    const rounding = assignment(); rounding.pending.result.tasks.length = 1; rounding._agents[0].cost = cost;
    p = await page(false, rounding);
    assert(p.d.querySelector('#plan-total').textContent.includes(expected + ' / 3'));
    p.close(); passed++;
  }
  console.log(`trace confirm jsdom: ${passed} passed`);
}
main().catch(error => { console.error(error.stack); process.exit(1); });
