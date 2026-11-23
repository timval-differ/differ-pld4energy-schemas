"""
Schemas of plugins as YAML schemas, one file per plugin: what an exported
upload brings along so that a NOMAD without this plugin, nomad-material-
processing or the other plugins of the Oasis can read it.
"""

import json
import re
import subprocess
import sys
import warnings
from pathlib import Path

import pytest
import yaml
from helpers import eds_plugin
from nomad.datamodel import EntryArchive
from nomad.datamodel.context import ClientContext
from nomad.metainfo import Reference

from differ_pld4e_schemas.schema_packages.schema_package import m_package
from differ_pld4e_schemas.snapshot import build_snapshot
from differ_pld4e_schemas.yaml_schema import schema_path, section_of, yaml_schemas

EXAMPLES = sorted((Path(__file__).parent / 'data').glob('*.archive.yaml'))
assert EXAMPLES, 'the examples in tests/data are missing'

OWN = schema_path('differ_pld4e_schemas')
NMP = schema_path('nomad_material_processing')
EDS = schema_path('helpers')


@pytest.fixture(scope='module')
def schemas():
    return yaml_schemas([m_package, eds_plugin.m_package])


def _write(files, directory):
    for path, content in files.items():
        (directory / path).parent.mkdir(parents=True, exist_ok=True)
        data = content.encode() if isinstance(content, str) else content
        (directory / path).write_bytes(data)


def _read(directory, path):
    """An archive of `directory`, read as NOMAD reads a file of an upload."""
    with warnings.catch_warnings():
        # NOMAD 2.0 warns about every sub-section of a YAML section that holds a
        # section derived from the one it is defined with.
        warnings.filterwarnings('ignore', 'is not derived from its definition')
        return EntryArchive.m_from_dict(
            yaml.safe_load((directory / path).read_text(encoding='utf-8')),
            m_context=ClientContext(local_dir=str(directory), auth=object()),
        )


@pytest.fixture(scope='module')
def yaml_sections(schemas, tmp_path_factory):
    """The sections of the YAML schemas, as NOMAD reads them, by (file, name)."""
    directory = tmp_path_factory.mktemp('upload')
    _write(schemas.files, directory)
    sections = {}
    for path in schemas.files:
        definitions = _read(directory, path).definitions
        for section in definitions.section_definitions:
            # Sets the section up after its bases, as reading data of it does.
            assert section.section_cls is not None
            sections[path, section.name] = section
    return sections


def _location(section):
    """A section of a YAML schema by (file, name); NOMAD's by Python name."""
    package, _, name = section.qualified_name().rpartition('.')
    if package.endswith('_yaml'):
        return schema_path(package.removesuffix('_yaml')), name
    return section.qualified_name()


def test_one_schema_file_per_plugin(schemas):
    assert sorted(schemas.files) == sorted([OWN, NMP, EDS])


def test_schemas_rely_only_on_nomad_and_each_other(schemas):
    for path, text in schemas.files.items():
        # Plugins may be named only in prose and in the schema files' names.
        outside = re.findall(
            r'(?<![/\w])(?:differ_pld4e_schemas|nomad_material_processing|helpers)'
            r'\.(?!archive\.yaml)\w+',
            text,
        )
        assert outside == [], path
        assert '/section_definitions/' not in text, path
        for name in set(re.findall(r'\bnomad(?:\.\w+)+', text)):
            assert name.startswith(('nomad.datamodel.', 'nomad.metainfo.')), name


def test_sections_of_other_files_are_named_by_their_file(schemas):
    own = yaml.safe_load(schemas.files[OWN])['definitions']['sections']
    # The plugin has a PLDTarget too, which extends nomad-material-processing's.
    assert f'../upload/raw/{NMP}#PLDTarget' in own['PLDTarget']['base_sections']
    eds = yaml.safe_load(schemas.files[EDS])['definitions']['sections']
    assert eds['Spectrum']['quantities']['sample']['type']['type_data'] == (
        f'../upload/raw/{OWN}#Sample'
    )


