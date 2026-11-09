"""
The form definition (spec) is a contract between Python (spec.py, rules.py,
convert.py) and the page (static/*.js). Nothing types it, so a misspelt key or
an unknown kind is silently ignored by both. These tests check every field,
condition and section of both dashboards' definitions.
"""

import re
from pathlib import Path

import pytest

from differ_pld4e_schemas.dashboards.common import fields as fields_module
from differ_pld4e_schemas.dashboards.common.rules import LEVELS
from differ_pld4e_schemas.dashboards.common.samples import MADE_HERE
from differ_pld4e_schemas.dashboards.pld_logbook import rules as pld_rules
from differ_pld4e_schemas.dashboards.pld_logbook.spec import form_spec as pld_spec
from differ_pld4e_schemas.dashboards.sputter_logbook import rules as sputter_rules
from differ_pld4e_schemas.dashboards.sputter_logbook.spec import (
    form_spec as sputter_spec,
)
from differ_pld4e_schemas.sample import NEW_SAMPLE

STATIC = Path(fields_module.__file__).parent / 'static'
SECTION_KINDS = {'object', 'list', 'variant_list'}
SECTION_KEYS = {
    'key',
    'title',
    'kind',
    'fields',
    'variants',
    'intro',
    'item_label',
    'min_items',
    'count_control',
    'unique',
    'requirement',
}
VARIANT_KEYS = {'label', 'sections', 'fields', 'prefill_from', 'laser', 'target'}
COMPUTED_BY_ALL = {'sample_id', 'sample_name'}

DASHBOARDS = [
    pytest.param(pld_spec(), pld_rules.RULES, id='pld'),
    pytest.param(sputter_spec(), sputter_rules.RULES, id='sputter'),
]


def _all_fields(spec):
    """(where, field) of every field, rows columns included."""

    def walk(where, fields):
        for field in fields:
            yield f'{where}.{field.get("key")}', field
            if field.get('kind') == 'rows':
                yield from walk(f'{where}.{field.get("key")}', field.get('columns', []))

    for section in spec['sections']:
        if section['kind'] == 'variant_list':
            for name, variant in section['variants'].items():
                yield from walk(f'{section["key"]}[{name}]', variant['fields'])
        else:
            yield from walk(section['key'], section['fields'])


def _condition_problems(condition):  # noqa: PLR0911
    if condition is None:
        return []
    if not isinstance(condition, dict):
        return [f'not an object: {condition!r}']
    if set(condition) in ({'all'}, {'any'}):
        (parts,) = condition.values()
        if not isinstance(parts, list) or not parts:
            return [f'needs a list of conditions: {condition!r}']
        return [p for part in parts for p in _condition_problems(part)]
    tests = set(condition) - {'key'}
    if (
        'key' not in condition
        or len(tests) != 1
        or tests - {'equals', 'in', 'has_type'}
    ):
        return [f'needs a key and one of equals, in, has_type: {condition!r}']
    if tests & {'in', 'has_type'} and not isinstance(condition[tests.pop()], list):
        return [f'in/has_type needs a list: {condition!r}']
    return []


@pytest.mark.parametrize('spec, rules', DASHBOARDS)
def test_fields_have_known_kinds_and_keys(spec, rules):
    problems = []
    for where, field in _all_fields(spec):
        if field.get('kind') not in fields_module.KNOWN_KINDS:
            problems.append(f'{where}: unknown kind {field.get("kind")!r}')
        unknown = set(field) - fields_module.FIELD_KEYS
        if unknown:
            problems.append(f'{where}: unknown keys {sorted(unknown)}')
        if not field.get('key') or not field.get('label'):
            problems.append(f'{where}: needs a key and a label')
    assert problems == []


@pytest.mark.parametrize('spec, rules', DASHBOARDS)
def test_conditions_are_well_formed(spec, rules):
    problems = [
        f'{where} {name}: {problem}'
        for where, field in _all_fields(spec)
        for name in ('visible_if', 'required_if')
        for problem in _condition_problems(field.get(name))
    ]
    assert problems == []


