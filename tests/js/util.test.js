import assert from 'node:assert/strict';
import {test} from 'node:test';

import {clockIn} from '../../src/differ_pld4e_schemas/dashboards/common/static/util.js';

test('clockIn gives the date and time on the lab clock, not this computer\'s', () => {
  // 07:15 UTC is 09:15 in Amsterdam in summer, 08:15 in winter.
  assert.deepEqual(clockIn('Europe/Amsterdam', new Date('2026-10-22T07:15:00Z')), {date: '2026-10-22', time: '09:15'});
  assert.deepEqual(clockIn('Europe/Amsterdam', new Date('2026-01-15T07:15:00Z')), {date: '2026-01-15', time: '08:15'});
  assert.deepEqual(clockIn('UTC', new Date('2026-10-22T07:15:00Z')), {date: '2026-10-22', time: '07:15'});
});

test('clockIn moves to the next day after midnight on the lab clock', () => {
  assert.deepEqual(clockIn('Europe/Amsterdam', new Date('2026-10-22T22:30:00Z')), {date: '2026-10-23', time: '00:30'});
});
