"""
Sputter logbook dashboard: a guided form for runs in the SPS sputter system,
built like the PLD logbook dashboard (see `dashboards.pld_logbook`).
"""

from nomad.config.models.plugins import DashboardEntryPoint


class SputterLogbookDashboardEntryPoint(DashboardEntryPoint):
    def load(self):
        from differ_pld4e_schemas.dashboards.sputter_logbook.app import create_app

        return create_app()


sputter_logbook_dashboard_entry_point = SputterLogbookDashboardEntryPoint(
    name='Sputter logbook',
    id_url_safe='differ_pld4e_schemas-sputter-logbook',
    description=(
        'Fill in the logbook of an SPS sputter run step by step, starting from its '
        'samples. Only the fields that apply are shown, and the logbook is saved '
        'only when it is complete; until then it can be kept as a draft.'
    ),
    launch_modes=['embedded', 'tab'],
)
