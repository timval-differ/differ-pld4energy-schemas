/*
 * Logbook dashboard (PLD logbook, sputter logbook).
 *
 * The form is built from the definition served by `api/spec` (see the spec.py
 * of each dashboard); its `client` part holds the texts and settings of the
 * page that differ between dashboards. The rules below mirror
 * common/rules.py so problems show while typing; the server validates again
 * before it builds the archive files. Everything that needs the user's NOMAD
 * session (uploads, searching entries, writing files) goes straight to the
 * NOMAD API, which accepts the GUI's Authorization cookie.
 *
 * The page loads this file as an ES module (strict mode, its own scope); it
 * imports the other scripts in this folder.
 */
import {makePdf} from './pdf.js';
import {createRules} from './rules.js';
import {uid, localDate, localTime, utcOffset, localizeRun, fileNameFor, entryRef} from './util.js';

const BASE = window.location.pathname.replace(/\/dashboards\/.*$/, '');
const API = BASE + '/api/v1';
const GUI = BASE + '/gui/v2';
const DASHBOARD = window.location.pathname.replace(/\/?$/, '/');
const DRAFT_VERSION = 1;
const INCH = 0.0254;

const app = {
  spec: null,
  form: null,
  edit: null, // {upload_id, entry_id, mainfile} of an opened logbook
  draft: null, // {upload_id, path, savedAt} of the draft kept in NOMAD
  // Upload holding the files of an opened logbook or draft. Its file fields
  // name files there, so the logbook is saved to it, overwritten or not.
  source: null,
  upload: '', // selected upload id, or '__new__'
  newUploadName: '',
  current: 'home', // 'home' (start page), a section key, or 'save'
  started: false, // whether the form holds a logbook being worked on
  user: null,
  uploads: [],
  refs: {target: [], sample: [], substrate: []},
  maintainer: false, // whether the user can edit the target and substrate database
  pendingFiles: {}, // form path -> File, uploaded on save
  touched: new Set(),
  shown: new Set(), // sections whose problems are all shown
  collapsed: new Set(), // collapsed step uids
  errors: [],
  rendered: [],
  saving: false,
  log: [],
  referencesLoadedAt: 0, // when targets and samples were last loaded (ms)
  dialogCancelled: null, // closes the open dialog as cancelled
};

// The rules read the form definition and the entries in NOMAD from the page's
// state when they run (see rules.js).
const {
  evaluate,
  fieldOptions,
  toNumber,
  compute,
  madeHere,
  sampleId,
  sampleName,
  isEmpty,
  sectionRequirement,
  validate,
  stepTimeWarnings,
  normalTime,
  validateDraft,
} = createRules(app);

/* ---------------------------------------------------------------- helpers */

/* Texts and settings of this dashboard (the spec's `client`). */
function client() {
  return app.spec.client;
}

/**
 * A new element: `attrs` become properties, attributes, or listeners (`on…`).
 * @template {keyof HTMLElementTagNameMap} K
 * @param {K} tag
 * @param {Object<string, any>} [attrs]
 * @param {...any} children nodes, text, or (nested) lists of them
 * @returns {HTMLElementTagNameMap[K]}
 */
function el(tag, attrs, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === 'class') node.className = value;
    else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else if (key in node && key !== 'list') node[key] = value;
    else node.setAttribute(key, value === true ? '' : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

/*
 * The API path of a file or folder in an upload (`kind` 'raw' or 'rawdir'),
 * with every part encoded. Upload ids and paths come from drafts and forms
 * kept in uploads others can write to, so a part that would leave the folder
 * ('..') or change the request (?, #) is refused or encoded.
 */
function uploadPath(uploadId, kind, path = '') {
  if (typeof uploadId !== 'string' || !/^[\w-]+$/.test(uploadId)) {
    throw new Error(`Not an upload id: ${uploadId}`);
  }
  const parts = path ? String(path).split('/') : [];
  if (parts.some((part) => part === '' || part === '.' || part === '..')) {
    throw new Error(`Not a path in the upload: ${path}`);
  }
  return `/uploads/${uploadId}/${kind}/` + parts.map(encodeURIComponent).join('/');
}

function escapeRegExp(text) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/*
 * Whether `name` is a logbook file this dashboard makes, mirroring
 * is_logbook_file in common/convert.py. Only such a file may be overwritten
 * when an opened logbook is saved; the server checks it again.
 */
function isLogbookFile(name) {
  const systems = (app.spec && app.spec.systems) || [];
  if (typeof name !== 'string' || !systems.length) return false;
  return new RegExp(`^(?:${systems.map(escapeRegExp).join('|')})`
    + '_\\d{4}-\\d{2}-\\d{2}_\\d{4}(?:_[\\p{L}\\p{N}\\p{M}_.-]+)?\\.archive\\.json$', 'u').test(name);
}

/*
 * The logbook a save may overwrite, or null. A draft is a file in an upload that
 * others may write to, so the logbook it names must be in the draft's own upload
 * (`uploadId`) and be one this dashboard makes; else the save would go into
 * another upload or overwrite another file.
 */
function checkedEdit(edit, uploadId) {
  if (!edit || typeof edit !== 'object') return null;
  if (typeof edit.upload_id !== 'string' || !/^[\w-]+$/.test(edit.upload_id)) return null;
  if (uploadId !== undefined && edit.upload_id !== uploadId) return null;
  if (!isLogbookFile(edit.mainfile)) return null;
  const entryId = typeof edit.entry_id === 'string' ? edit.entry_id : null;
  return {upload_id: edit.upload_id, entry_id: entryId, mainfile: edit.mainfile};
}

const UNVERIFIED_EDIT = 'It referred to a logbook that could not be verified, '
  + 'so saving stores it as a new logbook.';

function validUploadId(value) {
  return typeof value === 'string' && /^[\w-]+$/.test(value) ? value : null;
}

/* The upload the logbook is saved to whatever is chosen, or null. */
function formUpload() {
  return app.edit ? app.edit.upload_id : app.source;
}

async function api(path, options = {}) {
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
    const error = new Error(detail);
    error.status = response.status;
    throw error;
  }
  return body;
}

async function dashboard(path, body) {
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

function showBanner(message, kind, action) {
  const banner = document.getElementById('banner');
  banner.replaceChildren(el('span', {}, message));
  banner.className = 'banner' + (kind ? ' ' + kind : '');
  if (action) banner.append(el('button', {class: 'btn btn-text', type: 'button', onclick: action.run}, action.label));
  banner.append(el('button', {class: 'btn btn-text btn-icon', type: 'button', title: 'Close', onclick: () => { banner.hidden = true; }}, '✕'));
  banner.hidden = false;
}

/* ------------------------------------------------------------ form state */

function defaults(fields) {
  const values = {};
  for (const field of fields) {
    if ('default' in field) values[field.key] = field.default;
    else if (field.kind === 'bool') values[field.key] = false;
  }
  return values;
}

function section(key) {
  return app.spec.sections.find((s) => s.key === key);
}

/*
 * A new step of a variant with `prefill_from` starts with the values it shares
 * with the last step of that variant, e.g. a deposition step with the target,
 * target stage, gases and laser of the pre-ablation before it.
 */
function prefill(listSection, variantKey, list) {
  const variant = listSection.variants[variantKey];
  const source = [...(list || [])].reverse().find((item) => item.type === variant.prefill_from);
  if (!source) return {};
  const keys = new Set(listSection.variants[variant.prefill_from].fields.map((f) => f.key));
  const values = {};
  for (const field of variant.fields) {
    if (field.key === 'comments' || field.prefill === false || !keys.has(field.key)
        || isEmpty(source[field.key])) continue;
    values[field.key] = source[field.key];
  }
  return values;
}

/* A new step starts by default when the step before it ended. */
function startAfterPrevious(fields, list) {
  const previous = (list || [])[(list || []).length - 1];
  if (!previous || isEmpty(previous.end_time) || !fields.some((f) => f.key === 'start_time')) return {};
  return {start_time: previous.end_time};
}

function newItem(listSection, variantKey, list) {
  if (variantKey) {
    const fields = listSection.variants[variantKey].fields;
    return {
      uid: uid(), type: variantKey, ...defaults(fields),
      ...prefill(listSection, variantKey, list),
      ...startAfterPrevious(fields, list),
    };
  }
  return {uid: uid(), ...defaults(listSection.fields)};
}

function newForm() {
  const form = {recipe: null};
  for (const s of app.spec.sections) {
    if (s.kind === 'object') form[s.key] = defaults(s.fields);
    else if (s.kind === 'list' && s.min_items !== 0) form[s.key] = [newItem(s)];
    else form[s.key] = [];
  }
  const now = new Date();
  form.run.date = localDate(now);
  form.run.time = localTime(now);
  form.run.utc_offset = utcOffset(now);
  fillOperator(form);
  return form;
}

/*
 * A draft kept from an earlier version of the form: sections added since get
 * their defaults, the in-situ techniques (once one set per run) become one
 * measurement, and a file field that took one file now takes a list.
 */
function upgradeForm(form) {
  for (const s of app.spec.sections) {
    const value = form[s.key];
    if (s.kind === 'object') {
      if (!value || typeof value !== 'object') form[s.key] = defaults(s.fields);
    } else if (!Array.isArray(value)) {
      const filled = value && typeof value === 'object' && Object.values(value).some((v) => v === true);
      form[s.key] = filled ? [{uid: uid(), steps: [], ...value}] : [];
    }
    const items = s.kind === 'object' ? [form[s.key]] : form[s.key];
    for (const item of items) {
      const fields = s.kind === 'variant_list' ? (s.variants[item.type] || {fields: []}).fields : s.fields;
      for (const field of fields) {
        if (field.kind !== 'files') continue;
        // Renamed from `..._file`, which held one file.
        const old = field.key.slice(0, -1);
        if (isEmpty(item[field.key]) && typeof item[old] === 'string') item[field.key] = [item[old]];
        if (typeof item[field.key] === 'string') item[field.key] = [item[field.key]];
        delete item[old];
      }
    }
  }
  return form;
}

function fillOperator(form) {
  if (!app.user || !form.run) return;
  if (!form.run.operator_name) form.run.operator_name = app.user.name || app.user.username || null;
  if (!form.run.operator_email) form.run.operator_email = app.user.email || null;
}

function errorsFor(prefix) {
  return app.errors.filter((e) => e.path === prefix || e.path.startsWith(prefix + '.'));
}

let draftTimer = null;
function changed() {
  app.started = true;
  app.errors = validate(app.form, app.spec);
  refresh();
  clearTimeout(draftTimer);
  draftTimer = setTimeout(saveDraft, 400);
}

/* Kept in this browser as a safeguard; see saveDraftToNomad for drafts on NOMAD. */
function saveDraft() {
  try {
    localStorage.setItem(client().draft_key, JSON.stringify({
      form: app.form, edit: app.edit, draft: app.draft, source: app.source, upload: app.upload,
      pending: Object.keys(app.pendingFiles), savedAt: new Date().toISOString(),
    }));
    document.getElementById('draft-status').textContent = 'Kept in this browser at '
      + new Date().toLocaleTimeString();
  } catch (e) {
    document.getElementById('draft-status').textContent = 'The form could not be kept in this browser.';
  }
}

function loadDraft() {
  try {
    const draft = JSON.parse(localStorage.getItem(client().draft_key) || 'null');
    if (!draft || !draft.form || !draft.form.run) return null;
    return draft;
  } catch (e) {
    return null;
  }
}

function clearDraft() {
  try {
    localStorage.removeItem(client().draft_key);
  } catch (e) {
    /* storage unavailable */
  }
}

/*
 * Files chosen but not uploaded yet are lost on reload; ask for them again.
 * Files already in the upload (also those added in the NOMAD GUI) are kept.
 */
function dropPendingFiles(form, pendingPaths) {
  let dropped = 0;
  // From the end, so the positions of the files still to drop stay valid.
  const paths = [...(pendingPaths || [])].sort((a, b) => {
    const [pa, pb] = [a, b].map((p) => Number(p.split('.').pop()));
    return pb - pa;
  });
  for (const path of paths) {
    const parts = path.split('.');
    const last = parts.pop();
    const container = formAt(form, parts);
    if (Array.isArray(container) && container[Number(last)] !== undefined) {
      container.splice(Number(last), 1);
      dropped += 1;
    } else if (container && container[last]) {
      // Kept by an earlier version of the page, for a field of one file.
      container[last] = null;
      dropped += 1;
    }
  }
  return dropped;
}

/* The value at a form path given as parts, e.g. ['in_situ', '0', 'files']. */
function formAt(form, parts) {
  let value = form;
  for (const part of parts) {
    if (value === null || value === undefined) return undefined;
    value = value[Array.isArray(value) ? Number(part) : part];
  }
  return value;
}

/* ------------------------------------------------------- NOMAD lookups */

async function loadUser() {
  try {
    app.user = await api('/users/me');
    document.getElementById('user').textContent = app.user.name || app.user.username || '';
    fillOperator(app.form);
  } catch (e) {
    app.user = null;
    showBanner(
      e.status === 401
        ? 'You are not logged in. Log in to NOMAD and reload this page to load targets and save logbooks.'
        : 'Could not reach the NOMAD API: ' + e.message,
      'error',
    );
  }
}

async function searchEntries(qualifiedNames, required, {owner = 'visible', pageSize = 1000, uploadId = null} = {}) {
  const query = {'section_defs.definition_qualified_name:any': qualifiedNames};
  if (uploadId) query.upload_id = uploadId;
  const body = {
    owner,
    query,
    pagination: {page_size: pageSize, order_by: 'entry_create_time', order: 'desc'},
  };
  if (required) {
    body.required = required;
    return (await api('/entries/archive/query', {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
    })).data || [];
  }
  body.required = {include: ['entry_id', 'upload_id', 'entry_name', 'mainfile', 'entry_create_time']};
  return (await api('/entries/query', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
  })).data || [];
}

