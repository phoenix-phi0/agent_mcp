// 纯函数：把 /api/run 的记录整理成会议视图。不碰 DOM、不发请求，Node 里可直接 import。
// 会议按步骤的「格式」认，不按流程名、步骤名：speech（发言/追问）、meeting_check（主持判断）、meeting_decision（会议结论）。
// 所以单独开的会（meeting_workflow）和嵌在别的流程里的会（如前端流程的「评审发言 / 评审判断 / 评审结论」）用同一个会议室。
// 嵌在流程里的会：步骤名统一成「发言 / 追问 / 主持判断 / 会议结论」再往下用。

export const MEETING_WORKFLOW = 'meeting_workflow';
export const MEETING_FORMATS = new Set(['speech', 'meeting_check', 'meeting_decision']);
const WORKFLOW_LABEL = {
  frontend_workflow: '前端流程', project_workflow: '整项目流程', project_meeting_workflow: '整项目流程（架构评审会）',
  refactor_workflow: '重构流程', change_workflow: '改项目流程',
};

export function splitNames(str) {
  if (str === null || str === undefined) return [];
  return String(str).split(',').map((s) => s.trim()).filter(Boolean);
}

export function lines(text) {
  if (text === null || text === undefined) return [];
  return String(text).split('\n').map((s) => s.trim()).filter(Boolean);
}

// 一个步骤在会议里的统一名字；不是会议步骤返回 null。
// 单独开的会按步骤名认（发言 / 追问 / 主持判断 / 会议结论）；流程里的会按格式认（步骤名各流程自己起）
export function canonicalName(name, format, embedded = true) {
  if (!embedded) return ['发言', '追问', '主持判断', '会议结论'].includes(name) ? name : null;
  if (format === 'speech') return String(name || '').includes('追问') ? '追问' : '发言';
  if (format === 'meeting_check') return '主持判断';
  if (format === 'meeting_decision') return '会议结论';
  // 老记录、测试数据可能没有 format：按单独开的会的步骤名认
  if (['发言', '追问', '主持判断', '会议结论'].includes(name)) return name;
  return null;
}

function hasMeetingStep(run) {
  for (const ev of (run && run.events) || []) {
    if (ev && ev.type === 'task' && MEETING_FORMATS.has(ev.format)) return true;
  }
  const p = run && run.status === 'waiting' ? run.pending : null;
  return !!(p && MEETING_FORMATS.has(p.format));
}

// 已经有会议步骤的运行（单独开的会，或流程里已经开到会）
export function isMeetingRun(run) {
  return !!run && (run.workflow === MEETING_WORKFLOW || hasMeetingStep(run));
}

// 流程脚本里有会议步骤（_formats 是脚本用到的格式）：还没开到会也算，会议室先显示「会议以外的步骤」
export function meetingCapable(run) {
  if (isMeetingRun(run)) return true;
  const fmts = run && run._formats && typeof run._formats === 'object' ? Object.keys(run._formats) : [];
  return fmts.some((f) => MEETING_FORMATS.has(f));
}

// 嵌在别的流程里的会（记录没写流程名的按单独开的会算）
export function isEmbedded(run) {
  return !!run && !!run.workflow && run.workflow !== MEETING_WORKFLOW;
}

function str(v) {
  return v === undefined || v === null ? '' : String(v);
}

// 议题：单独开的会用启动时传的 topic；流程里的会用「哪个流程里的会」加上流程的需求摘要
export function meetingTopic(run) {
  const vars = (run && run._control && run._control.vars) || {};
  const inputs = (run && run.inputs) || {};
  if (typeof vars.topic === 'string' && vars.topic) return vars.topic;
  if (typeof inputs.topic === 'string' && inputs.topic) return inputs.topic;
  if (isEmbedded(run)) {
    const wf = str(run.workflow);
    const label = WORKFLOW_LABEL[wf] || wf;
    const goal = [vars.content, vars.goal, vars.brief, inputs.content, inputs.goal, inputs.task]
      .find((x) => typeof x === 'string' && x);
    const chars = goal ? Array.from(goal) : [];
    const brief = chars.length ? chars.slice(0, 40).join('') + (chars.length > 40 ? '…' : '') : '';
    return `「${label}」里的会` + (brief ? `：${brief}` : '');
  }
  return '（没有记录议题）';
}

