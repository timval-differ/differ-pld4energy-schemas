"""
A snapshot of an upload for publication: the upload and the entries it refers
to in other uploads, with references that stay inside the snapshot.
"""

import json

import pytest
from helpers import DATABASE_UPLOAD
from nomad.datamodel.util import parse_path
from nomad.utils import generate_entry_id

from differ_pld4e_schemas.snapshot import SnapshotError, build_snapshot

UPLOAD = 'researchers_upload'
INTERNAL = '../upload/archive/mainfile/'


class Uploads:
    """Uploads in memory: {upload id: {path: content}}; every archive is an entry."""

    def __init__(self, uploads):
        self.uploads = {
            upload_id: {
                path: content if isinstance(content, bytes) else content.encode()
                for path, content in files.items()
            }
            for upload_id, files in uploads.items()
        }
        self.single_reads = []

    def raw_files(self, upload_id):
        return dict(self.uploads[upload_id])

    def mainfiles(self, upload_id):
        return {
            generate_entry_id(upload_id, path): path
            for path in self.uploads.get(upload_id, {})
            if '.archive.' in path
        }

    def raw_file(self, upload_id, path):
        self.single_reads.append((upload_id, path))
        try:
            return self.uploads[upload_id][path]
        except KeyError:
            raise SnapshotError(f'Cannot read "{path}" of upload {upload_id}') from None


def _by_id(upload_id, path, fragment='#/data'):
    entry_id = generate_entry_id(upload_id, path)
    return f'../uploads/{upload_id}/archive/{entry_id}{fragment}'


def _archive(**data):
    return json.dumps({'data': data})


def _data(files, path):
    return json.loads(files[path])['data']


def _lab():
    """A logbook and its sample, on a target and a substrate of the database."""
    return Uploads(
        {
            UPLOAD: {
                'run 1/logbook.archive.json': _archive(
                    targets=[{'target': _by_id(DATABASE_UPLOAD, 'YSZ.archive.json')}],
                    samples=[_by_id(UPLOAD, 'sample.archive.json')],
                    recipe='../upload/archive/mainfile/recipe.archive.yaml#data',
                    own='#/data/steps/0',
                ),
                'sample.archive.json': _archive(
                    substrate=_by_id(DATABASE_UPLOAD, 'STO.archive.json'),
                    layers=[
                        {
                            'target': _by_id(
                                DATABASE_UPLOAD, 'YSZ.archive.json', '#/data'
                            )
                        }
                    ],
                ),
                'recipe.archive.yaml': 'data:\n  name: recipe\n',
                'run 1/rheed.png': b'\x89PNG\xff\x00',
            },
            DATABASE_UPLOAD: {
                'YSZ.archive.json': _archive(
                    material='8YSZ',
                    supplier='../upload/archive/mainfile/supplier.archive.json#/data',
                ),
                'STO.archive.json': _archive(material='SrTiO3'),
                'supplier.archive.json': _archive(name='A supplier'),
                'unused.archive.json': _archive(material='Ta'),
            },
        }
    )


def test_referenced_entries_are_copied_into_the_snapshot():
    files = build_snapshot(UPLOAD, _lab())
    copied = f'referenced/{DATABASE_UPLOAD}/'
    assert sorted(files) == [
        'recipe.archive.yaml',
        copied + 'STO.archive.json',
        copied + 'YSZ.archive.json',
        # Referenced by the target only: references are followed all the way.
        copied + 'supplier.archive.json',
        'run 1/logbook.archive.json',
        'run 1/rheed.png',
        'sample.archive.json',
    ]
    assert _data(files, copied + 'STO.archive.json') == {'material': 'SrTiO3'}
    assert files['run 1/rheed.png'] == b'\x89PNG\xff\x00'


def test_references_stay_inside_the_snapshot():
    files = build_snapshot(UPLOAD, _lab())
    copied = f'referenced/{DATABASE_UPLOAD}/'
    logbook = _data(files, 'run 1/logbook.archive.json')
    assert logbook == {
        'targets': [{'target': f'{INTERNAL}{copied}YSZ.archive.json#/data'}],
        # A reference into the upload itself by ID: the ID changes too.
        'samples': [f'{INTERNAL}sample.archive.json#/data'],
        'recipe': f'{INTERNAL}recipe.archive.yaml#data',
        'own': '#/data/steps/0',
    }
    sample = _data(files, 'sample.archive.json')
    assert sample['substrate'] == f'{INTERNAL}{copied}STO.archive.json#/data'
    # In the copied target, its own upload is no longer "the upload".
    target = _data(files, copied + 'YSZ.archive.json')
    assert target['supplier'] == f'{INTERNAL}{copied}supplier.archive.json#/data'
    for content in files.values():
        assert b'uploads/' not in content


def test_rewritten_reference_names_the_entry_in_any_upload():
    """As NOMAD reads it: the entry of that file, in whichever upload it is."""
    files = build_snapshot(UPLOAD, _lab())
    path = f'referenced/{DATABASE_UPLOAD}/STO.archive.json'
    assert path in files
    url = _data(files, 'sample.archive.json')['substrate']
    assert parse_path(url, 'central_upload') == (
        None,
        'central_upload',
        generate_entry_id('central_upload', path),
        'archive',
        '/data',
    )
    # From a file in a directory with a space in its name.
    url = _data(files, 'run 1/logbook.archive.json')['samples'][0]
    assert parse_path(url, 'central_upload')[2] == generate_entry_id(
        'central_upload', 'sample.archive.json'
    )