/*
 * The page is read from disk on every request, the dashboard's Python code only
 * when NOMAD starts. After an update without a restart, this page would run
 * against an old form definition.
 */
function checkServerVersion() {
  const meta = document.querySelector('meta[name="script-version"]');
  const page = meta && meta.content;
  if (!page || page.startsWith('{{') || page === app.spec.script_version) return true;
  showBanner('The dashboard was updated, but NOMAD still runs the previous version of it. '
    + 'Restart NOMAD (stop it and run "poe start" again), then reload this page.', 'error');
  return false;
}

/*
 * Targets and substrates are only chosen from the target and substrate
 * database: one upload that maintainers edit (as its coauthors) and everyone
 * else can only view (as reviewers).
 */
function databaseUpload() {
  return app.spec.database_upload_id || null;
}

async function loadDatabaseAccess() {
  app.maintainer = false;
  const database = databaseUpload();
  if (!app.user || !database) return;
  try {
    const upload = (await api(`/uploads/${encodeURIComponent(database)}`)).data || {};
    const userId = app.user.user_id;
    if ((upload.writers || []).includes(userId)) {
      app.maintainer = true;
      return;
    }
    const groups = upload.writer_groups || [];
    if (!groups.length) return;
    const mine = (await api(`/groups?user_id=${encodeURIComponent(userId)}&page_size=1000`)).data || [];
    app.maintainer = mine.some((g) => groups.includes(g.group_id));
  } catch (e) {
    showBanner('Could not open the target and substrate database (upload '
      + `${database}): ${e.message}. Ask a maintainer to add you to it as a reviewer.`, 'error');
  }
}

async function loadReferences() {
  if (!app.user) return;
  const names = app.spec.reference_sections;
  const database = databaseUpload();
  if (!database) {
    showBanner('The target and substrate database is not set up in NOMAD yet, so no '
      + 'targets or substrates can be chosen. Ask a maintainer.', 'error');
  }
  try {
    const targets = !names.target || !database ? [] : await searchEntries([names.target], {
      data: '*', metadata: {entry_name: '*', mainfile: '*'},
    }, {uploadId: database});
    app.refs.target = targets.filter(Boolean).map((t) => {
      const data = (t.archive && t.archive.data) || {};
      const metadata = (t.archive && t.archive.metadata) || {};
      const file = metadata.mainfile ? metadata.mainfile.replace(/\.archive\.(json|yaml)$/, '') : t.entry_id;
      return {
        ref: entryRef(t.upload_id, t.entry_id),
        name: data.name || data.material || metadata.entry_name || `${file} (no material entered)`,
        material: data.material || null,
        retired: data.in_stock === false,
        info: [data.lab_id && `ID ${data.lab_id}`, data.material,
          data.diameter && `${Number((data.diameter / INCH).toPrecision(3))}"`,
          data.shape === 'Rectangular' && data.length && data.width && `${formatNumber(data.length * 1000)} x ${formatNumber(data.width * 1000)} mm`,
          data.manufacturer, data.purchase_date && String(data.purchase_date).slice(0, 10),
          data.in_stock === false ? 'out of stock' : null]
          .filter(Boolean).join(' · ') || 'This target has no material, size, manufacturer or purchase date yet.',
      };
    }).sort((a, b) => a.name.localeCompare(b.name));
  } catch (e) {
    showBanner('Could not load the targets: ' + e.message, 'error');
  }
  try {
    const samples = !names.sample ? [] : await searchEntries([names.sample], {
      data: {sample_id: '*', name: '*', system: '*'}, metadata: {entry_name: '*', mainfile: '*'},
    });
    app.refs.sample = samples.filter(Boolean).map((s) => {
      const data = (s.archive && s.archive.data) || {};
      const metadata = (s.archive && s.archive.metadata) || {};
      return {
        ref: entryRef(s.upload_id, s.entry_id),
        name: data.sample_id || metadata.entry_name || metadata.mainfile,
        sampleId: data.sample_id || null,
        sampleName: data.name || null,
        info: [data.name, data.system].filter(Boolean).join(' · '),
      };
    }).sort((a, b) => b.name.localeCompare(a.name));
  } catch (e) {
    showBanner('Could not load the samples: ' + e.message, 'error');
  }
  try {
    const substrates = !names.substrate || !database ? [] : await searchEntries([names.substrate], {
      data: {name: '*', material: '*', size: '*', supplier: '*', in_stock: '*'},
      metadata: {entry_name: '*', mainfile: '*'},
    }, {uploadId: database});
    app.refs.substrate = substrates.filter(Boolean).map((s) => {
      const data = (s.archive && s.archive.data) || {};
      const metadata = (s.archive && s.archive.metadata) || {};
      return {
        ref: entryRef(s.upload_id, s.entry_id),
        name: data.name || data.material || metadata.entry_name || metadata.mainfile,
        material: data.material || null,
        size: data.size || null,
        retired: data.in_stock === false,
        info: [data.material, data.size, data.supplier, data.in_stock === false ? 'out of stock' : null]
          .filter(Boolean).join(' · '),
      };
    }).sort((a, b) => a.name.localeCompare(b.name));
  } catch (e) {
    showBanner('Could not load the substrates: ' + e.message, 'error');
  }
  refresh();
}

/* Copy values of a chosen entry into the form, e.g. the material of a target. */
function copyFromRef(field, local, value) {
  if (!field.ref_copy) return;
  const found = app.refs[field.reference].find((r) => r.ref === value) || {};
  for (const [key, attribute] of Object.entries(field.ref_copy)) local[key] = found[attribute] ?? null;
}

async function loadUploads() {
  if (!app.user) return;
  try {
    const response = await api('/uploads?is_published=false&page_size=200&order_by=upload_create_time&order=desc');
    app.uploads = response.data || [];
  } catch (e) {
    app.uploads = [];
  }
}

function refName(kind, ref) {
  const found = app.refs[kind].find((r) => r.ref === ref);
  return found ? found.name : ref;
}

/* ------------------------------------------------------------ rendering */

function choiceOptions(field, local) {
  const root = app.form;
  if (field.kind === 'target_choice') {
    return (root.targets || []).filter((t) => t.target).map((t) => ({
      value: t.target,
      label: refName('target', t.target) + (t.target_number ? ` (target ${t.target_number})` : ''),
    }));
  }
  if (field.kind === 'sample_choice') {
    return (root.samples || []).map((s, index) => {
      if (madeHere(s)) {
        return {value: `new:${s.uid}`, label: sampleId(s, root) || sampleName(s, root) || `Sample ${index + 1}`};
      }
      return s.sample ? {value: s.sample, label: refName('sample', s.sample)} : null;
    }).filter(Boolean);
  }
  if (field.kind === 'reference') {
    // Entries that are out of stock are not offered, unless already chosen here.
    return app.refs[field.reference]
      .filter((r) => !r.retired || r.ref === local[field.key])
      .map((r) => ({value: r.ref, label: r.name + (r.retired ? ' (out of stock)' : '')}));
  }
  return fieldOptions(field, local, root).map((o) => ({value: o, label: o}));
}

function emptyChoiceText(field) {
  if (field.options_by) return field.options_by.empty_text || 'Choose the other options first';
  if (field.kind === 'target_choice') return 'Select targets under Targets first';
  if (field.kind === 'sample_choice') return 'Add samples under Samples first';
  if (field.kind === 'reference') return 'None found in NOMAD';
  return 'No options available';
}

const CHOICE_KINDS = ['select', 'reference', 'target_choice', 'sample_choice'];

function fillSelect(select, options, value, field) {
  const current = value === undefined || value === null ? '' : value;
  const items = [el('option', {value: ''}, options.length ? 'Choose…' : emptyChoiceText(field))];
  for (const option of options) items.push(el('option', {value: option.value}, option.label));
  if (current !== '' && !options.some((o) => o.value === current)) {
    items.push(el('option', {value: current}, `${current} (not available)`));
  }
  select.replaceChildren(...items);
  select.value = current;
}

function formatNumber(value) {
  if (value === null || value === undefined) return '–';
  return Number(value.toPrecision(6)).toString();
}

function control(field, local, path) {
  const id = 'f-' + path.replace(/\./g, '-');
  const set = (value) => {
    local[field.key] = value;
    copyFromRef(field, local, value);
    app.touched.add(path);
    changed();
  };
  const unitLabel = field.unit_label || field.unit;
  let input = null;
  let body = null;
  switch (field.kind) {
    case 'bool': {
      input = el('input', {type: 'checkbox', id, checked: Boolean(local[field.key]), onchange: (e) => set(e.target.checked)});
      body = el('label', {class: 'switch', for: id}, input, el('span', {class: 'track'}), el('span', {}, field.label));
      return {body, input, labelInside: true};
    }
    case 'textarea':
      input = el('textarea', {id, value: local[field.key] || '', oninput: (e) => set(e.target.value)});
      return {body: input, input};
    case 'select':
    case 'reference':
    case 'target_choice':
    case 'sample_choice': {
      input = el('select', {id, onchange: (e) => set(e.target.value || null)});
      body = el('div', {class: 'input-wrap'}, input);
      return {body, input};
    }
    case 'rows':
      return rowsControl(field, local, path, id);
    case 'computed': {
      input = el('div', {class: 'computed', id});
      return {body: input, input};
    }
    case 'files': {
      // Several files of one format; each is uploaded on save (see uploadPendingFiles).
      const files = el('div', {class: 'file-list'});
      input = el('input', {
        type: 'file', id, multiple: true, accept: field.accept || undefined,
        onchange: (e) => {
          const values = local[field.key] || (local[field.key] = []);
          for (const file of e.target.files) {
            app.pendingFiles[`${path}.${values.length}`] = file;
            values.push(file.name);
          }
          input.value = '';
          app.touched.add(path);
          changed();
        },
      });
      input.hidden = true;
      const choose = el('button', {type: 'button', class: 'btn btn-outlined', onclick: () => input.click()}, 'Add files');
      // Exported data files are plotted (see renderFileCharts).
      const charts = field.chart ? el('div', {class: 'file-charts'}) : null;
      body = el('div', {class: 'rows'}, input, files, choose, charts);
      return {body, input, fileList: files, charts};
    }
    case 'step_choice': {
      // One checkbox per process step, rebuilt by refresh when the steps change.
      input = el('div', {class: 'step-choices', id});
      return {body: input, input};
    }
    case 'date':
      input = el('input', {type: field.kind, id, value: local[field.key] || '', onchange: (e) => set(e.target.value || null)});
      return {body: el('div', {class: 'input-wrap'}, input), input};
    case 'time':
      // Text, not <input type="time">: that shows AM/PM in some browser languages.
      input = el('input', {
        type: 'text', id, inputMode: 'numeric', placeholder: 'hh:mm (24 h)', maxLength: 5,
        autocomplete: 'off', value: local[field.key] || '',
        oninput: (e) => set(e.target.value || null),
        onchange: (e) => { e.target.value = normalTime(e.target.value); set(e.target.value || null); },
      });
      return {body: el('div', {class: 'input-wrap'}, input), input};
    default: {
      const numeric = field.kind === 'number' || field.kind === 'integer';
      input = el('input', {
        type: 'text', id, inputMode: numeric ? (field.kind === 'integer' ? 'numeric' : 'decimal') : undefined,
        placeholder: field.placeholder || '', value: local[field.key] ?? '', autocomplete: 'off',
        oninput: (e) => set(e.target.value === '' ? null : e.target.value),
      });
      body = el('div', {class: 'input-wrap' + (unitLabel ? ' has-unit' : '')}, input,
        unitLabel ? el('span', {class: 'unit'}, unitLabel) : null);
      return {body, input};
    }
  }
}

