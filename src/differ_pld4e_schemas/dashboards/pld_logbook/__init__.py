"""
PLD logbook dashboard: a guided form for SA-PLD and LA-PLD runs.

Unlike the NOMAD entry editor, the form shows only the fields that apply to the
choices made (system, process steps, scan type, gases, techniques, ...) and only
saves a logbook once every required field is filled in. Incomplete runs can be
kept as drafts in the upload, which are not entries.
"""

from nomad.config.models.plugins import DashboardEntryPoint


class PLDLogbookDashboardEntryPoint(DashboardEntryPoint):
    def load(self):
        from differ_pld4e_schemas.dashboards.pld_logbook.app import create_app

        return create_app()


pld_logbook_dashboard_entry_point = PLDLogbookDashboardEntryPoint(
    name='PLD logbook',
    id_url_safe='differ_pld4e_schemas-pld-logbook',
    description=(
        'Fill in the logbook of an SA-PLD or LA-PLD run step by step, starting '
        'from its samples. Only the fields that apply are shown, and the logbook '
        'is saved only when it is complete; until then it can be kept as a draft.'
    ),
    launch_modes=['embedded', 'tab'],
)
