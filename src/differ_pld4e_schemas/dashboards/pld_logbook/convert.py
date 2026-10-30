"""
Conversion between the PLD logbook form data and NOMAD archive files.

Values are entered in lab units (mbar, mJ, °C, ...) and stored in the units of
the schema quantities (SI), using the `unit` of each form field.
"""

from __future__ import annotations

import re
import uuid

from differ_pld4e_schemas import pld_deposition
from differ_pld4e_schemas.gas import BACKGROUND_GAS, BackgroundGas
from differ_pld4e_schemas.in_situ import InSituTechniques
from differ_pld4e_schemas.laser import LaserCalibration

from ..common.archive import (
    SKIPPED_KINDS,
    file_name_for,
    fill,
    normalize_reference,
    quantity_of,
    read,
    to_archive_value,
    to_form_value,
)
from ..common.samples import samples_to_archive, samples_to_form
from ..common.values import is_empty, to_number, visible_fields
from .rules import section_requirement
from .spec import GASES, LOGBOOK_SECTIONS

__all__ = [
    'SKIPPED_KINDS',
    'archive_to_form',
    'draft_path',
    'form_to_files',
    'recipe_to_form',
    'run_file_stem',
]

DRAFT_DIR = 'pld_drafts'
DRAFT_SUFFIX = '.draft.json'


def run_file_stem(data: dict) -> str:
    """`{system}_{date}_{hhmm}[_{name}]`, the start of the run's file names."""
    run = data.get('run') or {}
    stem = f'{run["system"]}_{run["date"]}_{run["time"].replace(":", "")}'
    if run.get('name'):
        stem += f'_{run["name"]}'
    return re.sub(r'[^\w.-]', '_', stem)


def draft_path(data: dict) -> str:
    return f'{DRAFT_DIR}/{run_file_stem(data)}{DRAFT_SUFFIX}'


def _sections(spec: dict) -> dict:
    return {section['key']: section for section in spec['sections']}


def _run_datetime(run: dict) -> str:
    offset = run.get('utc_offset')
    if not isinstance(offset, str) or not re.fullmatch(r'[+-]\d{2}:\d{2}', offset):
        offset = '+00:00'
    return f'{run["date"]}T{run["time"]}:00{offset}'


def _gases(fields, item, root) -> list:
    if item.get('atmosphere', BACKGROUND_GAS) != BACKGROUND_GAS:
        return []
    visible = visible_fields(fields, item, root)
    shown = {f['key'] for f in visible}
    gases = []
    for gas in GASES:
        if f'gas_{gas}' not in shown or not item.get(f'gas_{gas}'):
            continue
        entry = {'gas': gas}
        for field in visible:
            if field.get('gas') != gas or field['archive'] is None:
                continue
            value = item.get(field['key'])
            if is_empty(value):
                continue
            quantity = quantity_of(BackgroundGas, field['archive'])
            entry[field['archive']] = to_archive_value(value, field, quantity)
        gases.append(entry)
    return gases


def _read_gases(fields, gases) -> dict:
    form = {}
    for entry in gases or []:
        gas = entry.get('gas')
        if gas not in GASES:
            continue
        form[f'gas_{gas}'] = True
        for field in fields:
            if field.get('gas') != gas or field['archive'] is None:
                continue
            if entry.get(field['archive']) is not None:
                quantity = quantity_of(BackgroundGas, field['archive'])
                form[field['key']] = to_form_value(
                    entry[field['archive']], field, quantity
                )
    return form


def _step_class(variant: dict, system: str):
    return getattr(pld_deposition, variant['sections'][system])


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


def _step_samples(item: dict, system: str, references: dict) -> list:
    """SA-PLD deposits on all samples in the chamber, LA-PLD on the chosen one."""
    if system == 'SA-PLD':
        return list(references.values())
    chosen = item.get('sample')
    return [references.get(chosen, chosen)] if chosen else []


def _steps_to_archive(data: dict, sections: dict, system: str, references: dict):
    steps = []
    variants = sections['steps']['variants']
    for item in data.get('steps') or []:
        variant = variants[item['type']]
        step_cls = _step_class(variant, system)
        step = {'m_def': step_cls.m_def.qualified_name()}
        fill(step, step_cls, variant['fields'], item, data)
        if 'samples' in step_cls.m_def.all_quantities:
            samples = _step_samples(item, system, references)
            if samples:
                step['samples'] = samples
        step['background_gases'] = _gases(variant['fields'], item, data)
        steps.append(step)
    return steps


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


def _targets_to_archive(data: dict) -> list:
    return [
        {
            'target_number': int(to_number(item['target_number'])),
            'target': item['target'],
        }
        for item in data.get('targets') or []
        if item.get('target') and to_number(item.get('target_number')) is not None
    ]


