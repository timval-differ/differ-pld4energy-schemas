"""
The publication dashboard: exports run in the background as the logged-in
user, and only that user sees and downloads them.
"""

import io
import json
import logging
import zipfile
from contextlib import contextmanager
from http import HTTPStatus
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import differ_pld4e_schemas.dashboards.publication.app as app_module
from differ_pld4e_schemas.dashboards.publication.jobs import (
    INTERRUPTED,
    LIFETIME,
    STUCK_AFTER,
    UNEXPECTED,
    AlreadyRunning,
    Jobs,
)
from differ_pld4e_schemas.dashboards.publication.source import NomadFilesSource
from differ_pld4e_schemas.snapshot import SnapshotError, build_snapshot

# NOMAD's login check needs NOMAD's server modules, which are installed with
# NOMAD's infrastructure extras (as in nomad-distro-dev) but not in CI. All
# other tests replace NOMAD's server parts and run everywhere.
NEEDS_NOMAD_SERVER = "NOMAD's login check needs nomad-lab[infrastructure]"

ALICE = SimpleNamespace(user_id='alice')
BOB = SimpleNamespace(user_id='bob')


class Inline:
    """Runs the export at once, so the tests need not wait for a thread."""

    def submit(self, function, *args):
        function(*args)


class Later:
    """Keeps the export until `run` is called: it is still running before."""

    def __init__(self):
        self.pending = []

    def submit(self, function, *args):
        self.pending.append((function, args))

    def run(self):
        while self.pending:
            function, args = self.pending.pop(0)
            function(*args)


@pytest.fixture
def jobs(tmp_path):
    return Jobs(tmp_path / 'exports', executor=Inline())


def _age(jobs, job_id, seconds):
    """Pretend the export started `seconds` ago."""
    path = jobs.directory / job_id / 'job.json'
    state = json.loads(path.read_text(encoding='utf-8'))
    state['started'] -= seconds
    path.write_text(json.dumps(state), encoding='utf-8')


def test_export_is_written_as_a_zip(jobs):
    job = jobs.start('alice', 'up1', lambda: {'b/c.txt': b'c', 'a.txt': b'a'})
    state = jobs.get(job['job_id'], 'alice')
    assert state['status'] == 'done'
    assert state['file_name'] == 'up1-publication.zip'
    assert 'user_id' not in state
    with zipfile.ZipFile(jobs.zip_path(job['job_id'], 'alice')) as archive:
        assert archive.namelist() == ['a.txt', 'b/c.txt']
        assert archive.read('b/c.txt') == b'c'


def test_only_the_user_who_started_an_export_sees_it(jobs):
    job = jobs.start('alice', 'up1', lambda: {'a.txt': b'a'})
    with pytest.raises(KeyError):
        jobs.get(job['job_id'], 'bob')
    with pytest.raises(KeyError):
        jobs.zip_path(job['job_id'], 'bob')
    for job_id in ('../exports', 'nope', '0' * 31, job['job_id'] + '\n'):
        with pytest.raises(KeyError):
            jobs.get(job_id, 'alice')


def test_a_running_export_has_no_zip_yet(tmp_path):
    later = Later()
    jobs = Jobs(tmp_path, executor=later)
    job = jobs.start('alice', 'up1', lambda: {'a.txt': b'a'})
    assert jobs.get(job['job_id'], 'alice')['status'] == 'running'
    with pytest.raises(KeyError):
        jobs.zip_path(job['job_id'], 'alice')
    later.run()
    assert jobs.get(job['job_id'], 'alice')['status'] == 'done'


def test_one_export_at_a_time_per_user(tmp_path):
    later = Later()
    jobs = Jobs(tmp_path, executor=later)
    jobs.start('alice', 'up1', dict)
    with pytest.raises(AlreadyRunning):
        jobs.start('alice', 'up2', dict)
    jobs.start('bob', 'up2', dict)  # others are not held up
    later.run()
    jobs.start('alice', 'up2', dict)


def test_an_interrupted_export_ends(tmp_path):
    """A restart of NOMAD leaves 'running' behind; the page must not poll forever."""
    jobs = Jobs(tmp_path, executor=Later())  # never runs: as if NOMAD restarted
    job = jobs.start('alice', 'up1', dict)
    _age(jobs, job['job_id'], STUCK_AFTER + 60)
    state = jobs.get(job['job_id'], 'alice')
    assert state['status'] == 'failed' and state['error'] == INTERRUPTED
    jobs.start('alice', 'up1', dict)  # and does not block a new export


