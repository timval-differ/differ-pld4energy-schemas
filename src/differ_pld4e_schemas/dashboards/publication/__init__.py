"""
Publication dashboard: export an upload as one self-contained ZIP, to publish
on the central NOMAD.

The ZIP holds the upload and every entry it refers to in other uploads (the
targets and substrate types of the database), with references rewritten to
stay inside it; see `differ_pld4e_schemas.snapshot`.
"""

from nomad.config.models.plugins import DashboardEntryPoint


class PublicationDashboardEntryPoint(DashboardEntryPoint):
    def load(self):
        from differ_pld4e_schemas.dashboards.publication.app import create_app

        return create_app()


publication_dashboard_entry_point = PublicationDashboardEntryPoint(
    name='Export for publication',
    id_url_safe='differ_pld4e_schemas-publication',
    description=(
        'Export an upload with the targets and substrates it uses as one ZIP, '
        'to publish it on the central NOMAD.'
    ),
    launch_modes=['embedded', 'tab'],
)
