"""
Saving an opened logbook again keeps what the form does not hold: values
added in NOMAD's entry editor stay in the logbook and in its Sample files.
"""

import copy

import pytest
from fastapi.testclient import TestClient
from helpers import pld_forms as pld
from helpers import sputter_forms as sputter

from differ_pld4e_schemas.dashboards import pld_logbook_dashboard_entry_point
from differ_pld4e_schemas.dashboards.common.convert import UnsafeLogbookFile

LOGBOOK = 'LA-PLD_2026-10-22_0915_STO_on_Si.archive.json'
SAMPLE = 'LA-PLD_2026-10-22_09_15_S01.archive.json'
SAMPLE_REF = f'../upload/archive/mainfile/{SAMPLE}#data'


def _saved():
    """The files of the complete form, as saved before."""
    files = pld.form_to_files(pld.FORM, pld.SPEC)['files']
    return {f['file_name']: copy.deepcopy(f['archive']['data']) for f in files}


def _reopened():
    """The form of the saved logbook, its sample saved (as the page keeps it)."""
    data = pld.form(
        samples__0__ref=SAMPLE_REF, samples__0__sample_id='LA-PLD_2026-10-22_09:15_S01'
    )
    return data


def _existing(logbook=None, sample=None):
    saved = _saved()
    return {
        'logbook': {**saved[LOGBOOK], **(logbook or {})},
        'samples': {SAMPLE: {**saved[SAMPLE], **(sample or {})}},
    }


def _files(data, existing):
    files = pld.form_to_files(data, pld.SPEC, LOGBOOK, existing)['files']
    return {f['file_name']: f['archive']['data'] for f in files}


def test_values_added_in_nomad_are_kept():
    existing = _existing(
        logbook={
            'references': ['https://doi.org/x'],
            'lab_id': 'run-17',
            'tags': ['x'],
        },
        sample={'lab_id': 'box 3', 'tags': ['STO']},
    )
    files = _files(_reopened(), existing)
    logbook, sample = files[LOGBOOK], files[SAMPLE]
    assert logbook['references'] == ['https://doi.org/x']
    assert logbook['lab_id'] == 'run-17'
    assert logbook['tags'] == ['x']
    assert sample['lab_id'] == 'box 3'
    assert sample['tags'] == ['STO']


def test_the_form_decides_what_it_holds():
    existing = _existing(
        logbook={
            'name': 'old name',
            'base_pressure': 1.0,
            'figures': [{'label': 'x'}],
            # The run's comments field writes the description: the form decides it.
            'description': 'edited in NOMAD',
        },
        sample={'description': 'old comment'},
    )
    data = _reopened()
    del data['chamber']['particle_reduction_plate']  # cleared in the form
    files = _files(data, existing)
    logbook = files[LOGBOOK]
    assert logbook['name'] == 'STO on Si'
    assert logbook['base_pressure'] == pytest.approx(1e-6)
    assert 'particle_reduction_plate' not in logbook
    # Figures are made again when NOMAD processes the logbook.
    assert 'figures' not in logbook
    assert 'description' not in files[SAMPLE]
    assert logbook.get('description') != 'edited in NOMAD'


def test_without_existing_files_the_result_is_unchanged():
    data = _reopened()
    assert _files(data, None) == _files(data, {})


def test_a_new_logbook_takes_nothing_from_existing_files():
    existing = _existing(logbook={'lab_id': 'from another logbook'})
    result = pld.form_to_files(pld.FORM, pld.SPEC, None, existing)['files']
    assert 'lab_id' not in result[-1]['archive']['data']


def test_steps_the_form_cannot_hold_stop_the_overwrite():
    existing = _existing()
    existing['logbook']['steps'].append({'m_def': 'some.other.StepType', 'name': 'x'})
    with pytest.raises(UnsafeLogbookFile, match='1 process step'):
        pld.form_to_files(_reopened(), pld.SPEC, LOGBOOK, existing)


def test_sputter_logbook_keeps_values_too():
    stem = sputter.LOGBOOK_FILE
    saved = sputter.form_to_files(sputter.FORM, sputter.SPEC)['files'][-1]
    existing = {'logbook': {**saved['archive']['data'], 'lab_id': 'kept'}}
    files = sputter.form_to_files(sputter.FORM, sputter.SPEC, stem, existing)['files']
    assert files[-1]['archive']['data']['lab_id'] == 'kept'


def test_the_api_takes_the_existing_files():
    client = TestClient(pld_logbook_dashboard_entry_point.load())
    body = client.post(
        '/api/archive',
        json={
            'form': _reopened(),
            'logbook_file': LOGBOOK,
            'existing': _existing(logbook={'lab_id': 'kept'}),
        },
    ).json()
    assert body['errors'] == []
    assert body['files'][-1]['archive']['data']['lab_id'] == 'kept'
    existing = _existing()
    existing['logbook']['steps'].append({'m_def': 'some.other.StepType'})
    body = client.post(
        '/api/archive',
        json={'form': _reopened(), 'logbook_file': LOGBOOK, 'existing': existing},
    ).json()
    assert body['errors'][0]['path'] == 'logbook_file'


def test_values_the_sample_normalizer_derives_are_not_kept():
    files = _files(_reopened(), _existing(sample={'substrate_size': '10x10 mm'}))
    assert 'substrate_size' not in files[SAMPLE]
