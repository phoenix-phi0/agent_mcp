// 会开完以后「交给流程」：选一个入口，把会议结论拼成需求填进它的参数，人看过、改过再启动。
// createHandoff(container, {write}) → {sync(meeting), destroy()}
// 只在：可写、会议已开完（done）、结论已出（decision ok）时出现；出现后不随轮询重画，免得冲掉正在改的内容。
import { h, clear, showMessage, clearMessage } from './ui.js';
import { getEntries, startRun } from './api.js';

// 承接会议结论的参数：入口声明了哪个就填哪个（按这个顺序认第一个）
export const TEXT_PARAMS = ['content', 'goal'];
export const VALUE_MAX = 4000;
const LABELS = {
  content: '需求（已按会议结论填好，可以改）',
  goal: '目标（已按会议结论填好，可以改）',
  project: '项目目录（work/ 下；用一个新名字，不要和已有项目重名）',
  review_attendees: '评审会参会者（逗号分隔，按发言顺序；想自己参加就加上 HUMAN）',
  moderator: '评审会主持人（不填是 MODERATOR；填 HUMAN 就是你来主持）',
};

export function targetParam(entry) {
  const names = new Set((entry && Array.isArray(entry.params) ? entry.params : []).map((p) => p && p.name));
  return TEXT_PARAMS.find((n) => names.has(n)) || null;
}

function listOf(v) {
  return Array.isArray(v) ? v.filter((x) => x !== null && x !== undefined) : [];
}

function str(v) {
  return v === undefined || v === null ? '' : String(v);
}

// 会议结论 → 交给流程的需求文本（截到 VALUE_MAX 字）
export function handoffText(m) {
  const r = (m && m.decision && m.decision.result) || {};
  const out = [`来自会议「${str(m && m.topic)}」的结论：${str(r.decision)}`];
  const reasons = listOf(r.reasons);
  if (reasons.length) out.push('理由：', ...reasons.map((x) => '- ' + str(x)));
  const todo = listOf(r.todo);
  if (todo.length) out.push('待办：', ...todo.map((x) => `- ${str(x.who)}：${str(x.what)}`));
  const dissent = listOf(r.dissent);
  if (dissent.length) out.push('保留意见：', ...dissent.map((x) => '- ' + str(x)));
  const bg = str(m && m.background).trim();
  if (bg && bg !== '无') out.push('会议背景：' + bg);
  return Array.from(out.join('\n')).slice(0, VALUE_MAX).join('');
}

// 项目目录默认值后面加上时间，避免直接用到已有项目的目录
export function freshProject(base, now = new Date()) {
  const p = (n) => String(n).padStart(2, '0');
  const stamp = `${p(now.getMonth() + 1)}${p(now.getDate())}${p(now.getHours())}${p(now.getMinutes())}`;
  return `${str(base) || 'project'}_${stamp}`;
}

