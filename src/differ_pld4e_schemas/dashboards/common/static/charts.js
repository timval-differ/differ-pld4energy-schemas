// @ts-check
import {displayName, parsePending} from './files.js';
import {el} from './dom.js';
import {formatNumber} from './util.js';

/*
 * Exported data files (e.g. RHEED ROI intensities, MIC curvature) are plotted
 * as soon as they are added, from the file in the browser; once saved, from
 * NOMAD on request. The field's `chart` (FILE_CHARTS in spec.py) says how to
 * read the file and what to plot. The NOMAD entry plots the same data.
 */
const SERIES_COLORS = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948'];
export const CHART_POINTS = 1000;
const SVG = 'http://www.w3.org/2000/svg';

/* Header (or null) and columns of an exported text file, as in in_situ.read_columns. */
export function readColumns(text, delimiter) {
  let header = null;
  let columns = null;
  const lines = text.split(/\r?\n/);
  for (let number = 1; number <= lines.length; number++) {
    const line = lines[number - 1];
    if (!line.trim()) continue;
    const parts = delimiter ? line.split(delimiter).map((p) => p.trim()) : line.trim().split(/\s+/);
    const values = parts.map((p) => (p === '' ? NaN : Number(p)));
    if (values.some(Number.isNaN)) {
      if (columns) throw new Error(`line ${number} is not numbers`);
      header = parts;
      continue;
    }
    if (!columns) columns = values.map(() => []);
    if (values.length !== columns.length) {
      throw new Error(`line ${number} has ${values.length} columns instead of ${columns.length}`);
    }
    values.forEach((v, i) => columns[i].push(v));
  }
  if (!columns || columns.length < 2) throw new Error('no columns of data found');
  return {header, columns};
}

/* The mean of each block of samples, keeping at most `points`. */
export function blockMean(values, points) {
  const size = Math.ceil(values.length / points);
  if (size <= 1) return values;
  const means = [];
  for (let start = 0; start < values.length; start += size) {
    const block = values.slice(start, start + size);
    means.push(block.reduce((a, b) => a + b, 0) / block.length);
  }
  return means;
}

/* The plots of a chart definition: [{title, yTitle, x, series: [{name, values}]}]. */
export function chartPlots(chart, {header, columns}) {
  const name = (column) => column.split('(')[0].trim().toLowerCase();
  const x = blockMean(columns[0], CHART_POINTS);
  const plots = chart.plots.map((plot) => {
    let series;
    if (plot.columns === null) {
      series = columns.slice(1).map((values, i) => ({name: plot.name.replace('{n}', i + 1), values}));
    } else {
      series = plot.columns.map((column, i) => {
        const index = (header || []).findIndex((h) => name(h) === column.toLowerCase());
        return index < 0 ? null : {name: plot.names[i], values: columns[index]};
      }).filter(Boolean);
    }
    series = series.map((s) => ({...s, values: blockMean(s.values, CHART_POINTS)}));
    return {title: plot.title, yTitle: plot.y_title, x, series};
  }).filter((plot) => plot.series.length);
  if (!plots.length) throw new Error('none of the expected columns found');
  return plots;
}

function svgEl(tag, attrs, ...children) {
  const node = document.createElementNS(SVG, tag);
  for (const [key, value] of Object.entries(attrs || {})) node.setAttribute(key, String(value));
  node.append(...children);
  return node;
}

/* About `count` round tick values within min..max, or (outward) around it. */
export function niceTicks(min, max, count = 5, outward = false) {
  if (!(max > min)) return [min];
  const raw = (max - min) / count;
  const power = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 5, 10].map((f) => f * power).find((s) => s >= raw);
  const ticks = [];
  const first = (outward ? Math.floor(min / step) : Math.ceil(min / step)) * step;
  const last = outward ? Math.ceil(max / step) * step : max;
  for (let v = first; v <= last + step * 1e-9; v += step) {
    ticks.push(Number(v.toPrecision(12)));
  }
  return ticks;
}

/*
 * A line chart of one plot against the time, with a crosshair tooltip. It is
 * drawn at the width it gets (and redrawn when that changes), so that its text
 * keeps the size of the page's text instead of being scaled with the chart.
 */