/* A repeating sub-section (e.g. the films of a sample): one small grid per row. */
function rowsControl(field, local, path, id) {
  const rows = local[field.key] || (local[field.key] = []);
  const body = el('div', {class: 'rows', id});
  rows.forEach((row, index) => {
    const line = el('div', {class: 'row-line'});
    renderFields(line, field.columns, row, `${path}.${index}`);
    line.append(el('button', {
      type: 'button', class: 'btn btn-text btn-icon btn-danger', title: `Remove ${field.item_label || 'row'}`,
      onclick: () => { rows.splice(index, 1); changed(); render(); },
    }, '✕'));
    body.append(line);
  });
  body.append(el('button', {
    type: 'button', class: 'btn btn-text',
    onclick: () => { rows.push(defaults(field.columns)); changed(); render(); },
  }, `+ Add ${field.item_label || 'row'}`));
  return {body, input: body};
}

function renderFields(container, fields, local, path) {
  let group = null;
  let grid = null;
  const newGrid = (title) => {
    grid = el('div', {class: 'grid'});
    if (title) {
      const fieldset = el('fieldset', {}, el('legend', {}, title), grid);
      container.append(fieldset);
      grid.fieldset = fieldset;
    } else {
      container.append(grid);
    }
  };
  for (const field of fields) {
    if (grid === null || field.group !== group) {
      group = field.group;
      newGrid(group);
    }
    const fieldPath = `${path}.${field.key}`;
    const made = control(field, local, fieldPath);
    const error = el('div', {class: 'error'});
    const wide = ['textarea', 'files', 'rows', 'step_choice'].includes(field.kind);
    const classes = 'field' + (wide ? ' wide' : '') + (field.row_start ? ' row-start' : '');
    const helper = el('div', {class: 'helper'}, field.help || '');
    const wrap = el('div', {class: classes, 'data-path': fieldPath},
      made.labelInside ? null : el('label', {for: made.input.id, class: field.required ? 'required' : ''},
        field.label),
      made.body,
      helper,
      error);
    grid.append(wrap);
    app.rendered.push({field, local, path: fieldPath, wrap, error, grid, helper, ...made});
  }
}

/* ------------------------------------------------- charts of data files */

/*
 * Exported data files (e.g. RHEED ROI intensities, MIC curvature) are plotted
 * as soon as they are added, from the file in the browser; once saved, from
 * NOMAD on request. The field's `chart` (FILE_CHARTS in spec.py) says how to
 * read the file and what to plot. The NOMAD entry plots the same data.
 */
const SERIES_COLORS = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948'];
const CHART_POINTS = 1000;
const SVG = 'http://www.w3.org/2000/svg';

/* Header (or null) and columns of an exported text file, as in in_situ.read_columns. */
function readColumns(text, delimiter) {
  let header = null;
  let columns = null;
  const lines = text.split(/\r?\n/);
  for (let number = 1; number <= lines.length; number++) {
    const line = lines[number - 1];
    if (!line.trim()) continue;
    const parts = delimiter ? line.split(delimiter).map((p) => p.trim()) : line.trim().split(/\s+/);
    const values = parts.map((p) => (p === '' ? NaN : Number(p)));
    if (values.some(Number.isNaN)) {
      if (columns) throw new Error(`line ${number} is not numbers`);
      header = parts;
      continue;
    }
    if (!columns) columns = values.map(() => []);
    if (values.length !== columns.length) {
      throw new Error(`line ${number} has ${values.length} columns instead of ${columns.length}`);
    }
    values.forEach((v, i) => columns[i].push(v));
  }
  if (!columns || columns.length < 2) throw new Error('no columns of data found');
  return {header, columns};
}

/* The mean of each block of samples, keeping at most `points`. */
function blockMean(values, points) {
  const size = Math.ceil(values.length / points);
  if (size <= 1) return values;
  const means = [];
  for (let start = 0; start < values.length; start += size) {
    const block = values.slice(start, start + size);
    means.push(block.reduce((a, b) => a + b, 0) / block.length);
  }
  return means;
}

/* The plots of a chart definition: [{title, yTitle, x, series: [{name, values}]}]. */
function chartPlots(chart, {header, columns}) {
  const name = (column) => column.split('(')[0].trim().toLowerCase();
  const x = blockMean(columns[0], CHART_POINTS);
  const plots = chart.plots.map((plot) => {
    let series;
    if (plot.columns === null) {
      series = columns.slice(1).map((values, i) => ({name: plot.name.replace('{n}', i + 1), values}));
    } else {
      series = plot.columns.map((column, i) => {
        const index = (header || []).findIndex((h) => name(h) === column.toLowerCase());
        return index < 0 ? null : {name: plot.names[i], values: columns[index]};
      }).filter(Boolean);
    }
    series = series.map((s) => ({...s, values: blockMean(s.values, CHART_POINTS)}));
    return {title: plot.title, yTitle: plot.y_title, x, series};
  }).filter((plot) => plot.series.length);
  if (!plots.length) throw new Error('none of the expected columns found');
  return plots;
}

function svgEl(tag, attrs, ...children) {
  const node = document.createElementNS(SVG, tag);
  for (const [key, value] of Object.entries(attrs || {})) node.setAttribute(key, value);
  node.append(...children);
  return node;
}

/* About `count` round tick values within min..max, or (outward) around it. */
function niceTicks(min, max, count = 5, outward = false) {
  if (!(max > min)) return [min];
  const raw = (max - min) / count;
  const power = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 5, 10].map((f) => f * power).find((s) => s >= raw);
  const ticks = [];
  const first = (outward ? Math.floor(min / step) : Math.ceil(min / step)) * step;
  const last = outward ? Math.ceil(max / step) * step : max;
  for (let v = first; v <= last + step * 1e-9; v += step) {
    ticks.push(Number(v.toPrecision(12)));
  }
  return ticks;
}

/*
 * A line chart of one plot against the time, with a crosshair tooltip. It is
 * drawn at the width it gets (and redrawn when that changes), so that its text
 * keeps the size of the page's text instead of being scaled with the chart.
 */
function lineChart(plot, fileName) {
  const H = 300;
  const m = {left: 72, right: 20, top: 12, bottom: 52};
  const {x, series} = plot;
  const color = (i) => SERIES_COLORS[i % SERIES_COLORS.length];
  const all = series.flatMap((s) => s.values).filter(Number.isFinite);
  let [yMin, yMax] = [Math.min(...all), Math.max(...all)];
  if (yMin === yMax) [yMin, yMax] = [yMin - 1, yMax + 1];
  const yTicks = niceTicks(yMin, yMax, 5, true);
  [yMin, yMax] = [yTicks[0], yTicks[yTicks.length - 1]];
  const [xMin, xMax] = [x[0], x[x.length - 1]];
  const sy = (v) => H - m.bottom - ((v - yMin) / (yMax - yMin)) * (H - m.top - m.bottom);
  const tooltip = el('div', {class: 'chart-tooltip', hidden: true});

  const draw = (W) => {
    const sx = (v) => m.left + ((v - xMin) / (xMax - xMin || 1)) * (W - m.left - m.right);
    const svg = svgEl('svg', {width: W, height: H, viewBox: `0 0 ${W} ${H}`, class: 'chart-svg', role: 'img',
      'aria-label': `${plot.title} against time, ${fileName}`});
    for (const t of yTicks) {
      svg.append(svgEl('line', {x1: m.left, x2: W - m.right, y1: sy(t), y2: sy(t), class: 'chart-grid'}),
        svgEl('text', {x: m.left - 8, y: sy(t), class: 'chart-tick', 'text-anchor': 'end', 'dominant-baseline': 'middle'},
          formatNumber(t)));
    }
    // About one time tick per 110 px.
    for (const t of niceTicks(xMin, xMax, Math.max(2, Math.floor((W - m.left - m.right) / 110)))) {
      svg.append(svgEl('line', {x1: sx(t), x2: sx(t), y1: H - m.bottom, y2: H - m.bottom + 5, class: 'chart-axis'}),
        svgEl('text', {x: sx(t), y: H - m.bottom + 20, class: 'chart-tick', 'text-anchor': 'middle'}, formatNumber(t)));
    }
    const middle = (m.top + H - m.bottom) / 2;
    svg.append(
      svgEl('line', {x1: m.left, x2: W - m.right, y1: H - m.bottom, y2: H - m.bottom, class: 'chart-axis'}),
      svgEl('text', {x: (m.left + W - m.right) / 2, y: H - 8, class: 'chart-label', 'text-anchor': 'middle'}, 'Time (s)'),
      svgEl('text', {x: 16, y: middle, class: 'chart-label', 'text-anchor': 'middle',
        transform: `rotate(-90 16 ${middle})`}, plot.yTitle));
    series.forEach((s, i) => {
      let d = '';
      let pen = 'M';
      s.values.forEach((v, j) => {
        if (!Number.isFinite(v)) { pen = 'M'; return; }
        d += `${pen}${sx(x[j]).toFixed(1)} ${sy(v).toFixed(1)}`;
        pen = 'L';
      });
      svg.append(svgEl('path', {d, class: 'chart-line', stroke: color(i)}));
    });

    // Hover: a crosshair at the nearest time, a dot per series, and a tooltip.
    const cross = svgEl('line', {y1: m.top, y2: H - m.bottom, class: 'chart-cross', visibility: 'hidden'});
    const dots = series.map((s, i) => svgEl('circle', {r: 4, class: 'chart-dot', fill: color(i), visibility: 'hidden'}));
    const hit = svgEl('rect', {x: m.left, y: m.top, width: W - m.left - m.right, height: H - m.top - m.bottom,
      fill: 'transparent'});
    svg.append(cross, ...dots, hit);
    hit.addEventListener('pointerleave', () => {
      tooltip.hidden = true;
      for (const node of [cross, ...dots]) node.setAttribute('visibility', 'hidden');
    });
    hit.addEventListener('pointermove', (e) => {
      const px = e.clientX - svg.getBoundingClientRect().left;
      const time = xMin + ((px - m.left) / (W - m.left - m.right)) * (xMax - xMin);
      let j = x.findIndex((v) => v >= time);
      if (j < 0) j = x.length - 1;
      if (j > 0 && time - x[j - 1] < x[j] - time) j -= 1;
      cross.setAttribute('x1', sx(x[j]));
      cross.setAttribute('x2', sx(x[j]));
      cross.setAttribute('visibility', 'visible');
      series.forEach((s, i) => {
        const shown = Number.isFinite(s.values[j]);
        dots[i].setAttribute('visibility', shown ? 'visible' : 'hidden');
        if (shown) { dots[i].setAttribute('cx', sx(x[j])); dots[i].setAttribute('cy', sy(s.values[j])); }
      });
      tooltip.replaceChildren(el('div', {class: 'chart-tooltip-time'}, `${formatNumber(x[j])} s`),
        ...series.map((s, i) => el('div', {class: 'chart-tooltip-row'},
          el('span', {class: 'chart-swatch', style: `background:${color(i)}`}),
          el('span', {}, s.name), el('span', {class: 'chart-tooltip-value'}, formatNumber(s.values[j])))));
      tooltip.hidden = false;
      tooltip.style.left = `${sx(x[j])}px`;
      tooltip.classList.toggle('flip', sx(x[j]) > W / 2);
    });
    return svg;
  };

  let width = 0;
  const frame = el('div', {class: 'chart-frame'}, draw(720), tooltip);
  new ResizeObserver(() => {
    const now = Math.round(frame.clientWidth);
    if (!now || now === width) return;
    width = now;
    tooltip.hidden = true;
    frame.firstChild.replaceWith(draw(Math.max(now, 320)));
  }).observe(frame);

  const legend = series.length > 1 ? el('div', {class: 'chart-legend'}, ...series.map((s, i) => el('span', {class: 'chart-key'},
    el('span', {class: 'chart-swatch', style: `background:${color(i)}`}), s.name))) : null;
  return el('figure', {class: 'chart'},
    el('figcaption', {}, el('span', {class: 'chart-title'}, plot.title), el('span', {class: 'muted small'}, fileName)),
    legend, frame);
}