def form_to_files(data: dict, spec: dict, logbook_file: str | None = None) -> dict:
    """
    The archive files for a complete (validated) form: one Sample file per new
    or external sample, then the logbook. References between them use file
    names, so everything can be written in one go.
    """
    sections = _sections(spec)
    run = data.get('run') or {}
    system = run['system']
    logbook_cls = LOGBOOK_SECTIONS[system]
    start = _run_datetime(run)

    logbook = {'m_def': logbook_cls.m_def.qualified_name()}
    fill(logbook, logbook_cls, sections['run']['fields'], run, data)
    fill(
        logbook,
        logbook_cls,
        sections['chamber']['fields'],
        data.get('chamber') or {},
        data,
    )
    logbook['datetime'] = start
    # The schema only has it as a default, which NOMAD does not show as a value.
    logbook['pvd_system'] = system
    logbook['samples'], files, references = samples_to_archive(
        data, sections['samples']['fields'], system, start
    )
    if section_requirement(sections['targets'], spec, data) != 'none':
        targets = _targets_to_archive(data)
        if targets:
            logbook['targets'] = targets
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
    logbook['steps'] = _steps_to_archive(data, sections, system, references)
    in_situ = _in_situ_to_archive(data, sections)
    if in_situ:
        logbook['in_situ_techniques'] = in_situ
    if data.get('recipe'):
        logbook['load_recipe'] = {'recipe': data['recipe']}

    # Only an opened logbook (with its file name given) may be overwritten.
    overwrite = logbook_file is not None
    if logbook_file is None:
        logbook_file = file_name_for(run_file_stem(data))
    files.append(
        {
            'file_name': logbook_file,
            'kind': 'logbook',
            'overwrite': overwrite,
            'archive': {'data': logbook},
        }
    )
    return {'files': files, 'logbook_file': logbook_file}


def _system_of(data: dict) -> str | None:
    m_def = data.get('m_def') or ''
    for system, section in LOGBOOK_SECTIONS.items():
        if m_def == section.m_def.qualified_name() or m_def.endswith(
            f'.{section.__name__}'
        ):
            return system
    return None


def _variant_of(variants: dict, m_def: str, system: str):
    for key, variant in variants.items():
        if (m_def or '').endswith(f'.{variant["sections"][system]}'):
            return key
    return None


def _uid() -> str:
    return uuid.uuid4().hex[:12]


def _steps_to_form(data, sections, system, samples, by_reference) -> list:
    """Form steps; samples used by steps but not in the logbook are added."""
    steps = []
    variants = sections['steps']['variants']
    for item in data.get('steps') or []:
        variant_key = _variant_of(variants, item.get('m_def'), system)
        if variant_key is None:
            continue
        variant = variants[variant_key]
        form_item = read(item, _step_class(variant, system), variant['fields'])
        form_item.update(_read_gases(variant['fields'], item.get('background_gases')))
        form_item.update(uid=_uid(), type=variant_key)
        step_samples = item.get('samples') or []
        if system != 'SA-PLD' and step_samples:
            reference = normalize_reference(step_samples[0])
            if reference not in by_reference:
                samples.append(
                    {'uid': _uid(), 'origin': 'Existing sample', 'sample': reference}
                )
                by_reference[reference] = reference
            form_item['sample'] = by_reference[reference]
        steps.append(form_item)
    return steps


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


def _run_to_form(data: dict, run_fields: list, system: str) -> dict:
    run = read(data, LOGBOOK_SECTIONS[system], run_fields)
    run['system'] = system
    start = str(data.get('datetime') or '')
    match = re.match(r'(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})', start)
    if match:
        run['date'], run['time'] = match.groups()
        # The browser shows the start in local time.
        run['start'] = start
    return run


def archive_to_form(data: dict, spec: dict) -> dict:
    """
    Form data from the `data` section of a logbook archive, e.g. to edit a saved
    logbook or to take the steps of a recipe.
    """
    system = _system_of(data)
    if system is None:
        raise ValueError('This entry is not an SA-PLD or LA-PLD logbook.')
    sections = _sections(spec)
    logbook_cls = LOGBOOK_SECTIONS[system]

    laser = read(
        data.get('laser_details') or {}, LaserCalibration, sections['laser']['fields']
    )
    laser['transmission_window_1_manual'] = bool(
        laser.get('transmission_window_1_manual')
    )
    targets = [
        {
            'uid': _uid(),
            'target': normalize_reference(item.get('target')),
            'target_number': item.get('target_number'),
        }
        for item in data.get('targets') or []
    ]
    samples, by_reference = samples_to_form(data, sections['samples']['fields'], _uid)
    steps = _steps_to_form(data, sections, system, samples, by_reference)

    form = {
        'run': _run_to_form(data, sections['run']['fields'], system),
        'samples': samples,
        'chamber': read(data, logbook_cls, sections['chamber']['fields']),
        'laser': laser,
        'targets': targets,
        'steps': steps,
        'in_situ': _in_situ_to_form(data, sections),
    }
    recipe = (data.get('load_recipe') or {}).get('recipe')
    if recipe:
        form['recipe'] = recipe
    return form


def recipe_to_form(data: dict, spec: dict) -> dict:
    """The steps (and targets) of a recipe, without sample links."""
    form = archive_to_form(data, spec)
    for step in form['steps']:
        step.pop('sample', None)
    return {
        'system': form['run']['system'],
        'targets': form['targets'],
        'steps': form['steps'],
    }
