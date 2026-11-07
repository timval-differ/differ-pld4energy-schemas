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