export function createHandoff(container, opts) {
  const { write } = opts || {};
  let alive = true;
  let shown = false;
  let starting = false;
  let started = false; // 启动成功过：按钮和回车都不再启动第二次

  function ready(m) {
    return write === true && m && !m.embedded && m.status === 'done' && m.decision && m.decision.state === 'ok' && !!m.decision.result;
  }

  function sync(m) {
    if (!alive) return;
    if (!ready(m)) {
      if (shown) { clear(container); shown = false; }
      return;
    }
    if (shown) return;
    shown = true;
    render(m);
  }

  async function render(m) {
    clear(container);
    // 不是每场会都要交给流程：默认只是结论下面一个小链接，点开才展开
    const body = h('div', { class: 'handoff-body' },
      h('p', { class: 'handoff-hint' }, '把会议结论当成需求，交给一个流程去做。不需要就不用管。'),
      h('p', { id: 'handoff-loading' }, '加载入口…'));
    const box = h('details', { id: 'handoff' },
      h('summary', null, h('span', { class: 'handoff-title' }, '交给流程')),
      body);
    box.addEventListener('toggle', () => {
      if (box.open && typeof box.scrollIntoView === 'function') {
        try { box.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); } catch (e) { /* ignore */ }
      }
    });
    container.appendChild(box);
    let entries;
    try {
      entries = (await getEntries()).entries || [];
    } catch (e) {
      if (!alive || !box.isConnected) return;
      box.querySelector('#handoff-loading').remove();
      body.appendChild(h('p', { id: 'handoff-error' }, '取不到能启动的流程：' + (e && e.message ? e.message : String(e))));
      return;
    }
    if (!alive || !box.isConnected) return;
    box.querySelector('#handoff-loading').remove();
    const usable = entries.filter((e) => e && e.entry !== 'meeting.zs' && targetParam(e));
    if (!usable.length) {
      body.appendChild(h('p', { id: 'handoff-none' },
        '没有能接收会议结论的流程：入口脚本要用「# 参数：」声明 content 或 goal。'));
      return;
    }

    const select = h('select', { id: 'handoff-entry' },
      usable.map((e) => h('option', { value: e.entry }, `${str(e.title) || e.entry}（${e.entry}）`)));
    const params = h('div', { id: 'handoff-params' });
    const button = h('button', { id: 'handoff-start', type: 'submit' }, '启动流程');
    const result = h('div', { id: 'handoff-result' });

    function renderParams() {
      clear(params);
      const entry = usable.find((e) => e.entry === select.value) || usable[0];
      const target = targetParam(entry);
      for (const p of entry.params || []) {
        const id = 'handoff-param-' + p.name;
        let control;
        if (p.name === target) {
          control = h('textarea', { id, rows: 6, maxlength: String(VALUE_MAX), 'data-param': p.name });
          control.value = handoffText(m);
        } else {
          control = h('input', { id, type: 'text', 'data-param': p.name });
          control.value = p.name === 'project' ? freshProject(p.default) : str(p.default);
        }
        if (p.required) control.setAttribute('data-required', 'true');
        params.appendChild(h('div', { class: p.name === target ? 'form-field handoff-wide' : 'form-field' },
          h('label', { for: id }, (LABELS[p.name] || p.name) + (p.required ? '（必填）' : '')), control));
      }
    }

    async function onSubmit(ev) {
      ev.preventDefault();
      if (starting || started || !alive) return;
      clearMessage();
      const vars = {};
      for (const el of params.querySelectorAll('[data-param]')) {
        const v = el.value.trim();
        if (!v) {
          if (el.getAttribute('data-required') === 'true') {
            showMessage('error', `请填写 ${el.getAttribute('data-param')}`);
            return;
          }
          continue;
        }
        if (Array.from(v).length > VALUE_MAX) {
          showMessage('error', `${el.getAttribute('data-param')} 最多 ${VALUE_MAX} 字`);
          return;
        }
        vars[el.getAttribute('data-param')] = v;
      }
      starting = true;
      button.disabled = true;
      try {
        const r = await startRun(select.value, vars);
        started = true;
        if (!alive) return;
        clear(result);
        result.appendChild(h('p', { id: 'handoff-started', 'data-run': r.name },
          '已启动：', h('a', { id: 'handoff-link', href: '../#run=' + encodeURIComponent(r.name), target: '_blank' }, r.name),
          '（在查看器里看进度）'));
        showMessage('ok', '流程已启动');
      } catch (e) {
        if (!alive) return;
        let text = e && e.message ? e.message : '启动失败';
        if (e && Array.isArray(e.errors) && e.errors.length) {
          text += e.errors.map((x) => `（${str(x && x.path)}：${str(x && x.message)}）`).join('');
        }
        showMessage('error', text);
        button.disabled = false;
      } finally {
        starting = false;
      }
    }

    select.addEventListener('change', renderParams);
    body.appendChild(h('form', { id: 'handoff-form', novalidate: true, onsubmit: onSubmit },
      h('div', { class: 'form-field' }, h('label', { for: 'handoff-entry' }, '交给哪个流程'), select),
      params,
      h('p', { class: 'panel-actions' }, button)));
    body.appendChild(result);
    renderParams();
  }

  return {
    sync,
    destroy() {
      alive = false;
      clear(container);
    },
  };
}
