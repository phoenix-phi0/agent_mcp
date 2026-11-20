const DIRECT = new Set(['id', 'href', 'type', 'name', 'for', 'placeholder', 'role', 'rows', 'title', 'min', 'max']);
const BOOL = new Set(['hidden', 'disabled', 'checked', 'required', 'novalidate', 'value', 'selected']);

export function h(tag, attrs, ...children) {
  const el = window.document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === 'class') {
      if (v) el.className = v;
    } else if (k.startsWith('data-') || k.startsWith('aria-') || DIRECT.has(k)) {
      if (v !== null && v !== undefined && v !== false) el.setAttribute(k, v === true ? '' : String(v));
    } else if (k.startsWith('on') && typeof v === 'function') {
      el.addEventListener(k.slice(2), v);
    } else if (BOOL.has(k)) {
      if (k === 'value') {
        if (v !== null && v !== undefined) el.value = v;
      } else if (v) {
        el[k] = true;
        if (k === 'novalidate' || k === 'required' || k === 'hidden') el.setAttribute(k, '');
      }
    } else if (v !== null && v !== undefined && v !== false) {
      el.setAttribute(k, v === true ? '' : String(v));
    }
  }
  const add = (c) => {
    if (c === null || c === undefined || c === false) return;
    if (Array.isArray(c)) c.forEach(add);
    else if (typeof c === 'string' || typeof c === 'number') el.appendChild(window.document.createTextNode(String(c)));
    else el.appendChild(c);
  };
  children.forEach(add);
  return el;
}

export function clear(el) {
  while (el.firstChild) el.removeChild(el.firstChild);
}

export function showMessage(kind, text) {
  const m = window.document.getElementById('message');
  if (!m) return;
  m.textContent = text;
  m.setAttribute('data-kind', kind);
  m.removeAttribute('hidden');
}

export function clearMessage() {
  const m = window.document.getElementById('message');
  if (!m) return;
  m.textContent = '';
  m.setAttribute('hidden', '');
  m.removeAttribute('data-kind');
}

const STATUS = {
  outside: '流程在做会议以外的事', running: '进行中', waiting: '等待中', done: '已结束', error: '出错', aborted: '已中止', interrupted: '被打断' };
export function statusLabel(status) {
  return STATUS[status] || status;
}

export const STEP_VERB = { '发言': '发言', '追问': '回答追问', '主持判断': '判断', '会议结论': '写结论' };
export function stepVerb(name) {
  return STEP_VERB[name] || name;
}

export function turnLine(status, cur, { me, write, error } = {}) {
  switch (status) {
    case 'running':
      return { state: 'running', text: cur ? `${cur.role} 正在${stepVerb(cur.name)}…` : '会议进行中…' };
    case 'waiting': {
      const c = cur || {};
      if (write && c.role === me && (c.reason === undefined || c.reason === null || c.reason === 'human')) {
        return { state: 'waiting-me', text: `轮到你（${c.role}）${stepVerb(c.name)}` };
      }
      return { state: 'waiting-other', text: `等 ${c.role} ${stepVerb(c.name)}…` };
    }
    case 'done': return { state: 'done', text: '会议已结束' };
    case 'outside': return { state: 'outside', text: '流程在做会议以外的事（会议还没开始，或开完了在等别的步骤）' };
    case 'error': return { state: 'error', text: `会议出错：${error || '未知错误'}` };
    case 'aborted': return { state: 'aborted', text: '会议已被中止' };
    case 'interrupted': return { state: 'interrupted', text: '会议被打断了（服务重启过），要在查看器里点续跑' };
    default: return { state: status, text: statusLabel(status) };
  }
}

export function formatTime(iso) {
  if (!iso) return '';
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?(?:\.\d+)?(Z|[+-]\d{2}:?\d{2})?$/.exec(iso);
  if (!m) return iso;
  let tz = m[7] || 'Z';
  if (/^[+-]\d{4}$/.test(tz)) tz = tz.slice(0, 3) + ':' + tz.slice(3);
  const d = new Date(`${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6] || '00'}${tz}`);
  if (isNaN(d.getTime())) return iso;
  const p = (n) => String(n).padStart(2, '0');
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}
