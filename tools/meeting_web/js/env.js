export const MEETING_WORKFLOW = 'meeting_workflow';
export const MEETING_ENTRY = 'meeting.zs';

export function isWritable() {
  return !!window.document.querySelector('meta[name="trace-write"][content="1"]');
}

export function getMe() {
  const v = new URLSearchParams(window.location.search).get('me');
  return v && /^[A-Z][A-Z0-9_]*$/.test(v) ? v : 'HUMAN';
}

export function getPollMs() {
  const raw = new URLSearchParams(window.location.search).get('poll');
  if (raw === null || !/^-?\d+$/.test(raw.trim())) return 2000;
  return Math.max(100, parseInt(raw, 10));
}
