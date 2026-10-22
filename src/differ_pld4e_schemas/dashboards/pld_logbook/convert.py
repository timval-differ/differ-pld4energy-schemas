"""
Conversion between the PLD logbook form data and NOMAD archive files.

Values are entered in lab units (mbar, mJ, °C, ...) and stored in the units of
the schema quantities (SI), using the `unit` of each form field.
"""

from __future__ import annotations

import re
import uuid

from nomad.units import ureg

from differ_pld4e_schemas import pld_deposition
from differ_pld4e_schemas.gas import BackgroundGas
from differ_pld4e_schemas.in_situ import InSituTechniques
from differ_pld4e_schemas.laser import LaserCalibration
from differ_pld4e_schemas.pld_substrate import NewSubstrate, PLDSubstrate

from .rules import NEW_SUBSTRATE, compute, is_empty, to_number, visible_fields
from .spec import GASES, LOGBOOK_SECTIONS

SKIPPED_KINDS = ('computed', 'reference', 'substrate_choice')


def file_name_for(text: str) -> str:
    return re.sub(r'[^\w.-]', '_', text) + '.archive.json'


def mainfile_reference(file_name: str) -> str:
    return f'../upload/archive/mainfile/{file_name}#data'


def normalize_reference(reference):
    """Write references to entry data in one form, so they can be compared."""
    if not isinstance(reference, str):
        return reference
    return re.sub(r'#data$', '#/data', reference)


def _quantity(section_cls, path: str):
    m_def = section_cls.m_def
    *sub_sections, name = path.split('.')
    for sub_section in sub_sections:
        m_def = m_def.all_sub_sections[sub_section].sub_section
    return m_def.all_quantities[name]


def _set(target: dict, path: str, value) -> None:
    *parents, name = path.split('.')
    for parent in parents:
        target = target.setdefault(parent, {})
    target[name] = value


def _get(source: dict, path: str):
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


def _fill(target: dict, section_cls, fields, local, root) -> None:
    for field in visible_fields(fields, local, root):
        if field['archive'] is None or field['kind'] in SKIPPED_KINDS:
            continue
        if 'gas' in field:
            continue
        value = local.get(field['key'])
        if is_empty(value) and field['kind'] != 'bool':
            continue
        quantity = _quantity(section_cls, field['archive'])
        _set(target, field['archive'], to_archive_value(value, field, quantity))


def _read(source: dict, section_cls, fields) -> dict:
    form = {}
    for field in fields:
        if field['archive'] is None or field['kind'] in SKIPPED_KINDS:
            continue
        if 'gas' in field:
            continue
        value = _get(source, field['archive'])
        if value is None:
            continue
        quantity = _quantity(section_cls, field['archive'])
        form[field['key']] = to_form_value(value, field, quantity)
    return form


def _sections(spec: dict) -> dict:
    return {section['key']: section for section in spec['sections']}


def _datetime(date_text: str) -> str:
    return f'{date_text}T00:00:00+00:00'


def _gases(fields, item, root) -> list:
    gases = []
    for gas in GASES:
        if not item.get(f'gas_{gas}'):
            continue
        entry = {'gas': gas}
        for field in visible_fields(fields, item, root):
            if field.get('gas') != gas or field['archive'] is None:
                continue
            value = item.get(field['key'])
            if is_empty(value) and field['kind'] != 'bool':
                continue
            quantity = _quantity(BackgroundGas, field['archive'])
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
                quantity = _quantity(BackgroundGas, field['archive'])
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


def _substrate_file(item: dict, system: str, date_text: str, new_substrate: dict):
    file_name = file_name_for(new_substrate['sample_user_id'])
    return {
        'file_name': file_name,
        'kind': 'substrate',
        'uid': item.get('uid'),
        'reference': mainfile_reference(file_name),
        'overwrite': False,
        'archive': {
            'data': {
                'm_def': PLDSubstrate.m_def.qualified_name(),
                'name': item.get('sample_name'),
                'pvd_system': system,
                'datetime': _datetime(date_text),
                'run_number': item.get('run_number'),
                'sample_number': item.get('sample_number'),
                'size': item.get('size'),
                'substrate_material': item.get('substrate_material'),
                'description': item.get('comments'),
                'sample_user_id': new_substrate['sample_user_id'],
                'sample_uuid': new_substrate['sample_uuid'],
            }
        },
    }


def _substrates_to_archive(data: dict, sections: dict, system: str):
    """NewSubstrate sections, substrate files to create, and form choice -> ref."""
    new_substrates, files, references = [], [], {}
    for item in data.get('substrates') or []:
        if item.get('mode', NEW_SUBSTRATE) != NEW_SUBSTRATE:
            continue
        new_substrate = {
            'sample_user_id': compute('sample_user_id', item, data),
            'sample_uuid': item.get('sample_uuid') or str(uuid.uuid4()),
        }
        _fill(new_substrate, NewSubstrate, sections['substrates']['fields'], item, data)
        reference = item.get('ref')
        if not reference:
            file = _substrate_file(item, system, data['run']['date'], new_substrate)
            files.append(file)
            reference = file['reference']
        new_substrate['substrate'] = reference
        references[f'new:{item.get("uid")}'] = reference
        new_substrates.append(new_substrate)
    return new_substrates, files, references


