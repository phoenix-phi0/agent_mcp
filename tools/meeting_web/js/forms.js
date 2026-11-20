// 会议室里轮到我时的输入区：发言/追问回答（聊天输入框）、主持判断、会议结论。
// createFormArea(container, {name, me, write, refresh, onSent}) → {sync(meeting), destroy()}
import { h, clear, showMessage, clearMessage, stepVerb } from './ui.js';
import { submitResult } from './api.js';
import { lines } from './meeting_model.js';

const FORM_NAMES = new Set(['发言', '追问', '主持判断', '会议结论']);
const SPEECH_MAX = 3000;
const QUESTION_MAX = 1000;
const GROW_MAX = 220; // 输入框跟着内容长高，最多这么高（px），再多就在框里滚

function charLen(s) {
  return Array.from(s).length;
}

// 流程里的会：参考文本里除了发言记录以外的东西（设计稿等），按 JSON 缩进显示；单独开的会不显示
const MATERIAL_SKIP = new Set(['minutes', 'open_issues', 'check']);
export function materialOf(meeting, p) {
  if (!meeting || !meeting.embedded || !p || !p.context || typeof p.context !== 'object') return '';
  const keep = {};
  for (const [k, v] of Object.entries(p.context)) if (!MATERIAL_SKIP.has(k)) keep[k] = v;
  if (!Object.keys(keep).length) return '';
  return JSON.stringify(keep, null, 2);
}

// 输入框跟着内容长高
function autoGrow(ta) {
  const fit = () => {
    ta.style.height = 'auto';
    const sh = ta.scrollHeight;
    if (sh) ta.style.height = Math.min(sh, GROW_MAX) + 'px';
  };
  ta.addEventListener('input', fit);
  return ta;
}

// Enter 发送、Shift+Enter 换行；输入法还在选字时（isComposing / keyCode 229）的 Enter 不算
function enterToSend(ta, button) {
  ta.addEventListener('keydown', (ev) => {
    if (ev.key !== 'Enter' || ev.shiftKey || ev.isComposing || ev.keyCode === 229) return;
    ev.preventDefault();
    if (!button.disabled) button.click();
  });
  return ta;
}

