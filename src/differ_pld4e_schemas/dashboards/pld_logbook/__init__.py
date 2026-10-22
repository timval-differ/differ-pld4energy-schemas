"""
PLD logbook dashboard: a guided form for SA-PLD and LA-PLD runs.

Unlike the NOMAD entry editor, the form shows only the fields that apply to the
choices made (system, scan type, gases, techniques, ...) and only saves once
every required field is filled in.
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
        'Fill in the logbook of an SA-PLD or LA-PLD run step by step. Only the '
        'fields that apply are shown, and the logbook is saved only when it is '
        'complete.'
    ),
    launch_modes=['embedded', 'tab'],
)