def _steps_to_archive(data: dict, sections: dict, system: str, references: dict):
    steps = []
    variants = sections['steps']['variants']
    for item in data.get('steps') or []:
        variant = variants[item['type']]
        step_cls = _step_class(variant, system)
        step = {'m_def': step_cls.m_def.qualified_name()}
        _fill(step, step_cls, variant['fields'], item, data)
        if item.get('substrate'):
            step['substrate'] = references.get(item['substrate'], item['substrate'])
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
        _fill(
            entry,
            _technique_class(technique),
            _technique_fields(fields, technique),
            in_situ,
            data,
        )
        result[technique] = [entry]
    return result


def form_to_files(data: dict, spec: dict, logbook_file: str | None = None) -> dict:
    """
    The archive files for a complete (validated) form: one PLD Substrate file per
    new substrate, then the logbook. References between them use file names, so
    everything can be written in one go.
    """
    sections = _sections(spec)
    run = data.get('run') or {}
    system = run['system']
    logbook_cls = LOGBOOK_SECTIONS[system]

    logbook = {'m_def': logbook_cls.m_def.qualified_name()}
    _fill(logbook, logbook_cls, sections['run']['fields'], run, data)
    logbook['datetime'] = _datetime(run['date'])
    # The schema only has it as a default, which NOMAD does not show as a value.
    logbook['pvd_system'] = system
    laser_details = {}
    _fill(
        laser_details,
        LaserCalibration,
        sections['laser']['fields'],
        data.get('laser') or {},
        data,
    )
    logbook['laser_details'] = laser_details
    logbook['targets'] = [
        {
            'target_number': int(to_number(item['target_number'])),
            'target': item['target'],
        }
        for item in data.get('targets') or []
    ]
    logbook['substrates'], files, references = _substrates_to_archive(
        data, sections, system
    )
    logbook['steps'] = _steps_to_archive(data, sections, system, references)
    in_situ = _in_situ_to_archive(data, sections)
    if in_situ:
        logbook['in_situ_techniques'] = in_situ
    if data.get('recipe'):
        logbook['load_recipe'] = {'recipe': data['recipe']}

    # Only an opened logbook (with its file name given) may be overwritten.
    overwrite = logbook_file is not None
    if logbook_file is None:
        name = run.get('name') or 'logbook'
        logbook_file = file_name_for(f'{system}_{run["date"]}_{name}')
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


def _substrates_to_form(data: dict, sections: dict):
    substrates, by_reference = [], {}
    for item in data.get('substrates') or []:
        form_item = _read(item, NewSubstrate, sections['substrates']['fields'])
        form_item.update(
            uid=_uid(),
            mode=NEW_SUBSTRATE,
            sample_uuid=item.get('sample_uuid'),
            ref=item.get('substrate'),
        )
        substrates.append(form_item)
        if item.get('substrate'):
            by_reference[normalize_reference(item['substrate'])] = (
                f'new:{form_item["uid"]}'
            )
    return substrates, by_reference


def _steps_to_form(data, sections, system, substrates, by_reference) -> list:
    """Form steps; substrates used by steps but not in the logbook are added."""
    steps = []
    variants = sections['steps']['variants']
    for item in data.get('steps') or []:
        variant_key = _variant_of(variants, item.get('m_def'), system)
        if variant_key is None:
            continue
        variant = variants[variant_key]
        form_item = _read(item, _step_class(variant, system), variant['fields'])
        form_item.update(_read_gases(variant['fields'], item.get('background_gases')))
        form_item.update(uid=_uid(), type=variant_key)
        substrate = normalize_reference(item.get('substrate'))
        if substrate:
            if substrate not in by_reference:
                substrates.append(
                    {
                        'uid': _uid(),
                        'mode': 'Use existing substrate',
                        'substrate': substrate,
                    }
                )
                by_reference[substrate] = substrate
            form_item['substrate'] = by_reference[substrate]
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
                    _quantity(technique_cls, field['archive']),
                )
    return in_situ


def archive_to_form(data: dict, spec: dict) -> dict:
    """
    Form data from the `data` section of a logbook archive, e.g. to edit a saved
    logbook or to take the steps of a recipe.
    """
    system = _system_of(data)
    if system is None:
        raise ValueError('This entry is not an SA-PLD or LA-PLD logbook.')
    sections = _sections(spec)

    run = _read(data, LOGBOOK_SECTIONS[system], sections['run']['fields'])
    run['system'] = system
    if data.get('datetime'):
        run['date'] = str(data['datetime'])[:10]
    laser = _read(
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
    substrates, by_reference = _substrates_to_form(data, sections)
    steps = _steps_to_form(data, sections, system, substrates, by_reference)

    form = {
        'run': run,
        'laser': laser,
        'targets': targets,
        'substrates': substrates,
        'steps': steps,
        'in_situ': _in_situ_to_form(data, sections),
    }
    recipe = (data.get('load_recipe') or {}).get('recipe')
    if recipe:
        form['recipe'] = recipe
    return form


def recipe_to_form(data: dict, spec: dict) -> dict:
    """The steps (and targets) of a recipe, without substrate links."""
    form = archive_to_form(data, spec)
    for step in form['steps']:
        step.pop('substrate', None)
    return {
        'system': form['run']['system'],
        'targets': form['targets'],
        'steps': form['steps'],
    }
