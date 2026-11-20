import { isWritable, getMe, getPollMs } from './env.js';
import { clear, showMessage, clearMessage } from './ui.js';
import * as listPage from './pages/list.js';
import * as startPage from './pages/start.js';
import * as roomPage from './pages/room.js';

export function parseHash(hash) {
  const hs = hash || '';
  if (hs === '#/new') return { page: 'new' };
  if (hs.startsWith('#/room/')) {
    const x = hs.slice('#/room/'.length);
    if (x) {
      try {
        return { page: 'room', params: { name: decodeURIComponent(x) } };
      } catch (e) {
        return { page: 'list' };
      }
    }
  }
  return { page: 'list' };
}

const PAGES = { list: listPage, new: startPage, room: roomPage };

const doc = window.document;
const env = { write: isWritable(), me: getMe(), pollMs: getPollMs() };
let current = null;

function setupTopbar() {
  const me = doc.getElementById('me-name');
  me.textContent = `我：${env.me}`;
  me.setAttribute('data-me', env.me);
  const badge = doc.getElementById('mode-badge');
  badge.setAttribute('data-mode', env.write ? 'write' : 'readonly');
  badge.textContent = env.write ? '可参与' : '只读';
  const nav = doc.getElementById('nav-new');
  if (env.write) nav.removeAttribute('hidden');
  else nav.setAttribute('hidden', '');
}

function route() {
  if (current) {
    try {
      current.destroy();
    } catch (e) {
      // 旧页面清理失败不影响切换
    }
    current = null;
  }
  clearMessage();
  const app = doc.getElementById('app');
  clear(app);
  const r = parseHash(window.location.hash);
  app.setAttribute('data-page', r.page);
  const navList = doc.getElementById('nav-list');
  const navNew = doc.getElementById('nav-new');
  if (r.page === 'new') {
    navNew.setAttribute('aria-current', 'page');
    navList.removeAttribute('aria-current');
  } else {
    navList.setAttribute('aria-current', 'page');
    navNew.removeAttribute('aria-current');
  }
  try {
    current = PAGES[r.page].mount(app, { params: r.params || {}, write: env.write, me: env.me, pollMs: env.pollMs });
  } catch (e) {
    current = null;
    clear(app);
    showMessage('error', '页面出错：' + (e && e.message ? e.message : String(e)));
  }
}

setupTopbar();
window.addEventListener('hashchange', route);
route();
