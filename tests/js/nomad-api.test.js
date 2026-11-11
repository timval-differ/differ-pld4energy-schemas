// Tests of the requests to NOMAD and to the dashboard (static/nomad-api.js)
// and of the path helpers in static/util.js, with a stand-in for fetch.
import assert from 'node:assert/strict';
import {afterEach, describe, test} from 'node:test';

import {
  api, dashboard, putArchive, rawFileText, readNomadDraft,
} from '../../src/differ_pld4e_schemas/dashboards/common/static/nomad-api.js';
import {
  entryRef, fileNameFor, formatNumber, uploadOfRef, uploadPath, validUploadId,
} from '../../src/differ_pld4e_schemas/dashboards/common/static/util.js';

const realFetch = globalThis.fetch;
let requests = [];

/* Answer every request with `status` and `body` (text). */
function answer(status, body) {
  requests = [];
  globalThis.fetch = async (url, options = {}) => {
    requests.push({url, options});
    return new Response(body, {status});
  };
}

afterEach(() => { globalThis.fetch = realFetch; });

describe('paths in an upload', () => {
  test('every part is encoded', () => {
    assert.equal(uploadPath('abc-_1', 'raw'), '/uploads/abc-_1/raw/');
    assert.equal(uploadPath('u1', 'raw', 'pld_drafts/a b#?.json'), '/uploads/u1/raw/pld_drafts/a%20b%23%3F.json');
    assert.equal(uploadPath('u1', 'rawdir', 'pld_drafts'), '/uploads/u1/rawdir/pld_drafts');
  });

  test('an upload id or path that leaves its place is refused', () => {
    for (const [id, path] of [['../x', 'a'], ['u1/../u2', 'a'], [undefined, 'a'], ['u1', '../a'],
      ['u1', 'a//b'], ['u1', 'a/./b'], ['u1', 'a/']]) {
      assert.throws(() => uploadPath(id, 'raw', path), undefined, `${id} ${path}`);
    }
    assert.equal(validUploadId('ab_C-1'), 'ab_C-1');
    assert.equal(validUploadId('a/b'), null);
    assert.equal(validUploadId(5), null);
  });

  test('references and file names', () => {
    assert.equal(entryRef('u1', 'e1'), '../uploads/u1/archive/e1#/data');
    assert.equal(uploadOfRef('../uploads/u1/archive/e1#/data'), 'u1');
    assert.equal(uploadOfRef('../upload/archive/mainfile/x.json#data'), null);
    assert.equal(fileNameFor('LA-PLD 2026:10'), 'LA-PLD_2026_10');
    assert.equal(formatNumber(1234.56789), '1234.57');
    assert.equal(formatNumber(null), '–');
  });
});

describe('NOMAD API', () => {
  test('sends the session cookie and asks for JSON', async () => {
    answer(200, '{"data": 1}');
    assert.deepEqual(await api('/uploads', {headers: {'X-A': 'b'}}), {data: 1});
    const [{url, options}] = requests;
    assert.equal(url, '/api/v1/uploads');
    assert.equal(options.credentials, 'same-origin');
    assert.deepEqual(options.headers, {Accept: 'application/json', 'X-A': 'b'});
  });

  test('an answer that is not JSON is given as text', async () => {
    answer(200, 'plain');
    assert.equal(await api('/x'), 'plain');
    answer(200, '');
    assert.equal(await api('/x'), null);
  });

  test('an error answer throws its detail and status', async () => {
    answer(404, '{"detail": "Upload not found"}');
    await assert.rejects(api('/x'), {message: 'Upload not found', status: 404});
    answer(422, '{"detail": [{"loc": ["q"], "msg": "bad"}]}');
    await assert.rejects(api('/x'), {message: '[{"loc":["q"],"msg":"bad"}]', status: 422});
    answer(502, '<html>Bad gateway</html>');
    await assert.rejects(api('/x'), {message: 'HTTP 502', status: 502});
  });

  test('archive files are written with the overwrite flag the server allowed', async () => {
    answer(200, '{"processing": {}}');
    await putArchive('u1', 'LA-PLD_2026-10-22_0915.archive.json', {data: {}}, false);
    const [{url, options}] = requests;
    assert.equal(url, '/api/v1/uploads/u1/raw/?file_name=LA-PLD_2026-10-22_0915.archive.json'
      + '&overwrite_if_exists=false&wait_for_processing=true');
    assert.equal(options.method, 'PUT');
    assert.equal(options.body, '{"data":{}}');
  });

  test('a draft that is not there is null; other errors are thrown', async () => {
    answer(404, '{"detail": "not found"}');
    assert.equal(await readNomadDraft('u1', 'pld_drafts/a.draft.json'), null);
    answer(500, '{"detail": "broken"}');
    await assert.rejects(readNomadDraft('u1', 'pld_drafts/a.draft.json'), /broken/);
  });

  test('raw files are read as text', async () => {
    answer(200, '1 2\n3 4');
    assert.equal(await rawFileText('u1', 'pld_files/a b.txt'), '1 2\n3 4');
    assert.equal(requests[0].url, '/api/v1/uploads/u1/raw/pld_files/a%20b.txt');
    answer(403, 'no');
    await assert.rejects(rawFileText('u1', 'x.txt'), /HTTP 403/);
  });
});

