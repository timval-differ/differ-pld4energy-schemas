"""
What the browser sends cannot choose which files a save overwrites: only the
file of an opened logbook made by the dashboard, and only a sample's own file.
"""

import copy

import pytest
import test_pld_logbook as pld
import test_sputter_logbook as sputter
from fastapi.testclient import TestClient

from differ_pld4e_schemas.dashboards import (
    pld_logbook_dashboard_entry_point,
    sputter_logbook_dashboard_entry_point,
)
from differ_pld4e_schemas.dashboards.common.convert import (
    UnsafeLogbookFile,
    is_logbook_file,
)
from differ_pld4e_schemas.dashboards.common.samples import own_sample_file
from differ_pld4e_schemas.dashboards.pld_logbook.convert import (
    form_to_files as pld_form_to_files,
)

HTTP_UNPROCESSABLE = 422
PLD_SYSTEMS = ['SA-PLD', 'LA-PLD']
PLD_LOGBOOK = 'LA-PLD_2026-10-22_0915_STO_on_Si.archive.json'
SAMPLE_ID = 'LA-PLD_2026-10-22_09:15_S01'

DASHBOARDS = [
    pytest.param(pld_logbook_dashboard_entry_point, pld.FORM, PLD_LOGBOOK, id='pld'),
    pytest.param(
        sputter_logbook_dashboard_entry_point,
        sputter.FORM,
        sputter.LOGBOOK_FILE,
        id='sputter',
    ),
]

UNSAFE_LOGBOOK_FILES = [
    'victim.csv',
    '../LA-PLD_2026-10-22_0915.archive.json',
    'pld_drafts/LA-PLD_2026-10-22_0915.archive.json',
    # A sample file, of this run or another.
    'LA-PLD_2026-10-22_09_15_S01.archive.json',
    'SPS_2026-10-22_09_15_S01.archive.json',
    # Hand-made logbooks are saved as a new file, not overwritten with JSON.
    'LA-PLD_2026-10-22_0915.archive.yaml',
    'example_la_pld.archive.yaml',
    'LA-PLD_2026-10-22_0915.archive.json.csv',
    '',
]


def _sample_reference(file_name):
    return f'../upload/archive/mainfile/{file_name}#data'


@pytest.mark.parametrize(
    'name',
    [
        PLD_LOGBOOK,
        'SA-PLD_2026-01-02_2359.archive.json',
        'LA-PLD_2026-10-22_0915_a.b-c_d.archive.json',
    ],
)
def test_dashboard_logbook_names_are_logbook_files(name):
    assert is_logbook_file(name, PLD_SYSTEMS)


@pytest.mark.parametrize('name', [*UNSAFE_LOGBOOK_FILES, None, 42])
def test_other_names_are_not_logbook_files(name):
    assert not is_logbook_file(name, PLD_SYSTEMS)


def test_logbook_of_another_dashboard_is_not_a_logbook_file():
    assert not is_logbook_file(sputter.LOGBOOK_FILE, PLD_SYSTEMS)
    assert not is_logbook_file(PLD_LOGBOOK, ['SPS'])


@pytest.mark.parametrize('name', UNSAFE_LOGBOOK_FILES)
def test_form_to_files_refuses_to_overwrite_other_files(name):
    with pytest.raises(UnsafeLogbookFile):
        pld_form_to_files(pld.FORM, pld.SPEC, name)


def test_opened_logbook_is_overwritten():
    result = pld_form_to_files(pld.FORM, pld.SPEC, PLD_LOGBOOK)
    logbook = result['files'][-1]
    assert logbook['file_name'] == PLD_LOGBOOK
    assert logbook['overwrite'] is True
    assert result['warnings'] == []


@pytest.mark.parametrize('entry_point, form, logbook_file', DASHBOARDS)
def test_app_reports_unsafe_logbook_file(entry_point, form, logbook_file):
    client = TestClient(entry_point.load())
    for name in ('victim.csv', '../x.archive.json', logbook_file + '.yaml'):
        response = client.post(
            '/api/archive', json={'form': form, 'logbook_file': name}
        ).json()
        assert response['files'] == []
        assert [error['path'] for error in response['errors']] == ['logbook_file']
    response = client.post(
        '/api/archive', json={'form': form, 'logbook_file': logbook_file}
    ).json()
    assert response['errors'] == []
    assert response['files'][-1]['overwrite'] is True