/* Parsed plots by File (added here) or by path (saved in NOMAD), read once. */
const chartCache = new Map();

async function rawFileText(uploadId, path) {
  const url = API + uploadPath(uploadId, 'raw', path);
  const response = await fetch(url, {credentials: 'same-origin'});
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.text();
}

async function plotFile(box, chart, key, fileName, read) {
  box.replaceChildren(el('span', {class: 'muted small'}, `Reading ${fileName}…`));
  if (!chartCache.has(key)) {
    // Let the message show before a large file is parsed.
    chartCache.set(key, new Promise((resolve) => setTimeout(resolve)).then(read)
      .then((text) => chartPlots(chart, readColumns(text, chart.delimiter))));
  }
  try {
    const plots = await chartCache.get(key);
    box.replaceChildren(...plots.map((plot) => lineChart(plot, fileName)));
  } catch (error) {
    chartCache.delete(key);
    box.replaceChildren(el('span', {class: 'chart-error'}, `Could not plot ${fileName}: ${error.message}`));
  }
}

/* The charts of the files of a field, redrawn only when its files change. */
function renderFileCharts(r, value) {
  const files = value || [];
  const pending = files.map((_, index) => app.pendingFiles[`${r.path}.${index}`]);
  const key = files.join('|') + '|' + pending.map(Boolean).join();
  if (r.charts.dataset.key === key) return;
  r.charts.dataset.key = key;
  r.charts.replaceChildren(...files.map((name, index) => {
    const fileName = String(name).split('/').pop();
    const box = el('div', {class: 'file-chart'});
    const file = pending[index];
    if (file) {
      plotFile(box, r.field.chart, file, fileName, () => file.text());
    } else if (formUpload()) {
      const source = formUpload();
      const cacheKey = `${source}/${name}`;
      const plot = () => plotFile(box, r.field.chart, cacheKey, fileName, () => rawFileText(source, name));
      if (chartCache.has(cacheKey)) plot();
      else box.append(el('button', {type: 'button', class: 'btn btn-text', onclick: plot}, `Plot ${fileName}`));
    }
    return box;
  }));
}

/* Remove one file of a `files` field; files still to upload keep their place. */
function removeFile(local, key, path, index) {
  local[key].splice(index, 1);
  const pending = {};
  for (const [pendingPath, file] of Object.entries(app.pendingFiles)) {
    if (!pendingPath.startsWith(`${path}.`)) {
      pending[pendingPath] = file;
      continue;
    }
    const position = Number(pendingPath.slice(path.length + 1));
    if (position !== index) pending[`${path}.${position > index ? position - 1 : position}`] = file;
  }
  app.pendingFiles = pending;
  app.touched.add(path);
  changed();
}

function renderStepChoices(r) {
  const chosen = r.local[r.field.key] || [];
  const steps = app.form.steps || [];
  const toggle = (stepUid, on) => {
    const current = (r.local[r.field.key] || []).filter((v) => v !== stepUid);
    // Kept in the order of the steps.
    r.local[r.field.key] = on
      ? steps.map((s) => s.uid).filter((v) => v === stepUid || current.includes(v)) : current;
    app.touched.add(r.path);
    changed();
  };
  const boxes = steps.map((s, index) => {
    const id = `${r.input.id}-${s.uid}`;
    return el('label', {class: 'step-choice', for: id},
      el('input', {type: 'checkbox', id, checked: chosen.includes(s.uid), onchange: (e) => toggle(s.uid, e.target.checked)}),
      itemTitle(`steps.${index}`));
  });
  // A step that was removed after it was chosen.
  if (chosen.some((v) => !steps.some((s) => s.uid === v))) {
    boxes.push(el('button', {
      type: 'button', class: 'btn btn-text',
      onclick: () => toggle(chosen.find((v) => !steps.some((s) => s.uid === v)), false),
    }, 'Remove a step that no longer exists'));
  }
  r.input.replaceChildren(...(boxes.length ? boxes : [el('span', {class: 'muted'}, 'Add process steps first')]));
}

/* Whether a ticked in-situ technique of a measurement has no data file yet. */
function awaitingData(technique, measurement) {
  return section('in_situ').fields
    .filter((f) => f.technique === technique)
    .every((f) => isEmpty(measurement[f.key]));
}

/* E.g. ['Measurement 1: RHEED (KSA 400)']. */
function awaitingTechniques(form) {
  if (!section('in_situ')) return [];
  const techniques = section('in_situ').fields.filter((f) => f.kind === 'bool');
  return (Array.isArray(form.in_situ) ? form.in_situ : []).flatMap((measurement, index) => techniques
    .filter((f) => measurement[f.key] && awaitingData(f.key, measurement))
    .map((f) => `Measurement ${index + 1}: ${f.group}`));
}

function sectionShown(path) {
  return app.shown.has(path.split('.')[0]);
}

function refresh() {
  const root = app.form;
  const byPath = new Map();
  for (const error of app.errors) if (!byPath.has(error.path)) byPath.set(error.path, error.message);
  // Warnings show at once, without waiting for the field to be touched.
  const warnings = new Map(stepTimeWarnings(root).map((w) => [w.path, w.message]));
  const grids = new Set();
  for (const r of app.rendered) {
    const visible = evaluate(r.field.visible_if, r.local, root);
    r.wrap.hidden = !visible;
    grids.add(r.grid);
    const kind = r.field.kind;
    const value = r.local[r.field.key];
    if (CHOICE_KINDS.includes(kind) && document.activeElement !== r.input) {
      fillSelect(r.input, choiceOptions(r.field, r.local), value, r.field);
    }
    if (kind === 'computed') {
      const computed = compute(r.field.compute, r.local, root);
      r.input.textContent = computed === null ? '–'
        : (typeof computed === 'number' ? `${formatNumber(computed)} ${r.field.unit_label || ''}` : computed);
    }
    if (kind === 'files') {
      r.fileList.replaceChildren(...(value || []).map((name, index) => el('div', {class: 'file-row'},
        el('span', {class: 'file-name'}, String(name).split('/').pop()),
        el('span', {class: 'file-pending'}, app.pendingFiles[`${r.path}.${index}`] ? 'uploaded on save' : ''),
        el('button', {
          type: 'button', class: 'btn btn-text btn-icon btn-danger', title: 'Remove file',
          onclick: () => removeFile(r.local, r.field.key, r.path, index),
        }, '✕'))));
      if (!(value || []).length) r.fileList.append(el('span', {class: 'muted'}, 'No files added'));
      if (r.charts && visible) renderFileCharts(r, value);
    }
    if (kind === 'step_choice') renderStepChoices(r);
    if (r.field.required && r.field.required_if) {
      const label = r.wrap.querySelector('label');
      if (label) label.classList.toggle('required', evaluate(r.field.required_if, r.local, root));
    }
    if (r.field.reference) {
      const found = app.refs[r.field.reference].find((t) => t.ref === value);
      r.helper.textContent = found ? found.info : (r.field.help || '');
    }
    if (r.path.startsWith('in_situ.') && kind === 'bool') {
      r.helper.textContent = value && awaitingData(r.field.key, r.local)
        ? 'Awaiting data: add the files now or later, by opening the saved logbook.' : '';
    }
    const message = visible ? byPath.get(r.path) : null;
    const show = message && (app.touched.has(r.path) || sectionShown(r.path));
    const warning = !show && visible ? warnings.get(r.path) : null;
    r.wrap.classList.toggle('invalid', Boolean(show));
    r.wrap.classList.toggle('warning', Boolean(warning));
    r.error.textContent = show ? message : (warning || '');
  }
  for (const grid of grids) {
    if (grid.fieldset) grid.fieldset.hidden = [...grid.children].every((c) => c.hidden);
  }
  for (const box of document.querySelectorAll('[data-list-errors]')) {
    const key = box.getAttribute('data-list-errors');
    const messages = app.errors.filter((e) => e.path === key).map((e) => e.message);
    box.hidden = !messages.length || !sectionShown(key);
    box.textContent = messages.join(' ');
  }
  for (const badge of document.querySelectorAll('[data-item-errors]')) {
    const count = errorsFor(badge.getAttribute('data-item-errors')).length;
    badge.textContent = count ? `${count} to do` : 'complete';
    badge.className = 'badge ' + (count ? 'todo' : 'done');
  }
  for (const title of document.querySelectorAll('[data-item-title]')) {
    title.textContent = itemTitle(title.getAttribute('data-item-title'));
  }
  renderNav();
  renderChips();
  if (app.current === 'save') updateSaveState();
}

function itemTitle(path) {
  const [key, index] = path.split('.');
  const item = app.form[key][Number(index)];
  const s = section(key);
  if (!item) return '';
  if (key === 'steps') return `${Number(index) + 1}. ${s.variants[item.type].label}`;
  if (key === 'targets') {
    return `${s.item_label} ${Number(index) + 1}` + (item.target ? `: ${refName('target', item.target)}` : '');
  }
  if (key === 'samples') {
    const name = sampleId(item, app.form) || sampleName(item, app.form);
    return `${s.item_label} ${Number(index) + 1}` + (name ? `: ${name}` : '');
  }
  if (key === 'in_situ') {
    const field = s.fields.find((f) => f.kind === 'sample_choice');
    const sample = field && displayValue(field, item);
    return `${s.item_label} ${Number(index) + 1}` + (sample ? `: ${sample}` : '');
  }
  return `${s.item_label} ${Number(index) + 1}`;
}

function renderChips() {
  const system = app.form.run.system;
  const chip = document.getElementById('system-chip');
  chip.hidden = !system;
  chip.textContent = system || '';
  const mode = document.getElementById('mode-chip');
  mode.hidden = !app.edit && !app.draft;
  mode.textContent = app.edit ? 'Saved logbook' : (app.draft ? 'Draft' : '');
  mode.title = app.edit ? `Editing ${app.edit.mainfile}; saving overwrites it.` : (app.draft ? app.draft.path : '');
  const home = app.current === 'home';
  chip.hidden = home || !system;
  mode.hidden = home || mode.hidden;
  document.getElementById('btn-draft-save').hidden = home;
  document.getElementById('btn-pdf').hidden = home;
  document.getElementById('btn-home').hidden = home;
}

function navSections() {
  return [...app.spec.sections.map((s) => ({key: s.key, title: s.title})), {key: 'save', title: 'Review and save'}];
}

const REQUIREMENT_NOTES = {
  none: 'Not needed for these process steps: it is only logged when a step needs it. '
    + 'What you enter here is not saved.',
  optional: 'Optional for these process steps: fill it in if it applies.',
};

function requirementNote(level) {
  return level === 'none' && client().requirement_note ? client().requirement_note : REQUIREMENT_NOTES[level];
}

