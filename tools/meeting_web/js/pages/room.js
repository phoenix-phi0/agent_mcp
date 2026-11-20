// 会议室：聊天框的样子。顶部是议题栏，中间按时间排的发言气泡（别人在左、我在右），底部是输入区。
// 轮到我时的表单由 forms.js 的 createFormArea 管，本页只提供 #form-area 并在每次内容变化后调用 sync。
import { h, clear, showMessage, clearMessage, statusLabel, turnLine } from '../ui.js';
import { getRun } from '../api.js';
import { meetingCapable, buildMeeting } from '../meeting_model.js';
import { createFormArea } from '../forms.js';
import { createHandoff } from '../handoff.js';

const PENDING_TEXT = {
  speech: { running: '正在发言…', waiting: '等待发言…' },
  reply: { running: '正在回答追问…', waiting: '等待回答…' },
  check: { running: '正在判断…', waiting: '等待判断…' },
  decision: { running: '正在写结论…', waiting: '等待写结论…' },
};
const NEAR_BOTTOM = 80; // 离底部这么近就算「在看最新的」，新消息来了自动滚下去
const AVATAR_TONES = 6;

function pendingText(kind, state) {
  if (state === 'error') return '这一步出错了';
  const t = PENDING_TEXT[kind];
  return state === 'running' ? t.running : t.waiting;
}

function pendingEl(kind, state) {
  return h('p', { class: 'turn-pending', 'data-state': state }, pendingText(kind, state));
}

function replyToText(t) {
  if (!t.askedBy) return '回答追问';
  if (t.question) return `回答 ${t.askedBy} 的追问：${t.question}`;
  return `回答 ${t.askedBy} 的追问`;
}

// 头像上的缩写：REVIEWER_GPT → RG，ARCHITECT → AR，中文名取第一个字
export function initials(role) {
  const s = String(role || '?');
  const parts = s.split(/[_\-\s]+/).filter(Boolean);
  if (!/^[\x00-\x7f]+$/.test(s)) return Array.from(s)[0];
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return s.slice(0, 2).toUpperCase();
}

function toneOf(role) {
  let n = 0;
  for (const ch of String(role || '')) n = (n * 31 + ch.codePointAt(0)) >>> 0;
  return String(n % AVATAR_TONES);
}

function avatarEl(role, me) {
  return h('div', {
    class: 'turn-avatar', 'aria-hidden': 'true', 'data-tone': role === me ? 'me' : toneOf(role),
  }, initials(role));
}

function turnEl(t, me) {
  const mine = !!me && t.role === me;
  const meta = [h('span', { class: 'turn-who' }, t.role)];
  if (mine) meta.push(h('span', { class: 'turn-you' }, '（你）'));
  const bodyKids = [];
  if (t.kind === 'reply') bodyKids.push(h('div', { class: 'turn-reply-to' }, replyToText(t)));
  if (t.state === 'ok' && t.result) {
    const r = t.result;
    meta.push(h('span', { class: 'turn-agree', 'data-agree': r.agree ? 'true' : 'false' }, r.agree ? '认可' : '不认可'));
    bodyKids.push(h('div', { class: 'turn-text' }, r.speech === undefined || r.speech === null ? '' : String(r.speech)));
    if (r.ask) bodyKids.push(h('div', { class: 'turn-ask', 'data-ask': r.ask }, `点名 ${r.ask}：${r.question || ''}`));
  } else {
    bodyKids.push(pendingEl(t.kind === 'reply' ? 'reply' : 'speech', t.state));
  }
  return h('div', {
    class: 'turn',
    'data-kind': t.kind,
    'data-step': t.step,
    'data-role': t.role,
    'data-state': t.state,
    'data-me': mine ? 'true' : null,
  },
  avatarEl(t.role, me),
  h('div', { class: 'turn-body' }, h('div', { class: 'turn-meta' }, meta), bodyKids));
}

