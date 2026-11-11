// Tests of the form rules (static/rules.js) on a small form definition. The
// real definitions of both dashboards are compared with the Python rules in
// the parity tests. Run with `npm test`.
import assert from 'node:assert/strict';
import {describe, test} from 'node:test';

import {createRules} from '../../src/differ_pld4e_schemas/dashboards/common/static/rules.js';

const DATABASE = 'db-upload';
const SPEC = {
  systems: ['SA-PLD', 'LA-PLD'],
  database_upload_id: DATABASE,
  client: {film_steps: ['deposition'], mask_systems: ['SA-PLD']},
  sections: [
    {
      key: 'run', kind: 'object', fields: [
        {key: 'system', label: 'System', kind: 'select', options: ['SA-PLD', 'LA-PLD'], required: true},
        {key: 'date', label: 'Date', kind: 'date', required: true},
        {key: 'time', label: 'Time', kind: 'time', required: true},
        {key: 'name', label: 'Name', kind: 'text'},
      ],
    },
    {
      key: 'samples', kind: 'list', item_label: 'Sample', min_items: 1, unique: ['sample_id', 'sample'],
      fields: [
        {key: 'origin', label: 'Sample', kind: 'select', options: ['New sample', 'External sample', 'Existing sample']},
        {key: 'sample', label: 'Existing sample', kind: 'reference', required: true,
          visible_if: {key: 'origin', in: ['Existing sample']}},
        {key: 'substrate', label: 'Substrate', kind: 'reference', database: true, required: true,
          visible_if: {key: 'origin', in: ['New sample', 'External sample']},
          required_if: {key: 'origin', in: ['New sample']}},
        {key: 'sample_id', label: 'Sample ID', kind: 'computed', compute: 'sample_id'},
        {key: 'name', label: 'Sample name', kind: 'computed', compute: 'sample_name'},
      ],
    },
    {
      key: 'laser', kind: 'object', requirement: {from_steps: 'laser'}, fields: [
        {key: 'energy', label: 'Energy', kind: 'number', min: 0, max: 1000, required: true},
        {key: 'pulses', label: 'Pulses', kind: 'integer', required: true},
      ],
    },
    {
      key: 'targets', kind: 'list', item_label: 'Target', requirement: {from_steps: 'targets'}, fields: [
        {key: 'target', label: 'Target', kind: 'reference', database: true, required: true},
      ],
    },
    {
      key: 'steps', kind: 'variant_list', item_label: 'Step', variants: {
        heating: {laser: 'none', targets: 'none', fields: [
          {key: 'start_time', label: 'Start', kind: 'time'},
          {key: 'end_time', label: 'End', kind: 'time'},
        ]},
        deposition: {laser: 'required', targets: 'required', fields: [
          {key: 'target', label: 'Target', kind: 'target_choice', required: true},
          {key: 'sample', label: 'Sample', kind: 'sample_choice', required: true,
            visible_if: {key: '/run/system', equals: 'LA-PLD'}},
          {key: 'samples', label: 'Samples covered', kind: 'sample_mask', required: true,
            visible_if: {key: '/run/system', equals: 'SA-PLD'}},
          {key: 'film_thickness', label: 'Thickness', kind: 'number', required: true},
          {key: 'start_time', label: 'Start', kind: 'time'},
          {key: 'end_time', label: 'End', kind: 'time'},
        ]},
        ablation: {laser: 'optional', targets: 'none', fields: []},
      },
    },
  ],
};

const SUBSTRATE = `../uploads/${DATABASE}/archive/si#/data`;
const TARGET = `../uploads/${DATABASE}/archive/sto#/data`;

function form(changes = {}) {
  return {
    run: {system: 'LA-PLD', date: '2026-10-22', time: '09:15'},
    samples: [{uid: 's1', origin: 'New sample', substrate: SUBSTRATE, substrate_material: 'Si'}],
    laser: {energy: '420', pulses: '1000'},
    targets: [{uid: 't1', target: TARGET, material: 'SrTiO3'}],
    steps: [
      {uid: 'h', type: 'heating', start_time: '09:20', end_time: '10:00'},
      {uid: 'd', type: 'deposition', target: TARGET, sample: 'new:s1', film_thickness: '20', start_time: '10:00', end_time: '10:30'},
    ],
    ...changes,
  };
}