def test_export_that_cannot_be_made_says_why(jobs):
    def build():
        raise SnapshotError('a.archive.json: points at nothing')

    job = jobs.start('alice', 'up1', build)
    state = jobs.get(job['job_id'], 'alice')
    assert state['status'] == 'failed'
    assert state['error'] == 'a.archive.json: points at nothing'


def test_unexpected_failure_is_logged_not_shown(jobs, caplog):
    def build():
        raise RuntimeError('database password in this message')

    job = jobs.start('alice', 'up1', build)
    state = jobs.get(job['job_id'], 'alice')
    assert state['status'] == 'failed' and state['error'] == UNEXPECTED
    assert 'password' in caplog.text


def test_failure_to_save_the_state_is_logged(tmp_path, caplog):
    later = Later()
    jobs = Jobs(tmp_path, executor=later)
    job = jobs.start('alice', 'up1', dict)
    (tmp_path / job['job_id'] / 'job.json').unlink()
    (tmp_path / job['job_id'] / 'job.tmp').mkdir()  # the state cannot be written
    with caplog.at_level(logging.ERROR):
        later.run()
    assert 'could not be saved' in caplog.text


def test_old_exports_are_removed(jobs):
    job = jobs.start('alice', 'up1', lambda: {'a.txt': b'a'})
    _age(jobs, job['job_id'], LIFETIME / 2)
    jobs.remove_expired()
    assert jobs.get(job['job_id'], 'alice')
    _age(jobs, job['job_id'], LIFETIME)
    jobs.remove_expired()
    with pytest.raises(KeyError):
        jobs.get(job['job_id'], 'alice')
    jobs.remove_expired()  # nothing left, nothing fails


def test_job_state_is_json_on_disk(jobs, tmp_path):
    """Any NOMAD process can read it, not only the one that started it."""
    job = jobs.start('alice', 'up1', dict)
    state = json.loads(
        (tmp_path / 'exports' / job['job_id'] / 'job.json').read_text(encoding='utf-8')
    )
    assert state['status'] == 'done' and state['user_id'] == 'alice'


class _Files:
    def __init__(self, files):
        self.files = files
        self.opened = 0

    def raw_listdir(self, recursive, files_only):
        return [SimpleNamespace(path=path) for path in self.files]

    def raw_file(self, path, mode):
        self.opened += 1
        if path not in self.files:
            raise KeyError(path)
        return io.BytesIO(self.files[path])

    def close(self):
        pass

    @contextmanager
    def read_archive(self, entry_id):
        """As if processing left the data of each file as it is."""
        path = entry_id.removeprefix('id-')
        if path not in self.files:
            raise KeyError(entry_id)
        yield {entry_id: json.loads(self.files[path] or b'{}')}


def _entry(path, mainfile_key=None, process_status='SUCCESS'):
    return SimpleNamespace(
        entry_id=f'id-{path}',
        mainfile=path,
        mainfile_key=mainfile_key,
        process_status=process_status,
    )


@pytest.fixture
def uploads():
    """
    Upload `mine` (Alice's), `database` (Alice and Bob read it), `private`
    (no one), and `busy` (Alice's, being processed): their files, and NOMAD's
    read rule and entry lookup for them.
    """
    files = {
        'mine': _Files(
            {
                'a.archive.json': b'{"data": {"t": "../uploads/database/archive/id-t.archive.json#/data"}}'
            }
        ),
        'database': _Files({'t.archive.json': b'{}'}),
        'private': _Files({'secret.archive.json': b'{}'}),
        'busy': _Files({}),
    }
    readers = {
        'mine': {'alice'},
        'database': {'alice', 'bob'},
        'private': set(),
        'busy': {'alice'},
    }
    entries = {
        upload_id: [_entry(path) for path in uploaded.files]
        for upload_id, uploaded in files.items()
    }
    entries['database'].append(_entry('t.archive.json', mainfile_key='child'))

    def read_access(upload_id, user):
        if upload_id not in readers:
            raise HTTPException(404, 'The specified upload_id was not found.')
        if user.user_id not in readers[upload_id]:
            raise HTTPException(403, 'You do not have access to the specified upload.')
        return SimpleNamespace(
            upload_files=files[upload_id], process_running=upload_id == 'busy'
        )

    return SimpleNamespace(
        files=files,
        readers=readers,
        read_access=read_access,
        entries=lambda upload_id: entries[upload_id],
        entry_lists=entries,
    )


