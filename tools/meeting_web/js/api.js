export class ApiError extends Error {
  constructor(message, status = 0, errors = []) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.errors = errors;
  }
}

async function request(path, init) {
  let resp;
  try {
    resp = await window.fetch('../api/' + path, init);
  } catch (e) {
    throw new ApiError('连不上服务：' + (e && e.message ? e.message : String(e)), 0, []);
  }
  let data = null;
  try {
    data = await resp.json();
  } catch (e) {
    data = null;
  }
  if (!resp.ok) {
    const msg = data && typeof data === 'object' && typeof data.error === 'string' && data.error
      ? data.error : `请求失败（HTTP ${resp.status}）`;
    const errors = data && Array.isArray(data.errors) ? data.errors : [];
    throw new ApiError(msg, resp.status, errors);
  }
  if (data === null) throw new ApiError(`请求失败（HTTP ${resp.status}）`, resp.status, []);
  return data;
}

export function apiGet(path) {
  return request(path);
}

export function apiPost(path, body) {
  return request(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

export async function listRuns() {
  return (await apiGet('runs')).runs;
}

export function getRun(name) {
  return apiGet('run?name=' + encodeURIComponent(name));
}

export function getEntries() {
  return apiGet('entries');
}

export async function startMeeting(vars) {
  const r = await apiPost('start', { entry: 'meeting.zs', mode: 'auto', vars });
  return { name: r.name, status: r.status };
}

// 启动别的流程（会后「交给流程」）：entry 是入口脚本名，vars 是它「# 参数：」声明的参数
export async function startRun(entry, vars) {
  const r = await apiPost('start', { entry, mode: 'auto', vars });
  return { name: r.name, status: r.status };
}

export async function submitResult(name, step, result) {
  const r = await apiPost('submit', { name, step, result });
  return r.status;
}
