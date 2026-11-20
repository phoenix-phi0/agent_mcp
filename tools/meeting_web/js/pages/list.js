// 会议列表页：只列会议类运行；议题要逐场读 run 取（限 4 个并发，成功才缓存）
import { h, clear, showMessage, clearMessage, statusLabel, turnLine, formatTime } from '../ui.js';
import { listRuns, getRun } from '../api.js';
import { MEETING_WORKFLOW } from '../env.js';
import { meetingTopic } from '../meeting_model.js';

const MAX_CONCURRENT = 4;
const NO_TOPIC = '（没有记录议题）';
const TOPIC_FAILED = '（读不了议题）';

function topicOf(run) {
  const ctl = run && run._control;
  const vars = ctl && ctl.vars;
  if (vars && typeof vars.topic === 'string' && vars.topic) return vars.topic;
  const inp = run && run.inputs;
  if (inp && typeof inp.topic === 'string' && inp.topic) return inp.topic;
  return NO_TOPIC;
}

// started 倒序（字符串比较，null 排最后）；相同时按记录名倒序，保证稳定
function compareRuns(a, b) {
  const sa = a.started || null;
  const sb = b.started || null;
  if (sa !== sb) {
    if (sa === null) return 1;
    if (sb === null) return -1;
    return sa < sb ? 1 : -1;
  }
  if (a.name === b.name) return 0;
  return a.name < b.name ? 1 : -1;
}

function rowKey(r) {
  return {
    name: r.name, status: r.status, started: r.started || null,
    error: r.error || null, current: r.current || null,
  };
}

export function mount(container, ctx) {
  let alive = true;
  let timer = null;
  let first = true;
  let lastKey = null;
  let errShown = null; // 自己发的刷新失败提示文字
  const topicCache = new Map(); // name → 成功取得的议题
  const topicFailed = new Set(); // 最近一次读失败的会议
  const queued = new Set();
  const queue = [];
  const inflight = new Set();
  let currentNames = new Set();

  const body = h('div', { id: 'list-body' }, h('p', { id: 'list-loading' }, '加载中…'));
  const header = h('div', { class: 'list-head' },
    h('h1', { id: 'list-title' }, '会议列表'),
    ctx.write ? h('a', { id: 'new-meeting', href: '#/new' }, '开会') : null);
  container.appendChild(header);
  container.appendChild(body);

  function rowEl(r) {
    const t = turnLine(r.status, r.current, { me: ctx.me, write: ctx.write, error: r.error });
    let turn = t;
    if (r.status === 'waiting' && !r.current) turn = { state: 'waiting-other', text: '等待中…' };
    const loading = !topicCache.has(r.name) && !topicFailed.has(r.name);
    const topicText = topicCache.has(r.name) ? topicCache.get(r.name)
      : topicFailed.has(r.name) ? TOPIC_FAILED : '…';
    return h('li', {
      class: 'meeting-row',
      'data-name': r.name,
      'data-status': r.status,
      'data-mine': turn.state === 'waiting-me' ? 'true' : null,
      'data-topic-loading': loading ? 'true' : null,
    },
    h('a', { class: 'row-link', href: '#/room/' + encodeURIComponent(r.name) }, topicText),
    ' ',
    h('span', { class: 'row-status' }, statusLabel(r.status)),
    ' ',
    h('span', { class: 'row-turn', 'data-state': turn.state }, turn.text),
    ' ',
    h('span', { class: 'row-started' }, formatTime(r.started)));
  }

  function render(rows) {
    clear(body);
    if (!rows.length) {
      const empty = h('div', { id: 'list-empty' }, h('p', null, '还没有会议'));
      if (ctx.write) empty.appendChild(h('p', null, '点上面的「开会」开一场'));
      body.appendChild(empty);
      return;
    }
    body.appendChild(h('ul', { id: 'meeting-list' }, rows.map(rowEl)));
  }

  // 只更新某一行的议题文字，不重绘整行
  function updateTopicDom(name) {
    const list = container.querySelector('#meeting-list');
    if (!list) return;
    for (const li of list.querySelectorAll('.meeting-row')) {
      if (li.getAttribute('data-name') !== name) continue;
      const a = li.querySelector('.row-link');
      if (topicCache.has(name)) {
        a.textContent = topicCache.get(name);
        li.removeAttribute('data-topic-loading');
      } else if (topicFailed.has(name)) {
        a.textContent = TOPIC_FAILED;
        li.removeAttribute('data-topic-loading');
      }
    }
  }

  function pump() {
    while (alive && inflight.size < MAX_CONCURRENT && queue.length) {
      const name = queue.shift();
      queued.delete(name);
      if (!currentNames.has(name) || topicCache.has(name) || inflight.has(name)) continue;
      inflight.add(name);
      getRun(name).then((run) => {
        if (!alive) return;
        topicCache.set(name, meetingTopic(run));
        topicFailed.delete(name);
      }, () => {
        if (!alive) return;
        topicFailed.add(name);
      }).then(() => {
        inflight.delete(name);
        if (!alive) return;
        updateTopicDom(name);
        pump();
      });
    }
  }

  function wantTopics(rows) {
    for (const r of rows) {
      if (topicCache.has(r.name) || inflight.has(r.name) || queued.has(r.name)) continue;
      queued.add(r.name);
      queue.push(r.name);
    }
    pump();
  }

  function schedule() {
    if (!alive) return;
    timer = window.setTimeout(refresh, ctx.pollMs);
  }

  async function refresh() {
    timer = null;
    let runs;
    try {
      runs = await listRuns();
    } catch (e) {
      if (!alive) return;
      const text = e && e.message ? e.message : '连不上服务…';
      errShown = text;
      showMessage('error', text);
      if (first) {
        first = false;
        const l = container.querySelector('#list-loading');
        if (l) l.remove();
      }
      schedule();
      return;
    }
    if (!alive) return;
    if (errShown !== null) {
      const m = window.document.getElementById('message');
      if (m && m.textContent === errShown) clearMessage();
      errShown = null;
    }
    const rows = runs.filter((r) => r && (r.workflow === MEETING_WORKFLOW || r.meeting === 'embedded')).sort(compareRuns);
    currentNames = new Set(rows.map((r) => r.name));
    const key = JSON.stringify(rows.map(rowKey));
    if (key !== lastKey || first) {
      lastKey = key;
      render(rows);
    }
    first = false;
    wantTopics(rows);
    schedule();
  }

  refresh();

  return {
    destroy() {
      alive = false;
      if (timer !== null) window.clearTimeout(timer);
      timer = null;
      queue.length = 0;
      queued.clear();
    },
  };
}