describe('dashboard API', () => {
  test('GET without a body, POST with JSON', async () => {
    answer(200, '{"sections": []}');
    assert.deepEqual(await dashboard('api/spec'), {sections: []});
    assert.equal(requests[0].options.method, 'GET');
    answer(200, '{"errors": []}');
    await dashboard('api/validate', {form: {}});
    assert.equal(requests[0].options.method, 'POST');
    assert.equal(requests[0].options.body, '{"form":{}}');
  });

  test('errors and answers without data are reported', async () => {
    answer(400, '{"detail": "Malformed form: KeyError"}');
    await assert.rejects(dashboard('api/archive', {}), /Malformed form/);
    answer(413, '<html>Too large</html>');
    await assert.rejects(dashboard('api/archive', {}), /HTTP 413/);
    answer(200, '');
    await assert.rejects(dashboard('api/spec'), /sent no data/);
  });
});

describe('raw files', () => {
  test('one file per request, never replacing a file', async () => {
    // NOMAD refuses wait_for_processing for a request with several files.
    const {putRawFile} = await import('../../src/differ_pld4e_schemas/dashboards/common/static/nomad-api.js');
    answer(200, '{}');
    await putRawFile('u1', 'pld_files/run/in_situ/mic_files', {name: 'a.csv', file: new Blob(['1'])});
    assert.equal(requests.length, 1);
    assert.match(requests[0].url, /\/uploads\/u1\/raw\/pld_files\/run\/in_situ\/mic_files\?overwrite_if_exists=false&wait_for_processing=true$/);
    assert.deepEqual(requests[0].options.body.getAll('file').map((f) => f.name), ['a.csv']);
  });

  test('the files of a missing folder are none', async () => {
    const {folderFileNames, rawExists} = await import('../../src/differ_pld4e_schemas/dashboards/common/static/nomad-api.js');
    answer(404, '{"detail": "not found"}');
    assert.deepEqual(await folderFileNames('u1', 'x'), []);
    assert.equal(await rawExists('u1', 'x.json'), false);
    answer(200, JSON.stringify({directory_metadata: {content: [{name: 'a', is_file: true}, {name: 'd', is_file: false}]}}));
    assert.deepEqual(await folderFileNames('u1', 'x'), ['a']);
    assert.equal(await rawExists('u1', 'a'), true);
  });
});

describe('changes made elsewhere', () => {
  test('a logbook is written with the hash it was read with', async () => {
    answer(200, '{}');
    await putArchive('u1', 'a.archive.json', {data: {}}, true, 'h1');
    assert.match(requests[0].url, /overwrite_if_exists=true&wait_for_processing=true&entry_hash=h1$/);
    await putArchive('u1', 'a.archive.json', {data: {}}, false);
    assert.doesNotMatch(requests[1].url, /entry_hash/);
  });

  test('the hash of an entry and the data of a file', async () => {
    const {entryHash, readArchiveData} = await import('../../src/differ_pld4e_schemas/dashboards/common/static/nomad-api.js');
    answer(200, JSON.stringify({data: {archive: {metadata: {entry_hash: 'abc'}}}}));
    assert.equal(await entryHash('e1'), 'abc');
    assert.match(requests[0].url, /\/entries\/e1\/archive\/query$/);
    assert.deepEqual(JSON.parse(requests[0].options.body), {required: {metadata: {entry_hash: '*'}}});
    answer(200, JSON.stringify({data: {name: 'x'}}));
    assert.deepEqual(await readArchiveData('u1', 'a.archive.json'), {name: 'x'});
    answer(404, '{"detail": "gone"}');
    assert.equal(await readArchiveData('u1', 'a.archive.json'), null);
    answer(200, '"not an archive"');
    await assert.rejects(readArchiveData('u1', 'a.archive.json'), /not an archive/);
  });
});