function renderNav() {
  const nav = document.getElementById('nav');
  const items = navSections().map((s, index) => {
    const level = s.key === 'save' ? 'required' : sectionRequirement(section(s.key), app.form);
    const count = s.key === 'save' ? app.errors.length : errorsFor(s.key).length;
    let state = s.key === 'save' ? (count ? '' : 'done') : (count ? 'todo' : 'done');
    if (level === 'none') state = 'skipped';
    return el('li', {}, el('button', {
      type: 'button', class: (s.key === app.current ? 'active' : '') + (level === 'none' ? ' not-needed' : ''),
      onclick: () => go(s.key),
      title: level === 'required' ? '' : requirementNote(level),
    }, el('span', {class: 'nav-index ' + state}, state === 'done' ? '✓' : (state === 'skipped' ? '–' : String(index + 1))),
    el('span', {class: 'nav-title'}, s.title,
      level === 'none' ? el('span', {class: 'nav-note'}, 'not needed') : null,
      level === 'optional' ? el('span', {class: 'nav-note'}, 'optional') : null),
    count && s.key !== 'save' ? el('span', {class: 'nav-count'}, String(count)) : null));
  });
  nav.replaceChildren(...items);
  const keys = navSections().map((s) => s.key);
  const position = keys.indexOf(app.current);
  document.getElementById('btn-prev').disabled = position <= 0;
  const next = document.getElementById('btn-next');
  next.hidden = position >= keys.length - 1;
}


function go(key, focusPath) {
  if (key !== app.current && (key === 'targets' || key === 'samples') && Date.now() - app.referencesLoadedAt > 30000) {
    app.referencesLoadedAt = Date.now();
    loadReferences();
  }
  app.current = key;
  window.history.replaceState(null, '', key === 'home' ? window.location.pathname : '#' + key);
  render();
  window.scrollTo(0, 0);
  if (focusPath) {
    const target = document.querySelector(`[data-path="${focusPath}"]`);
    if (target) {
      const item = target.closest('.item-card');
      if (item && item.classList.contains('collapsed')) item.querySelector('.item-header').click();
      target.scrollIntoView({block: 'center'});
      const input = target.querySelector('input, select, textarea');
      if (input) input.focus();
    }
  }
}

function render() {
  app.rendered = [];
  const container = document.getElementById('section');
  container.replaceChildren();
  document.body.classList.toggle('home', app.current === 'home');
  if (app.current === 'home') renderHome(container);
  else if (app.current === 'save') renderSave(container);
  else {
    const s = section(app.current);
    if (s.kind === 'object') renderObject(container, s);
    else if (s.kind === 'list') renderList(container, s);
    else renderSteps(container, s);
  }
  refresh();
}

/* ------------------------------------------------------------ start page */

function runLabel(form) {
  const run = (form && form.run) || {};
  const when = [run.date, run.time].filter(Boolean).join(' ');
  return [run.system || 'No system chosen yet', when, run.name].filter(Boolean).join(' · ');
}

/* Starting or opening another logbook replaces the one in the form. */
async function confirmReplace() {
  return !app.started || askConfirm('Replace the logbook in the form?',
    `Replace the logbook you are working on (${runLabel(app.form)})? `
    + 'What is not saved as a draft or logbook is lost.', 'Replace');
}

function entryList(id, empty) {
  return el('ul', {class: 'pick-list home-list', id}, el('li', {class: 'muted'}, empty));
}

function fillEntryList(id, entries, empty, onPick) {
  const list = document.getElementById(id);
  if (!list) return; // the start page was left meanwhile
  list.replaceChildren(...(entries.length ? entries.map((e) => el('li', {}, el('button', {
    type: 'button', onclick: () => onPick(e),
  }, e.title, el('span', {class: 'sub'}, e.sub)))) : [el('li', {class: 'muted'}, empty)]));
}

function renderHome(container) {
  const intro = el('div', {class: 'card'},
    el('h1', {}, client().title),
    el('p', {class: 'section-intro'}, client().intro),
    el('div', {class: 'btn-row'},
      el('button', {type: 'button', class: 'btn btn-contained', onclick: () => newLogbook(false)}, 'New logbook'),
      app.started ? el('button', {type: 'button', class: 'btn btn-outlined', onclick: () => go('run')},
        'Continue current logbook') : null));
  if (app.started) {
    const where = app.edit ? `Saved logbook ${app.edit.mainfile}`
      : (app.draft ? `Draft ${app.draft.path}` : 'Not saved yet: kept in this browser only');
    intro.append(el('div', {class: 'info'}, el('strong', {}, 'Current logbook: '), runLabel(app.form), el('br'), where));
  }
  const drafts = el('div', {class: 'card'},
    el('h2', {}, 'Drafts'),
    el('p', {class: 'muted small'}, 'Unfinished runs kept in your uploads, to continue on any computer. '
      + 'They only count as logged once the logbook is saved.'),
    entryList('home-drafts', app.user ? 'Looking for drafts…' : 'Log in to NOMAD to see your drafts.'));
  const recent = el('div', {class: 'card'},
    el('h2', {}, 'Recent logbooks'),
    entryList('home-recent', app.user ? 'Loading…' : 'Log in to NOMAD to see your logbooks.'),
    el('div', {class: 'btn-row'},
      el('button', {type: 'button', class: 'btn btn-text', onclick: openLogbookDialog}, 'Find a logbook…')));
  container.append(intro, el('div', {class: 'home-grid'}, drafts, recent));
  if (!app.user) return;
  findDrafts().then(
    (entries) => fillEntryList('home-drafts', entries, 'No drafts.', (e) => openNomadDraft(e.uploadId, e.path, e.stored)),
    (e) => fillEntryList('home-drafts', [], 'Could not look for drafts: ' + e.message),
  );
  searchEntries(Object.values(app.spec.logbook_sections), null, {owner: 'user', pageSize: 8}).then(
    (entries) => fillEntryList('home-recent', entries.map(logbookItem), 'No logbooks yet.', openLogbook),
    (e) => fillEntryList('home-recent', [], 'Could not load logbooks: ' + e.message),
  );
}

function sectionHeader(s, intro) {
  const level = sectionRequirement(s, app.form);
  return [
    el('h1', {}, s.title),
    intro ? el('p', {class: 'section-intro'}, intro) : null,
    level === 'required' ? null : el('div', {class: 'info requirement-' + level}, requirementNote(level)),
  ];
}

function renderObject(container, s) {
  const card = el('div', {class: 'card'}, sectionHeader(s));
  if (s.intro) card.append(el('div', {class: 'info'}, s.intro));
  if (s.key === 'run' && app.form.recipe) {
    card.append(el('div', {class: 'info'}, 'The process steps were loaded from a recipe.'));
  }
  renderFields(card, s.fields, app.form[s.key], s.key);
  container.append(card);
}

function moveItem(list, index, offset) {
  const target = index + offset;
  if (target < 0 || target >= list.length) return;
  [list[index], list[target]] = [list[target], list[index]];
  changed();
  render();
}

function removeItem(list, index) {
  list.splice(index, 1);
  changed();
  render();
}

function itemCard(s, list, index, bodyFill, options = {}) {
  const item = list[index];
  const path = `${s.key}.${index}`;
  const collapsed = options.collapsible && app.collapsed.has(item.uid);
  const body = el('div', {class: 'item-body'});
  const header = el('div', {class: 'item-header'},
    el('h2', {'data-item-title': path}, itemTitle(path)),
    el('span', {class: 'badge', 'data-item-errors': path}),
    options.movable ? el('button', {type: 'button', class: 'btn btn-text btn-icon', title: 'Move up', disabled: index === 0, onclick: (e) => { e.stopPropagation(); moveItem(list, index, -1); }}, '↑') : null,
    options.movable ? el('button', {type: 'button', class: 'btn btn-text btn-icon', title: 'Move down', disabled: index === list.length - 1, onclick: (e) => { e.stopPropagation(); moveItem(list, index, 1); }}, '↓') : null,
    el('button', {type: 'button', class: 'btn btn-text btn-danger', onclick: (e) => { e.stopPropagation(); removeItem(list, index); }}, 'Remove'));
  const card = el('div', {class: 'item-card' + (collapsed ? ' collapsed' : '')}, header, body);
  if (options.collapsible) {
    header.style.cursor = 'pointer';
    header.title = 'Show or hide';
    header.addEventListener('click', () => {
      card.classList.toggle('collapsed');
      if (card.classList.contains('collapsed')) app.collapsed.add(item.uid);
      else app.collapsed.delete(item.uid);
    });
  }
  bodyFill(body, item, path);
  return card;
}

/* "How many": adds or removes new samples at the end of the list. */
function countControl(s, list) {
  const count = list.filter(madeHere).length;
  const input = el('input', {type: 'number', min: 0, max: 99, value: count, class: 'count-input'});
  const apply = async () => {
    const wanted = Math.max(0, Math.min(99, Number(input.value) || 0));
    let made = list.filter(madeHere);
    while (made.length < wanted) {
      list.push(newItem(s));
      made = list.filter(madeHere);
    }
    const extra = made.slice(wanted);
    const filled = extra.filter((item) => item.substrate || (item.layers || []).length || item.comments);
    if (filled.length && !(await askConfirm('Remove samples?',
      `Remove ${extra.length} sample(s), of which ${filled.length} filled in?`, 'Remove'))) {
      input.value = made.length;
      return;
    }
    for (const item of extra) list.splice(list.indexOf(item), 1);
    changed();
    render();
  };
  return el('div', {class: 'count-row'},
    el('label', {}, `Number of new and external samples`), input,
    el('button', {type: 'button', class: 'btn btn-outlined', onclick: apply}, 'Set'));
}

function renderList(container, s) {
  const intro = s.intro || (s.key === 'targets'
    ? 'Select the targets that are in the system and enter their target number for this run.' : '');
  const card = el('div', {class: 'card'}, sectionHeader(s, intro), el('div', {class: 'list-error', 'data-list-errors': s.key}));
  const list = app.form[s.key];
  if (s.count_control) card.append(countControl(s, list));
  if (s.key === 'in_situ' && awaitingTechniques(app.form).length) {
    card.append(el('div', {class: 'info'},
      `Awaiting data: ${awaitingTechniques(app.form).join(', ')}. The logbook can be saved without them.`));
  }
  list.forEach((item, index) => {
    card.append(itemCard(s, list, index, (body, it, path) => renderFields(body, s.fields, it, path)));
  });
  const actions = el('div', {class: 'btn-row'}, el('button', {
    type: 'button', class: 'btn btn-outlined',
    onclick: () => { list.push(newItem(s)); changed(); render(); },
  }, `+ Add ${s.item_label.toLowerCase()}`));
  // Only maintainers add targets and substrates, in the database upload.
  // Without a `target_entry` targets are only added in NOMAD itself.
  const database = databaseUpload();
  const usesDatabase = s.key === 'targets' || s.key === 'samples';
  if (app.maintainer && database) {
    if (s.key === 'samples') {
      actions.append(el('button', {type: 'button', class: 'btn btn-text', onclick: newSubstrateDialog}, 'New substrate in the database'));
    }
    if (client().target_entry && usesDatabase) {
      actions.append(el('button', {type: 'button', class: 'btn btn-text', onclick: newTargetDialog}, 'New target in the database'));
    }
  }
  if (database && usesDatabase) {
    actions.append(el('a', {class: 'btn btn-text', href: `${GUI}/projects/${database}`, target: '_blank', rel: 'noopener'},
      app.maintainer ? 'Edit the database in NOMAD' : 'View the database in NOMAD'));
  }
  actions.append(el('button', {type: 'button', class: 'btn btn-text', onclick: loadReferences}, 'Refresh lists'));
  card.append(actions);
  if (usesDatabase && !app.maintainer) {
    card.append(el('p', {class: 'muted small'}, 'Targets and substrates are chosen from the target and '
      + 'substrate database. Is one missing? Ask a maintainer to add it.'
      + (s.key === 'samples' ? ' An external sample on a substrate that is not in the database: '
        + 'leave the substrate empty and describe it under Substrate details.' : '')));
  }
  container.append(card);
}

