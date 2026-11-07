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
from datetime import date, datetime, time, timedelta, timezone


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


# A number as typed in the form, after its first ',' became '.'. The same
# pattern is in static/rules.js (toNumber); the parity tests check they agree.
NUMBER = re.compile(r'[-+]?([0-9]+\.?[0-9]*|\.[0-9]+)([eE][-+]?[0-9]+)?')
DATE = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}')


def to_number(value):
    """A float, or None if the value is not a number."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(value) else None
    if isinstance(value, str):
        # A decimal comma, as typed on many keyboards; not '1_000' or '1e5,0'.
        text = value.strip().replace(',', '.', 1)
        if not NUMBER.fullmatch(text):
            return None
        number = float(text)
        return number if math.isfinite(number) else None
    return None


def parse_date(value):
    """A date from 'yyyy-mm-dd' (a real one: not 2026-02-30), or None."""
    if not isinstance(value, str) or not DATE.fullmatch(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def parse_time(value):
    """A time from 'HH:MM', or None."""
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{2}:[0-9]{2}', value):
        return None
    try:
        return time.fromisoformat(value)
    except ValueError:
        return None


def run_timezone(run: dict) -> timezone:
    offset = run.get('utc_offset')
    match = isinstance(offset, str) and re.fullmatch(r'([+-])(\d{2}):(\d{2})', offset)
    if not match:
        return timezone.utc
    sign = -1 if match[1] == '-' else 1
    return timezone(sign * timedelta(hours=int(match[2]), minutes=int(match[3])))


# A step time this much before the previous time is on the next day.
NEXT_DAY_AFTER = timedelta(hours=12)


def step_times(run: dict, steps: list) -> list[tuple]:
    """
    (start, end) datetimes of each step, None where not given. A step only has
    hh:mm times: the day is that of the run start, and moves on to the next day
    when a time is far (12 h) before the time before it, e.g. 00:10 after 23:30.
    A time a bit earlier stays on the same day, so an end before its start can
    be reported.
    """
    day, clock = parse_date(run.get('date')), parse_time(run.get('time'))
    if day is None or clock is None:
        return [(None, None) for _ in steps]
    previous = datetime.combine(day, clock, run_timezone(run))
    times = []
    for step in steps:
        pair = []
        for key in ('start_time', 'end_time'):
            clock = parse_time(step.get(key))
            if clock is None:
                pair.append(None)
                continue
            moment = datetime.combine(previous.date(), clock, previous.tzinfo)
            if previous - moment > NEXT_DAY_AFTER:
                moment += timedelta(days=1)
            pair.append(moment)
            previous = moment
        times.append(tuple(pair))
    return times


def is_empty(value) -> bool:
    return value is None or value in ('', [])
