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
const DRAFT_KEY = 'pld-logbook-draft-v1';
const NEW_SUBSTRATE = 'Create new substrate';
const FILE_DIR = 'pld_files';

const app = {
  spec: null,
  form: null,
  edit: null, // {upload_id, entry_id, mainfile} of an opened logbook
  upload: '', // selected upload id, or '__new__'
  newUploadName: 'PLD logbooks',
  current: 'run',
  user: null,
  uploads: [],
  refs: {target: [], substrate: []},
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

function today() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
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
  if (name === 'sample_user_id') {
    const system = lookup('/run/system', local, root);
    const date = lookup('/run/date', local, root);
    if (!system || !date || !local.run_number || !local.sample_number) return null;
    return `${system}_${date}_${local.run_number}_${local.sample_number}`;
  }
  throw new Error('Unknown computed value ' + name);
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

function substrateChoices(root) {
  const choices = [];
  for (const substrate of root.substrates || []) {
    if ((substrate.mode || NEW_SUBSTRATE) === NEW_SUBSTRATE) choices.push(`new:${substrate.uid}`);
    else if (substrate.substrate) choices.push(substrate.substrate);
  }
  return choices;
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
  } else if (kind === 'target_choice') {
    if (!targetChoices(root).includes(value)) return 'Choose one of the targets selected under Targets.';
  } else if (kind === 'substrate_choice') {
    if (!substrateChoices(root).includes(value)) return 'Choose one of the substrates under Substrates.';
  }
  return null;
}

function validateFields(fields, rules, local, path, root, errors) {
  for (const field of fields) {
    if (!evaluate(field.visible_if, local, root) || field.kind === 'computed') continue;
    const value = local[field.key];
    const fieldPath = `${path}.${field.key}`;
    if (isEmpty(value)) {
      if (field.required) errors.push({path: fieldPath, message: 'Required.'});
      continue;
    }
    const message = fieldError(field, value, local, root);
    if (message) errors.push({path: fieldPath, message});
  }
  for (const rule of rules || []) {
    if (rule.type === 'any_of' && evaluate(rule.visible_if, local, root)
      && rule.keys.every((key) => isEmpty(local[key]))) {
      errors.push({path: `${path}.${rule.keys[0]}`, message: rule.message});
    }
  }
}