function renderSteps(container, s) {
  const card = el('div', {class: 'card'}, sectionHeader(s, s.intro),
    el('div', {class: 'list-error', 'data-list-errors': s.key}));
  const system = app.form.run.system;
  if (!system) {
    card.append(el('div', {class: 'info'}, 'Choose the PVD system under Run first: the fields of the steps depend on it.'));
  } else if ((client().system_notes || {})[system]) {
    card.append(el('div', {class: 'info'}, client().system_notes[system]));
  }
  const list = app.form.steps;
  list.forEach((item, index) => {
    card.append(itemCard(s, list, index,
      (body, it, path) => renderFields(body, s.variants[it.type].fields, it, path),
      {movable: true, collapsible: true}));
  });
  const actions = el('div', {class: 'btn-row'});
  for (const [key, variant] of Object.entries(s.variants)) {
    actions.append(el('button', {
      type: 'button', class: 'btn btn-outlined',
      onclick: () => { list.push(newItem(s, key, list)); changed(); render(); },
    }, `+ ${variant.label}`));
  }
  actions.append(el('button', {type: 'button', class: 'btn btn-text', onclick: recipeDialog},
    'Load steps from a recipe…'));
  card.append(actions);
  container.append(card);
}

/* -------------------------------------------------------------- dialogs */

function openDialog(title, content) {
  document.getElementById('dialog-title').textContent = title;
  document.getElementById('dialog-cancel').textContent = 'Cancel';
  document.getElementById('dialog-body').replaceChildren(...[content].flat());
  document.getElementById('dialog').hidden = false;
}

function closeDialog() {
  document.getElementById('dialog').hidden = true;
  const cancelled = app.dialogCancelled;
  app.dialogCancelled = null;
  if (cancelled) cancelled();
}

/*
 * A yes/no question in the page's own dialog, resolving to true for yes.
 * (window.confirm() does nothing in the sandboxed frame NOMAD shows us in.)
 */
function askConfirm(title, question, yes, no = 'Cancel') {
  return new Promise((resolve) => {
    const answer = (value) => {
      app.dialogCancelled = null;
      closeDialog();
      resolve(value);
    };
    openDialog(title, [
      el('p', {}, question),
      el('div', {class: 'btn-row'},
        el('button', {type: 'button', class: 'btn btn-contained', onclick: () => answer(true)}, yes)),
    ]);
    document.getElementById('dialog-cancel').textContent = no;
    app.dialogCancelled = () => resolve(false);
  });
}

function pickList(entries, onPick) {
  const filter = el('input', {type: 'text', placeholder: 'Filter…', class: 'filter'});
  const list = el('ul', {class: 'pick-list'});
  const fill = () => {
    const text = filter.value.toLowerCase();
    const shown = entries.filter((e) => (e.title + ' ' + e.sub).toLowerCase().includes(text));
    list.replaceChildren(...(shown.length ? shown.map((e) => el('li', {}, el('button', {
      type: 'button', onclick: () => onPick(e),
    }, e.title, el('span', {class: 'sub'}, e.sub)))) : [el('li', {class: 'muted'}, 'Nothing found.')]));
  };
  filter.addEventListener('input', fill);
  fill();
  return [el('div', {class: 'input-wrap'}, filter), list];
}

function logbookItem(e) {
  const created = String(e.entry_create_time || '').slice(0, 10);
  if (e.entry_name) return {entry: e, title: e.entry_name, sub: `${e.mainfile} · ${created}`};
  return {entry: e, title: String(e.mainfile).replace(/\.archive\.(json|yaml)$/, ''), sub: `saved ${created}`};
}

async function logbookEntries(systems) {
  const names = systems.map((s) => app.spec.logbook_sections[s]);
  return (await searchEntries(names)).map(logbookItem);
}

async function fetchLogbook(entry) {
  const response = await api(`/entries/${encodeURIComponent(entry.entry_id)}/archive`);
  return response.data.archive.data;
}

async function openLogbook(picked) {
  if (!(await confirmReplace())) return;
  try {
    const data = await fetchLogbook(picked.entry);
    const form = await dashboard('api/form-from-archive', {data, mode: 'edit'});
    localizeRun(form.run);
    app.form = {recipe: null, ...form};
    // A logbook not made by this dashboard (e.g. a hand-written .archive.yaml)
    // is saved as a new file instead of being overwritten.
    app.edit = checkedEdit({upload_id: picked.entry.upload_id, entry_id: picked.entry.entry_id, mainfile: picked.entry.mainfile});
    app.source = validUploadId(picked.entry.upload_id);
    app.draft = null;
    app.upload = picked.entry.upload_id;
    app.pendingFiles = {};
    app.touched.clear();
    app.shown.clear();
    closeDialog();
    changed();
    go('run');
    const awaiting = awaitingTechniques(app.form);
    showBanner(`Opened ${picked.title}. `
      + (app.edit ? 'Saving overwrites this logbook.'
        : 'Its file name is not one this dashboard writes (e.g. a hand-written or older logbook), '
          + 'so saving stores it as a new logbook in the same upload.')
      + (awaiting.length ? ` Awaiting in-situ data: ${awaiting.join(', ')}.` : ''));
  } catch (e) {
    showBanner('Could not open the logbook: ' + e.message, 'error');
  }
}

async function openLogbookDialog() {
  if (!app.user) return showBanner('Log in to NOMAD to open logbooks.', 'error');
  openDialog('Open logbook', el('p', {class: 'muted'}, 'Loading…'));
  try {
    const entries = await logbookEntries(app.spec.systems);
    openDialog('Open logbook', pickList(entries, openLogbook));
  } catch (e) {
    openDialog('Open logbook', el('p', {class: 'error'}, 'Could not load logbooks: ' + e.message));
  }
}

async function recipeDialog() {
  if (!app.user) return showBanner('Log in to NOMAD to load recipes.', 'error');
  const system = app.form.run.system;
  if (!system) {
    go('run');
    return showBanner('Choose the PVD system first: a recipe must be from the same system.', 'error');
  }
  openDialog('Load recipe', el('p', {class: 'muted'}, 'Loading…'));
  try {
    const entries = (await logbookEntries([system]))
      .filter((e) => !app.edit || e.entry.entry_id !== app.edit.entry_id);
    openDialog(`Load recipe (${system})`, [
      el('p', {class: 'muted'}, 'The process steps of the chosen logbook are added after the current steps. '
        + 'Samples are not copied: the steps apply to the samples of this run.'),
      ...pickList(entries, async (picked) => {
        try {
          const data = await fetchLogbook(picked.entry);
          const recipe = await dashboard('api/form-from-archive', {data, mode: 'recipe'});
          const hasTargets = app.form.targets.some((t) => t.target);
          if (!hasTargets) app.form.targets = recipe.targets;
          app.form.steps.push(...recipe.steps);
          app.form.recipe = entryRef(picked.entry.upload_id, picked.entry.entry_id);
          closeDialog();
          changed();
          go('steps');
          showBanner(`Added ${recipe.steps.length} steps from ${picked.title}`
            + (hasTargets ? '.' : ' and its targets.') + ' Check the targets'
            + (client().all_samples.includes(system) ? '.' : ' and choose the sample of each deposition step.'));
        } catch (e) {
          showBanner('Could not load the recipe: ' + e.message, 'error');
        }
      }),
    ]);
  } catch (e) {
    openDialog('Load recipe', el('p', {class: 'error'}, 'Could not load logbooks: ' + e.message));
  }
}

function uploadSelect(onChange) {
  const select = el('select', {onchange: (e) => { app.upload = e.target.value; onChange && onChange(); }});
  const options = [el('option', {value: ''}, 'Choose an upload…'),
    el('option', {value: '__new__'}, '+ New upload')];
  for (const upload of app.uploads) {
    options.push(el('option', {value: upload.upload_id},
      `${upload.upload_name || 'Unnamed upload'} (${String(upload.upload_create_time || '').slice(0, 10)})`));
  }
  select.replaceChildren(...options);
  select.value = app.upload;
  return select;
}

async function ensureUpload() {
  if (formUpload()) return formUpload();
  if (app.upload && app.upload !== '__new__') return app.upload;
  if (app.upload === '__new__') {
    const name = encodeURIComponent(app.newUploadName || client().upload_name);
    const response = await api(`/uploads?upload_name=${name}`, {method: 'POST'});
    app.upload = response.upload_id;
    await loadUploads();
    return app.upload;
  }
  throw new Error('Choose an upload first.');
}

async function putArchive(uploadId, fileName, archive, overwrite) {
  return api(`${uploadPath(uploadId, 'raw')}?file_name=${encodeURIComponent(fileName)}`
    + `&overwrite_if_exists=${overwrite}&wait_for_processing=true`, {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(archive),
  });
}

/*
 * Add an entry to one of the databases (targets, substrates) without leaving
 * the form. `place` puts the new entry into the form, e.g. into the first
 * empty target row.
 */
function newEntryDialog({kind, noun, intro, fields, build, place}) {
  if (!app.user) return showBanner(`Log in to NOMAD to add ${noun}s.`, 'error');
  const database = databaseUpload();
  if (!app.maintainer || !database) {
    return showBanner(`Only maintainers add ${noun}s to the target and substrate database.`, 'error');
  }
  const values = Object.fromEntries(fields.map((f) => [f.key, '']));
  const message = el('p', {class: 'error'});
  const input = (f) => el('div', {class: 'field'},
    el('label', {class: f.required ? 'required' : ''}, f.label),
    el('div', {class: 'input-wrap'}, el('input', {type: f.type || 'text', placeholder: f.placeholder || '',
      oninput: (e) => { values[f.key] = e.target.value.trim(); }})));
  const create = el('button', {type: 'button', class: 'btn btn-contained', onclick: async () => {
    const missing = fields.find((f) => f.required && !values[f.key]);
    if (missing) {
      message.textContent = `Enter the ${missing.label.toLowerCase()}.`;
      return;
    }
    create.disabled = true;
    try {
      const uploadId = database;
      const data = {m_def: app.spec.reference_sections[kind], ...build(values)};
      const fileName = fileNameFor(`${kind}_${data.name || data.material}_${uid().slice(0, 6)}`) + '.archive.json';
      const response = await putArchive(uploadId, fileName, {data}, false);
      const entry = response.processing && response.processing.entry_id;
      await loadReferences();
      if (entry) place(entryRef(uploadId, entry), data);
      closeDialog();
      changed();
      render();
      showBanner(`${noun[0].toUpperCase() + noun.slice(1)} ${data.name || data.material} added to the database.`, 'success');
    } catch (e) {
      message.textContent = `Could not create the ${noun}: ${e.message}`;
      create.disabled = false;
    }
  }}, `Create ${noun}`);
  openDialog(`New ${noun} in the database`, [
    el('p', {class: 'muted'}, intro),
    el('p', {class: 'muted small'}, `Saved in the target and substrate database (upload ${database}).`),
    el('div', {class: 'grid'}, ...fields.map(input)),
    message,
    el('div', {class: 'btn-row'}, create),
  ]);
}

function setReference(field, local, ref) {
  local[field.key] = ref;
  copyFromRef(field, local, ref);
}

function newTargetDialog() {
  newEntryDialog({
    kind: 'target',
    noun: 'target',
    intro: client().target_entry.intro,
    // A field with a `scale` is a number, multiplied into the schema's unit.
    fields: client().target_entry.fields,
    build: (v) => Object.fromEntries(client().target_entry.fields.map((f) => {
      const value = v[f.key];
      if (!value) return [f.key, null];
      if (f.type === 'date') return [f.key, value + 'T00:00:00+00:00'];
      if (f.scale) return [f.key, toNumber(value) === null ? null : toNumber(value) * f.scale];
      return [f.key, value];
    }).filter(([, value]) => value !== null)),
    place: (ref) => {
      const empty = app.form.targets.find((t) => !t.target);
      if (empty) empty.target = ref;
      else app.form.targets.push({...newItem(section('targets')), target: ref});
    },
  });
}

