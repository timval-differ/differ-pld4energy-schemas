"""
The page and its static files, shared by every logbook dashboard: each file is
linked with a version from its content, revalidated by the browser, and any
change to one of them tells the page that NOMAD has to be restarted.
"""

import re
import shutil

import pytest
from fastapi.testclient import TestClient

from differ_pld4e_schemas.dashboards import (
    pld_logbook_dashboard_entry_point,
    sputter_logbook_dashboard_entry_point,
)
from differ_pld4e_schemas.dashboards.common import app as app_module

STATIC = app_module.STATIC
SCRIPTS = sorted(path.name for path in STATIC.glob('*.js'))
ENTRY_POINTS = [
    pytest.param(pld_logbook_dashboard_entry_point, id='pld'),
    pytest.param(sputter_logbook_dashboard_entry_point, id='sputter'),
]


@pytest.fixture(params=ENTRY_POINTS)
def client(request):
    return TestClient(request.param.load())


def test_every_linked_file_has_the_version_of_its_content(client):
    page = client.get('/').text
    linked = re.findall(r'static/([\w.-]+)\?v=([0-9a-f]{12})"', page)
    assert {name for name, _ in linked} >= {'app.js', 'style.css'}
    for name, version in linked:
        assert version == app_module.asset_version(name), name
    # No static file is linked without a version.
    assert not re.search(r'static/[\w.-]+"', page)


def test_static_files_are_revalidated(client):
    for path in STATIC.iterdir():
        response = client.get(f'/static/{path.name}')
        assert response.status_code == 200  # noqa: PLR2004
        assert response.headers['cache-control'] == 'no-cache', path.name
        assert response.headers.get('etag'), path.name


def test_unchanged_static_file_is_not_sent_again(client):
    etag = client.get('/static/app.js').headers['etag']
    response = client.get('/static/app.js', headers={'If-None-Match': etag})
    assert response.status_code == 304  # noqa: PLR2004


def test_page_and_spec_have_the_version_of_all_static_files(client):
    page = client.get('/').text
    version = re.search(r'name="script-version" content="([0-9a-f]{12})"', page)
    assert version.group(1) == app_module.static_version()
    assert client.get('/api/spec').json()['script_version'] == version.group(1)


@pytest.mark.parametrize('name', ['pdf.js', 'style.css', 'index.html'])
def test_a_change_to_any_static_file_changes_the_version(tmp_path, monkeypatch, name):
    static = tmp_path / 'static'
    shutil.copytree(STATIC, static)
    monkeypatch.setattr(app_module, 'STATIC', static)
    before = app_module.static_version()
    with open(static / name, 'a', encoding='utf-8') as file:
        file.write('\n')
    assert app_module.static_version() != before


@pytest.mark.parametrize('name', SCRIPTS)
def test_scripts_do_not_use_dialogs_the_frame_blocks(name):
    """
    NOMAD shows dashboards in a sandboxed frame, where window.print(),
    confirm(), alert() and prompt() are ignored.
    """
    script = (STATIC / name).read_text(encoding='utf-8')
    assert not re.search(r'window\.(print|confirm|alert|prompt)\([^)]', script)
