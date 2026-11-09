"""Shared test helpers; tests/ is on the pytest pythonpath."""

# The upload of the target and substrate database in the tests.
DATABASE_UPLOAD = 'target_db'

# NOMAD sets the creation time of every entry it processes; logbooks without
# a start of the run take it (base_sections.RunDetails.default_datetime).
ENTRY_CREATE_TIME = '2026-10-22T07:00:00+00:00'
