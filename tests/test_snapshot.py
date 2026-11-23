"""
A snapshot of an upload for publication: the upload and the entries it refers
to in other uploads, with references that stay inside the snapshot.
"""

import json

import pytest
import yaml
from helpers import DATABASE_UPLOAD
from nomad.datamodel.util import parse_path
from nomad.utils import generate_entry_id

# Loaded in the Oasis as a plugin; the export looks sections up among those.
import differ_pld4e_schemas.schema_packages.schema_package  # noqa: F401
from differ_pld4e_schemas.snapshot import SnapshotError, build_snapshot
from differ_pld4e_schemas.yaml_schema import schema_path

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
        # What NOMAD stored when processing, where it is not the file's data.
        self.processed = {}

    def processed_data(self, upload_id, path):
        """By default, as if processing left the data of the file as it is."""
        if (upload_id, path) in self.processed:
            processed = self.processed[upload_id, path]
            if isinstance(processed, Exception):
                raise processed
            return processed
        return yaml.safe_load(self.uploads[upload_id][path]).get('data')

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
    # With data, an archive is written as JSON (which is YAML) under its name.
    assert yaml.safe_load(files['a.archive.yaml'])['data'] == {
        'by_file': target,
        'encoded': target,
        'other_nomad': target,
        'in_upload_by_id': f'{INTERNAL}b.archive.json#/data',
    }
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


_PLUGIN = 'differ_pld4e_schemas.schema_packages.schema_package'
_OWN = schema_path('differ_pld4e_schemas')
_NMP = schema_path('nomad_material_processing')
_EDS = schema_path('helpers')
_LAEDS = schema_path('laeds_tools')
SCHEMA = f'../upload/raw/{_OWN}#'


def _logbook_upload():
    """A logbook and a sample of this plugin, on a target of the database."""
    return Uploads(
        {
            UPLOAD: {
                'logbook.archive.json': json.dumps(
                    {
                        'data': {
                            'm_def': f'{_PLUGIN}.SAPLDLogbook',
                            'steps': [
                                {
                                    'm_def': 'differ_pld4e_schemas.pld_deposition.'
                                    'SAPLDHeatingStep'
                                }
                            ],
                            'target': _by_id(DATABASE_UPLOAD, 'YSZ.archive.yaml'),
                        }
                    }
                ),
                'sample.archive.yaml': (
                    'data:\n'
                    f'  m_def: {_PLUGIN}.Sample\n'
                    '  results:\n'
                    "    m_def: 'nomad.datamodel.results.Results'\n"
                    '  pld:\n'
                    '    m_def: "nomad_material_processing.vapor_deposition.pvd.pld.'
                    'PLDTarget"\n'
                ),
            },
            DATABASE_UPLOAD: {
                'YSZ.archive.yaml': f'data:\n  m_def: {_PLUGIN}.PLDTarget\n'
            },
        }
    )


def test_snapshot_holds_the_schemas_of_the_plugins_it_uses():
    files = build_snapshot(UPLOAD, _logbook_upload())
    # nomad-material-processing and laeds_tools too: this plugin's sections
    # build on them.
    assert sorted(path for path in files if path.startswith('schema/')) == [
        _OWN,
        _LAEDS,
        _NMP,
    ]
    own = yaml.safe_load(files[_OWN])['definitions']['sections']
    assert f'../upload/raw/{_NMP}#PLDTarget' in own['PLDTarget']['base_sections']
    # An upload without sections of plugins needs no schema.
    assert not any(
        path.startswith('schema/') for path in build_snapshot(UPLOAD, _lab())
    )


def test_entries_name_their_sections_in_the_schemas():
    """Wherever the section is named, and by any module of the plugin that has it."""
    files = build_snapshot(UPLOAD, _logbook_upload())
    logbook = _data(files, 'logbook.archive.json')
    assert logbook['m_def'] == f'{SCHEMA}SAPLDLogbook'
    assert logbook['steps'][0]['m_def'] == f'{SCHEMA}SAPLDHeatingStep'
    sample = yaml.safe_load(files['sample.archive.yaml'])['data']
    assert sample['m_def'] == f'{SCHEMA}Sample'
    # NOMAD's own sections are in every NOMAD.
    assert sample['results']['m_def'] == 'nomad.datamodel.results.Results'
    assert sample['pld']['m_def'] == f'../upload/raw/{_NMP}#PLDTarget'
    # A copied entry names its section in the schemas of the snapshot.
    copied = yaml.safe_load(files[f'referenced/{DATABASE_UPLOAD}/YSZ.archive.yaml'])
    assert copied['data']['m_def'] == f'{SCHEMA}PLDTarget'