export function lineChart(plot, fileName) {
  const H = 300;
  const m = {left: 72, right: 20, top: 12, bottom: 52};
  const {x, series} = plot;
  const color = (i) => SERIES_COLORS[i % SERIES_COLORS.length];
  const all = series.flatMap((s) => s.values).filter(Number.isFinite);
  let [yMin, yMax] = [Math.min(...all), Math.max(...all)];
  if (yMin === yMax) [yMin, yMax] = [yMin - 1, yMax + 1];
  const yTicks = niceTicks(yMin, yMax, 5, true);
  [yMin, yMax] = [yTicks[0], yTicks[yTicks.length - 1]];
  const [xMin, xMax] = [x[0], x[x.length - 1]];
  const sy = (v) => H - m.bottom - ((v - yMin) / (yMax - yMin)) * (H - m.top - m.bottom);
  const tooltip = el('div', {class: 'chart-tooltip', hidden: true});

  const draw = (W) => {
    const sx = (v) => m.left + ((v - xMin) / (xMax - xMin || 1)) * (W - m.left - m.right);
    const svg = svgEl('svg', {width: W, height: H, viewBox: `0 0 ${W} ${H}`, class: 'chart-svg', role: 'img',
      'aria-label': `${plot.title} against time, ${fileName}`});
    for (const t of yTicks) {
      svg.append(svgEl('line', {x1: m.left, x2: W - m.right, y1: sy(t), y2: sy(t), class: 'chart-grid'}),
        svgEl('text', {x: m.left - 8, y: sy(t), class: 'chart-tick', 'text-anchor': 'end', 'dominant-baseline': 'middle'},
          formatNumber(t)));
    }
    // About one time tick per 110 px.
    for (const t of niceTicks(xMin, xMax, Math.max(2, Math.floor((W - m.left - m.right) / 110)))) {
      svg.append(svgEl('line', {x1: sx(t), x2: sx(t), y1: H - m.bottom, y2: H - m.bottom + 5, class: 'chart-axis'}),
        svgEl('text', {x: sx(t), y: H - m.bottom + 20, class: 'chart-tick', 'text-anchor': 'middle'}, formatNumber(t)));
    }
    const middle = (m.top + H - m.bottom) / 2;
    svg.append(
      svgEl('line', {x1: m.left, x2: W - m.right, y1: H - m.bottom, y2: H - m.bottom, class: 'chart-axis'}),
      svgEl('text', {x: (m.left + W - m.right) / 2, y: H - 8, class: 'chart-label', 'text-anchor': 'middle'}, 'Time (s)'),
      svgEl('text', {x: 16, y: middle, class: 'chart-label', 'text-anchor': 'middle',
        transform: `rotate(-90 16 ${middle})`}, plot.yTitle));
    series.forEach((s, i) => {
      let d = '';
      let pen = 'M';
      s.values.forEach((v, j) => {
        if (!Number.isFinite(v)) { pen = 'M'; return; }
        d += `${pen}${sx(x[j]).toFixed(1)} ${sy(v).toFixed(1)}`;
        pen = 'L';
      });
      svg.append(svgEl('path', {d, class: 'chart-line', stroke: color(i)}));
    });

    // Hover: a crosshair at the nearest time, a dot per series, and a tooltip.
    const cross = svgEl('line', {y1: m.top, y2: H - m.bottom, class: 'chart-cross', visibility: 'hidden'});
    const dots = series.map((s, i) => svgEl('circle', {r: 4, class: 'chart-dot', fill: color(i), visibility: 'hidden'}));
    const hit = svgEl('rect', {x: m.left, y: m.top, width: W - m.left - m.right, height: H - m.top - m.bottom,
      fill: 'transparent'});
    svg.append(cross, ...dots, hit);
    hit.addEventListener('pointerleave', () => {
      tooltip.hidden = true;
      for (const node of [cross, ...dots]) node.setAttribute('visibility', 'hidden');
    });
    hit.addEventListener('pointermove', (e) => {
      const px = e.clientX - svg.getBoundingClientRect().left;
      const time = xMin + ((px - m.left) / (W - m.left - m.right)) * (xMax - xMin);
      let j = x.findIndex((v) => v >= time);
      if (j < 0) j = x.length - 1;
      if (j > 0 && time - x[j - 1] < x[j] - time) j -= 1;
      cross.setAttribute('x1', sx(x[j]));
      cross.setAttribute('x2', sx(x[j]));
      cross.setAttribute('visibility', 'visible');
      series.forEach((s, i) => {
        const shown = Number.isFinite(s.values[j]);
        dots[i].setAttribute('visibility', shown ? 'visible' : 'hidden');
        if (shown) { dots[i].setAttribute('cx', sx(x[j])); dots[i].setAttribute('cy', sy(s.values[j])); }
      });
      tooltip.replaceChildren(el('div', {class: 'chart-tooltip-time'}, `${formatNumber(x[j])} s`),
        ...series.map((s, i) => el('div', {class: 'chart-tooltip-row'},
          el('span', {class: 'chart-swatch', style: `background:${color(i)}`}),
          el('span', {}, s.name), el('span', {class: 'chart-tooltip-value'}, formatNumber(s.values[j])))));
      tooltip.hidden = false;
      tooltip.style.left = `${sx(x[j])}px`;
      tooltip.classList.toggle('flip', sx(x[j]) > W / 2);
    });
    return svg;
  };

  let width = 0;
  const frame = el('div', {class: 'chart-frame'}, draw(720), tooltip);
  new ResizeObserver(() => {
    const now = Math.round(frame.clientWidth);
    if (!now || now === width) return;
    width = now;
    tooltip.hidden = true;
    frame.firstChild.replaceWith(draw(Math.max(now, 320)));
  }).observe(frame);

  const legend = series.length > 1 ? el('div', {class: 'chart-legend'}, ...series.map((s, i) => el('span', {class: 'chart-key'},
    el('span', {class: 'chart-swatch', style: `background:${color(i)}`}), s.name))) : null;
  return el('figure', {class: 'chart'},
    el('figcaption', {}, el('span', {class: 'chart-title'}, plot.title), el('span', {class: 'muted small'}, fileName)),
    legend, frame);
}

