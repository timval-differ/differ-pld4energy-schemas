// @ts-check
/*
 * Requests to the NOMAD API, with the user's session (the GUI's cookie), and
 * to this dashboard's own API (api/spec, api/validate, api/archive, ...).
 */

import {API, DASHBOARD} from './config.js';
import {uploadPath} from './util.js';

/**
 * A request to the NOMAD API: the parsed JSON (or text) of the answer. An
 * error answer throws an Error with its `detail` and HTTP `status`.
 * @param {string} path e.g. '/uploads/<id>/raw/<path>'
 * @param {RequestInit & {headers?: Object<string, string>}} [options]
 */
export async function api(path, options = {}) {
  // Several NOMAD endpoints (creating an upload, writing raw files) only answer
  // in JSON when asked for exactly `application/json`.
  const headers = {Accept: 'application/json', ...(options.headers || {})};
  const response = await fetch(API + path, {credentials: 'same-origin', ...options, headers});
  let body = null;
  const text = await response.text();
  try {
    body = text ? JSON.parse(text) : null;
  } catch (e) {
    body = text;
  }
  if (!response.ok) {
    const detail = body && body.detail
      ? (typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail))
      : `HTTP ${response.status}`;
    const error = /** @type {Error & {status?: number}} */ (new Error(detail));
    error.status = response.status;
    throw error;
  }
  return body;
}

export async function dashboard(path, body) {
  const response = await fetch(DASHBOARD + path, {
    method: body === undefined ? 'GET' : 'POST',
    headers: body === undefined ? {} : {'Content-Type': 'application/json'},
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await response.text();
  let json = null;
  try {
    json = text ? JSON.parse(text) : null;
  } catch (e) {
    // E.g. an error page of a proxy.
  }
  if (!response.ok) {
    const detail = json && json.detail;
    throw new Error(detail
      ? (typeof detail === 'string' ? detail : JSON.stringify(detail))
      : `HTTP ${response.status}`);
  }
  if (json === null) throw new Error(`The dashboard sent no data (HTTP ${response.status}).`);
  return json;
}

/* The bytes of a raw file in an upload, e.g. an export to decode (charts.decodeExport). */
export async function rawFileBytes(uploadId, path) {
  const url = API + uploadPath(uploadId, 'raw', path);
  const response = await fetch(url, {credentials: 'same-origin'});
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.arrayBuffer();
}

export async function rawFileText(uploadId, path) {
  const url = API + uploadPath(uploadId, 'raw', path);
  const response = await fetch(url, {credentials: 'same-origin'});
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.text();
}

/**
 * Write an archive file. With `entryHash` (that of the entry as it was read),
 * NOMAD refuses with a 409 when the file was changed since.
 */
export async function putArchive(uploadId, fileName, archive, overwrite, entryHash = null) {
  return api(`${uploadPath(uploadId, 'raw')}?file_name=${encodeURIComponent(fileName)}`
    + `&overwrite_if_exists=${overwrite}&wait_for_processing=true`
    + (entryHash ? `&entry_hash=${encodeURIComponent(entryHash)}` : ''), {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(archive),
  });
}

/** The hash of an entry's raw file as NOMAD last processed it, or null. */
export async function entryHash(entryId) {
  const response = await api(`/entries/${encodeURIComponent(entryId)}/archive/query`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({required: {metadata: {entry_hash: '*'}}}),
  });
  const metadata = (((response || {}).data || {}).archive || {}).metadata || {};
  return typeof metadata.entry_hash === 'string' ? metadata.entry_hash : null;
}

/**
 * The `data` of a JSON archive file in an upload, or null if there is no such
 * file. A file that is not an archive throws: overwriting it would lose it.
 */
export async function readArchiveData(uploadId, path) {
  let archive;
  try {
    archive = await api(uploadPath(uploadId, 'raw', path));
  } catch (e) {
    if (e.status === 404) return null;
    throw e;
  }
  if (!archive || typeof archive !== 'object' || !archive.data || typeof archive.data !== 'object') {
    throw new Error(`${path} is not an archive file the dashboard can update.`);
  }
  return archive.data;
}

export async function readNomadDraft(uploadId, path) {
  try {
    return await api(uploadPath(uploadId, 'raw', path));
  } catch (e) {
    if (e.status === 404) return null;
    throw e;
  }
}

/**
 * Upload files into one folder of an upload in one request, never replacing
 * a file that is there (NOMAD then refuses the request). Waits for NOMAD to
 * process the upload, so the next write does not find it busy.
 * @param {string} uploadId
 * @param {string} folder
 * @param {{name: string, file: Blob}[]} files
 */
export async function putRawFiles(uploadId, folder, files) {
  const body = new FormData();
  for (const {name, file} of files) body.append('file', file, name);
  return api(`${uploadPath(uploadId, 'raw', folder)}?overwrite_if_exists=false&wait_for_processing=true`, {
    method: 'PUT', body,
  });
}

/** The names of the files in a folder of an upload; none if it does not exist. */
export async function folderFileNames(uploadId, folder) {
  try {
    const listing = await api(`${uploadPath(uploadId, 'rawdir', folder)}?page_size=1000`);
    return ((listing.directory_metadata || {}).content || []).filter((f) => f.is_file).map((f) => f.name);
  } catch (e) {
    if (e.status === 404) return [];
    throw e;
  }
}

/** Whether a file exists in an upload. */
export async function rawExists(uploadId, path) {
  try {
    await api(uploadPath(uploadId, 'rawdir', path));
    return true;
  } catch (e) {
    if (e.status === 404) return false;
    throw e;
  }
}