def test_archives_hold_the_data_nomad_stored_for_them():
    """What a normalizer filled in is kept as values; the rest of the file too."""
    import helpers.eds_plugin  # noqa: F401 (loaded in the Oasis as a plugin)

    spectrum = 'eds/spectrum.archive.json'
    uploads = Uploads(
        {
            UPLOAD: {
                spectrum: json.dumps(
                    {
                        'data': {
                            'm_def': 'helpers.eds_plugin.Spectrum',
                            'data_file': 'x.sp0',
                        }
                    }
                ),
                'eds/x.sp0': 'Iridium',
                'sample.archive.json': _archive(m_def=f'{_PLUGIN}.Sample'),
                'schema_of_mine.archive.yaml': 'definitions:\n  name: mine\n',
            }
        }
    )
    uploads.processed[UPLOAD, spectrum] = {
        'm_def': 'helpers.eds_plugin.Spectrum',
        'm_def_id': 'a1b2',
        'data_file': 'x.sp0',
        'sample': f'../upload/archive/{generate_entry_id(UPLOAD, "sample.archive.json")}'
        '#/data',
        'settings': {'live_time': 100.0, 'm_def_id': 'c3d4'},
        'energy': [10.0, 20.0],
        'counts': [5, 7],
    }
    files = build_snapshot(UPLOAD, uploads)

    assert _data(files, spectrum) == {
        'm_def': f'../upload/raw/{_EDS}#Spectrum',
        'data_file': 'x.sp0',
        'sample': f'{INTERNAL}sample.archive.json#/data',
        'settings': {'live_time': 100.0},
        'energy': [10.0, 20.0],
        'counts': [5, 7],
    }
    # An archive without data, such as a schema of the upload, is kept as it is.
    assert files['schema_of_mine.archive.yaml'] == b'definitions:\n  name: mine\n'
    # One file per plugin; this one refers to the sample of the other.
    assert sorted(path for path in files if path.startswith('schema/')) == [
        _OWN,
        _EDS,
        _LAEDS,
        _NMP,
    ]
    eds = yaml.safe_load(files[_EDS])['definitions']['sections']
    assert eds['Spectrum']['quantities']['sample']['type']['type_data'] == (
        f'../upload/raw/{_OWN}#Sample'
    )


@pytest.mark.parametrize(
    'processed, problem',
    [
        (SnapshotError('a.archive.json: NOMAD could not process'), 'could not process'),
        # The file has data, so its entry should have too.
        (None, 'NOMAD stored no data'),
    ],
)
def test_no_snapshot_without_the_data_nomad_stored(processed, problem):
    uploads = Uploads({UPLOAD: {'a.archive.json': _archive(name='x')}})
    uploads.processed[UPLOAD, 'a.archive.json'] = processed
    with pytest.raises(SnapshotError, match=problem):
        build_snapshot(UPLOAD, uploads)


def test_no_snapshot_with_sections_no_schema_holds():
    uploads = Uploads(
        {
            UPLOAD: {
                'a.archive.json': _archive(m_def='differ_pld4e_schemas.gone.Section'),
                'b.archive.yaml': 'data:\n  m_def: other_plugin.schemas.Thing\n',
            }
        }
    )
    with pytest.raises(SnapshotError) as error:
        build_snapshot(UPLOAD, uploads)
    message = str(error.value)
    assert (
        'a.archive.json' in message and 'differ_pld4e_schemas.gone.Section' in message
    )
    assert 'b.archive.yaml' in message and 'other_plugin.schemas.Thing' in message
    # Each reported once.
    assert message.count('a.archive.json') == message.count('b.archive.yaml') == 1


def test_upload_may_not_use_the_directory_of_the_schemas():
    uploads = Uploads({UPLOAD: {'schema/notes.txt': 'x'}})
    with pytest.raises(SnapshotError, match='schema/notes.txt'):
        build_snapshot(UPLOAD, uploads)


@pytest.mark.parametrize(
    'content',
    [
        f'data:\n  m_def :  {_PLUGIN}.Sample\n',
        f"data: {{'m_def': {_PLUGIN}.Sample}}\n",
        f'data: {{m_def: {_PLUGIN}.Sample, name: x}}\n',
        '{"data": {"m_def": "differ_pld4e_schemas.sample.Sample"}}',
    ],
)
def test_m_def_forms(content):
    files = build_snapshot(UPLOAD, Uploads({UPLOAD: {'a.archive.yaml': content}}))
    assert yaml.safe_load(files['a.archive.yaml'])['data']['m_def'] == (
        f'{SCHEMA}Sample'
    )


