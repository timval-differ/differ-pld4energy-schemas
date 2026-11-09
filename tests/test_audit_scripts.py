"""The read-only audit scripts in scripts/."""

import importlib.util
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_shifted_step_times_are_found():
    audit = _load('audit_shifted_step_times')
    run = '2026-10-22T07:15:00+00:00'  # 09:15 on the lab clock
    good = {'datetime': run, 'steps': [{'start_time': '2026-10-22T07:20:00+00:00'}]}
    # Re-saved before the fix: 09:20 read as UTC, saved as 09:20+02:00.
    shifted = {
        'datetime': run,
        'steps': [{'start_time': '2026-10-22T05:20:00+00:00'}, {}],
    }
    assert audit.suspicious(good) == []
    assert audit.suspicious(shifted) == ['step 1 starts 1:55:00 before the run']
    assert audit.suspicious({'steps': []}) == []
