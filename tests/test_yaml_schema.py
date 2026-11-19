"""
The plugin's schemas as a YAML schema: what an exported upload brings along so
that a NOMAD without this plugin or nomad-material-processing can read it.
"""

import json
import re
import subprocess
import sys
import warnings
from pathlib import Path

import pytest
import yaml
from nomad.datamodel import EntryArchive
from nomad.metainfo import Reference

from differ_pld4e_schemas.snapshot import build_snapshot
from differ_pld4e_schemas.yaml_schema import (
    PACKAGE_NAME,
    SCHEMA_PATH,
    plugin_yaml_schema,
)

EXAMPLES = sorted((Path(__file__).parent / 'data').glob('*.archive.yaml'))
assert EXAMPLES, 'the examples in tests/data are missing'


@pytest.fixture(scope='module')
def schema():
    return plugin_yaml_schema()


@pytest.fixture(scope='module')
def yaml_sections(schema):
    """The sections of the YAML schema, as NOMAD reads them, by name."""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        archive = EntryArchive.m_from_dict(yaml.safe_load(schema.text))
        # As NOMAD does with a schema package it loads (nomad.schemas).
        archive.definitions.init_metainfo()
    return {
        section.name: section for section in archive.definitions.section_definitions
    }


def _python_sections(schema):
    """The sections the YAML schema holds, as the plugin defines them, by YAML name."""
    from differ_pld4e_schemas.schema_packages.schema_package import m_package

    sections = {}
    todo = list(m_package.section_definitions)
    while todo:
        section = todo.pop()
        name = schema.names.get(section.qualified_name())
        if name is None or name in sections:
            continue
        sections[name] = section
        todo += section.base_sections
        todo += [sub_section.sub_section for sub_section in section.sub_sections]
        todo += [
            quantity.type.target_section_def
            for quantity in section.quantities
            if isinstance(quantity.type, Reference)
        ]
    return sections


def test_schema_relies_only_on_nomad(schema):
    # Other packages may be named only in prose and in the schema's own file name.
    outside = re.findall(
        r'(?:differ_pld4e_schemas|nomad_material_processing)\.(?!archive\.yaml)\w+',
        schema.text,
    )
    assert outside == []
    assert '/section_definitions/' not in schema.text
    names = set(re.findall(r'\bnomad(?:\.\w+)+', schema.text))
    for name in names:
        assert name.startswith(('nomad.datamodel.', 'nomad.metainfo.')), name


def test_schema_holds_nomad_material_processing_sections(schema, yaml_sections):
    assert (
        schema.section_name(
            'nomad_material_processing.vapor_deposition.pvd.pld.PulsedLaserDeposition'
        )
        == 'PulsedLaserDeposition'
    )
    # The plugin has a PLDTarget too, which extends this one.
    plugin_target = 'differ_pld4e_schemas.schema_packages.schema_package.PLDTarget'
    nmp_target = 'nomad_material_processing.vapor_deposition.pvd.pld.PLDTarget'
    assert schema.section_name(plugin_target) == 'PLDTarget'
    assert schema.section_name(nmp_target) == 'pld_PLDTarget'
    bases = [base.name for base in yaml_sections['PLDTarget'].base_sections]
    assert 'pld_PLDTarget' in bases


def test_sections_are_named_by_any_module_that_has_them(schema):
    assert schema.section_name('differ_pld4e_schemas.pld_deposition.SAPLDLogbook') == (
        'SAPLDLogbook'
    )
    assert schema.section_name('differ_pld4e_schemas.gone.SAPLDLogbook') is None
    assert schema.section_name('nomad.datamodel.data.EntryData') is None


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


def _yaml_name(section):
    """A section of the YAML schema by its name in it; NOMAD's by Python name."""
    qualified = section.qualified_name()
    return section.name if qualified.startswith(f'{PACKAGE_NAME}.') else qualified


def test_yaml_sections_are_those_of_the_plugin(schema, yaml_sections):
    python = _python_sections(schema)
    assert set(python) == set(yaml_sections)

    def python_name(section):
        """A section of the plugin by the name the YAML schema gives it."""
        qualified = section.qualified_name()
        return schema.names.get(qualified, qualified)

    for name, section in python.items():
        copy = yaml_sections[name]
        assert [python_name(base) for base in section.all_base_sections] == [
            _yaml_name(base) for base in copy.all_base_sections
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
                assert python_name(quantity.type.target_section_def) == _yaml_name(
                    other.type.target_section_def
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
            assert python_name(sub_section.sub_section) == _yaml_name(
                other.sub_section
            ), f'{name}.{key}'


class _OneUpload:
    def __init__(self, files):
        self.files = files

    def raw_files(self, upload_id):
        return dict(self.files)

    def mainfiles(self, upload_id):
        return {}

    def raw_file(self, upload_id, path):
        return self.files[path]


def _without_m_def(value):
    if isinstance(value, dict):
        return {k: _without_m_def(v) for k, v in value.items() if k != 'm_def'}
    if isinstance(value, list):
        return [_without_m_def(item) for item in value]
    return value


# Reads exported entries in a NOMAD without this plugin and nomad-material-
# processing, as the central NOMAD is: neither can be imported, nor are their
# entry points found. NOMAD reads the schema file as it does in an upload.
_WITHOUT_PLUGINS = """
import importlib.abc, importlib.metadata, json, sys, warnings
import yaml

HIDDEN = ('differ_pld4e_schemas', 'nomad_material_processing')

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
    files = build_snapshot(
        'u', _OneUpload({example.name: example.read_bytes() for example in EXAMPLES})
    )
    for path, content in files.items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_bytes(content)
    names = [example.name for example in EXAMPLES]
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
        assert read['section'] == f'{PACKAGE_NAME}.{with_plugin.data.m_def.name}'
        expected = json.loads(json.dumps(with_plugin.data.m_to_dict(), default=str))
        assert _without_m_def(read['data']) == _without_m_def(expected)


@pytest.mark.parametrize('example', EXAMPLES, ids=lambda path: path.name)
def test_exported_entries_read_the_same_without_the_plugin(example, schema):
    files = build_snapshot('u', _OneUpload({example.name: example.read_bytes()}))
    exported = yaml.safe_load(files[example.name])
    assert files[SCHEMA_PATH] == schema.text.encode()

    # Every section is named in the schema file; read it within one archive.
    prefix = f'../upload/raw/{SCHEMA_PATH}#'
    text = yaml.safe_dump(exported)
    assert re.findall(r'm_def: (\S+)', text) and all(
        m_def.startswith(prefix) for m_def in re.findall(r'm_def: (\S+)', text)
    )
    exported = yaml.safe_load(text.replace(prefix, ''))
    exported['definitions'] = yaml.safe_load(schema.text)['definitions']
    with warnings.catch_warnings():
        # NOMAD 2.0 warns about every sub-section of a YAML section that holds a
        # section derived from the one it is defined with.
        warnings.filterwarnings('ignore', 'is not derived from its definition')
        without_plugin = EntryArchive.m_from_dict(exported)
    with_plugin = EntryArchive.m_from_dict(yaml.safe_load(example.read_text()))

    assert type(without_plugin.data).__module__ == 'nomad.metainfo.metainfo'
    assert without_plugin.data.m_def.name == with_plugin.data.m_def.name
    assert _without_m_def(without_plugin.data.m_to_dict()) == _without_m_def(
        with_plugin.data.m_to_dict()
    )