function rules(refs = {target: [], sample: []}) {
  return createRules({spec: SPEC, refs});
}

const paths = (errors) => errors.map((e) => e.path).sort();

describe('conditions', () => {
  const {lookup, evaluate} = rules();
  const root = {run: {system: 'SA-PLD'}, steps: [{type: 'heating'}, {type: 'deposition'}]};

  test('look up a key of the item, or a path from the form', () => {
    assert.equal(lookup('origin', {origin: 'x'}, root), 'x');
    assert.equal(lookup('/run/system', {}, root), 'SA-PLD');
    assert.equal(lookup('/run/missing/deeper', {}, root), undefined);
  });

  test('equals, in, has_type, all and any', () => {
    assert.equal(evaluate(undefined, {}, root), true);
    assert.equal(evaluate({key: 'on', equals: true}, {on: 'yes'}, root), true);
    assert.equal(evaluate({key: 'on', equals: false}, {}, root), true);
    assert.equal(evaluate({key: 'a', equals: 'x'}, {a: 'x'}, root), true);
    assert.equal(evaluate({key: '/run/system', in: ['LA-PLD']}, {}, root), false);
    assert.equal(evaluate({key: '/steps', has_type: ['deposition']}, {}, root), true);
    assert.equal(evaluate({all: [{key: 'a', equals: 'x'}, {key: 'b', equals: 'y'}]}, {a: 'x', b: 'z'}, root), false);
    assert.equal(evaluate({any: [{key: 'a', equals: 'x'}, {key: 'b', equals: 'y'}]}, {a: 'x', b: 'z'}, root), true);
    assert.throws(() => evaluate({key: 'a', like: 'x'}, {}, root), /Unknown condition/);
  });
});

describe('numbers and times', () => {
  const {toNumber, clockMinutes, normalTime, stepMoments} = rules();

  test('numbers as typed in the form', () => {
    assert.equal(toNumber('1.5'), 1.5);
    assert.equal(toNumber(' 1,5 '), 1.5);
    assert.equal(toNumber('-2e-3'), -0.002);
    assert.equal(toNumber('.5'), 0.5);
    assert.equal(toNumber(7), 7);
    for (const value of ['', 'abc', '1.2.3', true, null, undefined, NaN, Infinity, {}]) {
      assert.equal(toNumber(value), null, String(value));
    }
  });

  test('numbers the server would not take are not numbers', () => {
    for (const value of ['1e400', '-1e999', '1_000', '1,000,5', '١٢', '0x10', 'Infinity', 'NaN', '1 000']) {
      assert.equal(toNumber(value), null, value);
    }
  });

  test('dates are real dates written yyyy-mm-dd', () => {
    const {isDate} = rules();
    for (const value of ['2026-10-22', '2024-02-29', '2000-02-29']) assert.equal(isDate(value), true, value);
    for (const value of ['2026-02-30', '2025-02-29', '1900-02-29', '2026-13-01', '2026-00-10', '20261022',
      '2026-W43-4', '2026-10-22T09:15', ' 2026-10-22', '0000-01-01', '', null, 20261022]) {
      assert.equal(isDate(value), false, String(value));
    }
  });

  test('clock times and what was typed for them', () => {
    assert.equal(clockMinutes('09:30'), 570);
    assert.equal(clockMinutes('24:00'), null);
    assert.equal(normalTime('930'), '09:30');
    assert.equal(normalTime('9.30'), '09:30');
    assert.equal(normalTime(' 23:59 '), '23:59');
    assert.equal(normalTime('25:00'), '25:00');
    assert.equal(normalTime('soon'), 'soon');
  });

  test('step times continue on the next day after midnight', () => {
    const data = form({
      run: {system: 'LA-PLD', date: '2026-10-22', time: '22:00'},
      steps: [{type: 'heating', start_time: '23:30', end_time: '00:10'}, {type: 'heating', start_time: '00:15'}],
    });
    const day = 24 * 60;
    assert.deepEqual(stepMoments(data), [[23 * 60 + 30, day + 10], [day + 15, null]]);
    assert.deepEqual(stepMoments(form({run: {}})), [[null, null], [null, null]]);
  });
});

