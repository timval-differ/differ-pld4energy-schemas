/*
 * A small PDF writer for the logbook report, so the dashboard can hand out a
 * PDF without a print dialog: NOMAD shows dashboards in a sandboxed frame in
 * which browsers ignore window.print().
 *
 * It only knows what the report needs: text in the standard Helvetica fonts
 * (which every PDF reader has, so nothing is embedded), wrapped to the page
 * width, horizontal rules and page numbers. Characters outside the Windows
 * Latin-1 character set are printed as "?".
 */

/* Character widths of Helvetica and Helvetica-Bold (per 1000 units), ' ' to '~'. */
const PDF_WIDTHS = {
  regular: [
    278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278,
    556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556,
    1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778,
    667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556,
    333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556,
    556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584,
  ],
  bold: [
    278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333, 278, 278,
    556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 333, 333, 584, 584, 584, 611,
    975, 722, 722, 722, 722, 667, 611, 778, 722, 278, 556, 722, 611, 833, 722, 778,
    667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 333, 278, 333, 584, 556,
    333, 556, 611, 556, 611, 556, 333, 611, 611, 278, 278, 556, 278, 889, 611, 611,
    611, 611, 389, 556, 333, 611, 556, 778, 556, 556, 500, 389, 280, 389, 584,
  ],
};

/* Characters of the Windows Latin-1 encoding outside ISO Latin-1. */
const PDF_WIN_ANSI = {
  '€': 0x80, '‚': 0x82, '„': 0x84, '…': 0x85, '‘': 0x91, '’': 0x92, '“': 0x93,
  '”': 0x94, '•': 0x95, '–': 0x96, '—': 0x97, '™': 0x99,
};

const PDF_SUBSCRIPTS = '₀₁₂₃₄₅₆₇₈₉';

/* Text in the font's encoding: one character code per character. */
function pdfEncode(text) {
  return [...String(text)].map((c) => {
    const subscript = PDF_SUBSCRIPTS.indexOf(c);
    if (subscript >= 0) return String(subscript);
    const code = c.codePointAt(0);
    if (code >= 32 && code <= 126) return c;
    if (code >= 0xa0 && code <= 0xff) return c;
    if (PDF_WIN_ANSI[c]) return String.fromCharCode(PDF_WIN_ANSI[c]);
    return '?';
  }).join('');
}

function pdfTextWidth(text, font, size) {
  let width = 0;
  for (const c of text) {
    const code = c.charCodeAt(0);
    width += code >= 32 && code <= 126 ? PDF_WIDTHS[font][code - 32] : 556;
  }
  return (width * size) / 1000;
}

/* An encoded text as a PDF string; everything outside ASCII as octal escapes. */
function pdfString(text) {
  let out = '(';
  for (const c of text) {
    const code = c.charCodeAt(0);
    if (c === '\\' || c === '(' || c === ')') out += '\\' + c;
    else if (code < 32 || code > 126) out += '\\' + code.toString(8).padStart(3, '0');
    else out += c;
  }
  return out + ')';
}

/* Encoded text broken into lines that fit the width. */
function pdfWrap(text, font, size, width) {
  const lines = [];
  for (const paragraph of pdfEncode(text).split('\n')) {
    let line = '';
    for (const word of paragraph.split(' ')) {
      const candidate = line ? `${line} ${word}` : word;
      if (pdfTextWidth(candidate, font, size) <= width) {
        line = candidate;
        continue;
      }
      if (line) lines.push(line);
      line = word;
      // A word longer than the line (a file name, an ID) is cut where it must be.
      while (pdfTextWidth(line, font, size) > width) {
        let cut = line.length - 1;
        while (cut > 1 && pdfTextWidth(line.slice(0, cut), font, size) > width) cut -= 1;
        lines.push(line.slice(0, cut));
        line = line.slice(cut);
      }
    }
    lines.push(line);
  }
  return lines;
}

/* How each kind of block is set: font, size, grey level, space above and below. */
const PDF_STYLES = {
  title: {font: 'bold', size: 15, grey: 0, before: 0, after: 4},
  status: {font: 'bold', size: 10.5, grey: 0, before: 0, after: 2},
  alert: {font: 'bold', size: 10.5, grey: 0, red: true, before: 0, after: 2},
  note: {font: 'regular', size: 9, grey: 0.35, before: 0, after: 2},
  heading: {font: 'bold', size: 12.5, grey: 0, before: 14, after: 5, rule: true},
  subheading: {font: 'bold', size: 10.5, grey: 0, before: 8, after: 2},
  group: {font: 'bold', size: 9.5, grey: 0, before: 4, after: 1},
  row: {font: 'regular', size: 9.5, grey: 0, before: 0, after: 1.5},
};