function newSubstrateDialog() {
  const samples = section('samples');
  newEntryDialog({
    kind: 'substrate',
    noun: 'substrate',
    intro: 'Creates a Substrate type entry: a kind of substrate that samples are made on, '
      + 'e.g. SrTiO3 10x10 mm. Its material is used in the sample names; NOMAD finds '
      + 'the samples by the elements of its chemical formula.',
    fields: [
      {key: 'material', label: 'Material', required: true, placeholder: 'e.g. SrTiO3'},
      {key: 'chemical_formula', label: 'Chemical formula', required: true,
        placeholder: 'e.g. SrTiO3 or Si, not a lab name'},
      {key: 'size', label: 'Size', placeholder: 'e.g. 10x10 mm or 1" with flat'},
      {key: 'name', label: 'Name (optional, defaults to material and size)'},
      {key: 'supplier', label: 'Supplier'},
    ],
    build: (v) => Object.fromEntries(Object.entries(v).filter(([, value]) => value)),
    place: (ref, data) => {
      const field = samples.fields.find((f) => f.key === 'substrate');
      const empty = app.form.samples.find((item) => madeHere(item) && !item.substrate);
      if (!empty) return;
      setReference(field, empty, ref);
      // In case the search does not list the new entry yet.
      empty.substrate_material = empty.substrate_material || data.material;
    },
  });
}

/* ---------------------------------------------------------------- save */

function describeError(error) {
  const [key, index, field] = error.path.split('.');
  const s = section(key);
  if (!s) return error.message;
  let where = s.title;
  if (index !== undefined && s.kind !== 'object') where += ` › ${itemTitle(`${key}.${index}`)}`;
  const fieldKey = s.kind === 'object' ? index : field;
  if (fieldKey) {
    let fields = s.fields;
    if (s.kind === 'variant_list') {
      const item = app.form.steps[Number(index)];
      fields = item && s.variants[item.type] ? s.variants[item.type].fields : [];
    }
    const f = (fields || []).find((x) => x.key === fieldKey);
    if (f) where += ` › ${f.group ? f.group + ' › ' : ''}${f.label}`;
  }
  return {where, message: error.message, section: key};
}

function renderSave(container) {
  const card = el('div', {class: 'card'}, el('h1', {}, 'Review and save'));
  const status = el('div', {id: 'save-status'});
  card.append(status);

  const where = el('div', {class: 'grid'});
  if (app.edit) {
    where.append(el('div', {class: 'field wide'}, el('span', {class: 'label'}, 'Saved to'),
      el('div', {class: 'computed'}, `${app.edit.mainfile} in upload ${app.edit.upload_id} (overwritten on save)`)));
  } else if (app.source) {
    where.append(el('div', {class: 'field wide'}, el('span', {class: 'label'}, 'Saved to'),
      el('div', {class: 'computed'}, `A new logbook in upload ${app.source}, which holds its files`)));
  } else {
    const nameField = el('div', {class: 'field', id: 'new-upload-name'},
      el('label', {}, 'Name of the new upload'),
      el('div', {class: 'input-wrap'}, el('input', {type: 'text', value: app.newUploadName,
        oninput: (e) => { app.newUploadName = e.target.value; }})));
    where.append(el('div', {class: 'field'}, el('label', {class: 'required'}, 'Upload'),
      el('div', {class: 'input-wrap'}, uploadSelect(() => { nameField.hidden = app.upload !== '__new__'; updateSaveState(); }))),
    nameField);
    nameField.hidden = app.upload !== '__new__';
  }
  card.append(where);

  const save = el('button', {type: 'button', class: 'btn btn-contained', id: 'btn-save', onclick: saveLogbook}, 'Save logbook to NOMAD');
  const draft = el('button', {type: 'button', class: 'btn btn-outlined', id: 'btn-save-draft', onclick: saveDraftToNomad}, 'Save draft');
  const pdf = el('button', {type: 'button', class: 'btn btn-text', onclick: exportPdf}, 'Export as PDF');
  card.append(el('div', {class: 'btn-row'}, save, draft, pdf));
  card.append(el('p', {class: 'muted small'}, 'A draft keeps an unfinished run in the upload so it can be '
    + 'continued on another computer. Drafts are not logbooks: only a complete, saved logbook counts as logged.'));
  card.append(el('ul', {class: 'log', id: 'save-log'}));
  container.append(card);
  renderLog();
}

function updateSaveState() {
  const status = document.getElementById('save-status');
  if (!status) return;
  if (app.errors.length) {
    const items = app.errors.map((error) => {
      const d = describeError(error);
      return el('li', {}, el('a', {onclick: () => { app.shown.add(d.section); go(d.section, error.path); }}, d.where),
        ' — ', d.message);
    });
    status.replaceChildren(el('div', {class: 'list-error'},
      `${app.errors.length} ${app.errors.length === 1 ? 'thing is' : 'things are'} still missing. `
      + 'The logbook can only be saved when it is complete.'),
    el('ul', {class: 'problems'}, items));
  } else {
    const awaiting = awaitingTechniques(app.form);
    status.replaceChildren(el('div', {class: 'banner success', style: 'margin: 8px 0 16px'},
      'Everything is filled in.' + (awaiting.length ? ` In-situ data still to come: ${awaiting.join(', ')}.` : '')));
  }
  const noUpload = !formUpload() && !app.draft && !app.upload;
  const reason = !app.user ? 'Log in to NOMAD first' : (noUpload ? 'Choose an upload' : '');
  const save = document.getElementById('btn-save');
  if (save) {
    save.disabled = app.saving || Boolean(app.errors.length) || Boolean(reason);
    save.title = reason;
  }
  const draft = document.getElementById('btn-save-draft');
  if (draft) {
    const draftErrors = validateDraft(app.form);
    draft.disabled = app.saving || Boolean(reason) || Boolean(draftErrors.length);
    draft.title = reason || draftErrors.map((e) => e.message).join(' ');
  }
}

function logLine(text, kind) {
  app.log.push({text, kind});
  renderLog();
}

function renderLog() {
  const log = document.getElementById('save-log');
  if (!log) return;
  log.replaceChildren(...app.log.map((line) => el('li', {class: line.kind || ''},
    line.link ? el('a', {href: line.link, target: '_top'}, line.text) : line.text)));
}

function processingMessages(response, label) {
  const entry = response && response.processing && response.processing.entry;
  if (!entry) return;
  for (const message of entry.errors || []) logLine(`${label}: ${message}`, 'err');
  for (const message of entry.warnings || []) logLine(`${label}: ${message}`, 'warn');
}

/*
 * A pending file is kept under `<field path>.<position in the list>`, e.g.
 * `in_situ.0.rheed_pattern_export_files.2`. The files of a list item go into
 * a folder of their own (`in_situ_1`), so equal file names of two
 * measurements do not overwrite each other.
 */
async function uploadPendingFiles(uploadId, directory) {
  for (const [path, file] of Object.entries(app.pendingFiles)) {
    const parts = path.split('.');
    const position = Number(parts.pop());
    const list = formAt(app.form, parts);
    const folder = parts.length > 2 ? `${directory}/${parts[0]}_${Number(parts[1]) + 1}` : `${directory}/${parts[0]}`;
    const body = new FormData();
    body.append('file', file, file.name);
    await api(`${uploadPath(uploadId, 'raw', folder)}?wait_for_processing=false&overwrite_if_exists=true`, {
      method: 'PUT', body,
    });
    if (Array.isArray(list)) list[position] = `${folder}/${file.name}`;
    delete app.pendingFiles[path];
    logLine(`Uploaded ${file.name}`, 'ok');
  }
}

async function saveLogbook() {
  if (app.saving) return;
  let rerender = false;
  app.errors = validate(app.form, app.spec);
  if (app.errors.length) {
    app.spec.sections.forEach((s) => app.shown.add(s.key));
    return refresh();
  }
  app.saving = true;
  app.log = [];
  updateSaveState();
  try {
    // Checked again here, whichever way the logbook was opened: the save goes
    // to the upload of `app.edit` and overwrites its file.
    if (app.edit && !checkedEdit(app.edit, app.draft ? app.draft.upload_id : undefined)) {
      app.edit = null;
      rerender = true;
      logLine('The logbook to overwrite could not be verified, so it is saved as a new logbook.', 'warn');
    }
    const logbookFile = app.edit ? app.edit.mainfile : null;
    let result = await dashboard('api/archive', {form: app.form, logbook_file: logbookFile});
    const fileError = result.errors.find((e) => e.path === 'logbook_file');
    if (fileError) {
      app.edit = null;
      rerender = true;
      logLine(fileError.message, 'err');
      showBanner(`${fileError.message} Save again to store it as a new logbook.`, 'error');
      return;
    }
    if (result.errors.length) throw new Error('The server found problems: ' + result.errors.map((e) => `${e.path}: ${e.message}`).join('; '));
    const uploadId = await ensureUpload();
    logLine(`Saving to upload ${uploadId}`);
    if (Object.keys(app.pendingFiles).length) {
      const directory = `${client().file_dir}/${result.logbook_file.replace(/\.archive\.json$/, '')}`;
      await uploadPendingFiles(uploadId, directory);
      result = await dashboard('api/archive', {form: app.form, logbook_file: logbookFile});
    }
    let logbookEntry = null;
    for (const file of result.files) {
      let response;
      try {
        response = await putArchive(uploadId, file.file_name, file.archive, file.overwrite);
      } catch (e) {
        if (e.status === 409 || /exist/i.test(e.message)) {
          throw new Error(`${file.file_name} already exists in this upload. `
            + (file.kind === 'sample'
              ? 'A sample with this ID was saved before: check the date and time of the run.'
              : 'Change the run name or time, or open the existing logbook.'));
        }
        throw e;
      }
      const label = file.kind === 'sample' ? `Sample ${file.archive.data.sample_id}` : `Logbook ${file.file_name}`;
      logLine(`${label} saved`, 'ok');
      processingMessages(response, label);
      if (file.kind === 'sample') {
        const item = app.form.samples.find((s) => s.uid === file.uid);
        if (item) {
          // From now on the sample keeps this ID and its entry is updated on save.
          item.ref = file.reference;
          item.sample_id = file.archive.data.sample_id;
          item.sample_uuid = file.archive.data.sample_uuid;
        }
      } else {
        logbookEntry = response.processing && response.processing.entry_id;
      }
    }
    for (const warning of result.warnings || []) {
      const sample = /^samples\.(\d+)$/.exec(warning.path || '');
      logLine((sample ? `Sample ${Number(sample[1]) + 1}: ` : '') + warning.message, 'warn');
    }
    await deleteNomadDraft();
    app.edit = {upload_id: uploadId, entry_id: logbookEntry, mainfile: result.logbook_file};
    app.source = uploadId;
    app.upload = uploadId;
    if (logbookEntry) {
      app.log.push({text: 'Open the logbook in NOMAD', link: `${GUI}/projects/${uploadId}/entries/${logbookEntry}`, kind: 'ok'});
    }
    app.log.push({text: 'Open the upload in NOMAD', link: `${GUI}/projects/${uploadId}`, kind: 'ok'});
    renderLog();
    showBanner('The logbook was saved to NOMAD. Further saves update the same logbook.', 'success',
      {label: 'Start a new logbook', run: () => newLogbook(true)});
    clearDraft();
  } catch (e) {
    logLine('Saving failed: ' + e.message, 'err');
  } finally {
    app.saving = false;
    // The save card shows where the logbook goes, which changed.
    if (rerender && app.current === 'save') render();
    else refresh();
  }
}

/* ------------------------------------------------------------ PDF export */

/*
 * The logbook as a PDF report (pdf.js). Only the fields that apply and are
 * filled in are listed, like in the saved logbook.
 */

function displayValue(field, local) {
  const root = app.form;
  if (field.kind === 'computed') {
    const value = compute(field.compute, local, root);
    if (value === null || value === undefined) return null;
    return typeof value === 'number' ? `${formatNumber(value)} ${field.unit_label || ''}`.trim() : String(value);
  }
  const value = local[field.key];
  if (field.kind === 'bool') {
    // Switches that only open a group (a gas, a technique) are shown by their fields.
    if (!value && field.archive === null) return null;
    return value ? 'yes' : 'no';
  }
  if (isEmpty(value)) return null;
  if (field.kind === 'rows') {
    const rows = value.map((row) => field.columns.map((c) => displayValue(c, row)).filter(Boolean).join(', '));
    return rows.filter(Boolean).join('; ') || null;
  }
  if (field.kind === 'reference') return refName(field.reference, value);
  if (field.kind === 'target_choice') return refName('target', value);
  if (field.kind === 'sample_choice') {
    const option = choiceOptions(field, local).find((o) => o.value === value);
    return option ? option.label : value;
  }
  if (field.kind === 'files') return value.map((name) => String(name).split('/').pop()).join(', ');
  if (field.kind === 'step_choice') {
    return value.map((stepUid) => {
      const index = (root.steps || []).findIndex((s) => s.uid === stepUid);
      return index < 0 ? 'removed step' : itemTitle(`steps.${index}`);
    }).join('; ');
  }
  const unit = field.unit_label || field.unit;
  return field.kind === 'number' && unit ? `${value} ${unit}` : String(value);
}

