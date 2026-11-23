// Tests of the PDF writer (static/pdf.js), which the page uses to export the
// logbook report. Run with `npm test`.
import assert from 'node:assert/strict';
import {test} from 'node:test';

import {makePdf} from '../../src/differ_pld4e_schemas/dashboards/common/static/pdf.js';

/* The PDF as text: everything in it is ASCII. */
async function pdfText(blocks, title = 'Logbook') {
  const blob = makePdf(blocks, title);
  assert.equal(blob.type, 'application/pdf');
  return blob.text();
}

/* The strings shown with Tj, unescaped back to character codes. */
function shownTexts(pdf) {
  return [...pdf.matchAll(/\((.*?)(?<!\\)\) Tj/g)].map(([, s]) => s
    .replace(/\\([0-7]{3})/g, (_, octal) => String.fromCharCode(parseInt(octal, 8)))
    .replace(/\\([\\()])/g, '$1'));
}

function pageCount(pdf) {
  return Number(/\/Type \/Pages \/Kids \[[^\]]*\] \/Count (\d+)/.exec(pdf)[1]);
}

const REPORT = [
  {kind: 'title', text: 'LA-PLD 2026-10-22 09:15'},
  {kind: 'heading', text: 'Run'},
  {kind: 'row', label: 'Operator', value: 'Ada Lovelace'},
  {kind: 'row', label: 'Base pressure', value: '1e-8 mbar'},
];

test('a report is a complete PDF', async () => {
  const pdf = await pdfText(REPORT);
  assert.match(pdf, /^%PDF-1\.4\n/);
  assert.match(pdf, /%%EOF\n$/);
  assert.equal(pageCount(pdf), 1);
  assert.match(pdf, /\/BaseFont \/Helvetica \/Encoding \/WinAnsiEncoding/);
  assert.deepEqual(shownTexts(pdf).slice(0, 4), ['LA-PLD 2026-10-22 09:15', 'Run', 'Operator', 'Ada Lovelace']);
});

test('the cross-reference table points at every object', async () => {
  const pdf = await pdfText(REPORT);
  const xref = Number(/startxref\n(\d+)\n/.exec(pdf)[1]);
  assert.ok(pdf.startsWith('xref\n', xref));
  const offsets = [...pdf.slice(xref).matchAll(/^(\d{10}) 00000 n $/gm)].map(([, o]) => Number(o));
  assert.ok(offsets.length > 4);
  offsets.forEach((offset, i) => assert.ok(pdf.startsWith(`${i + 1} 0 obj\n`, offset), `object ${i + 1}`));
  const size = Number(/\/Size (\d+)/.exec(pdf)[1]);
  assert.equal(size, offsets.length + 1);
});

test('stream lengths match their content', async () => {
  const pdf = await pdfText(REPORT);
  for (const [, length, content] of pdf.matchAll(/<< \/Length (\d+) >>\nstream\n([\s\S]*?)\nendstream/g)) {
    assert.equal(content.length, Number(length));
  }
});

test('text is in the Windows Latin-1 encoding', async () => {
  const pdf = await pdfText([{kind: 'row', label: 'Bow (µm)', value: 'SrTiO₃ – 5 °C “ok” 漢'}]);
  const [label, value] = shownTexts(pdf);
  assert.equal(label, 'Bow (\xb5m)');
  // Subscript digits as digits, the en dash and quotes in their Windows codes,
  // characters the fonts do not have as '?'.
  assert.equal(value, 'SrTiO3 \x96 5 \xb0C \x93ok\x94 ?');
  // Only ASCII in the file: other codes are written as octal escapes.
  assert.match(pdf, /\(Bow \\\(\\265m\\\)\) Tj/);
  assert.ok(/^[\x00-\x7f]*$/.test(pdf));
});

test('parentheses and backslashes are escaped', async () => {
  const pdf = await pdfText([{kind: 'note', text: 'a (b) c\\d'}]);
  assert.match(pdf, /\(a \\\(b\\\) c\\\\d\) Tj/);
  assert.equal(shownTexts(pdf)[0], 'a (b) c\\d');
});

test('long text is wrapped, and a long word is cut', async () => {
  const words = Array.from({length: 60}, (_, i) => `word${i}`).join(' ');
  const pdf = await pdfText([{kind: 'note', text: words}, {kind: 'note', text: 'x'.repeat(400)}]);
  const lines = shownTexts(pdf).filter((line) => !line.includes('page'));
  assert.ok(lines.length > 4);
  assert.equal(lines.filter((line) => line.startsWith('word')).join(' '), words);
  assert.equal(lines.filter((line) => line.startsWith('x')).join(''), 'x'.repeat(400));
});

test('a long report gets more pages, each numbered', async () => {
  const rows = Array.from({length: 150}, (_, i) => ({kind: 'row', label: `Field ${i}`, value: `${i}`}));
  const pdf = await pdfText([{kind: 'heading', text: 'Steps'}, ...rows], 'Run 1');
  const pages = pageCount(pdf);
  assert.ok(pages >= 3, `${pages} pages`);
  const numbers = shownTexts(pdf).filter((line) => line.startsWith('Run 1 \xb7 page'));
  assert.deepEqual(numbers, Array.from({length: pages}, (_, i) => `Run 1 \xb7 page ${i + 1} of ${pages}`));
});

