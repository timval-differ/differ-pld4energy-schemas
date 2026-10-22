"""
Conditions, computed values and validation of the PLD logbook form.

`static/app.js` implements the same rules for live feedback in the browser;
the server always validates again before an archive is built.

Form data layout::

    {
        'run': {...}, 'laser': {...}, 'in_situ': {...},  # object sections
        'targets': [{'uid': ..., ...}, ...],               # list sections
        'substrates': [{'uid': ..., ...}, ...],
        'steps': [{'uid': ..., 'type': 'deposition', ...}, ...],
    }

Condition keys are looked up in the containing object, or from the form root
when they start with '/', e.g. '/run/system'.
"""

from __future__ import annotations

import math
from datetime import date

from differ_pld4e_schemas.pld_substrate import sample_user_id

NEW_SUBSTRATE = 'Create new substrate'


def lookup(key: str, local: dict, root: dict):
    if not key.startswith('/'):
        return local.get(key)
    value = root
    for part in key.strip('/').split('/'):
        value = value.get(part) if isinstance(value, dict) else None
    return value


def evaluate(condition: dict | None, local: dict, root: dict) -> bool:
    if not condition:
        return True
    if 'all' in condition:
        return all(evaluate(c, local, root) for c in condition['all'])
    if 'any' in condition:
        return any(evaluate(c, local, root) for c in condition['any'])
    value = lookup(condition['key'], local, root)
    if 'equals' in condition:
        expected = condition['equals']
        if isinstance(expected, bool):
            return bool(value) == expected
        return value == expected
    if 'in' in condition:
        return value in condition['in']
    raise ValueError(f'Unknown condition {condition}')


def options(field: dict, local: dict, root: dict) -> list:
    if 'options_by' in field:
        by = field['options_by']
        return by['map'].get(lookup(by['key'], local, root), [])
    return field.get('options') or []


def to_number(value):
    """A float, or None if the value is not a number."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(value) else None
    if isinstance(value, str):
        try:
            number = float(value.replace(',', '.'))
        except ValueError:
            return None
        return number if math.isfinite(number) else None
    return None


def parse_date(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def compute(name: str, local: dict, root: dict):
    if name == 'transmission_window_1':
        # Same formula as differ_pld4e_schemas.laser.transmission_window_1.
        before = to_number(local.get('energy_before_chamber'))
        after = to_number(local.get('energy_after_chamber'))
        t2 = to_number(local.get('transmission_window_2'))
        if before is None or after is None or not before or not t2:
            return None
        return after / (before * t2 / 100) * 100
    if name == 'sample_user_id':
        return sample_user_id(
            lookup('/run/system', local, root),
            parse_date(lookup('/run/date', local, root)),
            local.get('run_number'),
            local.get('sample_number'),
        )
    raise ValueError(f'Unknown computed value {name}')


def value_of(field: dict, local: dict, root: dict):
    if field['kind'] == 'computed':
        return compute(field['compute'], local, root)
    return local.get(field['key'])


def is_empty(value) -> bool:
    return value is None or value in ('', [])


def target_choices(root: dict) -> list:
    return [t['target'] for t in root.get('targets') or [] if t.get('target')]


def substrate_choices(root: dict) -> list:
    choices = []
    for substrate in root.get('substrates') or []:
        if substrate.get('mode', NEW_SUBSTRATE) == NEW_SUBSTRATE:
            choices.append(f'new:{substrate.get("uid")}')
        elif substrate.get('substrate'):
            choices.append(substrate['substrate'])
    return choices


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
        'target_choice': (
            lambda: value in target_choices(root),
            'Choose one of the targets selected under Targets.',
        ),
        'substrate_choice': (
            lambda: value in substrate_choices(root),
            'Choose one of the substrates under Substrates.',
        ),
    }
    if kind in checks:
        is_valid, message = checks[kind]
        return None if is_valid() else message
    return None


def visible_fields(fields: list, local: dict, root: dict) -> list:
    return [f for f in fields if evaluate(f.get('visible_if'), local, root)]


def _validate_fields(fields, local, path, root, errors):
    for field in visible_fields(fields, local, root):
        if field['kind'] == 'computed':
            continue
        value = local.get(field['key'])
        field_path = f'{path}.{field["key"]}'
        if is_empty(value):
            if field['required']:
                errors.append({'path': field_path, 'message': 'Required.'})
            continue
        message = _field_error(field, value, local, root)
        if message:
            errors.append({'path': field_path, 'message': message})


def _validate_rules(rules, local, path, root, errors):
    for rule in rules or []:
        if rule['type'] == 'any_of' and evaluate(rule.get('visible_if'), local, root):
            if all(is_empty(local.get(key)) for key in rule['keys']):
                errors.append(
                    {'path': f'{path}.{rule["keys"][0]}', 'message': rule['message']}
                )


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
        if section['kind'] == 'object':
            local = data.get(key) or {}
            _validate_fields(section['fields'], local, key, data, errors)
            _validate_rules(section.get('rules'), local, key, data, errors)
            continue
        items = data.get(key) or []
        if len(items) < section.get('min_items', 0):
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
            _validate_fields(fields, item, f'{key}.{index}', data, errors)
        if section['kind'] == 'list':
            _validate_unique(section, items, data, errors)
        for variant_key in section.get('required_variants', []):
            if not any(item.get('type') == variant_key for item in items):
                label = section['variants'][variant_key]['label'].lower()
                errors.append({'path': key, 'message': f'Add at least one {label}.'})
    return errors
