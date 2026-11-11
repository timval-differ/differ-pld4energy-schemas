"""
A fresh Oasis, before the target and substrate database is set up: the
dashboards still load, and say why no target or substrate can be chosen.
"""

import pytest
from fastapi.testclient import TestClient
from helpers import pld_forms as pld
from nomad.config import config

from differ_pld4e_schemas.dashboards.pld_logbook import spec as pld_spec_module
from differ_pld4e_schemas.dashboards.pld_logbook.rules import validate
from differ_pld4e_schemas.database import ENTRY_POINT_ID

NOT_SET_UP = (
    'The target and substrate database is not set up in NOMAD yet. Ask a maintainer.'
)


@pytest.fixture
def no_database(monkeypatch):
    entry_point = config.get_plugin_entry_point(ENTRY_POINT_ID)
    monkeypatch.setattr(entry_point, 'database_upload_id', None)


def test_spec_without_a_database(no_database):
    assert pld_spec_module.form_spec()['database_upload_id'] is None


def test_targets_and_substrates_cannot_be_chosen(no_database):
    errors = pld.messages(validate(pld.FORM, pld_spec_module.form_spec()))
    assert errors['samples.0.substrate'] == NOT_SET_UP
    assert errors['targets.0.target'] == NOT_SET_UP


def test_the_dashboard_loads_and_validates(no_database):
    from differ_pld4e_schemas.dashboards import pld_logbook_dashboard_entry_point

    client = TestClient(pld_logbook_dashboard_entry_point.load())
    assert client.get('/api/spec').json()['database_upload_id'] is None
    body = client.post('/api/validate', json={'form': pld.FORM}).json()
    assert {e['message'] for e in body['errors']} == {NOT_SET_UP}
