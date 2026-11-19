"""
This plugin's schemas as a YAML schema, for NOMADs that do not run the plugin.

The central NOMAD does not have this plugin or nomad-material-processing. An
exported upload brings its schemas along as one `.archive.yaml` schema file
(https://docs.nomad-lab.eu/howto/schemas/define.html), and its entries name
their sections in that file instead of by Python name.

The YAML schema holds every section of the plugin and every section they build
on from outside NOMAD itself (from nomad-material-processing), so it only relies
on NOMAD's own sections. It describes the data; the plugin's Python code
(normalizers, dashboards) does not come along.

References are written from the definitions, not by rewriting what
`m_to_dict` writes: NOMAD 2.0 writes a reference quantity's target as a path in
the target's own package, which inside another package names the wrong section.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from functools import cache
from importlib.metadata import PackageNotFoundError, version

import yaml
from nomad.metainfo import Reference, Section

__all__ = ['SCHEMA_PATH', 'YamlSchema', 'plugin_yaml_schema', 'yaml_schema']

# Where the schema is in an exported upload.
SCHEMA_PATH = 'schema/differ_pld4e_schemas.archive.yaml'

# Distinct from the plugin's package, which NOMAD registers by name where the
# plugin runs.
PACKAGE_NAME = 'differ_pld4e_schemas_yaml'

# A Python name of a definition, as NOMAD writes it ('a.b.Name').
_PYTHON_NAME = re.compile(r'[A-Za-z_]\w*(?:\.\w+)+')

# What `m_to_dict` writes about where a definition sits in its package; the
# YAML form says it by where the definition is written.
_POSITION_KEYS = ('m_def', 'm_parent_index', 'm_parent_sub_section')


def _is_nomad(section: Section) -> bool:
    return section.qualified_name().split('.')[0] == 'nomad'


def _depends_on(section: Section) -> list[Section]:
    """The sections that `section` names: bases, sub-sections, reference targets."""
    names = list(section.base_sections)
    names += [sub_section.sub_section for sub_section in section.sub_sections]
    names += [
        quantity.type.target_section_def
        for quantity in section.quantities
        if isinstance(quantity.type, Reference)
    ]
    return names


def _sections(package) -> list[Section]:
    """
    The sections of `package` and those they build on outside NOMAD, each after
    its base sections.

    NOMAD sets up the sections of a YAML schema in the order they are written,
    and a section inherits what its base sections have when it is set up.
    """
    found = list(package.section_definitions)
    included = {id(section) for section in found}
    index = 0
    while index < len(found):
        for section in _depends_on(found[index]):
            if not _is_nomad(section) and id(section) not in included:
                included.add(id(section))
                found.append(section)
        index += 1

    ordered: list[Section] = []
    placed: set[int] = set()

    def place(section: Section) -> None:
        if id(section) in placed or _is_nomad(section):
            return
        placed.add(id(section))
        for base in section.base_sections:
            place(base)
        ordered.append(section)

    for section in found:
        place(section)
    return ordered


def _names(sections: list[Section], package) -> dict[int, str]:
    """
    The name of each section in the YAML schema.

    The package's own sections keep theirs. A section from elsewhere is renamed
    after its module where the name is taken (the plugin's PLDTarget extends
    nomad-material-processing's PLDTarget, which becomes 'pld_PLDTarget').
    """
    own = list(package.section_definitions)
    own_ids = {id(section) for section in own}
    names: dict[int, str] = {}
    taken: set[str] = set()
    for section in own + [s for s in sections if id(s) not in own_ids]:
        name = section.name
        if name in taken:
            module = section.qualified_name().rsplit('.', 2)[-2]
            name = f'{module}_{name}'
        if name in taken:
            raise ValueError(f'Two sections would be called {name} in the YAML schema.')
        taken.add(name)
        names[id(section)] = name
    return names


def _without_position(definition: dict) -> dict:
    return {
        key: value for key, value in definition.items() if key not in _POSITION_KEYS
    }


def _by_name(items: list[dict], definitions) -> dict[str, dict]:
    """`items` (serialized `definitions`) keyed by name, as YAML schemas write them."""
    result = {}
    for item, definition in zip(items, definitions, strict=True):
        if item['name'] != definition.name:
            raise ValueError(f'{definition} was serialized as {item["name"]}.')
        result[definition.name] = _without_position(item)
        del result[definition.name]['name']
    return result


class _Writer:
    def __init__(self, sections: list[Section], package):
        self.sections = sections
        self.names = _names(sections, package)

    def reference(self, section: Section) -> str:
        if id(section) in self.names:
            return self.names[id(section)]
        if _is_nomad(section):
            return section.qualified_name()
        raise ValueError(f'{section.qualified_name()} is not in the YAML schema.')

    def section(self, section: Section) -> dict:
        if section.inner_section_definitions:
            # Never needed so far; their references would need paths, not names.
            raise ValueError(
                f'{section.qualified_name()} has inner sections, which the YAML '
                f'schema does not support.'
            )
        result = _without_position(section.m_to_dict(with_meta=False))
        del result['name']
        if section.base_sections:
            result['base_sections'] = [
                self.reference(base) for base in section.base_sections
            ]
        if section.quantities:
            result['quantities'] = _by_name(result['quantities'], section.quantities)
            for quantity in section.quantities:
                if isinstance(quantity.type, Reference):
                    if not isinstance(quantity.type.target_section_def, Section):
                        raise ValueError(f'{quantity} refers to a quantity.')
                    result['quantities'][quantity.name]['type']['type_data'] = (
                        self.reference(quantity.type.target_section_def)
                    )
        if section.sub_sections:
            result['sub_sections'] = _by_name(
                result['sub_sections'], section.sub_sections
            )
            for sub_section in section.sub_sections:
                result['sub_sections'][sub_section.name]['sub_section'] = (
                    self.reference(sub_section.sub_section)
                )
        return result


def _outside_nomad(value, where: str = '') -> list[str]:
    """Every name in `value` of a definition that is not NOMAD's own."""
    if isinstance(value, dict):
        return [
            found
            for key, item in value.items()
            for found in _outside_nomad(item, f'{where}/{key}')
        ]
    if isinstance(value, list):
        return [
            found
            for index, item in enumerate(value)
            for found in _outside_nomad(item, f'{where}/{index}')
        ]
    if isinstance(value, str) and (
        re.match(r'#?/\w+_definitions/', value)
        or (_PYTHON_NAME.fullmatch(value) and value.split('.')[0] != 'nomad')
    ):
        return [f'{where}: {value}']
    return []


def _plugin_version() -> str:
    try:
        return version('differ_pld4e_schemas')
    except PackageNotFoundError:
        return 'unknown'


@dataclass(frozen=True)
class YamlSchema:
    """The YAML schema's text, and the name in it of each section it holds."""

    text: str
    names: dict[str, str]  # by the section's Python name

    def section_name(self, python_name: str) -> str | None:
        """
        The name in the schema of the section an entry names by `python_name`
        (its `m_def`), or None if the schema does not hold it.

        Entries name a section by any module that has it, for example
        'differ_pld4e_schemas.pld_deposition.SAPLDLogbook'. Only modules that
        are already imported are looked in: this imports nothing.
        """
        if python_name in self.names:
            return self.names[python_name]
        module, _, attribute = python_name.rpartition('.')
        definition = getattr(
            getattr(sys.modules.get(module), attribute, None), 'm_def', None
        )
        if not isinstance(definition, Section):
            return None
        return self.names.get(definition.qualified_name())


def yaml_schema(package, description: str) -> YamlSchema:
    """`package` and the sections it builds on outside NOMAD, as a YAML schema."""
    sections = _sections(package)
    writer = _Writer(sections, package)
    definitions = {
        'name': PACKAGE_NAME,
        'description': description,
        'sections': {
            writer.names[id(section)]: writer.section(section) for section in sections
        },
    }
    outside = _outside_nomad(definitions, 'definitions')
    if outside:
        raise ValueError(
            'The YAML schema still names definitions outside NOMAD:\n'
            + '\n'.join(outside)
        )
    text = yaml.safe_dump(
        {'definitions': definitions}, sort_keys=False, allow_unicode=True, width=88
    )
    names = {
        section.qualified_name(): writer.names[id(section)] for section in sections
    }
    return YamlSchema(text=text, names=names)


@cache
def plugin_yaml_schema() -> YamlSchema:
    """This plugin's schemas as a YAML schema."""
    from differ_pld4e_schemas.schema_packages.schema_package import m_package

    plugin_version = _plugin_version()
    description = (
        f'The schemas of the differ_pld4e_schemas NOMAD plugin {plugin_version} '
        f'(PLD4Energy lab, DIFFER), written as a YAML schema so that NOMAD can '
        f'read these entries without the plugin. It includes the sections of '
        f'nomad-material-processing that they build on. It describes the data '
        f"only: the plugin's code, which fills in some values and makes the "
        f'sample entries, does not run here.'
    )
    schema = yaml_schema(m_package, description)
    header = (
        f'# Written by differ_pld4e_schemas {plugin_version} when this upload was\n'
        f'# exported for publication. Entries refer to its sections as\n'
        f"# '../upload/raw/{SCHEMA_PATH}#<section>'.\n"
    )
    return YamlSchema(text=header + schema.text, names=schema.names)
