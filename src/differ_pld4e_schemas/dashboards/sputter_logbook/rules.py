"""
Computed values and validation of the sputter logbook form; the rules are
those of `dashboards.common.rules`.
"""

from __future__ import annotations

from differ_pld4e_schemas.sps_deposition import SPS

from ..common.rules import LogbookRules

__all__ = ['RULES', 'compute', 'sample_films', 'validate', 'validate_draft']

# Step types that grow a film on their samples.
FILM_STEPS = ('sputtering',)
# A sputtering step covers the samples its sample mask leaves open.
MASK_SYSTEMS = (SPS,)

RULES = LogbookRules(FILM_STEPS, MASK_SYSTEMS)
compute = RULES.compute
sample_films = RULES.sample_films
validate = RULES.validate
validate_draft = RULES.validate_draft