def test_sections_are_found_by_any_module_that_has_them():
    assert (
        section_of('differ_pld4e_schemas.pld_deposition.SAPLDLogbook')
        is (m_package.all_definitions['SAPLDLogbook'])
    )
    assert section_of('differ_pld4e_schemas.gone.SAPLDLogbook') is None
    assert section_of('not_imported_module.Thing') is None


def _python_sections(schemas):
    """The sections the YAML schemas hold, as Python defines them, by (file, name)."""
    sections = {}
    todo = list(m_package.section_definitions) + list(
        eds_plugin.m_package.section_definitions
    )
    while todo:
        section = todo.pop()
        location = schemas.locations.get(section.qualified_name())
        if location is None or location in sections:
            continue
        sections[location] = section
        todo += section.base_sections
        todo += [sub_section.sub_section for sub_section in section.sub_sections]
        todo += [
            quantity.type.target_section_def
            for quantity in section.quantities
            if isinstance(quantity.type, Reference)
        ]
    return sections


def _annotations(definition):
    """
    The annotations of `definition` by kind, as dicts. Read from YAML, NOMAD
    keeps an annotation in a list of one, where Python keeps it as it is.
    """
    result = {}
    for kind, value in definition.m_annotations.items():
        annotations = value if isinstance(value, list) else [value]
        result[kind] = [
            annotation.model_dump(exclude={'m_definition', 'm_error'})
            if hasattr(annotation, 'model_dump')
            else annotation
            for annotation in annotations
        ]
    return result


def test_yaml_sections_are_those_of_the_plugins(schemas, yaml_sections):
    python = _python_sections(schemas)
    assert set(python) == set(yaml_sections)

    def python_location(section):
        qualified = section.qualified_name()
        return schemas.locations.get(qualified, qualified)

    for location, section in python.items():
        copy = yaml_sections[location]
        name = '#'.join(location)
        assert [python_location(base) for base in section.all_base_sections] == [
            _location(base) for base in copy.all_base_sections
        ], name
        assert copy.label == section.label and copy.description == section.description
        assert copy.more == section.more and copy.links == section.links, name
        assert _annotations(copy) == _annotations(section), name

        assert set(copy.all_quantities) == set(section.all_quantities), name
        for key, quantity in section.all_quantities.items():
            other = copy.all_quantities[key]
            where = f'{name}.{key}'
            if isinstance(quantity.type, Reference):
                assert isinstance(other.type, Reference), where
                assert python_location(quantity.type.target_section_def) == (
                    _location(other.type.target_section_def)
                ), where
            else:
                assert other.m_to_dict()['type'] == quantity.m_to_dict()['type'], where
            assert str(other.unit) == str(quantity.unit), where
            assert other.shape == quantity.shape, where
            assert other.default == quantity.default, where
            assert _annotations(other) == _annotations(quantity), where

        assert set(copy.all_sub_sections) == set(section.all_sub_sections), name
        for key, sub_section in section.all_sub_sections.items():
            other = copy.all_sub_sections[key]
            assert other.repeats == sub_section.repeats, f'{name}.{key}'
            assert python_location(sub_section.sub_section) == _location(
                other.sub_section
            ), f'{name}.{key}'


def _processed(content: bytes) -> dict:
    """The data NOMAD stores for an archive, as the plugins read it."""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return EntryArchive.m_from_dict(yaml.safe_load(content)).m_to_dict()['data']


# A spectrum entry of the other plugin, as its normalizer leaves it.
SPECTRUM = 'eds/spectrum.archive.json'
SPECTRUM_DATA = {
    'm_def': 'helpers.eds_plugin.Spectrum',
    'data_file': 'spectrum.sp0',
    'settings': {'live_time': 100.0},
    'energy': [10.0, 20.0, 30.0],
    'counts': [5, 7, 2],
}


class _OneUpload:
    """The examples (and the spectrum), as NOMAD processed them."""

    def __init__(self, files):
        self.files = files

    def raw_files(self, upload_id):
        return dict(self.files)

    def mainfiles(self, upload_id):
        return {}

    def raw_file(self, upload_id, path):
        return self.files[path]

    def processed_data(self, upload_id, path):
        if path == SPECTRUM:
            return SPECTRUM_DATA
        return _processed(self.files[path])


