"""
Run and step times are on the lab's clock (Europe/Amsterdam in the tests),
whatever time zone the browser is in or NOMAD gives the datetimes back in.
"""

from datetime import date, datetime, time

import pytest
from helpers import pld_forms as pld
from helpers import sputter_forms as sputter
from nomad.datamodel import EntryArchive

from differ_pld4e_schemas.dashboards.pld_logbook.convert import archive_to_form
from differ_pld4e_schemas.dashboards.pld_logbook.rules import validate
from differ_pld4e_schemas.time_zone import is_skipped, lab_instant, lab_wall_time

DASHBOARDS = [
    pytest.param(pld, pld.FORM, id='pld'),
    pytest.param(sputter, sputter.FORM, id='sputter'),
]


def _as_nomad_gives_it(logbook: dict) -> dict:
    """The logbook as NOMAD returns it once stored: datetimes in UTC."""
    return EntryArchive.m_from_dict({'data': logbook}).m_to_dict()['data']


def _instants(logbook: dict) -> list:
    moments = [logbook['datetime']]
    for step in logbook['steps']:
        moments += [step.get('start_time'), step.get('end_time')]
    return [datetime.fromisoformat(m) if m else None for m in moments]


def test_nomad_gives_datetimes_back_in_utc():
    stored = _as_nomad_gives_it(pld._logbook())
    assert stored['datetime'] == '2026-10-22T07:15:00+00:00'


@pytest.mark.parametrize('module, data', DASHBOARDS)
def test_reopened_logbook_shows_the_lab_clock(module, data):
    stored = _as_nomad_gives_it(module._logbook(data))
    form = module.archive_to_form(stored, module.SPEC)
    assert form['run']['date'] == data['run']['date']
    assert form['run']['time'] == data['run']['time']
    # Nothing is left for the browser to convert.
    assert 'start' not in form['run']
    for step, original in zip(form['steps'], data['steps']):
        assert step.get('start_time') == original.get('start_time')
        assert step.get('end_time') == original.get('end_time')


@pytest.mark.parametrize('module, data', DASHBOARDS)
def test_saving_a_reopened_logbook_keeps_every_time(module, data):
    first = module._logbook(data)
    form = module.archive_to_form(_as_nomad_gives_it(first), module.SPEC)
    again = module._logbook(form)
    assert _instants(again) == _instants(first)


def test_browser_offset_is_ignored():
    data = pld.form(run__utc_offset='+00:00')
    assert pld._logbook(data)['datetime'] == '2026-10-22T09:15:00+02:00'
    del data['run']['utc_offset']
    assert pld._logbook(data)['datetime'] == '2026-10-22T09:15:00+02:00'


def test_winter_and_summer_runs_get_their_own_offset():
    winter = pld._logbook(pld.form(run__date='2026-01-15'))
    summer = pld._logbook(pld.form(run__date='2026-07-15'))
    assert winter['datetime'] == '2026-01-15T09:15:00+01:00'
    assert winter['steps'][0]['start_time'] == '2026-01-15T09:20:00+01:00'
    assert summer['datetime'] == '2026-07-15T09:15:00+02:00'


def test_step_over_the_clock_change_has_its_real_duration():
    # The clocks go back from 03:00 to 02:00 on 25 October 2026.
    data = pld.form(
        run__date='2026-10-24',
        run__time='23:00',
        steps__0__start_time='23:30',
        steps__0__end_time='04:30',
        steps__1__start_time='04:40',
        steps__1__end_time='05:00',
    )
    assert validate(data, pld.SPEC) == []
    heating = pld._logbook(data)['steps'][0]
    assert heating['start_time'] == '2026-10-24T23:30:00+02:00'
    assert heating['end_time'] == '2026-10-25T04:30:00+01:00'
    assert heating['duration'] == pytest.approx(6 * 3600)


def test_time_skipped_by_the_clock_change_is_refused():
    # The clocks go forward from 02:00 to 03:00 on 29 March 2026.
    assert is_skipped(date(2026, 3, 29), time(2, 30))
    assert not is_skipped(date(2026, 3, 29), time(3, 30))
    errors = pld.messages(
        validate(pld.form(run__date='2026-03-29', run__time='02:30'), pld.SPEC)
    )
    assert errors['run.time'].startswith('The lab clock skipped this time')


def test_lab_time_helpers():
    assert lab_instant(date(2026, 1, 15), time(9)).isoformat() == (
        '2026-01-15T09:00:00+01:00'
    )
    naive_utc = datetime(2026, 7, 15, 7, 0)
    assert lab_wall_time(naive_utc).strftime('%H:%M') == '09:00'


def test_logbook_with_utc_steps_opens_on_the_lab_clock():
    stored = _as_nomad_gives_it(pld._logbook())
    assert stored['steps'][0]['start_time'] == '2026-10-22T07:20:00+00:00'
    step = archive_to_form(stored, pld.SPEC)['steps'][0]
    assert (step['start_time'], step['end_time']) == ('09:20', '10:05')