@pytest.mark.parametrize('spec, rules', DASHBOARDS)
def test_field_details_fit_their_kind(spec, rules):
    problems = []
    for where, field in _all_fields(spec):
        kind = field['kind']
        if kind == 'select' and not (field.get('options') or field.get('options_by')):
            problems.append(f'{where}: a select needs options')
        if 'options_by' in field:
            by = field['options_by']
            # empty_text: what the page shows while there are no options yet.
            if not {'key', 'map'} <= set(by) <= {'key', 'map', 'empty_text'} or not all(
                isinstance(v, list) for v in by['map'].values()
            ):
                problems.append(f'{where}: options_by needs a key and a map of lists')
        if kind == 'rows' and not field.get('columns'):
            problems.append(f'{where}: rows need columns')
        if kind == 'computed' and not field.get('compute'):
            problems.append(f'{where}: a computed field needs `compute`')
        if (
            kind == 'reference'
            and field.get('reference') not in spec['reference_sections']
        ):
            problems.append(f'{where}: unknown reference {field.get("reference")!r}')
        if {'min', 'max'} & set(field) and kind not in ('number', 'integer'):
            problems.append(f'{where}: min/max on a {kind}')
    assert problems == []


@pytest.mark.parametrize('spec, rules', DASHBOARDS)
def test_computed_values_are_known(spec, rules):
    names = {f['compute'] for _, f in _all_fields(spec) if f['kind'] == 'computed'}
    assert names <= COMPUTED_BY_ALL | set(rules.extra_computed)
    # The page computes them too (static/rules.js, COMPUTED).
    script = (STATIC / 'rules.js').read_text(encoding='utf-8')
    block = re.search(r'const COMPUTED = \{(.*?)\n  \};', script, re.S).group(1)
    in_script = set(re.findall(r'^    (\w+)[(:]', block, re.M))
    assert names <= in_script


@pytest.mark.parametrize('spec, rules', DASHBOARDS)
def test_sections_are_well_formed(spec, rules):
    problems = []
    variants = {}
    for section in spec['sections']:
        key = section.get('key')
        if section.get('kind') not in SECTION_KINDS:
            problems.append(f'{key}: unknown kind {section.get("kind")!r}')
        if set(section) - SECTION_KEYS:
            problems.append(
                f'{key}: unknown keys {sorted(set(section) - SECTION_KEYS)}'
            )
        field_keys = {f['key'] for f in section.get('fields') or []}
        for unique in section.get('unique') or []:
            if unique not in field_keys:
                problems.append(f'{key}: unique key {unique!r} is not a field')
        if section.get('kind') == 'variant_list':
            variants = section['variants']
            for name, variant in variants.items():
                if set(variant) - VARIANT_KEYS:
                    problems.append(f'{key}[{name}]: unknown keys')
                if set(variant['sections']) != set(spec['systems']):
                    problems.append(f'{key}[{name}]: needs a section for every system')
    for section in spec['sections']:
        aspect = (section.get('requirement') or {}).get('from_steps')
        if aspect is None:
            continue
        levels = {variant.get(aspect) for variant in variants.values()}
        if not levels - {None} or not levels - {None} <= set(LEVELS):
            problems.append(f'{section["key"]}: steps give no levels of {aspect!r}')
    assert problems == []


def test_page_constants_match_python():
    script = (STATIC / 'constants.js').read_text(encoding='utf-8')

    def constant(name):
        text = re.search(rf'export const {name} = (.*?);', script).group(1)
        return re.findall(r"'([^']*)'", text)

    assert constant('NEW_SAMPLE') == [NEW_SAMPLE]
    assert constant('MADE_HERE') == list(MADE_HERE)
    assert constant('LEVELS') == list(LEVELS)


def test_misspelt_keys_are_found():
    """The checks above do catch mistakes."""
    spec = {
        'sections': [
            {
                'key': 'run',
                'kind': 'object',
                'fields': [
                    {'key': 'a', 'label': 'A', 'kind': 'text', 'visble_if': {}},
                    {'key': 'b', 'label': 'B', 'kind': 'txt'},
                ],
            }
        ]
    }
    found = [
        where
        for where, field in _all_fields(spec)
        if set(field) - fields_module.FIELD_KEYS
        or field['kind'] not in fields_module.KNOWN_KINDS
    ]
    assert found == ['run.a', 'run.b']
    assert _condition_problems({'key': 'x', 'equal': 1})
    assert _condition_problems({'all': {'key': 'x', 'equals': 1}})
    assert _condition_problems({'key': 'x', 'in': 'abc'})


