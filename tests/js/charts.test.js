// Tests of reading and plotting exported data files (static/charts.js), with
// the real chart definitions of the PLD logbook and the example exports in
// tests/data/exports. Run with `npm test`.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {describe, test} from 'node:test';

import {
  CHART_POINTS, blockMean, chartPlots, decodeExport, niceTicks, readColumns,
} from '../../src/differ_pld4e_schemas/dashboards/common/static/charts.js';

const parity = JSON.parse(readFileSync(new URL('./fixtures/parity.json', import.meta.url), 'utf8'));
// As the page reads them: the bytes, decoded like in_situ.decode_export.
const exports = (path) => decodeExport(readFileSync(new URL(`../data/exports/${path}`, import.meta.url)));

/* The `chart` of the PLD fields whose files have it, by delimiter. */
function chartDefinitions() {
  const found = [];
  const walk = (fields) => fields.forEach((f) => {
    if (f.chart) found.push(f.chart);
    if (f.kind === 'rows') walk(f.columns);
  });
  for (const s of parity.pld.spec.sections) {
    walk(s.kind === 'variant_list' ? Object.values(s.variants).flatMap((v) => v.fields) : s.fields);
  }
  return found;
}
const [RHEED_CHART, MIC_CHART] = ['null', ';'].map((d) => chartDefinitions().find((c) => String(c.delimiter) === d));

describe('reading exported text files (as in_situ.read_columns)', () => {
  test('a header line, then columns of numbers', () => {
    const {header, columns} = readColumns('a;b (s)\n1;2\n\n3;4', ';');
    assert.deepEqual(header, ['a', 'b (s)']);
    assert.deepEqual(columns, [[1, 3], [2, 4]]);
  });

  test('white space between columns, Windows line ends, no header', () => {
    const {header, columns} = readColumns('0.0\t1.0\t2.0\r\n0.1 1.5 2.5\r\n');
    assert.equal(header, null);
    assert.deepEqual(columns, [[0, 0.1], [1, 1.5], [2, 2.5]]);
  });

  test('broken files are reported', () => {
    assert.throws(() => readColumns('1 2\n1 2 3'), /line 2 has 3 columns instead of 2/);
    assert.throws(() => readColumns('1 2\nx y'), /line 2 is not numbers/);
    assert.throws(() => readColumns('only a header'), /no columns of data found/);
    assert.throws(() => readColumns('1\n2'), /no columns of data found/);
    assert.throws(() => readColumns(''), /no columns of data found/);
  });
});

describe('plots', () => {
  test('long series are averaged in blocks to at most CHART_POINTS', () => {
    assert.deepEqual(blockMean([1, 3, 5, 7, 9], 2), [3, 8]);
    assert.deepEqual(blockMean([1, 2, 3], 5), [1, 2, 3]);
    const long = Array.from({length: 12000}, (_, i) => i);
    const averaged = blockMean(long, CHART_POINTS);
    assert.ok(averaged.length <= CHART_POINTS);
    assert.equal(averaged[0], (0 + 11) / 2);
  });

  test('RHEED: one series per ROI column', () => {
    const plots = chartPlots(RHEED_CHART, readColumns(exports('RHEED/step1.txt'), RHEED_CHART.delimiter));
    assert.equal(plots.length, 1);
    const [plot] = plots;
    assert.equal(plot.title, 'ROI intensity');
    assert.deepEqual(plot.series.map((s) => s.name), ['ROI 1', 'ROI 2', 'ROI 3']);
    // 2024 samples, averaged in blocks of 3.
    assert.equal(plot.x.length, 675);
    assert.equal(plot.x[0], (0 + 0.106 + 0.212) / 3);
    assert.ok(Math.abs(plot.series[0].values[0] - (98.99878 + 97.85104 + 97.89988) / 3) < 1e-9);
  });

  test('MIC: the columns named in the definition, by their header', () => {
    const plots = chartPlots(MIC_CHART, readColumns(exports('MIC/EZ-CURVE_dated_09_October_2026_timestamped_11h_51m_13s.csv'), ';'));
    assert.deepEqual(plots.map((p) => p.title), ['Stress x thickness', 'Curvature']);
    assert.deepEqual(plots[0].series.map((s) => s.name), ['Sagittal', 'Tangential']);
    assert.equal(plots[0].x.length, 300);
    assert.equal(plots[0].x[0], 0.0100000000002183);
    assert.equal(plots[0].series[1].values[0], 0.870112194638309);
    assert.equal(plots[1].series[0].values[0], 14.6924654976594);
  });

  test('a file without the expected columns is reported', () => {
    assert.throws(() => chartPlots(MIC_CHART, readColumns('a;b\n1;2', ';')), /none of the expected columns/);
  });

  test('axis ticks are round values within or around the range', () => {
    assert.deepEqual(niceTicks(0, 1), [0, 0.2, 0.4, 0.6, 0.8, 1]);
    assert.deepEqual(niceTicks(0.3, 9.7, 5), [2, 4, 6, 8]);
    assert.deepEqual(niceTicks(0.3, 9.7, 5, true), [0, 2, 4, 6, 8, 10]);
    assert.deepEqual(niceTicks(-0.0287, 34.75, 5, true), [-10, 0, 10, 20, 30, 40]);
    assert.deepEqual(niceTicks(5, 5), [5]);
    const ticks = niceTicks(0, 214.621, 5, true);
    assert.ok(ticks[0] <= 0 && ticks.at(-1) >= 214.621);
  });
});

describe('exported files as the page reads them', () => {
  test('encodings and byte order marks', () => {
    assert.equal(decodeExport(Buffer.from('Bow (µm);x\r\n1;2', 'latin1')), 'Bow (µm);x\r\n1;2');
    assert.equal(decodeExport(Buffer.from('﻿Time (s);x', 'utf8')), 'Time (s);x');
    assert.equal(decodeExport(Buffer.concat([Buffer.from([0xff, 0xfe]), Buffer.from('a;b', 'utf16le')])), 'a;b');
  });

  test('decimal commas, unless commas separate the columns', () => {
    assert.deepEqual(readColumns('0,5\t1,25e3\r1,5\t2', null).columns, [[0.5, 1.5], [1250, 2]]);
    assert.deepEqual(readColumns('1,2\n3,4', ',').columns, [[1, 3], [2, 4]]);
  });
});

test('commas in a file with decimal points are not decimal commas', () => {
  assert.throws(() => readColumns('0.5\t1.0\n1,234\t2.0', null), /not numbers/);
});
