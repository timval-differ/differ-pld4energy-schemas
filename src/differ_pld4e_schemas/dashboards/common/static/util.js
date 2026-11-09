// @ts-check
/* Small helpers of the dashboard scripts: no state, no DOM. */

export function uid() {
  return Math.random().toString(16).slice(2, 14);
}

export const pad = (n) => String(n).padStart(2, '0');

/*
 * The date (yyyy-mm-dd) and time (hh:mm) the clock of `timeZone`, an IANA
 * name such as the lab's 'Europe/Amsterdam', shows at moment `d`: run times
 * are on the lab's clock, whatever time zone this computer is set to.
 */
export function clockIn(timeZone, d = new Date()) {
  const format = new Intl.DateTimeFormat('en-CA', {
    timeZone, year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  });
  const parts = Object.fromEntries(format.formatToParts(d).map((p) => [p.type, p.value]));
  return {date: `${parts.year}-${parts.month}-${parts.day}`, time: `${parts.hour}:${parts.minute}`};
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

/*
 * The API path of a file or folder in an upload (`kind` 'raw' or 'rawdir'),
 * with every part encoded. Upload ids and paths come from drafts and forms
 * kept in uploads others can write to, so a part that would leave the folder
 * ('..') or change the request (?, #) is refused or encoded.
 */
export function uploadPath(uploadId, kind, path = '') {
  if (typeof uploadId !== 'string' || !/^[\w-]+$/.test(uploadId)) {
    throw new Error(`Not an upload id: ${uploadId}`);
  }
  const parts = path ? String(path).split('/') : [];
  if (parts.some((part) => part === '' || part === '.' || part === '..')) {
    throw new Error(`Not a path in the upload: ${path}`);
  }
  return `/uploads/${uploadId}/${kind}/` + parts.map(encodeURIComponent).join('/');
}

export function validUploadId(value) {
  return typeof value === 'string' && /^[\w-]+$/.test(value) ? value : null;
}

export function formatNumber(value) {
  if (value === null || value === undefined) return '–';
  return Number(value.toPrecision(6)).toString();
}