test('a heading is not left alone at the bottom of a page', async () => {
  // However many rows come before it, so the heading lands at every place on
  // the page, including its bottom.
  for (let count = 40; count <= 90; count += 1) {
    const rows = Array.from({length: count}, (_, i) => ({kind: 'row', label: `Field ${i}`, value: `${i}`}));
    const pdf = await pdfText([...rows, {kind: 'heading', text: 'Next section'}, {kind: 'row', label: 'a', value: 'b'}]);
    const streams = [...pdf.matchAll(/stream\n([\s\S]*?)\nendstream/g)].map(([, s]) => s);
    const pageWithHeading = streams.find((s) => s.includes('(Next section) Tj'));
    assert.ok(pageWithHeading.includes('(a) Tj'), `after ${count} rows`);
  }
});

test('line breaks in a value start new lines', async () => {
  // Comments typed in a textarea: '\n' from the browser, '\r\n' when pasted
  // from or saved on Windows.
  const pdf = await pdfText([
    {kind: 'row', label: 'Comments', value: 'Comment 1\nComment 2\r\nComment 3\n\nComment 4'},
  ]);
  const lines = shownTexts(pdf).filter((line) => !line.includes('page'));
  assert.deepEqual(lines, ['Comments', 'Comment 1', 'Comment 2', 'Comment 3', '', 'Comment 4']);
});

/* A plot as charts.js's chartPlots gives it, with the file as its caption. */
const CHART = {
  kind: 'chart', title: 'ROI intensity', caption: 'step1.txt', xTitle: 'Time (s)', yTitle: 'Intensity (a.u.)',
  x: [0, 1, 2, 3], series: [{name: 'ROI 1', values: [1, 2, NaN, 4]}, {name: 'ROI 2', values: [2, 3, 4, 5]}],
};

test('a chart is drawn as lines, with its axes and legend', async () => {
  const pdf = await pdfText([...REPORT, CHART]);
  assert.equal(pageCount(pdf), 1);
  const texts = shownTexts(pdf);
  for (const t of ['ROI intensity', 'step1.txt', 'ROI 1', 'ROI 2', 'Time (s)', 'Intensity (a.u.)', '0', '3', '5']) {
    assert.ok(texts.includes(t), t);
  }
  // A path per series in its colour (charts.js's first two), broken at the missing value.
  const paths = [...pdf.matchAll(/([\d.]+ [\d.]+ [\d.]+) RG 0\.8 w 1 j 1 J\n([\s\S]*?)S/g)];
  assert.deepEqual(paths.map(([, colour]) => colour), ['0.165 0.471 0.839', '0.922 0.408 0.204']);
  assert.deepEqual(paths[0][2].trim().split('\n').map((op) => op.split(' ')[2]), ['m', 'l', 'm']);
  assert.deepEqual(paths[1][2].trim().split('\n').map((op) => op.split(' ')[2]), ['m', 'l', 'l', 'l']);
  // The y title reads upwards.
  assert.match(pdf, /0 1 -1 0 [\d.]+ [\d.]+ Tm \(Intensity \\\(a\.u\.\\\)\) Tj/);
  assert.ok(/^[\x00-\x7f]*$/.test(pdf));
});

test('one series has no legend; a chart that does not fit starts a new page', async () => {
  const single = {...CHART, series: [CHART.series[1]]};
  const rows = Array.from({length: 50}, (_, i) => ({kind: 'row', label: `Field ${i}`, value: `${i}`}));
  const pdf = await pdfText([...rows, single]);
  assert.ok(!shownTexts(pdf).includes('ROI 2'));
  assert.equal(pageCount(pdf), 2);
  const streams = [...pdf.matchAll(/stream\n([\s\S]*?)\nendstream/g)].map(([, s]) => s);
  assert.ok(streams[1].includes('(ROI intensity) Tj') && streams[1].includes(' RG '));
  // Everything on the second page stays between its margins.
  const ys = [...streams[1].matchAll(/([\d.]+) ([\d.]+) [ml]\n/g)].map(([, , yv]) => Number(yv));
  assert.ok(Math.min(...ys) > 50 && Math.max(...ys) < 841.89 - 50);
});

test('a report with charts is still a well-formed PDF', async () => {
  const pdf = await pdfText([...REPORT, CHART, CHART, CHART, CHART]);
  assert.ok(pageCount(pdf) >= 2);
  const xref = Number(/startxref\n(\d+)\n/.exec(pdf)[1]);
  const offsets = [...pdf.slice(xref).matchAll(/^(\d{10}) 00000 n $/gm)].map(([, o]) => Number(o));
  offsets.forEach((offset, i) => assert.ok(pdf.startsWith(`${i + 1} 0 obj\n`, offset), `object ${i + 1}`));
  for (const [, length, content] of pdf.matchAll(/<< \/Length (\d+) >>\nstream\n([\s\S]*?)\nendstream/g)) {
    assert.equal(content.length, Number(length));
  }
});

test('a chart without numbers becomes a note, not NaN in the PDF', async () => {
  const empty = {...CHART, x: [], series: [{name: 'Counts', values: []}]};
  const blank = {...CHART, series: [{name: 'ROI 1', values: [NaN, NaN, NaN, NaN]}]};
  const pdf = await pdfText([empty, blank]);
  assert.ok(!/NaN|Infinity|undefined/.test(pdf));
  const texts = shownTexts(pdf);
  assert.ok(texts.includes('ROI intensity (step1.txt): no data to plot.'));
  assert.ok(!pdf.includes(' RG '));
});
