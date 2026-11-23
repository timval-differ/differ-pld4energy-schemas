"""
Schemas of plugins as YAML schemas, for NOMADs that do not run those plugins.

The central NOMAD has neither this plugin nor the other plugins of the Oasis
(nomad-material-processing, laeds_tools, ...). An exported upload brings the
schemas of its entries along as YAML schema files
(https://docs.nomad-lab.eu/howto/schemas/define.html), one per plugin:
'schema/<plugin>.archive.yaml'. Its entries name their sections in those files
instead of by Python name.

The files hold every section of the schema packages the upload uses and every
section those build on outside NOMAD itself, so together they rely only on
NOMAD's own sections. A section in another file is named by its file:
'../upload/raw/schema/<plugin>.archive.yaml#<section>'. They describe the data;
the plugins' Python code (normalizers, dashboards) does not come along.

References are written from the definitions, not by rewriting what
`m_to_dict` writes: NOMAD 2.0 writes a reference quantity's target as a path in
the target's own package, which inside another package names the wrong section.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from functools import cache
from importlib.metadata import PackageNotFoundError, packages_distributions, version

import yaml
from nomad.metainfo import Reference, Section

__all__ = [
    'SCHEMA_DIRECTORY',
    'YamlSchemas',
    'schema_path',
    'section_of',
    'yaml_schemas',
]

# Where the schemas are in an exported upload.
SCHEMA_DIRECTORY = 'schema'

# A Python name of a definition, as NOMAD writes it ('a.b.Name').
_PYTHON_NAME = re.compile(r'[A-Za-z_]\w*(?:\.\w+)+')

# What `m_to_dict` writes about where a definition sits in its package; the
# YAML form says it by where the definition is written.
_POSITION_KEYS = ('m_def', 'm_parent_index', 'm_parent_sub_section')


def schema_path(plugin: str) -> str:
    """The YAML schema file of `plugin` (its top-level Python package)."""
    return f'{SCHEMA_DIRECTORY}/{plugin}.archive.yaml'


def _plugin(section: Section) -> str:
    return section.qualified_name().split('.')[0]


def _is_nomad(section: Section) -> bool:
    return _plugin(section) == 'nomad'


def section_of(python_name: str) -> Section | None:
    """
    The section an entry names by `python_name` (its `m_def`), if any.

    Entries name a section by any module that has it, for example
    'differ_pld4e_schemas.pld_deposition.SAPLDLogbook'. Only modules that are
    already imported are looked in: this imports nothing named in an upload.
    """
    module_name, _, attribute = python_name.rpartition('.')
    module = sys.modules.get(module_name)
    # From the module's namespace: a module's __getattr__ may import.
    found = vars(module).get(attribute) if module is not None else None
    definition = getattr(found, 'm_def', None) if isinstance(found, type) else None
    return definition if isinstance(definition, Section) else None


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


def _sections(packages: list) -> list[Section]:
    """
    The sections of `packages` and those they build on outside NOMAD, each after
    its base sections.

    NOMAD sets up the sections of a YAML schema in the order they are written,
    and a section inherits what its base sections have when it is set up.
    """
    found = [section for package in packages for section in package.section_definitions]
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


def _names(sections: list[Section], packages: list) -> dict[int, str]:
    """
    The name of each section in the file of its plugin.

    The sections of `packages` keep theirs. A section that builds on is renamed
    after its module where the name is taken in its file.
    """
    own = [section for package in packages for section in package.section_definitions]
    own_ids = {id(section) for section in own}
    names: dict[int, str] = {}
    taken: set[tuple[str, str]] = set()
    for section in own + [s for s in sections if id(s) not in own_ids]:
        plugin, name = _plugin(section), section.name
        if (plugin, name) in taken:
            module = section.qualified_name().rsplit('.', 2)[-2]
            name = f'{module}_{name}'
        if (plugin, name) in taken:
            raise ValueError(
                f'Two sections would be called {name} in the YAML schema of {plugin}.'
            )
        taken.add((plugin, name))
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
    def __init__(self, sections: list[Section], packages: list):
        self.names = _names(sections, packages)

    def reference(self, section: Section, plugin: str) -> str:
        """`section` as the file of `plugin` refers to it."""
        if _is_nomad(section):
            return section.qualified_name()
        if id(section) not in self.names:
            raise ValueError(f'{section.qualified_name()} is not in a YAML schema.')
        name = self.names[id(section)]
        if _plugin(section) == plugin:
            return name
        return f'../upload/raw/{schema_path(_plugin(section))}#{name}'

    def section(self, section: Section) -> dict:
        if section.inner_section_definitions:
            # Never needed so far; their references would need paths, not names.
            raise ValueError(
                f'{section.qualified_name()} has inner sections, which the YAML '
                f'schema does not support.'
            )
        plugin = _plugin(section)
        result = _without_position(section.m_to_dict(with_meta=False))
        del result['name']
        if section.base_sections:
            result['base_sections'] = [
                self.reference(base, plugin) for base in section.base_sections
            ]
        if section.quantities:
            result['quantities'] = _by_name(result['quantities'], section.quantities)
            for quantity in section.quantities:
                if isinstance(quantity.type, Reference):
                    if not isinstance(quantity.type.target_section_def, Section):
                        raise ValueError(f'{quantity} refers to a quantity.')
                    result['quantities'][quantity.name]['type']['type_data'] = (
                        self.reference(quantity.type.target_section_def, plugin)
                    )
        if section.sub_sections:
            result['sub_sections'] = _by_name(
                result['sub_sections'], section.sub_sections
            )
            for sub_section in section.sub_sections:
                result['sub_sections'][sub_section.name]['sub_section'] = (
                    self.reference(sub_section.sub_section, plugin)
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


@cache  # installed distributions do not change while NOMAD runs; listing is slow
def _distributions() -> dict[str, list[str]]:
    return packages_distributions()


def _distribution(plugin: str) -> str:
    """The installed distribution of `plugin` and its version, e.g. 'x 1.0'."""
    for name in _distributions().get(plugin, []):
        try:
            return f'{name} {version(name)}'
        except PackageNotFoundError:
            continue
    return plugin


def _description(plugin: str, own: bool) -> str:
    distribution = _distribution(plugin)
    if own:
        return (
            f'The schemas of the NOMAD plugin {distribution}, written as a YAML '
            f'schema so that NOMAD can read these entries without the plugin. It '
            f"describes the data only: the plugin's code does not run here."
        )
    return (
        f'The sections of {distribution} that the other schemas in this folder '
        f'build on, written as a YAML schema.'
    )


@dataclass(frozen=True)
class YamlSchemas:
    """The YAML schema files by path, and where each section is in them."""

    files: dict[str, str]
    locations: dict[str, tuple[str, str]]  # by Python name: (path, name)

    def reference(self, section: Section) -> str:
        """How an entry names `section`, a section of these schemas, as its `m_def`."""
        path, name = self.locations[section.qualified_name()]
        return f'../upload/raw/{path}#{name}'


def yaml_schemas(packages: list) -> YamlSchemas:
    """
    The schema `packages` and the sections they build on outside NOMAD, as one
    YAML schema file per plugin.
    """
    sections = _sections(packages)
    writer = _Writer(sections, packages)
    own_plugins = {
        _plugin(section)
        for package in packages
        for section in package.section_definitions
    }
    plugins = list(dict.fromkeys(_plugin(section) for section in sections))

    files = {}
    for plugin in plugins:
        definitions = {
            'name': f'{plugin}_yaml',
            'description': _description(plugin, plugin in own_plugins),
            'sections': {
                writer.names[id(section)]: writer.section(section)
                for section in sections
                if _plugin(section) == plugin
            },
        }
        outside = _outside_nomad(definitions, schema_path(plugin))
        if outside:
            raise ValueError(
                'The YAML schema still names definitions outside NOMAD:\n'
                + '\n'.join(outside)
            )
        header = (
            f'# Written when this upload was exported for publication from an\n'
            f'# Oasis with {_distribution(plugin)}. Entries refer to its sections\n'
            f"# as '../upload/raw/{schema_path(plugin)}#<section>'.\n"
        )
        files[schema_path(plugin)] = header + yaml.safe_dump(
            {'definitions': definitions}, sort_keys=False, allow_unicode=True, width=88
        )

    locations = {
        section.qualified_name(): (
            schema_path(_plugin(section)),
            writer.names[id(section)],
        )
        for section in sections
    }
    return YamlSchemas(files=files, locations=locations)
