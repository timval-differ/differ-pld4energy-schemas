"""
Computed values and validation of the PLD logbook form.

`static/app.js` implements the same rules for live feedback in the browser;
the server always validates again before an archive is built.

Form data layout::

    {
        'run': {...}, 'chamber': {...}, 'laser': {...},     # object sections
        'in_situ': {...},
        'samples': [{'uid': ..., ...}, ...],                 # list sections
        'targets': [{'uid': ..., ...}, ...],
        'steps': [{'uid': ..., 'type': 'deposition', ...}, ...],
    }

Conditions are described in `dashboards.common.values`.
"""

from __future__ import annotations

from ..common.samples import (
    MADE_HERE,
    NEW_SAMPLE,
    compute_sample_id,
    compute_sample_name,
    sample_choices,
)
from ..common.values import (
    evaluate,
    is_empty,
    options,
    parse_date,
    parse_time,
    to_number,
    visible_fields,
)

__all__ = [
    'compute',
    'evaluate',
    'is_empty',
    'options',
    'section_requirement',
    'to_number',
    'validate',
    'validate_draft',
    'visible_fields',
]

LEVELS = ('none', 'optional', 'required')
# Step types that grow a film on their samples.
FILM_STEPS = ('deposition',)


def sample_choice(item: dict):
    """How a step refers to a sample of the run (see `sample_choices`)."""
    if item.get('origin', NEW_SAMPLE) in MADE_HERE:
        return f'new:{item.get("uid")}'
    return item.get('sample')


def step_applies_to(step: dict, choice, root: dict) -> bool:
    """SA-PLD deposits on all samples in the chamber, LA-PLD on the chosen one."""
    if (root.get('run') or {}).get('system') == 'SA-PLD':
        return True
    return step.get('sample') == choice


def sample_films(item: dict, root: dict) -> list:
    """
    The films grown on a sample in this run, in order: one per deposition step
    on it, from the step's target (its material as selected under Targets) and
    film thickness.
    """
    materials = {t.get('target'): t.get('material') for t in root.get('targets') or []}
    choice = sample_choice(item)
    return [
        {
            'target': step.get('target'),
            'material': materials.get(step.get('target')),
            'thickness': step.get('film_thickness'),
        }
        for step in root.get('steps') or []
        if step.get('type') in FILM_STEPS and step_applies_to(step, choice, root)
    ]


def compute(name: str, local: dict, root: dict):
    if name == 'transmission_window_1':
        # Same formula as differ_pld4e_schemas.laser.transmission_window_1.
        before = to_number(local.get('energy_before_chamber'))
        after = to_number(local.get('energy_after_chamber'))
        t2 = to_number(local.get('transmission_window_2'))
        if before is None or after is None or not before or not t2:
            return None
        return after / (before * t2 / 100) * 100
    if name == 'sample_id':
        return compute_sample_id(local, root)
    if name == 'sample_name':
        return compute_sample_name(local, root, sample_films(local, root))
    raise ValueError(f'Unknown computed value {name}')


def value_of(field: dict, local: dict, root: dict):
    if field['kind'] == 'computed':
        return compute(field['compute'], local, root)
    return local.get(field['key'])


def _steps_section(spec: dict) -> dict | None:
    return next((s for s in spec['sections'] if s['kind'] == 'variant_list'), None)


def step_level(variant: dict, item: dict, aspect: str) -> str:
    """What one step needs of an aspect: an optional laser counts once used."""
    level = variant.get(aspect, 'none')
    if level == 'optional' and item.get(f'{aspect}_used'):
        return 'required'
    return level


def section_requirement(section: dict, spec: dict, data: dict) -> str:
    """
    'required', 'optional' or 'none'. A section with a `requirement` is needed
    as much as the step that needs it most; e.g. the laser details are required
    once there is a deposition step and not logged at all for an annealing run.
    """
    requirement = section.get('requirement')
    if not requirement:
        return 'required'
    steps = _steps_section(spec)
    if steps is None:
        return 'none'
    level = 'none'
    for item in data.get(steps['key']) or []:
        variant = steps['variants'].get(item.get('type'))
        if variant is not None:
            level = max(
                level,
                step_level(variant, item, requirement['from_steps']),
                key=LEVELS.index,
            )
    return level


def target_choices(root: dict) -> list:
    return [t['target'] for t in root.get('targets') or [] if t.get('target')]