function listOf(v) {
  return Array.isArray(v) ? v : [];
}

function checkEl(c, roundIndex) {
  const kids = [h('div', { class: 'check-head' },
    h('span', { class: 'check-label' }, '主持判断'),
    h('span', { class: 'check-who' }, c.role))];
  if (c.state === 'ok' && c.result) {
    const r = c.result;
    const yes = r.done === '是';
    kids[0].appendChild(h('span', { class: 'check-done', 'data-done': yes ? '是' : '否' }, yes ? '可以出结论' : '还要再议'));
    kids.push(h('div', { class: 'check-summary' }, r.summary === undefined || r.summary === null ? '' : String(r.summary)));
    const ds = listOf(r.disagreements);
    if (ds.length) kids.push(h('ul', { class: 'check-disagreements' }, ds.map((d) => h('li', null, String(d)))));
    else kids.push(h('p', { class: 'check-none' }, '没有分歧了'));
  } else {
    kids.push(pendingEl('check', c.state));
  }
  return h('div', { class: 'check', 'data-round': roundIndex, 'data-state': c.state }, kids);
}

function decisionEl(d) {
  const kids = [h('h2', { class: 'decision-title' }, '结论')];
  if (d.state === 'ok' && d.result) {
    const r = d.result;
    const reasons = listOf(r.reasons);
    const dissent = listOf(r.dissent);
    const todo = listOf(r.todo);
    kids.push(h('p', { class: 'decision-text' }, r.decision === undefined || r.decision === null ? '' : String(r.decision)));
    kids.push(h('h3', null, '理由'));
    kids.push(h('ul', { class: 'decision-reasons' }, reasons.map((x) => h('li', null, String(x)))));
    kids.push(h('h3', null, '保留意见'));
    if (dissent.length) kids.push(h('ul', { class: 'decision-dissent' }, dissent.map((x) => h('li', null, String(x)))));
    else kids.push(h('p', { class: 'decision-dissent decision-none' }, '没有保留意见'));
    kids.push(h('h3', null, '待办'));
    if (todo.length) {
      kids.push(h('ul', { class: 'decision-todo' }, todo.map((x) => h('li', null,
        h('span', { class: 'todo-who' }, x && x.who !== undefined && x.who !== null ? String(x.who) : ''),
        '：',
        h('span', { class: 'todo-what' }, x && x.what !== undefined && x.what !== null ? String(x.what) : '')))));
    } else {
      kids.push(h('p', { class: 'todo-none' }, '没有待办'));
    }
    kids.push(h('p', { class: 'decision-summary' }, r.summary === undefined || r.summary === null ? '' : String(r.summary)));
  } else {
    kids.push(pendingEl('decision', d.state));
  }
  return h('section', { id: 'decision', 'data-state': d.state }, kids);
}

// 已经出结果的条目数：用来判断「来了新消息」
function doneCount(m) {
  let n = 0;
  for (const r of m.rounds) {
    for (const t of r.turns) if (t.state === 'ok') n++;
    if (r.check && r.check.state === 'ok') n++;
  }
  if (m.decision && m.decision.state === 'ok') n++;
  return n;
}

