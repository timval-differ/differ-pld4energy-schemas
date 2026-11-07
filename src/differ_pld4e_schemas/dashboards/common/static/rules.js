// @ts-check
/*
 * Computed values and validation of a logbook form, for live feedback in the
 * browser. They mirror common/rules.py (and samples.py, values.py), which the
 * server applies again before it builds the archive files.
 *
 * `createRules(ctx)` is the counterpart of `LogbookRules`: the rules read the
 * form definition (`ctx.spec`) and the entries found in NOMAD (`ctx.refs`)
 * when they run, so the page passes its state object, which it changes in
 * place, and tests pass a plain object.
 */

import {LEVELS, MADE_HERE, NEW_SAMPLE} from './constants.js';
import {pad, uploadOfRef} from './util.js';

/**
 * @typedef {object} RulesContext
 * @property {any} spec the form definition served by api/spec
 * @property {{target: any[], sample: any[]}} refs entries found in NOMAD,
 *   as {ref, material} (targets) and {ref, sampleId, sampleName} (samples)
 */

/**
 * @param {RulesContext} ctx
 */
export function createRules(ctx) {
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
    return ctx.refs.sample.find((r) => r.ref === item.sample) || {};
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

  /* The films grown on a sample: one per film step on it (mirror LogbookRules.sample_films). */
  function sampleFilms(item, root) {
    const material = (target) => {
      const selected = (root.targets || []).find((t) => t.target === target);
      return (selected && selected.material) || (ctx.refs.target.find((r) => r.ref === target) || {}).material;
    };
    const all = ctx.spec.client.all_samples.includes((root.run || {}).system);
    return (root.steps || [])
      .filter((step) => ctx.spec.client.film_steps.includes(step.type) && (all || step.sample === sampleChoice(item)))
      .map((step) => ({target: step.target, material: material(step.target), ...filmThickness(step)}));
  }

  /* In nm or as a number of pulses (mirror rules.film_thickness). */
  function filmThickness(step) {
    return step.film_thickness_unit === 'pulses'
      ? {pulses: step.film_thickness_pulses} : {thickness: step.film_thickness};
  }

  function sampleName(item, root) {
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
      const pulses = toNumber(film.pulses);
      if (thickness !== null) parts.push(`${film.material}-${Number(thickness.toPrecision(6))}nm`);
      else if (pulses !== null) parts.push(`${film.material}-${Number(pulses.toPrecision(6))}p`);
      else parts.push(film.material);
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

  /* Values a measurement uses to name process steps (mirror rules.step_choices). */
  function stepChoices(root) {
    return (root.steps || []).filter((s) => s.uid).map((s) => s.uid);
  }

  /* What one step needs of an aspect (e.g. the laser): an optional one counts once used. */
  function stepLevel(variant, item, aspect) {
    const level = variant[aspect] || 'none';
    return level === 'optional' && item[`${aspect}_used`] ? 'required' : level;
  }

  /* 'required', 'optional' or 'none': a section with a `requirement` follows the steps. */
  function sectionRequirement(s, data) {
    if (!s.requirement) return 'required';
    const steps = ctx.spec.sections.find((x) => x.kind === 'variant_list');
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
      if ('max' in field && number > field.max) return `Must be at most ${field.max}.`;
    } else if (kind === 'select') {
      if (!fieldOptions(field, local, root).includes(value)) return 'Choose one of the options.';
    } else if (kind === 'date') {
      if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return 'Enter a date.';
    } else if (kind === 'time') {
      if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(value)) return 'Enter a time (hh:mm).';
    } else if (kind === 'reference' && field.database) {
      const database = ctx.spec.database_upload_id;
      if (!database) return 'The target and substrate database is not set up in NOMAD yet. Ask a maintainer.';
      if (uploadOfRef(value) !== database) return 'Choose one from the target and substrate database.';
    } else if (kind === 'target_choice') {
      if (!targetChoices(root).includes(value)) return 'Choose one of the targets selected under Targets.';
    } else if (kind === 'sample_choice') {
      if (!sampleChoices(root).includes(value)) return 'Choose one of the samples under Samples.';
    } else if (kind === 'step_choice') {
      const steps = stepChoices(root);
      if (!value.every((v) => steps.includes(v))) return 'Choose steps listed under Process steps.';
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
    errors.push(...stepTimeErrors(data));
    return errors;
  }

  function clockMinutes(value) {
    return /^([01]\d|2[0-3]):[0-5]\d$/.test(value || '')
      ? Number(value.slice(0, 2)) * 60 + Number(value.slice(3)) : null;
  }

  /*
   * [start, end] of each step in minutes from the run's day, null where not
   * given (mirror values.step_times): a time far (12 h) before the time before
   * it is on the next day, e.g. 00:10 after 23:30.
   */
  function stepMoments(data) {
    const run = data.run || {};
    const day = 24 * 60;
    let previous = /^\d{4}-\d{2}-\d{2}$/.test(run.date || '') ? clockMinutes(run.time) : null;
    return (data.steps || []).map((step) => ['start_time', 'end_time'].map((key) => {
      const clock = clockMinutes(step[key]);
      if (clock === null || previous === null) return null;
      let moment = Math.floor(previous / day) * day + clock;
      if (previous - moment > 12 * 60) moment += day;
      previous = moment;
      return moment;
    }));
  }

  /* Steps that end before they start (mirror rules._validate_step_times). */
  function stepTimeErrors(data) {
    const errors = [];
    stepMoments(data).forEach(([start, end], index) => {
      if (start !== null && end !== null && end < start) {
        errors.push({path: `steps.${index}.end_time`, message: 'The end time is before the start time.'});
      }
    });
    return errors;
  }

  /*
   * Steps that start before the step before them ends (mirror
   * rules.step_time_warnings). Only a warning: saving still works.
   */
  function stepTimeWarnings(data) {
    const moments = stepMoments(data);
    const warnings = [];
    for (let index = 1; index < moments.length; index++) {
      const start = moments[index][0];
      const previousEnd = moments[index - 1][1];
      if (start !== null && previousEnd !== null && start < previousEnd) {
        warnings.push({path: `steps.${index}.start_time`, message: 'Starts before the previous step ends.'});
      }
    }
    return warnings;
  }

  /* 24-hour hh:mm from what was typed, e.g. 930, 9:30 or 9.30 → 09:30; else as typed. */
  function normalTime(value) {
    const match = /^(\d{1,2})[:.]?(\d{2})$/.exec((value || '').trim());
    if (!match) return value;
    const time = `${match[1].padStart(2, '0')}:${match[2]}`;
    return clockMinutes(time) === null ? value : time;
  }

  /* What a draft needs (mirror rules.validate_draft): it names the draft file. */
  function validateDraft(data) {
    const run = data.run || {};
    const errors = [];
    if (!ctx.spec.systems.includes(run.system)) errors.push({path: 'run.system', message: 'Choose the PVD system.'});
    if (!/^\d{4}-\d{2}-\d{2}$/.test(run.date || '')) errors.push({path: 'run.date', message: 'Enter a date.'});
    if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(run.time || '')) errors.push({path: 'run.time', message: 'Enter a time (hh:mm).'});
    return errors;
  }

  return {
    lookup,
    evaluate,
    fieldOptions,
    toNumber,
    compute,
    madeHere,
    sampleNumber,
    existingSample,
    sampleId,
    sampleChoice,
    sampleFilms,
    filmThickness,
    sampleName,
    valueOf,
    isEmpty,
    targetChoices,
    sampleChoices,
    stepChoices,
    stepLevel,
    sectionRequirement,
    fieldError,
    validateFields,
    validate,
    clockMinutes,
    stepMoments,
    stepTimeErrors,
    stepTimeWarnings,
    normalTime,
    validateDraft,
  };
}