def _export(names):
    files = {example.name: example.read_bytes() for example in EXAMPLES}
    files[SPECTRUM] = json.dumps({'data': {'data_file': 'spectrum.sp0'}}).encode()
    return build_snapshot('u', _OneUpload({name: files[name] for name in names}))


def _without_m_def(value):
    if isinstance(value, dict):
        return {k: _without_m_def(v) for k, v in value.items() if k != 'm_def'}
    if isinstance(value, list):
        return [_without_m_def(item) for item in value]
    return value


@pytest.mark.parametrize('example', EXAMPLES, ids=lambda path: path.name)
def test_exported_entries_read_the_same_from_the_schemas(example, tmp_path):
    files = _export([example.name])
    _write(files, tmp_path)
    exported = _read(tmp_path, example.name)
    with_plugin = EntryArchive.m_from_dict(yaml.safe_load(example.read_text()))

    assert type(exported.data).__module__ == 'nomad.metainfo.metainfo'
    assert exported.data.m_def.qualified_name() == (
        f'differ_pld4e_schemas_yaml.{with_plugin.data.m_def.name}'
    )
    assert _without_m_def(exported.data.m_to_dict()) == _without_m_def(
        with_plugin.data.m_to_dict()
    )


# Reads exported entries in a NOMAD without the plugins, as the central NOMAD
# is: none can be imported, nor are their entry points found. NOMAD reads the
# schema files as it does in an upload.
_WITHOUT_PLUGINS = """
import importlib.abc, importlib.metadata, json, sys, warnings
import yaml

HIDDEN = ('differ_pld4e_schemas', 'nomad_material_processing', 'helpers')

class Hide(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path, target=None):
        if name.split('.')[0] in HIDDEN:
            raise ModuleNotFoundError(f'No module named {name!r}', name=name)

sys.meta_path.insert(0, Hide())
entry_points = importlib.metadata.entry_points

def without_hidden(**kwargs):
    found = entry_points(**kwargs)
    if kwargs.get('group') != 'nomad.plugin':
        return found
    return importlib.metadata.EntryPoints(
        point
        for point in found
        if point.value.split(':')[0].split('.')[0] not in HIDDEN
    )

importlib.metadata.entry_points = without_hidden
warnings.simplefilter('ignore')
from nomad.datamodel import EntryArchive
from nomad.datamodel.context import ClientContext

directory, names = sys.argv[1], sys.argv[2:]
result = {}
for name in names:
    with open(f'{directory}/{name}', encoding='utf-8') as file:
        archive = EntryArchive.m_from_dict(
            yaml.safe_load(file),
            m_context=ClientContext(local_dir=directory, auth=object()),
        )
    result[name] = {
        'section': archive.data.m_def.qualified_name(),
        'data': archive.data.m_to_dict(),
    }
print(json.dumps(result, default=str))
"""


def test_exported_upload_reads_in_a_nomad_without_the_plugins(tmp_path):
    names = [example.name for example in EXAMPLES] + [SPECTRUM]
    _write(_export(names), tmp_path)
    process = subprocess.run(
        [sys.executable, '-c', _WITHOUT_PLUGINS, str(tmp_path), *names],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert process.returncode == 0, process.stderr[-3000:]
    result = json.loads(process.stdout.strip().splitlines()[-1])

    for example in EXAMPLES:
        read = result[example.name]
        with_plugin = EntryArchive.m_from_dict(yaml.safe_load(example.read_text()))
        assert read['section'] == (
            f'differ_pld4e_schemas_yaml.{with_plugin.data.m_def.name}'
        )
        expected = json.loads(json.dumps(with_plugin.data.m_to_dict(), default=str))
        assert _without_m_def(read['data']) == _without_m_def(expected)

    # What the other plugin's normalizer filled in reads back as values.
    spectrum = result[SPECTRUM]
    assert spectrum['section'] == 'helpers_yaml.Spectrum'
    assert _without_m_def(spectrum['data']) == _without_m_def(SPECTRUM_DATA)