export function createFormArea(container, opts) {
  const { name, me, write, refresh, onSent } = opts || {};
  let alive = true;
  let current = null; // 当前表单实例 {step, pendingName, form, button, submitting}
  const submittedSteps = new Set(); // 已提交成功的 pending.step
  let seen = null; // 最近一次 sync 看到的会议（只用来判断提交后是否还在 running）

  function eligible(meeting) {
    const p = meeting && meeting.pending;
    return !!(write === true && meeting && meeting.status === 'waiting' && p
      && p.role === me && p.reason === 'human' && FORM_NAMES.has(p.name));
  }

  function emptyArea() {
    current = null;
    clear(container);
  }

  function errorText(e) {
    let text = e && e.message ? e.message : '请求失败';
    if (e && Array.isArray(e.errors) && e.errors.length) {
      text += e.errors.map((x) => `（${x && x.path !== undefined ? x.path : ''}：${x && x.message !== undefined ? x.message : ''}）`).join('');
    }
    return text;
  }

  async function submitFlow(inst, result) {
    inst.submitting = true;
    inst.button.disabled = true;
    clearMessage();
    let ok = false;
    try {
      await submitResult(name, inst.step, result);
      ok = true;
    } catch (e) {
      if (alive) showMessage('error', errorText(e));
    }
    if (ok) {
      submittedSteps.add(inst.step);
      if (alive) {
        showMessage('ok', '已交上去，会议接着进行');
        if (current === inst) emptyArea();
        if (typeof onSent === 'function') {
          try { onSent(); } catch (e) { /* ignore */ }
        }
      }
    } else {
      inst.submitting = false;
      inst.button.disabled = false;
    }
    if (!alive || typeof refresh !== 'function') return;
    seen = null;
    try { await refresh(); } catch (e) { /* 刷新失败由会议室自己提示 */ }
    // 后端交上去之后在后台接着跑：刚刷新到的可能还是「进行中」。
    // 提交成功后再追几次，直到不是 running（轮询间隔很大时页面也能马上跟上）
    if (!ok) return;
    for (let i = 0; i < 30 && alive && seen && seen.status === 'running'; i++) {
      await new Promise((r) => window.setTimeout(r, 150));
      if (!alive) return;
      try { await refresh(); } catch (e) { /* 同上 */ }
    }
  }

  // 统一的 submit 处理：preventDefault → 校验 → 提交
  function makeHandler(inst, collect) {
    return (ev) => {
      ev.preventDefault();
      if (inst.submitting || !alive) return;
      const r = collect();
      if (r.error) {
        showMessage('error', r.error);
        return;
      }
      submitFlow(inst, r.result);
    };
  }

  function field(id, label, control) {
    return h('div', { class: 'form-field' }, h('label', { for: id }, label), control);
  }

  // 发言 / 追问回答：聊天输入框。上面一排小开关（认可、点名），点了名才出现问题框
  function buildSpeech(meeting, p) {
    const isReply = p.name === '追问';
    const button = h('button', { id: 'speech-submit', type: 'submit', class: 'send' }, '发送');
    const text = h('textarea', {
      id: 'speech-text', name: 'speech', rows: 2, maxlength: String(SPEECH_MAX), required: true,
      placeholder: isReply ? '回答他的追问…' : '说点什么…',
    });
    autoGrow(enterToSend(text, button));
    const agree = h('input', { id: 'speech-agree', type: 'checkbox', name: 'agree' });
    let ask = null;
    let question = null;
    let questionRow = null;
    if (!isReply) {
      const names = [];
      for (const a of meeting.attendees || []) {
        if (a !== me && !names.includes(a)) names.push(a);
      }
      ask = h('select', { id: 'speech-ask', name: 'ask' },
        h('option', { value: '' }, '不点名'),
        names.map((n) => h('option', { value: n }, n)));
      question = h('textarea', {
        id: 'speech-question', name: 'question', rows: 1, maxlength: String(QUESTION_MAX), placeholder: '要问他的问题',
      });
      autoGrow(enterToSend(question, button));
      questionRow = h('div', { class: 'composer-question', hidden: true },
        h('label', { for: 'speech-question', class: 'composer-at' }, '@'), question);
      ask.addEventListener('change', () => {
        questionRow.hidden = !ask.value;
        if (ask.value) {
          question.placeholder = `要问 ${ask.value} 的问题`;
          question.focus();
        } else {
          question.value = ''; // 收起来的问题框里不留字：否则交的时候报「没点名问谁」，人却看不见那段字
        }
      });
    }
    const inst = { step: p.step, pendingName: p.name, button, submitting: false };
    const collect = () => {
      const speech = text.value.trim();
      if (!speech) return { error: '请写发言内容' };
      if (charLen(speech) > SPEECH_MAX) return { error: '发言最多 3000 字' };
      let askVal = '';
      let q = '';
      if (!isReply) {
        askVal = ask.value;
        q = question.value.trim();
        if (askVal && !q) return { error: '点名了就要写问题' };
        if (!askVal && q) return { error: '没点名问谁，问题不会被问：请选一位，或清空问题' };
      }
      return { result: { speech, agree: !!agree.checked, ask: askVal, question: q } };
    };
    const tools = h('div', { class: 'composer-tools' },
      h('span', { class: 'chip chip-check' }, agree, h('label', { for: 'speech-agree' }, '认可现在的方向')),
      isReply ? null : h('span', { class: 'chip chip-select' },
        h('label', { for: 'speech-ask' }, '点名'), ask));
    const form = h('form', {
      id: 'speech-form', class: 'composer-form', novalidate: true, 'data-step': p.step, 'data-kind': isReply ? 'reply' : 'speech',
      onsubmit: makeHandler(inst, collect),
    },
    h('label', { for: 'speech-text', class: 'sr-only' }, isReply ? '你的回答' : '你的发言'),
    tools,
    questionRow,
    h('div', { class: 'composer-row' }, text, button),
    h('p', { class: 'composer-hint' }, 'Enter 发送，Shift+Enter 换行'));
    inst.form = form;
    return inst;
  }

  function buildCheck(meeting, p) {
    const yes = h('input', { id: 'check-done-yes', type: 'radio', name: 'done', value: '是' });
    const no = h('input', { id: 'check-done-no', type: 'radio', name: 'done', value: '否' });
    const dis = h('textarea', { id: 'check-disagreements', name: 'disagreements', rows: 2, placeholder: '每行一条，没有就空着' });
    const summary = h('textarea', { id: 'check-summary', name: 'summary', rows: 2, required: true, placeholder: '一两句话' });
    autoGrow(dis);
    autoGrow(summary);
    const button = h('button', { id: 'check-submit', type: 'submit', class: 'send' }, '提交判断');
    const inst = { step: p.step, pendingName: p.name, button, submitting: false };
    const collect = () => {
      const done = yes.checked ? '是' : no.checked ? '否' : '';
      if (!done) return { error: '请选择能不能出结论' };
      const s = summary.value.trim();
      if (!s) return { error: '请写这一轮讨论到哪了' };
      return { result: { done, disagreements: lines(dis.value), summary: s } };
    };
    inst.form = h('form', {
      id: 'check-form', class: 'panel-form', novalidate: true, 'data-step': p.step, onsubmit: makeHandler(inst, collect),
    },
    h('div', { class: 'form-field form-radios', role: 'radiogroup', 'aria-label': '能不能出结论？' },
      h('span', { class: 'form-legend' }, '能不能出结论？'),
      h('span', { class: 'seg' }, yes, h('label', { for: 'check-done-yes' }, '可以出结论')),
      h('span', { class: 'seg' }, no, h('label', { for: 'check-done-no' }, '还要再议一轮'))),
    field('check-disagreements', '还没解决的分歧，每行一条', dis),
    field('check-summary', '这一轮讨论到哪了', summary),
    h('p', { class: 'panel-actions' }, button));
    return inst;
  }

  function buildDecision(meeting, p) {
    const decision = h('textarea', { id: 'decision-text', name: 'decision', rows: 2, required: true });
    const reasons = h('textarea', { id: 'decision-reasons', name: 'reasons', rows: 3, required: true });
    const dissent = h('textarea', { id: 'decision-dissent', name: 'dissent', rows: 2 });
    const todoList = h('div', { id: 'todo-list' });
    const summary = h('textarea', { id: 'decision-summary', name: 'summary', rows: 1, required: true });
    [decision, reasons, dissent, summary].forEach(autoGrow);
    const button = h('button', { id: 'decision-submit', type: 'submit', class: 'send' }, '提交结论');
    const inst = { step: p.step, pendingName: p.name, button, submitting: false };

    function addRow() {
      const row = h('div', { class: 'todo-row' });
      row.appendChild(h('input', { class: 'todo-who', type: 'text', 'aria-label': '谁', placeholder: '谁' }));
      row.appendChild(h('input', { class: 'todo-what', type: 'text', 'aria-label': '做什么', placeholder: '做什么' }));
      row.appendChild(h('button', { class: 'todo-remove', type: 'button', onclick: () => row.remove() }, '删除'));
      todoList.appendChild(row);
    }
    const addBtn = h('button', { id: 'todo-add', type: 'button', class: 'ghost' }, '+ 加一条待办');
    addBtn.addEventListener('click', addRow);

    const collect = () => {
      const d = decision.value.trim();
      if (!d) return { error: '请写结论' };
      const rs = lines(reasons.value);
      if (!rs.length) return { error: '至少写一条理由' };
      const s = summary.value.trim();
      if (!s) return { error: '请写一句话总结' };
      const todo = [];
      for (const row of todoList.querySelectorAll('.todo-row')) {
        const who = row.querySelector('.todo-who').value.trim();
        const what = row.querySelector('.todo-what').value.trim();
        if (!who && !what) continue;
        if (!who || !what) return { error: '待办要同时写谁和做什么' };
        todo.push({ who, what });
      }
      return { result: { decision: d, reasons: rs, dissent: lines(dissent.value), todo, summary: s } };
    };
    inst.form = h('form', {
      id: 'decision-form', class: 'panel-form', novalidate: true, 'data-step': p.step, onsubmit: makeHandler(inst, collect),
    },
    field('decision-text', '定下来的结论', decision),
    field('decision-reasons', '理由，每行一条', reasons),
    field('decision-dissent', '保留意见，每行一条（可不写）', dissent),
    h('div', { class: 'form-field' }, h('span', { class: 'form-legend' }, '待办（可不写）'), todoList, h('p', null, addBtn)),
    field('decision-summary', '一句话总结', summary),
    h('p', { class: 'panel-actions' }, button));
    return inst;
  }

  function build(meeting) {
    const p = meeting.pending;
    const inst = p.name === '主持判断' ? buildCheck(meeting, p)
      : p.name === '会议结论' ? buildDecision(meeting, p)
        : buildSpeech(meeting, p);
    const task = p.task === undefined || p.task === null ? '' : String(p.task);
    clear(container);
    // 「轮到你」在 #status-line 里已经显示了；这里给读屏留一份
    container.appendChild(h('div', { class: 'form-banner sr-only' }, `轮到你（${me}）${stepVerb(p.name)}`));
    if (p.name === '追问') {
      container.appendChild(h('div', { class: 'form-task form-quote' }, task));
    }
    const extras = [];
    if (p.name !== '追问' && task) {
      extras.push(h('details', { class: 'form-details' },
        h('summary', null, '议题和要求'),
        h('div', { class: 'form-task' }, task)));
    }
    const material = materialOf(meeting, p);
    if (material) {
      extras.push(h('details', { class: 'form-details', id: 'form-material' },
        h('summary', null, '会议材料'),
        h('pre', { class: 'form-material-text' }, material)));
    }
    if (extras.length) container.appendChild(h('div', { class: 'form-extras' }, extras));
    container.appendChild(inst.form);
    current = inst;
    if (inst.pendingName === '发言' || inst.pendingName === '追问') {
      const ta = inst.form.querySelector('#speech-text');
      try { ta.focus({ preventScroll: true }); } catch (e) { /* ignore */ }
    }
  }

  return {
    sync(meeting) {
      if (!alive) return;
      seen = meeting;
      if (!eligible(meeting)) {
        if (container.firstChild || current) emptyArea();
        return;
      }
      const p = meeting.pending;
      if (submittedSteps.has(p.step)) {
        if (container.firstChild || current) emptyArea();
        return;
      }
      if (current && current.step === p.step && current.pendingName === p.name && current.form.parentNode === container) return;
      build(meeting);
    },
    destroy() {
      alive = false;
      current = null;
    },
  };
}