@pytest.mark.parametrize(
    'data',
    [
        # Already in a schema, another key that ends in m_def, not a Python name.
        {'m_def': f'{SCHEMA}Sample'},
        {'my_m_def': 'a.b.C'},
        {'m_def': 'a.b-c.D'},
    ],
)
def test_m_defs_left_as_they_are(data):
    uploads = Uploads({UPLOAD: {'a.archive.json': json.dumps({'data': data})}})
    assert _data(build_snapshot(UPLOAD, uploads), 'a.archive.json') == data


def test_no_snapshot_with_plugin_definitions_named_outside_an_m_def():
    """An upload's own YAML schema built on the plugin's would not resolve elsewhere."""
    schema = (
        'definitions:\n'
        '  sections:\n'
        '    MySample:\n'
        f'      base_sections: [{_PLUGIN}.Sample]\n'
    )
    uploads = Uploads({UPLOAD: {'my_schema.archive.yaml': schema}})
    with pytest.raises(SnapshotError) as error:
        build_snapshot(UPLOAD, uploads)
    message = str(error.value)
    assert 'my_schema.archive.yaml' in message and f'{_PLUGIN}.Sample' in message
    assert len(message.splitlines()) == 1


VALUE = 1.5


def test_archives_keep_their_format():
    """Values YAML and JSON write differently, such as NaN, keep their value."""
    uploads = Uploads(
        {
            UPLOAD: {
                'a.archive.yaml': 'metadata:\n  made: 2026-11-23\ndata:\n  name: a\n',
                'b.archive.json': _archive(name='b'),
            }
        }
    )
    long_name = 'x' * 200
    for path in ('a.archive.yaml', 'b.archive.json'):
        uploads.processed[UPLOAD, path] = {
            'name': long_name,
            'values': [VALUE, float('nan'), float('inf')],
            'text': 'Ångström – 10 µm',
        }
    files = build_snapshot(UPLOAD, uploads)

    a = yaml.safe_load(files['a.archive.yaml'])
    assert str(a['metadata']['made']) == '2026-11-23'  # a date, kept as one
    b = json.loads(files['b.archive.json'])  # Python's json, as NOMAD reads it
    for data in (a['data'], b['data']):
        assert data['name'] == long_name and data['text'] == 'Ångström – 10 µm'
        assert data['values'][0] == VALUE and data['values'][2] == float('inf')
        assert data['values'][1] != data['values'][1]  # NaN
    # A YAML archive stays YAML, with long values on one line.
    assert files['a.archive.yaml'].decode().count('\n') == len(
        yaml.safe_dump(a, width=float('inf'), allow_unicode=True).splitlines()
    )


def test_nomad_sections_named_by_a_plugin_module_get_nomads_name():
    """A plugin module that imports a section of NOMAD has it under its name too."""
    uploads = Uploads(
        {
            UPLOAD: {
                'a.archive.json': _archive(
                    m_def='differ_pld4e_schemas.sample.CompositeSystem'
                )
            }
        }
    )
    files = build_snapshot(UPLOAD, uploads)
    assert _data(files, 'a.archive.json')['m_def'] == (
        'nomad.datamodel.metainfo.basesections.v1.CompositeSystem'
    )
    assert not any(path.startswith('schema/') for path in files)


def test_text_that_looks_like_python_names_is_left_as_it_is():
    data = {
        'data_file': 'run 1/x.sp0',
        'note': 'e.g. scipy.stats or numpy.float64, see os.path',
    }
    uploads = Uploads({UPLOAD: {'a.archive.json': json.dumps({'data': data})}})
    assert _data(build_snapshot(UPLOAD, uploads), 'a.archive.json') == data


def test_copied_entries_have_the_data_stored_in_their_upload():
    uploads = Uploads(
        {
            UPLOAD: {
                'a.archive.json': _archive(t=_by_id(DATABASE_UPLOAD, 'T.archive.json'))
            },
            DATABASE_UPLOAD: {'T.archive.json': _archive(material='raw')},
        }
    )
    uploads.processed[DATABASE_UPLOAD, 'T.archive.json'] = {'material': 'stored'}
    files = build_snapshot(UPLOAD, uploads)
    copied = _data(files, f'referenced/{DATABASE_UPLOAD}/T.archive.json')
    assert copied == {'material': 'stored'}