export function mount(container, ctx) {
  const name = ctx.params.name;
  let alive = true;
  let timer = null;
  let current = null; // 在途请求 {valid, promise}
  let queued = null; // refresh 合并出来的下一次请求的 Promise
  let stopped = false; // 首次失败 / 非会议 / 已结束：不再排下一次轮询
  let lastKey = null;
  let errShown = null; // 自己发的「刷新失败」提示文字
  let view = null; // 首次成功后才有的整页内容
  let formArea = null;
  let handoff = null; // 会开完以后「交给流程」
  let seenCount = -1; // 上次画的时候已出结果的条目数（-1 = 还没画过）
  let forceScroll = false; // 我刚交了东西：下次画完滚到底

  const back = h('a', { id: 'back-to-list', href: '#/' }, '← 会议列表');
  const loading = h('p', { id: 'room-loading' }, '加载中…');
  const body = h('div', { id: 'room-body' }, loading);
  container.appendChild(back);
  container.appendChild(body);

  function teardownView() {
    if (formArea) {
      try { formArea.destroy(); } catch (e) { /* ignore */ }
      formArea = null;
    }
    if (handoff) {
      try { handoff.destroy(); } catch (e) { /* ignore */ }
      handoff = null;
    }
    view = null;
    body.classList.remove('chat');
    clear(body);
  }

  function showFatal(text) {
    teardownView();
    body.appendChild(h('p', { id: 'room-error' }, text));
  }

  function nearBottom() {
    const el = view.mid;
    return el.scrollHeight - el.scrollTop - el.clientHeight <= NEAR_BOTTOM;
  }

  function toBottom() {
    view.mid.scrollTop = view.mid.scrollHeight;
    view.newMsg.hidden = true;
  }

  function buildView() {
    clear(body);
    body.classList.add('chat');
    view = {
      title: h('h1', { id: 'room-title' }),
      status: h('span', { id: 'room-status' }),
      background: h('p', { id: 'room-background', class: 'multiline' }),
      attendees: h('ul', { id: 'room-attendees' }),
      moderator: h('span', { id: 'room-moderator' }),
      line: h('div', { id: 'status-line', role: 'status' }),
      empty: null,
      minutes: h('div', { id: 'minutes' }),
      formArea: h('div', { id: 'form-area' }),
      handoffArea: h('div', { id: 'handoff-area' }),
    };
    view.newMsg = h('div', {
      id: 'new-msg', role: 'button', tabindex: '0', hidden: true,
      onclick: () => toBottom(),
      onkeydown: (ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); toBottom(); } },
    }, '有新消息 ↓');
    view.top = h('header', { id: 'room-head' },
      h('div', { class: 'head-row' },
        view.title,
        view.status,
        h('a', { id: 'room-viewer-link', href: '../#run=' + encodeURIComponent(name), target: '_blank' }, '查看器')),
      h('div', { class: 'head-meta' },
        h('span', { class: 'head-label' }, '参会'), view.attendees,
        h('span', { class: 'head-label' }, '主持'), view.moderator),
      h('details', { id: 'room-info' }, h('summary', null, '背景'), view.background));
    view.tail = h('div', { id: 'room-tail' });
    // 「交给流程」是结论的可选后续：跟在结论卡片下面，默认只是一个小链接，不放进底部输入区
    view.mid = h('section', { id: 'room-main', 'aria-label': '会议记录' }, view.minutes, view.tail, view.handoffArea, view.newMsg);
    view.mid.addEventListener('scroll', () => { if (nearBottom()) view.newMsg.hidden = true; });
    view.composer = h('footer', { id: 'composer' }, view.line, view.formArea);
    body.appendChild(view.top);
    body.appendChild(view.mid);
    body.appendChild(view.composer);
    formArea = createFormArea(view.formArea, {
      name, me: ctx.me, write: ctx.write, refresh, onSent: () => { forceScroll = true; },
    });
    handoff = createHandoff(view.handoffArea, { write: ctx.write });
  }

  function render(m) {
    const first = seenCount < 0;
    const stick = first || forceScroll || nearBottom();
    forceScroll = false;

    view.title.textContent = m.topic;
    view.status.textContent = statusLabel(m.status);
    view.status.setAttribute('data-status', m.status);
    view.background.textContent = m.background;
    clear(view.attendees);
    for (const a of m.attendees) {
      view.attendees.appendChild(h('li', { class: 'attendee', 'data-name': a, 'data-me': a === ctx.me ? 'true' : null }, a));
    }
    view.moderator.textContent = m.moderator;

    const cur = m.status === 'running' ? m.running : m.status === 'waiting' ? m.pending : null;
    const tl = turnLine(m.status, cur, { me: ctx.me, write: ctx.write, error: m.error });
    view.line.setAttribute('data-state', tl.state);
    if (cur && cur.role) view.line.setAttribute('data-role', cur.role);
    else view.line.removeAttribute('data-role');
    clear(view.line);
    view.line.appendChild(h('span', { class: 'status-text' }, tl.text));

    const anyOk = m.rounds.some((r) => r.turns.some((t) => t.state === 'ok'));
    if (view.empty) { view.empty.remove(); view.empty = null; }
    if (!anyOk) {
      view.empty = h('p', { id: 'minutes-empty' }, '还没有人发言');
      view.mid.insertBefore(view.empty, view.minutes);
    }

    clear(view.minutes);
    for (const r of m.rounds) {
      const kids = [h('h2', { class: 'round-title' }, `第 ${r.index} 轮`)];
      for (const t of r.turns) kids.push(turnEl(t, ctx.me));
      if (r.check) kids.push(checkEl(r.check, r.index));
      view.minutes.appendChild(h('section', { class: 'round', 'data-round': r.index }, kids));
    }

    clear(view.tail);
    if (m.decision) view.tail.appendChild(decisionEl(m.decision));

    const n = doneCount(m);
    if (stick) toBottom();
    else if (n > seenCount) view.newMsg.hidden = false;
    seenCount = n;
  }

  function clearOwnError() {
    if (errShown === null) return;
    const el = window.document.getElementById('message');
    if (el && el.textContent === errShown) clearMessage();
    errShown = null;
  }

  function apply(res) {
    if (res.err) {
      const text = res.err && res.err.message ? res.err.message : '连不上服务';
      if (!view) {
        showFatal(text);
        showMessage('error', text);
        stopped = true;
      } else {
        errShown = '刷新失败：' + text;
        showMessage('error', errShown);
      }
      return;
    }
    clearOwnError();
    const run = res.run;
    // 流程脚本里有会议步骤、只是还没开到会：先按「会议以外的步骤」显示，接着刷新；脚本里根本没有会议步骤才算不是会议
    if (!meetingCapable(run)) {
      showFatal('这不是一场会议');
      stopped = true;
      return;
    }
    const key = JSON.stringify({
      status: run.status, error: run.error, events: run.events, pending: run.pending, _control: run._control,
    });
    if (view && key === lastKey) {
      stopped = run.status === 'done';
      return;
    }
    lastKey = key;
    const m = buildMeeting(run);
    if (!view) buildView();
    render(m);
    stopped = run.status === 'done';
    formArea.sync(m);
    handoff.sync(m);
  }

  function clearTimer() {
    if (timer !== null) {
      window.clearTimeout(timer);
      timer = null;
    }
  }

  function scheduleNext() {
    if (!alive || stopped) return;
    clearTimer();
    timer = window.setTimeout(() => {
      timer = null;
      if (!alive || stopped || current) return;
      start();
    }, ctx.pollMs);
  }

  function start() {
    const req = { valid: true, promise: null };
    current = req;
    req.promise = getRun(name).then((run) => ({ run }), (err) => ({ err })).then((res) => {
      if (current === req) current = null;
      if (!alive || !req.valid) return;
      apply(res);
      scheduleNext();
    });
    return req.promise;
  }

  function refresh() {
    if (!alive) return Promise.resolve();
    clearTimer();
    if (queued) return queued;
    if (current) {
      current.valid = false;
      queued = current.promise.then(() => {
        queued = null;
        if (!alive) return undefined;
        return start();
      });
      return queued;
    }
    return start();
  }

  start();

  return {
    refresh,
    destroy() {
      alive = false;
      clearTimer();
      if (current) current.valid = false;
      if (formArea) {
        try { formArea.destroy(); } catch (e) { /* ignore */ }
        formArea = null;
      }
      if (handoff) {
        try { handoff.destroy(); } catch (e) { /* ignore */ }
        handoff = null;
      }
    },
  };
}