def _source(uploads, user):
    return NomadFilesSource(user, uploads.read_access, uploads.entries)


def test_source_reads_the_uploads_the_user_can_see(uploads):
    source = _source(uploads, ALICE)
    assert source.raw_files('database') == {'t.archive.json': b'{}'}
    assert source.raw_file('database', 't.archive.json') == b'{}'
    # An entry made from part of a file is left out: it has no file of its own.
    assert source.mainfiles('database') == {'id-t.archive.json': 't.archive.json'}
    with pytest.raises(SnapshotError, match='no such file'):
        source.raw_file('database', 'gone.json')


def test_source_reads_nothing_of_an_upload_the_user_cannot_see(uploads):
    for user, upload_id in [(BOB, 'mine'), (ALICE, 'private'), (ALICE, 'nope')]:
        with pytest.raises(SnapshotError, match=f'Cannot read upload {upload_id}'):
            _source(uploads, user).raw_files(upload_id)
        with pytest.raises(SnapshotError):
            _source(uploads, user).mainfiles(upload_id)
    assert uploads.files['mine'].opened == uploads.files['private'].opened == 0


def test_a_reference_into_an_upload_the_user_cannot_see_stops_the_export(uploads):
    """Bob may not read Alice's sample, even if his archive refers to it."""
    uploads.files['bobs'] = _Files(
        {
            'b.archive.json': b'{"s": "../uploads/private/archive/id-secret.archive.json#/data"}'
        }
    )
    uploads.readers['bobs'] = {'bob'}
    uploads.entry_lists['bobs'] = [_entry('b.archive.json')]
    with pytest.raises(SnapshotError, match='Cannot read upload private'):
        build_snapshot('bobs', _source(uploads, BOB))
    assert uploads.files['private'].opened == 0


def test_source_reads_the_data_nomad_stored(uploads, tmp_path):
    """From an archive file as NOMAD writes and reads it."""
    from nomad.archive import read_archive, write_archive

    stored = {
        'm_def': 'differ_pld4e_schemas.schema_packages.schema_package.Sample',
        'm_def_id': 'abc',
        'name': 'S1',
        'layers': [{'thickness': 2e-8}],
    }
    path = tmp_path / 'id-a.archive.json.msg'
    write_archive(str(path), {'id-a.archive.json': {'data': stored, 'metadata': {}}})

    @contextmanager
    def from_disk(entry_id):
        with read_archive(str(path)) as archive:
            yield archive

    uploads.files['mine'].read_archive = from_disk
    assert _source(uploads, ALICE).processed_data('mine', 'a.archive.json') == stored


def test_source_reads_no_data_of_entries_nomad_could_not_process(uploads):
    uploads.entry_lists['mine'] = [_entry('a.archive.json', process_status='FAILURE')]
    with pytest.raises(SnapshotError, match='could not process.*FAILURE'):
        _source(uploads, ALICE).processed_data('mine', 'a.archive.json')
    uploads.entry_lists['mine'] = [_entry('a.archive.json', process_status='RUNNING')]
    with pytest.raises(SnapshotError, match='still processing'):
        _source(uploads, ALICE).processed_data('mine', 'a.archive.json')
    with pytest.raises(SnapshotError, match='no entry'):
        _source(uploads, ALICE).processed_data('mine', 'other.archive.json')


def test_source_reports_an_entry_without_a_stored_archive(uploads):
    @contextmanager
    def missing(entry_id):
        raise KeyError(entry_id)
        yield

    uploads.files['mine'].read_archive = missing
    with pytest.raises(SnapshotError, match='stored no archive'):
        _source(uploads, ALICE).processed_data('mine', 'a.archive.json')


def test_export_follows_references_into_readable_uploads(uploads):
    files = build_snapshot('mine', _source(uploads, ALICE))
    assert sorted(files) == [
        'a.archive.json',
        'referenced/database/t.archive.json',
    ]