describe('samples', () => {
  test('a new sample gets an ID from the run and its place among the new samples', () => {
    const {sampleId} = rules();
    const data = form();
    data.samples.push({uid: 's2', origin: 'Existing sample', sample: 'x'}, {uid: 's3', origin: 'External sample'});
    assert.equal(sampleId(data.samples[0], data), 'LA-PLD_2026-10-22_09:15_S01');
    assert.equal(sampleId(data.samples[2], data), 'LA-PLD_2026-10-22_09:15_S02');
    assert.equal(sampleId(data.samples[0], form({run: {system: 'LA-PLD', date: '2026-10-22'}})), null);
  });

  test('a saved sample keeps its ID', () => {
    const {sampleId} = rules();
    const item = {uid: 's1', ref: 'saved', sample_id: 'LA-PLD_2026-01-01_08:00_S03'};
    assert.equal(sampleId(item, form()), 'LA-PLD_2026-01-01_08:00_S03');
  });

  test('an existing sample shows the ID of its entry', () => {
    const {sampleId, sampleName} = rules({target: [], sample: [{ref: 'old', sampleId: 'OLD_S01', sampleName: 'Old'}]});
    const item = {uid: 'e', origin: 'Existing sample', sample: 'old'};
    assert.equal(sampleId(item, form()), 'OLD_S01');
    assert.equal(sampleName(item, form()), 'Old');
  });

  test('the name lists the substrate and the films, in nm or pulses', () => {
    const {sampleName} = rules();
    const data = form();
    assert.equal(sampleName(data.samples[0], data), 'Si_SrTiO3-20nm');
    data.steps[1] = {...data.steps[1], film_thickness_unit: 'pulses', film_thickness_pulses: '1500'};
    assert.equal(sampleName(data.samples[0], data), 'Si_SrTiO3-1500p');
    const external = {uid: 'x', origin: 'External sample', substrate_details: 'MgO',
      prior_films: [{material: 'SrRuO3', thickness: '12.5'}, {material: 'Pt'}]};
    assert.equal(sampleName(external, form({samples: [external]})), 'MgO_SrRuO3-12.5nm_Pt');
    assert.equal(sampleName({uid: 'n', origin: 'New sample'}, data), null);
  });

  test('a film takes the material of its target as selected in the form, like the server', () => {
    const data = form();
    assert.deepEqual(rules().sampleFilms(data.samples[0], data), [{target: TARGET, material: 'SrTiO3', thickness: '20'}]);
    // Not from the entry in NOMAD: the server does not look it up (the page
    // copies it into the form instead).
    const missing = form({targets: [{uid: 't1', target: TARGET}, {uid: 't2', target: TARGET, material: 'Later'}]});
    const withEntries = rules({target: [{ref: TARGET, material: 'STO'}], sample: []});
    assert.equal(withEntries.sampleFilms(missing.samples[0], missing)[0].material, undefined);
  });

  test('film thicknesses in the name are written like Python writes them', () => {
    const {gText} = rules();
    const cases = {
      0: '0', 20: '20', 12.5: '12.5', 0.1: '0.1', 100000: '100000', 123456.7: '123457',
      1234567: '1.23457e+06', 1e6: '1e+06', 0.0001: '0.0001', 0.00005: '5e-05',
      1.5e-7: '1.5e-07', 1e21: '1e+21', [-2.5]: '-2.5', 999999.5: '1e+06',
    };
    for (const [value, text] of Object.entries(cases)) assert.equal(gText(Number(value)), text, value);
  });

  test('on a system with a sample mask, only the ticked samples get the film', () => {
    const data = form({run: {system: 'SA-PLD', date: '2026-10-22', time: '09:15'}});
    data.samples.push({uid: 's2', origin: 'New sample'});
    data.steps[1].sample = undefined;
    data.steps[1].samples = ['new:s1', 'new:s2'];
    assert.equal(rules().sampleFilms(data.samples[1], data).length, 1);
    data.steps[1].samples = ['new:s1'];
    assert.equal(rules().sampleFilms(data.samples[0], data).length, 1);
    assert.equal(rules().sampleFilms(data.samples[1], data).length, 0);
  });

  test('sample masks follow the samples of the run', () => {
    const {syncSampleMasks} = rules();
    const data = form({run: {system: 'SA-PLD', date: '2026-10-22', time: '09:15'}});
    const masks = () => data.steps.map((s) => s.samples);
    // A form just opened: a step without a mask covers every sample, the heating step has none.
    let seen = syncSampleMasks(data, null);
    assert.deepEqual(masks(), [undefined, ['new:s1']]);
    // A sample added later is ticked, also on a step where the user unticked another.
    data.samples.push({uid: 's2', origin: 'New sample'});
    seen = syncSampleMasks(data, seen);
    assert.deepEqual(data.steps[1].samples, ['new:s1', 'new:s2']);
    data.steps[1].samples = ['new:s2'];
    // A sample turned into an existing one keeps its tick, or its untick.
    const EXISTING = '../uploads/u0/archive/s0#/data';
    Object.assign(data.samples[1], {origin: 'Existing sample', sample: EXISTING});
    seen = syncSampleMasks(data, seen);
    assert.deepEqual(data.steps[1].samples, [EXISTING]);
    Object.assign(data.samples[0], {origin: 'Existing sample', sample: undefined});
    seen = syncSampleMasks(data, seen);
    assert.deepEqual(data.steps[1].samples, [EXISTING]);
    // An existing sample is ticked once it is picked; a removed sample is unticked.
    data.samples[0].sample = '../uploads/u0/archive/s9#/data';
    seen = syncSampleMasks(data, seen);
    assert.deepEqual(data.steps[1].samples, ['../uploads/u0/archive/s9#/data', EXISTING]);
    data.samples.pop();
    seen = syncSampleMasks(data, seen);
    assert.deepEqual(data.steps[1].samples, ['../uploads/u0/archive/s9#/data']);
    // A sample the step was saved with but not in the run is kept, for the page to show.
    data.steps[1].samples.push('../uploads/u0/archive/old#/data');
    syncSampleMasks(data, seen);
    assert.deepEqual(data.steps[1].samples, ['../uploads/u0/archive/s9#/data', '../uploads/u0/archive/old#/data']);
  });

  test('a sample mask must name samples of the run, at least one', () => {
    const data = form({run: {system: 'SA-PLD', date: '2026-10-22', time: '09:15'}});
    data.steps[1].sample = undefined;
    data.steps[1].samples = ['new:s1'];
    assert.deepEqual(rules().validate(data, SPEC), []);
    data.steps[1].samples = ['new:gone'];
    assert.deepEqual(rules().validate(data, SPEC).map((e) => [e.path, e.message]),
      [['steps.1.samples', 'Choose samples listed under Samples.']]);
    data.steps[1].samples = [];
    assert.deepEqual(rules().validate(data, SPEC).map((e) => [e.path, e.message]), [['steps.1.samples', 'Required.']]);
  });
});

