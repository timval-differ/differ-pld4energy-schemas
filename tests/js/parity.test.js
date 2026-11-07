// The browser rules (static/rules.js) must give what the server rules give
// (common/rules.py) for the same forms: tests/js/fixtures/parity.json holds
// the forms and the Python results, written by tests/dashboards/test_js_parity.py.
// Entries found in NOMAD are left out: the server does not look them up.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {describe, test} from 'node:test';

import {createRules} from '../../src/differ_pld4e_schemas/dashboards/common/static/rules.js';

const cases = JSON.parse(readFileSync(new URL('./fixtures/parity.json', import.meta.url), 'utf8'));

const problems = (list) => list.map((p) => `${p.path}: ${p.message}`).sort();

function computedFields(spec, form) {
  const found = [];
  for (const section of spec.sections) {
    const items = section.kind === 'object'
      ? [[section.key, section.fields, form[section.key] || {}]]
      : (form[section.key] || []).map((item, index) => [
        `${section.key}.${index}`,
        section.kind === 'variant_list' ? (section.variants[item.type] || {fields: []}).fields : section.fields,
        item,
      ]);
    for (const [path, fields, local] of items) {
      for (const field of fields) {
        if (field.kind === 'computed') found.push([`${path}.${field.key}`, field.compute, local]);
      }
    }
  }
  return found;
}

function sameValue(actual, expected) {
  if (typeof actual === 'number' && typeof expected === 'number') {
    return Math.abs(actual - expected) <= 1e-9 * Math.max(1, Math.abs(expected));
  }
  return actual === expected;
}

for (const [dashboard, {spec, cases: list}] of Object.entries(cases)) {
  describe(`${dashboard} logbook: the same results as the server`, () => {
    const rules = createRules({spec, refs: {target: [], sample: []}});

    test('every computed value of the form definition is known', () => {
      const names = new Set(list.flatMap((c) => computedFields(spec, c.form).map(([, name]) => name)));
      for (const section of spec.sections) {
        const fields = section.kind === 'variant_list'
          ? Object.values(section.variants).flatMap((v) => v.fields) : section.fields;
        for (const field of fields) if (field.kind === 'computed') names.add(field.compute);
      }
      for (const name of names) assert.ok(Object.hasOwn(rules.COMPUTED, name), name);
    });

    for (const c of list) {
      test(c.name, () => {
        const form = structuredClone(c.form);
        assert.deepEqual(problems(rules.validate(form, spec)), problems(c.errors), 'errors');
        assert.deepEqual(problems(rules.stepTimeWarnings(form)), problems(c.warnings), 'warnings');
        assert.deepEqual(problems(rules.validateDraft(form)), problems(c.draft_errors), 'draft errors');
        const computed = Object.fromEntries(computedFields(spec, form)
          .map(([path, name, local]) => [path, rules.compute(name, local, form) ?? null]));
        assert.deepEqual(Object.keys(computed).sort(), Object.keys(c.computed).sort(), 'computed fields');
        for (const [path, value] of Object.entries(c.computed)) {
          assert.ok(sameValue(computed[path], value), `${path}: ${JSON.stringify(computed[path])} != ${JSON.stringify(value)}`);
        }
      });
    }
  });
}