/* Parsed plots by File (added here) or by path (saved in NOMAD), read once. */
const chartCache = new Map();

async function plotFile(box, chart, key, fileName, read) {
  box.replaceChildren(el('span', {class: 'muted small'}, `Reading ${fileName}…`));
  if (!chartCache.has(key)) {
    // Let the message show before a large file is parsed.
    chartCache.set(key, new Promise((resolve) => setTimeout(resolve)).then(read)
      .then((text) => chartPlots(chart, readColumns(text, chart.delimiter))));
  }
  try {
    const plots = await chartCache.get(key);
    box.replaceChildren(...plots.map((plot) => lineChart(plot, fileName)));
  } catch (error) {
    chartCache.delete(key);
    box.replaceChildren(el('span', {class: 'chart-error'}, `Could not plot ${fileName}: ${error.message}`));
  }
}

/*
 * The charts of the files of a field, redrawn only when its files change. A
 * file still to be uploaded (`pendingFiles`, by id; see files.js) is plotted from the
 * browser; a saved one on request, read from NOMAD with `readRaw` from the
 * upload the form's files are in (`uploadId`).
 */
export function renderFileCharts(r, value, {pendingFiles, uploadId, readRaw}) {
  const files = value || [];
  const pending = files.map((name) => {
    const token = parsePending(name);
    return token ? pendingFiles[token.id] : undefined;
  });
  const key = files.join('|') + '|' + pending.map(Boolean).join();
  if (r.charts.dataset.key === key) return;
  r.charts.dataset.key = key;
  r.charts.replaceChildren(...files.map((name, index) => {
    const fileName = displayName(name);
    const box = el('div', {class: 'file-chart'});
    const file = pending[index];
    if (file) {
      plotFile(box, r.field.chart, file, fileName, () => file.text());
    } else if (uploadId) {
      const cacheKey = `${uploadId}/${name}`;
      const plot = () => plotFile(box, r.field.chart, cacheKey, fileName, () => readRaw(uploadId, name));
      if (chartCache.has(cacheKey)) plot();
      else box.append(el('button', {type: 'button', class: 'btn btn-text', onclick: plot}, `Plot ${fileName}`));
    }
    return box;
  }));
}
