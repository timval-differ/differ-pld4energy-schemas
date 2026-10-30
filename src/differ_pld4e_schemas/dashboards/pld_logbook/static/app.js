/*
 * PLD logbook dashboard.
 *
 * The form is built from the definition served by `api/spec` (see spec.py).
 * The rules below mirror rules.py so problems show while typing; the server
 * validates again before it builds the archive files. Everything that needs
 * the user's NOMAD session (uploads, searching entries, writing files) goes
 * straight to the NOMAD API, which accepts the GUI's Authorization cookie.
 */
'use strict';

const BASE = window.location.pathname.replace(/\/dashboards\/.*$/, '');
const API = BASE + '/api/v1';
const GUI = BASE + '/gui/v2';
const DASHBOARD = window.location.pathname.replace(/\/?$/, '/');
const DRAFT_KEY = 'pld-logbook-draft-v2';
const DRAFT_DIR = 'pld_drafts';
const DRAFT_VERSION = 1;
const NEW_SAMPLE = 'New sample';
const MADE_HERE = ['New sample', 'External sample'];
const FILE_DIR = 'pld_files';
const LEVELS = ['none', 'optional', 'required'];

const app = {
  spec: null,
  form: null,
  edit: null, // {upload_id, entry_id, mainfile} of an opened logbook
  draft: null, // {upload_id, path, savedAt} of the draft kept in NOMAD
  upload: '', // selected upload id, or '__new__'
  newUploadName: 'PLD logbooks',
  current: 'home', // 'home' (start page), a section key, or 'save'
  started: false, // whether the form holds a logbook being worked on
  user: null,
  uploads: [],
  refs: {target: [], sample: [], substrate: []},
  pendingFiles: {}, // form path -> File, uploaded on save
  touched: new Set(),
  shown: new Set(), // sections whose problems are all shown
  collapsed: new Set(), // collapsed step uids
  errors: [],
  rendered: [],
  saving: false,
  log: [],
};

/* ---------------------------------------------------------------- helpers */

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

function uid() {
  return Math.random().toString(16).slice(2, 14);
}

const pad = (n) => String(n).padStart(2, '0');