function validate(data, spec) {
  const errors = [];
  for (const section of spec.sections) {
    const key = section.key;
    if (section.kind === 'object') {
      validateFields(section.fields, section.rules, data[key] || {}, key, data, errors);
      continue;
    }
    const items = data[key] || [];
    if (items.length < (section.min_items || 0)) {
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
      validateFields(fields, null, item, `${key}.${index}`, data, errors);
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
    for (const variantKey of section.required_variants || []) {
      if (!items.some((item) => item.type === variantKey)) {
        errors.push({path: key, message: `Add at least one ${section.variants[variantKey].label.toLowerCase()}.`});
      }
    }
  }
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

function newItem(listSection, variantKey) {
  if (variantKey) {
    return {uid: uid(), type: variantKey, ...defaults(listSection.variants[variantKey].fields)};
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
  form.run.date = today();
  return form;
}

function errorsFor(prefix) {
  return app.errors.filter((e) => e.path === prefix || e.path.startsWith(prefix + '.'));
}

let draftTimer = null;
function changed() {
  app.errors = validate(app.form, app.spec);
  refresh();
  clearTimeout(draftTimer);
  draftTimer = setTimeout(saveDraft, 400);
}

function saveDraft() {
  try {
    localStorage.setItem(DRAFT_KEY, JSON.stringify({
      form: app.form, edit: app.edit, upload: app.upload, savedAt: new Date().toISOString(),
    }));
    document.getElementById('draft-status').textContent = 'Draft saved in this browser at '
      + new Date().toLocaleTimeString();
  } catch (e) {
    document.getElementById('draft-status').textContent = 'The draft could not be saved in this browser.';
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

/* Files chosen but not uploaded are lost on reload; ask for them again. */
function dropPendingFiles(form) {
  let dropped = 0;
  const inSitu = form.in_situ || {};
  for (const field of section('in_situ').fields) {
    if (field.kind === 'file' && inSitu[field.key] && !String(inSitu[field.key]).startsWith(FILE_DIR + '/')) {
      inSitu[field.key] = null;
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

async function searchEntries(qualifiedNames, required) {
  const body = {
    owner: 'visible',
    query: {'section_defs.definition_qualified_name:any': qualifiedNames},
    pagination: {page_size: 1000, order_by: 'entry_create_time', order: 'desc'},
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

async function loadReferences() {
  if (!app.user) return;
  const names = app.spec.reference_sections;
  try {
    const targets = await searchEntries([names.target], {
      data: '*', metadata: {entry_name: '*', mainfile: '*'},
    });
    app.refs.target = targets.filter(Boolean).map((t) => {
      const data = (t.archive && t.archive.data) || {};
      const metadata = (t.archive && t.archive.metadata) || {};
      const file = metadata.mainfile ? metadata.mainfile.replace(/\.archive\.(json|yaml)$/, '') : t.entry_id;
      return {
        ref: entryRef(t.upload_id, t.entry_id),
        name: data.name || data.material || metadata.entry_name || `${file} (no material entered)`,
        info: [data.material, data.manufacturer, data.purchase_date && String(data.purchase_date).slice(0, 10)]
          .filter(Boolean).join(' · ') || 'This target has no material, manufacturer or purchase date yet.',
      };
    }).sort((a, b) => a.name.localeCompare(b.name));
    const substrates = await searchEntries([names.substrate]);
    app.refs.substrate = substrates.map((s) => ({
      ref: entryRef(s.upload_id, s.entry_id),
      name: s.entry_name || s.mainfile,
      info: s.mainfile,
    }));
  } catch (e) {
    showBanner('Could not load targets and substrates: ' + e.message, 'error');
  }
  refresh();
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
  if (field.kind === 'substrate_choice') {
    return (root.substrates || []).map((s, index) => {
      if ((s.mode || NEW_SUBSTRATE) === NEW_SUBSTRATE) {
        return {
          value: `new:${s.uid}`,
          label: s.sample_name || compute('sample_user_id', s, root) || `New substrate ${index + 1}`,
        };
      }
      return s.substrate ? {value: s.substrate, label: refName('substrate', s.substrate)} : null;
    }).filter(Boolean);
  }
  if (field.kind === 'reference') {
    return app.refs[field.reference].map((r) => ({value: r.ref, label: r.name}));
  }
  return fieldOptions(field, local, root).map((o) => ({value: o, label: o}));
}

function emptyChoiceText(field) {
  if (field.options_by) return 'Choose the PVD system first';
  if (field.kind === 'target_choice') return 'Select targets under Targets first';
  if (field.kind === 'substrate_choice') return 'Add substrates under Substrates first';
  if (field.kind === 'reference') return 'None found in NOMAD';
  return 'No options available';
}

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
    case 'substrate_choice': {
      input = el('select', {id, onchange: (e) => set(e.target.value || null)});
      body = el('div', {class: 'input-wrap'}, input);
      return {body, input};
    }
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
      input = el('input', {type: 'date', id, value: local[field.key] || '', onchange: (e) => set(e.target.value || null)});
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
    const wide = field.kind === 'textarea' || field.kind === 'file';
    const classes = 'field' + (wide ? ' wide' : '') + (field.row_start ? ' row-start' : '');
    const wrap = el('div', {class: classes, 'data-path': fieldPath},
      made.labelInside ? null : el('label', {for: made.input.id, class: field.required ? 'required' : ''},
        field.label),
      made.body,
      field.reference === 'target' ? el('div', {class: 'helper'}) : null,
      error);
    grid.append(wrap);
    app.rendered.push({field, local, path: fieldPath, wrap, error, grid, ...made});
  }
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
    if (['select', 'reference', 'target_choice', 'substrate_choice'].includes(kind) && document.activeElement !== r.input) {
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
    if (r.field.reference === 'target') {
      const found = app.refs.target.find((t) => t.ref === value);
      r.wrap.querySelector('.helper').textContent = found ? found.info : '';
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
  if (key === 'substrates') {
    const name = (item.mode || NEW_SUBSTRATE) === NEW_SUBSTRATE
      ? compute('sample_user_id', item, app.form) || item.sample_name
      : item.substrate && refName('substrate', item.substrate);
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
  mode.hidden = !app.edit;
  mode.textContent = app.edit ? `Editing ${app.edit.mainfile}` : '';
}

function navSections() {
  return [...app.spec.sections.map((s) => ({key: s.key, title: s.title})), {key: 'save', title: 'Review and save'}];
}

function renderNav() {
  const nav = document.getElementById('nav');
  const items = navSections().map((s, index) => {
    const count = s.key === 'save' ? app.errors.length : errorsFor(s.key).length;
    const state = s.key === 'save' ? (count ? '' : 'done') : (count ? 'todo' : 'done');
    return el('li', {}, el('button', {
      type: 'button', class: s.key === app.current ? 'active' : '', onclick: () => go(s.key),
    }, el('span', {class: 'nav-index ' + state}, state === 'done' ? '✓' : String(index + 1)),
    el('span', {class: 'nav-title'}, s.title),
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
  app.current = key;
  window.history.replaceState(null, '', '#' + key);
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
  if (app.current === 'save') renderSave(container);
  else {
    const s = section(app.current);
    if (s.kind === 'object') renderObject(container, s);
    else if (s.kind === 'list') renderList(container, s);
    else renderSteps(container, s);
  }
  refresh();
}

function sectionHeader(s, intro) {
  return [el('h1', {}, s.title), intro ? el('p', {class: 'section-intro'}, intro) : null];
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

function renderList(container, s) {
  const intro = s.key === 'targets'
    ? 'Select the targets that are in the system and enter their target number for this run.'
    : 'Create the substrates of this run, or pick substrates that already exist.';
  const card = el('div', {class: 'card'}, sectionHeader(s, intro), el('div', {class: 'list-error', 'data-list-errors': s.key}));
  const list = app.form[s.key];
  list.forEach((item, index) => {
    card.append(itemCard(s, list, index, (body, it, path) => renderFields(body, s.fields, it, path)));
  });
  const actions = el('div', {class: 'btn-row'}, el('button', {
    type: 'button', class: 'btn btn-outlined',
    onclick: () => { list.push(newItem(s)); changed(); render(); },
  }, `+ Add ${s.item_label.toLowerCase()}`));
  if (s.key === 'targets') {
    actions.append(el('button', {type: 'button', class: 'btn btn-text', onclick: newTargetDialog}, 'New target in the database'));
    actions.append(el('button', {type: 'button', class: 'btn btn-text', onclick: loadReferences}, 'Refresh target list'));
  }
  card.append(actions);
  container.append(card);
}

function renderSteps(container, s) {
  const card = el('div', {class: 'card'}, sectionHeader(s,
    'Add the steps in the order they were done. Steps can be added more than once, e.g. for multilayers.'),
  el('div', {class: 'list-error', 'data-list-errors': s.key}));
  if (!app.form.run.system) {
    card.append(el('div', {class: 'info'}, 'Choose the PVD system under System details first: the fields of the steps depend on it.'));
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
      onclick: () => { list.push(newItem(s, key)); changed(); render(); },
    }, `+ ${variant.label}`));
  }
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

async function logbookEntries(systems) {
  const names = systems.map((s) => app.spec.logbook_sections[s]);
  const entries = await searchEntries(names);
  return entries.map((e) => ({
    entry: e,
    title: e.entry_name || e.mainfile,
    sub: `${e.mainfile} · ${String(e.entry_create_time || '').slice(0, 10)}`,
  }));
}

async function fetchLogbook(entry) {
  const response = await api(`/entries/${entry.entry_id}/archive`);
  return response.data.archive.data;
}

async function openLogbookDialog() {
  if (!app.user) return showBanner('Log in to NOMAD to open logbooks.', 'error');
  openDialog('Open logbook', el('p', {class: 'muted'}, 'Loading…'));
  try {
    const entries = await logbookEntries(app.spec.systems);
    openDialog('Open logbook', pickList(entries, async (picked) => {
      try {
        const data = await fetchLogbook(picked.entry);
        const form = await dashboard('api/form-from-archive', {data, mode: 'edit'});
        app.form = {recipe: null, ...form};
        app.edit = {upload_id: picked.entry.upload_id, entry_id: picked.entry.entry_id, mainfile: picked.entry.mainfile};
        app.upload = picked.entry.upload_id;
        app.pendingFiles = {};
        app.touched.clear();
        app.shown.clear();
        closeDialog();
        changed();
        go('run');
        showBanner(`Opened ${picked.title}. Saving overwrites this logbook.`);
      } catch (e) {
        showBanner('Could not open the logbook: ' + e.message, 'error');
      }
    }));
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
        + 'Substrates are not copied: choose the substrate in each deposition step afterwards.'),
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
            + (hasTargets ? '.' : ' and its targets.') + ' Check the targets and choose the substrates.');
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

function newTargetDialog() {
  if (!app.user) return showBanner('Log in to NOMAD to add targets.', 'error');
  const values = {name: '', material: '', manufacturer: '', purchase_date: ''};
  const message = el('p', {class: 'error'});
  const input = (key, label, type = 'text') => el('div', {class: 'field'},
    el('label', {class: key === 'material' ? 'required' : ''}, label),
    el('div', {class: 'input-wrap'}, el('input', {type, oninput: (e) => { values[key] = e.target.value; }})));
  const create = el('button', {type: 'button', class: 'btn btn-contained', onclick: async () => {
    if (!values.material) {
      message.textContent = 'Enter the material.';
      return;
    }
    create.disabled = true;
    try {
      const uploadId = await ensureUpload();
      const data = {m_def: app.spec.reference_sections.target, material: values.material};
      if (values.name) data.name = values.name;
      if (values.manufacturer) data.manufacturer = values.manufacturer;
      if (values.purchase_date) data.purchase_date = values.purchase_date + 'T00:00:00+00:00';
      const fileName = fileNameFor('target_' + (values.name || values.material) + '_' + uid().slice(0, 6)) + '.archive.json';
      const response = await putArchive(uploadId, fileName, {data}, false);
      const entry = response.processing && response.processing.entry_id;
      await loadReferences();
      if (entry) {
        const empty = app.form.targets.find((t) => !t.target);
        const ref = entryRef(uploadId, entry);
        if (empty) empty.target = ref;
        else app.form.targets.push({...newItem(section('targets')), target: ref});
      }
      closeDialog();
      changed();
      render();
      showBanner(`Target ${values.name || values.material} added to the database.`, 'success');
    } catch (e) {
      message.textContent = 'Could not create the target: ' + e.message;
      create.disabled = false;
    }
  }}, 'Create target');
  const uploadNeeded = !app.edit && (!app.upload);
  openDialog('New target in the database', [
    el('p', {class: 'muted'}, 'Creates a PLD Target entry. Do not put the target number in the name: '
      + 'it is entered per run.'),
    el('div', {class: 'grid'},
      input('material', 'Material'), input('name', 'Name (optional, defaults to material)'),
      input('manufacturer', 'Manufacturer'), input('purchase_date', 'Purchase date', 'date'),
      uploadNeeded ? el('div', {class: 'field'}, el('label', {class: 'required'}, 'Upload to store it in'),
        el('div', {class: 'input-wrap'}, uploadSelect())) : null),
    message,
    el('div', {class: 'btn-row'}, create),
  ]);
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
  card.append(el('div', {class: 'btn-row'}, save));
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
    status.replaceChildren(el('div', {class: 'banner success', style: 'margin: 8px 0 16px'},
      'Everything is filled in.'));
  }
  const save = document.getElementById('btn-save');
  if (save) {
    save.disabled = app.saving || Boolean(app.errors.length) || !app.user
      || (!app.edit && !app.upload);
    save.title = !app.user ? 'Log in to NOMAD first' : (!app.edit && !app.upload ? 'Choose an upload' : '');
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
  const inSitu = app.form.in_situ;
  for (const [path, file] of Object.entries(app.pendingFiles)) {
    const key = path.split('.').slice(1).join('.');
    const body = new FormData();
    body.append('file', file, file.name);
    await api(`/uploads/${uploadId}/raw/${directory}?wait_for_processing=false&overwrite_if_exists=true`, {
      method: 'PUT', body,
    });
    inSitu[key] = `${directory}/${file.name}`;
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
            + (file.kind === 'substrate' ? 'Check the run and sample number of the substrate.' : 'Change the run name or open the existing logbook.'));
        }
        throw e;
      }
      const label = file.kind === 'substrate' ? `Substrate ${file.file_name}` : `Logbook ${file.file_name}`;
      logLine(`${label} saved`, 'ok');
      processingMessages(response, label);
      if (file.kind === 'substrate') {
        const item = app.form.substrates.find((s) => s.uid === file.uid);
        if (item) {
          item.ref = file.reference;
          item.sample_uuid = file.archive.data.sample_uuid;
        }
      } else {
        logbookEntry = response.processing && response.processing.entry_id;
      }
    }
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

/* ----------------------------------------------------------- lifecycle */

function newLogbook(force) {
  if (!force && !window.confirm('Start a new, empty logbook? The current form is cleared.')) return;
  app.form = newForm();
  app.edit = null;
  app.pendingFiles = {};
  app.touched.clear();
  app.shown.clear();
  app.log = [];
  clearDraft();
  document.getElementById('banner').hidden = true;
  changed();
  go('run');
}

function step(offset) {
  const keys = navSections().map((s) => s.key);
  const position = keys.indexOf(app.current);
  if (offset > 0 && app.current !== 'save') app.shown.add(app.current);
  const next = keys[position + offset];
  if (next) go(next);
}

async function init() {
  document.getElementById('btn-new').addEventListener('click', () => newLogbook(false));
  document.getElementById('btn-open').addEventListener('click', openLogbookDialog);
  document.getElementById('btn-recipe').addEventListener('click', recipeDialog);
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
  const draft = loadDraft();
  if (draft) {
    app.form = draft.form;
    app.edit = draft.edit || null;
    app.upload = draft.upload || '';
    const dropped = dropPendingFiles(app.form);
    showBanner(`Your draft from ${new Date(draft.savedAt).toLocaleString()} was restored.`
      + (dropped ? ` Choose the ${dropped} in-situ file(s) again: files are only kept until the page is closed.` : ''),
    '', {label: 'Discard draft', run: () => newLogbook(true)});
  } else {
    app.form = newForm();
  }
  const linked = window.location.hash.slice(1);
  if (navSections().some((s) => s.key === linked)) app.current = linked;
  app.errors = validate(app.form, app.spec);
  render();
  await loadUser();
  await Promise.all([loadReferences(), loadUploads()]);
  if (app.current === 'save') render();
  else refresh();
}

init();
