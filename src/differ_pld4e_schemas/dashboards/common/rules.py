"""
Computed values and validation of a logbook form.

`static/app.js` implements the same rules for live feedback in the browser;
the server always validates again before an archive is built.

Form data layout::

    {
        'run': {...}, 'chamber': {...},                      # object sections
        'samples': [{'uid': ..., ...}, ...],                 # list sections
        'targets': [{'uid': ..., ...}, ...],
        'steps': [{'uid': ..., 'type': ..., ...}, ...],
    }

Conditions are described in `dashboards.common.values`.
"""

from __future__ import annotations

from .samples import (
    MADE_HERE,
    NEW_SAMPLE,
    compute_sample_id,
    compute_sample_name,
    sample_choices,
)
from .values import (
    evaluate,
    is_empty,
    options,
    parse_date,
    parse_time,
    step_times,
    to_number,
    visible_fields,
)

LEVELS = ('none', 'optional', 'required')


def sample_choice(item: dict):
    """How a step refers to a sample of the run (see `sample_choices`)."""
    if item.get('origin', NEW_SAMPLE) in MADE_HERE:
        return f'new:{item.get("uid")}'
    return item.get('sample')


def film_thickness(step: dict) -> dict:
    """{'thickness'} in nm or {'pulses'}, as chosen with `film_thickness_unit`."""
    if step.get('film_thickness_unit') == 'pulses':
        return {'pulses': step.get('film_thickness_pulses')}
    return {'thickness': step.get('film_thickness')}


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
    if 'max' in field and number > field['max']:
        return f'Must be at most {field["max"]}.'
    return None


def step_choices(root: dict) -> list:
    """Values a measurement uses to name a process step of the run."""
    return [step.get('uid') for step in root.get('steps') or [] if step.get('uid')]


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
        'step_choice': (
            lambda: set(value) <= set(step_choices(root)),
            'Choose steps listed under Process steps.',
        ),
    }
    if kind in checks:
        is_valid, message = checks[kind]
        return None if is_valid() else message
    return None


def _validate_step_times(root: dict) -> list[dict]:
    steps = root.get('steps') or []
    return [
        {
            'path': f'steps.{index}.end_time',
            'message': 'The end time is before the start time.',
        }
        for index, (start, end) in enumerate(step_times(root.get('run') or {}, steps))
        if start and end and end < start
    ]


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


class LogbookRules:
    """
    The rules of one logbook dashboard.

    film_steps         step types that grow a film on their samples
    all_samples        systems whose film steps cover every sample of the run;
                       in the others a step names its one sample
    extra_computed     {name: function(local, root)} computed values besides
                       the sample ID and name
    """

    def __init__(
        self,
        film_steps: tuple,
        all_samples: tuple = (),
        extra_computed: dict | None = None,
    ):
        self.film_steps = tuple(film_steps)
        self.all_samples = tuple(all_samples)
        self.extra_computed = dict(extra_computed or {})

    def step_applies_to(self, step: dict, choice, root: dict) -> bool:
        if (root.get('run') or {}).get('system') in self.all_samples:
            return True
        return step.get('sample') == choice

    def sample_films(self, item: dict, root: dict) -> list:
        """
        The films grown on a sample in this run, in order: one per film step
        on it, from the step's target (its material as selected under Targets)
        and film thickness, in nm or as a number of pulses.
        """
        materials = {
            t.get('target'): t.get('material') for t in root.get('targets') or []
        }
        choice = sample_choice(item)
        return [
            {
                'target': step.get('target'),
                'material': materials.get(step.get('target')),
                **film_thickness(step),
            }
            for step in root.get('steps') or []
            if step.get('type') in self.film_steps
            and self.step_applies_to(step, choice, root)
        ]

    def compute(self, name: str, local: dict, root: dict):
        if name in self.extra_computed:
            return self.extra_computed[name](local, root)
        if name == 'sample_id':
            return compute_sample_id(local, root)
        if name == 'sample_name':
            return compute_sample_name(local, root, self.sample_films(local, root))
        raise ValueError(f'Unknown computed value {name}')

    def value_of(self, field: dict, local: dict, root: dict):
        if field['kind'] == 'computed':
            return self.compute(field['compute'], local, root)
        return local.get(field['key'])

    def _validate_unique(self, section, items, root, errors):
        fields = {f['key']: f for f in section.get('fields', [])}
        for key in section.get('unique', []):
            seen = set()
            for index, item in enumerate(items):
                field = fields[key]
                if not evaluate(field.get('visible_if'), item, root):
                    continue
                value = self.value_of(field, item, root)
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

    def validate(self, data: dict, spec: dict) -> list[dict]:
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
                errors += _validate_fields(
                    section['fields'], local, key, data, required
                )
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
                            {
                                'path': f'{key}.{index}.type',
                                'message': 'Unknown step type.',
                            }
                        )
                        continue
                    fields = variant['fields']
                errors += _validate_fields(
                    fields, item, f'{key}.{index}', data, required
                )
            if section['kind'] == 'list':
                self._validate_unique(section, items, data, errors)
        errors += _validate_step_times(data)
        return errors

    @staticmethod
    def validate_draft(data: dict, spec: dict) -> list[dict]:
        """
        What a draft needs: the system, date and time, which name the draft
        file and make up the sample IDs. Everything else may still be missing.
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