function localDate(d) {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function localTime(d) {
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/* The browser's UTC offset at a moment, e.g. '+01:00'. */
function utcOffset(d) {
  const minutes = -d.getTimezoneOffset();
  const sign = minutes < 0 ? '-' : '+';
  return `${sign}${pad(Math.floor(Math.abs(minutes) / 60))}:${pad(Math.abs(minutes) % 60)}`;
}

/* NOMAD returns the start of the run in UTC; show it in local time. */
function localizeRun(run) {
  if (!run || !run.start) return;
  const start = new Date(run.start);
  if (!Number.isNaN(start.getTime())) {
    run.date = localDate(start);
    run.time = localTime(start);
    run.utc_offset = utcOffset(start);
  }
  delete run.start;
}

function fileNameFor(text) {
  return text.replace(/[^\w.-]/g, '_');
}

function entryRef(uploadId, entryId) {
  return `../uploads/${uploadId}/archive/${entryId}#/data`;
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
  const json = await response.json();
  if (!response.ok) throw new Error(json.detail || `HTTP ${response.status}`);
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

/* ------------------------------------------------- rules (mirror rules.py) */

function lookup(key, local, root) {
  if (!key.startsWith('/')) return local[key];
  let value = root;
  for (const part of key.replace(/^\/+|\/+$/g, '').split('/')) {
    value = value && typeof value === 'object' ? value[part] : undefined;
  }
  return value;
}

function evaluate(condition, local, root) {
  if (!condition) return true;
  if (condition.all) return condition.all.every((c) => evaluate(c, local, root));
  if (condition.any) return condition.any.some((c) => evaluate(c, local, root));
  const value = lookup(condition.key, local, root);
  if ('equals' in condition) {
    if (typeof condition.equals === 'boolean') return Boolean(value) === condition.equals;
    return value === condition.equals;
  }
  if ('in' in condition) return condition.in.includes(value);
  if ('has_type' in condition) {
    return (value || []).some((item) => item && condition.has_type.includes(item.type));
  }
  throw new Error('Unknown condition');
}

function fieldOptions(field, local, root) {
  if (field.options_by) return field.options_by.map[lookup(field.options_by.key, local, root)] || [];
  return field.options || [];
}

function toNumber(value) {
  if (typeof value === 'boolean' || value === null || value === undefined) return null;
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  if (typeof value === 'string') {
    const text = value.trim().replace(',', '.');
    if (!/^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$/.test(text)) return null;
    return Number(text);
  }
  return null;
}

function compute(name, local, root) {
  if (name === 'transmission_window_1') {
    const before = toNumber(local.energy_before_chamber);
    const after = toNumber(local.energy_after_chamber);
    const t2 = toNumber(local.transmission_window_2);
    if (before === null || after === null || !before || !t2) return null;
    return (after / (before * t2 / 100)) * 100;
  }
  if (name === 'sample_id') return sampleId(local, root);
  if (name === 'sample_name') return sampleName(local, root);
  throw new Error('Unknown computed value ' + name);
}

/* Samples (mirror dashboards/common/samples.py and sample.py) */

function madeHere(item) {
  return MADE_HERE.includes(item.origin || NEW_SAMPLE);
}

function sampleNumber(item, root) {
  let number = 0;
  for (const other of root.samples || []) {
    if (!madeHere(other)) continue;
    number += 1;
    if (other === item || (item.uid && other.uid === item.uid)) return number;
  }
  return null;
}

function existingSample(item) {
  return app.refs.sample.find((r) => r.ref === item.sample) || {};
}

function sampleId(item, root) {
  // An existing sample keeps its ID, and so does a sample whose entry exists.
  if (!madeHere(item)) return item.sample_id || existingSample(item).sampleId || null;
  if (item.ref) return item.sample_id || null;
  const system = lookup('/run/system', item, root);
  const date = lookup('/run/date', item, root);
  const time = lookup('/run/time', item, root);
  const number = sampleNumber(item, root);
  if (!system || !/^\d{4}-\d{2}-\d{2}$/.test(date || '') || !/^\d{2}:\d{2}$/.test(time || '') || !number) {
    return null;
  }
  return `${system}_${date}_${time}_S${pad(number)}`;
}

/* How a step refers to a sample of the run (mirror rules.sample_choice). */
function sampleChoice(item) {
  return madeHere(item) ? `new:${item.uid}` : item.sample;
}

/* The films grown on a sample: one per deposition step on it (mirror rules.sample_films). */
function sampleFilms(item, root) {
  const material = (target) => {
    const selected = (root.targets || []).find((t) => t.target === target);
    return (selected && selected.material) || (app.refs.target.find((r) => r.ref === target) || {}).material;
  };
  const sa = (root.run || {}).system === 'SA-PLD';
  return (root.steps || [])
    .filter((step) => step.type === 'deposition' && (sa || step.sample === sampleChoice(item)))
    .map((step) => ({target: step.target, material: material(step.target), thickness: step.film_thickness}));
}

function sampleName(item, root = app.form) {
  if (!madeHere(item)) return item.name || existingSample(item).sampleName || null;
  // The material is copied from the chosen substrate entry (see copyFromRef).
  const material = item.substrate ? item.substrate_material
    : (item.origin === 'External sample' ? item.substrate_details : null);
  if (!material) return null;
  const parts = [material];
  // An external sample may come with films; then those grown in this run.
  const prior = item.origin === 'External sample' ? (item.prior_films || []) : [];
  for (const film of [...prior, ...sampleFilms(item, root)]) {
    if (!film.material) continue;
    const thickness = toNumber(film.thickness);
    parts.push(thickness === null ? film.material : `${film.material}-${Number(thickness.toPrecision(6))}nm`);
  }
  return parts.join('_');
}

function valueOf(field, local, root) {
  return field.kind === 'computed' ? compute(field.compute, local, root) : local[field.key];
}

function isEmpty(value) {
  return value === null || value === undefined || value === '' || (Array.isArray(value) && !value.length);
}

function targetChoices(root) {
  return (root.targets || []).filter((t) => t.target).map((t) => t.target);
}

function sampleChoices(root) {
  const choices = [];
  for (const item of root.samples || []) {
    if (madeHere(item)) choices.push(`new:${item.uid}`);
    else if (item.sample) choices.push(item.sample);
  }
  return choices;
}

/* What one step needs of an aspect (e.g. the laser): an optional one counts once used. */
function stepLevel(variant, item, aspect) {
  const level = variant[aspect] || 'none';
  return level === 'optional' && item[`${aspect}_used`] ? 'required' : level;
}

/* 'required', 'optional' or 'none': a section with a `requirement` follows the steps. */
function sectionRequirement(s, data) {
  if (!s.requirement) return 'required';
  const steps = app.spec.sections.find((x) => x.kind === 'variant_list');
  if (!steps) return 'none';
  let level = 'none';
  for (const item of data[steps.key] || []) {
    const variant = steps.variants[item.type];
    if (!variant) continue;
    const step = stepLevel(variant, item, s.requirement.from_steps);
    if (LEVELS.indexOf(step) > LEVELS.indexOf(level)) level = step;
  }
  return level;
}

function fieldError(field, value, local, root) {
  const kind = field.kind;
  if (kind === 'number' || kind === 'integer') {
    const number = toNumber(value);
    if (number === null) return 'Enter a number.';
    if (kind === 'integer' && !Number.isInteger(number)) return 'Enter a whole number.';
    if ('min' in field && number < field.min) return `Must be at least ${field.min}.`;
  } else if (kind === 'select') {
    if (!fieldOptions(field, local, root).includes(value)) return 'Choose one of the options.';
  } else if (kind === 'date') {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return 'Enter a date.';
  } else if (kind === 'time') {
    if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(value)) return 'Enter a time (hh:mm).';
  } else if (kind === 'target_choice') {
    if (!targetChoices(root).includes(value)) return 'Choose one of the targets selected under Targets.';
  } else if (kind === 'sample_choice') {
    if (!sampleChoices(root).includes(value)) return 'Choose one of the samples under Samples.';
  }
  return null;
}

function validateFields(fields, local, path, root, errors, required = true) {
  for (const field of fields) {
    if (!evaluate(field.visible_if, local, root) || field.kind === 'computed') continue;
    const value = local[field.key];
    const fieldPath = `${path}.${field.key}`;
    if (field.kind === 'rows') {
      (value || []).forEach((row, index) => {
        validateFields(field.columns, row, `${fieldPath}.${index}`, root, errors, required);
      });
      continue;
    }
    if (isEmpty(value)) {
      if (field.required && required && evaluate(field.required_if, local, root)) {
        errors.push({path: fieldPath, message: 'Required.'});
      }
      continue;
    }
    const message = fieldError(field, value, local, root);
    if (message) errors.push({path: fieldPath, message});
  }
}

function validate(data, spec) {
  const errors = [];
  for (const section of spec.sections) {
    const key = section.key;
    const level = sectionRequirement(section, data);
    if (level === 'none') continue;
    const required = level === 'required';
    if (section.kind === 'object') {
      validateFields(section.fields, data[key] || {}, key, data, errors, required);
      continue;
    }
    const items = data[key] || [];
    if (required && items.length < (section.min_items || 0)) {
      errors.push({path: key, message: `Add at least one ${section.item_label.toLowerCase()}.`});
    }
    items.forEach((item, index) => {
      let fields = section.fields;
      if (section.kind === 'variant_list') {
        const variant = section.variants[item.type];
        if (!variant) {
          errors.push({path: `${key}.${index}.type`, message: 'Unknown step type.'});
          return;
        }
        fields = variant.fields;
      }
      validateFields(fields, item, `${key}.${index}`, data, errors, required);
    });
    if (section.kind === 'list') {
      for (const uniqueKey of section.unique || []) {
        const field = section.fields.find((f) => f.key === uniqueKey);
        const seen = new Set();
        items.forEach((item, index) => {
          if (!evaluate(field.visible_if, item, data)) return;
          const value = valueOf(field, item, data);
          if (isEmpty(value)) return;
          if (seen.has(value)) {
            errors.push({path: `${key}.${index}.${uniqueKey}`, message: `${field.label} is used more than once.`});
          }
          seen.add(value);
        });
      }
    }
  }
  return errors;
}

/* What a draft needs (mirror rules.validate_draft): it names the draft file. */
function validateDraft(data) {
  const run = data.run || {};
  const errors = [];
  if (!app.spec.systems.includes(run.system)) errors.push({path: 'run.system', message: 'Choose the PVD system.'});
  if (!/^\d{4}-\d{2}-\d{2}$/.test(run.date || '')) errors.push({path: 'run.date', message: 'Enter a date.'});
  if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(run.time || '')) errors.push({path: 'run.time', message: 'Enter a time (hh:mm).'});
  return errors;
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
    if (field.key === 'comments' || !keys.has(field.key) || isEmpty(source[field.key])) continue;
    values[field.key] = source[field.key];
  }
  return values;
}

