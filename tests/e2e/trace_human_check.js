// 会议里轮到人（卡 model=human，pending.reason = human）时的运行页：离线 jsdom，fetch 记下请求。
// node trace_human_check.js tools/trace_view.html 真实记录.json 请求输出.json
// 真实记录由 test_wf_meeting.py 用 workflow_ctl 跑到「轮到 HUMAN 发言」停下；这里按人的操作填表交上去，
// 把请求写到输出文件，Python 再交给 workflow_ctl，核对会议接着往下走。
const fs = require('fs');
const assert = require('assert');
const { JSDOM } = require('jsdom');
const html = fs.readFileSync(process.argv[2], 'utf8');
const trace = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const out = process.argv[4];
const wait = () => new Promise(resolve => setTimeout(resolve, 30));

async function main() {
  const posts = [], errors = [];
  let rev = 0;
  const dom = new JSDOM(html.replace('<head>', '<head><meta name="trace-live" content="1"><meta name="trace-write" content="1">'), {
    runScripts: 'dangerously', url: 'http://127.0.0.1/#run=' + encodeURIComponent(trace._name),
    beforeParse(w) {
      w.setTimeout = () => 1;
      w.alert = w.confirm = () => { errors.push('不应调用浏览器弹窗'); };
      w.addEventListener('error', event => errors.push(event.message));
      w.fetch = async (url, opts = {}) => {
        let data, status = 200;
        if (opts.method === 'POST') { posts.push({ url, body: JSON.parse(opts.body) }); data = { ok: true }; }
        else if (url.startsWith('api/plan?')) { status = 400; data = { error: '没有清单' }; }
        else if (url === 'api/runs') data = { runs: [{ name: trace._name, status: 'waiting', controlled: true }] };
        else data = { ...trace, updated: String(++rev) };
        return { ok: status === 200, status, json: async () => data };
      };
    },
  });
  await wait();
  const w = dom.window, d = w.document;
  const act = d.querySelector('#act');
  assert(act, '停在人的那一步：有操作区');
  assert(act.textContent.includes('轮到你（'), '标题是「轮到你」，不是「扮演」');
  assert(!d.querySelector('[data-act="exec"]'), '人的那一步没有「按默认执行」');
  assert(!d.querySelector('[data-act="resume"]'), '人的那一步没有「继续自动跑」');
  assert(d.querySelector('#act-human').textContent.includes('不调模型'), '说清这一步是人、不调模型');
  assert(d.querySelector('[data-act="exec-as"]'), '还能换卡或换模型让 AI 代答');
  const field = ps => d.querySelector(`#act [data-ps="${ps}"]`);
  for (const ps of ['speech', 'agree', 'ask', 'question']) assert(field(ps), '按发言格式出表单：' + ps);
  const set = (el, value) => {
    if (el.type === 'checkbox') el.checked = value; else el.value = value;
    el.dispatchEvent(new w.Event(el.tagName === 'SELECT' || el.type === 'checkbox' ? 'change' : 'input', { bubbles: true }));
  };
  set(field('speech'), '要不要兼容旧浏览器？');
  set(field('ask'), 'ARCHITECT');
  set(field('question'), '兼容 IE 吗？');
  d.querySelector('[data-act="submit"]').click(); await wait();
  assert.equal(posts.length, 1, '交了一次');
  assert.equal(posts[0].url, 'api/submit');
  assert.equal(posts[0].body.result.speech, '要不要兼容旧浏览器？');
  assert.equal(posts[0].body.result.ask, 'ARCHITECT');
  fs.writeFileSync(out, JSON.stringify(posts[0].body));
  assert.deepStrictEqual(errors, []);
  w.close();
  console.log('trace human jsdom: passed');
}
main().catch(error => { console.error(error.stack); process.exit(1); });
