"""
Computed values and validation of the PLD logbook form; the shared rules are
in `dashboards.common.rules`.

Besides the common sections, the form data has `'laser': {...}` and
`'in_situ': {...}`.
"""

from __future__ import annotations

from ..common.rules import LogbookRules, section_requirement
from ..common.values import (
    evaluate,
    is_empty,
    options,
    to_number,
    visible_fields,
)

__all__ = [
    'RULES',
    'compute',
    'evaluate',
    'is_empty',
    'options',
    'sample_films',
    'section_requirement',
    'to_number',
    'validate',
    'validate_draft',
    'visible_fields',
]

# Step types that grow a film on their samples.
FILM_STEPS = ('deposition',)
# SA-PLD deposits on all samples in the chamber, LA-PLD on the chosen one.
ALL_SAMPLES = ('SA-PLD',)


def transmission_window_1(local: dict, root: dict):
    # Same formula as differ_pld4e_schemas.laser.transmission_window_1.
    before = to_number(local.get('energy_before_chamber'))
    after = to_number(local.get('energy_after_chamber'))
    t2 = to_number(local.get('transmission_window_2'))
    if before is None or after is None or not before or not t2:
        return None
    return after / (before * t2 / 100) * 100


RULES = LogbookRules(
    FILM_STEPS,
    ALL_SAMPLES,
    extra_computed={'transmission_window_1': transmission_window_1},
)
compute = RULES.compute
sample_films = RULES.sample_films
validate = RULES.validate
validate_draft = RULES.validate_draft
