// Tests of the pending data files of a form (static/files.js).
import assert from 'node:assert/strict';
import {describe, test} from 'node:test';

import {
  collectPending, displayName, fileFieldsOf, folderFor, parsePending, pendingToken, planUploads,
  stripPending, uniqueName,
} from '../../src/differ_pld4e_schemas/dashboards/common/static/files.js';

const FIELDS = {in_situ: ['rheed_files', 'mic_files'], logfiles: ['system_logfiles']};

function form() {
  return {
    in_situ: [
      {uid: 'm1', rheed_files: ['pld_files/run/in_situ/rheed_files/old.txt', pendingToken('a', 'step1.txt')]},
      {uid: 'm2', rheed_files: [pendingToken('b', 'step1.txt')], mic_files: [pendingToken('c', 'step1.txt')]},
    ],
    logfiles: {system_logfiles: [pendingToken('d', 'tsst.txt')]},
  };
}

describe('pending file tokens', () => {
  test('round trip and display name', () => {
    assert.deepEqual(parsePending(pendingToken('x1', 'a b.txt')), {id: 'x1', name: 'a b.txt'});
    assert.equal(parsePending('pld_files/a.txt'), null);
    assert.equal(parsePending(null), null);
    assert.equal(displayName(pendingToken('x1', 'a.txt')), 'a.txt');
    assert.equal(displayName('pld_files/run/a.txt'), 'a.txt');
  });

  test('unique names keep the extension', () => {
    assert.equal(uniqueName('a.txt', []), 'a.txt');
    assert.equal(uniqueName('a.txt', ['a.txt']), 'a (2).txt');
    assert.equal(uniqueName('a.txt', ['a.txt', 'a (2).txt']), 'a (3).txt');
    assert.equal(uniqueName('README', ['README']), 'README (2)');
  });

  test('a folder per field', () => {
    assert.equal(folderFor('pld_files/run', 'in_situ', 'mic_files'), 'pld_files/run/in_situ/mic_files');
  });
});

describe('collecting pending files', () => {
  test('finds every token in lists and objects', () => {
    const found = collectPending(form(), FIELDS);
    assert.deepEqual(found.map((p) => [p.id, p.section, p.field]), [
      ['a', 'in_situ', 'rheed_files'], ['b', 'in_situ', 'rheed_files'],
      ['c', 'in_situ', 'mic_files'], ['d', 'logfiles', 'system_logfiles'],
    ]);
  });

  test('a file stays with its measurement when the measurements are reordered', () => {
    const data = form();
    data.in_situ.reverse();
    const files = {a: 'A', b: 'B', c: 'C', d: 'D'};
    const plan = planUploads(data, FIELDS, files, 'dir');
    for (const group of plan) for (const f of group.files) f.target(`${group.folder}/${f.name}`);
    // Measurement m1 (now second) still has its own file, m2 its own.
    assert.deepEqual(data.in_situ[1].rheed_files, [
      'pld_files/run/in_situ/rheed_files/old.txt', 'dir/in_situ/rheed_files/step1 (2).txt']);
    assert.deepEqual(data.in_situ[0].rheed_files, ['dir/in_situ/rheed_files/step1.txt']);
  });

  test('files of one name in different techniques go to different folders', () => {
    const plan = planUploads(form(), FIELDS, {b: 'B', c: 'C'}, 'dir');
    assert.deepEqual(plan.map((g) => [g.folder, g.files.map((f) => f.name)]), [
      ['dir/in_situ/rheed_files', ['step1.txt']],
      ['dir/in_situ/mic_files', ['step1.txt']],
    ]);
  });

  test('a file already in the folder is never replaced', () => {
    const plan = planUploads(form(), FIELDS, {d: 'D'}, 'dir', {'dir/logfiles/system_logfiles': ['tsst.txt']});
    assert.equal(plan[0].files[0].name, 'tsst (2).txt');
  });

  test('tokens of files no longer at hand are removed', () => {
    const data = form();
    assert.equal(stripPending(data, FIELDS, {c: 'C'}), 3);
    assert.deepEqual(data.in_situ[0].rheed_files, ['pld_files/run/in_situ/rheed_files/old.txt']);
    assert.deepEqual(data.in_situ[1].rheed_files, []);
    assert.deepEqual(data.in_situ[1].mic_files, [pendingToken('c', 'step1.txt')]);
  });
});

test('the files fields of a form definition', () => {
  const spec = {sections: [
    {key: 'run', kind: 'object', fields: [{key: 'name', kind: 'text'}]},
    {key: 'logfiles', kind: 'object', fields: [{key: 'system_logfiles', kind: 'files'}]},
    {key: 'steps', kind: 'variant_list', variants: {a: {fields: [{key: 'f', kind: 'files'}]}, b: {fields: [{key: 'f', kind: 'files'}]}}},
  ]};
  assert.deepEqual(fileFieldsOf(spec), {logfiles: ['system_logfiles'], steps: ['f']});
});

test('an upload lands on its file also when the list changed meanwhile', () => {
  const data = form();
  const plan = planUploads(data, FIELDS, {a: 'A'}, 'dir');
  // The file before it is removed while the upload runs.
  data.in_situ[0].rheed_files.splice(0, 1);
  plan[0].files[0].target('dir/in_situ/rheed_files/step1.txt');
  assert.deepEqual(data.in_situ[0].rheed_files, ['dir/in_situ/rheed_files/step1.txt']);
});