@pytest.mark.parametrize('entry_point, form, logbook_file', DASHBOARDS)
def test_app_refuses_overlong_logbook_file(entry_point, form, logbook_file):
    client = TestClient(entry_point.load())
    name = 'x' * 300 + '.archive.json'
    response = client.post('/api/archive', json={'form': form, 'logbook_file': name})
    assert response.status_code == HTTP_UNPROCESSABLE


# Samples


def test_own_sample_file():
    own = _sample_reference(pld.SAMPLE_FILE)
    assert own_sample_file(own, SAMPLE_ID, PLD_SYSTEMS) == pld.SAMPLE_FILE
    # The file of another sample, or a sample ID of another dashboard.
    other = _sample_reference('LA-PLD_2026-10-22_09_15_S02.archive.json')
    assert own_sample_file(other, SAMPLE_ID, PLD_SYSTEMS) is None
    assert own_sample_file(own, SAMPLE_ID, ['SPS']) is None
    assert own_sample_file(own, 'S01', PLD_SYSTEMS) is None
    assert own_sample_file(own, None, PLD_SYSTEMS) is None
    # Only references by file name in the same upload are files to write.
    reference = '../uploads/u/archive/e#/data'
    assert own_sample_file(reference, SAMPLE_ID, PLD_SYSTEMS) is None


@pytest.mark.parametrize(
    'file_name',
    [
        PLD_LOGBOOK,
        'LA-PLD_2026-10-22_09_15_S02.archive.json',
        'notes.txt',
        '../other/LA-PLD_2026-10-22_09_15_S01.archive.json',
    ],
)
def test_sample_reference_to_another_file_is_kept_but_not_written(file_name):
    reference = _sample_reference(file_name)
    data = pld.form(samples__0__ref=reference, samples__0__sample_id=SAMPLE_ID)
    result = pld_form_to_files(data, pld.SPEC)
    assert [f['kind'] for f in result['files']] == ['logbook']
    logbook = result['files'][-1]['archive']['data']
    assert logbook['samples'][0]['reference'] == reference
    assert [w['path'] for w in result['warnings']] == ['samples.0']


def test_sample_reference_with_a_forged_sample_id_is_not_written():
    """The sample ID must have the form the run's system gives."""
    reference = _sample_reference('notes.archive.json')
    data = pld.form(samples__0__ref=reference, samples__0__sample_id='notes')
    result = pld_form_to_files(data, pld.SPEC)
    assert [f['kind'] for f in result['files']] == ['logbook']
    assert result['warnings']


def test_saved_sample_is_updated_without_warnings():
    data = pld.form(
        samples__0__ref=_sample_reference(pld.SAMPLE_FILE),
        samples__0__sample_id=SAMPLE_ID,
    )
    result = pld_form_to_files(data, pld.SPEC)
    sample = result['files'][0]
    assert (sample['file_name'], sample['overwrite']) == (pld.SAMPLE_FILE, True)
    assert sample['reference'] == _sample_reference(pld.SAMPLE_FILE)
    assert result['warnings'] == []


def test_saved_sample_is_updated_after_the_system_is_changed():
    """The sample keeps its ID, and its entry, when the run's system changes."""
    data = pld.form(
        run__system='SA-PLD',
        chamber__substrate_carrier='1" carrier',
        samples__0__ref=_sample_reference(pld.SAMPLE_FILE),
        samples__0__sample_id=SAMPLE_ID,
    )
    data['chamber'].pop('particle_reduction_plate')
    result = pld_form_to_files(data, pld.SPEC)
    sample = result['files'][0]
    assert (sample['kind'], sample['file_name']) == ('sample', pld.SAMPLE_FILE)
    assert sample['overwrite'] is True
    assert result['warnings'] == []


def test_new_sample_is_never_overwritten():
    result = pld_form_to_files(copy.deepcopy(pld.FORM), pld.SPEC)
    assert result['files'][0]['overwrite'] is False
    assert result['warnings'] == []
