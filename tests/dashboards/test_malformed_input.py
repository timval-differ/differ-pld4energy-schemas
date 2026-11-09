"""
A malformed request gets a 400 (or a 200 listing the problems), never a 500:
the browser and drafts kept in uploads are not trusted to send a well-formed
form.
"""

import copy

import pytest
from fastapi.testclient import TestClient
from helpers import pld_forms as pld
from helpers import sputter_forms as sputter

from differ_pld4e_schemas.dashboards import (
    pld_logbook_dashboard_entry_point,
    sputter_logbook_dashboard_entry_point,
)
from differ_pld4e_schemas.dashboards.common.archive import to_archive_value

HTTP_OK = 200
HTTP_BAD_REQUEST = 400
HTTP_UNPROCESSABLE = 422

DASHBOARDS = {
    'pld': (pld_logbook_dashboard_entry_point, pld.FORM),
    'sputter': (sputter_logbook_dashboard_entry_point, sputter.FORM),
}


def _set(form, path, value):
    *parents, key = path.split('.')
    target = form
    for parent in parents:
        target = target[int(parent)] if parent.isdigit() else target[parent]
    target[key] = value


# (name, changes to the dashboard's complete form; None replaces the form)
MALFORMED = [
    ('steps not a list', {'steps': 'x'}),
    ('step not an object', {'steps': ['x']}),
    ('step type not a string', {'steps.0.type': [1]}),
    ('unknown step type', {'steps.0.type': 'no-such-step'}),
    ('step uid an object', {'steps.0.uid': {}}),
    ('step time a list', {'steps.0.start_time': [9, 20]}),
    ('samples not a list', {'samples': 'abc'}),
    ('sample not an object', {'samples': ['x']}),
    ('sample origin a list', {'samples.0.origin': ['New sample']}),
    ('substrate material a list', {'samples.0.substrate_material': [1]}),
    ('sample ref a number', {'samples.0.ref': 5}),
    (
        'films not a list',
        {'samples.0.origin': 'External sample', 'samples.0.prior_films': 'ab'},
    ),
    (
        'film not an object',
        {'samples.0.origin': 'External sample', 'samples.0.prior_films': ['ab']},
    ),
    ('run a list', {'run': [1]}),
    ('run a string', {'run': 'x'}),
    ('system a list', {'run.system': ['LA-PLD']}),
    ('date a number', {'run.date': 20261022}),
    ('time an object', {'run.time': {'h': 9}}),
    ('chamber a list', {'chamber': []}),
    ('number an object', {'chamber.base_pressure': {'value': 1}}),
    ('number huge', {'chamber.base_pressure': '1e308'}),
    ('targets not a list', {'targets': 'x'}),
    ('target not an object', {'targets': [1]}),
    ('recipe an object', {'recipe': {'a': 1}}),
    ('empty form', None),
]
PLD_ONLY = [
    ('in-situ not a list', {'in_situ': 'x'}),
    ('in-situ steps a number', {'in_situ.0.steps': 5}),
    ('in-situ files a number', {'in_situ.0.rheed_pattern_export_files': 5}),
    ('in-situ files a string', {'in_situ.0.rheed_pattern_export_files': 'abc'}),
    ('in-situ file an object', {'in_situ.0.rheed_pattern_export_files': [{}]}),
    ('laser an object of lists', {'laser': {'energy_before_chamber': [1]}}),
    ('logfiles a string', {'logfiles': 'x'}),
]


def _cases():
    for dashboard in DASHBOARDS:
        cases = MALFORMED + (PLD_ONLY if dashboard == 'pld' else [])
        for name, changes in cases:
            yield pytest.param(dashboard, changes, id=f'{dashboard}: {name}')


def _form(dashboard, changes):
    if changes is None:
        return {}
    form = copy.deepcopy(DASHBOARDS[dashboard][1])
    for path, value in changes.items():
        _set(form, path, value)
    return form


@pytest.fixture(scope='module')
def clients():
    return {
        name: TestClient(entry_point.load(), raise_server_exceptions=False)
        for name, (entry_point, _) in DASHBOARDS.items()
    }


@pytest.mark.parametrize('endpoint', ['validate', 'archive', 'draft-name'])
@pytest.mark.parametrize('dashboard, changes', list(_cases()))
def test_malformed_form_is_never_a_server_error(clients, dashboard, changes, endpoint):
    form = _form(dashboard, changes)
    response = clients[dashboard].post(f'/api/{endpoint}', json={'form': form})
    assert response.status_code in (HTTP_OK, HTTP_BAD_REQUEST), response.text
    if response.status_code == HTTP_BAD_REQUEST:
        assert response.json()['detail'].startswith('Malformed form')
    else:
        assert 'errors' in response.json()
    if endpoint == 'archive' and response.status_code == HTTP_OK:
        # A form with problems never gives files to write.
        body = response.json()
        assert not (body['errors'] and body['files'])


@pytest.mark.parametrize('dashboard', DASHBOARDS)
@pytest.mark.parametrize(
    'data',
    [
        {},
        {'m_def': [1]},
        {'m_def': 'x.Y'},
        {'m_def': 'differ_pld4e_schemas.pld_deposition.LAPLDLogbook', 'steps': 'x'},
        {'m_def': 'differ_pld4e_schemas.pld_deposition.LAPLDLogbook', 'steps': ['x']},
        {'m_def': 'differ_pld4e_schemas.pld_deposition.LAPLDLogbook', 'samples': 5},
        {
            'm_def': 'differ_pld4e_schemas.sps_deposition.SPSLogbook',
            'steps': [{'m_def': 5}],
        },
        {'m_def': 'differ_pld4e_schemas.sps_deposition.SPSLogbook', 'datetime': [1]},
    ],
)
@pytest.mark.parametrize('mode', ['edit', 'recipe'])
def test_malformed_archive_is_never_a_server_error(clients, dashboard, data, mode):
    response = clients[dashboard].post(
        '/api/form-from-archive', json={'data': data, 'mode': mode}
    )
    assert response.status_code in (HTTP_OK, HTTP_BAD_REQUEST), response.text


@pytest.mark.parametrize('dashboard', DASHBOARDS)
@pytest.mark.parametrize(
    'body', [{}, {'form': 'x'}, {'form': []}, {'form': {}, 'logbook_file': 5}]
)
def test_request_of_the_wrong_shape_is_refused(clients, dashboard, body):
    response = clients[dashboard].post('/api/archive', json=body)
    assert response.status_code == HTTP_UNPROCESSABLE


@pytest.mark.parametrize('value', [5, 'abc', [{}], [1, 'a']])
def test_files_value_must_be_a_list_of_file_names(value):
    with pytest.raises(ValueError, match='list of file names'):
        to_archive_value(value, {'kind': 'files'}, None)


def test_complete_forms_are_still_saved(clients):
    for name, (_, form) in DASHBOARDS.items():
        body = clients[name].post('/api/archive', json={'form': form}).json()
        assert body['errors'] == []
        assert body['files']
