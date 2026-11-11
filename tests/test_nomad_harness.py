"""
The test harness collects NOMAD's log messages the same way whether NOMAD
logs through structlog (installed with its infrastructure extras, as in the
distribution) or through the standard logging module (as in the plugin's CI).
"""

import logging

from helpers.nomad_harness import _LogRecords, warnings
from nomad.utils import ClassicLogger


def test_events_logged_without_structlog_have_no_bound_values():
    records = _LogRecords()
    root = logging.getLogger()
    level = root.level
    root.addHandler(records)
    root.setLevel(logging.DEBUG)
    try:
        # What NOMAD's normalizers log in CI: values bound to the logger.
        ClassicLogger('t').bind(normalizer='MetainfoNormalizer').warning('A (1) b.')
        ClassicLogger('t').warning('no values')
        ClassicLogger('t').warning('two', a=1, b='x y')
    finally:
        root.removeHandler(records)
        root.setLevel(level)
    assert warnings(records.logs) == ['A (1) b.', 'no values', 'two']
