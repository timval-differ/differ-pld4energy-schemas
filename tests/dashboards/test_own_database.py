"""
For now every user may choose their own target and substrate database on the
page (one of their uploads); the server checks the form against that choice.
"""

from http import HTTPStatus

import pytest
from fastapi.testclient import TestClient
from helpers import DATABASE_UPLOAD
from helpers import pld_forms as pld
from nomad.config import config

from differ_pld4e_schemas.dashboards import pld_logbook_dashboard_entry_point
from differ_pld4e_schemas.database import ENTRY_POINT_ID

NOT_FROM_DATABASE = 'Choose one from the target and substrate database.'
DATABASE_FIELDS = {'samples.0.substrate', 'targets.0.target'}


@pytest.fixture
def client():
    return TestClient(pld_logbook_dashboard_entry_point.load())


def _database_errors(body):
    return {
        e['path']
        for e in body['errors']
        if e['message'] == NOT_FROM_DATABASE or 'not set up' in e['message']
    }


def test_without_a_choice_the_lab_database_applies(client):
    # pld.FORM takes its target and substrate from the lab's database.
    body = client.post('/api/validate', json={'form': pld.FORM}).json()
    assert _database_errors(body) == set()


def test_the_chosen_database_applies(client):
    other = {'form': pld.FORM, 'database_upload_id': 'my_own_database'}
    body = client.post('/api/validate', json=other).json()
    assert _database_errors(body) == DATABASE_FIELDS
    body = client.post('/api/archive', json=other).json()
    assert _database_errors(body) == DATABASE_FIELDS and body['files'] == []

    same = {'form': pld.FORM, 'database_upload_id': DATABASE_UPLOAD}
    assert _database_errors(client.post('/api/validate', json=same).json()) == set()
    body = client.post('/api/archive', json=same).json()
    assert body['errors'] == [] and body['files']


def test_a_choice_works_without_a_lab_database(client, monkeypatch):
    entry_point = config.get_plugin_entry_point(ENTRY_POINT_ID)
    monkeypatch.setattr(entry_point, 'database_upload_id', None)
    client = TestClient(pld_logbook_dashboard_entry_point.load())
    body = client.post('/api/validate', json={'form': pld.FORM}).json()
    assert _database_errors(body) == DATABASE_FIELDS
    chosen = {'form': pld.FORM, 'database_upload_id': DATABASE_UPLOAD}
    assert _database_errors(client.post('/api/validate', json=chosen).json()) == set()


@pytest.mark.parametrize('upload_id', ['../x', 'a b', 'x' * 65, 'ünïcode'])
def test_a_choice_must_be_an_upload_id(client, upload_id):
    body = {'form': pld.FORM, 'database_upload_id': upload_id}
    response = client.post('/api/validate', json=body)
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_the_page_sends_its_choice_with_every_save(client):
    script = client.get('/static/app.js').text
    assert script.count('database_upload_id: databaseUpload()') == 2  # noqa: PLR2004
    assert script.count("dashboard('api/archive'") == 2  # noqa: PLR2004