function newItem(listSection, variantKey, list) {
  if (variantKey) {
    return {
      uid: uid(), type: variantKey, ...defaults(listSection.variants[variantKey].fields),
      ...prefill(listSection, variantKey, list),
    };
  }
  return {uid: uid(), ...defaults(listSection.fields)};
}

function newForm() {
  const form = {recipe: null};
  for (const s of app.spec.sections) {
    if (s.kind === 'object') form[s.key] = defaults(s.fields);
    else if (s.kind === 'list') form[s.key] = [newItem(s)];
    else form[s.key] = [];
  }
  const now = new Date();
  form.run.date = localDate(now);
  form.run.time = localTime(now);
  form.run.utc_offset = utcOffset(now);
  fillOperator(form);
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
    localStorage.setItem(DRAFT_KEY, JSON.stringify({
      form: app.form, edit: app.edit, draft: app.draft, upload: app.upload,
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
    const draft = JSON.parse(localStorage.getItem(DRAFT_KEY) || 'null');
    if (!draft || !draft.form || !draft.form.run) return null;
    return draft;
  } catch (e) {
    return null;
  }
}

function clearDraft() {
  try {
    localStorage.removeItem(DRAFT_KEY);
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
  for (const path of pendingPaths || []) {
    const [key, field] = path.split('.');
    if (form[key] && form[key][field]) {
      form[key][field] = null;
      dropped += 1;
    }
  }
  return dropped;
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

async function searchEntries(qualifiedNames, required, {owner = 'visible', pageSize = 1000} = {}) {
  const body = {
    owner,
    query: {'section_defs.definition_qualified_name:any': qualifiedNames},
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

async function loadReferences() {
  if (!app.user) return;
  const names = app.spec.reference_sections;
  try {
    const targets = !names.target ? [] : await searchEntries([names.target], {
      data: '*', metadata: {entry_name: '*', mainfile: '*'},
    });
    app.refs.target = targets.filter(Boolean).map((t) => {
      const data = (t.archive && t.archive.data) || {};
      const metadata = (t.archive && t.archive.metadata) || {};
      const file = metadata.mainfile ? metadata.mainfile.replace(/\.archive\.(json|yaml)$/, '') : t.entry_id;
      return {
        ref: entryRef(t.upload_id, t.entry_id),
        name: data.name || data.material || metadata.entry_name || `${file} (no material entered)`,
        material: data.material || null,
        retired: data.in_stock === false,
        info: [data.material, data.manufacturer, data.purchase_date && String(data.purchase_date).slice(0, 10),
          data.in_stock === false ? 'out of stock' : null]
          .filter(Boolean).join(' · ') || 'This target has no material, manufacturer or purchase date yet.',
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
    const substrates = !names.substrate ? [] : await searchEntries([names.substrate], {
      data: {name: '*', material: '*', size: '*', supplier: '*', in_stock: '*'},
      metadata: {entry_name: '*', mainfile: '*'},
    });
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
        return {value: `new:${s.uid}`, label: sampleId(s, root) || sampleName(s) || `Sample ${index + 1}`};
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
    case 'file': {
      const name = el('span', {class: 'file-name'});
      const pending = el('span', {class: 'file-pending'});
      input = el('input', {
        type: 'file', id, accept: field.accept || undefined,
        onchange: (e) => {
          const file = e.target.files[0];
          if (!file) return;
          app.pendingFiles[path] = file;
          set(file.name);
        },
      });
      const clear = el('button', {
        type: 'button', class: 'btn btn-text btn-icon btn-danger', title: 'Remove file',
        onclick: () => {
          delete app.pendingFiles[path];
          input.value = '';
          set(null);
        },
      }, '✕');
      input.hidden = true;
      const choose = el('button', {type: 'button', class: 'btn btn-outlined', onclick: () => input.click()}, 'Choose file');
      body = el('div', {class: 'file-row'}, input, choose, name, pending, clear);
      return {body, input, fileName: name, filePending: pending, fileClear: clear};
    }
    case 'date':
    case 'time':
      input = el('input', {type: field.kind, id, value: local[field.key] || '', onchange: (e) => set(e.target.value || null)});
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
    const wide = ['textarea', 'file', 'rows'].includes(field.kind);
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

/* Whether a ticked in-situ technique has no data file yet. */
function awaitingData(technique, inSitu) {
  return section('in_situ').fields
    .filter((f) => f.technique === technique)
    .every((f) => isEmpty(inSitu[f.key]));
}

function awaitingTechniques(form) {
  const inSitu = form.in_situ || {};
  return section('in_situ').fields
    .filter((f) => f.kind === 'bool' && inSitu[f.key] && awaitingData(f.key, inSitu))
    .map((f) => f.group);
}

function sectionShown(path) {
  return app.shown.has(path.split('.')[0]);
}

function refresh() {
  const root = app.form;
  const byPath = new Map();
  for (const error of app.errors) if (!byPath.has(error.path)) byPath.set(error.path, error.message);
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
    if (kind === 'file') {
      r.fileName.textContent = value ? String(value).split('/').pop() : 'No file chosen';
      r.filePending.textContent = value && app.pendingFiles[r.path] ? 'uploaded on save' : '';
      r.fileClear.hidden = !value;
    }
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
    r.wrap.classList.toggle('invalid', Boolean(show));
    r.error.textContent = show ? message : '';
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
    const name = sampleId(item, app.form) || sampleName(item);
    return `${s.item_label} ${Number(index) + 1}` + (name ? `: ${name}` : '');
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
  document.getElementById('btn-home').hidden = home;
}

function navSections() {
  return [...app.spec.sections.map((s) => ({key: s.key, title: s.title})), {key: 'save', title: 'Review and save'}];
}

const REQUIREMENT_NOTES = {
  none: 'Not needed for these process steps: it is only logged when a step needs it '
    + '(e.g. a pre-ablation or deposition step). What you enter here is not saved.',
  optional: 'Optional for these process steps: fill it in if it applies.',
};

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
      title: level === 'required' ? '' : REQUIREMENT_NOTES[level],
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

let referencesLoaded = 0;

function go(key, focusPath) {
  if (key !== app.current && (key === 'targets' || key === 'samples') && Date.now() - referencesLoaded > 30000) {
    referencesLoaded = Date.now();
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
function confirmReplace() {
  return !app.started || window.confirm(
    `Replace the logbook you are working on (${runLabel(app.form)})? `
    + 'What is not saved as a draft or logbook is lost.');
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
    el('h1', {}, 'PLD logbook'),
    el('p', {class: 'section-intro'}, 'Log an SA-PLD or LA-PLD run step by step, starting from its samples. '
      + 'Only the fields that apply are shown, and a logbook is saved once it is complete.'),
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
    level === 'required' ? null : el('div', {class: 'info requirement-' + level}, REQUIREMENT_NOTES[level]),
  ];
}

function renderObject(container, s) {
  const card = el('div', {class: 'card'}, sectionHeader(s));
  if (s.intro) card.append(el('div', {class: 'info'}, s.intro));
  if (s.key === 'run' && app.form.recipe) {
    card.append(el('div', {class: 'info'}, 'The process steps were loaded from a recipe.'));
  }
  if (s.key === 'in_situ' && awaitingTechniques(app.form).length) {
    card.append(el('div', {class: 'info'},
      `Awaiting data: ${awaitingTechniques(app.form).join(', ')}. The logbook can be saved without them.`));
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
  const apply = () => {
    const wanted = Math.max(0, Math.min(99, Number(input.value) || 0));
    let made = list.filter(madeHere);
    while (made.length < wanted) {
      list.push(newItem(s));
      made = list.filter(madeHere);
    }
    const extra = made.slice(wanted);
    const filled = extra.filter((item) => item.substrate || (item.layers || []).length || item.comments);
    if (filled.length && !window.confirm(`Remove ${extra.length} sample(s), of which ${filled.length} filled in?`)) {
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
  list.forEach((item, index) => {
    card.append(itemCard(s, list, index, (body, it, path) => renderFields(body, s.fields, it, path)));
  });
  const actions = el('div', {class: 'btn-row'}, el('button', {
    type: 'button', class: 'btn btn-outlined',
    onclick: () => { list.push(newItem(s)); changed(); render(); },
  }, `+ Add ${s.item_label.toLowerCase()}`));
  if (s.key === 'targets') {
    actions.append(el('button', {type: 'button', class: 'btn btn-text', onclick: newTargetDialog}, 'New target in the database'));
  }
  if (s.key === 'samples') {
    actions.append(el('button', {type: 'button', class: 'btn btn-text', onclick: newSubstrateDialog}, 'New substrate in the database'));
    actions.append(el('button', {type: 'button', class: 'btn btn-text', onclick: newTargetDialog}, 'New target in the database'));
  }
  actions.append(el('button', {type: 'button', class: 'btn btn-text', onclick: loadReferences}, 'Refresh lists'));
  card.append(actions);
  container.append(card);
}

function renderSteps(container, s) {
  const card = el('div', {class: 'card'}, sectionHeader(s,
    'Add the steps in the order they were done. Steps can be added more than once, e.g. for multilayers. '
    + 'A run without deposition, e.g. annealing or only characterisation, needs no laser details or targets.'),
  el('div', {class: 'list-error', 'data-list-errors': s.key}));
  if (!app.form.run.system) {
    card.append(el('div', {class: 'info'}, 'Choose the PVD system under Run first: the fields of the steps depend on it.'));
  } else if (app.form.run.system === 'SA-PLD') {
    card.append(el('div', {class: 'info'}, 'In the SA-PLD a deposition covers all samples loaded in the chamber.'));
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
  document.getElementById('dialog-body').replaceChildren(...[content].flat());
  document.getElementById('dialog').hidden = false;
}

function closeDialog() {
  document.getElementById('dialog').hidden = true;
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
  const response = await api(`/entries/${entry.entry_id}/archive`);
  return response.data.archive.data;
}

async function openLogbook(picked) {
  if (!confirmReplace()) return;
  try {
    const data = await fetchLogbook(picked.entry);
    const form = await dashboard('api/form-from-archive', {data, mode: 'edit'});
    localizeRun(form.run);
    app.form = {recipe: null, ...form};
    app.edit = {upload_id: picked.entry.upload_id, entry_id: picked.entry.entry_id, mainfile: picked.entry.mainfile};
    app.draft = null;
    app.upload = picked.entry.upload_id;
    app.pendingFiles = {};
    app.touched.clear();
    app.shown.clear();
    closeDialog();
    changed();
    go('run');
    const awaiting = awaitingTechniques(app.form);
    showBanner(`Opened ${picked.title}. Saving overwrites this logbook.`
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
            + (system === 'LA-PLD' ? ' and choose the sample of each deposition step.' : '.'));
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
  if (app.edit) return app.edit.upload_id;
  if (app.upload && app.upload !== '__new__') return app.upload;
  if (app.upload === '__new__') {
    const name = encodeURIComponent(app.newUploadName || 'PLD logbooks');
    const response = await api(`/uploads?upload_name=${name}`, {method: 'POST'});
    app.upload = response.upload_id;
    await loadUploads();
    return app.upload;
  }
  throw new Error('Choose an upload first.');
}

async function putArchive(uploadId, fileName, archive, overwrite) {
  return api(`/uploads/${uploadId}/raw/?file_name=${encodeURIComponent(fileName)}`
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
      const uploadId = await ensureUpload();
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
  const uploadNeeded = !app.edit && !app.draft && !app.upload;
  openDialog(`New ${noun} in the database`, [
    el('p', {class: 'muted'}, intro),
    el('div', {class: 'grid'}, ...fields.map(input),
      uploadNeeded ? el('div', {class: 'field'}, el('label', {class: 'required'}, 'Upload to store it in'),
        el('div', {class: 'input-wrap'}, uploadSelect())) : null),
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
    intro: 'Creates a PLD Target entry. Do not put the target number in the name: it is entered per run.',
    fields: [
      {key: 'material', label: 'Material', required: true},
      {key: 'name', label: 'Name (optional, defaults to material)'},
      {key: 'manufacturer', label: 'Manufacturer'},
      {key: 'purchase_date', label: 'Purchase date', type: 'date'},
    ],
    build: (v) => Object.fromEntries(Object.entries({
      material: v.material, name: v.name, manufacturer: v.manufacturer,
      purchase_date: v.purchase_date && v.purchase_date + 'T00:00:00+00:00',
    }).filter(([, value]) => value)),
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
      + 'e.g. SrTiO3 10x10 mm. Its material is used in the sample names.',
    fields: [
      {key: 'material', label: 'Material', required: true, placeholder: 'e.g. SrTiO3'},
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
  card.append(el('div', {class: 'btn-row'}, save, draft));
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
  const noUpload = !app.edit && !app.draft && !app.upload;
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

async function uploadPendingFiles(uploadId, directory) {
  for (const [path, file] of Object.entries(app.pendingFiles)) {
    const [key, field] = path.split('.');
    const body = new FormData();
    body.append('file', file, file.name);
    await api(`/uploads/${uploadId}/raw/${directory}?wait_for_processing=false&overwrite_if_exists=true`, {
      method: 'PUT', body,
    });
    app.form[key][field] = `${directory}/${file.name}`;
    delete app.pendingFiles[path];
    logLine(`Uploaded ${file.name}`, 'ok');
  }
}

async function saveLogbook() {
  if (app.saving) return;
  app.errors = validate(app.form, app.spec);
  if (app.errors.length) {
    app.spec.sections.forEach((s) => app.shown.add(s.key));
    return refresh();
  }
  app.saving = true;
  app.log = [];
  updateSaveState();
  try {
    const logbookFile = app.edit ? app.edit.mainfile : null;
    let result = await dashboard('api/archive', {form: app.form, logbook_file: logbookFile});
    if (result.errors.length) throw new Error('The server found problems: ' + result.errors.map((e) => `${e.path}: ${e.message}`).join('; '));
    const uploadId = await ensureUpload();
    logLine(`Saving to upload ${uploadId}`);
    if (Object.keys(app.pendingFiles).length) {
      const directory = `${FILE_DIR}/${result.logbook_file.replace(/\.archive\.json$/, '')}`;
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
    await deleteNomadDraft();
    app.edit = {upload_id: uploadId, entry_id: logbookEntry, mainfile: result.logbook_file};
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
    refresh();
  }
}

/* ---------------------------------------------------- drafts on NOMAD */

/*
 * A draft is the form state kept as a plain file in the upload
 * (pld_drafts/<run>.draft.json). No parser reads it, so it never becomes an
 * entry: only the final save creates the logbook and sample entries, and it
 * deletes the draft.
 */

async function readNomadDraft(uploadId, path) {
  try {
    return await api(`/uploads/${uploadId}/raw/${path}`);
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
      const overwrite = window.confirm(`This draft was saved${by} on ${new Date(stored.savedAt).toLocaleString()}, `
        + 'after you opened it here. Overwrite it with this form? Cancel to load that version instead.');
      if (!overwrite) {
        openNomadDraft(uploadId, path, stored);
        return;
      }
    }
    const directory = path.slice(0, path.lastIndexOf('/'));
    const fileName = path.slice(path.lastIndexOf('/') + 1);
    const stem = fileName.replace(/\.draft\.json$/, '');
    if (Object.keys(app.pendingFiles).length) await uploadPendingFiles(uploadId, `${FILE_DIR}/${stem}`);
    const draft = {
      version: DRAFT_VERSION,
      form: app.form,
      edit: app.edit,
      savedAt: new Date().toISOString(),
      savedBy: app.user.name || app.user.username || '',
    };
    await api(`/uploads/${uploadId}/raw/${directory}?file_name=${encodeURIComponent(fileName)}`
      + '&overwrite_if_exists=true&wait_for_processing=false', {
      method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(draft),
    });
    app.draft = {upload_id: uploadId, path, savedAt: draft.savedAt};
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
    await api(`/uploads/${app.draft.upload_id}/raw/${app.draft.path}`, {method: 'DELETE'});
    logLine('Draft removed: the logbook is saved.', 'ok');
  } catch (e) {
    if (e.status !== 404) logLine(`The draft ${app.draft.path} could not be removed: ${e.message}`, 'warn');
  }
  app.draft = null;
}

function openNomadDraft(uploadId, path, stored) {
  const same = app.draft && app.draft.upload_id === uploadId && app.draft.path === path;
  if (!same && !confirmReplace()) return;
  app.form = stored.form;
  app.edit = stored.edit || null;
  app.draft = {upload_id: uploadId, path, savedAt: stored.savedAt};
  app.upload = uploadId;
  app.pendingFiles = {};
  app.touched.clear();
  app.shown.clear();
  closeDialog();
  changed();
  go('run');
  showBanner(`Continuing the draft ${path}, saved ${new Date(stored.savedAt).toLocaleString()}`
    + (stored.savedBy ? ` by ${stored.savedBy}` : '') + '.');
}

/* The drafts in the user's unpublished uploads, newest first. */
async function findDrafts() {
  await loadUploads();
  const found = await Promise.all(app.uploads.map(async (upload) => {
    let listing;
    try {
      listing = await api(`/uploads/${upload.upload_id}/rawdir/${DRAFT_DIR}?page_size=200`);
    } catch (e) {
      return [];
    }
    const files = ((listing.directory_metadata || {}).content || [])
      .filter((f) => f.is_file && f.name.endsWith('.draft.json'));
    return Promise.all(files.map(async (f) => {
      const path = `${DRAFT_DIR}/${f.name}`;
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

function newLogbook(force) {
  if (!force && !confirmReplace()) return;
  app.form = newForm();
  app.edit = null;
  app.draft = null;
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
  // The logbook last worked on in this browser is offered on the start page,
  // or opened straight away when the page is reloaded inside the form.
  const draft = loadDraft();
  const linked = window.location.hash.slice(1);
  if (draft) {
    app.form = draft.form;
    app.edit = draft.edit || null;
    app.draft = draft.draft || null;
    app.upload = draft.upload || '';
    app.started = true;
    const dropped = dropPendingFiles(app.form, draft.pending);
    if (dropped) {
      showBanner(`Choose the ${dropped} in-situ file(s) of the current logbook again: `
        + 'files are only kept until the page is closed.');
    }
    if (navSections().some((s) => s.key === linked)) app.current = linked;
  } else {
    app.form = newForm();
  }
  app.errors = validate(app.form, app.spec);
  render();
  await loadUser();
  referencesLoaded = Date.now();
  await Promise.all([loadReferences(), loadUploads()]);
  // Render again: the operator is filled in from the login.
  render();
}

init();
