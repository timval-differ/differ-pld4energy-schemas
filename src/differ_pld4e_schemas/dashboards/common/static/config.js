// @ts-check
/*
 * Where the page runs: NOMAD's base path, its API and GUI, and this dashboard,
 * e.g. /nomad-oasis, /nomad-oasis/api/v1 and /nomad-oasis/dashboards/<id>/ for
 * the page at /nomad-oasis/dashboards/<id>/. Outside a browser (tests) NOMAD
 * is at the root: /api/v1, and the dashboard at /.
 */

const PATH = typeof window === 'undefined' ? '' : window.location.pathname;

export const BASE = PATH.replace(/\/dashboards\/.*$/, '');
export const API = BASE + '/api/v1';
export const GUI = BASE + '/gui/v2';
export const DASHBOARD = PATH.replace(/\/?$/, '/');
