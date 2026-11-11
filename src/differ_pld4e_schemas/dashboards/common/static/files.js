// @ts-check
/*
 * Data files chosen in the form but not uploaded yet.
 *
 * A chosen file is kept in the form's file list as a token
 * `pending:<id>/<name>`, and the File itself in the page's map id -> File.
 * The token moves with its item when items are moved or removed, so on save a
 * file always lands in the measurement it was added to. Saving uploads each
 * file to its folder (`folderFor`) and replaces the token with the file's path
 * in the upload.
 *
 * No state, no DOM: the page passes the form and its map of files.
 */

const PENDING = /^pending:([\w-]+)\/(.+)$/;

/** @param {string} id @param {string} name */
export function pendingToken(id, name) {
  return `pending:${id}/${name}`;
}

/** {id, name} of a pending file's token, else null. */
export function parsePending(value) {
  const match = typeof value === 'string' ? PENDING.exec(value) : null;
  return match ? {id: match[1], name: match[2]} : null;
}

/** The file name to show: without the token or the folders of the upload. */
export function displayName(value) {
  const pending = parsePending(value);
  return pending ? pending.name : String(value).split('/').pop();
}

/** Whether a browser can show the file as an image, e.g. a RHEED pattern export. */
export function isImage(value) {
  return /\.(png|jpe?g|gif|bmp|webp)$/i.test(displayName(value));
}

/**
 * `name`, or `name (2).ext`, `name (3).ext`, ... if it is in `taken`.
 * @param {string} name
 * @param {Iterable<string>} taken
 */
export function uniqueName(name, taken) {
  const names = new Set(taken);
  if (!names.has(name)) return name;
  const dot = name.lastIndexOf('.');
  const [stem, ext] = dot > 0 ? [name.slice(0, dot), name.slice(dot)] : [name, ''];
  for (let n = 2; ; n++) {
    const candidate = `${stem} (${n})${ext}`;
    if (!names.has(candidate)) return candidate;
  }
}

/**
 * The folder in the upload for the files of one field, e.g.
 * `pld_files/<logbook>/in_situ/rheed_pattern_export_files`. One folder per
 * field (technique), so files of different techniques never share a name.
 * @param {string} directory @param {string} sectionKey @param {string} fieldKey
 */
export function folderFor(directory, sectionKey, fieldKey) {
  return `${directory}/${sectionKey}/${fieldKey}`;
}

/**
 * Every pending file of the form: {list, index, id, name, section, field},
 * where `list[index]` holds its token. `fileFields` maps a section key to the
 * keys of its `files` fields.
 * @param {any} form
 * @param {Object<string, string[]>} fileFields
 */
export function collectPending(form, fileFields) {
  const found = [];
  for (const [section, keys] of Object.entries(fileFields)) {
    const value = form ? form[section] : null;
    const items = Array.isArray(value) ? value : (value && typeof value === 'object' ? [value] : []);
    for (const item of items) {
      if (!item || typeof item !== 'object') continue;
      for (const field of keys) {
        const list = item[field];
        if (!Array.isArray(list)) continue;
        list.forEach((token, index) => {
          const pending = parsePending(token);
          if (pending) found.push({list, index, ...pending, section, field});
        });
      }
    }
  }
  return found;
}

/**
 * Remove the tokens of files that are no longer at hand (e.g. after a
 * reload: the browser does not keep chosen files). Returns how many.
 * @param {any} form
 * @param {Object<string, string[]>} fileFields
 * @param {Object<string, any>} [files] the files still at hand, by id
 */
export function stripPending(form, fileFields, files = {}) {
  const gone = collectPending(form, fileFields).filter((p) => !Object.hasOwn(files, p.id));
  // From the end, so the positions of the others stay valid.
  for (const p of [...gone].reverse()) p.list.splice(p.index, 1);
  return gone.length;
}

/**
 * The uploads a save makes: one per folder, with the files' final names (made
 * unique against the files already in the folder, `existing[folder]`, and
 * each other). Returns [{folder, files: [{id, name, file, target}]}], where
 * `target(path)` puts the uploaded path in place of the token. A file whose
 * upload was answered but whose answer was lost is uploaded again under a new
 * name on the next save: a copy, never a replaced file.
 * @param {any} form
 * @param {Object<string, string[]>} fileFields
 * @param {Object<string, any>} files the pending Files, by id
 * @param {string} directory
 * @param {Object<string, string[]>} [existing] file names already in each folder
 */
export function planUploads(form, fileFields, files, directory, existing = {}) {
  /** @type {Map<string, {folder: string, files: any[], taken: string[]}>} */
  const byFolder = new Map();
  for (const p of collectPending(form, fileFields)) {
    if (!Object.hasOwn(files, p.id)) continue;
    const folder = folderFor(directory, p.section, p.field);
    if (!byFolder.has(folder)) byFolder.set(folder, {folder, files: [], taken: [...(existing[folder] || [])]});
    const group = byFolder.get(folder);
    const name = uniqueName(p.name, group.taken);
    group.taken.push(name);
    const {list} = p;
    const token = list[p.index];
    group.files.push({
      id: p.id, name, file: files[p.id],
      // Found again by its token: the list may have changed during the upload.
      target: (/** @type {string} */ path) => {
        const at = list.indexOf(token);
        if (at >= 0) list[at] = path;
      },
    });
  }
  return [...byFolder.values()].map(({folder, files: groupFiles}) => ({folder, files: groupFiles}));
}

/**
 * The keys of the `files` fields of each section of a form definition, for
 * `collectPending` (files fields of steps are included per step type).
 * @param {any} spec
 */
export function fileFieldsOf(spec) {
  /** @type {Object<string, string[]>} */
  const keys = {};
  for (const section of spec.sections) {
    const fields = section.kind === 'variant_list'
      ? Object.values(section.variants).flatMap((v) => v.fields) : section.fields;
    const files = [...new Set(fields.filter((f) => f.kind === 'files').map((f) => f.key))];
    if (files.length) keys[section.key] = files;
  }
  return keys;
}