function reportFields(fields, local) {
  const blocks = [];
  let group = null;
  for (const field of fields) {
    if (!evaluate(field.visible_if, local, app.form)) continue;
    const value = displayValue(field, local);
    if (value === null) continue;
    if (field.group && field.group !== group) {
      group = field.group;
      if (field.label !== group) blocks.push({kind: 'group', text: group});
    }
    blocks.push({kind: 'row', label: field.label, value});
  }
  return blocks.length ? blocks : [{kind: 'note', text: 'Nothing filled in.'}];
}

function reportBlocks() {
  const form = app.form;
  const complete = Boolean(app.edit) && !app.errors.length;
  const missing = app.errors.length;
  const blocks = [
    {kind: 'title', text: `${client().title} · ${runLabel(form)}`},
    complete
      ? {kind: 'status', text: `Saved logbook ${app.edit.mainfile}`}
      : {kind: 'alert', text: 'DRAFT / INCOMPLETE: this is not a logged logbook'
        + (missing ? ` (${missing} thing${missing === 1 ? '' : 's'} still missing)` : '')},
    {kind: 'note', text: [
      form.run.operator_name && `Operator: ${form.run.operator_name}`,
      `Exported ${new Date().toLocaleString()}`,
    ].filter(Boolean).join(' · ')},
  ];
  for (const s of app.spec.sections) {
    if (sectionRequirement(s, form) === 'none') continue;
    blocks.push({kind: 'heading', text: s.title});
    if (s.kind === 'object') {
      blocks.push(...reportFields(s.fields, form[s.key] || {}));
      continue;
    }
    const items = form[s.key] || [];
    if (!items.length) blocks.push({kind: 'note', text: 'None.'});
    items.forEach((item, index) => {
      const fields = s.kind === 'variant_list' ? (s.variants[item.type] || {fields: []}).fields : s.fields;
      blocks.push({kind: 'subheading', text: itemTitle(`${s.key}.${index}`)}, ...reportFields(fields, item));
    });
  }
  return blocks;
}

/*
 * A PDF file made in the browser and downloaded. NOMAD shows the dashboard in a
 * sandboxed frame in which browsers ignore window.print(), but allow downloads.
 */
function exportPdf() {
  const title = `${client().title} ${runLabel(app.form)}`;
  const blob = makePdf(reportBlocks(), title);
  const fileName = title.replace(/ · /g, ' ').replace(/:/g, '-').replace(/[^\w .-]+/g, '_') + '.pdf';
  const link = el('a', {href: URL.createObjectURL(blob), download: fileName});
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 60000);
}

/* ---------------------------------------------------- drafts on NOMAD */

/*
 * A draft is the form state kept as a plain file in the upload
 * (e.g. pld_drafts/<run>.draft.json). No parser reads it, so it never becomes an
 * entry: only the final save creates the logbook and sample entries, and it
 * deletes the draft.
 */

async function readNomadDraft(uploadId, path) {
  try {
    return await api(uploadPath(uploadId, 'raw', path));
  } catch (e) {
    if (e.status === 404) return null;
    throw e;
  }
}

async function saveDraftToNomad() {
  if (app.saving) return;
  if (!app.user) return showBanner('Log in to NOMAD to save a draft.', 'error');
  const problems = validateDraft(app.form);
  if (problems.length) {
    app.shown.add('run');
    go('run', problems[0].path);
    return showBanner('A draft needs the PVD system, date and start time of the run.', 'error');
  }
  if (!app.edit && !app.draft && !app.upload) {
    go('save');
    return showBanner('Choose the upload to keep the draft in.', 'error');
  }
  app.saving = true;
  app.log = [];
  updateSaveState();
  try {
    const uploadId = app.draft ? app.draft.upload_id : await ensureUpload();
    let path = app.draft && app.draft.upload_id === uploadId ? app.draft.path : null;
    if (!path) {
      const named = await dashboard('api/draft-name', {form: app.form});
      if (named.errors.length) throw new Error(named.errors.map((e) => e.message).join(' '));
      path = named.path;
    }
    // Another computer may have saved this draft since it was opened here.
    const stored = await readNomadDraft(uploadId, path);
    if (stored && (!app.draft || stored.savedAt !== app.draft.savedAt)) {
      const by = stored.savedBy ? ` by ${stored.savedBy}` : '';
      const overwrite = await askConfirm('Draft changed elsewhere',
        `This draft was saved${by} on ${new Date(stored.savedAt).toLocaleString()}, after you opened it here. `
        + 'Overwrite it with this form, or load that version instead?', 'Overwrite', 'Load that version');
      if (!overwrite) {
        openNomadDraft(uploadId, path, stored, true);
        return;
      }
    }
    const directory = path.slice(0, path.lastIndexOf('/'));
    const fileName = path.slice(path.lastIndexOf('/') + 1);
    const stem = fileName.replace(/\.draft\.json$/, '');
    if (Object.keys(app.pendingFiles).length) await uploadPendingFiles(uploadId, `${client().file_dir}/${stem}`);
    const draft = {
      version: DRAFT_VERSION,
      form: app.form,
      edit: app.edit,
      savedAt: new Date().toISOString(),
      savedBy: app.user.name || app.user.username || '',
    };
    await api(`${uploadPath(uploadId, 'raw', directory)}?file_name=${encodeURIComponent(fileName)}`
      + '&overwrite_if_exists=true&wait_for_processing=false', {
      method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(draft),
    });
    app.draft = {upload_id: uploadId, path, savedAt: draft.savedAt};
    // Files added to the form were just uploaded here.
    app.source = uploadId;
    app.upload = uploadId;
    logLine(`Draft saved as ${path}`, 'ok');
    saveDraft();
    showBanner(`Draft saved in the upload at ${new Date(draft.savedAt).toLocaleTimeString()}. Continue it on any `
      + 'computer from the start page. It only counts as logged once the logbook is saved.', 'success');
  } catch (e) {
    logLine('Saving the draft failed: ' + e.message, 'err');
    showBanner('Saving the draft failed: ' + e.message, 'error');
  } finally {
    app.saving = false;
    refresh();
  }
}

async function deleteNomadDraft() {
  if (!app.draft) return;
  try {
    await api(uploadPath(app.draft.upload_id, 'raw', app.draft.path), {method: 'DELETE'});
    logLine('Draft removed: the logbook is saved.', 'ok');
  } catch (e) {
    if (e.status !== 404) logLine(`The draft ${app.draft.path} could not be removed: ${e.message}`, 'warn');
  }
  app.draft = null;
}

async function openNomadDraft(uploadId, path, stored, force) {
  const same = app.draft && app.draft.upload_id === uploadId && app.draft.path === path;
  if (!force && !same && !(await confirmReplace())) return;
  app.form = upgradeForm(stored.form);
  // The draft is a file others in the upload can change: only a logbook of
  // this upload, made by this dashboard, may be overwritten by the save.
  app.edit = checkedEdit(stored.edit, uploadId);
  const unverified = Boolean(stored.edit) && !app.edit;
  app.source = uploadId;
  app.draft = {upload_id: uploadId, path, savedAt: stored.savedAt};
  app.upload = uploadId;
  app.pendingFiles = {};
  app.touched.clear();
  app.shown.clear();
  closeDialog();
  changed();
  go('run');
  showBanner(`Continuing the draft ${path}, saved ${new Date(stored.savedAt).toLocaleString()}`
    + (stored.savedBy ? ` by ${stored.savedBy}` : '') + '.'
    + (unverified ? ` ${UNVERIFIED_EDIT}` : ''), unverified ? 'error' : undefined);
}

/* The drafts in the user's unpublished uploads, newest first. */
async function findDrafts() {
  await loadUploads();
  const found = await Promise.all(app.uploads.map(async (upload) => {
    let listing;
    try {
      listing = await api(`${uploadPath(upload.upload_id, 'rawdir', client().draft_dir)}?page_size=200`);
    } catch (e) {
      return [];
    }
    const files = ((listing.directory_metadata || {}).content || [])
      .filter((f) => f.is_file && /^[\p{L}\p{N}\p{M}_.-]+\.draft\.json$/u.test(f.name));
    return Promise.all(files.map(async (f) => {
      const path = `${client().draft_dir}/${f.name}`;
      const stored = await readNomadDraft(upload.upload_id, path).catch(() => null);
      if (!stored || !stored.form) return null;
      return {
        title: f.name.replace(/\.draft\.json$/, ''),
        sub: `${upload.upload_name || upload.upload_id} · saved ${new Date(stored.savedAt).toLocaleString()}`
          + (stored.savedBy ? ` by ${stored.savedBy}` : ''),
        uploadId: upload.upload_id, path, stored,
      };
    }));
  }));
  return found.flat().filter(Boolean).sort((a, b) => b.stored.savedAt.localeCompare(a.stored.savedAt));
}

/* ----------------------------------------------------------- lifecycle */

async function newLogbook(force) {
  if (!force && !(await confirmReplace())) return;
  app.form = newForm();
  app.edit = null;
  app.draft = null;
  app.source = null;
  app.pendingFiles = {};
  app.touched.clear();
  app.shown.clear();
  app.log = [];
  clearDraft();
  document.getElementById('banner').hidden = true;
  changed();
  go('run');
  // Targets and samples added elsewhere in NOMAD since the page was opened.
  loadReferences();
}

function step(offset) {
  const keys = navSections().map((s) => s.key);
  const position = keys.indexOf(app.current);
  if (offset > 0 && app.current !== 'save') app.shown.add(app.current);
  const next = keys[position + offset];
  if (next) go(next);
}

async function init() {
  document.getElementById('btn-home').addEventListener('click', () => go('home'));
  document.getElementById('brand').addEventListener('click', () => go('home'));
  document.getElementById('btn-draft-save').addEventListener('click', saveDraftToNomad);
  document.getElementById('btn-pdf').addEventListener('click', exportPdf);
  document.getElementById('btn-prev').addEventListener('click', () => step(-1));
  document.getElementById('btn-next').addEventListener('click', () => step(1));
  document.getElementById('dialog-cancel').addEventListener('click', closeDialog);
  document.getElementById('dialog').addEventListener('click', (e) => {
    if (e.target.id === 'dialog') closeDialog();
  });

  try {
    app.spec = await dashboard('api/spec');
  } catch (e) {
    document.getElementById('section').replaceChildren(el('div', {class: 'card'}, 'Could not load the form: ' + e.message));
    return;
  }
  checkServerVersion();
  app.newUploadName = client().upload_name;
  // The logbook last worked on in this browser is offered on the start page,
  // or opened straight away when the page is reloaded inside the form.
  const draft = loadDraft();
  const linked = window.location.hash.slice(1);
  if (draft) {
    app.form = draft.form;
    app.draft = draft.draft || null;
    app.edit = checkedEdit(draft.edit, app.draft ? app.draft.upload_id : undefined);
    // Kept by older versions only as the upload of `edit` or `draft`.
    app.source = validUploadId(draft.source)
      || (app.draft ? validUploadId(app.draft.upload_id) : null)
      || (app.edit ? app.edit.upload_id : null);
    app.upload = draft.upload || '';
    app.started = true;
    const dropped = dropPendingFiles(app.form, draft.pending);
    upgradeForm(app.form);
    if (dropped) {
      showBanner(`Choose the ${dropped} file(s) of the current logbook again: `
        + 'files are only kept until the page is closed.');
    }
    if (navSections().some((s) => s.key === linked)) app.current = linked;
  } else {
    app.form = newForm();
  }
  app.errors = validate(app.form, app.spec);
  render();
  await loadUser();
  app.referencesLoadedAt = Date.now();
  await Promise.all([loadDatabaseAccess(), loadReferences(), loadUploads()]);
  // Render again: the operator is filled in from the login.
  render();
}

init();
