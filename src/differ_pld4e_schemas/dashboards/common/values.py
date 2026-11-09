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
from datetime import date, time, timedelta

from differ_pld4e_schemas.time_zone import lab_instant


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


# A number as typed in the form, after a decimal comma became '.'. The same
# patterns are in static/rules.js (toNumber); the parity tests check they agree.
NUMBER = re.compile(r'[-+]?([0-9]+\.?[0-9]*|\.[0-9]+)([eE][-+]?[0-9]+)?')
# '12,000' or '1,500': a comma that may group thousands rather than mark
# decimals. Read as a decimal comma it would silently store 12 or 1.5.
THOUSANDS = re.compile(r'[-+]?[1-9][0-9]{0,2},[0-9]{3}([eE][-+]?[0-9]+)?')
DATE = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}')


def decimal_comma(text: str) -> str | None:
    """
    `text` with a decimal comma (as typed on many keyboards) made a '.', or
    None if its comma is ambiguous: more than one, a comma and a dot, or what
    may be a thousands separator ('12,000'). '12,5', '0,125' and '1,5e-8' are
    decimals.
    """
    if ',' not in text:
        return text
    if text.count(',') > 1 or '.' in text or THOUSANDS.fullmatch(text):
        return None
    return text.replace(',', '.')


def to_number(value):
    """A float, or None if the value is not a number."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            number = float(value)
        except OverflowError:  # a JSON integer beyond the range of a float
            return None
        return number if math.isfinite(number) else None
    if isinstance(value, str):
        text = decimal_comma(value.strip())
        if text is None or not NUMBER.fullmatch(text):
            return None
        number = float(text)
        return number if math.isfinite(number) else None
    return None


def is_grouped_number(value) -> bool:
    """A text that is a number but for its commas, e.g. '12,000' or '1.000,5'."""
    if not isinstance(value, str) or ',' not in value:
        return False
    return bool(NUMBER.fullmatch(value.strip().replace(',', '')))


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


# A step time this much before the previous time is on the next day.
NEXT_DAY_AFTER = timedelta(hours=12)


def step_times(run: dict, steps: list) -> list[tuple]:
    """
    (start, end) datetimes of each step, None where not given. A step only has
    hh:mm times on the lab's clock: the day is that of the run start, and moves
    on to the next day when a time is far (12 h) before the time before it,
    e.g. 00:10 after 23:30. A time a bit earlier stays on the same day, so an
    end before its start can be reported. The datetimes are in the lab's time
    zone; subtract them in UTC (see convert.seconds_between).
    """
    day, clock = parse_date(run.get('date')), parse_time(run.get('time'))
    if day is None or clock is None:
        return [(None, None) for _ in steps]
    previous = lab_instant(day, clock)
    times = []
    for step in steps:
        pair = []
        for key in ('start_time', 'end_time'):
            clock = parse_time(step.get(key))
            if clock is None:
                pair.append(None)
                continue
            moment = lab_instant(previous.date(), clock)
            # Compared on the clock: the rule is about the times as noted.
            if previous.replace(tzinfo=None) - moment.replace(tzinfo=None) > (
                NEXT_DAY_AFTER
            ):
                moment = lab_instant(previous.date() + timedelta(days=1), clock)
            pair.append(moment)
            previous = moment
        times.append(tuple(pair))
    return times


def is_empty(value) -> bool:
    """Nothing entered: also a text of only spaces."""
    if isinstance(value, str):
        return not value.strip()
    return value is None or value == []