def _number_error(field: dict, value) -> str | None:
    number = to_number(value)
    if number is None:
        return 'Enter a number.'
    if field['kind'] == 'integer' and number != int(number):
        return 'Enter a whole number.'
    if 'min' in field and number < field['min']:
        return f'Must be at least {field["min"]}.'
    return None


def _field_error(field: dict, value, local: dict, root: dict) -> str | None:
    kind = field['kind']
    if kind in ('number', 'integer'):
        return _number_error(field, value)
    checks = {
        'select': (
            lambda: value in options(field, local, root),
            'Choose one of the options.',
        ),
        'date': (lambda: parse_date(value) is not None, 'Enter a date.'),
        'time': (lambda: parse_time(value) is not None, 'Enter a time (hh:mm).'),
        'target_choice': (
            lambda: value in target_choices(root),
            'Choose one of the targets selected under Targets.',
        ),
        'sample_choice': (
            lambda: value in sample_choices(root),
            'Choose one of the samples under Samples.',
        ),
    }
    if kind in checks:
        is_valid, message = checks[kind]
        return None if is_valid() else message
    return None


def _validate_fields(fields, local, path, root, required=True) -> list[dict]:
    """
    Problems of the visible fields; with `required` False only badly entered
    values count, not missing ones.
    """
    errors = []
    for field in visible_fields(fields, local, root):
        if field['kind'] == 'computed':
            continue
        value = local.get(field['key'])
        field_path = f'{path}.{field["key"]}'
        if field['kind'] == 'rows':
            for index, row in enumerate(value or []):
                errors += _validate_fields(
                    field['columns'], row, f'{field_path}.{index}', root, required
                )
            continue
        if is_empty(value):
            if (
                field['required']
                and required
                and evaluate(field.get('required_if'), local, root)
            ):
                errors.append({'path': field_path, 'message': 'Required.'})
            continue
        message = _field_error(field, value, local, root)
        if message:
            errors.append({'path': field_path, 'message': message})
    return errors


def _validate_unique(section, items, root, errors):
    fields = {f['key']: f for f in section.get('fields', [])}
    for key in section.get('unique', []):
        seen = set()
        for index, item in enumerate(items):
            field = fields[key]
            if not evaluate(field.get('visible_if'), item, root):
                continue
            value = value_of(field, item, root)
            if is_empty(value):
                continue
            if value in seen:
                errors.append(
                    {
                        'path': f'{section["key"]}.{index}.{key}',
                        'message': f'{field["label"]} is used more than once.',
                    }
                )
            seen.add(value)


def validate(data: dict, spec: dict) -> list[dict]:
    """All problems in the form as {'path', 'message'}; empty if complete."""
    errors: list[dict] = []
    for section in spec['sections']:
        key = section['key']
        level = section_requirement(section, spec, data)
        if level == 'none':
            continue
        required = level == 'required'
        if section['kind'] == 'object':
            local = data.get(key) or {}
            errors += _validate_fields(section['fields'], local, key, data, required)
            continue
        items = data.get(key) or []
        if required and len(items) < section.get('min_items', 0):
            errors.append(
                {
                    'path': key,
                    'message': f'Add at least one {section["item_label"].lower()}.',
                }
            )
        for index, item in enumerate(items):
            fields = section.get('fields')
            if section['kind'] == 'variant_list':
                variant = section['variants'].get(item.get('type'))
                if variant is None:
                    errors.append(
                        {'path': f'{key}.{index}.type', 'message': 'Unknown step type.'}
                    )
                    continue
                fields = variant['fields']
            errors += _validate_fields(fields, item, f'{key}.{index}', data, required)
        if section['kind'] == 'list':
            _validate_unique(section, items, data, errors)
    return errors


def validate_draft(data: dict, spec: dict) -> list[dict]:
    """
    What a draft needs: the system, date and time, which name the draft file and
    make up the sample IDs. Everything else may still be missing.
    """
    run = data.get('run') or {}
    errors = []
    if run.get('system') not in spec['systems']:
        errors.append({'path': 'run.system', 'message': 'Choose the PVD system.'})
    if parse_date(run.get('date')) is None:
        errors.append({'path': 'run.date', 'message': 'Enter a date.'})
    if parse_time(run.get('time')) is None:
        errors.append({'path': 'run.time', 'message': 'Enter a time (hh:mm).'})
    return errors
