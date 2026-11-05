"""
Conversion between the PLD logbook form data and NOMAD archive files. The
parts every logbook has are in `dashboards.common.convert`; this adds the
laser details, the in-situ measurements and the system logfiles.

An in-situ measurement refers to its process steps by their position in the
logbook, e.g. `#/data/steps/2`; in the form it names them by their uid.
"""

from __future__ import annotations

import re

from differ_pld4e_schemas import pld_deposition
from differ_pld4e_schemas.in_situ import InSituTechniques
from differ_pld4e_schemas.laser import LaserCalibration

from ..common.archive import (
    SKIPPED_KINDS,
    fill,
    normalize_reference,
    quantity_of,
    read,
    to_form_value,
)
from ..common.convert import LogbookConverter, new_uid, run_file_stem, sections_of
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
    # A technique is ticked with a toggle that is not stored itself.
    return [
        f['key'] for f in in_situ_fields if f['kind'] == 'bool' and f['archive'] is None
    ]


STEP_REFERENCE = re.compile(r'/data/steps/(\d+)$')


def _measurement_to_archive(item: dict, data: dict, fields: list, references):
    measurement = {}
    if item.get('sample'):
        measurement['sample'] = references.get(item['sample'], item['sample'])
    positions = {step.get('uid'): i for i, step in enumerate(data.get('steps') or [])}
    steps = [
        f'#/data/steps/{positions[uid]}'
        for uid in item.get('steps') or []
        if uid in positions
    ]
    if steps:
        measurement['process_steps'] = steps
    for technique in _techniques(fields):
        if not item.get(technique):
            continue
        entry = {}
        fill(
            entry,
            _technique_class(technique),
            _technique_fields(fields, technique),
            item,
            data,
        )
        # Written even without files: the technique then awaits its data.
        measurement[technique] = [entry]
    return measurement


def _techniques_to_form(entry: dict, fields: list) -> dict:
    """The techniques of one measurement section."""
    item = {}
    for technique in _techniques(fields):
        if not entry.get(technique):
            continue
        item[technique] = True
        technique_cls = _technique_class(technique)
        values = entry[technique][0]
        for field in _technique_fields(fields, technique):
            value = values.get(field['archive'])
            if value is None and field['kind'] == 'files':
                # One file, saved before a technique took several (`..._file`).
                value = values.get(field['archive'][:-1])
            if value is not None:
                item[field['form_key']] = to_form_value(
                    value, field, quantity_of(technique_cls, field['archive'])
                )
    return item


def _measurement_to_form(entry: dict, fields: list, form: dict, by_reference):
    item = {'uid': new_uid(), **_techniques_to_form(entry, fields)}
    sample = normalize_reference(entry.get('sample'))
    if sample:
        item['sample'] = by_reference.get(sample, sample)
    uids = {step['archive_index']: step['uid'] for step in form['steps']}
    steps = []
    for reference in entry.get('process_steps') or []:
        match = STEP_REFERENCE.search(str(reference))
        if match and int(match.group(1)) in uids:
            steps.append(uids[int(match.group(1))])
    item['steps'] = steps
    return item


def _in_situ_to_archive(data: dict, sections: dict, references: dict) -> list:
    fields = sections['in_situ']['fields']
    return [
        _measurement_to_archive(item, data, fields, references)
        for item in data.get('in_situ') or []
    ]


def _in_situ_to_form(data: dict, sections: dict, form: dict, by_reference) -> list:
    fields = sections['in_situ']['fields']
    measurements = [
        _measurement_to_form(entry, fields, form, by_reference)
        for entry in data.get('in_situ_measurements') or []
    ]
    # A logbook saved before measurements had a sample and steps: its techniques
    # become one measurement, whose sample and steps still have to be chosen.
    old = _techniques_to_form(data.get('in_situ_techniques') or {}, fields)
    if old:
        measurements.append({'uid': new_uid(), 'steps': [], **old})
    return measurements


class PLDConverter(LogbookConverter):
    def extra_to_archive(
        self, data: dict, spec: dict, logbook: dict, references: dict
    ) -> None:
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
        in_situ = _in_situ_to_archive(data, sections, references)
        if in_situ:
            logbook['in_situ_measurements'] = in_situ
        fill(
            logbook,
            self.logbook_sections[data['run']['system']],
            sections['logfiles']['fields'],
            data.get('logfiles') or {},
            data,
        )

    def extra_to_form(
        self, data: dict, spec: dict, form: dict, by_reference: dict
    ) -> None:
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
        form['in_situ'] = _in_situ_to_form(data, sections, form, by_reference)
        form['logfiles'] = read(
            data,
            self.logbook_sections[form['run']['system']],
            sections['logfiles']['fields'],
        )


CONVERTER = PLDConverter(LOGBOOK_SECTIONS, pld_deposition, RULES, DRAFT_DIR)
archive_to_form = CONVERTER.archive_to_form
draft_path = CONVERTER.draft_path
form_to_files = CONVERTER.form_to_files
recipe_to_form = CONVERTER.recipe_to_form
