"""
Reading form values and evaluating conditions. The browser page mirrors these
functions so the form reacts while typing.

Condition keys are looked up in the containing object, or from the form root
when they start with '/', e.g. '/run/system'. Conditions:

    {'all': [...]}, {'any': [...]}
    {'key': ..., 'equals': value}   booleans compare truthiness
    {'key': ..., 'in': [...]}
    {'key': ..., 'has_type': [...]} a list (e.g. '/steps') has an item of a type
"""

from __future__ import annotations

import math
import re
from datetime import date, time


def lookup(key: str, local: dict, root: dict):
    if not key.startswith('/'):
        return local.get(key)
    value = root
    for part in key.strip('/').split('/'):
        value = value.get(part) if isinstance(value, dict) else None
    return value


def _equals(value, expected) -> bool:
    if isinstance(expected, bool):
        return bool(value) == expected
    return value == expected


def _has_type(value, types) -> bool:
    return any(
        isinstance(item, dict) and item.get('type') in types for item in value or []
    )


COMPARISONS = {
    'equals': _equals,
    'in': lambda value, options: value in options,
    'has_type': _has_type,
}


def evaluate(condition: dict | None, local: dict, root: dict) -> bool:
    if not condition:
        return True
    if 'all' in condition:
        return all(evaluate(c, local, root) for c in condition['all'])
    if 'any' in condition:
        return any(evaluate(c, local, root) for c in condition['any'])
    value = lookup(condition['key'], local, root)
    for name, compare in COMPARISONS.items():
        if name in condition:
            return compare(value, condition[name])
    raise ValueError(f'Unknown condition {condition}')


def options(field: dict, local: dict, root: dict) -> list:
    if 'options_by' in field:
        by = field['options_by']
        return by['map'].get(lookup(by['key'], local, root), [])
    return field.get('options') or []


def visible_fields(fields: list, local: dict, root: dict) -> list:
    return [f for f in fields if evaluate(f.get('visible_if'), local, root)]


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


def parse_time(value):
    """A time from 'HH:MM', or None."""
    if not isinstance(value, str) or not re.fullmatch(r'\d{2}:\d{2}', value):
        return None
    try:
        return time.fromisoformat(value)
    except ValueError:
        return None


def is_empty(value) -> bool:
    return value is None or value in ('', [])
