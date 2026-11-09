"""
The entries the test forms refer to, as the archive dicts NOMAD would return:
the target and substrate database upload and an upload with an existing
sample. Built from the plugin's own classes so they follow the schema.
"""

from differ_pld4e_schemas.sample import Sample, SubstrateType
from differ_pld4e_schemas.target import PLDTarget, SputterTarget
from helpers import DATABASE_UPLOAD

SAMPLE_UPLOAD = 'u0'
INCH = 0.0254


def _entry(section):
    return {'data': section.m_to_dict(with_root_def=True)}


def database_uploads():
    """{upload_id: {entry_id: archive dict}} for `LocalUpload`."""
    return {
        DATABASE_UPLOAD: {
            'target1': _entry(PLDTarget(name='STO 1', material='SrTiO3')),
            'target2': _entry(PLDTarget(name='YSZ 1', material='8YSZ')),
            'ta': _entry(SputterTarget(name='Ta', material='Ta', diameter=2 * INCH)),
            'ti': _entry(SputterTarget(name='Ti', material='Ti', diameter=2 * INCH)),
            'substrate_si': _entry(
                SubstrateType(name='Si 1"', material='Si', size='1" with flat')
            ),
        },
        SAMPLE_UPLOAD: {
            'sample0': _entry(
                Sample(sample_id='LA-PLD_2026-01-05_10:00_S01', name='Si_STO-20nm')
            ),
        },
    }