describe('validation', () => {
  test('a complete form has no problems', () => {
    assert.deepEqual(rules().validate(form(), SPEC), []);
  });

  test('required fields, and fields required only in some cases', () => {
    // A new sample needs a substrate, an external one need not have one.
    const errors = rules().validate(form({run: {}, samples: [{uid: 's1', origin: 'New sample'}, {uid: 's2', origin: 'External sample'}]}), SPEC);
    assert.deepEqual(paths(errors), ['run.date', 'run.system', 'run.time', 'samples.0.substrate']);
  });

  test('numbers, whole numbers, limits, options, dates and times', () => {
    const errors = rules().validate(form({
      run: {system: 'XX', date: '22-10-2026', time: '9:15'},
      laser: {energy: '1200', pulses: '10.5'},
    }), SPEC);
    const messages = Object.fromEntries(errors.map((e) => [e.path, e.message]));
    assert.equal(messages['run.system'], 'Choose one of the options.');
    assert.equal(messages['run.date'], 'Enter a date.');
    assert.equal(messages['run.time'], 'Enter a time (hh:mm).');
    assert.equal(messages['laser.energy'], 'Must be at most 1000.');
    assert.equal(messages['laser.pulses'], 'Enter a whole number.');
  });

  test('database references must be in the database upload', () => {
    const data = form({targets: [{uid: 't1', target: '../uploads/elsewhere/archive/x#/data'}]});
    const errors = rules().validate(data, SPEC);
    assert.ok(errors.some((e) => e.path === 'targets.0.target' && /database/.test(e.message)));
    const noDatabase = createRules({spec: {...SPEC, database_upload_id: null}, refs: {target: [], sample: []}});
    assert.match(noDatabase.fieldError(SPEC.sections[3].fields[0], TARGET, {}, form()), /not set up/);
  });

  test('steps must choose targets, samples and steps of the form', () => {
    const data = form();
    data.steps[1] = {...data.steps[1], target: 'other', sample: 'new:nobody'};
    assert.deepEqual(paths(rules().validate(data, SPEC)), ['steps.1.sample', 'steps.1.target']);
  });

  test('sections required by the steps: none, optional or required', () => {
    const {sectionRequirement} = rules();
    const laser = SPEC.sections[2];
    assert.equal(sectionRequirement(laser, form()), 'required');
    assert.equal(sectionRequirement(laser, form({steps: [{type: 'heating'}]})), 'none');
    assert.equal(sectionRequirement(laser, form({steps: [{type: 'ablation'}]})), 'optional');
    assert.equal(sectionRequirement(laser, form({steps: [{type: 'ablation', laser_used: true}]})), 'required');
    // A section that is not needed is not validated.
    assert.deepEqual(rules().validate(form({laser: {}, targets: [], steps: [{uid: 'h', type: 'heating'}]}), SPEC), []);
  });

  test('lists: at least one item, unique values, known step types', () => {
    const data = form();
    data.samples.push({...data.samples[0], uid: 's2', origin: 'Existing sample', sample: 'x'},
      {uid: 's3', origin: 'Existing sample', sample: 'x'});
    data.steps.push({uid: 'q', type: 'teleport'});
    const errors = rules().validate(data, SPEC);
    assert.deepEqual(paths(errors), ['samples.2.sample', 'steps.2.type']);
    assert.deepEqual(paths(rules().validate(form({samples: []}), SPEC)).slice(0, 1), ['samples']);
  });

  test('a step that ends before it starts is an error, an overlap only a warning', () => {
    const {validate, stepTimeWarnings} = rules();
    const data = form();
    data.steps[0].end_time = '09:00';
    assert.deepEqual(paths(validate(data, SPEC)), ['steps.0.end_time']);
    const overlap = form();
    overlap.steps[1].start_time = '09:50';
    assert.deepEqual(validate(overlap, SPEC), []);
    assert.deepEqual(paths(stepTimeWarnings(overlap)), ['steps.1.start_time']);
  });

  test('a draft needs only the system, date and time', () => {
    const {validateDraft} = rules();
    assert.deepEqual(validateDraft(form({samples: [], steps: []})), []);
    assert.deepEqual(paths(validateDraft({run: {system: 'XX', date: '2026-1-1', time: '25:00'}})), ['run.date', 'run.system', 'run.time']);
  });

  test('the rules read the form definition when they run', () => {
    const ctx = {spec: null, refs: {target: [], sample: []}};
    const {validateDraft} = createRules(ctx);
    ctx.spec = SPEC;
    assert.deepEqual(validateDraft(form()), []);
  });
});
