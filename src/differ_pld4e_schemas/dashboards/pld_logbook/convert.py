"""
Conversion between the PLD logbook form data and NOMAD archive files. The
parts every logbook has are in `dashboards.common.convert`; this adds the
laser details and the in-situ techniques.
"""

from __future__ import annotations

from differ_pld4e_schemas import pld_deposition
from differ_pld4e_schemas.in_situ import InSituTechniques
from differ_pld4e_schemas.laser import LaserCalibration

from ..common.archive import SKIPPED_KINDS, fill, quantity_of, read, to_form_value
from ..common.convert import LogbookConverter, run_file_stem, sections_of
from ..common.rules import section_requirement
from .rules import RULES
from .spec import DRAFT_DIR, LOGBOOK_SECTIONS

__all__ = [
    'SKIPPED_KINDS',
    'archive_to_form',
    'draft_path',
    'form_to_files',
    'recipe_to_form',
    'run_file_stem',
]


def _technique_fields(in_situ_fields: list, technique: str) -> list:
    """The fields of one in-situ technique, with paths relative to its section."""
    return [
        dict(f, archive=f['archive'].split('.', 1)[1], form_key=f['key'])
        for f in in_situ_fields
        if f['archive'] and f['archive'].startswith(f'{technique}.')
    ]


def _technique_class(technique: str):
    return InSituTechniques.m_def.all_sub_sections[technique].sub_section.section_cls


def _techniques(in_situ_fields: list) -> list:
    return [f['key'] for f in in_situ_fields if f['archive'] is None]


def _in_situ_to_archive(data: dict, sections: dict) -> dict:
    in_situ = data.get('in_situ') or {}
    fields = sections['in_situ']['fields']
    result = {}
    for technique in _techniques(fields):
        if not in_situ.get(technique):
            continue
        entry = {}
        fill(
            entry,
            _technique_class(technique),
            _technique_fields(fields, technique),
            in_situ,
            data,
        )
        # Written even without files: the technique then awaits its data.
        result[technique] = [entry]
    return result


def _in_situ_to_form(data: dict, sections: dict) -> dict:
    in_situ = {}
    in_situ_data = data.get('in_situ_techniques') or {}
    fields = sections['in_situ']['fields']
    for technique in _techniques(fields):
        if not in_situ_data.get(technique):
            continue
        in_situ[technique] = True
        technique_cls = _technique_class(technique)
        entry = in_situ_data[technique][0]
        for field in _technique_fields(fields, technique):
            if entry.get(field['archive']) is not None:
                in_situ[field['form_key']] = to_form_value(
                    entry[field['archive']],
                    field,
                    quantity_of(technique_cls, field['archive']),
                )
    return in_situ


class PLDConverter(LogbookConverter):
    def extra_to_archive(self, data: dict, spec: dict, logbook: dict) -> None:
        sections = sections_of(spec)
        if section_requirement(sections['laser'], spec, data) != 'none':
            laser_details = {}
            fill(
                laser_details,
                LaserCalibration,
                sections['laser']['fields'],
                data.get('laser') or {},
                data,
            )
            if laser_details:
                logbook['laser_details'] = laser_details
        in_situ = _in_situ_to_archive(data, sections)
        if in_situ:
            logbook['in_situ_techniques'] = in_situ

    def extra_to_form(self, data: dict, spec: dict, form: dict) -> None:
        sections = sections_of(spec)
        laser = read(
            data.get('laser_details') or {},
            LaserCalibration,
            sections['laser']['fields'],
        )
        laser['transmission_window_1_manual'] = bool(
            laser.get('transmission_window_1_manual')
        )
        form['laser'] = laser
        form['in_situ'] = _in_situ_to_form(data, sections)


CONVERTER = PLDConverter(LOGBOOK_SECTIONS, pld_deposition, RULES, DRAFT_DIR)
archive_to_form = CONVERTER.archive_to_form
draft_path = CONVERTER.draft_path
form_to_files = CONVERTER.form_to_files
recipe_to_form = CONVERTER.recipe_to_form
