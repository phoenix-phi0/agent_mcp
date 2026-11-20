// 开会页：填议题和背景，按发言顺序选参会者，选主持人，启动后跳到会议室
import { h, clear, showMessage, clearMessage } from '../ui.js';
import { getEntries, startMeeting } from '../api.js';
import { MEETING_ENTRY } from '../env.js';

const MODERATOR_DEFAULT = 'MODERATOR';

function isHuman(agent) {
  return !!agent && agent.model === 'human';
}

export function mount(container, ctx) {
  let alive = true;
  let submitting = false;

  const back = h('a', { id: 'back-to-list', href: '#/' }, '回会议列表');
  container.appendChild(h('h1', { id: 'start-title' }, '开会'));

  if (!ctx.write) {
    container.appendChild(h('p', { id: 'readonly-notice' }, '这是只读的服务，不能开会，只能看'));
    container.appendChild(back);
    return { destroy() { alive = false; } };
  }

  const body = h('div', { id: 'start-body' }, h('p', { id: 'start-loading' }, '加载中…'));
  container.appendChild(body);
  container.appendChild(back);

  function buildForm(agents) {
    const byName = new Map(agents.map((a) => [a.name, a]));
    const attendees = []; // 按发言顺序的卡名

    const topic = h('input', { id: 'topic', type: 'text', name: 'topic', required: true, placeholder: '这场会要讨论什么' });
    const background = h('textarea', { id: 'background', name: 'background', rows: 3, placeholder: '背景（可不填）' });
    const poolBox = h('div', { id: 'card-pool' });
    const emptyBox = h('div', { class: 'attendee-empty-box' });
    const list = h('ul', { id: 'attendee-list' });
    const moderator = h('select', { id: 'moderator', name: 'moderator' });
    const submit = h('button', { id: 'start-submit', type: 'submit' }, '开会');

    const addButtons = new Map();

    if (!agents.length) {
      poolBox.appendChild(h('p', { id: 'card-pool-empty' }, '没有可选的角色卡'));
    }
    for (const a of agents) {
      const human = isHuman(a);
      const btn = h('button', { class: 'card-add', type: 'button', onclick: () => addAttendee(a.name) }, '加入');
      addButtons.set(a.name, btn);
      poolBox.appendChild(h('div', { class: 'card', 'data-name': a.name, 'data-human': human ? 'true' : 'false' },
        h('span', { class: 'card-name' }, a.name),
        human ? h('span', { class: 'card-human' }, '人') : null,
        h('span', { class: 'card-desc' }, a.description || ''),
        btn));
    }

    for (const a of agents) {
      moderator.appendChild(h('option', { value: a.name }, isHuman(a) ? `${a.name}（人）` : a.name));
    }
    if (agents.length) {
      moderator.value = byName.has(MODERATOR_DEFAULT) ? MODERATOR_DEFAULT : agents[0].name;
    }

    function addAttendee(name) {
      if (attendees.includes(name)) return;
      attendees.push(name);
      renderAttendees();
    }
    function move(i, d) {
      const j = i + d;
      if (j < 0 || j >= attendees.length) return;
      const t = attendees[i];
      attendees[i] = attendees[j];
      attendees[j] = t;
      renderAttendees();
    }
    function removeAt(i) {
      attendees.splice(i, 1);
      renderAttendees();
    }

    function renderAttendees() {
      clear(list);
      clear(emptyBox);
      if (!attendees.length) {
        emptyBox.appendChild(h('p', { id: 'attendee-empty' }, '还没有选参会者'));
      }
      attendees.forEach((name, i) => {
        list.appendChild(h('li', { class: 'attendee-item', 'data-name': name },
          h('span', { class: 'attendee-no' }, String(i + 1)),
          h('span', { class: 'attendee-name' }, name),
          h('button', { class: 'attendee-up', type: 'button', disabled: i === 0, onclick: () => move(i, -1) }, '上移'),
          h('button', { class: 'attendee-down', type: 'button', disabled: i === attendees.length - 1, onclick: () => move(i, 1) }, '下移'),
          h('button', { class: 'attendee-remove', type: 'button', onclick: () => removeAt(i) }, '移除')));
      });
      for (const [name, btn] of addButtons) btn.disabled = attendees.includes(name);
    }

    async function onSubmit(ev) {
      ev.preventDefault();
      if (submitting) return;
      const t = topic.value.trim();
      if (!t) {
        showMessage('error', '请填写议题');
        return;
      }
      if (!attendees.length) {
        showMessage('error', '请至少选一位参会者');
        return;
      }
      const vars = {
        topic: t,
        attendees: attendees.join(','),
        moderator: moderator.value,
      };
      const bg = background.value.trim();
      if (bg) vars.background = bg;
      submitting = true;
      submit.disabled = true;
      clearMessage();
      try {
        const res = await startMeeting(vars);
        if (!alive) return;
        window.location.hash = '#/room/' + encodeURIComponent(res.name);
      } catch (e) {
        if (!alive) return;
        showMessage('error', e && e.message ? e.message : '请求失败');
        submitting = false;
        submit.disabled = false;
      }
    }

    const form = h('form', { id: 'start-form', novalidate: true, onsubmit: onSubmit },
      h('label', { for: 'topic' }, '议题'),
      topic,
      h('label', { for: 'background' }, '背景'),
      background,
      h('h2', null, '参会者（按发言顺序）'),
      h('div', { class: 'start-cols' },
        h('div', null, h('h3', null, '可选的角色卡'), poolBox),
        h('div', null, h('h3', null, '已选参会者'), emptyBox, list)),
      h('label', { for: 'moderator' }, '主持人'),
      moderator,
      h('p', null, submit));
    renderAttendees();
    return form;
  }

  async function load() {
    let data;
    try {
      data = await getEntries();
    } catch (e) {
      if (!alive) return;
      clear(body);
      showMessage('error', e && e.message ? e.message : '请求失败');
      return;
    }
    if (!alive) return;
    clear(body);
    const entries = data && Array.isArray(data.entries) ? data.entries : [];
    const agents = data && Array.isArray(data.agents) ? data.agents.filter((a) => a && typeof a.name === 'string') : [];
    if (!entries.some((e) => e && e.entry === MEETING_ENTRY)) {
      body.appendChild(h('p', { id: 'start-missing' }, '这个服务里没有会议入口（meeting.zs）'));
      return;
    }
    body.appendChild(buildForm(agents));
  }

  load();

  return { destroy() { alive = false; } };
}