def test_other_reference_forms():
    uploads = Uploads(
        {
            UPLOAD: {
                'a.archive.yaml': (
                    'data:\n'
                    f'  by_file: ../uploads/{DATABASE_UPLOAD}/archive/mainfile/'
                    'my target.archive.json#/data\n'
                    f'  encoded: "../uploads/{DATABASE_UPLOAD}/archive/mainfile/'
                    'my%20target.archive.json#/data"\n'
                    '  other_nomad: https://oasis.example/nomad/api/v1/uploads/'
                    f'{DATABASE_UPLOAD}/archive/'
                    f'{generate_entry_id(DATABASE_UPLOAD, "my target.archive.json")}'
                    '#/data\n'
                    f'  in_upload_by_id: ../upload/archive/'
                    f'{generate_entry_id(UPLOAD, "b.archive.json")}#/data\n'
                ),
                'b.archive.json': _archive(),
                # Not an archive: left as it is.
                'notes.txt': f'see ../uploads/{DATABASE_UPLOAD}/archive/abc#/data',
            },
            DATABASE_UPLOAD: {'my target.archive.json': _archive()},
        }
    )
    files = build_snapshot(UPLOAD, uploads, 'https://oasis.example/nomad/api/v1/')
    target = f'{INTERNAL}referenced/{DATABASE_UPLOAD}/my target.archive.json#/data'
    assert files['a.archive.yaml'].decode() == (
        'data:\n'
        f'  by_file: {target}\n'
        f'  encoded: "{target}"\n'
        f'  other_nomad: {target}\n'
        f'  in_upload_by_id: {INTERNAL}b.archive.json#/data\n'
    )
    assert b'uploads/' in files['notes.txt']
    # The target is read once, however often it is referenced.
    assert uploads.single_reads == [(DATABASE_UPLOAD, 'my target.archive.json')]


def test_no_snapshot_with_references_that_lead_nowhere():
    uploads = Uploads(
        {
            UPLOAD: {
                'a.archive.json': _archive(
                    gone=f'../uploads/{DATABASE_UPLOAD}/archive/no_such_entry#/data',
                    hidden='../uploads/private_upload/archive/some_entry#/data',
                )
            },
            DATABASE_UPLOAD: {},
        }
    )
    with pytest.raises(SnapshotError) as error:
        build_snapshot(UPLOAD, uploads)
    message = str(error.value)
    assert 'a.archive.json' in message
    assert 'no_such_entry' in message and DATABASE_UPLOAD in message
    assert 'some_entry' in message and 'private_upload' in message


@pytest.mark.parametrize(
    'reference, problem',
    [
        ('/entries/some_entry/archive#/data', 'cannot rewrite'),
        ('../entries/some_entry/archive#/data', 'cannot rewrite'),
        (f'/uploads/{DATABASE_UPLOAD}/archive/some_entry#/data', 'cannot rewrite'),
        (f'../uploads/{DATABASE_UPLOAD}/raw/data.csv#/x', 'cannot rewrite'),
        # The same upload and entry IDs in another NOMAD are other entries.
        (
            f'https://other.example/api/v1/uploads/{DATABASE_UPLOAD}/archive/'
            f'{generate_entry_id(DATABASE_UPLOAD, "YSZ.archive.json")}#/data',
            'another NOMAD',
        ),
        (_by_id(DATABASE_UPLOAD, 'what?.archive.json'), 'Rename it'),
        (_by_id(DATABASE_UPLOAD, 'my_mainfile/a.archive.json'), 'Rename it'),
    ],
)
def test_no_snapshot_with_references_that_cannot_be_rewritten(reference, problem):
    uploads = Uploads(
        {
            UPLOAD: {'a.archive.json': _archive(target=reference)},
            DATABASE_UPLOAD: {
                'YSZ.archive.json': _archive(),
                'what?.archive.json': _archive(),
                'my_mainfile/a.archive.json': _archive(),
            },
        }
    )
    with pytest.raises(SnapshotError) as error:
        build_snapshot(UPLOAD, uploads, 'https://oasis.example/api/v1')
    message = str(error.value)
    assert len(message.splitlines()) == 1  # reported once
    assert problem in message and 'a.archive.json' in message


def test_raw_file_references_of_copied_entries_are_not_followed():
    """A raw file of the upload itself is in the snapshot; another's is not."""
    raw = '../upload/raw/spectrum.csv'
    uploads = Uploads(
        {
            UPLOAD: {
                'a.archive.json': _archive(
                    file=raw, target=_by_id(DATABASE_UPLOAD, 'YSZ.archive.json')
                ),
                'spectrum.csv': 'x',
            },
            DATABASE_UPLOAD: {'YSZ.archive.json': _archive()},
        }
    )
    assert _data(build_snapshot(UPLOAD, uploads), 'a.archive.json')['file'] == raw
    uploads.uploads[DATABASE_UPLOAD]['YSZ.archive.json'] = _archive(file=raw).encode()
    with pytest.raises(SnapshotError, match='YSZ.archive.json.*cannot rewrite'):
        build_snapshot(UPLOAD, uploads)


def test_upload_may_not_use_the_directory_of_referenced_entries():
    uploads = Uploads({UPLOAD: {'referenced/x.archive.json': _archive()}})
    with pytest.raises(SnapshotError, match='referenced/x.archive.json'):
        build_snapshot(UPLOAD, uploads)
