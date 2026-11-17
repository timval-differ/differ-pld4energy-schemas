// @ts-check
/*
 * The publication dashboard: choose one of your uploads, export it on the
 * server and download the ZIP. The export runs in the background; the page
 * asks for its state every few seconds.
 *
 * NOMAD's session cookie is sent to NOMAD's API only, not to this dashboard,
 * so every request to the dashboard carries a signature token from the API
 * (valid for 10 s, so one is fetched per request).
 */

import {DASHBOARD} from '../../common/static/config.js';
import {api} from '../../common/static/nomad-api.js';

const POLL_MS = 3000;

const $ = (id) => /** @type {any} */ (document.getElementById(id));

function showBanner(text, kind = 'error') {
  const banner = $('banner');
  banner.textContent = text;
  banner.className = `banner ${kind}`;
  banner.hidden = !text;
}

function setStatus(...content) {
  $('status').replaceChildren(...content);
}

/**
 * A request to this dashboard's own API, as the logged-in user.
 * @param {string} path below api/exports
 * @param {RequestInit} [options]
 * @returns {Promise<Response>}
 */
async function exportsRequest(path, options = {}) {
  const {signature_token: token} = await api('/auth/signature_token');
  const response = await fetch(DASHBOARD + 'api/exports' + path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      Authorization: `Bearer ${token}`,
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = body && body.detail;
    throw new Error(typeof detail === 'string' ? detail : `HTTP ${response.status}`);
  }
  return response;
}

async function loadUploads() {
  try {
    const user = await api('/users/me');
    $('user').textContent = user.name || user.username || '';
  } catch (e) {
    showBanner(
      e.status === 401
        ? 'You are not logged in. Log in to NOMAD and reload this page.'
        : 'Could not reach the NOMAD API: ' + e.message,
    );
    return;
  }
  const result = await api('/uploads?order_by=upload_create_time&order=desc&page_size=200');
  const select = $('upload');
  const uploads = result.data || [];
  if (!uploads.length) {
    select.replaceChildren(new Option('You have no uploads.'));
    return;
  }
  select.replaceChildren(
    ...uploads.map((upload) => {
      const name = upload.upload_name || '(no name)';
      const published = upload.published ? ' (published)' : '';
      return new Option(`${name} — ${upload.upload_id}${published}`, upload.upload_id);
    }),
  );
  const wanted = new URLSearchParams(window.location.search).get('upload_id');
  if (wanted && uploads.some((upload) => upload.upload_id === wanted)) select.value = wanted;
  select.disabled = false;
  $('btn-export').disabled = false;
}

async function download(job) {
  const response = await exportsRequest(`/${job.job_id}/download`);
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  link.href = url;
  link.download = job.file_name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}

function showResult(job) {
  if (job.status === 'done') {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'btn btn-outlined';
    button.textContent = `Download ${job.file_name}`;
    button.addEventListener('click', () =>
      download(job).catch((e) => showBanner('The download failed: ' + e.message)),
    );
    setStatus(button);
  } else {
    // A failed export names every reference it could not resolve, one per line.
    const pre = document.createElement('pre');
    pre.className = 'problems';
    pre.textContent = job.error;
    setStatus('The export failed:', pre);
  }
}

async function exportUpload() {
  const button = $('btn-export');
  button.disabled = true;
  showBanner('');
  setStatus('Exporting…');
  let job = null;
  try {
    const response = await exportsRequest('', {
      method: 'POST',
      body: JSON.stringify({upload_id: $('upload').value}),
    });
    job = await response.json();
    // The server reports an export that runs too long as failed, so this ends.
    while (job.status === 'running') {
      await new Promise((resolve) => setTimeout(resolve, POLL_MS));
      job = await (await exportsRequest(`/${job.job_id}`)).json();
    }
    showResult(job);
  } catch (e) {
    setStatus('');
    showBanner(
      job
        ? 'Lost contact with the export, which may still be running: ' + e.message
        : 'The export could not be started: ' + e.message,
    );
  } finally {
    button.disabled = false;
  }
}

$('btn-export').addEventListener('click', exportUpload);
loadUploads().catch((e) => showBanner('Could not load your uploads: ' + e.message));