@pytest.fixture
def client(tmp_path, uploads, monkeypatch):
    """The dashboard, with Alice or Bob logged in (`client.state.user`)."""
    later = Later()
    jobs = Jobs(tmp_path / 'exports', executor=later)
    state = SimpleNamespace(user=ALICE)
    monkeypatch.setattr(app_module, 'api_url', lambda: 'https://oasis/api/v1')
    app = app_module.create_app(
        jobs,
        user_dependency=lambda: state.user,
        read_access=uploads.read_access,
        entries=uploads.entries,
    )
    test_client = TestClient(app)
    test_client.later = later
    test_client.state = state
    return test_client


def test_export_through_the_dashboard(client):
    response = client.post('api/exports', json={'upload_id': 'mine'})
    assert response.status_code == HTTPStatus.ACCEPTED
    job = response.json()
    assert job['status'] == 'running'
    url = f'api/exports/{job["job_id"]}'
    # Still running: the request did not wait for the export.
    assert client.get(url).json()['status'] == 'running'
    assert client.get(url + '/download').status_code == HTTPStatus.NOT_FOUND
    # One at a time.
    again = client.post('api/exports', json={'upload_id': 'mine'})
    assert again.status_code == HTTPStatus.CONFLICT

    client.later.run()
    assert client.get(url).json()['status'] == 'done'
    response = client.get(url + '/download')
    assert response.status_code == HTTPStatus.OK
    assert response.headers['content-type'] == 'application/zip'
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert sorted(archive.namelist()) == [
            'a.archive.json',
            'referenced/database/t.archive.json',
        ]

    # Another user knows nothing of it.
    client.state.user = BOB
    assert client.get(url).status_code == HTTPStatus.NOT_FOUND
    assert client.get(url + '/download').status_code == HTTPStatus.NOT_FOUND


@pytest.mark.parametrize(
    'upload_id, status',
    [
        ('private', HTTPStatus.FORBIDDEN),
        ('nope', HTTPStatus.NOT_FOUND),
        ('busy', HTTPStatus.CONFLICT),
        ('../x', HTTPStatus.UNPROCESSABLE_ENTITY),
        ('', HTTPStatus.UNPROCESSABLE_ENTITY),
    ],
)
def test_no_export_of_an_upload_that_cannot_be_exported(client, upload_id, status):
    response = client.post('api/exports', json={'upload_id': upload_id})
    assert response.status_code == status
    assert client.later.pending == []


def test_page_and_its_scripts_are_served(client):
    page = client.get('')
    assert page.status_code == HTTPStatus.OK
    # Served at their paths on disk relative to dashboards/, which the
    # imports in publication.js rely on.
    for path in (
        'publication/static/publication.js',
        'common/static/style.css',
        'common/static/config.js',
        'common/static/nomad-api.js',
        'common/static/util.js',
    ):
        assert client.get(path).status_code == HTTPStatus.OK, path
    assert 'publication/static/publication.js' in page.text
    assert 'common/static/style.css' in page.text


def test_requests_need_a_login(tmp_path):
    """With NOMAD's own check of the user: no token, no export."""
    pytest.importorskip('mongoengine', reason=NEEDS_NOMAD_SERVER)
    client = TestClient(app_module.create_app(Jobs(tmp_path, executor=Later())))
    response = client.post('api/exports', json={'upload_id': 'mine'})
    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert client.get('api/exports/' + '0' * 32).status_code == HTTPStatus.UNAUTHORIZED


def test_the_signature_token_of_the_page_is_accepted(tmp_path, monkeypatch):
    """The page sends a token from NOMAD's /auth/signature_token as Bearer."""
    pytest.importorskip('mongoengine', reason=NEEDS_NOMAD_SERVER)
    from nomad.auth.tokens import generate_simple_token
    from nomad.config import config
    from nomad.datamodel import User
    from pydantic import SecretStr

    monkeypatch.setattr(
        config.services, 'api_secret', SecretStr('a test secret of 32 characters!!')
    )

    user = SimpleNamespace(user_id='alice', email='a@lab', username='alice')

    async def a_get(**query):
        return user if query.get('user_id') == 'alice' else None

    monkeypatch.setattr(User, 'a_get', a_get)
    client = TestClient(app_module.create_app(Jobs(tmp_path, executor=Later())))
    token = generate_simple_token('alice', expires_in=10)
    response = client.get(
        'api/exports/' + '0' * 32, headers={'Authorization': f'Bearer {token}'}
    )
    # Logged in: the export is unknown, rather than the user.
    assert response.status_code == HTTPStatus.NOT_FOUND
