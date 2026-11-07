// @ts-check
/* Small helpers of the dashboard scripts: no state, no DOM. */

export function uid() {
  return Math.random().toString(16).slice(2, 14);
}

export const pad = (n) => String(n).padStart(2, '0');

export function localDate(d) {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function localTime(d) {
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/* The browser's UTC offset at a moment, e.g. '+01:00'. */
export function utcOffset(d) {
  const minutes = -d.getTimezoneOffset();
  const sign = minutes < 0 ? '-' : '+';
  return `${sign}${pad(Math.floor(Math.abs(minutes) / 60))}:${pad(Math.abs(minutes) % 60)}`;
}

/* NOMAD returns the start of the run in UTC; show it in local time. */
export function localizeRun(run) {
  if (!run || !run.start) return;
  const start = new Date(run.start);
  if (!Number.isNaN(start.getTime())) {
    run.date = localDate(start);
    run.time = localTime(start);
    run.utc_offset = utcOffset(start);
  }
  delete run.start;
}

export function fileNameFor(text) {
  return text.replace(/[^\w.-]/g, '_');
}

export function entryRef(uploadId, entryId) {
  return `../uploads/${uploadId}/archive/${entryId}#/data`;
}

export function uploadOfRef(ref) {
  const match = /^(?:\.\.\/)?uploads\/([^/]+)\//.exec(ref || '');
  return match ? match[1] : null;
}