/*
 * The report as a PDF. `blocks` is a list of {kind, text} with the kinds of
 * PDF_STYLES; a `row` has a `label` and a `value` in two columns instead.
 */
function makePdf(blocks, title) {
  const page = {width: 595.28, height: 841.89, margin: 50};
  const width = page.width - 2 * page.margin;
  const labelWidth = width * 0.38;
  const pages = [];
  let ops = null;
  let y = 0;
  const newPage = () => {
    ops = [];
    pages.push(ops);
    y = page.height - page.margin;
  };
  const text = (line, x, style) => {
    const colour = style.red ? '0.69 0 0.13 rg' : `${style.grey} g`;
    ops.push(`BT /${style.font === 'bold' ? 'F2' : 'F1'} ${style.size} Tf ${colour} `
      + `${x.toFixed(2)} ${y.toFixed(2)} Td ${pdfString(line)} Tj ET`);
  };
  newPage();
  blocks.forEach((block, index) => {
    const style = PDF_STYLES[block.kind];
    const leading = style.size * 1.25;
    let left;
    let right = [];
    if (block.kind === 'row') {
      left = pdfWrap(block.label, 'regular', style.size, labelWidth - 8);
      right = pdfWrap(block.value, 'regular', style.size, width - labelWidth);
    } else {
      left = pdfWrap(block.text, style.font, style.size, width);
    }
    let height = style.before + Math.max(left.length, right.length) * leading + style.after;
    // Headings stay on the page of what follows them.
    const next = blocks[index + 1];
    if (['heading', 'subheading', 'group'].includes(block.kind) && next) height += 2 * PDF_STYLES.row.size * 1.25;
    if (y - height < page.margin && y < page.height - page.margin) newPage();
    if (y < page.height - page.margin) y -= style.before;
    const top = y;
    left.forEach((line, i) => {
      y = top - (i + 1) * leading + style.size * 0.25;
      text(line, page.margin, block.kind === 'row' ? {...style, grey: 0.3} : style);
    });
    right.forEach((line, i) => {
      y = top - (i + 1) * leading + style.size * 0.25;
      text(line, page.margin + labelWidth, style);
    });
    y = top - Math.max(left.length, right.length) * leading;
    if (style.rule) {
      y -= 2;
      ops.push(`0.6 G 0.5 w ${page.margin} ${y.toFixed(2)} m ${page.margin + width} ${y.toFixed(2)} l S`);
    }
    y -= style.after;
  });
  // Page numbers, now that the number of pages is known.
  pages.forEach((pageOps, i) => {
    const label = pdfEncode(`${title} · page ${i + 1} of ${pages.length}`);
    const size = 8;
    ops = pageOps;
    y = page.margin / 2;
    text(label, page.width - page.margin - pdfTextWidth(label, 'regular', size), {font: 'regular', size, grey: 0.45});
  });

  // Objects 1-4: catalogue, page tree, the two fonts; then a page and its content per page.
  const font = (name) => `<< /Type /Font /Subtype /Type1 /BaseFont /${name} /Encoding /WinAnsiEncoding >>`;
  const kids = pages.map((_, i) => `${5 + 2 * i} 0 R`).join(' ');
  const objects = [
    '<< /Type /Catalog /Pages 2 0 R >>',
    `<< /Type /Pages /Kids [${kids}] /Count ${pages.length} >>`,
    font('Helvetica'),
    font('Helvetica-Bold'),
  ];
  for (const [i, pageOps] of pages.entries()) {
    const content = pageOps.join('\n');
    objects.push(`<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${page.width} ${page.height}] `
      + `/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents ${6 + 2 * i} 0 R >>`);
    objects.push(`<< /Length ${content.length} >>\nstream\n${content}\nendstream`);
  }
  objects.push(`<< /Title ${pdfString(pdfEncode(title))} /Producer (PLD4Energy logbook dashboard) >>`);

  // Everything is ASCII, so string lengths are byte offsets.
  let out = '%PDF-1.4\n';
  const offsets = objects.map((body, i) => {
    const offset = out.length;
    out += `${i + 1} 0 obj\n${body}\nendobj\n`;
    return offset;
  });
  const xref = out.length;
  out += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  out += offsets.map((o) => `${String(o).padStart(10, '0')} 00000 n \n`).join('');
  out += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R /Info ${objects.length} 0 R >>\n`;
  out += `startxref\n${xref}\n%%EOF\n`;
  return new Blob([out], {type: 'application/pdf'});
}
