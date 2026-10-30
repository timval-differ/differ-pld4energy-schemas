"""
Mapping form values to archive quantities and back.

Values are entered in lab units (mbar, mJ, °C, ...) and stored in the units of
the schema quantities (SI), using the `unit` of each form field.
"""

from __future__ import annotations

import re

from nomad.units import ureg

from .values import is_empty, to_number, visible_fields

# Kinds whose value the converter of each dashboard handles itself.
SKIPPED_KINDS = ('computed', 'reference', 'sample_choice')


def file_name_for(text: str) -> str:
    return re.sub(r'[^\w.-]', '_', text) + '.archive.json'


def mainfile_reference(file_name: str) -> str:
    return f'../upload/archive/mainfile/{file_name}#data'


def is_mainfile_reference(reference) -> bool:
    """Whether a reference points to a file in the same upload by its name."""
    return isinstance(reference, str) and reference.startswith(
        '../upload/archive/mainfile/'
    )


def normalize_reference(reference):
    """Write references to entry data in one form, so they can be compared."""
    if not isinstance(reference, str):
        return reference
    return re.sub(r'#data$', '#/data', reference)


def sub_section_class(section_cls, path: str):
    m_def = section_cls.m_def
    for sub_section in path.split('.'):
        m_def = m_def.all_sub_sections[sub_section].sub_section
    return m_def.section_cls


def quantity_of(section_cls, path: str):
    *sub_sections, name = path.split('.')
    m_def = section_cls.m_def
    if sub_sections:
        m_def = sub_section_class(section_cls, '.'.join(sub_sections)).m_def
    return m_def.all_quantities[name]


def set_path(target: dict, path: str, value) -> None:
    *parents, name = path.split('.')
    for parent in parents:
        target = target.setdefault(parent, {})
    target[name] = value


def get_path(source: dict, path: str):
    for part in path.split('.'):
        if not isinstance(source, dict):
            return None
        source = source.get(part)
    return source


def to_archive_value(value, field: dict, quantity):
    kind = field['kind']
    if kind == 'bool':
        return bool(value)
    if kind in ('number', 'integer'):
        number = to_number(value)
        if field.get('unit') and quantity.unit is not None:
            number = ureg.Quantity(number, field['unit']).to(quantity.unit).magnitude
        return int(round(number)) if kind == 'integer' else number
    if kind == 'target_choice':
        return value
    return str(value)


def to_form_value(value, field: dict, quantity):
    kind = field['kind']
    if kind in ('number', 'integer') and value is not None:
        if field.get('unit') and quantity.unit is not None:
            value = ureg.Quantity(value, quantity.unit).to(field['unit']).magnitude
        value = int(round(value)) if kind == 'integer' else float(f'{value:.12g}')
    if kind == 'target_choice':
        return normalize_reference(value)
    return value


def _row_values(row: dict, columns: list, row_cls) -> dict:
    values = {}
    for column in columns:
        value = row.get(column['key'])
        if is_empty(value):
            continue
        quantity = quantity_of(row_cls, column['archive'])
        values[column['archive']] = to_archive_value(value, column, quantity)
    return values


def fill(target: dict, section_cls, fields, local, root) -> None:
    """Write the visible, filled-in fields of `local` into the archive `target`."""
    for field in visible_fields(fields, local, root):
        if field['archive'] is None or field['kind'] in SKIPPED_KINDS:
            continue
        if 'gas' in field:
            continue
        value = local.get(field['key'])
        if field['kind'] == 'rows':
            row_cls = sub_section_class(section_cls, field['archive'])
            rows = [_row_values(row, field['columns'], row_cls) for row in value or []]
            rows = [row for row in rows if row]
            if rows:
                set_path(target, field['archive'], rows)
            continue
        if is_empty(value) and field['kind'] != 'bool':
            continue
        quantity = quantity_of(section_cls, field['archive'])
        set_path(target, field['archive'], to_archive_value(value, field, quantity))


def read(source: dict, section_cls, fields) -> dict:
    """Form values of `fields` from the archive section `source`."""
    form = {}
    for field in fields:
        if field['archive'] is None or field['kind'] in SKIPPED_KINDS:
            continue
        if 'gas' in field:
            continue
        value = get_path(source, field['archive'])
        if value is None:
            continue
        if field['kind'] == 'rows':
            row_cls = sub_section_class(section_cls, field['archive'])
            form[field['key']] = [
                {
                    column['key']: to_form_value(
                        row[column['archive']],
                        column,
                        quantity_of(row_cls, column['archive']),
                    )
                    for column in field['columns']
                    if row.get(column['archive']) is not None
                }
                for row in value
            ]
            continue
        quantity = quantity_of(section_cls, field['archive'])
        form[field['key']] = to_form_value(value, field, quantity)
    return form