# Units: the dashboard converts each number from the field's unit to the unit
# of the schema quantity it is written to. A field without a unit written to a
# quantity with one (or the other way round) is stored unconverted, so the
# value would be silently wrong by the factor between the units.


def _unit_classes():
    from differ_pld4e_schemas import pld_deposition, sps_deposition
    from differ_pld4e_schemas.gas import BackgroundGas
    from differ_pld4e_schemas.in_situ import InSituTechniques
    from differ_pld4e_schemas.laser import LaserCalibration
    from differ_pld4e_schemas.sample import SampleInRun

    pld_logbooks = [pld_deposition.SAPLDLogbook, pld_deposition.LAPLDLogbook]
    common = {'samples': [SampleInRun], 'gas': [BackgroundGas]}
    return [
        pytest.param(
            pld_spec(),
            pld_deposition,
            {
                **common,
                'run': pld_logbooks,
                'chamber': pld_logbooks,
                'targets': [pld_deposition.SelectedTarget],
                'laser': [LaserCalibration],
                'in_situ': [InSituTechniques],
                'logfiles': pld_logbooks,
            },
            id='pld',
        ),
        pytest.param(
            sputter_spec(),
            sps_deposition,
            {
                **common,
                'run': [sps_deposition.SPSLogbook],
                'chamber': [sps_deposition.SPSLogbook],
                'targets': [sps_deposition.SelectedSputterTarget],
                'comments': [sps_deposition.SPSLogbook],
            },
            id='sputter',
        ),
    ]


def _number_fields(spec, module, classes):
    """(where, field, candidate classes) of every number written to the archive."""
    from differ_pld4e_schemas.dashboards.common.archive import sub_section_class

    def walk(where, fields, candidates):
        for field in fields:
            if field.get('archive') is None:
                continue
            here = f'{where}.{field["key"]}'
            if field['kind'] == 'rows':
                rows = [sub_section_class(c, field['archive']) for c in candidates]
                yield from walk(here, field['columns'], rows)
            elif field['kind'] in ('number', 'integer'):
                yield here, field, classes['gas'] if 'gas' in field else candidates

    for section in spec['sections']:
        key = section['key']
        if section['kind'] == 'variant_list':
            for name, variant in section['variants'].items():
                candidates = [getattr(module, c) for c in variant['sections'].values()]
                yield from walk(f'{key}[{name}]', variant['fields'], candidates)
        else:
            yield from walk(key, section['fields'], classes[key])


@pytest.mark.parametrize('spec, module, classes', _unit_classes())
def test_field_units_match_schema_units(spec, module, classes):
    from nomad.units import ureg

    from differ_pld4e_schemas.dashboards.common.archive import quantity_of

    problems, checked = [], 0
    for where, field, candidates in _number_fields(spec, module, classes):
        quantities = []
        for section_cls in candidates:
            try:
                quantities.append(
                    (section_cls, quantity_of(section_cls, field['archive']))
                )
            except KeyError:
                pass
        if not quantities:
            problems.append(f'{where}: {field["archive"]} is in none of {candidates}')
        for section_cls, quantity in quantities:
            checked += 1
            unit = field.get('unit')
            name = f'{where} -> {section_cls.__name__}.{field["archive"]}'
            if bool(unit) != (quantity.unit is not None):
                problems.append(
                    f'{name}: field unit {unit!r}, quantity {quantity.unit}'
                )
            elif unit and not ureg.Unit(unit).is_compatible_with(quantity.unit):
                problems.append(
                    f'{name}: {unit} cannot be converted to {quantity.unit}'
                )
    assert problems == []
    assert checked > 0


def test_target_entry_fields_are_target_quantities():
    from differ_pld4e_schemas.target import SputterTarget

    problems = []
    for field in sputter_spec()['client']['target_entry']['fields']:
        quantity = SputterTarget.m_def.all_quantities.get(field['key'])
        if quantity is None:
            problems.append(f'{field["key"]} is not a SputterTarget quantity')
        elif 'scale' in field and str(quantity.unit) != 'meter':
            problems.append(
                f'{field["key"]}: scale to metres, but unit {quantity.unit}'
            )
    assert problems == []