// 每个 step 取最后一条 task 事件（数组里靠后的为准），只留会议步骤，按 step 升序返回条目
function collectEntries(events, embedded) {
  const byStep = new Map();
  for (const ev of events || []) {
    if (!ev || ev.type !== 'task' || ev.step === undefined || ev.step === null) continue;
    byStep.set(ev.step, ev);
  }
  return [...byStep.values()]
    .sort((a, b) => a.step - b.step)
    .map((ev) => ({
      step: ev.step,
      name: canonicalName(ev.name, ev.format, embedded),
      role: ev.role,
      state: ev.status,
      result: ev.status === 'ok' && ev.result !== undefined ? ev.result : null,
    }))
    .filter((e) => e.name !== null);
}

function findRunning(events, entries, embedded) {
  const stateOf = new Map(entries.map((e) => [e.step, e.state]));
  let found = null;
  for (const ev of events || []) {
    if (!ev || ev.type !== 'task' || ev.status !== 'running') continue;
    if (stateOf.get(ev.step) !== 'running') continue;
    found = { step: ev.step, name: canonicalName(ev.name, ev.format, embedded), role: ev.role };
  }
  return found;
}

function questionOf(speechEntry) {
  if (!speechEntry || !speechEntry.result || typeof speechEntry.result !== 'object') return null;
  const q = speechEntry.result.question;
  return q === undefined || q === null ? null : q;
}

export function buildMeeting(run) {
  const ctl = (run && run._control) || {};
  const vars = ctl.vars || {};
  const embedded = isEmbedded(run);
  const entries = collectEntries(run && run.events, embedded);

  const rounds = [];
  let decision = null;
  const newRound = () => {
    const r = { index: rounds.length + 1, turns: [], check: null };
    rounds.push(r);
    return r;
  };
  const lastSpeech = (round) => {
    for (let i = round.turns.length - 1; i >= 0; i--) if (round.turns[i].kind === 'speech') return round.turns[i];
    return null;
  };
  const place = (e) => {
    if (e.name === '发言') {
      let r = rounds[rounds.length - 1];
      if (!r || r.check) r = newRound();
      r.turns.push({ ...e, kind: 'speech' });
    } else if (e.name === '追问') {
      const r = rounds[rounds.length - 1] || newRound();
      const sp = lastSpeech(r);
      r.turns.push({ ...e, kind: 'reply', askedBy: sp ? sp.role : null, question: questionOf(sp) });
    } else if (e.name === '主持判断') {
      const r = rounds[rounds.length - 1] || newRound();
      r.check = { ...e };
    } else if (e.name === '会议结论') {
      decision = { ...e };
    }
  };
  for (const e of entries) place(e);

  let pending = null;
  let pendingOutside = false; // 流程停在会议以外的步骤
  if (run && run.status === 'waiting' && run.pending) {
    const p = run.pending;
    const name = canonicalName(p.name, p.format, embedded);
    if (name === null) {
      pendingOutside = true;
    } else {
      pending = { step: p.step, name, role: p.role, reason: p.reason, format: p.format, task: p.task };
      if (embedded) pending.context = p.context;      // 流程里的会：表单上方显示会议材料用
      const exists = rounds.some((r) => r.turns.some((t) => t.step === p.step) || (r.check && r.check.step === p.step))
        || (decision && decision.step === p.step);
      if (!exists) place({ step: p.step, name, role: p.role, state: 'waiting', result: null });
    }
  }
  const running = findRunning(run && run.events, entries, embedded);

  // 会议自己的状态：单独开的会就是运行的状态；流程里的会，结论出了就算开完（流程接着做别的），
  // 流程停在、跑在会议以外的步骤上是 outside
  let status = run ? run.status : undefined;
  if (embedded) {
    if (decision && decision.state === 'ok') status = 'done';
    else if (run.status === 'waiting' && pendingOutside) status = 'outside';
    else if (run.status === 'running' && !running) status = 'outside';
  }

  let attendees = splitNames(vars.attendees || vars.review_attendees);
  if (!attendees.length) {
    for (const e of entries) if (e.name === '发言' && !attendees.includes(e.role)) attendees.push(e.role);
    if (embedded && pending && pending.name === '发言' && !attendees.includes(pending.role)) attendees.push(pending.role);
  }
  const modEntry = entries.find((e) => e.name === '主持判断' || e.name === '会议结论');

  return {
    name: run ? run._name : undefined,
    workflow: run ? run.workflow : undefined,
    embedded,
    status,
    error: (run && run.error) || null,
    topic: meetingTopic(run),
    background: vars.background || (embedded ? '（会议材料在每一步的参考文本里，轮到你时在表单上方可以展开看）' : '无'),
    attendees,
    moderator: vars.moderator || (embedded && modEntry ? modEntry.role : (embedded ? '（还没轮到主持人）' : 'MODERATOR')),
    rounds,
    decision,
    running,
    pending,
  };
}
